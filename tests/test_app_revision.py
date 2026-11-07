"""Human in the loop: la coordinación revisa, rechaza movimientos y aprueba la propuesta."""

import pytest
from fastapi.testclient import TestClient

from src.app import _optimizar, app, cohorte_con_rechazos, leer_rechazadas, url_revision
from src.models import cargar_cohorte
from src.optimizer.objective import optimizar

MOCK = "data/mock/evaluaciones_mock.json"


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app)


@pytest.fixture(scope="module")
def cohorte():
    return cargar_cohorte(MOCK)


@pytest.fixture(scope="module")
def primer_movimiento(cohorte):
    return optimizar(cohorte).movimientos[0]


def test_leer_rechazadas_ignora_ids_desconocidos(cohorte, primer_movimiento):
    assert leer_rechazadas(cohorte, f"no-existe,{primer_movimiento.id}") == (primer_movimiento.id,)
    assert leer_rechazadas(cohorte, None) == ()


def test_rechazar_mantiene_la_fecha_y_recalcula(cohorte, primer_movimiento):
    con_rechazo = cohorte_con_rechazos(cohorte, (primer_movimiento.id,))
    resultado = optimizar(con_rechazo)
    original = next(e for e in cohorte.evaluaciones if e.id == primer_movimiento.id)
    assert resultado.fechas[primer_movimiento.id] == original.fecha
    assert primer_movimiento.id not in {m.id for m in resultado.movimientos}
    assert resultado.factible


def test_url_revision_agrega_y_quita():
    url = url_revision("/antes-despues", "mock", ("b",), agregar="a", ancla="#movimientos")
    assert url == "/antes-despues?fuente=mock&rechazadas=a%2Cb#movimientos"
    assert url_revision("/antes-despues", "mock", ("a",), quitar="a") == "/antes-despues?fuente=mock"
    assert url_revision("/x", "mock", (), aprobada=True) == "/x?fuente=mock&aprobada=1"


def test_pantalla_ofrece_rechazar_y_muestra_borrador(cliente):
    r = cliente.get("/antes-despues", params={"fuente": "mock"})
    assert r.status_code == 200
    assert "Rechazar" in r.text
    assert "Borrador · pendiente de aprobación" in r.text


def test_movimiento_rechazado_aparece_como_mantenido(cliente, primer_movimiento):
    r = cliente.get("/antes-despues", params={"fuente": "mock", "rechazadas": primer_movimiento.id})
    assert r.status_code == 200
    assert "Mantenidas en su fecha por la coordinación (1)" in r.text
    assert "Restaurar" in r.text
    assert f"rechazadas={primer_movimiento.id}" in r.text  # la propuesta se pide con las decisiones


def test_propuesta_borrador_y_aprobada(cliente, primer_movimiento):
    borrador = cliente.get("/antes-despues/propuesta", params={"fuente": "mock"})
    assert "Aprobar propuesta" in borrador.text and "Descargar propuesta" not in borrador.text
    aprobada = cliente.get(
        "/antes-despues/propuesta", params={"fuente": "mock", "rechazadas": primer_movimiento.id, "aprobada": "1"}
    )
    assert "Descargar propuesta" in aprobada.text
    assert "1 evaluación se mantiene en su fecha" in aprobada.text


def test_pantalla_aprobada_cierra_las_decisiones(cliente):
    r = cliente.get("/antes-despues", params={"fuente": "mock", "aprobada": "1"})
    assert "Aprobada por la coordinación" in r.text
    assert "Rechazar" not in r.text


def test_descarga_incluye_las_decisiones(cliente, primer_movimiento):
    r = cliente.get("/antes-despues/propuesta.md", params={"fuente": "mock", "rechazadas": primer_movimiento.id})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers["content-disposition"]
    assert "Revisado por la coordinación" in r.text


def test_optimizacion_con_rechazos_se_cachea_aparte(primer_movimiento):
    from pathlib import Path

    ruta = Path(MOCK).resolve()
    base = _optimizar(ruta, ruta.stat().st_mtime)
    con = _optimizar(ruta, ruta.stat().st_mtime, (primer_movimiento.id,))
    assert base is not con
    assert len(con.movimientos) != len(base.movimientos) or con.fechas != base.fechas
