"""Detector de colisiones (PUL-10).

Una colisión es una ventana de 72 h (3 días calendario consecutivos) con al menos
`MIN_EVALUACIONES` evaluaciones fuertes. Las ventanas que se solapan se fusionan en una
sola colisión, así la semana de finales aparece como un único bloque y no como varias ventanas repetidas.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.engine.load_index import carga_evaluacion
from src.models import Evaluacion

VENTANA_DIAS = 3  # 72 h: día d, d+1 y d+2
MIN_EVALUACIONES = 3
# Una evaluación es "fuerte" si aporta al menos esta carga (peso × factor de tipo).
# Con 10 entra una práctica calificada de 10 % y queda fuera un laboratorio de 5 %.
UMBRAL_FUERTE = 10.0


@dataclass
class Colision:
    inicio: date
    fin: date
    evaluaciones: list[Evaluacion] = field(default_factory=list)
    max_en_72h: int = 0
    fechas: dict[str, date] = field(default_factory=dict, repr=False)

    @property
    def cursos(self) -> list[str]:
        return sorted({e.curso for e in self.evaluaciones})

    @property
    def carga(self) -> float:
        return round(sum(carga_evaluacion(e) for e in self.evaluaciones), 2)

    def to_dict(self) -> dict:
        return {
            "inicio": self.inicio.isoformat(),
            "fin": self.fin.isoformat(),
            "max_en_72h": self.max_en_72h,
            "carga": self.carga,
            "cursos": self.cursos,
            "evaluaciones": [
                {"id": e.id, "curso": e.curso, "nombre": e.nombre, "fecha": self.fechas[e.id].isoformat()}
                for e in self.evaluaciones
            ],
        }


def es_fuerte(evaluacion: Evaluacion, umbral: float = UMBRAL_FUERTE) -> bool:
    return carga_evaluacion(evaluacion) >= umbral


def detectar_colisiones(
    evaluaciones: Iterable[Evaluacion],
    fechas: dict[str, date] | None = None,
    *,
    umbral: float = UMBRAL_FUERTE,
    min_evaluaciones: int = MIN_EVALUACIONES,
    ventana_dias: int = VENTANA_DIAS,
) -> list[Colision]:
    """Devuelve las colisiones ordenadas por fecha.

    `fechas={id: fecha}` sobrescribe fechas (escenario propuesto por el optimizador).
    Las evaluaciones sin fecha se ignoran: la normalización (PUL-06) debe completarlas antes.
    """
    fechas = fechas or {}
    fuertes: list[tuple[date, Evaluacion]] = sorted(
        ((fechas.get(e.id) or e.fecha, e) for e in evaluaciones if es_fuerte(e, umbral) and (fechas.get(e.id) or e.fecha)),
        key=lambda par: (par[0], par[1].id),
    )

    # 1) Ventanas de `ventana_dias` días que arrancan en la fecha de cada evaluación fuerte.
    ventanas: list[tuple[date, date, list[tuple[date, Evaluacion]]]] = []
    for inicio, _ in fuertes:
        fin = inicio + timedelta(days=ventana_dias - 1)
        dentro = [(f, e) for f, e in fuertes if inicio <= f <= fin]
        if len(dentro) >= min_evaluaciones:
            ventanas.append((inicio, fin, dentro))

    # 2) Fusionar ventanas que se solapan.
    colisiones: list[Colision] = []
    for inicio, fin, dentro in ventanas:
        actual = colisiones[-1] if colisiones else None
        if actual and inicio <= actual.fin:
            ids = {e.id for e in actual.evaluaciones}
            actual.evaluaciones += [e for _, e in dentro if e.id not in ids]
            actual.fechas.update({e.id: f for f, e in dentro})
            actual.fin = max(actual.fin, max(f for f, _ in dentro))
            actual.max_en_72h = max(actual.max_en_72h, len(dentro))
        else:
            colisiones.append(
                Colision(
                    inicio=inicio,
                    fin=max(f for f, _ in dentro),
                    evaluaciones=[e for _, e in dentro],
                    max_en_72h=len(dentro),
                    fechas={e.id: f for f, e in dentro},
                )
            )
    return colisiones
