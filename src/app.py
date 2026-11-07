"""Entrypoint de PULSO: monolito FastAPI que Vercel detecta automáticamente (`app`).

Local: uvicorn src.app:app --reload
"""

from __future__ import annotations

import hashlib
import logging
import re
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from pydantic import ValidationError

from src.engine.collisions import MIN_EVALUACIONES, Colision, detectar_colisiones
from src.engine.load_index import carga_semanal_cohorte, evaluaciones_por_semana, semana_de, semana_pico
from src.extraction.batch import CACHE_POR_DEFECTO, ReporteSilabo, guardar_cohorte, procesar_cohorte
from src.extraction.llm import config_llm, crear_cliente
from src.extraction.llm_parser import ResultadoExtraccion, extraer_evaluaciones
from src.extraction.pdf_reader import leer_pdf
from src.extraction.proposal import Propuesta, generar_propuesta
from src.formato import nombre_curso
from src.models import SEMANAS_CICLO, Cohorte, Evaluacion, TipoEvaluacion, cargar_cohorte
from src.optimizer.objective import ResultadoOptimizacion, optimizar
from src.optimizer.simulator import simular
from src.api import router as api_router

RAIZ = Path(__file__).resolve().parent.parent
logger = logging.getLogger("pulso")
DIR_UI = Path(__file__).resolve().parent / "ui"

# En Vercel el filesystem es de solo lectura salvo /tmp: ahí van la caché de extracción y la cohorte subida.
DIR_TMP = Path(tempfile.gettempdir()) / "pulso"

# Fuentes de datos seleccionables: clave -> (etiqueta, ruta del JSON de cohorte).
# Cada una aparece en el selector solo si su JSON existe.
FUENTES: dict[str, tuple[str, Path]] = {
    "cohorte": ("Cohorte extraída de los sílabos", RAIZ / "data" / "cohorte.json"),  # PUL-07
    "subida": ("Sílabos subidos en la app", DIR_TMP / "cohorte-subida.json"),  # POST /simulacion
    "mock": ("Datos de ejemplo (mock)", RAIZ / "data" / "mock" / "evaluaciones_mock.json"),
}
# Los datos reales reemplazan al mock (PUL-17); el mock queda como respaldo.
FUENTE_POR_DEFECTO = "cohorte" if FUENTES["cohorte"][1].is_file() else "mock"

# Otros ciclos de la carrera para compararlos: data/cohortes/ciclo-01.json, ciclo-02.json…
# (los genera scripts/procesar_cohorte.py con --salida). Cada uno es también una fuente más.
DIR_CICLOS = RAIZ / "data" / "cohortes"
PATRON_CICLO = re.compile(r"ciclo-0*(\d+)", re.IGNORECASE)


def registrar_ciclos(carpeta: Path) -> dict[str, tuple[str, Path]]:
    """Fuentes `ciclo-NN` de la carpeta, ordenadas por número de ciclo. No abre los JSON (se validan al usarlos)."""
    ciclos = {}
    for ruta in sorted(carpeta.glob("ciclo-*.json"), key=lambda r: int(PATRON_CICLO.search(r.stem).group(1))):
        numero = int(PATRON_CICLO.search(ruta.stem).group(1))
        ciclos[ruta.stem.lower()] = (f"Ciclo {numero} · sílabos reales", ruta)
    return ciclos


FUENTES.update(registrar_ciclos(DIR_CICLOS))

# Límites para que la subida y el LLM quepan en una Vercel Function (body ~4.5 MB, maxDuration 60 s).
LIMITE_BYTES_SUBIDA = 4 * 1024 * 1024
TIMEOUT_LLM_S = 20  # por llamada; el cliente reintenta 1 vez → hasta 40 s
PRESUPUESTO_LLM_S = 15  # pasado este tiempo no se empieza otra extracción: 15 + 40 = 55 s < 60 s

