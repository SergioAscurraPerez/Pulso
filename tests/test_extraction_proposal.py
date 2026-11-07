import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.extraction.proposal import datos_propuesta, fecha_larga, generar_propuesta, metricas_caso, propuesta_plantilla
from src.models import cargar_cohorte
from src.optimizer.objective import optimizar

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


@pytest.fixture(scope="module")
def caso():
    cohorte = cargar_cohorte(MOCK)
    return cohorte, optimizar(cohorte)


class ClienteStub:
    def __init__(self, texto="Resumen redactado por el LLM.", error=None):
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
    assert p.generada_por == "llm"
    # El LLM solo redacta el resumen: el resto del documento (cifras incluidas) lo arma el código.
    assert "## Resumen\nResumen redactado por el LLM." in p.texto
    assert "## Métricas del caso (antes → después)" in p.texto and "## Beneficio" in p.texto
    [llamada] = cliente.llamadas
    assert llamada["model"] == "proveedor/modelo"
    sistema, usuario = llamada["messages"]
    assert "No inventes" in sistema["content"]
    assert json.loads(usuario["content"])["reduccion_pico_pct"] == res.reduccion_pico_pct
    assert "Estimado" in sistema["content"] and "prohibidos" in sistema["content"]  # voz de documento, sin destinatario


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
    assert f"baja **{res.reduccion_pico_pct}%**" in texto
    for m in res.movimientos:
        assert m.curso in texto and m.nombre in texto
        assert (f"{m.dias:+d} día)" if abs(m.dias) == 1 else f"{m.dias:+d} días)") in texto
    assert "Colisiones (3 o más evaluaciones fuertes en 72 h): 3 → **0**" in texto


def test_limita_tokens_de_salida(caso):
    cohorte, res = caso
    cliente = ClienteStub()
    generar_propuesta(cohorte, res, cliente=cliente, modelo="m")
    assert 0 < cliente.llamadas[0]["max_tokens"] <= 4000


def test_documento_no_es_una_carta(caso):
    cohorte, res = caso
    texto = propuesta_plantilla(datos_propuesta(cohorte, res))
    assert texto.startswith("# Propuesta de reprogramación de evaluaciones")
    for saludo in ("Estimado", "Atentamente", "le presento", "usted"):
        assert saludo not in texto


def test_metricas_del_caso_con_matricula(caso):
    cohorte, res = caso  # el mock trae grupos de matrícula (120 estudiantes)
    m = metricas_caso(cohorte, res)
    a, d = m["antes"], m["despues"]
    assert (a["colisiones"], d["colisiones"]) == (res.colisiones_antes, res.colisiones_despues)
    assert a["evaluaciones_en_colision"] > d["evaluaciones_en_colision"] == 0
    assert a["alumnos_con_colision"] > d["alumnos_con_colision"] == 0
    assert m["reduccion_pico_pct"] == res.reduccion_pico_pct
    assert m["costo"]["evaluaciones_movidas"] == len(res.movimientos)
    assert m["costo"]["dias_movidos"] == sum(abs(x.dias) for x in res.movimientos)
    texto = propuesta_plantilla(datos_propuesta(cohorte, res))
    beneficio = texto.split("## Beneficio")[1].split("##")[0]
    assert f"{a['alumnos_con_colision']} estudiantes dejan" in beneficio
    assert f"Se eliminan **{a['colisiones']} de {a['colisiones']}** colisiones" in beneficio


def test_sin_matricula_lo_aclara_y_no_inventa_alumnos():
    cohorte = cargar_cohorte(Path(__file__).resolve().parents[1] / "data" / "cohorte.json")
    res = optimizar(cohorte)
    m = metricas_caso(cohorte, res)
    assert m["antes"]["alumnos_con_colision"] is None
    texto = propuesta_plantilla(datos_propuesta(cohorte, res))
    assert "Sin datos de matrícula" in texto
    assert "Estudiantes con al menos una colisión" not in texto
