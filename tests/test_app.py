import json

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


def _cohorte_con_colision(tmp_path, monkeypatch):
    """Semana 2: 3 prácticas de 10 % en 72 h (colisión). Semana 5: una tarea suelta."""
    evaluaciones = [
        {"curso": curso, "nombre": "Práctica 1", "tipo": "practica_calificada", "fecha": fecha, "peso": 10}
        for curso, fecha in [("Curso A", "2026-09-01"), ("Curso B", "2026-09-02"), ("Curso C", "2026-09-03")]
    ] + [{"curso": "Curso A", "nombre": "Tarea 1", "tipo": "tarea", "fecha": "2026-09-22", "peso": 5}]
    ruta = tmp_path / "cohorte.json"
    ruta.write_text(
        json.dumps({"nombre": "Prueba", "ciclo": "2026-II", "fecha_inicio": "2026-08-24", "evaluaciones": evaluaciones}),
        encoding="utf-8",
    )
    monkeypatch.setitem(FUENTES, "cohorte", ("Cohorte", ruta))


def test_carga_marca_en_rojo_solo_las_semanas_con_colision(tmp_path, monkeypatch):
    _cohorte_con_colision(tmp_path, monkeypatch)
    respuesta = cliente.get("/carga", params={"fuente": "cohorte"})
    assert respuesta.status_code == 200
    assert 'aria-label="Semana 2: carga 30, semana crítica"' in respuesta.text
    assert 'aria-label="Semana 5: carga 3"' in respuesta.text
    assert respuesta.text.count('class="celda critica"') == 1
    assert "Colisiones detectadas (1)" in respuesta.text


def test_carga_al_elegir_semana_muestra_sus_evaluaciones(tmp_path, monkeypatch):
    _cohorte_con_colision(tmp_path, monkeypatch)
    respuesta = cliente.get("/carga", params={"fuente": "cohorte", "semana": 2})
    assert respuesta.status_code == 200
    assert respuesta.text.count("En colisión") == 3
    assert "Curso C" in respuesta.text

    vacia = cliente.get("/carga", params={"fuente": "cohorte", "semana": 3})
    assert "Sin evaluaciones esta semana." in vacia.text


def test_carga_rechaza_semanas_fuera_del_ciclo():
    assert cliente.get("/carga", params={"semana": 0}).status_code == 422
    assert cliente.get("/carga", params={"semana": 18}).status_code == 422


def test_carga_con_el_mock():
    respuesta = cliente.get("/carga")
    assert respuesta.status_code == 200
    assert "en construcción" not in respuesta.text


def test_simulador_sin_parametros_muestra_el_formulario():
    respuesta = cliente.get("/simulador")
    assert respuesta.status_code == 200
    assert "Elige una evaluación" in respuesta.text
    assert "en construcción" not in respuesta.text


def test_simulador_da_riesgo_y_fecha_sugerida(tmp_path, monkeypatch):
    _cohorte_con_colision(tmp_path, monkeypatch)
    params = {"fuente": "cohorte", "evaluacion": "curso-c--practica-1", "fecha": "2026-09-03"}
    respuesta = cliente.get("/simulador", params=params)
    assert respuesta.status_code == 200
    # Sin grupos de matrícula, todos llevan los 3 cursos: el 3 de setiembre choca para el 100 %.
    assert "100 %" in respuesta.text
    # La mejor alternativa sin colisión y con menor carga es el lunes 7 de setiembre (semana 3).
    assert "lun 07/09/2026" in respuesta.text
    assert "fecha=2026-09-07" in respuesta.text


def test_simulador_valida_evaluacion_y_fecha(tmp_path, monkeypatch):
    _cohorte_con_colision(tmp_path, monkeypatch)
    no_existe = cliente.get("/simulador", params={"fuente": "cohorte", "evaluacion": "no-existe", "fecha": "2026-09-03"})
    assert no_existe.status_code == 404
    fuera = cliente.get("/simulador", params={"fuente": "cohorte", "evaluacion": "curso-c--practica-1", "fecha": "2027-03-01"})
    assert fuera.status_code == 200
    assert "La fecha debe estar dentro del ciclo" in fuera.text
