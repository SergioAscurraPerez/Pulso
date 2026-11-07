"""Propuesta de reprogramación (PUL-08): un documento listo para circular, no una carta.

Las cifras las calcula el código a partir del resultado del solver (PUL-12) y del motor de carga:
diagnóstico, cambios, métricas antes → después, beneficio y costo. El LLM solo redacta el
párrafo de resumen con esos mismos datos, en voz de documento (sin saludos ni destinatario),
así ninguna cifra puede salir inventada.

Si no hay API key o el LLM falla, el resumen sale de una plantilla y el documento queda igual
de completo: la demo nunca se queda sin propuesta.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta

from src.engine.collisions import MIN_EVALUACIONES, VENTANA_DIAS, detectar_colisiones, es_fuerte
from src.engine.load_index import carga_semanal_cohorte, semana_de
from src.extraction.llm import ClienteChat, config_llm, crear_cliente, razonamiento
from src.formato import nombre_curso
from src.models import Cohorte
from src.optimizer.objective import ResultadoOptimizacion

# Tope de tokens de salida (incluye razonamiento). Sin tope, OpenRouter reserva el máximo del
# modelo y una key con poco saldo rechaza la llamada (402). El LLM solo escribe un párrafo de
# resumen: 1200 alcanza con razonamiento "low" y entra en keys con poco saldo.
MAX_TOKENS = 1200

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

PROMPT_SISTEMA = """Eres el asistente de PULSO, un sistema que detecta sobrecarga académica en una cohorte
de estudiantes universitarios y propone reprogramar evaluaciones.
Redacta SOLO el párrafo de resumen de un documento de propuesta de reprogramación, en español.
Reglas:
- Usa SOLO los datos del JSON. No inventes cursos, fechas, porcentajes ni cifras.
- Voz de documento, impersonal: sin saludo, sin despedida, sin firma y sin dirigirte a nadie
  ("Estimado…", "le presento…", "usted" están prohibidos).
- Explica en 2 a 4 oraciones el problema (colisiones y semana más cargada), qué se propone
  (cuántas evaluaciones se mueven) y el beneficio principal (usa las métricas del JSON).
