"""Verifica que el entorno de PULSO está listo: Python, dependencias y llamada de prueba al LLM.

Uso (desde la raíz del repo):
    python scripts/verificar_entorno.py            # dependencias + .env + llamada al LLM
    python scripts/verificar_entorno.py --sin-llm  # solo dependencias

Devuelve código de salida 0 si todo está bien y 1 si algo falla.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PYTHON_MINIMO = (3, 12)

# paquete en requirements.txt -> módulo que se importa
DEPENDENCIAS = {
    "pydantic": "pydantic",
    "ortools": "ortools.sat.python.cp_model",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "jinja2": "jinja2",
    "python-multipart": "python_multipart",
    "pdfplumber": "pdfplumber",
    "openai": "openai",
    "python-dotenv": "dotenv",
}


def verificar_python() -> bool:
    actual = sys.version_info[:2]
    ok = actual >= PYTHON_MINIMO
    estado = "OK" if ok else "FALLA"
    print(f"[{estado}] Python {sys.version.split()[0]} (mínimo {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]})")
    return ok


def verificar_dependencias() -> bool:
    ok = True
    for paquete, modulo in DEPENDENCIAS.items():
        try:
            importlib.import_module(modulo)
            print(f"[OK] {paquete} {version(paquete)}")
        except (ImportError, PackageNotFoundError) as error:
            ok = False
            print(f"[FALLA] {paquete}: {error}")
    return ok


def verificar_llm() -> bool:
    from dotenv import load_dotenv
    from openai import OpenAI, OpenAIError

    load_dotenv(RAIZ / ".env")
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    modelo = os.getenv("LLM_MODEL", "").strip()

    faltantes = [nombre for nombre, valor in
                 (("LLM_BASE_URL", base_url), ("LLM_API_KEY", api_key), ("LLM_MODEL", modelo)) if not valor]
    if faltantes:
        print(f"[FALLA] Faltan variables en .env: {', '.join(faltantes)} (copia .env.example a .env)")
        return False

    cliente = OpenAI(base_url=base_url, api_key=api_key, timeout=30, max_retries=1)
    inicio = time.perf_counter()
    try:
        respuesta = cliente.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": "Responde solo con la palabra: OK"}],
            # Los modelos con razonamiento (p. ej. Gemini 3.x) gastan tokens pensando antes de
            # responder: con 10 la respuesta llega vacía.
            max_tokens=500,
        )
    except OpenAIError as error:
        print(f"[FALLA] Llamada al LLM ({modelo}): {error}")
        return False

    texto = (respuesta.choices[0].message.content or "").strip() if respuesta.choices else ""
    if not texto:
        print(f"[FALLA] El LLM ({modelo}) respondió vacío")
        return False
    print(f"[OK] LLM {modelo} respondió en {time.perf_counter() - inicio:.1f} s: {texto!r}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-llm", action="store_true", help="no hacer la llamada de prueba al LLM")
    args = parser.parse_args()

    ok = verificar_python()
    ok = verificar_dependencias() and ok
    if not args.sin_llm and ok:
        ok = verificar_llm() and ok

    print("\nEntorno listo." if ok else "\nEl entorno tiene errores (ver arriba).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
