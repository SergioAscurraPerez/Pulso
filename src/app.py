"""Entrypoint de PULSO: monolito FastAPI que Vercel detecta automáticamente (`app`).

Local: uvicorn src.app:app --reload
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from src.models import Cohorte, Evaluacion, cargar_cohorte

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
    "/carga": "PUL-15",
    "/antes-despues": "PUL-16",
    "/simulador": "PUL-18",
}

app = FastAPI(title="PULSO", description="Radar predictivo de sobrecarga académica")
app.mount("/static", StaticFiles(directory=DIR_UI / "static"), name="static")
templates = Jinja2Templates(directory=DIR_UI / "templates")
templates.env.filters["etiqueta_tipo"] = lambda tipo: tipo.value.replace("_", " ").capitalize()


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


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
    cohorte = obtener_cohorte(fuente)

    def fecha_efectiva(e: Evaluacion) -> date:
        # Si solo hay semana (antes de normalizar, PUL-06), se usa el lunes de esa semana.
        return e.fecha or cohorte.fecha_inicio + timedelta(weeks=e.semana - 1)

    evaluaciones = sorted(cohorte.evaluaciones, key=lambda e: (fecha_efectiva(e), e.curso, e.nombre))
    return renderizar(request, "inicio.html", fuente, cohorte=cohorte, evaluaciones=evaluaciones)


def _vista_pendiente(ruta: str, titulo: str, tarea: str) -> None:
    def vista(request: Request, fuente: str = FUENTE_POR_DEFECTO) -> HTMLResponse:
        validar_fuente(fuente)
        return renderizar(request, "pendiente.html", fuente, titulo=titulo, tarea=tarea)

    app.add_api_route(ruta, vista, methods=["GET"], response_class=HTMLResponse, name=f"pendiente{ruta}")


for _ruta, _titulo in VISTAS:
    if _ruta in VISTAS_PENDIENTES:
        _vista_pendiente(_ruta, _titulo, VISTAS_PENDIENTES[_ruta])
