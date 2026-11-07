"""Comparar ciclos: cada data/cohortes/ciclo-NN.json entra en la comparación y como fuente de datos."""

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

import src.app as app_modulo

cliente = TestClient(app_modulo.app)
MOCK = Path("data/mock/evaluaciones_mock.json")
REAL = Path("data/cohorte.json")


def test_registrar_ciclos_ordena_por_numero_y_no_abre_los_json(tmp_path):
    for nombre in ["ciclo-10.json", "ciclo-02.json", "otro.json"]:
        (tmp_path / nombre).write_text("no es json: se valida al usarlo", encoding="utf-8")
    ciclos = app_modulo.registrar_ciclos(tmp_path)
    assert list(ciclos) == ["ciclo-02", "ciclo-10"]
    assert ciclos["ciclo-02"][0] == "Ciclo 2 · sílabos reales"


def test_con_un_solo_ciclo_avisa_sin_mostrar_comandos(monkeypatch):
    for clave in [c for c in app_modulo.FUENTES if c.startswith("ciclo-")]:
        monkeypatch.delitem(app_modulo.FUENTES, clave)
    respuesta = cliente.get("/comparar")
    assert respuesta.status_code == 200
    assert "Por ahora solo hay un ciclo procesado" in respuesta.text
    # La página es para el usuario: sin comandos ni rutas del repositorio.
    assert "python scripts" not in respuesta.text and "data/cohortes" not in respuesta.text


def test_compara_ciclos_y_senala_el_mas_sobrecargado(tmp_path, monkeypatch):
    ciclo5 = tmp_path / "ciclo-05.json"
    shutil.copy(MOCK, ciclo5)  # el mock: 3 colisiones, pico 255
    monkeypatch.setitem(app_modulo.FUENTES, "ciclo-05", ("Ciclo 5 · sílabos reales", ciclo5))
    texto = cliente.get("/comparar").text
    assert "Por ahora solo hay" not in texto
    assert texto.index("Ciclo 5") < texto.index("Ciclo 7")  # ordenados por n.º de ciclo
    # Ciclo 7: también 3 colisiones pero pico 267.5 → es el más sobrecargado.
    assert "El ciclo 7 es el más sobrecargado" in texto
    assert "3 → 0" in texto and "3 → 1" in texto  # colisiones antes → después de cada uno
    assert texto.count('class="matriz-celda') == 2 * 17  # 2 ciclos × 17 semanas
    assert 'href="/antes-despues?fuente=ciclo-05"' in texto
    # El ciclo nuevo también es una fuente para las demás vistas.
    assert cliente.get("/carga", params={"fuente": "ciclo-05"}).status_code == 200


def test_el_mismo_ciclo_guardado_dos_veces_cuenta_una(monkeypatch):
    monkeypatch.setitem(app_modulo.FUENTES, "ciclo-07", ("Ciclo 7 · sílabos reales", REAL))
    texto = cliente.get("/comparar").text
    assert texto.count('class="matriz-celda') == 17
