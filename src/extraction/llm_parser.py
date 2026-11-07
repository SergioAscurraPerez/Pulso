"""Extracción de evaluaciones de un sílabo con LLM (PUL-05).

Recibe el texto de PUL-04 y devuelve una lista de `Evaluacion` validada con Pydantic.
- Salida estructurada: se pide JSON con un esquema (`response_format=json_schema`). Si el
  modelo no lo soporta, se reintenta con `json_object` y el esquema dentro del prompt.
- Si la respuesta no valida (JSON roto, campos inválidos, pesos que no suman ~100), se
  reintenta enviándole al LLM los errores concretos para que los corrija.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, ValidationError

from src.extraction.llm import ClienteChat, config_llm, crear_cliente
from src.extraction.pdf_reader import TextoSilabo
from src.models import SEMANAS_CICLO, Evaluacion, TipoEvaluacion

MAX_INTENTOS = 3
# Tope de tokens de salida (incluye el razonamiento del modelo). Sin tope, OpenRouter reserva el
# máximo del modelo y una key con poco saldo rechaza la llamada (402).
MAX_TOKENS = 6000
TOLERANCIA_PESOS = 5.0  # la suma de pesos debe estar en 100 ± 5


class EvaluacionExtraida(BaseModel):
    nombre: str = Field(description="Nombre como aparece en el sílabo, p. ej. 'Examen parcial', 'Práctica calificada 2'.")
    tipo: TipoEvaluacion
    semana: int | None = Field(default=None, ge=1, le=SEMANAS_CICLO, description="Semana del cronograma.")
    semana_estimada: bool = Field(default=False, description="true si el sílabo no indica la semana y se estimó.")
    fecha: str | None = Field(default=None, description="Fecha ISO YYYY-MM-DD solo si el sílabo la indica explícitamente.")
    peso: float = Field(gt=0, le=100, description="Porcentaje de la nota final (0–100].")


class SilaboExtraido(BaseModel):
    curso: str = Field(description="Nombre oficial del curso.")
    evaluaciones: list[EvaluacionExtraida]


PROMPT_SISTEMA = f"""Extraes las evaluaciones calificadas de sílabos universitarios peruanos.
Devuelve SOLO JSON con este esquema:
{json.dumps(SilaboExtraido.model_json_schema(), ensure_ascii=False)}

Reglas:
- Una entrada por cada evaluación calificada (exámenes, prácticas calificadas, laboratorios,
  proyectos/avances, exposiciones, trabajos, controles de lectura). Si la fórmula usa P1…P4,
  son 4 evaluaciones distintas.
- `tipo` debe ser uno de: {", ".join(t.value for t in TipoEvaluacion)}.
- `semana`: tómala del cronograma (filas "N | …" de las tablas). Examen parcial suele ser la
  semana 8 y examen final la 16, pero usa lo que diga el sílabo. Si el sílabo NO indica la
  semana de una evaluación, estímala repartiéndolas en el ciclo y pon `semana_estimada: true`.
- `fecha`: solo si el sílabo trae una fecha explícita; si no, null.
- `peso`: % de la nota final del curso, calculado con la fórmula del promedio final.
  Ejemplo: PF = (2*PE + EP + EF)/4 y PE = ((P1+P2+P3+P4)/4 + W1 + PL)/3 con PL = (Lb1+…+Lb4)/4
  → EP = 25, EF = 25, W1 = 16.67, cada P = 4.17, cada Lb = 4.17. Los pesos deben sumar ~100.