# Navegación: (ruta, título).
VISTAS: list[tuple[str, str]] = [
    ("/", "Cohorte"),
    ("/simulacion", "Simulación punta a punta"),
    ("/carga", "Carga semanal"),
    ("/antes-despues", "Antes / después"),
    ("/comparar", "Comparar ciclos"),
    ("/simulador", "Simulador docente"),
]
app = FastAPI(title="PULSO", description="Radar predictivo de sobrecarga académica")
app.mount("/static", StaticFiles(directory=DIR_UI / "static"), name="static")
app.include_router(api_router)  # API JSON de la simulación punta a punta (PUL-28)
templates = Jinja2Templates(directory=DIR_UI / "templates")
ETIQUETAS_TIPO: dict[TipoEvaluacion, str] = {
    TipoEvaluacion.EXAMEN_PARCIAL: "Examen parcial",
    TipoEvaluacion.EXAMEN_FINAL: "Examen final",
    TipoEvaluacion.PRACTICA_CALIFICADA: "Práctica calificada",
    TipoEvaluacion.LABORATORIO: "Laboratorio",
    TipoEvaluacion.PROYECTO: "Proyecto",
    TipoEvaluacion.EXPOSICION: "Exposición",
    TipoEvaluacion.TAREA: "Tarea",
    TipoEvaluacion.CONTROL_LECTURA: "Control de lectura",
    TipoEvaluacion.OTRO: "Otro",
}
templates.env.filters["etiqueta_tipo"] = lambda tipo: ETIQUETAS_TIPO[tipo]
DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
templates.env.filters["fecha_con_dia"] = lambda f: f"{DIAS_SEMANA[f.weekday()]} {f.strftime('%d/%m/%Y')}"

def escala_ticks(maximo: float, marcas: int = 4) -> list[float]:
    """Marcas redondas del eje Y (0, 100, 200, 300) que cubren `maximo`."""
    if maximo <= 0:
        return [0]
    crudo = maximo / marcas
    magnitud = 10 ** len(str(int(crudo))) / 10 if crudo >= 1 else 1
    paso = next(m * magnitud for m in (1, 2, 2.5, 5, 10) if m * magnitud >= crudo)
    tope = paso * -(-maximo // paso)
    return [round(paso * i, 2) for i in range(int(round(tope / paso)) + 1)]


templates.env.filters["nombre_curso"] = nombre_curso
templates.env.globals["escala_ticks"] = escala_ticks


def markdown_simple(texto: str) -> Markup:
    """Markdown mínimo (títulos #, viñetas -, **negrita**) para la propuesta del LLM. Todo se escapa antes."""
    html: list[str] = []
    en_lista = False
    for linea in texto.splitlines():
        linea = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(linea.strip())))
        linea = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", linea)  # *cursiva* del LLM
        es_item = linea.startswith(("- ", "* "))
        if es_item != en_lista:
            html.append("<ul>" if es_item else "</ul>")
            en_lista = es_item
        if es_item:
            html.append(f"<li>{linea[2:]}</li>")
        elif titulo := re.match(r"#{1,6} (.*)", linea):
            html.append(f"<h3>{titulo.group(1)}</h3>")
        elif linea:
            html.append(f"<p>{linea}</p>")
    if en_lista:
        html.append("</ul>")
    return Markup("\n".join(html))


templates.env.filters["markdown_simple"] = markdown_simple


def fuentes_disponibles() -> dict[str, str]:
    """Fuentes cuyo JSON existe en disco: clave -> etiqueta."""
    return {clave: etiqueta for clave, (etiqueta, ruta) in FUENTES.items() if ruta.is_file()}


@lru_cache(maxsize=8)
def _leer_cohorte(ruta: Path, modificado: float) -> Cohorte:
    # `modificado` forma parte de la clave de caché: si el JSON cambia en disco, se vuelve a leer.
    return cargar_cohorte(ruta)


class CohorteSubidaNoDisponible(Exception):
    """La cohorte subida vive en /tmp de una instancia de Vercel: si la función se reinicia, ya no está."""


def validar_fuente(fuente: str) -> None:
    if fuente not in fuentes_disponibles():
        if fuente == "subida":
            raise CohorteSubidaNoDisponible
        raise HTTPException(status_code=404, detail=f"Fuente de datos no disponible: {fuente!r}")


def obtener_cohorte(fuente: str) -> Cohorte:
    """Carga y valida la cohorte de una fuente; 404 si no existe, 500 con detalle si el JSON es inválido."""
    validar_fuente(fuente)
    ruta = FUENTES[fuente][1]
    try:
        return _leer_cohorte(ruta, ruta.stat().st_mtime)
    except ValidationError as error:
        raise HTTPException(status_code=500, detail=f"{ruta.name} no cumple el esquema: {error}") from error


def renderizar(request: Request, plantilla: str, fuente: str, status_code: int = 200, **contexto) -> HTMLResponse:
    """Renderiza una vista con el contexto común del layout (navegación y fuente activa)."""
    return templates.TemplateResponse(
        request,
        plantilla,
        {
            "vistas": VISTAS,
            "ruta_actual": request.url.path,
            "fuente": fuente,
            "fuentes": fuentes_disponibles(),
            **contexto,
        },
        status_code=status_code,
    )


_PAGINAS_ERROR = {
    404: ("No encontramos lo que buscas", "El enlace no es válido o esos datos ya no están disponibles."),
    422: ("Ese enlace no es válido", "Algún dato del enlace no es correcto. Vuelve a la pantalla anterior e inténtalo de nuevo."),
    500: ("Algo salió mal", "No pudimos cargar estos datos. Vuelve a intentarlo en unos minutos."),
}


