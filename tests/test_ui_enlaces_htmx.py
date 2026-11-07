"""Dentro de un bloque con hx-boost + hx-select, HTMX reemplaza solo ese bloque con el de la respuesta.

Un enlace a OTRA página dentro del bloque no navega (la otra página no tiene ese bloque):
tiene que llevar hx-boost="false". Se revisan todas las plantillas.
"""

import re
from pathlib import Path

PLANTILLAS = sorted(Path("src/ui/templates").glob("*.html"))
BLOQUE = re.compile(r'<(\w+)\b[^>]*\bid="([^"]+)"[^>]*\bhx-boost="true"[^>]*>')
ENLACE = re.compile(r'<a\b[^>]*\bhref="(/[^"?#]*)[^"]*"[^>]*>')


def _bloques_boost(texto: str):
    for inicio in BLOQUE.finditer(texto):
        etiqueta, profundidad = inicio.group(1), 0
        for marca in re.finditer(rf"<{etiqueta}\b|</{etiqueta}>", texto[inicio.start():]):
            profundidad += -1 if marca.group().startswith("</") else 1
            if profundidad == 0:
                yield texto[inicio.start(): inicio.start() + marca.end()]
                break


def test_enlaces_a_otra_pagina_dentro_de_hx_boost_desactivan_el_boost():
    pagina_de = {"carga.html": "/carga", "simulador.html": "/simulador"}
    problemas = []
    for plantilla in PLANTILLAS:
        for bloque in _bloques_boost(plantilla.read_text(encoding="utf-8")):
            for enlace in ENLACE.finditer(bloque):
                destino = enlace.group(1)
                misma_pagina = destino == pagina_de.get(plantilla.name)
                if not misma_pagina and 'hx-boost="false"' not in enlace.group(0):
                    problemas.append(f"{plantilla.name}: {enlace.group(0)}")
    assert not problemas, "Enlaces que HTMX no dejaría navegar:\n" + "\n".join(problemas)


def test_el_enlace_ver_como_se_resuelven_navega_a_antes_despues():
    from fastapi.testclient import TestClient

    from src.app import app

    texto = TestClient(app).get("/carga", params={"fuente": "mock"}).text
    enlace = re.search(r'<a\b[^>]*href="/antes-despues[^"]*"[^>]*>\s*Ver cómo se resuelven', texto)
    assert enlace and 'hx-boost="false"' in enlace.group(0)
