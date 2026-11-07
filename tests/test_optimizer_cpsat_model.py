from datetime import date
from pathlib import Path

from src.optimizer.cpsat_model import ConfigOptimizador, construir_modelo, dias_candidatos, resolver
from src.models import Cohorte, Evaluacion, cargar_cohorte

MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "evaluaciones_mock.json"


def _cohorte(*evs: Evaluacion) -> Cohorte:
    return Cohorte(nombre="t", ciclo="2026-II", fecha_inicio=date(2026, 8, 24), evaluaciones=list(evs))


def _ev(nombre: str, tipo: str, fecha: date, curso: str = "A", bloqueada: bool = False) -> Evaluacion:
    return Evaluacion(curso=curso, nombre=nombre, tipo=tipo, peso=10, fecha=fecha, bloqueada=bloqueada)


def test_mock_es_factible_en_menos_de_10_s():
    cohorte = cargar_cohorte(MOCK)
    sol = resolver(construir_modelo(cohorte))
    assert sol.factible
    assert sol.tiempo_s < 10
    assert set(sol.fechas) == {e.id for e in cohorte.evaluaciones}


def test_solucion_respeta_restricciones_en_el_mock():
    cohorte = cargar_cohorte(MOCK)
    cfg = ConfigOptimizador(feriados={date(2026, 10, 8)})  # Combate de Angamos
    # Forzar movimientos: prohibir la fecha original de todas las no bloqueadas.
    mp = construir_modelo(cohorte, cfg)
    for ev in cohorte.evaluaciones:
        if not ev.bloqueada:
            mp.modelo.add(mp.dia[ev.id] != mp.dia_original[ev.id])
    sol = resolver(mp)
    assert sol.factible
    for ev in cohorte.evaluaciones:
        nueva = sol.fechas[ev.id]
        if ev.bloqueada:
            assert nueva == ev.fecha
        assert abs((nueva - ev.fecha).days) <= cfg.ventana_dias
        assert nueva.weekday() < 5
        assert nueva not in cfg.feriados
    por_curso: dict[str, list[Evaluacion]] = {}
    for ev in cohorte.evaluaciones:
        por_curso.setdefault(ev.curso, []).append(ev)
    for evs in por_curso.values():
        evs.sort(key=lambda e: e.fecha)
        nuevas = [sol.fechas[e.id] for e in evs]
        assert nuevas == sorted(nuevas)


def test_bloqueada_solo_tiene_su_fecha():
    c = _cohorte(_ev("EF", "examen_final", date(2026, 12, 7), bloqueada=True))
    assert dias_candidatos(c, c.evaluaciones[0], ConfigOptimizador()) == [105]


def test_parcial_no_sale_de_la_semana_de_examenes():
    c = _cohorte(_ev("EP", "examen_parcial", date(2026, 10, 14)))  # miércoles semana 8
    dias = dias_candidatos(c, c.evaluaciones[0], ConfigOptimizador())
    assert dias and all(d // 7 + 1 == 8 for d in dias)


def test_practica_no_entra_a_semana_de_examenes():
    c = _cohorte(_ev("PC", "practica_calificada", date(2026, 10, 9)))  # viernes semana 7
    dias = dias_candidatos(c, c.evaluaciones[0], ConfigOptimizador())
    assert dias and all(d // 7 + 1 != 8 for d in dias)


def test_feriados_y_fines_de_semana_excluidos():
    c = _cohorte(_ev("PC", "practica_calificada", date(2026, 9, 2)))
    cfg = ConfigOptimizador(feriados={date(2026, 9, 1)})
    fechas = {c.fecha_inicio.toordinal() + d for d in dias_candidatos(c, c.evaluaciones[0], cfg)}
    assert date(2026, 9, 1).toordinal() not in fechas
    assert all(date.fromordinal(f).weekday() < 5 for f in fechas)


def test_sin_restricciones_extra_no_mueve_nada():
    cohorte = cargar_cohorte(MOCK)
    sol = resolver(construir_modelo(cohorte))
    assert sol.objetivo == 0
    assert all(sol.fechas[e.id] == e.fecha for e in cohorte.evaluaciones)
