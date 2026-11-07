"""Procesar el lote de sílabos de una cohorte y consolidar `data/cohorte.json` (PUL-07).

PDF → texto (PUL-04) → evaluaciones con LLM (PUL-05) → normalización (PUL-06) → `Cohorte`.

Caché en disco: la extracción de cada PDF se guarda en `data/cache/extraccion/<sha256 del PDF>.json`.
Si el PDF no cambió, no se vuelve a llamar al LLM. Así la demo no depende de la API en vivo,
y los archivos de caché se commitean junto con `data/cohorte.json`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from src.extraction.llm_parser import ResultadoExtraccion, extraer_evaluaciones
from src.extraction.normalize import normalizar
from src.extraction.pdf_reader import leer_pdf
from src.models import Cohorte, Evaluacion

RAIZ = Path(__file__).resolve().parents[2]
CACHE_POR_DEFECTO = RAIZ / "data" / "cache" / "extraccion"
SALIDA_POR_DEFECTO = RAIZ / "data" / "cohorte.json"

Extractor = Callable[[Path], ResultadoExtraccion]


@dataclass
class ReporteSilabo:
    archivo: str
    curso: str | None
    evaluaciones: int
    desde_cache: bool
    error: str | None = None
    advertencias: list[str] = field(default_factory=list)


@dataclass
class ResultadoLote:
    cohorte: Cohorte
    reportes: list[ReporteSilabo]
    advertencias: list[str]

    @property
    def fallidos(self) -> list[ReporteSilabo]:
        return [r for r in self.reportes if r.error]


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _extraer_con_llm(pdf: Path) -> ResultadoExtraccion:
    return extraer_evaluaciones(leer_pdf(pdf))


def extraer_con_cache(
    pdf: Path,
    cache: Path,
    extractor: Extractor,
    forzar: bool = False,
    caches_lectura: tuple[Path, ...] = (),
) -> tuple[ResultadoExtraccion, bool]:
    """Devuelve la extracción del PDF y si vino de la caché.

    Busca en `cache` y en `caches_lectura` (p. ej. la caché del repo, de solo lectura en Vercel);
    lo que extrae el LLM se escribe en `cache`.
    """
    nombre = f"{sha256(pdf)}.json"
    archivo_cache = cache / nombre
    if not forzar:
        for carpeta in (cache, *caches_lectura):
            if (carpeta / nombre).is_file():
                datos = json.loads((carpeta / nombre).read_text(encoding="utf-8"))
                evaluaciones = [Evaluacion.model_validate(e) for e in datos["evaluaciones"]]
                return ResultadoExtraccion(datos["curso"], evaluaciones, 0, datos.get("advertencias", [])), True

    resultado = extractor(pdf)
    cache.mkdir(parents=True, exist_ok=True)
    archivo_cache.write_text(
        json.dumps(
            {
                "archivo": pdf.name,
                "curso": resultado.curso,
                "extraido_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "intentos": resultado.intentos,
                "advertencias": resultado.advertencias,
                "evaluaciones": [e.model_dump(mode="json") for e in resultado.evaluaciones],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return resultado, False


def procesar_cohorte(
    carpeta: Path,
    *,
    nombre: str,
    ciclo: str,
    fecha_inicio: date,
    cache: Path = CACHE_POR_DEFECTO,
    extractor: Extractor = _extraer_con_llm,
    dias_clase: dict[str, int] | None = None,
    forzar: bool = False,
    al_procesar: Callable[[ReporteSilabo], None] | None = None,
    caches_lectura: tuple[Path, ...] = (),
) -> ResultadoLote:
    """Procesa todos los PDFs de `carpeta` y arma la `Cohorte`. Un PDF que falla no detiene el lote."""
    pdfs = sorted(Path(carpeta).glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"No hay PDFs en {carpeta}")

    evaluaciones: list[Evaluacion] = []
    reportes: list[ReporteSilabo] = []
    for pdf in pdfs:
        try:
            resultado, desde_cache = extraer_con_cache(pdf, cache, extractor, forzar, caches_lectura)
            evaluaciones += resultado.evaluaciones
            reporte = ReporteSilabo(pdf.name, resultado.curso, len(resultado.evaluaciones), desde_cache, None, resultado.advertencias)
        except Exception as error:  # noqa: BLE001 — se reporta y se sigue con el resto
            reporte = ReporteSilabo(pdf.name, None, 0, False, str(error))
        reportes.append(reporte)
        if al_procesar:
            al_procesar(reporte)

    if not evaluaciones:
        raise RuntimeError("Ningún sílabo pudo extraerse; revisa los errores del reporte.")
    normalizado = normalizar(evaluaciones, fecha_inicio, dias_clase=dias_clase)
    cohorte = Cohorte(nombre=nombre, ciclo=ciclo, fecha_inicio=fecha_inicio, evaluaciones=normalizado.evaluaciones)
    return ResultadoLote(cohorte, reportes, normalizado.advertencias)


def guardar_cohorte(cohorte: Cohorte, salida: Path = SALIDA_POR_DEFECTO) -> Path:
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(cohorte.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return salida
