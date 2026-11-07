"""Normalización de evaluaciones extraídas (PUL-06).

- Fechas: "Semana 8" → fecha real según el calendario del ciclo (lunes de la semana 1 = `fecha_inicio`).
  El sílabo casi nunca dice el día, así que cada curso tiene un **día de clase**: el que se pase en
  `dias_clase`, o uno asignado de forma determinística y repartida de lunes a viernes. Así todas las
  evaluaciones de un curso caen el mismo día de la semana (como en un horario real) y no se inventan
  colisiones por mandar todo al lunes.
- Feriados: si el día cae en feriado, se usa el siguiente día hábil de la misma semana (o el anterior).
- Consistencia: si hay fecha, la semana se recalcula a partir de ella.
- Tipo: si el LLM devolvió `otro`, se intenta deducir del nombre ("Examen parcial", "PC2", "Lab 1"…).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.models import SEMANAS_CICLO, Evaluacion, TipoEvaluacion

LUNES_A_VIERNES = (0, 1, 2, 3, 4)
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Feriados nacionales de Perú 2026 (Semana Santa 2026: 2 y 3 de abril).
FERIADOS_PERU_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 4, 2),
        date(2026, 4, 3),
        date(2026, 5, 1),
        date(2026, 6, 7),
        date(2026, 6, 29),
        date(2026, 7, 23),
        date(2026, 7, 28),
        date(2026, 7, 29),
        date(2026, 8, 6),
        date(2026, 8, 30),
        date(2026, 10, 8),
        date(2026, 11, 1),
        date(2026, 12, 8),
        date(2026, 12, 9),
        date(2026, 12, 25),
    }
)

# Palabras del nombre → tipo (se evalúan en orden; gana la primera que coincide).
_REGLAS_TIPO: list[tuple[re.Pattern, TipoEvaluacion]] = [
    (re.compile(r"\b(examen|ex)\s*(final|ef)\b|\bef\b"), TipoEvaluacion.EXAMEN_FINAL),
    (re.compile(r"\b(examen|ex)\s*(parcial|ep)\b|\bep\b|parcial"), TipoEvaluacion.EXAMEN_PARCIAL),
    (re.compile(r"practica\s*calificada|\bpc\s*\d"), TipoEvaluacion.PRACTICA_CALIFICADA),
    (re.compile(r"\blab(oratorio)?\b|\blb\s*\d"), TipoEvaluacion.LABORATORIO),
    (re.compile(r"proyecto|avance|trabajo\s*final|\bw\d\b"), TipoEvaluacion.PROYECTO),
    (re.compile(r"exposici|presentaci"), TipoEvaluacion.EXPOSICION),
    (re.compile(r"control\s*de\s*lectura"), TipoEvaluacion.CONTROL_LECTURA),
    (re.compile(r"tarea|ensayo|informe|trabajo"), TipoEvaluacion.TAREA),
]


@dataclass
class ResultadoNormalizacion:
    evaluaciones: list[Evaluacion]
    dias_clase: dict[str, int]
    advertencias: list[str] = field(default_factory=list)


def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def tipo_desde_nombre(nombre: str) -> TipoEvaluacion | None:
    texto = _sin_tildes(nombre)
    for patron, tipo in _REGLAS_TIPO:
        if patron.search(texto):
            return tipo
    return None


def asignar_dias_clase(cursos: list[str], fijos: dict[str, int] | None = None) -> dict[str, int]:
    """Día de clase (0=lun … 4=vie) por curso. Los que no vienen en `fijos` se reparten en orden
    alfabético de lunes a viernes, así el resultado no depende del orden de los PDFs."""
    fijos = dict(fijos or {})
    libres = [c for c in sorted(set(cursos)) if c not in fijos]
    for i, curso in enumerate(libres):
        fijos[curso] = LUNES_A_VIERNES[i % len(LUNES_A_VIERNES)]
    return fijos


def fecha_de_semana(fecha_inicio: date, semana: int, dia: int, feriados: frozenset[date] | set[date]) -> date:
    """Fecha del `dia` (0=lun) de la `semana`; si es feriado, el siguiente hábil de esa semana o el anterior."""
    lunes = fecha_inicio + timedelta(weeks=semana - 1)
    candidatos = [dia, *range(dia + 1, 5), *range(dia - 1, -1, -1)]
    for d in candidatos:
        fecha = lunes + timedelta(days=d)
        if fecha not in feriados:
            return fecha
    return lunes + timedelta(days=dia)  # semana entera feriada: improbable, se deja el día original


def normalizar(
    evaluaciones: list[Evaluacion],
    fecha_inicio: date,
    *,
    dias_clase: dict[str, int] | None = None,
    feriados: frozenset[date] | set[date] = FERIADOS_PERU_2026,
) -> ResultadoNormalizacion:
    """Devuelve copias de las evaluaciones con `fecha` y `semana` completas y `tipo` corregido."""
    if fecha_inicio.weekday() != 0:
        raise ValueError(f"fecha_inicio debe ser lunes (es {DIAS[fecha_inicio.weekday()]} {fecha_inicio}).")
    dias = asignar_dias_clase([e.curso for e in evaluaciones], dias_clase)
    fin_ciclo = fecha_inicio + timedelta(weeks=SEMANAS_CICLO) - timedelta(days=1)
    resultado, advertencias = [], []

    for ev in evaluaciones:
        cambios: dict = {}
        if ev.fecha is not None:
            semana = (ev.fecha - fecha_inicio).days // 7 + 1
            if not 1 <= semana <= SEMANAS_CICLO:
                advertencias.append(f"{ev.id}: la fecha {ev.fecha} está fuera del ciclo ({fecha_inicio} – {fin_ciclo}).")
                semana = min(max(semana, 1), SEMANAS_CICLO)
            if ev.semana is not None and ev.semana != semana:
                advertencias.append(f"{ev.id}: semana {ev.semana} no coincide con la fecha {ev.fecha}; se usa la semana {semana}.")
            cambios["semana"] = semana
        else:
            cambios["fecha"] = fecha_de_semana(fecha_inicio, ev.semana, dias[ev.curso], feriados)

        if ev.tipo is TipoEvaluacion.OTRO:
            deducido = tipo_desde_nombre(ev.nombre)
            if deducido:
                cambios["tipo"] = deducido
                advertencias.append(f"{ev.id}: tipo 'otro' → '{deducido.value}' por el nombre.")

        resultado.append(ev.model_copy(update=cambios))
    return ResultadoNormalizacion(resultado, dias, advertencias)