- No inventes evaluaciones que no estén en el sílabo."""


@dataclass
class ResultadoExtraccion:
    curso: str
    evaluaciones: list[Evaluacion]
    intentos: int
    advertencias: list[str] = field(default_factory=list)

    @property
    def suma_pesos(self) -> float:
        return round(sum(e.peso for e in self.evaluaciones), 2)


class ErrorExtraccion(RuntimeError):
    pass


def _json_de_respuesta(texto: str) -> dict:
    """Parsea el JSON aunque venga dentro de ```json … ``` o con texto alrededor."""
    texto = texto.strip()
    bloque = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    if bloque:
        texto = bloque.group(1)
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin == -1:
        raise ValueError("la respuesta no contiene un objeto JSON")
    return json.loads(texto[inicio : fin + 1])


def validar_respuesta(texto: str, curso_por_defecto: str | None = None) -> tuple[str, list[Evaluacion], list[str]]:
    """Convierte la respuesta del LLM en `Evaluacion`. Lanza `ValueError` con los errores para reintentar."""
    try:
        silabo = SilaboExtraido.model_validate(_json_de_respuesta(texto))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValueError(str(error)) from error
    curso = (silabo.curso or curso_por_defecto or "").strip()
    if not curso:
        raise ValueError("falta 'curso'")
    if not silabo.evaluaciones:
        raise ValueError("la lista 'evaluaciones' está vacía")

    evaluaciones, errores, advertencias = [], [], []
    nombres: dict[str, int] = {}
    for i, ev in enumerate(silabo.evaluaciones):
        nombre = ev.nombre.strip()
        nombres[nombre] = nombres.get(nombre, 0) + 1
        if nombres[nombre] > 1:  # nombres repetidos → ids repetidos en la cohorte
            nombre = f"{nombre} ({nombres[nombre]})"
        if ev.semana_estimada:
            advertencias.append(f"Semana estimada (el sílabo no la indica): {nombre} → semana {ev.semana}")
        try:
            evaluaciones.append(
                Evaluacion(curso=curso, nombre=nombre, tipo=ev.tipo, semana=ev.semana, fecha=ev.fecha, peso=ev.peso)
            )
        except ValidationError as error:
            errores.append(f"evaluaciones[{i}] ({ev.nombre}): {error.errors()[0]['msg']}")
    if errores:
        raise ValueError("; ".join(errores))

    suma = sum(e.peso for e in evaluaciones)
    if abs(suma - 100) > TOLERANCIA_PESOS:
        raise ValueError(f"los pesos suman {suma:.1f} y deben sumar ~100; recalcúlalos con la fórmula del promedio final")
    return curso, evaluaciones, advertencias


def _formato_respuesta(con_esquema: bool) -> dict:
    if con_esquema:
        return {
            "type": "json_schema",
            "json_schema": {"name": "silabo", "schema": SilaboExtraido.model_json_schema()},
        }
    return {"type": "json_object"}


def extraer_evaluaciones(
    silabo: TextoSilabo | str,
    *,
    curso: str | None = None,
    cliente: ClienteChat | None = None,
    modelo: str | None = None,
    max_intentos: int = MAX_INTENTOS,
) -> ResultadoExtraccion:
    """Extrae las evaluaciones de un sílabo con el LLM, reintentando si la validación falla."""
    texto = silabo.texto if isinstance(silabo, TextoSilabo) else silabo
    if cliente is None:
        config = config_llm()
        cliente = crear_cliente(config, timeout=120)
        modelo = modelo or config.modelo

    mensajes = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {"role": "user", "content": (f"Curso: {curso}\n\n" if curso else "") + f"Sílabo:\n{texto}"},
    ]
    con_esquema = True
    errores: list[str] = []
    for intento in range(1, max_intentos + 1):
        try:
            respuesta = cliente.chat.completions.create(
                model=modelo,
                temperature=0,
                max_tokens=MAX_TOKENS,
                messages=mensajes,
                response_format=_formato_respuesta(con_esquema),
                extra_body={"reasoning": {"effort": "low"}},
            )
        except Exception as error:  # noqa: BLE001
            mensaje = str(error).lower()
            if con_esquema and ("response_format" in mensaje or "json_schema" in mensaje):
                con_esquema = False  # el modelo no soporta json_schema: probar con json_object
                continue
            raise ErrorExtraccion(f"Falló la llamada al LLM: {error}") from error

        contenido = respuesta.choices[0].message.content or ""
        try:
            nombre_curso, evaluaciones, advertencias = validar_respuesta(contenido, curso)
            if errores:
                advertencias.append(f"Se corrigió tras {len(errores)} intento(s) fallido(s): " + " | ".join(errores))
            return ResultadoExtraccion(nombre_curso, evaluaciones, intento, advertencias)
        except ValueError as error:
            errores.append(str(error))
            mensajes += [
                {"role": "assistant", "content": contenido},
                {"role": "user", "content": f"Tu respuesta no es válida: {error}. Corrige y devuelve SOLO el JSON completo."},
            ]
    raise ErrorExtraccion(f"No se obtuvo una extracción válida en {max_intentos} intentos: {errores[-1] if errores else ''}")
