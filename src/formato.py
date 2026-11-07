"""Formato de textos para mostrar, compartido por la app y la propuesta."""

from __future__ import annotations

_ROMANOS = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
_MENORES = {"de", "del", "la", "las", "el", "los", "y", "e", "en", "para", "por", "a", "o", "u", "con", "si"}


def nombre_curso(nombre: str) -> str:
    """Los sílabos traen el curso en MAYÚSCULAS: se muestra en formato título ("Ingenieria de Software II")."""
    if nombre != nombre.upper():
        return nombre
    palabras = []
    for i, palabra in enumerate(nombre.split()):
        if palabra in _ROMANOS:
            palabras.append(palabra)
        elif i and palabra.lower() in _MENORES:
            palabras.append(palabra.lower())
        else:
            palabras.append(palabra.capitalize())
    return " ".join(palabras)
