"""Índice de carga semanal de una cohorte (PUL-09).

carga(semana) = Σ peso × factor_tipo de las evaluaciones de esa semana.
`peso` es el % de la nota final del curso, así que una semana con un parcial de 30 %
suma 30 × 1.3 = 39 puntos de carga.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from src.models import SEMANAS_CICLO, Cohorte, Evaluacion, TipoEvaluacion

# Cuánto "pesa" cada tipo para el estudiante, más allá de su % en la nota:
# preparar un examen exige más horas que una tarea del mismo peso.
FACTOR_TIPO: dict[TipoEvaluacion, float] = {
    TipoEvaluacion.EXAMEN_FINAL: 1.5,
    TipoEvaluacion.EXAMEN_PARCIAL: 1.3,
    TipoEvaluacion.PROYECTO: 1.2,
    TipoEvaluacion.PRACTICA_CALIFICADA: 1.0,
    TipoEvaluacion.EXPOSICION: 0.9,
    TipoEvaluacion.LABORATORIO: 0.7,
    TipoEvaluacion.TAREA: 0.6,
    TipoEvaluacion.CONTROL_LECTURA: 0.5,
    TipoEvaluacion.OTRO: 0.6,
}


def carga_evaluacion(evaluacion: Evaluacion) -> float:
    """Carga que aporta una evaluación: peso × factor de su tipo."""
    return evaluacion.peso * FACTOR_TIPO[evaluacion.tipo]


def semana_de(evaluacion: Evaluacion, fecha_inicio: date, fecha: date | None = None) -> int:
    """Semana del ciclo (1..SEMANAS_CICLO) de una evaluación.

    Usa `fecha` si se pasa (p. ej. la fecha propuesta por el optimizador); si no, la fecha
    de la evaluación; y si tampoco hay, su campo `semana`.
    """
    fecha = fecha or evaluacion.fecha
    if fecha is None:
        assert evaluacion.semana is not None  # garantizado por el modelo
        return evaluacion.semana
    semana = (fecha - fecha_inicio).days // 7 + 1
    return min(max(semana, 1), SEMANAS_CICLO)


# Semanas de exámenes del ciclo. Las semanas consecutivas forman un mismo periodo:
# {8} = parciales, {16, 17} = finales.
SEMANAS_EXAMENES: frozenset[int] = frozenset({8, 16, 17})
TIPOS_EXAMEN = frozenset({TipoEvaluacion.EXAMEN_PARCIAL, TipoEvaluacion.EXAMEN_FINAL})


def periodo_examenes(semana: int, semanas_examenes: Iterable[int] = SEMANAS_EXAMENES) -> frozenset[int]:
    """Semanas consecutivas de exámenes que contienen a `semana` (vacío si no es semana de exámenes)."""
    semanas = set(semanas_examenes)
    if semana not in semanas:
        return frozenset()
    inicio = fin = semana
    while inicio - 1 in semanas:
        inicio -= 1
    while fin + 1 in semanas:
        fin += 1
    return frozenset(range(inicio, fin + 1))


def semana_permitida(
    evaluacion: Evaluacion,
    semana_original: int,
    semana_nueva: int,
    semanas_examenes: Iterable[int] = SEMANAS_EXAMENES,
) -> bool:
    """Regla de semanas de exámenes (la usan el optimizador CP-SAT y el simulador docente).

    - Un parcial/final que está en un periodo de exámenes solo se mueve dentro de ese periodo.
    - Cualquier otra evaluación no entra a un periodo de exámenes distinto del suyo.
    """
    periodo_original = periodo_examenes(semana_original, semanas_examenes)
    periodo_nuevo = periodo_examenes(semana_nueva, semanas_examenes)
    if evaluacion.tipo in TIPOS_EXAMEN and periodo_original:
        return semana_nueva in periodo_original
    return not periodo_nuevo or periodo_nuevo == periodo_original


def evaluaciones_por_semana(
    evaluaciones: Iterable[Evaluacion],
    fecha_inicio: date,
    fechas: dict[str, date] | None = None,
) -> dict[int, list[Evaluacion]]:
    """Agrupa las evaluaciones por semana del ciclo (todas las semanas, aunque estén vacías).

    `fechas` permite sobrescribir la fecha de algunas evaluaciones por id (escenario "después").
    """
    fechas = fechas or {}
    semanas: dict[int, list[Evaluacion]] = {s: [] for s in range(1, SEMANAS_CICLO + 1)}
    for ev in evaluaciones:
        semanas[semana_de(ev, fecha_inicio, fechas.get(ev.id))].append(ev)
    return semanas


def carga_semanal(
    evaluaciones: Iterable[Evaluacion],
    fecha_inicio: date,
    fechas: dict[str, date] | None = None,
) -> dict[int, float]:
    """Índice de carga por semana del ciclo: {semana: Σ peso × factor_tipo}."""
    return {
        semana: round(sum(carga_evaluacion(ev) for ev in evs), 2)
        for semana, evs in evaluaciones_por_semana(evaluaciones, fecha_inicio, fechas).items()
    }


def carga_semanal_cohorte(cohorte: Cohorte, fechas: dict[str, date] | None = None) -> dict[int, float]:
    """Atajo de `carga_semanal` para una `Cohorte`."""
    return carga_semanal(cohorte.evaluaciones, cohorte.fecha_inicio, fechas)


def semana_pico(carga: dict[int, float]) -> tuple[int, float]:
    """Semana con mayor carga y su valor."""
    semana = max(carga, key=lambda s: carga[s])
    return semana, carga[semana]
