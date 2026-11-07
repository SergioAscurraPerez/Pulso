"""Extrae las evaluaciones de uno o más sílabos PDF con el LLM, para revisarlas a mano (PUL-05).

Uso (desde la raíz del repo, con .env configurado):
    python scripts/extraer_silabo.py data/silabos/ciclo-07/ingenieria-de-software-ii-2026-I.pdf
    python scripts/extraer_silabo.py data/silabos/ciclo-07/*.pdf --json salida.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction.llm_parser import ErrorExtraccion, extraer_evaluaciones  # noqa: E402
from src.extraction.pdf_reader import leer_pdf  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="guardar todas las evaluaciones extraídas en este archivo")
    args = parser.parse_args()

    salida, fallos = [], 0
    for pdf in args.pdfs:
        inicio = time.perf_counter()
        try:
            r = extraer_evaluaciones(leer_pdf(pdf))
        except ErrorExtraccion as error:
            fallos += 1
            print(f"\n✗ {pdf.name}: {error}")
            continue
        print(f"\n✓ {pdf.name} → {r.curso} · {len(r.evaluaciones)} evaluaciones · pesos suman {r.suma_pesos} "
              f"· {r.intentos} intento(s) · {time.perf_counter() - inicio:.1f} s")
        for e in r.evaluaciones:
            print(f"   sem {e.semana or '-':>2}  {e.peso:6.2f}%  {e.tipo.value:20s} {e.nombre}")
        for a in r.advertencias:
            print(f"   ⚠ {a}")
        salida += [e.model_dump(mode="json") for e in r.evaluaciones]

    if args.json:
        args.json.write_text(json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nGuardado en {args.json}")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
