"""Recorte del sílabo antes de enviarlo al LLM: menos tokens, misma información.

Para extraer las evaluaciones solo hace falta:
1. el encabezado con el nombre del curso;
2. el cronograma por semanas (filas `N | …` de PUL-04), solo las partes que mencionan una evaluación;
3. la sección de evaluación del aprendizaje, completa (fórmula del promedio y definiciones).

Competencias, sumilla, estrategias, horas y bibliografía se descartan. Si no se encuentra la sección de
evaluación con su fórmula, o no hay cronograma por semanas, se envía el texto completo (nunca se arriesga
perder información).
"""

from __future__ import annotations

import re

_FILA_SEMANA = re.compile(r"^(\d{1,2}) \|")
_EVALUACION = re.compile(
    r"examen|evaluaci|calificad|\bpc\s*\d|\bp\d\b|laboratorio|\blab\b|\blb\s*\d|avance|trabajo|proyecto|exposici|"
    r"presentaci|disertaci|sustentaci|control de lectura|informe|entrega|\btest\b|cuestionario|monograf|ensayo|tarea",
    re.I,
)
_INICIO_SECCION_EVAL = re.compile(r"(EVALUACI[ÓO]N DEL APRENDIZAJE|SISTEMA DE EVALUACI[ÓO]N|^\s*[IVX]+\.\s*EVALUACI[ÓO]N)", re.I)
_SIGUIENTE_SECCION = re.compile(r"^\s*(?:[IVX]+\.|\d+\.\d*\s*)?\s*(FUENTES|REFERENCIAS|BIBLIOGRAF|APORTE DE LA ASIGNATURA)", re.I)
# Corta en celdas, viñetas y fin de oración (punto seguido de mayúscula): "Evaluación No. 1" no se parte.
_TRAMOS = re.compile(r"\s+\|\s+|\s+-\s+|(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ¿])")
_FORMULA = re.compile(r"\bP\s*F\b|promedio|%", re.I)


def _encabezado(lineas: list[str]) -> list[str]:
    """Primeras líneas de la página 1 hasta 'DATOS GENERALES' (nombre del curso, área)."""
    salida = []
    for linea in lineas[:15]:
        if re.search(r"DATOS GENERALES|SUMILLA", linea, re.I):
            break
        salida.append(linea)
    return salida


def _fila_compacta(linea: str) -> str:
    semana = _FILA_SEMANA.match(linea).group(1)
    tramos = [t.strip(" -|") for t in _TRAMOS.split(linea[len(semana) + 2 :])]
    utiles = [t for t in tramos if t and _EVALUACION.search(t)]
    return f"{semana} | " + " | ".join(dict.fromkeys(utiles)) if utiles else f"{semana} |"


def _seccion_evaluacion(lineas: list[str]) -> list[str]:
    for i, linea in enumerate(lineas):
        if _INICIO_SECCION_EVAL.search(linea):
            seccion = []
            for siguiente in lineas[i:]:
                if seccion and _SIGUIENTE_SECCION.search(siguiente):
                    break
                seccion.append(siguiente)
            return seccion
    return []


def recortar_para_extraccion(texto: str) -> tuple[str, bool]:
    """Devuelve (texto recortado, si se recortó). Ante la duda, devuelve el original."""
    lineas = [l for l in texto.splitlines() if not l.startswith("=== Página")]
    evaluacion = _seccion_evaluacion(lineas)
    if not evaluacion or not any(_FORMULA.search(l) for l in evaluacion):
        return texto, False

    semanas: dict[str, str] = {}
    for linea in lineas:
        if _FILA_SEMANA.match(linea):
            fila = _fila_compacta(linea)
            numero = fila.split(" |")[0]
            if int(numero) <= 18 and len(fila) > len(semanas.get(numero, "")):
                semanas[numero] = fila

    partes = [
        "[Encabezado]",
        *_encabezado(lineas),
        "",
        "[Cronograma: semana | menciones de evaluaciones]",
        *[semanas[s] for s in sorted(semanas, key=int)],
        "",
        "[Evaluación del aprendizaje]",
        *evaluacion,
    ]
    if not semanas:
        return texto, False
    return "\n".join(partes).strip(), True
