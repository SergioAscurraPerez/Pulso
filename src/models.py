"""Esquema de datos compartido por todos los módulos de Pulso."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

SEMANAS_CICLO = 17


class TipoEvaluacion(str, Enum):
    """Tipos de evaluación que aparecen en los sílabos."""

    EXAMEN_PARCIAL = "examen_parcial"
    EXAMEN_FINAL = "examen_final"
    PRACTICA_CALIFICADA = "practica_calificada"
    LABORATORIO = "laboratorio"
    PROYECTO = "proyecto"
    EXPOSICION = "exposicion"
    TAREA = "tarea"
    CONTROL_LECTURA = "control_lectura"
    OTRO = "otro"


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


class Evaluacion(BaseModel):
    """Una evaluación de un curso.

    `fecha` o `semana` puede faltar justo después de la extracción;
    la normalización (PUL-06) completa la fecha a partir de la semana.
    """

    id: str | None = Field(default=None, description="Identificador estable; se genera desde curso + nombre si falta.")
    curso: str = Field(min_length=1)
    nombre: str = Field(min_length=1, description="Nombre tal como aparece en el sílabo, p. ej. 'Práctica calificada 2'.")
    tipo: TipoEvaluacion
    fecha: date | None = None
    peso: float = Field(gt=0, le=100, description="Porcentaje de la nota final del curso (0–100].")
    semana: int | None = Field(default=None, ge=1, le=SEMANAS_CICLO)
    bloqueada: bool = Field(default=False, description="True si el docente no permite moverla.")

    @model_validator(mode="after")
    def _completar(self) -> Evaluacion:
        if self.fecha is None and self.semana is None:
            raise ValueError("La evaluación necesita 'fecha' o 'semana'.")
        if self.id is None:
            self.id = f"{_slug(self.curso)}--{_slug(self.nombre)}"
        return self


class Cohorte(BaseModel):
    """Conjunto de evaluaciones de los cursos que lleva una misma cohorte en un ciclo."""

    nombre: str
    ciclo: str = Field(description="Ciclo académico, p. ej. '2026-II'.")
    fecha_inicio: date = Field(description="Lunes de la semana 1 del ciclo.")
    evaluaciones: list[Evaluacion]

    @model_validator(mode="after")
    def _ids_unicos(self) -> Cohorte:
        ids = [e.id for e in self.evaluaciones]
        repetidos = sorted({i for i in ids if ids.count(i) > 1})
        if repetidos:
            raise ValueError(f"IDs de evaluación repetidos: {repetidos}")
        return self

    @property
    def cursos(self) -> list[str]:
        return sorted({e.curso for e in self.evaluaciones})


def cargar_cohorte(ruta: str | Path) -> Cohorte:
    """Lee y valida un JSON de cohorte (mock o generado por la extracción)."""
    return Cohorte.model_validate_json(Path(ruta).read_text(encoding="utf-8"))
