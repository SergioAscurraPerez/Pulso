import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.extraction.llm_parser import extraer_evaluaciones
from src.extraction.pdf_reader import leer_pdf
from src.extraction.recorte import recortar_para_extraccion

SILABOS = Path(__file__).resolve().parents[1] / "data" / "silabos"
MENCIONES = [
    r"Evaluaci[óo]n N[°ºo]\.?\s*\d",
    r"[Pp]r[áa]ctica [Cc]alificada\s*N?[°º.]?\s*\d",
    r"[Ee]xamen [Pp]arcial",
    r"[Ee]xamen [Ff]inal",
    r"[Aa]vance de [Ll]aboratorio",
]


@pytest.fixture(scope="module")
def isw2():
    return leer_pdf(SILABOS / "ciclo-07" / "ingenieria-de-software-ii-2026-I.pdf").texto


def test_recorta_mucho_y_conserva_lo_necesario(isw2):
    recortado, ok = recortar_para_extraccion(isw2)
    assert ok
    assert len(recortado) < 0.3 * len(isw2)
    assert "INGENIERIA DE SOFTWARE II" in recortado
    assert "PF = (2*PE+EP+EF)/4" in recortado and "W1 = Trabajo" in recortado
    lineas = recortado.splitlines()
    assert any(l.startswith("4 | ") and "Evaluación No. 1" in l for l in lineas)  # el número no se corta
    assert any(l.startswith("8 | ") and "Examen Parcial" in l for l in lineas)
    assert any(l.startswith("16 | ") and "Examen final" in l for l in lineas)
    assert "SUMILLA" not in recortado and "Competencia" not in recortado


@pytest.mark.parametrize("pdf", sorted(SILABOS.glob("ciclo-0[17]/*.pdf")), ids=lambda p: p.stem)
def test_no_pierde_menciones_de_evaluaciones(pdf):
    texto = leer_pdf(pdf).texto
    recortado, _ = recortar_para_extraccion(texto)
    for patron in MENCIONES:
        if re.search(patron, texto):
            assert re.search(patron, recortado), f"se perdió {patron!r}"
    assert re.search(r"\bP\s*F\b|promedio", recortado, re.I)


def test_sin_seccion_de_evaluacion_manda_el_texto_completo():
    texto = "=== Página 1 ===\nSÍLABO\nCURSO X\n1 | Introducción\n8 | Examen parcial"
    assert recortar_para_extraccion(texto) == (texto, False)


def test_sin_cronograma_manda_el_texto_completo():
    texto = "SÍLABO\nCURSO X\nVII. EVALUACIÓN DEL APRENDIZAJE\nPF = (EP + EF)/2"
    assert recortar_para_extraccion(texto) == (texto, False)


class ClienteStub:
    def __init__(self):
        self.llamadas = []
        respuesta = json.dumps(
            {
                "curso": "X",
                "evaluaciones": [
                    {"nombre": "EP", "tipo": "examen_parcial", "semana": 8, "peso": 50},
                    {"nombre": "EF", "tipo": "examen_final", "semana": 16, "peso": 50},
                ],
            }
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: self._crear(kw, respuesta)))

    def _crear(self, kwargs, respuesta):
        self.llamadas.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=respuesta))])


def test_el_extractor_envia_el_texto_recortado(isw2, monkeypatch):
    monkeypatch.delenv("LLM_RECORTE", raising=False)
    cliente = ClienteStub()
    extraer_evaluaciones(isw2, cliente=cliente, modelo="m")
    enviado = cliente.llamadas[0]["messages"][-1]["content"]
    assert "[Cronograma: semana | menciones de evaluaciones]" in enviado
    assert len(enviado) < 0.3 * len(isw2)


def test_recorte_desactivable(isw2, monkeypatch):
    monkeypatch.setenv("LLM_RECORTE", "off")
    cliente = ClienteStub()
    extraer_evaluaciones(isw2, cliente=cliente, modelo="m")
    assert isw2 in cliente.llamadas[0]["messages"][-1]["content"]
