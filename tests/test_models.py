"""Validación del esquema de datos (PUL-21)."""

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models import Cohorte, Evaluacion, TipoEvaluacion, cargar_cohorte

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


def _ev(**kwargs) -> Evaluacion:
    datos = {"curso": "Física I", "nombre": "Práctica calificada 1", "tipo": "practica_calificada", "peso": 10, "semana": 4}
    return Evaluacion(**{**datos, **kwargs})


def test_mock_valida():
    cohorte = cargar_cohorte(MOCK)
    assert len(cohorte.evaluaciones) == 30
    assert len(cohorte.cursos) == 6
    assert cohorte.total_estudiantes == 120
    assert all(e.fecha is not None for e in cohorte.evaluaciones)


def test_id_se_genera_sin_tildes():
    assert _ev().id == "fisica-i--practica-calificada-1"
    assert _ev(id="propio").id == "propio"


def test_tipo_como_texto_o_enum():
    assert _ev(tipo="examen_final").tipo is TipoEvaluacion.EXAMEN_FINAL
    with pytest.raises(ValidationError):
        _ev(tipo="examen_sorpresa")


@pytest.mark.parametrize("peso", [0, -5, 100.5])
def test_peso_fuera_de_rango(peso):
    with pytest.raises(ValidationError):
        _ev(peso=peso)


@pytest.mark.parametrize("semana", [0, 18])
def test_semana_fuera_de_rango(semana):
    with pytest.raises(ValidationError):
        _ev(semana=semana)


def test_exige_fecha_o_semana():
    with pytest.raises(ValidationError):
        _ev(semana=None)
    assert _ev(semana=None, fecha=date(2026, 9, 1)).fecha == date(2026, 9, 1)


def test_fecha_iso_desde_json():
    ev = Evaluacion.model_validate_json(
        '{"curso": "X", "nombre": "EP", "tipo": "examen_parcial", "peso": 25, "fecha": "2026-10-12"}'
    )
    assert ev.fecha == date(2026, 10, 12)


def test_cohorte_rechaza_ids_repetidos():
    with pytest.raises(ValidationError, match="repetidos"):
        Cohorte(nombre="t", ciclo="2026-II", fecha_inicio=date(2026, 8, 24), evaluaciones=[_ev(), _ev()])


def test_cohorte_rechaza_grupos_con_cursos_desconocidos():
    with pytest.raises(ValidationError, match="sin evaluaciones"):
        Cohorte(
            nombre="t",
            ciclo="2026-II",
            fecha_inicio=date(2026, 8, 24),
            evaluaciones=[_ev()],
            grupos=[{"cursos": ["Química"], "cantidad": 10}],
        )


def test_cohorte_sin_grupos_es_valida():
    c = Cohorte(nombre="t", ciclo="2026-II", fecha_inicio=date(2026, 8, 24), evaluaciones=[_ev()])
    assert c.grupos == [] and c.total_estudiantes is None


def test_ida_y_vuelta_json():
    cohorte = cargar_cohorte(MOCK)
    copia = Cohorte.model_validate(json.loads(cohorte.model_dump_json()))
    assert copia == cohorte
