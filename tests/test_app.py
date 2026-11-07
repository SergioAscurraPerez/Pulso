from fastapi.testclient import TestClient

from src.app import FUENTES, VISTAS, app

cliente = TestClient(app)


def test_inicio_muestra_la_cohorte_mock():
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "(mock)" in respuesta.text
    assert "Examen parcial" in respuesta.text


def test_todas_las_vistas_de_la_navegacion_responden():
    for ruta, titulo in VISTAS:
        respuesta = cliente.get(ruta, params={"fuente": "mock"})
        assert respuesta.status_code == 200, ruta
        assert titulo in respuesta.text


def test_fuente_desconocida_da_404():
    assert cliente.get("/", params={"fuente": "no-existe"}).status_code == 404
    assert cliente.get("/carga", params={"fuente": "no-existe"}).status_code == 404


def test_fuente_sin_archivo_da_404(tmp_path, monkeypatch):
    monkeypatch.setitem(FUENTES, "cohorte", ("Cohorte", tmp_path / "cohorte.json"))
    assert cliente.get("/", params={"fuente": "cohorte"}).status_code == 404


def test_json_invalido_da_500_con_detalle(tmp_path, monkeypatch):
    ruta = tmp_path / "cohorte.json"
    ruta.write_text('{"nombre": "x"}', encoding="utf-8")
    monkeypatch.setitem(FUENTES, "cohorte", ("Cohorte", ruta))
    respuesta = cliente.get("/", params={"fuente": "cohorte"})
    assert respuesta.status_code == 500
    assert "no cumple el esquema" in respuesta.json()["detail"]


def test_archivos_estaticos():
    assert cliente.get("/static/styles.css").status_code == 200
