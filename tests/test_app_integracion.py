"""Integración de la app con la extracción y la propuesta (PUL-17). No llaman al LLM: simulan que no está configurado."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.app as app_modulo
from src.extraction import llm_parser, proposal
from src.extraction.llm import ConfigLLM
from src.models import cargar_cohorte

cliente = TestClient(app_modulo.app)
SILABOS = sorted(Path("data/silabos/ciclo-07").glob("*.pdf"))  # sus extracciones están en data/cache/extraccion


@pytest.fixture
def sin_llm(monkeypatch):
    """Simula que no hay LLM configurado aunque exista un .env local (los módulos de A leen la config por su cuenta)."""
    vacia = lambda: ConfigLLM("", "", "")  # noqa: E731
    for modulo in (app_modulo, proposal, llm_parser):
        monkeypatch.setattr(modulo, "config_llm", vacia)


@pytest.fixture
def tmp_app(tmp_path, monkeypatch):
    """/tmp de la app aislado por test (caché de extracción y cohorte subida)."""
    monkeypatch.setattr(app_modulo, "DIR_TMP", tmp_path)
    monkeypatch.setitem(app_modulo.FUENTES, "subida", ("Sílabos subidos", tmp_path / "cohorte-subida.json"))
    return tmp_path


def _subir(archivos, ciclo="2026-I", fecha_inicio="2026-03-30"):
    return cliente.post(
        "/cargar",
        files=[("archivos", (nombre, datos, "application/pdf")) for nombre, datos in archivos],
        data={"ciclo": ciclo, "fecha_inicio": fecha_inicio},
    )


def test_la_cohorte_real_reemplaza_al_mock_por_defecto():
    assert app_modulo.FUENTE_POR_DEFECTO == "cohorte"
    assert cargar_cohorte("data/cohorte.json").nombre in cliente.get("/").text


def test_formulario_de_carga_trae_ciclo_e_inicio_de_la_cohorte_real():
    respuesta = cliente.get("/cargar")
    assert respuesta.status_code == 200
    assert 'value="2026-I"' in respuesta.text
    assert 'value="2026-03-30"' in respuesta.text


def test_subir_silabos_en_cache_arma_la_cohorte_sin_llamar_al_llm(tmp_app, monkeypatch):
    def sin_llamadas(pdf):
        raise AssertionError(f"no debía llamar al LLM: {pdf}")

    monkeypatch.setattr(app_modulo, "_extraer_en_linea", sin_llamadas)
    respuesta = _subir([(pdf.name, pdf.read_bytes()) for pdf in SILABOS])
    assert respuesta.status_code == 200
    assert respuesta.text.count("(caché)") == len(SILABOS)

    # Mismo pipeline y mismos parámetros que data/cohorte.json → mismas evaluaciones.
    subida = cargar_cohorte(tmp_app / "cohorte-subida.json")
    assert {e.id for e in subida.evaluaciones} == {e.id for e in cargar_cohorte("data/cohorte.json").evaluaciones}
    for ruta in ["/carga", "/antes-despues", "/simulador"]:
        assert cliente.get(ruta, params={"fuente": "subida"}).status_code == 200


def test_el_mismo_pdf_dos_veces_cuenta_una(tmp_app):
    pdf = SILABOS[0]
    respuesta = _subir([(pdf.name, pdf.read_bytes()), ("copia.pdf", pdf.read_bytes())])
    assert respuesta.status_code == 200
    assert respuesta.text.count("(caché)") == 1


def test_pdf_nuevo_sin_llm_da_error_claro(tmp_app, sin_llm):
    respuesta = _subir([("nuevo.pdf", b"%PDF-1.4 sin cache")])
    assert respuesta.status_code == 422
    assert "no está en la caché y el LLM no está configurado" in respuesta.text
    assert not (tmp_app / "cohorte-subida.json").exists()


@pytest.mark.parametrize(
    ("archivos", "datos", "mensaje"),
    [
        ([("a.pdf", b"%PDF-1.4 a"), ("b.pdf", b"%PDF-1.4 b")], {}, "Solo se puede extraer 1 sílabo nuevo"),
        ([("notas.pdf", b"no soy un pdf")], {}, "No son PDF: notas.pdf"),
        ([("a.pdf", b"%PDF-1.4 a")], {"fecha_inicio": "2026-03-31"}, "debe ser el lunes"),
        ([("a.pdf", b"%PDF-1.4 a")], {"ciclo": "  "}, "Indica el ciclo"),
    ],
)
def test_subida_invalida_se_rechaza_con_mensaje(tmp_app, archivos, datos, mensaje):
    respuesta = _subir(archivos, **datos)
    assert respuesta.status_code == 422
    assert mensaje in respuesta.text


def test_antes_despues_pide_la_propuesta_aparte():
    assert 'hx-get="/antes-despues/propuesta?fuente=mock"' in cliente.get("/antes-despues", params={"fuente": "mock"}).text


def test_propuesta_sin_llm_usa_la_plantilla(sin_llm):
    app_modulo._propuesta.cache_clear()
    respuesta = cliente.get("/antes-despues/propuesta", params={"fuente": "mock"})
    assert respuesta.status_code == 200
    assert "Generada con la plantilla" in respuesta.text
    assert "<h3>Cambios propuestos</h3>" in respuesta.text
    app_modulo._propuesta.cache_clear()


def test_markdown_simple_escapa_el_html_del_llm():
    html = app_modulo.markdown_simple("## Título\n<script>alert(1)</script>\n- **uno**\n- dos\nfin")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<h3>Título</h3>" in html
    assert "<ul>\n<li><strong>uno</strong></li>\n<li>dos</li>\n</ul>" in html
