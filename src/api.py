"""API JSON de PULSO (PUL-28): la simulación punta a punta en una llamada.

    GET  /api/presets                       cohortes de prueba disponibles
    GET  /api/simular?preset=ciclo-07       simulación con la cohorte de prueba
    POST /api/simular                       simulación con sílabos subidos (multipart: archivos[])

La vista web de PUL-29 consume estos endpoints.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from src.pipeline import PRESETS, simular_pdfs, simular_preset

router = APIRouter(prefix="/api", tags=["simulación"])

MAX_ARCHIVOS = 10
MAX_BYTES = 4 * 1024 * 1024  # Vercel limita el body de cada petición a ~4.5 MB


@router.get("/presets")
def presets() -> list[dict]:
    return [{"clave": p.clave, "etiqueta": p.etiqueta, "ciclo": p.ciclo, "fecha_inicio": p.fecha_inicio.isoformat()} for p in PRESETS.values()]


@router.get("/simular")
def simular_con_preset(
    preset: str = Query("ciclo-07"),
    propuesta: str = Query("auto", pattern="^(auto|plantilla)$"),
) -> dict:
    try:
        return simular_preset(preset, propuesta=propuesta).to_dict()
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/simular")
async def simular_con_pdfs(
    archivos: list[UploadFile] = File(..., description="Sílabos en PDF"),
    ciclo: str = Form(...),
    inicio: date = Form(..., description="Lunes de la semana 1 (YYYY-MM-DD)"),
    nombre: str | None = Form(None),
    propuesta: str = Form("auto", pattern="^(auto|plantilla)$"),
) -> dict:
    if len(archivos) > MAX_ARCHIVOS:
        raise HTTPException(status_code=413, detail=f"Máximo {MAX_ARCHIVOS} sílabos por simulación.")
    contenidos = [(a.filename or "silabo.pdf", await a.read()) for a in archivos]
    if sum(len(c) for _, c in contenidos) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Los PDFs superan 4 MB en total (límite de Vercel).")
    if inicio.weekday() != 0:
        raise HTTPException(status_code=422, detail="La fecha de inicio debe ser lunes.")
    try:
        return simular_pdfs(contenidos, ciclo=ciclo, fecha_inicio=inicio, nombre=nombre, propuesta=propuesta).to_dict()
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