def _pagina_error(request: Request, codigo: int) -> HTMLResponse:
    titulo, mensaje = _PAGINAS_ERROR.get(codigo, _PAGINAS_ERROR[500])
    return renderizar(
        request, "aviso.html", FUENTE_POR_DEFECTO, status_code=codigo,
        titulo=titulo, mensaje=mensaje, enlace="/", texto_enlace="Ir al inicio",
    )


@app.exception_handler(StarletteHTTPException)
async def error_http(request: Request, error: StarletteHTTPException):
    """Página clara en vez del JSON de FastAPI. La API JSON (/api/…) y /static responden como siempre."""
    if request.url.path.startswith(("/api", "/static")):
        return await http_exception_handler(request, error)
    logger.warning("HTTP %s en %s: %s", error.status_code, request.url.path, error.detail)
    return _pagina_error(request, error.status_code)


@app.exception_handler(RequestValidationError)
async def error_validacion(request: Request, error: RequestValidationError):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, error)
    logger.warning("Parámetros inválidos en %s: %s", request.url.path, error.errors())
    return _pagina_error(request, 422)


@app.exception_handler(CohorteSubidaNoDisponible)
def cohorte_subida_no_disponible(request: Request, _: CohorteSubidaNoDisponible) -> HTMLResponse:
    """Página en vez de un JSON de error: el usuario llegó por un enlace de una subida anterior."""
    return renderizar(
        request,
        "aviso.html",
        FUENTE_POR_DEFECTO,
        status_code=404,
        titulo="Los sílabos subidos ya no están disponibles",
        mensaje="Se guardan de forma temporal en el servidor, y el servidor se reinició. Vuelve a subirlos para seguir.",
        enlace="/simulacion",
        texto_enlace="Ir a Simulación punta a punta",
    )


def lunes_de_semana(cohorte: Cohorte, semana: int) -> date:
    return cohorte.fecha_inicio + timedelta(weeks=semana - 1)


def ordenar_por_fecha(
    cohorte: Cohorte, evaluaciones: list[Evaluacion], fechas: dict[str, date] | None = None
) -> list[Evaluacion]:
    """Orden cronológico (con `fechas={id: fecha}` sobrescritas, si se pasan).

    Si solo hay semana (antes de normalizar, PUL-06), se usa el lunes de esa semana.
    """
    fechas = fechas or {}
    return sorted(
        evaluaciones,
        key=lambda e: (fechas.get(e.id) or e.fecha or lunes_de_semana(cohorte, e.semana), e.curso, e.nombre),
    )


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
    cohorte = obtener_cohorte(fuente)
    evaluaciones = ordenar_por_fecha(cohorte, cohorte.evaluaciones)
    calendario = construir_calendario(cohorte)  # la cinta del semestre y las colisiones: la pregunta de la pantalla
    return renderizar(request, "inicio.html", fuente, cohorte=cohorte, evaluaciones=evaluaciones, calendario=calendario)


@dataclass(frozen=True)
class SemanaCarga:
    numero: int
    lunes: date
    carga: float
    intensidad: float  # carga / escala del calendario, en [0, 1]: define el color de la celda
    critica: bool  # contiene evaluaciones de una colisión (PUL-10)
    evaluaciones: list[Evaluacion]

    @property
    def domingo(self) -> date:
        return self.lunes + timedelta(days=6)


@dataclass(frozen=True)
class Calendario:
    """Carga semanal y colisiones de la cohorte en un escenario de fechas."""

    semanas: list[SemanaCarga]
    colisiones: list[Colision]
    ids_en_colision: set[str]
    semana_pico: int | None  # None si la cohorte no tiene carga
    pico: float


def construir_calendario(cohorte: Cohorte, fechas: dict[str, date] | None = None, escala: float | None = None) -> Calendario:
    """Calendario con las fechas originales o, con `fechas={id: fecha}`, con las del optimizador.

    `escala` es la carga que se pinta con el color más intenso (por defecto, el pico del propio
    calendario). Para comparar dos calendarios lado a lado se usa la misma escala en ambos.
    """
    fechas = fechas or {}
    carga_por_semana = carga_semanal_cohorte(cohorte, fechas)
    numero_pico, pico = semana_pico(carga_por_semana)
    escala = escala or pico
    colisiones = detectar_colisiones(cohorte.evaluaciones, fechas)
    semanas_criticas = {
        semana_de(e, cohorte.fecha_inicio, colision.fechas[e.id]) for colision in colisiones for e in colision.evaluaciones
    }
    por_semana = evaluaciones_por_semana(cohorte.evaluaciones, cohorte.fecha_inicio, fechas)
    semanas = [
        SemanaCarga(
            numero=n,
            lunes=lunes_de_semana(cohorte, n),
            carga=carga_por_semana[n],
            intensidad=min(carga_por_semana[n] / escala, 1.0) if escala else 0.0,
            critica=n in semanas_criticas,
            evaluaciones=ordenar_por_fecha(cohorte, por_semana[n], fechas),
        )
        for n in range(1, SEMANAS_CICLO + 1)
    ]
    return Calendario(
        semanas=semanas,
        colisiones=colisiones,
        ids_en_colision={e.id for colision in colisiones for e in colision.evaluaciones},
        semana_pico=numero_pico if pico else None,
        pico=pico,
    )


