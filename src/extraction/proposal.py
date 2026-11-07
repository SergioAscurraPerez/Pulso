"""Propuesta de reprogramación para el coordinador (PUL-08).

El LLM redacta la propuesta en español a partir de los datos del solver (PUL-12): qué
evaluaciones se mueven, cuántos días, cuánto baja el pico y qué colisiones desaparecen.
El LLM solo redacta; los números salen del optimizador y se le pasan ya calculados.

Si no hay API key o el LLM falla, se genera la misma propuesta con una plantilla, para que
la demo nunca se quede sin texto.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from src.engine.collisions import detectar_colisiones
from src.extraction.llm import ClienteChat, config_llm, crear_cliente
from src.models import Cohorte
from src.optimizer.objective import ResultadoOptimizacion

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

PROMPT_SISTEMA = """Eres el asistente de PULSO, un sistema que detecta sobrecarga académica en una cohorte
de estudiantes universitarios y propone reprogramar evaluaciones.
Redacta una propuesta breve y formal, en español, dirigida al coordinador académico.
Reglas:
- Usa SOLO los datos del JSON. No inventes cursos, fechas, porcentajes ni cifras.
- Estructura: 1) contexto del problema (colisiones y semana pico), 2) cambios propuestos
  (cada evaluación movida con su fecha original, fecha nueva y días de diferencia),
  3) impacto (reducción del pico en % y colisiones antes/después), 4) siguiente paso
  (confirmar los cambios con los docentes de cada curso).
- Menciona que las evaluaciones bloqueadas por los docentes no se tocaron.
- Máximo 250 palabras. Formato Markdown simple (títulos ## y viñetas)."""


@dataclass
class Propuesta:
    texto: str
    generada_por: str  # "llm" | "plantilla"
    modelo: str | None = None
    advertencias: list[str] = field(default_factory=list)


def fecha_larga(f: date) -> str:
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]}"


def datos_propuesta(cohorte: Cohorte, resultado: ResultadoOptimizacion) -> dict:
    """Resumen del resultado del solver que se le pasa al LLM (y usa la plantilla)."""
    colisiones = detectar_colisiones(cohorte.evaluaciones)
    return {
        "cohorte": cohorte.nombre,
        "ciclo": cohorte.ciclo,
        "semana_pico_antes": resultado.pico_antes[0],
        "carga_pico_antes": resultado.pico_antes[1],
        "semana_pico_despues": resultado.pico_despues[0],
        "carga_pico_despues": resultado.pico_despues[1],
        "reduccion_pico_pct": resultado.reduccion_pico_pct,
        "colisiones_antes": resultado.colisiones_antes,
        "colisiones_despues": resultado.colisiones_despues,
        "detalle_colisiones_antes": [
            {"desde": fecha_larga(c.inicio), "hasta": fecha_larga(c.fin), "cursos": c.cursos} for c in colisiones
        ],
        "evaluaciones_bloqueadas": sum(e.bloqueada for e in cohorte.evaluaciones),
        "movimientos": [
            {
                "curso": m.curso,
                "evaluacion": m.nombre,
                "fecha_original": fecha_larga(m.fecha_original),
                "fecha_nueva": fecha_larga(m.fecha_nueva),
                "dias": m.dias,
            }
            for m in resultado.movimientos
        ],
    }


def propuesta_plantilla(datos: dict) -> str:
    """Propuesta determinística con los mismos datos (respaldo sin LLM)."""
    lineas = [
        f"## Propuesta de reprogramación — {datos['cohorte']} ({datos['ciclo']})",
        "",
        "## Contexto",
        f"La cohorte tiene {datos['colisiones_antes']} colisiones (3 o más evaluaciones fuertes en 72 h) "
        f"y su semana más cargada es la {datos['semana_pico_antes']} (índice {datos['carga_pico_antes']:g}).",
        "",
        "## Cambios propuestos",
    ]
    for m in datos["movimientos"]:
        lineas.append(
            f"- **{m['curso']} — {m['evaluacion']}**: del {m['fecha_original']} al {m['fecha_nueva']} "
            f"({m['dias']:+d} días)."
        )
    if not datos["movimientos"]:
        lineas.append("- No hace falta mover ninguna evaluación.")
    lineas += [
        "",
        f"Las {datos['evaluaciones_bloqueadas']} evaluaciones bloqueadas por los docentes se mantienen en su fecha.",
        "",
        "## Impacto",
        f"- La carga pico baja de {datos['carga_pico_antes']:g} a {datos['carga_pico_despues']:g} "
        f"(**−{datos['reduccion_pico_pct']}%**).",
        f"- Colisiones: {datos['colisiones_antes']} → {datos['colisiones_despues']}.",
        "",
        "## Siguiente paso",
        "Confirmar los cambios con los docentes de cada curso antes de publicar el calendario.",
    ]
    return "\n".join(lineas)


def generar_propuesta(
    cohorte: Cohorte,
    resultado: ResultadoOptimizacion,
    *,
    cliente: ClienteChat | None = None,
    modelo: str | None = None,
) -> Propuesta:
    """Redacta la propuesta con el LLM; si no se puede, usa la plantilla."""
    datos = datos_propuesta(cohorte, resultado)
    try:
        if cliente is None:
            config = config_llm()
            cliente = crear_cliente(config)
            modelo = modelo or config.modelo
        respuesta = cliente.chat.completions.create(
            model=modelo,
            temperature=0.3,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": json.dumps(datos, ensure_ascii=False, indent=2)},
            ],
        )
        texto = (respuesta.choices[0].message.content or "").strip()
        if not texto:
            raise ValueError("el LLM respondió vacío")
        return Propuesta(texto, "llm", modelo)
    except Exception as error:  # noqa: BLE001 — cualquier fallo del LLM cae a la plantilla
        return Propuesta(propuesta_plantilla(datos), "plantilla", advertencias=[f"Sin LLM: {error}"])
