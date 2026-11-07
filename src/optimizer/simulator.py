"""Simulador docente (PUL-13).

Antes de fijar una fecha, el docente pregunta: "si tomo esta evaluación este día,
¿cuántos de mis alumnos quedan con una colisión?, ¿qué día conviene más?".

- El % se calcula sobre los alumnos del curso de la evaluación, usando `Cohorte.grupos`
  (combinaciones de cursos matriculados). Sin grupos, se asume que todos llevan todos los cursos.
- Un alumno "tiene colisión" si la evaluación simulada queda dentro de una colisión
  (≥3 evaluaciones fuertes en 72 h) considerando solo los cursos que él lleva.
- Reutiliza el motor de carga: `detectar_colisiones` y `carga_semanal`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from src.engine.collisions import Colision, detectar_colisiones
from src.engine.load_index import carga_semanal, semana_de
from src.models import SEMANAS_CICLO, Cohorte, Evaluacion, GrupoMatricula, TipoEvaluacion

TIPOS_EXAMEN = {TipoEvaluacion.EXAMEN_PARCIAL, TipoEvaluacion.EXAMEN_FINAL}
SEMANAS_EXAMENES = {8, 16}


@dataclass
class EscenarioFecha:
    fecha: date
    pct_colision: float  # 0–100, sobre los alumnos del curso
    alumnos_con_colision: int
    alumnos_del_curso: int
    carga_semana: float
    colisiones: list[Colision] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "fecha": self.fecha.isoformat(),
            "pct_colision": self.pct_colision,
            "alumnos_con_colision": self.alumnos_con_colision,
            "alumnos_del_curso": self.alumnos_del_curso,
            "carga_semana": self.carga_semana,
            "colisiones": [c.to_dict() for c in self.colisiones],
        }


@dataclass
class ResultadoSimulacion:
    evaluacion: Evaluacion
    propuesta: EscenarioFecha
    mejor_alternativa: EscenarioFecha | None
    alternativas: list[EscenarioFecha]  # ordenadas de mejor a peor

    def to_dict(self) -> dict:
        return {
            "evaluacion": self.evaluacion.model_dump(mode="json"),
            "propuesta": self.propuesta.to_dict(),
            "mejor_alternativa": self.mejor_alternativa.to_dict() if self.mejor_alternativa else None,
            "alternativas": [a.to_dict() for a in self.alternativas],
        }


def _grupos(cohorte: Cohorte, curso: str) -> list[GrupoMatricula]:
    """Grupos de matrícula. Si ningún grupo lleva `curso` (curso nuevo), se asume que todos lo llevan."""
    grupos = cohorte.grupos or [GrupoMatricula(cursos=cohorte.cursos, cantidad=1)]
    if not any(curso in g.cursos for g in grupos):
        grupos = [GrupoMatricula(cursos=[*g.cursos, curso], cantidad=g.cantidad) for g in grupos]
    return grupos


def _con_evaluacion(cohorte: Cohorte, evaluacion: Evaluacion) -> list[Evaluacion]:
    """Evaluaciones de la cohorte con `evaluacion` agregada o reemplazando a la del mismo id."""
    return [e for e in cohorte.evaluaciones if e.id != evaluacion.id] + [evaluacion]


def evaluar_fecha(cohorte: Cohorte, evaluacion: Evaluacion, fecha: date) -> EscenarioFecha:
    """Riesgo de colisión si `evaluacion` se toma el día `fecha`."""
    todas = _con_evaluacion(cohorte, evaluacion)
    fechas = {evaluacion.id: fecha}
    afectados = del_curso = 0
    colisiones: dict[tuple[date, date], Colision] = {}
    for grupo in _grupos(cohorte, evaluacion.curso):
        if evaluacion.curso not in grupo.cursos:
            continue
        del_curso += grupo.cantidad
        suyas = [e for e in todas if e.curso in grupo.cursos]
        propias = [c for c in detectar_colisiones(suyas, fechas) if any(e.id == evaluacion.id for e in c.evaluaciones)]
        if propias:
            afectados += grupo.cantidad
            for c in propias:
                colisiones.setdefault((c.inicio, c.fin), c)
    semana = semana_de(evaluacion, cohorte.fecha_inicio, fecha)
    carga = carga_semanal(todas, cohorte.fecha_inicio, fechas)[semana]
    return EscenarioFecha(
        fecha=fecha,
        pct_colision=round(100 * afectados / del_curso, 1),
        alumnos_con_colision=afectados,
        alumnos_del_curso=del_curso,
        carga_semana=carga,
        colisiones=sorted(colisiones.values(), key=lambda c: c.inicio),
    )


def fechas_alternativas(
    cohorte: Cohorte,
    evaluacion: Evaluacion,
    fecha: date,
    ventana_dias: int = 7,
    feriados: set[date] | None = None,
    semanas_examenes: set[int] | None = None,
) -> list[date]:
    """Días a los que se podría mover la evaluación. Usa las mismas reglas que el modelo CP-SAT:
    - días hábiles (lun–vie), sin feriados, dentro de ±`ventana_dias` y dentro del ciclo;
    - un parcial/final que cae en una semana de exámenes no sale de ella;
    - otro tipo de evaluación no entra a una semana de exámenes.
    """
    feriados = feriados or set()
    semanas_examenes = SEMANAS_EXAMENES if semanas_examenes is None else semanas_examenes
    fin_ciclo = cohorte.fecha_inicio + timedelta(days=SEMANAS_CICLO * 7 - 1)
    semana_actual = semana_de(evaluacion, cohorte.fecha_inicio, fecha)
    es_examen = evaluacion.tipo in TIPOS_EXAMEN
    alternativas = []
    for d in range(-ventana_dias, ventana_dias + 1):
        f = fecha + timedelta(days=d)
        if f == fecha or not cohorte.fecha_inicio <= f <= fin_ciclo or f.weekday() >= 5 or f in feriados:
            continue
        semana = semana_de(evaluacion, cohorte.fecha_inicio, f)
        if es_examen and semana_actual in semanas_examenes and semana != semana_actual:
            continue
        if not es_examen and semana in semanas_examenes and semana != semana_actual:
            continue
        alternativas.append(f)
    return alternativas


def simular(
    cohorte: Cohorte,
    evaluacion: Evaluacion,
    fecha: date,
    *,
    ventana_dias: int = 7,
    feriados: set[date] | None = None,
    semanas_examenes: set[int] | None = None,
) -> ResultadoSimulacion:
    """Evalúa `fecha` y busca la mejor alternativa cercana.

    `evaluacion` puede ser una de la cohorte (se mueve) o una nueva que el docente está planificando.
    Mejor alternativa = menor % de colisión; a igualdad, menor carga semanal y luego más cercana.
    """
    propuesta = evaluar_fecha(cohorte, evaluacion, fecha)
    alternativas = sorted(
        (evaluar_fecha(cohorte, evaluacion, f) for f in fechas_alternativas(cohorte, evaluacion, fecha, ventana_dias, feriados, semanas_examenes)),
        key=lambda a: (a.pct_colision, a.carga_semana, abs((a.fecha - fecha).days)),
    )
    mejor = alternativas[0] if alternativas else None
    if mejor and (mejor.pct_colision, mejor.carga_semana) >= (propuesta.pct_colision, propuesta.carga_semana):
        mejor = None  # la fecha propuesta ya es la mejor de su ventana
    return ResultadoSimulacion(evaluacion, propuesta, mejor, alternativas)
