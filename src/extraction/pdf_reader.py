"""Lectura de sílabos PDF a texto (PUL-04).

- PDFs con texto seleccionable: pdfplumber. El texto fuera de las tablas va tal cual y cada
  tabla se reescribe como filas `celda | celda | …`, para que el LLM (PUL-05) no pierda la
  relación semana ↔ evaluación del cronograma.
- PDFs escaneados (casi sin texto): fallback a un modelo de visión vía OpenRouter, que transcribe
  cada página renderizada como imagen.
"""

from __future__ import annotations

import base64
import io
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import pdfplumber

# Menos caracteres útiles por página que esto → se considera escaneado.
MIN_CARACTERES_POR_PAGINA = 200
RESOLUCION_VISION = 150  # DPI al renderizar páginas para el modelo de visión

# Caracteres de uso privado (viñetas de fuentes Symbol/Wingdings, p. ej. U+F02E).
_USO_PRIVADO = re.compile("[-]")
_ESPACIOS = re.compile(r"[ \t ]+")
_LINEAS_VACIAS = re.compile(r"\n{3,}")

Transcriptor = Callable[[list[bytes]], list[str]]  # PNGs de las páginas → texto por página


@dataclass
class TextoSilabo:
    archivo: str
    texto: str
    paginas: int
    metodo: str  # "texto" | "vision"
    tablas: int = 0
    advertencias: list[str] = field(default_factory=list)

    @property
    def caracteres(self) -> int:
        return len(self.texto)


def limpiar(texto: str) -> str:
    """Normaliza el texto extraído: Unicode NFC, viñetas privadas → '-', espacios y líneas vacías."""
    texto = unicodedata.normalize("NFC", texto)
    texto = _USO_PRIVADO.sub("-", texto)
    texto = "\n".join(_ESPACIOS.sub(" ", linea).strip() for linea in texto.splitlines())
    return _LINEAS_VACIAS.sub("\n\n", texto).strip()


def _celda(valor: str | None) -> str:
    return " ".join((valor or "").split())


def tabla_a_texto(filas: list[list[str | None]]) -> str:
    """Convierte una tabla de pdfplumber en líneas `a | b | c`, sin filas vacías."""
    lineas = []
    for fila in filas:
        celdas = [_celda(c) for c in fila]
        if any(celdas):
            lineas.append(" | ".join(c for c in celdas if c))
    return "\n".join(lineas)


def _texto_pagina(pagina: pdfplumber.page.Page) -> tuple[str, int]:
    tablas = pagina.find_tables()
    bboxes = [t.bbox for t in tablas]

    def fuera_de_tablas(obj: dict) -> bool:
        x = (obj["x0"] + obj["x1"]) / 2
        y = (obj["top"] + obj["bottom"]) / 2
        return not any(x0 <= x <= x1 and top <= y <= bottom for x0, top, x1, bottom in bboxes)

    texto = (pagina.filter(fuera_de_tablas) if bboxes else pagina).extract_text() or ""
    partes = [texto]
    for i, tabla in enumerate(tablas, 1):
        contenido = tabla_a_texto(tabla.extract())
        if contenido:
            partes.append(f"[Tabla {i}]\n{contenido}")
    return "\n\n".join(partes), len(tablas)


def _abrir(origen: str | Path | bytes | BinaryIO) -> tuple[pdfplumber.PDF, str]:
    if isinstance(origen, (str, Path)):
        return pdfplumber.open(origen), Path(origen).name
    if isinstance(origen, bytes):
        return pdfplumber.open(io.BytesIO(origen)), "subido.pdf"
    return pdfplumber.open(origen), getattr(origen, "name", "subido.pdf")


def _renderizar(pdf: pdfplumber.PDF) -> list[bytes]:
    imagenes = []
    for pagina in pdf.pages:
        buffer = io.BytesIO()
        pagina.to_image(resolution=RESOLUCION_VISION).original.save(buffer, format="PNG")
        imagenes.append(buffer.getvalue())
    return imagenes


def transcribir_con_vision(imagenes: list[bytes]) -> list[str]:
    """Transcribe páginas escaneadas con un modelo de visión de OpenRouter.

    Usa `LLM_VISION_MODEL` si está definido; si no, `LLM_MODEL` (debe aceptar imágenes).
    """
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    modelo = os.getenv("LLM_VISION_MODEL") or os.getenv("LLM_MODEL")
    if not modelo:
        raise RuntimeError("Falta LLM_VISION_MODEL o LLM_MODEL en el entorno para transcribir PDFs escaneados.")
    cliente = OpenAI(base_url=os.getenv("LLM_BASE_URL"), api_key=os.getenv("LLM_API_KEY"), timeout=120)
    textos = []
    for png in imagenes:
        imagen = "data:image/png;base64," + base64.b64encode(png).decode()
        respuesta = cliente.chat.completions.create(
            model=modelo,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Transcribe literalmente el texto de esta página de un sílabo universitario. "
                            "Escribe las tablas como filas con celdas separadas por ' | '. No resumas ni comentes.",
                        },
                        {"type": "image_url", "image_url": {"url": imagen}},
                    ],
                }
            ],
        )
        textos.append(respuesta.choices[0].message.content or "")
    return textos


def leer_pdf(
    origen: str | Path | bytes | BinaryIO,
    *,
    transcriptor: Transcriptor | None = None,
    min_caracteres_por_pagina: int = MIN_CARACTERES_POR_PAGINA,
) -> TextoSilabo:
    """Lee un sílabo PDF (ruta, bytes o archivo abierto) y devuelve su texto limpio.

    Si el PDF casi no tiene texto seleccionable, usa `transcriptor` (por defecto, visión vía OpenRouter).
    """
    pdf, nombre = _abrir(origen)
    with pdf:
        paginas = []
        total_tablas = 0
        for numero, pagina in enumerate(pdf.pages, 1):
            texto, tablas = _texto_pagina(pagina)
            total_tablas += tablas
            paginas.append(f"=== Página {numero} ===\n{limpiar(texto)}")
        texto = "\n\n".join(paginas)
        n_paginas = len(pdf.pages)

        util = len(re.sub(r"=== Página \d+ ===|\s", "", texto))
        if n_paginas and util >= min_caracteres_por_pagina * n_paginas:
            return TextoSilabo(nombre, texto, n_paginas, "texto", total_tablas)

        transcriptor = transcriptor or transcribir_con_vision
        transcritas = transcriptor(_renderizar(pdf))
        texto = "\n\n".join(f"=== Página {i} ===\n{limpiar(t)}" for i, t in enumerate(transcritas, 1))
        return TextoSilabo(
            nombre,
            texto,
            n_paginas,
            "vision",
            advertencias=[f"PDF con poco texto seleccionable ({util} caracteres); se transcribió con visión."],
        )
