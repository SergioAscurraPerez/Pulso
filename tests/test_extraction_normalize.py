from datetime import date

import pytest

from src.extraction.normalize import (
    FERIADOS_PERU_2026,
    asignar_dias_clase,
    fecha_de_semana,
    normalizar,
    tipo_desde_nombre,
)
from src.models import Evaluacion, TipoEvaluacion

INICIO = date(2026, 3, 30)  # lunes, semana 1 del ciclo 2026-I


def _ev(curso="Curso A", nombre="Práctica calificada 1", tipo="practica_calificada", **kw) -> Evaluacion:
    return Evaluacion(curso=curso, nombre=nombre, tipo=tipo, peso=10, **({"semana": 4} | kw))


def test_todas_quedan_con_fecha_y_tipo_valido():
    evs = [
        _ev(semana=8, nombre="Examen parcial", tipo="examen_parcial"),
        _ev(curso="Curso B", semana=16, nombre="Examen final", tipo="examen_final"),
        _ev(curso="Curso C", semana=5, nombre="Laboratorio 2", tipo="otro"),
    ]
    r = normalizar(evs, INICIO)
    assert all(e.fecha is not None and isinstance(e.tipo, TipoEvaluacion) for e in r.evaluaciones)
    assert r.evaluaciones[2].tipo is TipoEvaluacion.LABORATORIO


def test_semana_a_fecha_con_dia_de_clase_del_curso():
    r = normalizar([_ev(semana=1), _ev(nombre="PC2", semana=8)], INICIO, dias_clase={"Curso A": 2})
    assert [e.fecha for e in r.evaluaciones] == [date(2026, 4, 1), date(2026, 5, 20)]  # miércoles
    assert all(e.fecha.weekday() == 2 for e in r.evaluaciones)


def test_dias_clase_se_reparten_y_no_dependen_del_orden():
    a = asignar_dias_clase(["C", "A", "B", "E", "D", "F"])
    b = asignar_dias_clase(["F", "E", "D", "C", "B", "A"])
    assert a == b == {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 0}
    assert asignar_dias_clase(["A", "B"], {"B": 4}) == {"A": 0, "B": 4}


def test_feriado_pasa_al_siguiente_dia_habil():
    # Semana 1 del ciclo: jueves 2 y viernes 3 de abril son Semana Santa.
    assert fecha_de_semana(INICIO, 1, 3, FERIADOS_PERU_2026) == date(2026, 4, 1)  # jue y vie feriados → miércoles
    assert fecha_de_semana(INICIO, 6, 4, FERIADOS_PERU_2026) == date(2026, 5, 8)  # viernes normal
    assert fecha_de_semana(date(2026, 4, 27), 1, 4, FERIADOS_PERU_2026) == date(2026, 4, 30)  # vie 1/5 → jueves


def test_fecha_explicita_manda_y_recalcula_semana():
    r = normalizar([_ev(semana=3, fecha=date(2026, 5, 20))], INICIO)
    assert r.evaluaciones[0].fecha == date(2026, 5, 20)
    assert r.evaluaciones[0].semana == 8
    assert any("no coincide" in a for a in r.advertencias)


def test_fecha_fuera_del_ciclo_advierte():
    r = normalizar([_ev(fecha=date(2025, 1, 10), semana=None)], INICIO)
    assert r.evaluaciones[0].semana == 1
    assert any("fuera del ciclo" in a for a in r.advertencias)


def test_inicio_debe_ser_lunes():
    with pytest.raises(ValueError, match="lunes"):
        normalizar([_ev()], date(2026, 4, 1))


def test_no_modifica_las_originales():
    original = _ev(semana=8)
    normalizar([original], INICIO)
    assert original.fecha is None


@pytest.mark.parametrize(
    "nombre, tipo",
    [
        ("Examen Final (EF)", TipoEvaluacion.EXAMEN_FINAL),
        ("EP", TipoEvaluacion.EXAMEN_PARCIAL),
        ("Práctica Calificada 3", TipoEvaluacion.PRACTICA_CALIFICADA),
        ("PC2", TipoEvaluacion.PRACTICA_CALIFICADA),
        ("Primer avance de Laboratorio (Lb1)", TipoEvaluacion.LABORATORIO),
        ("Trabajo Final", TipoEvaluacion.PROYECTO),
        ("Exposición grupal", TipoEvaluacion.EXPOSICION),
        ("Control de lectura 1", TipoEvaluacion.CONTROL_LECTURA),
        ("Ensayo", TipoEvaluacion.TAREA),
        ("Asistencia y participación", None),
    ],
)
def test_tipo_desde_nombre(nombre, tipo):
    assert tipo_desde_nombre(nombre) == tipo
