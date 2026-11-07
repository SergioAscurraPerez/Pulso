import json
from collections import Counter
from pathlib import Path

import pytest

from src.engine.collisions import es_fuerte
from src.engine.load_index import semana_de, semana_permitida
from src.models import cargar_cohorte
from src.optimizer.cpsat_model import ConfigOptimizador
from src.optimizer.objective import optimizar

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


@pytest.fixture(scope="module")
def cohorte():
    return cargar_cohorte(MOCK)


@pytest.fixture(scope="module")
def resultado(cohorte):
    return optimizar(cohorte)


def test_reduce_el_pico_y_elimina_colisiones(resultado):
    assert resultado.factible
    assert resultado.tiempo_s < 10
    assert resultado.pico_antes == (16, 255.0)
    assert resultado.reduccion_pico_pct >= 30
    assert resultado.colisiones_antes == 3
    assert resultado.colisiones_despues == 0


def test_diff_describe_lo_que_se_movio(cohorte, resultado):
    originales = {e.id: e.fecha for e in cohorte.evaluaciones}
    assert resultado.movimientos
    for mov in resultado.movimientos:
        assert mov.fecha_original == originales[mov.id]
        assert mov.fecha_nueva == resultado.fechas[mov.id] != mov.fecha_original
        assert mov.dias == (mov.fecha_nueva - mov.fecha_original).days
    movidos = {m.id for m in resultado.movimientos}
    assert all(resultado.fechas[i] == f for i, f in originales.items() if i not in movidos)


def test_respeta_restricciones(cohorte, resultado):
    cfg = ConfigOptimizador()
    for ev in cohorte.evaluaciones:
        nueva = resultado.fechas[ev.id]
        if ev.bloqueada:
            assert nueva == ev.fecha
        assert abs((nueva - ev.fecha).days) <= cfg.ventana_dias
        assert nueva.weekday() < 5
        assert semana_permitida(ev, semana_de(ev, cohorte.fecha_inicio), semana_de(ev, cohorte.fecha_inicio, nueva))


def test_no_deja_dos_fuertes_el_mismo_dia(cohorte, resultado):
    por_dia = Counter(resultado.fechas[e.id] for e in cohorte.evaluaciones if es_fuerte(e))
    assert max(por_dia.values()) == 1


def test_todo_bloqueado_no_mueve_nada(cohorte):
    bloqueada = cohorte.model_copy(
        update={"evaluaciones": [e.model_copy(update={"bloqueada": True}) for e in cohorte.evaluaciones]}
    )
    res = optimizar(bloqueada)
    assert res.factible
    assert res.movimientos == []
    assert res.reduccion_pico_pct == 0


def test_to_dict_es_serializable(resultado):
    d = json.loads(json.dumps(resultado.to_dict()))
    assert d["reduccion_pico_pct"] == resultado.reduccion_pico_pct
    assert d["evaluaciones_movidas"] == len(resultado.movimientos)