@app.get("/carga", response_class=HTMLResponse)
def carga(
    request: Request,
    fuente: str = FUENTE_POR_DEFECTO,
    semana: int | None = Query(default=None, ge=1, le=SEMANAS_CICLO),
) -> HTMLResponse:
    """Heatmap de carga semanal (PUL-15): semanas con colisiones en rojo; `semana` abre su detalle."""
    cohorte = obtener_cohorte(fuente)
    calendario = construir_calendario(cohorte)
    return renderizar(
        request,
        "carga.html",
        fuente,
        cohorte=cohorte,
        calendario=calendario,
        seleccionada=calendario.semanas[semana - 1] if semana else None,
        min_evaluaciones=MIN_EVALUACIONES,
    )


@lru_cache(maxsize=8)
def _optimizar(ruta: Path, modificado: float, rechazadas: tuple[str, ...] = ()) -> ResultadoOptimizacion:
    # Misma clave que `_leer_cohorte`: se vuelve a optimizar solo si el JSON cambia en disco
    # o si la coordinación rechaza otro movimiento (human in the loop).
    return optimizar(cohorte_con_rechazos(_leer_cohorte(ruta, modificado), rechazadas))


# ---------- Human in the loop: la coordinación revisa cada movimiento antes de aprobar ----------
# Sin estado en el servidor: las decisiones viajan en la URL (?rechazadas=id1,id2&aprobada=1),
# así funciona igual en Vercel y el enlace se puede compartir con quien tenga que revisar.


def leer_rechazadas(cohorte: Cohorte, rechazadas: str | None) -> tuple[str, ...]:
    """IDs de evaluaciones cuyo movimiento la coordinación rechazó (los desconocidos se ignoran)."""
    validos = {e.id for e in cohorte.evaluaciones}
    return tuple(sorted({i for i in (rechazadas or "").split(",") if i in validos}))


def cohorte_con_rechazos(cohorte: Cohorte, rechazadas: tuple[str, ...]) -> Cohorte:
    """Una evaluación rechazada se mantiene en su fecha: para el optimizador pasa a estar bloqueada."""
    if not rechazadas:
        return cohorte
    evaluaciones = [e.model_copy(update={"bloqueada": True}) if e.id in rechazadas else e for e in cohorte.evaluaciones]
    return cohorte.model_copy(update={"evaluaciones": evaluaciones})


def url_revision(ruta: str, fuente: str, rechazadas: tuple[str, ...], agregar: str | None = None,
                 quitar: str | None = None, aprobada: bool = False, ancla: str = "") -> str:
    ids = set(rechazadas) | ({agregar} if agregar else set())
    ids.discard(quitar)
    params = {"fuente": fuente}
    if ids:
        params["rechazadas"] = ",".join(sorted(ids))
    if aprobada:
        params["aprobada"] = "1"
    return f"{ruta}?{urlencode(params)}{ancla}"


templates.env.globals["url_revision"] = url_revision


@app.get("/antes-despues", response_class=HTMLResponse)
def antes_despues(
    request: Request, fuente: str = FUENTE_POR_DEFECTO, rechazadas: str | None = None, aprobada: bool = False
) -> HTMLResponse:
    """Calendario actual vs. el propuesto por el optimizador (PUL-16), con el diff y la reducción del pico.

    Human in the loop: la coordinación puede rechazar movimientos (el optimizador recalcula manteniendo
    esas fechas) y aprobar la propuesta antes de enviarla.
    """
    cohorte = obtener_cohorte(fuente)
    ruta = FUENTES[fuente][1]
    rechazos = leer_rechazadas(cohorte, rechazadas)
    try:
        resultado = _optimizar(ruta, ruta.stat().st_mtime, rechazos)
    except ValueError as error:  # p. ej. evaluaciones sin fecha: el optimizador necesita fechas (PUL-06)
        return renderizar(request, "antes_despues.html", fuente, cohorte=cohorte, error=mensaje_para_usuario(str(error)))
    if not resultado.factible:
        logger.warning("Optimizador sin solución para %s: %s", fuente, resultado.estado)
        error = "No se encontró una reprogramación válida con estas restricciones."
        return renderizar(request, "antes_despues.html", fuente, cohorte=cohorte, error=error)
    antes = construir_calendario(cohorte)
    # Misma escala de color en ambos calendarios para que la comparación sea justa.
    despues = construir_calendario(cohorte, resultado.fechas, escala=antes.pico)
    return renderizar(
        request,
        "antes_despues.html",
        fuente,
        cohorte=cohorte,
        resultado=resultado,
        antes=antes,
        despues=despues,
        rechazadas=rechazos,
        evaluaciones_rechazadas=[e for e in cohorte.evaluaciones if e.id in rechazos],
        aprobada=aprobada,
    )


