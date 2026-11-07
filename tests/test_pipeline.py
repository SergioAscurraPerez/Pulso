import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import pipeline
from src.app import app
from src.extraction.llm_parser import ResultadoExtraccion
from src.models import Evaluacion

RAIZ = Path(__file__).resolve().parents[1]
ISW2 = RAIZ / "data" / "silabos" / "ciclo-07" / "ingenieria-de-software-ii-2026-I.pdf"


@pytest.fixture
def cliente():
    return TestClient(app)


@pytest.fixture(autouse=True)
def cache_temporal(tmp_path, monkeypatch):
    """Lo que se extraiga en los tests se escribe en tmp, nunca en la caché del repo."""
    monkeypatch.setenv("PULSO_CACHE_DIR", str(tmp_path / "cache"))


def test_presets(cliente):
    [preset] = cliente.get("/api/presets").json()
    assert preset["clave"] == "ciclo-07" and preset["fecha_inicio"] == "2026-03-02"


def test_simulacion_punta_a_punta_con_ciclo_7(cliente):
    r = cliente.get("/api/simular", params={"preset": "ciclo-07", "propuesta": "plantilla"})
    assert r.status_code == 200
    d = r.json()
    assert d["cohorte"]["evaluaciones"] == 38 and len(d["cohorte"]["cursos"]) == 6
    leer, medir, optimizar, proponer = (d["pasos"][k] for k in ("leer", "medir", "optimizar", "proponer"))
    assert len(leer["silabos"]) == 6 and all(s["desde_cache"] and not s["error"] for s in leer["silabos"])
    assert len(medir["colisiones"]) == 3 and medir["semana_pico"]["semana"] == 16
    assert optimizar["estado"] in ("OPTIMAL", "FEASIBLE")
    assert optimizar["colisiones_despues"] < optimizar["colisiones_antes"]
    assert optimizar["evaluaciones_movidas"] > 0
    assert proponer["generada_por"] == "plantilla" and "Cambios propuestos" in proponer["texto"]
    assert d["tiempos_s"]["total"] < 5


def test_sin_pdfs_desplegados_usa_cohorte_y_cache(monkeypatch):
    """En Vercel data/silabos/ no se despliega: la simulación sale de data/cohorte.json + caché."""
    sin_carpeta = replace(pipeline.PRESETS["ciclo-07"], carpeta=Path("no-existe"))
    monkeypatch.setitem(pipeline.PRESETS, "ciclo-07", sin_carpeta)
    r = pipeline.simular_preset("ciclo-07", propuesta="plantilla")
    assert len(r.cohorte.evaluaciones) == 38
    assert len(r.silabos) == 6 and all(s.desde_cache for s in r.silabos)
    assert r.advertencias


def test_preset_desconocido(cliente):
    assert cliente.get("/api/simular", params={"preset": "ciclo-99"}).status_code == 404


def test_subir_pdf_ya_extraido_no_llama_al_llm(cliente, monkeypatch):
    def sin_llm(pdf):
        raise AssertionError("no debería llamar al LLM")

    monkeypatch.setattr(pipeline, "_extraer_con_llm", sin_llm)
    r = cliente.post(
        "/api/simular",
        files=[("archivos", (ISW2.name, ISW2.read_bytes(), "application/pdf"))],
        data={"ciclo": "2026-I", "inicio": "2026-03-02", "propuesta": "plantilla"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["cohorte"]["cursos"] == ["INGENIERIA DE SOFTWARE II"]
    assert d["pasos"]["leer"]["silabos"][0]["desde_cache"] is True


def test_subir_pdf_nuevo_usa_el_extractor(tmp_path):
    def extractor(pdf):
        evs = [
            Evaluacion(curso="Curso Nuevo", nombre="Examen parcial", tipo="examen_parcial", semana=8, peso=50),
            Evaluacion(curso="Curso Nuevo", nombre="Examen final", tipo="examen_final", semana=16, peso=50),
        ]
        return ResultadoExtraccion("Curso Nuevo", evs, 1, [])

    contenido = b"%PDF-1.4 silabo de prueba " + tmp_path.name.encode()
    r = pipeline.simular_pdfs([("nuevo.pdf", contenido)], ciclo="2026-I", fecha_inicio=date(2026, 3, 2), propuesta="plantilla", extractor=extractor)
    assert r.cohorte.cursos == ["Curso Nuevo"]
    assert r.silabos[0].desde_cache is False
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1  # se cacheó en la carpeta escribible
    json.loads(r.to_json())


@pytest.mark.parametrize(
    "archivos, data, codigo",
    [
        ([("archivos", ("x.txt", b"hola", "text/plain"))], {"ciclo": "2026-I", "inicio": "2026-03-02"}, 422),
        ([("archivos", ("x.pdf", b"%PDF-1.4", "application/pdf"))], {"ciclo": "2026-I", "inicio": "2026-03-04"}, 422),
    ],
    ids=["no-es-pdf", "inicio-no-es-lunes"],
)
def test_validaciones_de_subida(cliente, archivos, data, codigo):
    assert cliente.post("/api/simular", files=archivos, data=data).status_code == codigo


def test_cache_no_escribible_cae_a_tmp(tmp_path, monkeypatch):
    archivo = tmp_path / "soy-un-archivo"
    archivo.write_text("x")
    monkeypatch.setenv("PULSO_CACHE_DIR", str(archivo / "cache"))  # no se puede crear dentro de un archivo
    assert pipeline._cache_escribible().name == "pulso-cache"
