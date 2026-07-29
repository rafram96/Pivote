"""CLI de diagnóstico para el cliente reutilizable RENIPRESS.

Uso:
  python tools/renipress.py "CLINICA INTERNACIONAL"
  python tools/renipress.py 00008215
  python tools/renipress.py 20100054184 --todos
  python tools/renipress.py "CLINICA" --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from scraping.renipress import buscar_renipress  # noqa: E402


def _argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("termino", help="Nombre, razón social, código único o RUC")
    parser.add_argument(
        "--todos", action="store_true", help="Incluir establecimientos no activos"
    )
    parser.add_argument("--json", action="store_true", help="Emitir contrato JSON")
    parser.add_argument("--limite", type=int, default=50, help="Máximo de filas (1-500)")
    return parser.parse_args()


def main() -> int:
    args = _argumentos()
    resultado = buscar_renipress(
        args.termino, solo_activos=not args.todos, max_filas=args.limite
    )
    if args.json:
        print(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2))
    elif resultado.estado == "portal_no_disponible":
        print(f"RENIPRESS no respondió: {resultado.detalle_error}", file=sys.stderr)
    elif resultado.estado == "sin_resultados":
        print("Búsqueda válida sin resultados; esto no prueba inexistencia.")
    else:
        print(f"{resultado.total} resultado(s); ambiguo={resultado.ambiguo}")
        for fila in resultado.establecimientos:
            ubicacion = "/".join(
                v for v in (fila.distrito, fila.provincia, fila.departamento) if v
            )
            print(
                f"{fila.codigo_unico:>8}  {fila.estado or '-':10} "
                f"{ubicacion:34} {fila.nombre_razon_social}"
            )
    return {
        "encontrado": 0,
        "sin_resultados": 1,
        "portal_no_disponible": 3,
    }[resultado.estado]


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    raise SystemExit(main())
