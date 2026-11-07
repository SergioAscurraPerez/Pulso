import json
from types import SimpleNamespace

import pytest

from src.extraction.llm_parser import ErrorExtraccion, extraer_evaluaciones, validar_respuesta
from src.models import TipoEvaluacion

VALIDO = {
    "curso": "Ingeniería de Software II",
    "evaluaciones": [
        {"nombre": "Examen parcial", "tipo": "examen_parcial", "semana": 8, "fecha": None, "peso": 25},
        {"nombre": "Examen final", "tipo": "examen_final", "semana": 16, "fecha": None, "peso": 25},
        {"nombre": "Trabajo", "tipo": "proyecto", "semana": 14, "fecha": None, "peso": 16.67},
        *[{"nombre": f"Evaluación {i}", "tipo": "practica_calificada", "semana": s, "peso": 4.17} for i, s in enumerate([5, 7, 11, 13], 1)],
        *[{"nombre": "Laboratorio", "tipo": "laboratorio", "semana": s, "peso": 4.17} for s in [4, 8, 12, 15]],
    ],
}


class ClienteStub:
    """Devuelve las respuestas en orden; una respuesta que es Exception se lanza."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.llamadas.append(kwargs)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])


def test_validar_respuesta_valida():
    curso, evs, _ = validar_respuesta(json.dumps(VALIDO))
    assert curso == "Ingeniería de Software II"
    assert len(evs) == 11
    assert evs[0].tipo is TipoEvaluacion.EXAMEN_PARCIAL and evs[0].semana == 8
    assert len({e.id for e in evs}) == 11  # los laboratorios repetidos reciben sufijo
    assert evs[-1].nombre == "Laboratorio (4)"


def test_acepta_json_en_bloque_de_codigo():
    _, evs, _ = validar_respuesta("Aquí está:\n```json\n" + json.dumps(VALIDO) + "\n```")
    assert len(evs) == 11


@pytest.mark.parametrize(
    "respuesta, error",
    [
        ("no hay json", "JSON"),
        (json.dumps({**VALIDO, "evaluaciones": []}), "vacía"),
        (json.dumps({**VALIDO, "evaluaciones": [{**VALIDO["evaluaciones"][0], "tipo": "sorpresa"}]}), "tipo"),
        (json.dumps({**VALIDO, "evaluaciones": VALIDO["evaluaciones"][:2]}), "suman 50"),
        (json.dumps({**VALIDO, "evaluaciones": [{"nombre": "X", "tipo": "tarea", "peso": 100}]}), "fecha"),
    ],
)
def test_validar_respuesta_rechaza(respuesta, error):
    with pytest.raises(ValueError, match=error):
        validar_respuesta(respuesta)


def test_extraer_pide_json_schema_y_devuelve_evaluaciones():
    cliente = ClienteStub(json.dumps(VALIDO))
    r = extraer_evaluaciones("texto del sílabo", cliente=cliente, modelo="m")
    assert r.intentos == 1 and len(r.evaluaciones) == 11
    assert r.suma_pesos == pytest.approx(100, abs=0.1)
    llamada = cliente.llamadas[0]
    assert llamada["response_format"]["type"] == "json_schema"
    assert llamada["temperature"] == 0
    assert "texto del sílabo" in llamada["messages"][-1]["content"]


def test_reintenta_con_el_error_si_no_valida():
    malo = json.dumps({**VALIDO, "evaluaciones": VALIDO["evaluaciones"][:2]})
    cliente = ClienteStub(malo, json.dumps(VALIDO))
    r = extraer_evaluaciones("s", cliente=cliente, modelo="m")
    assert r.intentos == 2 and r.advertencias
    correccion = cliente.llamadas[1]["messages"][-1]["content"]
    assert "suman 50" in correccion


def test_si_no_soporta_json_schema_usa_json_object():
    cliente = ClienteStub(RuntimeError("response_format json_schema is not supported"), json.dumps(VALIDO))
    r = extraer_evaluaciones("s", cliente=cliente, modelo="m")
    assert len(r.evaluaciones) == 11
    assert cliente.llamadas[1]["response_format"] == {"type": "json_object"}


def test_falla_tras_max_intentos():
    with pytest.raises(ErrorExtraccion, match="3 intentos"):
        extraer_evaluaciones("s", cliente=ClienteStub("x", "y", "z"), modelo="m")


def test_error_de_red_no_se_reintenta():
    with pytest.raises(ErrorExtraccion, match="Falló la llamada"):
        extraer_evaluaciones("s", cliente=ClienteStub(TimeoutError("timeout")), modelo="m")


def test_semana_estimada_genera_advertencia():
    datos = json.loads(json.dumps(VALIDO))
    datos["evaluaciones"][3]["semana_estimada"] = True
    _, evs, advertencias = validar_respuesta(json.dumps(datos))
    assert len(evs) == 11
    assert advertencias == ["Semana estimada (el sílabo no la indica): Evaluación 1 → semana 5"]


def test_reintento_deja_el_motivo_en_advertencias():
    malo = json.dumps({**VALIDO, "evaluaciones": VALIDO["evaluaciones"][:2]})
    r = extraer_evaluaciones("s", cliente=ClienteStub(malo, json.dumps(VALIDO)), modelo="m")
    assert "suman 50" in r.advertencias[-1]


def test_limita_tokens_de_salida():
    cliente = ClienteStub(json.dumps(VALIDO))
    extraer_evaluaciones("s", cliente=cliente, modelo="m")
    assert 0 < cliente.llamadas[0]["max_tokens"] <= 8000


def _sin_semana():
    datos = json.loads(json.dumps(VALIDO))
    for ev in datos["evaluaciones"][3:6]:
        ev["semana"] = None
    return json.dumps(datos)


def test_secuencia_groq_400_luego_sin_semana_luego_corrige():
    """Lo que pasó en producción: json_schema rechazado (400), JSON sin semanas y luego la corrección."""
    cliente = ClienteStub(RuntimeError("Error code: 400 - json_schema not supported"), _sin_semana(), json.dumps(VALIDO))
    r = extraer_evaluaciones("s", cliente=cliente, modelo="m", max_intentos=2)
    assert len(r.evaluaciones) == 11 and len(cliente.llamadas) == 3
    assert "corrigió" in " ".join(r.advertencias)


def test_pasar_a_json_object_no_gasta_el_unico_intento():
    cliente = ClienteStub(RuntimeError("response_format json_schema is not supported"), json.dumps(VALIDO))
    r = extraer_evaluaciones("s", cliente=cliente, modelo="m", max_intentos=1)
    assert len(r.evaluaciones) == 11
