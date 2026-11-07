"""La cohorte subida vive en /tmp de una instancia de Vercel: si ya no está, la app avisa con una página."""

import json

import pytest
from fastapi.testclient import TestClient

import src.app as app_modulo

cliente = TestClient(app_modulo.app)


@pytest.fixture
def sin_cohorte_subida(tmp_path, monkeypatch):
    monkeypatch.setitem(app_modulo.FUENTES, "subida", ("Sílabos subidos", tmp_path / "no-existe.json"))


@pytest.mark.parametrize("ruta", ["/", "/carga", "/antes-despues", "/simulador", "/simulacion"])
def test_enlace_a_una_subida_que_ya_no_esta_muestra_un_aviso(sin_cohorte_subida, ruta):
    respuesta = cliente.get(ruta, params={"fuente": "subida"})
    assert respuesta.status_code == 404
    assert respuesta.headers["content-type"].startswith("text/html")
    assert "Los sílabos subidos ya no están disponibles" in respuesta.text
    assert 'href="/simulacion"' in respuesta.text


def test_la_propuesta_de_una_subida_que_ya_no_esta_no_deja_la_pantalla_esperando(sin_cohorte_subida):
    respuesta = cliente.get("/antes-despues/propuesta", params={"fuente": "subida"})
    assert respuesta.status_code == 200  # HTMX solo reemplaza el "Redactando…" con respuestas 2xx
    assert "No se pudo generar la propuesta" in respuesta.text


ERROR_402 = (
    "Falló la llamada al LLM: Error code: 402 - This request requires more credits. "
    "To increase, visit https://openrouter.ai/workspaces/default/keys/abc123 and adjust the key's daily limit"
)


def test_el_error_del_llm_no_muestra_urls_de_la_cuenta(tmp_path, monkeypatch):
    monkeypatch.setattr(app_modulo, "DIR_TMP", tmp_path)
    monkeypatch.setitem(app_modulo.FUENTES, "subida", ("Sílabos subidos", tmp_path / "cohorte-subida.json"))

    def falla(pdf):
        raise RuntimeError(ERROR_402)

    monkeypatch.setattr(app_modulo, "_extraer_en_linea", falla)
    respuesta = cliente.post(
        "/simulacion",
        files=[("archivos", ("nuevo.pdf", b"%PDF-1.4 nuevo", "application/pdf"))],
        data={"ciclo": "2026-I", "fecha_inicio": "2026-03-02"},
    )
    assert respuesta.status_code == 422
    assert "Error code: 402" in respuesta.text  # el motivo se ve…
    assert "openrouter.ai" not in respuesta.text  # …pero no la URL de la cuenta


def test_mensaje_para_usuario_quita_urls_y_acota():
    assert "https://" not in app_modulo.mensaje_para_usuario(ERROR_402)
    assert app_modulo.mensaje_para_usuario("a" * 500).endswith("…")
    assert len(app_modulo.mensaje_para_usuario("a" * 500)) == 240


def test_otras_fuentes_desconocidas_siguen_dando_404():
    assert cliente.get("/carga", params={"fuente": "no-existe"}).status_code == 404


def test_todos_los_tipos_tienen_etiqueta_con_tildes():
    assert set(app_modulo.ETIQUETAS_TIPO) == set(app_modulo.TipoEvaluacion)
    texto = cliente.get("/", params={"fuente": "mock"}).text
    assert "Práctica calificada" in texto
    assert "Practica calificada" not in texto


def test_ninguna_vista_muestra_paginas_en_construccion():
    for ruta, _ in app_modulo.VISTAS:
        texto = cliente.get(ruta, params={"fuente": "mock"}).text
        assert "en construcción" not in texto
        assert "PUL-" not in texto


def test_descargar_propuesta_sin_optimizacion_posible_no_da_500(tmp_path, monkeypatch):
    ruta = tmp_path / "cohorte.json"
    evaluacion = {"curso": "Curso A", "nombre": "Práctica 1", "tipo": "practica_calificada", "semana": 3, "peso": 10}
    ruta.write_text(
        json.dumps({"nombre": "Sin fechas", "ciclo": "2026-II", "fecha_inicio": "2026-08-24", "evaluaciones": [evaluacion]}),
        encoding="utf-8",
    )
    monkeypatch.setitem(app_modulo.FUENTES, "cohorte", ("Cohorte", ruta))
    respuesta = cliente.get("/antes-despues/propuesta.md", params={"fuente": "cohorte"})
    assert respuesta.status_code == 422
    assert "No se pudo generar la propuesta" in respuesta.text


def test_kpi_de_rechazos_concuerda_en_singular_y_plural():
    movidas = app_modulo._optimizar(app_modulo.FUENTES["mock"][1], app_modulo.FUENTES["mock"][1].stat().st_mtime).movimientos
    uno = cliente.get("/antes-despues", params={"fuente": "mock", "rechazadas": movidas[0].id}).text
    assert "las bloqueadas y la rechazada no se mueven" in uno
    dos = cliente.get("/antes-despues", params={"fuente": "mock", "rechazadas": f"{movidas[0].id},{movidas[1].id}"}).text
    assert "las bloqueadas y las 2 rechazadas no se mueven" in dos
