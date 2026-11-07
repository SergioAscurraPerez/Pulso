import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from src.extraction.pdf_reader import leer_pdf, limpiar, tabla_a_texto

SILABOS = sorted((Path(__file__).resolve().parents[1] / "data" / "silabos" / "ciclo-07").glob("*.pdf"))


@pytest.fixture(scope="module")
def leidos():
    return {p.name: leer_pdf(p) for p in SILABOS}


def test_hay_sílabos_de_prueba():
    assert 5 <= len(SILABOS) <= 8


@pytest.mark.parametrize("pdf", SILABOS, ids=lambda p: p.stem)
def test_silabo_devuelve_texto_legible(leidos, pdf):
    r = leidos[pdf.name]
    assert r.metodo == "texto"
    assert r.caracteres > 5000
    assert r.tablas > 0
    texto = r.texto.upper()
    assert "EVALUACI" in texto and "SEMANA" in texto
    assert not any("" <= c <= "" for c in r.texto)
    assert "=== Página 1 ===" in r.texto


def test_cronograma_conserva_semana_y_evaluacion(leidos):
    texto = leidos["ingenieria-de-software-ii-2026-I.pdf"].texto
    lineas = texto.splitlines()
    assert any(l.startswith("8 |") and "Examen Parcial" in l for l in lineas)
    assert any(l.startswith("16 |") and "Examen final" in l for l in lineas)
    assert "PF = (2*PE+EP+EF)/4" in texto


def test_limpiar():
    assert limpiar("  Reconoce\t los conceptos\n\n\n\nfin") == "- Reconoce los conceptos\n\nfin"


def test_tabla_a_texto_omite_vacios():
    assert tabla_a_texto([["SEMANA", None, "TEMA"], [None, None, None], ["8", "", "Examen\nparcial"]]) == (
        "SEMANA | TEMA\n8 | Examen parcial"
    )


def _pdf_sin_texto(paginas: int = 2) -> bytes:
    doc = pdfium.PdfDocument.new()
    for _ in range(paginas):
        doc.new_page(595, 842)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_pdf_escaneado_usa_vision():
    llamadas = []

    def transcriptor(imagenes):
        llamadas.append(imagenes)
        assert all(img.startswith(b"\x89PNG") for img in imagenes)
        return ["Semana 8 | Examen parcial  25%", "Semana 16 | Examen final"]

    r = leer_pdf(_pdf_sin_texto(), transcriptor=transcriptor)
    assert r.metodo == "vision"
    assert len(llamadas) == 1 and len(llamadas[0]) == 2
    assert "Semana 8 | Examen parcial - 25%" in r.texto
    assert r.advertencias


def test_acepta_bytes(leidos):
    pdf = SILABOS[0]
    r = leer_pdf(pdf.read_bytes())
    assert r.archivo == "subido.pdf"
    assert r.texto == leidos[pdf.name].texto
