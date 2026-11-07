"""Las páginas muestran errores claros; los detalles técnicos van a los logs. La API sigue en JSON."""

from fastapi.testclient import TestClient

from src.app import app

cliente = TestClient(app)


def test_404_y_422_son_paginas_no_json():
    for ruta, params, codigo in [
        ("/carga", {"fuente": "no-existe"}, 404),
        ("/simulador", {"fuente": "mock", "evaluacion": "no-existe", "fecha": "2026-09-01"}, 404),
        ("/carga", {"fuente": "mock", "semana": 99}, 422),
        ("/no-existe", {}, 404),
    ]:
        respuesta = cliente.get(ruta, params=params)
        assert respuesta.status_code == codigo, ruta
        assert respuesta.headers["content-type"].startswith("text/html"), ruta
        assert '"detail"' not in respuesta.text and "Fuente de datos no disponible" not in respuesta.text


def test_la_api_sigue_respondiendo_json():
    respuesta = cliente.get("/api/simular", params={"preset": "no-existe"})
    assert respuesta.status_code == 404
    assert "detail" in respuesta.json()
