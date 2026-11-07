"""Simulación punta a punta (PUL-29): una pantalla con Leer → Medir → Optimizar → Proponer. Sin LLM."""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

import src.app as app_modulo
from src.engine.collisions import detectar_colisiones
from src.models import cargar_cohorte

cliente = TestClient(app_modulo.app)
REAL = cargar_cohorte("data/cohorte.json")
PASOS = ["1 · Leer", "2 · Medir", "3 · Optimizar", "4 · Proponer"]


def test_sin_cohorte_elegida_muestra_las_dos_entradas():
    respuesta = cliente.get("/simulacion")
    assert respuesta.status_code == 200
    assert 'href="/simulacion?fuente=cohorte#leer"' in respuesta.text
    assert 'action="/simulacion"' in respuesta.text
    assert not any(paso in respuesta.text for paso in PASOS)


def test_ciclo_7_recorre_los_cuatro_pasos_con_los_numeros_del_motor():
    respuesta = cliente.get("/simulacion", params={"fuente": "cohorte"})
    assert respuesta.status_code == 200
    assert all(paso in respuesta.text for paso in PASOS)
    assert f"{len(REAL.evaluaciones)} evaluaciones" in respuesta.text
    assert f"{len(detectar_colisiones(REAL.evaluaciones))} colisiones" in respuesta.text
    ruta = app_modulo.FUENTES["cohorte"][1]
    resultado = app_modulo._optimizar(ruta, ruta.stat().st_mtime)  # el mismo que usan /antes-despues y la propuesta
    assert f"{resultado.reduccion_pico_pct:g} %" in respuesta.text
    assert 'hx-get="/antes-despues/propuesta?fuente=cohorte"' in respuesta.text


def test_el_enlace_al_simulador_abre_un_caso_real_de_colision():
    texto = cliente.get("/simulacion", params={"fuente": "cohorte"}).text
    enlace = re.search(r'href="(/simulador\?fuente=cohorte&(?:amp;)?evaluacion=[^"]+)"', texto)
    assert enlace, "falta el enlace al simulador con una evaluación en colisión"
    simulador = cliente.get(enlace.group(1).replace("&amp;", "&"))
    assert simulador.status_code == 200
    assert "con colisión el" in simulador.text
    assert "Fecha sugerida" in simulador.text  # el caso elegido tiene una alternativa mejor que mostrar


def test_cargar_redirige_a_la_simulacion():
    respuesta = cliente.get("/cargar", follow_redirects=False)
    assert respuesta.status_code == 307
    assert respuesta.headers["location"] == "/simulacion"


def test_fuente_desconocida_da_404():
    assert cliente.get("/simulacion", params={"fuente": "no-existe"}).status_code == 404


def test_subir_silabos_muestra_los_pasos_de_la_cohorte_subida(tmp_path, monkeypatch):
    monkeypatch.setattr(app_modulo, "DIR_TMP", tmp_path)
    monkeypatch.setitem(app_modulo.FUENTES, "subida", ("Sílabos subidos", tmp_path / "cohorte-subida.json"))
    pdf = sorted(Path("data/silabos/ciclo-07").glob("*.pdf"))[0]
    respuesta = cliente.post(
        "/simulacion",
        files=[("archivos", (pdf.name, pdf.read_bytes(), "application/pdf"))],
        data={"ciclo": REAL.ciclo, "fecha_inicio": REAL.fecha_inicio.isoformat()},
    )
    assert respuesta.status_code == 200
    assert all(paso in respuesta.text for paso in PASOS)
    assert "(caché)" in respuesta.text
    assert "/simulador?fuente=subida" in respuesta.text
    assert 'hx-get="/antes-despues/propuesta?fuente=subida"' in respuesta.text


def test_cohorte_que_no_se_puede_optimizar_avisa_sin_romper_la_pantalla(tmp_path, monkeypatch):
    ruta = tmp_path / "cohorte.json"
    evaluacion = {"curso": "Curso A", "nombre": "Práctica 1", "tipo": "practica_calificada", "semana": 3, "peso": 10}
    ruta.write_text(
        json.dumps({"nombre": "Sin fechas", "ciclo": "2026-II", "fecha_inicio": "2026-08-24", "evaluaciones": [evaluacion]}),
        encoding="utf-8",
    )
    monkeypatch.setitem(app_modulo.FUENTES, "cohorte", ("Cohorte", ruta))
    respuesta = cliente.get("/simulacion", params={"fuente": "cohorte"})
    assert respuesta.status_code == 200
    assert "Hay evaluaciones sin fecha" in respuesta.text
    assert "PUL-06" not in respuesta.text
    assert "/antes-despues/propuesta" not in respuesta.text  # sin optimización no hay propuesta que pedir