@dataclass(frozen=True)
class FilaCiclo:
    """Un ciclo en la comparación: su semestre y lo que logra el optimizador."""

    fuente: str
    numero: int | None  # n.º de ciclo de la carrera, si el nombre lo trae ("… ciclo-07 …")
    cohorte: Cohorte
    calendario: Calendario
    carga_total: float
    resultado: ResultadoOptimizacion | None  # None si no se pudo optimizar

    @property
    def etiqueta(self) -> str:
        return f"Ciclo {self.numero}" if self.numero is not None else self.cohorte.nombre


def fuentes_de_ciclos() -> list[str]:
    """Fuentes que entran en la comparación: la cohorte principal y los ciclos de data/cohortes."""
    return [f for f in fuentes_disponibles() if f == "cohorte" or f.startswith("ciclo-")]


def filas_comparacion() -> list[FilaCiclo]:
    filas: list[FilaCiclo] = []
    nombres: set[str] = set()
    for fuente in fuentes_de_ciclos():
        cohorte = obtener_cohorte(fuente)
        if cohorte.nombre in nombres:  # el mismo ciclo guardado dos veces (p. ej. cohorte.json y ciclo-07.json)
            continue
        nombres.add(cohorte.nombre)
        ruta = FUENTES[fuente][1]
        try:
            resultado = _optimizar(ruta, ruta.stat().st_mtime)
            resultado = resultado if resultado.factible else None
        except ValueError:  # p. ej. evaluaciones sin fecha
            resultado = None
        numero = PATRON_CICLO.search(cohorte.nombre) or PATRON_CICLO.search(fuente)
        calendario = construir_calendario(cohorte)
        filas.append(
            FilaCiclo(
                fuente=fuente,
                numero=int(numero.group(1)) if numero else None,
                cohorte=cohorte,
                calendario=calendario,
                carga_total=round(sum(s.carga for s in calendario.semanas), 2),
                resultado=resultado,
            )
        )
    return sorted(filas, key=lambda f: (f.numero is None, f.numero or 0, f.cohorte.fecha_inicio))


