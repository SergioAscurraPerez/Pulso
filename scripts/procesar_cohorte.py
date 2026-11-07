"""Genera data/cohorte.json a partir de una carpeta de sílabos PDF (PUL-07).

Uso (desde la raíz del repo, con .env configurado si hay PDFs sin caché):
    python scripts/procesar_cohorte.py data/silabos/ciclo-07 --ciclo 2026-I --inicio 2026-03-02
    python scripts/procesar_cohorte.py data/silabos/ciclo-07 --ciclo 2026-I --inicio 2026-03-02 --forzar

Las extracciones quedan en data/cache/extraccion/ (una por PDF): commitéalas junto con
data/cohorte.json para que la demo no dependa del LLM.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.batch import SALIDA_POR_DEFECTO, guardar_cohorte, procesar_cohorte  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("carpeta", type=Path, help="carpeta con los PDFs de una cohorte")
    parser.add_argument("--ciclo", required=True, help="p. ej. 2026-I")
    parser.add_argument("--inicio", required=True, type=date.fromisoformat, help="lunes de la semana 1 (YYYY-MM-DD)")
    parser.add_argument("--nombre", help="nombre de la cohorte (por defecto, el de la carpeta)")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)
    parser.add_argument("--forzar", action="store_true", help="volver a extraer aunque haya caché")
    args = parser.parse_args()

    nombre = args.nombre or f"Ingeniería de Computación y Sistemas – {args.carpeta.name} ({args.ciclo})"

    def mostrar(r):
        if r.error:
            print(f"✗ {r.archivo}: {r.error}")
        else:
            origen = "caché" if r.desde_cache else "LLM"
            print(f"✓ {r.archivo} → {r.curso} · {r.evaluaciones} evaluaciones ({origen})")

    lote = procesar_cohorte(args.carpeta, nombre=nombre, ciclo=args.ciclo, fecha_inicio=args.inicio, forzar=args.forzar, al_procesar=mostrar)
    for a in lote.advertencias:
        print(f"  ⚠ {a}")
    ruta = guardar_cohorte(lote.cohorte, args.salida)
    c = lote.cohorte
    print(f"\n{ruta}: {len(c.evaluaciones)} evaluaciones de {len(c.cursos)} cursos")
    if lote.fallidos:
        print(f"{len(lote.fallidos)} sílabo(s) fallaron; el resto se guardó.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
