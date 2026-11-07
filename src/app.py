"""Entrypoint de PULSO: monolito FastAPI que Vercel detecta automáticamente (`app`).

Local: uvicorn src.app:app --reload
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from src.engine.collisions import MIN_EVALUACIONES, Colision, detectar_colisiones
from src.engine.load_index import carga_semanal_cohorte, evaluaciones_por_semana, semana_de, semana_pico
from src.models import SEMANAS_CICLO, Cohorte, Evaluacion, cargar_cohorte
from src.optimizer.objective import ResultadoOptimizacion, optimizar
from src.optimizer.simulator import simular
from src.api import router as api_router

RAIZ = Path(__file__).resolve().parent.parent
DIR_UI = Path(__file__).resolve().parent / "ui"

# Fuentes de datos seleccionables: clave -> (etiqueta, ruta del JSON de cohorte).
# `cohorte` aparece en el selector cuando la extracción (PUL-07) genere data/cohorte.json.
FUENTES: dict[str, tuple[str, Path]] = {
    "mock": ("Datos de ejemplo (mock)", RAIZ / "data" / "mock" / "evaluaciones_mock.json"),
    "cohorte": ("Cohorte extraída de los sílabos", RAIZ / "data" / "cohorte.json"),
}
FUENTE_POR_DEFECTO = "mock"

# Navegación: (ruta, título). Las vistas sin implementar muestran una página "en construcción".
VISTAS: list[tuple[str, str]] = [
    ("/", "Cohorte"),
    ("/carga", "Carga semanal"),
    ("/antes-despues", "Antes / después"),
    ("/simulador", "Simulador docente"),
]
# Ruta -> tarea del backlog que la implementa. Cada tarea quita su entrada al agregar la vista real.
VISTAS_PENDIENTES: dict[str, str] = {
}

app = FastAPI(title="PULSO", description="Radar predictivo de sobrecarga académica")
app.mount("/static", StaticFiles(directory=DIR_UI / "static"), name="static")
app.include_router(api_router)  # API JSON de la simulación punta a punta (PUL-28)
templates = Jinja2Templates(directory=DIR_UI / "templates")
templates.env.filters["etiqueta_tipo"] = lambda tipo: tipo.value.replace("_", " ").capitalize()
DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
templates.env.filters["fecha_con_dia"] = lambda f: f"{DIAS_SEMANA[f.weekday()]} {f.strftime('%d/%m/%Y')}"


def fuentes_disponibles() -> dict[str, str]:
    """Fuentes cuyo JSON existe en disco: clave -> etiqueta."""
    return {clave: etiqueta for clave, (etiqueta, ruta) in FUENTES.items() if ruta.is_file()}


@lru_cache(maxsize=8)
def _leer_cohorte(ruta: Path, modificado: float) -> Cohorte:
    # `modificado` forma parte de la clave de caché: si el JSON cambia en disco, se vuelve a leer.
    return cargar_cohorte(ruta)


def validar_fuente(fuente: str) -> None:
    if fuente not in fuentes_disponibles():
        raise HTTPException(status_code=404, detail=f"Fuente de datos no disponible: {fuente!r}")


def obtener_cohorte(fuente: str) -> Cohorte:
    """Carga y valida la cohorte de una fuente; 404 si no existe, 500 con detalle si el JSON es inválido."""
    validar_fuente(fuente)
    ruta = FUENTES[fuente][1]
    try:
        return _leer_cohorte(ruta, ruta.stat().st_mtime)
    except ValidationError as error:
        raise HTTPException(status_code=500, detail=f"{ruta.name} no cumple el esquema: {error}") from error


def renderizar(request: Request, plantilla: str, fuente: str, **contexto) -> HTMLResponse:
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
    return renderizar(request, "inicio.html", fuente, cohorte=cohorte, evaluaciones=evaluaciones)


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
def _optimizar(ruta: Path, modificado: float) -> ResultadoOptimizacion:
    # Misma clave que `_leer_cohorte`: se vuelve a optimizar solo si el JSON cambia en disco.
    return optimizar(_leer_cohorte(ruta, modificado))


@app.get("/antes-despues", response_class=HTMLResponse)
def antes_despues(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
    """Calendario actual vs. el propuesto por el optimizador (PUL-16), con el diff y la reducción del pico."""
    cohorte = obtener_cohorte(fuente)
    ruta = FUENTES[fuente][1]
    try:
        resultado = _optimizar(ruta, ruta.stat().st_mtime)
    except ValueError as error:  # p. ej. evaluaciones sin fecha: el optimizador necesita fechas (PUL-06)
        return renderizar(request, "antes_despues.html", fuente, cohorte=cohorte, error=str(error))
    if not resultado.factible:
        error = f"El optimizador no encontró una reprogramación válida (estado: {resultado.estado})."
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
    resultado = error = None
    if seleccionada and fecha:
        if cohorte.fecha_inicio <= fecha <= fin_ciclo:
            resultado = simular(cohorte, seleccionada, fecha)
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
    )


def _vista_pendiente(ruta: str, titulo: str, tarea: str) -> None:
    def vista(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
        validar_fuente(fuente)
        return renderizar(request, "pendiente.html", fuente, titulo=titulo, tarea=tarea)

    app.add_api_route(ruta, vista, methods=["GET"], response_class=HTMLResponse, name=f"pendiente{ruta}")


for _ruta, _titulo in VISTAS:
    if _ruta in VISTAS_PENDIENTES:
        _vista_pendiente(_ruta, _titulo, VISTAS_PENDIENTES[_ruta])