@app.get("/comparar", response_class=HTMLResponse)
def comparar(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
    """Comparación entre ciclos de la carrera: ¿qué ciclo se sobrecarga más y cuánto mejora cada uno?"""
    validar_fuente(fuente)
    filas = filas_comparacion()
    escala = max((f.calendario.pico for f in filas), default=0)
    max_colisiones = max((len(f.calendario.colisiones) for f in filas), default=0)
    # El más sobrecargado: más colisiones y, a igualdad, mayor carga pico.
    critico = max(filas, key=lambda f: (len(f.calendario.colisiones), f.calendario.pico), default=None)
    return renderizar(
        request,
        "comparar.html",
        fuente,
        filas=filas,
        escala=escala,
        max_colisiones=max_colisiones,
        critico=critico,
    )


@app.get("/simulador", response_class=HTMLResponse)
def simulador(
    request: Request,
    fuente: str = FUENTE_POR_DEFECTO,
    evaluacion: str | None = None,
    fecha: date | None = None,
) -> HTMLResponse:
    """Simulador docente (PUL-18): evaluación + fecha → % de alumnos con colisión y mejor fecha cercana."""
    cohorte = obtener_cohorte(fuente)
    fin_ciclo = lunes_de_semana(cohorte, SEMANAS_CICLO) + timedelta(days=6)
    seleccionada = None
    if evaluacion:
        seleccionada = next((e for e in cohorte.evaluaciones if e.id == evaluacion), None)
        if seleccionada is None:
            raise HTTPException(status_code=404, detail=f"Evaluación no encontrada: {evaluacion!r}")
    resultado = error = calendario = None
    if seleccionada and fecha:
        if cohorte.fecha_inicio <= fecha <= fin_ciclo:
            resultado = simular(cohorte, seleccionada, fecha)
            # El semestre con la fecha simulada: dónde cae la evaluación y cómo queda la carga.
            calendario = construir_calendario(cohorte, {seleccionada.id: fecha})
        else:
            error = (
                f"La fecha debe estar dentro del ciclo: del {cohorte.fecha_inicio.strftime('%d/%m/%Y')} "
                f"al {fin_ciclo.strftime('%d/%m/%Y')}."
            )
    return renderizar(
        request,
        "simulador.html",
        fuente,
        cohorte=cohorte,
        evaluaciones=ordenar_por_fecha(cohorte, cohorte.evaluaciones),
        seleccionada=seleccionada,
        # Sin fecha elegida, el formulario propone la fecha actual de la evaluación.
        fecha=fecha or (seleccionada.fecha if seleccionada else None),
        fin_ciclo=fin_ciclo,
        resultado=resultado,
        error=error,
        calendario=calendario,
        semana_simulada=semana_de(seleccionada, cohorte.fecha_inicio, fecha) if calendario else None,
    )


@lru_cache(maxsize=8)
def _propuesta(ruta: Path, modificado: float, rechazadas: tuple[str, ...] = ()) -> Propuesta:
    """Propuesta para el coordinador (PUL-08). Sin LLM configurado, o si falla, usa la plantilla de A."""
    config = config_llm()
    cliente = crear_cliente(config, timeout=TIMEOUT_LLM_S) if config.completa else None
    cohorte = cohorte_con_rechazos(_leer_cohorte(ruta, modificado), rechazadas)
    return generar_propuesta(cohorte, _optimizar(ruta, modificado, rechazadas), cliente=cliente, modelo=config.modelo)


@app.get("/antes-despues/propuesta", response_class=HTMLResponse)
def propuesta(
    request: Request, fuente: str = FUENTE_POR_DEFECTO, rechazadas: str | None = None, aprobada: bool = False
) -> HTMLResponse:
    """Fragmento HTML que /antes-despues carga con HTMX, para no esperar al LLM al abrir la vista.

    Responde siempre 200 con el fragmento: HTMX no reemplaza el contenido con respuestas de error,
    y la pantalla se quedaría en "Redactando la propuesta…".
    """
    if fuente not in fuentes_disponibles():
        return templates.TemplateResponse(request, "_propuesta.html", {"error": "Los datos de esta cohorte ya no están disponibles."})
    ruta = FUENTES[fuente][1]
    rechazos = leer_rechazadas(obtener_cohorte(fuente), rechazadas)
    try:
        if not _optimizar(ruta, ruta.stat().st_mtime, rechazos).factible:
            raise ValueError("el optimizador no encontró una reprogramación válida")
        contexto = {"propuesta": _propuesta(ruta, ruta.stat().st_mtime, rechazos)}
    except ValueError as error:
        contexto = {"error": mensaje_para_usuario(str(error))}
    contexto.update(fuente=fuente, rechazadas=rechazos, aprobada=aprobada)
    return templates.TemplateResponse(request, "_propuesta.html", contexto)


@app.get("/antes-despues/propuesta.md", response_class=PlainTextResponse)
def propuesta_descarga(fuente: str = FUENTE_POR_DEFECTO, rechazadas: str | None = None) -> PlainTextResponse:
    """La propuesta aprobada, como archivo para enviar a los docentes."""
    cohorte = obtener_cohorte(fuente)
    ruta = FUENTES[fuente][1]
    rechazos = leer_rechazadas(cohorte, rechazadas)
    try:
        if not _optimizar(ruta, ruta.stat().st_mtime, rechazos).factible:
            raise ValueError("el optimizador no encontró una reprogramación válida")
        texto = _propuesta(ruta, ruta.stat().st_mtime, rechazos).texto
    except ValueError as error:  # p. ej. evaluaciones sin fecha: no hay propuesta que descargar
        return PlainTextResponse(f"No se pudo generar la propuesta. {mensaje_para_usuario(str(error))}", status_code=422)
    if rechazos:
        nombres = ", ".join(f"{e.nombre} ({nombre_curso(e.curso)})" for e in cohorte.evaluaciones if e.id in rechazos)
        texto += "\n\n" + f"_Revisado por la coordinación: se mantienen en su fecha {nombres}._"
    return PlainTextResponse(
        texto,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="propuesta-reprogramacion.md"'},
    )


def _extraer_en_linea(pdf: Path) -> ResultadoExtraccion:
    """Extrae un sílabo sin caché con el pipeline de A, con tiempos que caben en una Vercel Function."""
    config = config_llm()
    if not config.completa:
        raise RuntimeError("no está en la caché y el LLM no está configurado (LLM_API_KEY y LLM_MODEL)")
    cliente = crear_cliente(config, timeout=TIMEOUT_LLM_S)
    return extraer_evaluaciones(leer_pdf(pdf), cliente=cliente, modelo=config.modelo, max_intentos=1)


# Errores técnicos → mensaje para quien usa la app. Se busca por texto (en minúsculas) en el error.
_MENSAJES_ERROR: list[tuple[tuple[str, ...], str]] = [
    (("402", "credits", "saldo"), "La lectura con IA no está disponible en este momento. Vuelve a intentarlo más tarde."),
    (("no está en la caché",), "Es un sílabo nuevo y la lectura con IA no está disponible en este momento."),
    (("no alcanzó el tiempo",), "No alcanzó el tiempo para leerlo. Vuelve a subirlo: lo ya leído quedó guardado."),
    (("timeout", "timed out", "429", "rate limit"), "La IA tardó demasiado en responder. Vuelve a intentarlo en unos minutos."),
    (("ningún sílabo pudo extraerse",), "No se pudo leer ninguno de los sílabos."),
    (("ids de evaluación repetidos",), "Hay dos sílabos del mismo curso: sube uno por curso."),
    (("no tiene fecha",), "Hay evaluaciones sin fecha, así que no se puede optimizar esta cohorte."),
    (("reprogramación válida", "infeasible"), "No se encontró una reprogramación válida con estas restricciones."),
    (("ya no está disponible",), "Los datos de esta cohorte ya no están disponibles."),
]
_MENSAJE_GENERICO = "No se pudo completar esta acción. Vuelve a intentarlo."


def mensaje_para_usuario(error: str) -> str:
    """Mensaje claro para la página pública: sin códigos, trazas, URLs ni nombres internos.

    El error completo queda en los logs del servidor (Vercel → Logs).
    """
    logger.warning("Error mostrado al usuario como mensaje claro: %s", error)
    texto = error.lower()
    return next((mensaje for claves, mensaje in _MENSAJES_ERROR if any(c in texto for c in claves)), _MENSAJE_GENERICO)


def _formulario_por_defecto() -> dict:
    """Ciclo y fecha de inicio de la cohorte real, para que en la demo solo haya que elegir los PDFs."""
    cohorte = obtener_cohorte("cohorte") if "cohorte" in fuentes_disponibles() else None
    return {"ciclo": cohorte.ciclo if cohorte else "", "fecha_inicio": cohorte.fecha_inicio if cohorte else None, "nombre": ""}


def _pasos_simulacion(fuente: str) -> dict:
    """Medir y Optimizar de la simulación punta a punta (PUL-29) para una cohorte ya leída.

    Usa las mismas funciones (y cachés) que /carga, /antes-despues y la propuesta: los números
    de esta pantalla y los de la propuesta salen del mismo resultado del solver.
    """
    cohorte = obtener_cohorte(fuente)
    ruta = FUENTES[fuente][1]
    calendario = construir_calendario(cohorte)
    contexto: dict = {
        "cohorte": cohorte,
        "calendario": calendario,
        "evaluaciones_por_curso": sorted(Counter(e.curso for e in cohorte.evaluaciones).items()),
        "resultado": None,
    }
    try:
        resultado = _optimizar(ruta, ruta.stat().st_mtime)
        if resultado.factible:
            contexto["resultado"] = resultado
        else:
            contexto["error_optimizar"] = "No se encontró una reprogramación válida con estas restricciones."
    except ValueError as error:  # p. ej. evaluaciones sin fecha
        contexto["error_optimizar"] = mensaje_para_usuario(str(error))
    # Caso para el simulador docente: una evaluación movible que hoy está en una colisión, de preferencia
    # una para la que el simulador encuentra una fecha mejor (los exámenes no salen de su semana de exámenes).
    casos = [(e, c.fechas[e.id]) for c in calendario.colisiones for e in c.evaluaciones if not e.bloqueada]
    contexto["caso_simulador"] = next(
        (caso for caso in casos if simular(cohorte, *caso).mejor_alternativa), casos[0] if casos else None
    )
    return contexto


@app.get("/simulacion", response_class=HTMLResponse)
def simulacion(request: Request, fuente: str | None = None) -> HTMLResponse:
    """Simulación punta a punta (PUL-29): ciclo 7 o sílabos subidos → Leer → Medir → Optimizar → Proponer."""
    contexto = {"formulario": _formulario_por_defecto(), "seleccion": fuente}
    if fuente:
        contexto |= _pasos_simulacion(fuente)
    return renderizar(request, "simulacion.html", fuente or FUENTE_POR_DEFECTO, **contexto)


@app.get("/cargar", include_in_schema=False)
def cargar() -> RedirectResponse:
    """La subida de sílabos (PUL-17) ahora vive en la simulación punta a punta."""
    return RedirectResponse("/simulacion", status_code=307)


@app.post("/simulacion", response_class=HTMLResponse)
def simulacion_subir(
    request: Request,
    archivos: list[UploadFile] = File(...),
    ciclo: str = Form(...),
    fecha_inicio: date = Form(...),
    nombre: str = Form(""),
) -> HTMLResponse:
    """PDF → texto → evaluaciones (caché o LLM) → normalización → cohorte en /tmp, lista para las demás vistas."""
    formulario = {"ciclo": ciclo.strip(), "fecha_inicio": fecha_inicio, "nombre": nombre.strip()}
    reportes: list[ReporteSilabo] = []

    def rechazar(mensaje: str) -> HTMLResponse:
        for reporte in reportes:  # los errores del LLM pueden traer URLs de la cuenta del proveedor
            if reporte.error:
                reporte.error = mensaje_para_usuario(f"{reporte.archivo}: {reporte.error}")
        return renderizar(
            request, "simulacion.html", FUENTE_POR_DEFECTO, status_code=422, formulario=formulario, error=mensaje, reportes=reportes
        )

    if not formulario["ciclo"]:
        return rechazar("Indica el ciclo, p. ej. 2026-I.")
    if fecha_inicio.weekday() != 0:
        return rechazar("La fecha de inicio debe ser el lunes de la semana 1 del ciclo.")
    subidos = [(Path(a.filename).name, a.file.read()) for a in archivos if a.filename]
    if not subidos:
        return rechazar("Elige al menos un sílabo en PDF.")
    if sum(len(datos) for _, datos in subidos) > LIMITE_BYTES_SUBIDA:
        return rechazar(f"Los PDFs suman más de {LIMITE_BYTES_SUBIDA // (1024 * 1024)} MB: sube menos archivos a la vez.")
    no_pdf = [nombre_pdf for nombre_pdf, datos in subidos if not datos.startswith(b"%PDF-")]
    if no_pdf:
        return rechazar(f"No son PDF: {', '.join(no_pdf)}.")

    unicos: dict[str, tuple[str, bytes]] = {}  # sha256 -> (nombre, bytes): el mismo PDF subido dos veces cuenta una
    for nombre_pdf, datos in subidos:
        unicos.setdefault(hashlib.sha256(datos).hexdigest(), (nombre_pdf, datos))
    limite = time.monotonic() + PRESUPUESTO_LLM_S

    def extraer(pdf: Path) -> ResultadoExtraccion:
        # Solo se llama para PDFs sin caché. Lo ya extraído queda en caché: la siguiente subida sigue desde ahí.
        if time.monotonic() > limite:
            raise RuntimeError("no alcanzó el tiempo de esta subida; vuelve a subirlo (lo ya extraído quedó en caché)")
        return _extraer_en_linea(pdf)

    with tempfile.TemporaryDirectory() as carpeta:
        for i, (nombre_pdf, datos) in enumerate(unicos.values()):
            # Nombre seguro y siempre en .pdf: procesar_cohorte solo toma los *.pdf de la carpeta.
            base = "".join(c for c in Path(nombre_pdf).stem if c.isalnum() or c in "-_") or "silabo"
            (Path(carpeta) / f"{i:02d}-{base}.pdf").write_bytes(datos)
        try:
            lote = procesar_cohorte(
                Path(carpeta),
                nombre=formulario["nombre"] or f"Cohorte subida ({formulario['ciclo']})",
                ciclo=formulario["ciclo"],
                fecha_inicio=fecha_inicio,
                cache=DIR_TMP / "cache-extraccion",  # escribible también en Vercel
                caches_lectura=(CACHE_POR_DEFECTO,),  # extracciones commiteadas (PUL-07)
                extractor=extraer,
                al_procesar=reportes.append,
            )
        except (RuntimeError, ValueError) as error:  # ningún sílabo se pudo extraer, o la cohorte no valida
            return rechazar(mensaje_para_usuario(str(error)))

    guardar_cohorte(lote.cohorte, FUENTES["subida"][1])
    for reporte in reportes:  # un sílabo pudo fallar aunque el resto armó la cohorte
        if reporte.error:
            reporte.error = mensaje_para_usuario(f"{reporte.archivo}: {reporte.error}")
    return renderizar(
        request,
        "simulacion.html",
        "subida",
        formulario=formulario,
        seleccion="subida",
        reportes=reportes,
        advertencias=lote.advertencias,
        **_pasos_simulacion("subida"),
    )
