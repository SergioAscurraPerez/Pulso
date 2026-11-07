"""Simulación punta a punta (PUL-28).

Un solo punto de entrada para todo el flujo de PULSO:

    Leer      sílabos PDF → evaluaciones (PDF → texto → LLM, con caché) → normalización
    Medir     carga semanal y colisiones de 72 h
    Optimizar CP-SAT: reprogramación mínima, antes/después y diff
    Proponer  propuesta redactada para el coordinador (LLM, con respaldo en plantilla)

Dos entradas:
- `simular_pdfs(archivos, ...)`: PDFs subidos por el usuario (bytes).
- `simular_preset("ciclo-07")`: la cohorte de prueba con los sílabos reales del ciclo 7 (USMP, 2026-I).
  Si la carpeta de PDFs no está (en Vercel se excluye del despliegue), se usa `data/cohorte.json`
  y la caché de extracciones: no hace falta llamar al LLM.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from src.engine.collisions import detectar_colisiones
from src.engine.load_index import carga_semanal_cohorte, semana_pico
from src.extraction.batch import CACHE_POR_DEFECTO, Extractor, ReporteSilabo, _extraer_con_llm, procesar_cohorte
from src.extraction.proposal import generar_propuesta, propuesta_plantilla, datos_propuesta
from src.models import Cohorte, cargar_cohorte
from src.optimizer.cpsat_model import ConfigOptimizador
from src.optimizer.objective import ResultadoOptimizacion, optimizar

RAIZ = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Preset:
    clave: str
    etiqueta: str
    carpeta: Path
    cohorte_json: Path
    ciclo: str
    fecha_inicio: date


PRESETS: dict[str, Preset] = {
    "ciclo-07": Preset(
        clave="ciclo-07",
        etiqueta="Ciclo 7 · Ingeniería de Computación y Sistemas · USMP 2026-I (sílabos reales)",
        carpeta=RAIZ / "data" / "silabos" / "ciclo-07",
        cohorte_json=RAIZ / "data" / "cohorte.json",
        ciclo="2026-I",
        fecha_inicio=date(2026, 3, 2),  # inicio de clases oficial, calendario FIA 2026-I
    )
}


@dataclass
class ResultadoSimulacion:
    cohorte: Cohorte
    silabos: list[ReporteSilabo]
    optimizacion: ResultadoOptimizacion
    propuesta: dict
    tiempos_s: dict[str, float]
    advertencias: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        c, o = self.cohorte, self.optimizacion
        colisiones = detectar_colisiones(c.evaluaciones)
        carga = carga_semanal_cohorte(c)
        semana, valor = semana_pico(carga)
        return {
            "cohorte": {
                "nombre": c.nombre,
                "ciclo": c.ciclo,
                "fecha_inicio": c.fecha_inicio.isoformat(),
                "cursos": c.cursos,
                "evaluaciones": len(c.evaluaciones),
            },
            "pasos": {
                "leer": {
                    "silabos": [
                        {
                            "archivo": r.archivo,
                            "curso": r.curso,
                            "evaluaciones": r.evaluaciones,
                            "desde_cache": r.desde_cache,
                            "error": r.error,
                            "advertencias": r.advertencias,
                        }
                        for r in self.silabos
                    ],
                },
                "medir": {
                    "carga_semanal": carga,
                    "semana_pico": {"semana": semana, "carga": valor},
                    "colisiones": [col.to_dict() for col in colisiones],
                },
                "optimizar": o.to_dict(),
                "proponer": self.propuesta,
            },
            "tiempos_s": self.tiempos_s,
            "advertencias": self.advertencias,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def _cache_escribible() -> Path:
    """La caché del repo si se puede escribir; si no (Vercel), una carpeta en /tmp."""
    elegida = Path(os.getenv("PULSO_CACHE_DIR") or CACHE_POR_DEFECTO)
    try:
        elegida.mkdir(parents=True, exist_ok=True)
        prueba = elegida / ".escritura"
        prueba.write_text("ok", encoding="utf-8")
        prueba.unlink()
        return elegida
    except OSError:
        tmp = Path(tempfile.gettempdir()) / "pulso-cache"
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp


def _reportes_desde_cache(cohorte: Cohorte, cache: Path = CACHE_POR_DEFECTO) -> list[ReporteSilabo]:
    """Reporte del paso «Leer» a partir de la caché, para cuando los PDFs no están desplegados."""
    reportes = []
    cursos = set(cohorte.cursos)
    for archivo in sorted(cache.glob("*.json")):
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        if datos.get("curso") in cursos:
            reportes.append(
                ReporteSilabo(datos["archivo"], datos["curso"], len(datos["evaluaciones"]), True, None, datos.get("advertencias", []))
            )
    return sorted(reportes, key=lambda r: r.archivo)


def _completar(
    cohorte: Cohorte,
    silabos: list[ReporteSilabo],
    tiempos: dict[str, float],
    advertencias: list[str],
    propuesta: str,
    config: ConfigOptimizador | None,
) -> ResultadoSimulacion:
    inicio = time.perf_counter()
    resultado = optimizar(cohorte, config)
    tiempos["optimizar"] = round(time.perf_counter() - inicio, 3)

    inicio = time.perf_counter()
    if propuesta == "plantilla":
        texto = {"texto": propuesta_plantilla(datos_propuesta(cohorte, resultado)), "generada_por": "plantilla", "modelo": None, "advertencias": []}
    else:
        p = generar_propuesta(cohorte, resultado)
        texto = {"texto": p.texto, "generada_por": p.generada_por, "modelo": p.modelo, "advertencias": p.advertencias}
    tiempos["proponer"] = round(time.perf_counter() - inicio, 3)
    tiempos["total"] = round(sum(v for k, v in tiempos.items() if k != "total"), 3)
    return ResultadoSimulacion(cohorte, silabos, resultado, texto, tiempos, advertencias)


def simular_preset(
    clave: str = "ciclo-07",
    *,
    propuesta: str = "auto",
    config: ConfigOptimizador | None = None,
) -> ResultadoSimulacion:
    """Simulación con una cohorte de prueba. `propuesta`: "auto" (LLM si hay key) | "plantilla"."""
    if clave not in PRESETS:
        raise KeyError(f"Cohorte de prueba desconocida: {clave!r}. Disponibles: {sorted(PRESETS)}")
    preset = PRESETS[clave]
    tiempos: dict[str, float] = {}
    inicio = time.perf_counter()
    if preset.carpeta.is_dir() and any(preset.carpeta.glob("*.pdf")):
        lote = procesar_cohorte(
            preset.carpeta,
            nombre=f"Ingeniería de Computación y Sistemas – {clave} ({preset.ciclo})",
            ciclo=preset.ciclo,
            fecha_inicio=preset.fecha_inicio,
            cache=_cache_escribible(),
            caches_lectura=(CACHE_POR_DEFECTO,),
        )
        cohorte, silabos, advertencias = lote.cohorte, lote.reportes, lote.advertencias
    else:
        cohorte = cargar_cohorte(preset.cohorte_json)
        silabos, advertencias = _reportes_desde_cache(cohorte), ["PDFs no desplegados: se usó la cohorte ya extraída y su caché."]
    tiempos["leer"] = round(time.perf_counter() - inicio, 3)
    return _completar(cohorte, silabos, tiempos, advertencias, propuesta, config)


def simular_pdfs(
    archivos: list[tuple[str, bytes]],
    *,
    ciclo: str,
    fecha_inicio: date,
    nombre: str | None = None,
    propuesta: str = "auto",
    extractor: Extractor = _extraer_con_llm,
    config: ConfigOptimizador | None = None,
) -> ResultadoSimulacion:
    """Simulación con sílabos subidos: [(nombre_archivo, bytes_pdf), …]."""
    if not archivos:
        raise ValueError("Sube al menos un sílabo en PDF.")
    tiempos: dict[str, float] = {}
    inicio = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="pulso-") as tmp:
        carpeta = Path(tmp)
        for i, (nombre_archivo, contenido) in enumerate(archivos):
            if not contenido.startswith(b"%PDF"):
                raise ValueError(f"{nombre_archivo} no es un PDF.")
            seguro = "".join(ch for ch in Path(nombre_archivo).name if ch.isalnum() or ch in "-_.") or f"silabo-{i}.pdf"
            (carpeta / f"{i:02d}-{seguro}").write_bytes(contenido)
        lote = procesar_cohorte(
            carpeta,
            nombre=nombre or f"Cohorte subida ({ciclo})",
            ciclo=ciclo,
            fecha_inicio=fecha_inicio,
            cache=_cache_escribible(),
            caches_lectura=(CACHE_POR_DEFECTO,),
            extractor=extractor,
        )
    tiempos["leer"] = round(time.perf_counter() - inicio, 3)
    return _completar(lote.cohorte, lote.reportes, tiempos, lote.advertencias, propuesta, config)
