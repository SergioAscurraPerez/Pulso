"""Modelo CP-SAT de reprogramación (PUL-11).

Cada evaluación tiene una variable entera: el día del ciclo en que se toma
(0 = lunes de la semana 1). Se puede mover como máximo ±k días desde su fecha original.

Restricciones:
- evaluaciones `bloqueada` → se quedan en su fecha;
- solo días hábiles (lunes a viernes por defecto), nunca feriados;
- semana de exámenes: los parciales/finales que caen en una semana de exámenes no salen de ella,
  y las demás evaluaciones no pueden entrar a una semana de exámenes (si ya estaban, pueden quedarse);
- dentro de un curso se respeta el orden original (PC1 antes que PC2…);
- todas las fechas dentro del ciclo.

La función objetivo de este módulo solo minimiza los días movidos. La de carga pico + costo
de movimientos es PUL-12 y se construye sobre `ModeloPulso`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta

from ortools.sat.python import cp_model

from src.models import SEMANAS_CICLO, Cohorte, Evaluacion, TipoEvaluacion

TIPOS_EXAMEN = {TipoEvaluacion.EXAMEN_PARCIAL, TipoEvaluacion.EXAMEN_FINAL}


@dataclass
class ConfigOptimizador:
    ventana_dias: int = 7  # k: cuánto se puede mover una evaluación hacia adelante o atrás
    feriados: set[date] = field(default_factory=set)
    semanas_examenes: set[int] = field(default_factory=lambda: {8, 16})
    dias_habiles: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})  # weekday(): lun=0 … vie=4
    tiempo_max_s: float = 10.0


@dataclass
class ModeloPulso:
    cohorte: Cohorte
    config: ConfigOptimizador
    modelo: cp_model.CpModel
    dia: dict[str, cp_model.IntVar]  # id → día del ciclo
    dia_original: dict[str, int]
    desplazamiento: dict[str, cp_model.IntVar]  # id → |día − día original|

    def fecha(self, offset: int) -> date:
        return self.cohorte.fecha_inicio + timedelta(days=offset)


@dataclass
class Solucion:
    estado: str  # OPTIMAL, FEASIBLE, INFEASIBLE, …
    fechas: dict[str, date]
    tiempo_s: float
    objetivo: float | None = None

    @property
    def factible(self) -> bool:
        return self.estado in ("OPTIMAL", "FEASIBLE")


def _offset(cohorte: Cohorte, ev: Evaluacion) -> int:
    if ev.fecha is None:
        raise ValueError(f"'{ev.id}' no tiene fecha; normalízala antes de optimizar (PUL-06).")
    return (ev.fecha - cohorte.fecha_inicio).days


def dias_candidatos(cohorte: Cohorte, ev: Evaluacion, config: ConfigOptimizador) -> list[int]:
    """Días del ciclo a los que se puede mover la evaluación."""
    orig = _offset(cohorte, ev)
    if ev.bloqueada:
        return [orig]
    ultimo = SEMANAS_CICLO * 7 - 1
    semana_orig = orig // 7 + 1
    es_examen = ev.tipo in TIPOS_EXAMEN
    candidatos = []
    for d in range(max(0, orig - config.ventana_dias), min(ultimo, orig + config.ventana_dias) + 1):
        fecha = cohorte.fecha_inicio + timedelta(days=d)
        semana = d // 7 + 1
        if fecha.weekday() not in config.dias_habiles or fecha in config.feriados:
            continue
        if es_examen and semana_orig in config.semanas_examenes and semana != semana_orig:
            continue
        if not es_examen and semana in config.semanas_examenes and semana != semana_orig:
            continue
        candidatos.append(d)
    return candidatos or [orig]  # sin alternativas válidas: se queda donde está


def construir_modelo(cohorte: Cohorte, config: ConfigOptimizador | None = None) -> ModeloPulso:
    config = config or ConfigOptimizador()
    m = cp_model.CpModel()
    dia: dict[str, cp_model.IntVar] = {}
    dia_original: dict[str, int] = {}
    desplazamiento: dict[str, cp_model.IntVar] = {}

    for ev in cohorte.evaluaciones:
        orig = _offset(cohorte, ev)
        dia_original[ev.id] = orig
        x = m.new_int_var_from_domain(cp_model.Domain.from_values(dias_candidatos(cohorte, ev, config)), f"dia[{ev.id}]")
        dia[ev.id] = x
        mov = m.new_int_var(0, config.ventana_dias, f"mov[{ev.id}]")
        m.add_abs_equality(mov, x - orig)
        desplazamiento[ev.id] = mov

    # Orden dentro de cada curso.
    por_curso: dict[str, list[Evaluacion]] = {}
    for ev in cohorte.evaluaciones:
        por_curso.setdefault(ev.curso, []).append(ev)
    for evs in por_curso.values():
        evs.sort(key=lambda e: dia_original[e.id])
        for a, b in zip(evs, evs[1:]):
            if dia_original[a.id] < dia_original[b.id]:
                m.add(dia[a.id] < dia[b.id])

    return ModeloPulso(cohorte, config, m, dia, dia_original, desplazamiento)


def resolver(mp: ModeloPulso, minimizar_movimientos: bool = True) -> Solucion:
    """Resuelve el modelo. Si nadie fijó un objetivo, minimiza los días movidos."""
    if minimizar_movimientos and not mp.modelo.has_objective():
        mp.modelo.minimize(sum(mp.desplazamiento.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = mp.config.tiempo_max_s
    solver.parameters.num_workers = 8
    inicio = time.perf_counter()
    status = solver.solve(mp.modelo)
    tiempo = time.perf_counter() - inicio
    estado = solver.status_name(status)
    fechas: dict[str, date] = {}
    objetivo = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fechas = {i: mp.fecha(solver.value(x)) for i, x in mp.dia.items()}
        objetivo = solver.objective_value if mp.modelo.has_objective() else None
    return Solucion(estado=estado, fechas=fechas, tiempo_s=round(tiempo, 3), objetivo=objetivo)
