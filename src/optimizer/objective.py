"""Función objetivo del optimizador (PUL-12).

Minimiza, en este orden de importancia:
1. la **carga pico semanal** (el máximo del índice de PUL-09 entre todas las semanas);
2. las **colisiones**: por cada ventana de 72 h, cada evaluación fuerte por encima de 2;
   y, aparte, cada evaluación fuerte de más en un mismo día;
3. el **costo de movimientos**: días movidos en total, para no tocar más de lo necesario.

Se construye sobre el modelo de PUL-11 (`construir_modelo`) y devuelve el diff
(qué se movió y cuántos días) y las métricas antes/después calculadas con el motor de carga,
no con los valores internos del solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ortools.sat.python import cp_model

from src.engine.collisions import MIN_EVALUACIONES, VENTANA_DIAS, detectar_colisiones, es_fuerte
from src.engine.load_index import carga_evaluacion, carga_semanal_cohorte, semana_pico
from src.models import SEMANAS_CICLO, Cohorte
from src.optimizer.cpsat_model import ConfigOptimizador, construir_modelo, resolver

ESCALA = 100  # CP-SAT trabaja con enteros: carga × 100


@dataclass
class PesosObjetivo:
    pico: int = 1  # por cada 0.01 de carga en la semana pico
    colision: int = 3000  # por cada evaluación fuerte de más en una ventana de 72 h (= 30 puntos de carga)
    mismo_dia: int = 1500  # por cada evaluación fuerte de más en un mismo día (= 15 puntos de carga)
    movimiento: int = 20  # por cada día movido (= 0.2 puntos de carga)


@dataclass
class Movimiento:
    id: str
    curso: str
    nombre: str
    fecha_original: date
    fecha_nueva: date

    @property
    def dias(self) -> int:
        return (self.fecha_nueva - self.fecha_original).days

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "curso": self.curso,
            "nombre": self.nombre,
            "fecha_original": self.fecha_original.isoformat(),
            "fecha_nueva": self.fecha_nueva.isoformat(),
            "dias": self.dias,
        }


@dataclass
class ResultadoOptimizacion:
    estado: str
    tiempo_s: float
    fechas: dict[str, date]
    movimientos: list[Movimiento]
    carga_antes: dict[int, float]
    carga_despues: dict[int, float]
    colisiones_antes: int
    colisiones_despues: int
    metadatos: dict = field(default_factory=dict)

    @property
    def factible(self) -> bool:
        return self.estado in ("OPTIMAL", "FEASIBLE")

    @property
    def pico_antes(self) -> tuple[int, float]:
        return semana_pico(self.carga_antes)

    @property
    def pico_despues(self) -> tuple[int, float]:
        return semana_pico(self.carga_despues)

    @property
    def reduccion_pico_pct(self) -> float:
        antes, despues = self.pico_antes[1], self.pico_despues[1]
        return round(100 * (antes - despues) / antes, 1) if antes else 0.0

    def to_dict(self) -> dict:
        return {
            "estado": self.estado,
            "tiempo_s": self.tiempo_s,
            "pico_antes": {"semana": self.pico_antes[0], "carga": self.pico_antes[1]},
            "pico_despues": {"semana": self.pico_despues[0], "carga": self.pico_despues[1]},
            "reduccion_pico_pct": self.reduccion_pico_pct,
            "evaluaciones_movidas": len(self.movimientos),
            "colisiones_antes": self.colisiones_antes,
            "colisiones_despues": self.colisiones_despues,
            "movimientos": [m.to_dict() for m in self.movimientos],
            "carga_antes": self.carga_antes,
            "carga_despues": self.carga_despues,
            "fechas": {i: f.isoformat() for i, f in self.fechas.items()},
        }


def optimizar(
    cohorte: Cohorte,
    config: ConfigOptimizador | None = None,
    pesos: PesosObjetivo | None = None,
) -> ResultadoOptimizacion:
    config = config or ConfigOptimizador()
    pesos = pesos or PesosObjetivo()
    mp = construir_modelo(cohorte, config)
    m = mp.modelo

    # Un booleano por (evaluación, día candidato): la carga semanal y las ventanas de 72 h
    # quedan como sumas lineales de estos booleanos.
    en_dia: dict[str, dict[int, cp_model.IntVar]] = {}
    for ev in cohorte.evaluaciones:
        x = mp.dia[ev.id]
        dias = list(x.proto.domain)
        candidatos = [d for lo, hi in zip(dias[::2], dias[1::2]) for d in range(lo, hi + 1)]
        bools = {d: m.new_bool_var(f"en[{ev.id},{d}]") for d in candidatos}
        m.add_exactly_one(bools.values())
        m.add(x == sum(d * b for d, b in bools.items()))
        en_dia[ev.id] = bools

    # 1) Carga pico semanal.
    carga_max = sum(round(carga_evaluacion(e) * ESCALA) for e in cohorte.evaluaciones)
    pico = m.new_int_var(0, carga_max, "pico")
    for semana in range(1, SEMANAS_CICLO + 1):
        dias_semana = range((semana - 1) * 7, semana * 7)
        terminos = [
            round(carga_evaluacion(ev) * ESCALA) * b
            for ev in cohorte.evaluaciones
            for d, b in en_dia[ev.id].items()
            if d in dias_semana
        ]
        if terminos:
            m.add(pico >= sum(terminos))

    # 2) Exceso de evaluaciones fuertes por ventana de 72 h.
    fuertes = [ev for ev in cohorte.evaluaciones if es_fuerte(ev)]
    excesos = []
    ultimo_dia = SEMANAS_CICLO * 7 - 1
    for inicio in range(0, ultimo_dia + 1):
        ventana = range(inicio, inicio + VENTANA_DIAS)
        terminos = [b for ev in fuertes for d, b in en_dia[ev.id].items() if d in ventana]
        if len(terminos) >= MIN_EVALUACIONES:
            exceso = m.new_int_var(0, len(terminos), f"exceso[{inicio}]")
            m.add(exceso >= sum(terminos) - (MIN_EVALUACIONES - 1))
            excesos.append(exceso)

    # 2b) Más de una evaluación fuerte el mismo día.
    excesos_dia = []
    for dia in range(0, ultimo_dia + 1):
        terminos = [en_dia[ev.id][dia] for ev in fuertes if dia in en_dia[ev.id]]
        if len(terminos) >= 2:
            exceso = m.new_int_var(0, len(terminos), f"mismo_dia[{dia}]")
            m.add(exceso >= sum(terminos) - 1)
            excesos_dia.append(exceso)

    # 3) Objetivo ponderado.
    principal = (
        pesos.pico * pico
        + pesos.colision * sum(excesos)
        + pesos.mismo_dia * sum(excesos_dia)
        + pesos.movimiento * sum(mp.desplazamiento.values())
    )

    # 4) Desempate lexicográfico: solo decide entre soluciones con el mismo costo principal, que existen
    #    (p. ej. mover 4 o 6 evaluaciones sumando los mismos días). Sin él, cada máquina elegía una
    #    distinta (local vs. Vercel). Primero, menos evaluaciones movidas (menos docentes a coordinar);
    #    luego, un orden fijo por id. Los pesos escalonados garantizan que un nivel nunca compense al anterior.
    movidas = []
    for ev in cohorte.evaluaciones:
        movida = m.new_bool_var(f"movida[{ev.id}]")
        m.add(mp.desplazamiento[ev.id] >= 1).only_enforce_if(movida)
        m.add(mp.desplazamiento[ev.id] == 0).only_enforce_if(movida.Not())
        movidas.append(movida)
    rango = {ev_id: i + 1 for i, ev_id in enumerate(sorted(mp.dia))}
    orden = sum(rango[ev_id] * mp.dia[ev_id] for ev_id in mp.dia)
    max_orden = sum(rango.values()) * ultimo_dia
    desempate = (max_orden + 1) * sum(movidas) + orden
    max_desempate = (max_orden + 1) * len(movidas) + max_orden
    m.minimize((max_desempate + 1) * principal + desempate)
    sol = resolver(mp, minimizar_movimientos=False)

    originales = {e.id: e.fecha for e in cohorte.evaluaciones}
    fechas = sol.fechas or dict(originales)
    movimientos = [
        Movimiento(e.id, e.curso, e.nombre, e.fecha, fechas[e.id])
        for e in sorted(cohorte.evaluaciones, key=lambda e: e.fecha)
        if fechas[e.id] != e.fecha
    ]
    return ResultadoOptimizacion(
        estado=sol.estado,
        tiempo_s=sol.tiempo_s,
        fechas=fechas,
        movimientos=movimientos,
        carga_antes=carga_semanal_cohorte(cohorte),
        carga_despues=carga_semanal_cohorte(cohorte, fechas),
        colisiones_antes=len(detectar_colisiones(cohorte.evaluaciones)),
        colisiones_despues=len(detectar_colisiones(cohorte.evaluaciones, fechas)),
        metadatos={"objetivo": sol.objetivo},
    )
