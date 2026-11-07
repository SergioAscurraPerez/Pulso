"""Cliente LLM compartido (OpenRouter vía SDK `openai`).

Lee `LLM_BASE_URL`, `LLM_API_KEY` y `LLM_MODEL` del entorno (`.env` en local, variables del
proyecto en Vercel).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv


class ClienteChat(Protocol):
    """Lo mínimo que se usa del cliente `openai.OpenAI`; permite inyectar un stub en los tests."""

    @property
    def chat(self): ...


@dataclass
class ConfigLLM:
    base_url: str
    api_key: str
    modelo: str

    @property
    def completa(self) -> bool:
        return bool(self.base_url and self.api_key and self.modelo)


def config_llm() -> ConfigLLM:
    load_dotenv()
    return ConfigLLM(
        base_url=os.getenv("LLM_BASE_URL", "").strip(),
        api_key=os.getenv("LLM_API_KEY", "").strip(),
        modelo=os.getenv("LLM_MODEL", "").strip(),
    )


def razonamiento() -> dict:
    """Parámetro de razonamiento para `extra_body`, según LLM_REASONING.

    low (por defecto) | medium | high | off | auto. `reasoning` es propio de OpenRouter: con otro
    proveedor (p. ej. la API de Gemini compatible con OpenAI) usar `auto`, que no envía nada.
    """
    valor = (os.getenv("LLM_REASONING") or "low").strip().lower()
    if valor == "auto":
        return {}
    if valor == "off":
        return {"reasoning": {"enabled": False}}
    return {"reasoning": {"effort": valor}}


def crear_cliente(config: ConfigLLM | None = None, timeout: float = 60):
    """Crea el cliente de OpenRouter. Lanza `RuntimeError` si falta configuración."""
    from openai import OpenAI

    config = config or config_llm()
    if not config.completa:
        raise RuntimeError("Falta configurar LLM_BASE_URL, LLM_API_KEY y LLM_MODEL (ver .env.example).")
    return OpenAI(base_url=config.base_url, api_key=config.api_key, timeout=timeout, max_retries=1)
