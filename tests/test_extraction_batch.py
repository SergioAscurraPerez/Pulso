import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from src.extraction.batch import extraer_con_cache, guardar_cohorte, procesar_cohorte, sha256
from src.extraction.llm_parser import ResultadoExtraccion
from src.models import Evaluacion, cargar_cohorte

RAIZ = Path(__file__).resolve().parents[1]
SILABOS = RAIZ / "data" / "silabos" / "ciclo-07"
INICIO = date(2026, 3, 30)


@pytest.fixture
def carpeta(tmp_path):
    destino = tmp_path / "silabos"
    destino.mkdir()
    for pdf in sorted(SILABOS.glob("*.pdf"))[:3]:
        shutil.copy(pdf, destino / pdf.name)
    return destino


class ExtractorStub:
    def __init__(self, falla: str | None = None):
        self.llamadas: list[str] = []
        self.falla = falla

    def __call__(self, pdf: Path) -> ResultadoExtraccion:
        self.llamadas.append(pdf.name)
        if self.falla and pdf.name.startswith(self.falla):
            raise RuntimeError("LLM caído")
        curso = pdf.stem.upper()
        evs = [
            Evaluacion(curso=curso, nombre="Examen parcial", tipo="examen_parcial", semana=8, peso=50),
            Evaluacion(curso=curso, nombre="Examen final", tipo="examen_final", semana=16, peso=50),
        ]
        return ResultadoExtraccion(curso, evs, 1, ["stub"])


def test_procesa_y_arma_cohorte_valida(carpeta, tmp_path):
    stub = ExtractorStub()
    lote = procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=tmp_path / "cache", extractor=stub)
    assert len(stub.llamadas) == 3
    assert len(lote.cohorte.evaluaciones) == 6 and len(lote.cohorte.cursos) == 3
    assert all(e.fecha is not None for e in lote.cohorte.evaluaciones)
    assert not lote.fallidos


def test_segunda_corrida_usa_cache_sin_llm(carpeta, tmp_path):
    cache = tmp_path / "cache"
    procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=cache, extractor=ExtractorStub())
    stub = ExtractorStub()
    lote = procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=cache, extractor=stub)
    assert stub.llamadas == []
    assert all(r.desde_cache for r in lote.reportes)
    assert len(list(cache.glob("*.json"))) == 3


def test_forzar_ignora_cache(carpeta, tmp_path):
    cache = tmp_path / "cache"
    procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=cache, extractor=ExtractorStub())
    stub = ExtractorStub()
    procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=cache, extractor=stub, forzar=True)
    assert len(stub.llamadas) == 3


def test_un_pdf_que_falla_no_detiene_el_lote(carpeta, tmp_path):
    primero = sorted(carpeta.glob("*.pdf"))[0].name[:5]
    lote = procesar_cohorte(
        carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=tmp_path / "cache", extractor=ExtractorStub(falla=primero)
    )
    assert len(lote.fallidos) == 1 and "LLM caído" in lote.fallidos[0].error
    assert len(lote.cohorte.cursos) == 2


def test_cache_guarda_por_hash_del_pdf(carpeta, tmp_path):
    pdf = sorted(carpeta.glob("*.pdf"))[0]
    extraer_con_cache(pdf, tmp_path, ExtractorStub())
    datos = json.loads((tmp_path / f"{sha256(pdf)}.json").read_text(encoding="utf-8"))
    assert datos["archivo"] == pdf.name and len(datos["evaluaciones"]) == 2


def test_carpeta_vacia(tmp_path):
    with pytest.raises(FileNotFoundError):
        procesar_cohorte(tmp_path, nombre="x", ciclo="2026-I", fecha_inicio=INICIO, extractor=ExtractorStub())


def test_guardar_y_cargar(carpeta, tmp_path):
    lote = procesar_cohorte(carpeta, nombre="c7", ciclo="2026-I", fecha_inicio=INICIO, cache=tmp_path / "cache", extractor=ExtractorStub())
    ruta = guardar_cohorte(lote.cohorte, tmp_path / "cohorte.json")
    assert cargar_cohorte(ruta) == lote.cohorte


def test_cohorte_real_del_repo_esta_completa_y_cacheada():
    """data/cohorte.json (ciclo 7) se regenera desde la caché sin LLM: la demo no depende de la API."""
    cohorte = cargar_cohorte(RAIZ / "data" / "cohorte.json")
    assert len(cohorte.cursos) == 6 and len(cohorte.evaluaciones) >= 30
    assert all(e.fecha is not None for e in cohorte.evaluaciones)
    def sin_llm(pdf):
        raise AssertionError(f"no debería llamar al LLM: {pdf.name}")
    lote = procesar_cohorte(SILABOS, nombre=cohorte.nombre, ciclo=cohorte.ciclo, fecha_inicio=cohorte.fecha_inicio, extractor=sin_llm)
    assert lote.cohorte == cohorte
