from datetime import date
from pathlib import Path

from src.engine.load_index import (
    FACTOR_TIPO,
    carga_evaluacion,
    carga_semanal,
    carga_semanal_cohorte,
    semana_de,
    semana_pico,
)
from src.models import SEMANAS_CICLO, Evaluacion, TipoEvaluacion, cargar_cohorte

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"
INICIO = date(2026, 8, 24)


def _ev(nombre: str, tipo: str, peso: float, fecha: date | None = None, semana: int | None = None) -> Evaluacion:
    return Evaluacion(curso="Curso", nombre=nombre, tipo=tipo, peso=peso, fecha=fecha, semana=semana)


def test_todos_los_tipos_tienen_factor():
    assert set(FACTOR_TIPO) == set(TipoEvaluacion)


def test_carga_evaluacion_es_peso_por_factor():
    assert carga_evaluacion(_ev("EP", "examen_parcial", 30, semana=8)) == 30 * 1.3


def test_semana_de_usa_fecha_semana_o_fecha_propuesta():
    ev = _ev("PC", "practica_calificada", 10, fecha=date(2026, 8, 30))  # domingo de la semana 1
    assert semana_de(ev, INICIO) == 1
    assert semana_de(ev, INICIO, fecha=date(2026, 9, 1)) == 2
    assert semana_de(_ev("T", "tarea", 5, semana=7), INICIO) == 7


def test_carga_semanal_suma_por_semana_e_incluye_semanas_vacias():
    evs = [
        _ev("A", "examen_parcial", 30, fecha=date(2026, 10, 12)),  # semana 8
        _ev("B", "tarea", 10, fecha=date(2026, 10, 14)),  # semana 8
        _ev("C", "laboratorio", 10, semana=3),
    ]
    carga = carga_semanal(evs, INICIO)
    assert len(carga) == SEMANAS_CICLO
    assert carga[8] == 30 * 1.3 + 10 * 0.6
    assert carga[3] == 10 * 0.7
    assert carga[1] == 0


def test_mock_pico_en_semana_16_y_parciales_en_8():
    cohorte = cargar_cohorte(MOCK)
    carga = carga_semanal_cohorte(cohorte)
    assert sum(carga.values()) > 0
    assert semana_pico(carga)[0] == 16
    assert carga[8] > 2 * carga[7]


def test_fechas_propuestas_cambian_la_carga():
    cohorte = cargar_cohorte(MOCK)
    parcial_io = next(e for e in cohorte.evaluaciones if e.id == "investigacion-operativa--examen-parcial")
    antes = carga_semanal_cohorte(cohorte)
    despues = carga_semanal_cohorte(cohorte, fechas={parcial_io.id: date(2026, 10, 22)})  # semana 9
    delta = carga_evaluacion(parcial_io)
    assert despues[8] == round(antes[8] - delta, 2)
    assert despues[9] == round(antes[9] + delta, 2)
