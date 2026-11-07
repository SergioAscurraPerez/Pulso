import time
from datetime import date
from pathlib import Path

from src.models import Evaluacion, cargar_cohorte
from src.optimizer.simulator import evaluar_fecha, fechas_alternativas, simular

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


def _cohorte():
    return cargar_cohorte(MOCK)


def _por_id(cohorte, id_):
    return next(e for e in cohorte.evaluaciones if e.id == id_)


def test_parcial_io_en_semana_8_afecta_a_quienes_llevan_bd_y_so():
    c = _cohorte()
    io = _por_id(c, "investigacion-operativa--examen-parcial")
    esc = evaluar_fecha(c, io, io.fecha)
    # IO la llevan 70 + 20 + 15 = 105; los 15 de [SO, IO, Redes] no llevan BD → solo 2 fuertes en 72 h.
    assert esc.alumnos_del_curso == 105
    assert esc.alumnos_con_colision == 90
    assert esc.pct_colision == 85.7
    assert esc.colisiones


def test_simular_encuentra_alternativa_sin_colision():
    c = _cohorte()
    pc2 = _por_id(c, "sistemas-operativos--practica-calificada-2")  # semana 12, en colisión
    res = simular(c, pc2, pc2.fecha)
    assert res.propuesta.pct_colision > 0
    assert res.mejor_alternativa is not None
    assert res.mejor_alternativa.pct_colision == 0
    assert abs((res.mejor_alternativa.fecha - pc2.fecha).days) <= 7
    assert res.mejor_alternativa.fecha.weekday() < 5


def test_parcial_en_semana_de_examenes_no_sale_de_ella():
    c = _cohorte()
    io = _por_id(c, "investigacion-operativa--examen-parcial")
    fechas = fechas_alternativas(c, io, io.fecha)
    assert fechas and all(date(2026, 10, 12) <= f <= date(2026, 10, 16) for f in fechas)
    # Dentro de la semana 8 no hay día sin colisión: hay que mover otras (lo resuelve el optimizador).
    assert simular(c, io, io.fecha).mejor_alternativa is None


def test_practica_no_entra_a_semana_de_examenes():
    c = _cohorte()
    pc = _por_id(c, "redes-de-computadoras--practica-calificada-1")  # viernes semana 7
    assert all(not date(2026, 10, 12) <= f <= date(2026, 10, 18) for f in fechas_alternativas(c, pc, pc.fecha))


def test_evaluacion_nueva_del_docente():
    c = _cohorte()
    nueva = Evaluacion(curso="Redes de Computadoras", nombre="Práctica calificada 3", tipo="practica_calificada", peso=15, fecha=date(2026, 10, 13))
    res = simular(c, nueva, date(2026, 10, 13))  # martes de la semana 8
    assert res.propuesta.pct_colision == 100.0
    assert res.mejor_alternativa.pct_colision == 0


def test_fecha_sin_riesgo_no_propone_alternativa_peor():
    c = _cohorte()
    nueva = Evaluacion(curso="Ética y Deontología", nombre="Tarea 1", tipo="tarea", peso=5, fecha=date(2026, 9, 2))
    res = simular(c, nueva, date(2026, 9, 2))
    assert res.propuesta.pct_colision == 0
    if res.mejor_alternativa:
        assert res.mejor_alternativa.carga_semana < res.propuesta.carga_semana


def test_curso_nuevo_se_asume_para_toda_la_cohorte():
    c = _cohorte()
    nueva = Evaluacion(curso="Curso electivo", nombre="Examen", tipo="examen_parcial", peso=40, fecha=date(2026, 10, 13))
    esc = evaluar_fecha(c, nueva, nueva.fecha)
    assert esc.alumnos_del_curso == c.total_estudiantes == 120


def test_alternativas_respetan_ciclo_feriados_y_fines_de_semana():
    c = _cohorte()
    feriado = date(2026, 10, 8)
    tarea = Evaluacion(curso="Ética y Deontología", nombre="Tarea 2", tipo="tarea", peso=5, fecha=date(2026, 10, 6))
    fechas = fechas_alternativas(c, tarea, tarea.fecha, feriados={feriado})
    assert feriado not in fechas and tarea.fecha not in fechas
    assert all(f.weekday() < 5 for f in fechas)
    assert min(fechas_alternativas(c, tarea, date(2026, 8, 25))) >= c.fecha_inicio


def test_responde_en_menos_de_2_s():
    c = _cohorte()
    io = _por_id(c, "investigacion-operativa--examen-parcial")
    inicio = time.perf_counter()
    simular(c, io, io.fecha)
    assert time.perf_counter() - inicio < 2


def test_to_dict_serializable():
    import json

    c = _cohorte()
    io = _por_id(c, "investigacion-operativa--examen-parcial")
    json.dumps(simular(c, io, io.fecha).to_dict())
