from datetime import date
from pathlib import Path

from src.engine.collisions import detectar_colisiones, es_fuerte
from src.models import Evaluacion, cargar_cohorte

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


def _ev(curso: str, tipo: str, peso: float, fecha: date) -> Evaluacion:
    return Evaluacion(curso=curso, nombre=f"{tipo} {curso}", tipo=tipo, peso=peso, fecha=fecha)


def test_es_fuerte_usa_umbral_de_carga():
    assert es_fuerte(_ev("A", "practica_calificada", 10, date(2026, 9, 1)))
    assert not es_fuerte(_ev("A", "laboratorio", 5, date(2026, 9, 1)))


def test_tres_fuertes_en_72h_es_colision():
    evs = [
        _ev("A", "examen_parcial", 25, date(2026, 10, 12)),
        _ev("B", "examen_parcial", 25, date(2026, 10, 13)),
        _ev("C", "examen_parcial", 25, date(2026, 10, 14)),
    ]
    [col] = detectar_colisiones(evs)
    assert (col.inicio, col.fin) == (date(2026, 10, 12), date(2026, 10, 14))
    assert col.cursos == ["A", "B", "C"]
    assert col.max_en_72h == 3


def test_fuera_de_72h_no_es_colision():
    evs = [
        _ev("A", "examen_parcial", 25, date(2026, 10, 12)),
        _ev("B", "examen_parcial", 25, date(2026, 10, 13)),
        _ev("C", "examen_parcial", 25, date(2026, 10, 15)),  # 4.º día: fuera de la ventana
    ]
    assert detectar_colisiones(evs) == []


def test_evaluaciones_livianas_no_cuentan():
    evs = [
        _ev("A", "examen_parcial", 25, date(2026, 10, 12)),
        _ev("B", "examen_parcial", 25, date(2026, 10, 13)),
        _ev("C", "laboratorio", 5, date(2026, 10, 13)),
    ]
    assert detectar_colisiones(evs) == []


def test_ventanas_solapadas_se_fusionan():
    evs = [_ev(c, "examen_final", 30, date(2026, 12, 7 + i)) for i, c in enumerate("ABCDE")]  # lun–vie
    [col] = detectar_colisiones(evs)
    assert (col.inicio, col.fin) == (date(2026, 12, 7), date(2026, 12, 11))
    assert len(col.evaluaciones) == 5
    assert col.max_en_72h == 3


def test_mock_detecta_parciales_y_finales():
    cohorte = cargar_cohorte(MOCK)
    colisiones = detectar_colisiones(cohorte.evaluaciones)
    inicios = [c.inicio for c in colisiones]
    assert date(2026, 10, 12) in inicios  # semana 8: parciales lun–jue
    assert date(2026, 12, 7) in inicios  # semana 16: finales
    parciales = next(c for c in colisiones if c.inicio == date(2026, 10, 12))
    assert parciales.max_en_72h >= 3
    assert {"Base de Datos II", "Ingeniería de Software II", "Sistemas Operativos"} <= set(parciales.cursos)
    assert parciales.to_dict()["evaluaciones"][0]["fecha"] == "2026-10-12"


def test_mover_fechas_elimina_la_colision():
    cohorte = cargar_cohorte(MOCK)
    # Escenario propuesto: dos de los parciales de la semana 8 se adelantan a la semana 7.
    fechas = {
        "sistemas-operativos--examen-parcial": date(2026, 10, 5),
        "investigacion-operativa--examen-parcial": date(2026, 10, 8),
    }
    semana8 = lambda c: date(2026, 10, 12) <= c.inicio <= date(2026, 10, 16)  # noqa: E731
    assert any(semana8(c) for c in detectar_colisiones(cohorte.evaluaciones))
    assert not any(semana8(c) for c in detectar_colisiones(cohorte.evaluaciones, fechas))
