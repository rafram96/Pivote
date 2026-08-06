"""
Buscador de inversiones del MEF desde la consola — soporte y diagnóstico.

Misma búsqueda que sirve el endpoint `GET /api/pivote/mef/buscar` (comparten
`resolucion/busqueda_mef.py`), pero sin levantar el backend. Sirve para
comprobar a mano que la base local está instalada y responde, y para buscar un
CUI cuando uno está en el servidor sin panel a mano.

Todo es local: no toca internet ni el portal de InfoObras.

Uso (desde backend/):
    python -m scripts.buscar_mef "hospital abancay"
    python -m scripts.buscar_mef "puesto de salud chinchinga" --dpto huanuco
    python -m scripts.buscar_mef 2376130
    python -m scripts.buscar_mef "hospital" --entidad "gobierno regional" --limite 5
    python -m scripts.buscar_mef "hospital abancay" --json     # salida cruda

Ojo: la PRIMERA búsqueda de cada corrida carga el índice en memoria (medio
millón de inversiones) y tarda decenas de segundos; el endpoint lo paga una vez
por proceso, este CLI una vez por invocación.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolucion.busqueda_mef import (  # noqa: E402
    LIMITE_DEFECTO, ConsultaInvalida, buscar,
)


def _imprimir_legible(r: dict) -> None:
    if r["base_mef_no_disponible"]:
        print(r["aviso"])
        return

    filtros = "  ".join(f"{k}={v}" for k, v in r["filtros"].items())
    edad = r["edad_dias"]
    cabecera = f'Búsqueda: "{r["q"]}"'
    if filtros:
        cabecera += f"   filtros: {filtros}"
    if edad is not None:
        cabecera += f"   (base del MEF actualizada hace {edad} día(s))"
    print(cabecera)
    print("=" * 78)

    if not r["resultados"]:
        print(r["aviso"] or "Sin coincidencias. Prueba con menos palabras o sin filtros.")
        return

    for i, x in enumerate(r["resultados"], 1):
        codigo = x["cui"] or (f'SNIP {x["snip"]}' if x["snip"] else "sin código")
        score = f'  ·  coincidencia {x["score"]:.0f}%' if x["score"] is not None else ""
        print(f'{i:2}. CUI {codigo}{score}')
        print(f'    {x["nombre"]}')
        detalle = [d for d in (x["ubicacion"], x["entidad"], x["situacion"]) if d]
        if detalle:
            print("    " + "  ·  ".join(detalle))
    print("=" * 78)
    modo = "código exacto" if r["coincidencia"] == "codigo" else "nombre"
    print(f'{r["total"]} resultado(s) por {modo}  ·  {r["ms"]:.0f} ms de búsqueda '
          f'(sin contar la carga del índice).')


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="python -m scripts.buscar_mef",
        description="Busca inversiones (CUI/SNIP) en la base local del MEF.")
    p.add_argument("q", nargs="+", help="nombre de la obra, o un CUI/SNIP")
    p.add_argument("--dpto", default="", help="filtra por departamento")
    p.add_argument("--prov", default="", help="filtra por provincia")
    p.add_argument("--dist", default="", help="filtra por distrito")
    p.add_argument("--entidad", default="", help="filtra por entidad (parcial)")
    p.add_argument("--limite", type=int, default=LIMITE_DEFECTO,
                   help=f"cuántos resultados mostrar (1..50, def {LIMITE_DEFECTO})")
    p.add_argument("--json", action="store_true", dest="como_json",
                   help="imprime la respuesta cruda del contrato")
    a = p.parse_args(argv)

    try:
        r = buscar(" ".join(a.q), dpto=a.dpto, prov=a.prov, dist=a.dist,
                   entidad=a.entidad, limite=a.limite)
    except ConsultaInvalida as e:
        print(f"No se puede buscar eso: {e}", file=sys.stderr)
        return 2

    if a.como_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        _imprimir_legible(r)
    # Sin base instalada el resultado no es concluyente → código de salida != 0
    return 1 if r["base_mef_no_disponible"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