- Sin títulos ni viñetas: un solo párrafo de máximo 110 palabras. Puedes usar **negrita** en las cifras clave."""


@dataclass
class Propuesta:
    texto: str  # documento completo en Markdown
    generada_por: str  # "llm" | "plantilla": quién redactó el resumen (las cifras siempre son del código)
    modelo: str | None = None
    advertencias: list[str] = field(default_factory=list)


def fecha_larga(f: date) -> str:
    return f"{DIAS[f.weekday()]} {f.day} de {MESES[f.month - 1]}"


def _dias(n: int) -> str:
    return f"{n:+d} día" if abs(n) == 1 else f"{n:+d} días"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


CRITERIO = f"{MIN_EVALUACIONES} o más evaluaciones fuertes en 72 h"


# ---------------------------------------------------------------- métricas del caso


def _max_fuertes_en_72h(cohorte: Cohorte, fechas: dict[str, date]) -> int:
    """Máximo de evaluaciones fuertes que caen en una misma ventana de 72 h."""
    dias = sorted(fechas.get(e.id) or e.fecha for e in cohorte.evaluaciones if es_fuerte(e) and (fechas.get(e.id) or e.fecha))
    return max((sum(1 for d in dias if inicio <= d < inicio + timedelta(days=VENTANA_DIAS)) for inicio in dias), default=0)


def _escenario(cohorte: Cohorte, fechas: dict[str, date]) -> dict:
    """Métricas de un calendario (el actual con `fechas={}` o el propuesto por el solver)."""
    colisiones = detectar_colisiones(cohorte.evaluaciones, fechas)
    carga = carga_semanal_cohorte(cohorte, fechas)
    semana_pico = max(carga, key=lambda s: carga[s])
    en_colision = {e.id for c in colisiones for e in c.evaluaciones}
    escenario = {
        "colisiones": len(colisiones),
        "detalle_colisiones": [
            {"desde": fecha_larga(c.inicio), "hasta": fecha_larga(c.fin), "cursos": [nombre_curso(x) for x in c.cursos]}
            for c in colisiones
        ],
        "evaluaciones_en_colision": len(en_colision),
        "semanas_criticas": len({semana_de(e, cohorte.fecha_inicio, c.fechas[e.id]) for c in colisiones for e in c.evaluaciones}),
        "max_fuertes_72h": _max_fuertes_en_72h(cohorte, fechas),
        "semana_pico": semana_pico,
        "carga_pico": carga[semana_pico],
        "dispersion_carga": round(statistics.pstdev(carga.values()), 2),
        "alumnos_con_colision": None,
    }
    if cohorte.grupos:  # con matrícula: alumnos que tienen al menos una colisión entre sus cursos
        escenario["alumnos_con_colision"] = sum(
            g.cantidad
            for g in cohorte.grupos
            if detectar_colisiones([e for e in cohorte.evaluaciones if e.curso in g.cursos], fechas)
        )
    return escenario


def _reduccion_pct(antes: float, despues: float) -> float:
    return round(100 * (antes - despues) / antes, 1) if antes else 0.0


def metricas_caso(cohorte: Cohorte, resultado: ResultadoOptimizacion) -> dict:
    """Todas las métricas del caso, antes y después, más el costo de aplicar la propuesta."""
    antes, despues = _escenario(cohorte, {}), _escenario(cohorte, resultado.fechas)
    dias = [abs(m.dias) for m in resultado.movimientos]
    return {
        "evaluaciones": len(cohorte.evaluaciones),
        "cursos": len(cohorte.cursos),
        "estudiantes": cohorte.total_estudiantes,
        "antes": antes,
        "despues": despues,
        "reduccion_pico_pct": _reduccion_pct(antes["carga_pico"], despues["carga_pico"]),
        "reduccion_dispersion_pct": _reduccion_pct(antes["dispersion_carga"], despues["dispersion_carga"]),
        "costo": {
            "evaluaciones_movidas": len(resultado.movimientos),
            "dias_movidos": sum(dias),
            "max_dias_una_evaluacion": max(dias, default=0),
            "cursos_a_coordinar": sorted({nombre_curso(m.curso) for m in resultado.movimientos}),
            "evaluaciones_bloqueadas_respetadas": sum(e.bloqueada for e in cohorte.evaluaciones),
        },
    }


def datos_propuesta(cohorte: Cohorte, resultado: ResultadoOptimizacion) -> dict:
    """Datos del caso para el LLM y la plantilla: todo calculado por el código, nada por el LLM."""
    metricas = metricas_caso(cohorte, resultado)
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
        "detalle_colisiones_antes": metricas["antes"]["detalle_colisiones"],
        "evaluaciones_bloqueadas": metricas["costo"]["evaluaciones_bloqueadas_respetadas"],
        "movimientos": [
            {
                "curso": nombre_curso(m.curso),
                "evaluacion": m.nombre,
                "fecha_original": fecha_larga(m.fecha_original),
                "fecha_nueva": fecha_larga(m.fecha_nueva),
                "dias": m.dias,
            }
            for m in resultado.movimientos
        ],
        "metricas": metricas,
    }


# ---------------------------------------------------------------- documento


def resumen_plantilla(datos: dict) -> str:
    """Resumen determinístico (respaldo cuando no hay LLM)."""
    m = datos["metricas"]
    a, d, costo = m["antes"], m["despues"], m["costo"]
    if not datos["movimientos"]:
        return (
            f"El calendario de {datos['cohorte']} tiene {_plural(a['colisiones'], 'colisión', 'colisiones')} "
            "y no se encontró una reprogramación que lo mejore respetando las restricciones: se mantiene como está."
        )
    return (
        f"El calendario actual de {datos['cohorte']} concentra **{_plural(a['colisiones'], 'colisión', 'colisiones')}** "
        f"({CRITERIO}) y su semana más cargada es la {a['semana_pico']}. "
        f"Se propone mover **{_plural(costo['evaluaciones_movidas'], 'evaluación', 'evaluaciones')}** "
        f"({_plural(costo['dias_movidos'], 'día', 'días')} en total) sin cambiar su tipo ni su peso: "
        f"las colisiones pasan de {a['colisiones']} a **{d['colisiones']}** y la carga pico baja "
        f"**{m['reduccion_pico_pct']}%**."
    )


def _respetadas(bloqueadas: int) -> str:
    # "Bloqueada" incluye las que fija el docente y las que la coordinación decidió mantener (human in the loop).
    if not bloqueadas:
        return "- Se respetan los feriados y las semanas de exámenes; no hay evaluaciones bloqueadas."
    return (
        f"- Se respetan {_plural(bloqueadas, 'evaluación que no se puede mover', 'evaluaciones que no se pueden mover')} "
        "(fijadas por el docente o mantenidas por la coordinación), los feriados y las semanas de exámenes."
    )


def _antes_despues(etiqueta: str, antes, despues) -> str:
    return f"- {etiqueta}: {antes} → **{despues}**"


def documento(datos: dict, resumen: str) -> str:
    """Documento completo en Markdown: resumen (LLM o plantilla) + todo lo calculado por el código."""
    m = datos["metricas"]
    a, d, costo = m["antes"], m["despues"], m["costo"]
    lineas = [
        f"# Propuesta de reprogramación de evaluaciones — {datos['cohorte']}",
        f"Ciclo {datos['ciclo']} · {m['cursos']} cursos · {m['evaluaciones']} evaluaciones"
        + (f" · {m['estudiantes']} estudiantes" if m["estudiantes"] else "")
        + " · Fechas calculadas por el optimizador CP-SAT de PULSO",
        "",
        "## Resumen",
        resumen.strip(),
        "",
        "## Diagnóstico",
    ]
    if a["detalle_colisiones"]:
        for c in a["detalle_colisiones"]:
            lineas.append(f"- Colisión del {c['desde']} al {c['hasta']}: {', '.join(c['cursos'])}.")
    else:
        lineas.append("- El calendario actual no tiene colisiones.")
    lineas += [
        f"- Semana más cargada: la {a['semana_pico']} (índice de carga {a['carga_pico']:g}).",
        "",
        "## Cambios propuestos",
    ]
    for mov in datos["movimientos"]:
        lineas.append(
            f"- **{mov['curso']} — {mov['evaluacion']}**: del {mov['fecha_original']} al {mov['fecha_nueva']} "
            f"({_dias(mov['dias'])})."
        )
    if not datos["movimientos"]:
        lineas.append("- No hace falta mover ninguna evaluación.")
    lineas += [
        "",
        "## Métricas del caso (antes → después)",
        _antes_despues(f"Colisiones ({CRITERIO})", a["colisiones"], d["colisiones"]),
        _antes_despues("Evaluaciones en alguna colisión", a["evaluaciones_en_colision"], d["evaluaciones_en_colision"]),
        _antes_despues("Semanas críticas (con colisión)", a["semanas_criticas"], d["semanas_criticas"]),
        _antes_despues("Máximo de evaluaciones fuertes en 72 h", a["max_fuertes_72h"], d["max_fuertes_72h"]),
        _antes_despues(
            "Semana más cargada",
            f"S{a['semana_pico']} ({a['carga_pico']:g})",
            f"S{d['semana_pico']} ({d['carga_pico']:g})",
        ),
        _antes_despues("Dispersión de la carga semanal (desv. estándar)", f"{a['dispersion_carga']:g}", f"{d['dispersion_carga']:g}"),
    ]
    if a["alumnos_con_colision"] is not None:
        lineas.append(_antes_despues("Estudiantes con al menos una colisión", a["alumnos_con_colision"], d["alumnos_con_colision"]))
    lineas += ["", "## Beneficio"]
    beneficios = []
    if a["colisiones"] > d["colisiones"]:
        beneficios.append(
            f"Se eliminan **{a['colisiones'] - d['colisiones']} de {a['colisiones']}** colisiones."
        )
    if a["evaluaciones_en_colision"] > d["evaluaciones_en_colision"]:
        beneficios.append(
            f"**{_plural(a['evaluaciones_en_colision'] - d['evaluaciones_en_colision'], 'evaluación deja', 'evaluaciones dejan')}** "
            "de estar en una colisión."
        )
    if a["alumnos_con_colision"] is not None and a["alumnos_con_colision"] > d["alumnos_con_colision"]:
        beneficios.append(
            f"**{_plural(a['alumnos_con_colision'] - d['alumnos_con_colision'], 'estudiante deja', 'estudiantes dejan')}** "
            "de tener una colisión entre sus cursos."
        )
    if m["reduccion_pico_pct"] > 0:
        beneficios.append(f"La carga pico baja **{m['reduccion_pico_pct']}%** ({a['carga_pico']:g} → {d['carga_pico']:g}).")
    if m["reduccion_dispersion_pct"] > 0:
        beneficios.append(f"La carga semanal queda **{m['reduccion_dispersion_pct']}% más pareja** entre semanas.")
    lineas += [f"- {b}" for b in beneficios] or ["- Sin mejoras medibles respecto al calendario actual."]
    if d["detalle_colisiones"]:
        restantes = "; ".join(f"del {c['desde']} al {c['hasta']} ({', '.join(c['cursos'])})" for c in d["detalle_colisiones"])
        lineas.append(f"- Sigue {_plural(d['colisiones'], 'colisión', 'colisiones')}: {restantes}.")
    if a["alumnos_con_colision"] is None:
        lineas.append("- Sin datos de matrícula, se considera que todos los estudiantes llevan todos los cursos.")
    lineas += [
        "",
        "## Costo de aplicarla",
        f"- {_plural(costo['evaluaciones_movidas'], 'evaluación movida', 'evaluaciones movidas')} de {m['evaluaciones']}; "
        f"{_plural(costo['dias_movidos'], 'día', 'días')} en total (máximo {_plural(costo['max_dias_una_evaluacion'], 'día', 'días')} en una evaluación).",
        f"- Cursos a coordinar: {', '.join(costo['cursos_a_coordinar']) or 'ninguno'}.",
        _respetadas(costo["evaluaciones_bloqueadas_respetadas"]),
        "",
        "## Próximo paso",
        "Validar cada cambio con el docente del curso antes de publicar el calendario.",
    ]
    return "\n".join(lineas)


def propuesta_plantilla(datos: dict) -> str:
    """Documento completo con el resumen de la plantilla (respaldo sin LLM)."""
    return documento(datos, resumen_plantilla(datos))


def generar_propuesta(
    cohorte: Cohorte,
    resultado: ResultadoOptimizacion,
    *,
    cliente: ClienteChat | None = None,
    modelo: str | None = None,
) -> Propuesta:
    """Documento de propuesta; el LLM redacta el resumen y, si no se puede, lo hace la plantilla."""
    datos = datos_propuesta(cohorte, resultado)
    try:
        if cliente is None:
            config = config_llm()
            cliente = crear_cliente(config)
            modelo = modelo or config.modelo
        respuesta = cliente.chat.completions.create(
            model=modelo,
            temperature=0.3,
            max_tokens=MAX_TOKENS,
            extra_body=razonamiento(),
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": json.dumps(datos, ensure_ascii=False, indent=2)},
            ],
        )
        resumen = (respuesta.choices[0].message.content or "").strip()
        if not resumen:
            raise ValueError("el LLM respondió vacío")
        return Propuesta(documento(datos, resumen), "llm", modelo)
    except Exception as error:  # noqa: BLE001 — cualquier fallo del LLM cae a la plantilla
        return Propuesta(propuesta_plantilla(datos), "plantilla", advertencias=[f"Sin LLM: {error}"])
