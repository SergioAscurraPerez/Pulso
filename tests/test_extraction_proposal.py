import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.extraction.proposal import datos_propuesta, fecha_larga, generar_propuesta, propuesta_plantilla
from src.models import cargar_cohorte
from src.optimizer.objective import optimizar

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


@pytest.fixture(scope="module")
def caso():
    cohorte = cargar_cohorte(MOCK)
    return cohorte, optimizar(cohorte)


class ClienteStub:
    def __init__(self, texto="## Propuesta\nTexto del LLM", error=None):
        self.llamadas = []
        self.texto, self.error = texto, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.llamadas.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.texto))])


def test_fecha_larga():
    assert fecha_larga(date(2026, 10, 12)) == "lunes 12 de octubre"


def test_datos_vienen_del_solver(caso):
    cohorte, res = caso
    d = datos_propuesta(cohorte, res)
    assert d["reduccion_pico_pct"] == res.reduccion_pico_pct
    assert len(d["movimientos"]) == len(res.movimientos)
    assert d["colisiones_antes"] == 3 and d["colisiones_despues"] == 0
    assert d["evaluaciones_bloqueadas"] == 4
    json.dumps(d, ensure_ascii=False)


def test_usa_el_llm_con_los_datos(caso):
    cohorte, res = caso
    cliente = ClienteStub()
    p = generar_propuesta(cohorte, res, cliente=cliente, modelo="proveedor/modelo")
    assert p.generada_por == "llm" and p.texto == "## Propuesta\nTexto del LLM"
    [llamada] = cliente.llamadas
    assert llamada["model"] == "proveedor/modelo"
    sistema, usuario = llamada["messages"]
    assert "No inventes" in sistema["content"]
    assert json.loads(usuario["content"])["reduccion_pico_pct"] == res.reduccion_pico_pct


@pytest.mark.parametrize("cliente", [ClienteStub(error=RuntimeError("timeout")), ClienteStub(texto="")])
def test_si_el_llm_falla_usa_plantilla(caso, cliente):
    cohorte, res = caso
    p = generar_propuesta(cohorte, res, cliente=cliente, modelo="x")
    assert p.generada_por == "plantilla"
    assert p.advertencias


def test_sin_api_key_usa_plantilla(caso, monkeypatch):
    cohorte, res = caso
    monkeypatch.setattr("src.extraction.proposal.config_llm", lambda: SimpleNamespace(completa=False, modelo=""))
    p = generar_propuesta(cohorte, res)
    assert p.generada_por == "plantilla"


def test_plantilla_incluye_movimientos_dias_y_reduccion(caso):
    cohorte, res = caso
    texto = propuesta_plantilla(datos_propuesta(cohorte, res))
    assert f"−{res.reduccion_pico_pct}%" in texto
    for m in res.movimientos:
        assert m.curso in texto and m.nombre in texto and f"{m.dias:+d} días" in texto
    assert "3 → 0" in texto
