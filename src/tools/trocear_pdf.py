"""Trocea un PDF grande en sub-PDFs < 100 MB (límite del `Read` del harness).

Los escaneos de propuesta llegan a cientos de MB y el `Read` falla con
"exceeds maximum allowed size". Cada subagente debe recibir un sub-PDF que sí
abra, y reportar **páginas locales** con su offset (folio = página local + offset).

No re-rasteriza: copia las páginas tal cual (`fitz.Document.insert_pdf`), así el
folio impreso se preserva. Si una parte sigue pasándose del límite, la subdivide
sola hasta que entre.

Uso:
  venv/Scripts/python.exe src/tools/trocear_pdf.py <entrada.pdf> <dir_salida> [--paginas 150] [--prefijo tecnica]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz

LIMITE_BYTES = 100 * 1024 * 1024
MARGEN = 0.92  # apuntar a 92 MB para no quedar al filo del límite


def _guardar_rango(doc: fitz.Document, ini: int, fin: int, destino: Path) -> int:
    """Guarda las páginas [ini, fin] (0-based, inclusivas) y devuelve el tamaño."""
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=ini, to_page=fin)
    sub.save(destino, garbage=4, deflate=True)
    sub.close()
    return destino.stat().st_size


def trocear(ruta: Path, dir_salida: Path, paginas_por_parte: int, prefijo: str) -> list[dict]:
    doc = fitz.open(ruta)
    dir_salida.mkdir(parents=True, exist_ok=True)
    total = doc.page_count

    # Rangos iniciales, 0-based inclusivos.
    rangos = [(i, min(i + paginas_por_parte - 1, total - 1)) for i in range(0, total, paginas_por_parte)]

    partes: list[dict] = []
    pendientes = list(rangos)
    while pendientes:
        ini, fin = pendientes.pop(0)
        temporal = dir_salida / f".tmp_{ini + 1}_{fin + 1}.pdf"
        tam = _guardar_rango(doc, ini, fin, temporal)
        if tam > LIMITE_BYTES * MARGEN and fin > ini:
            # Se pasó: partir a la mitad y reintentar ambas mitades.
            temporal.unlink()
            medio = (ini + fin) // 2
            pendientes.insert(0, (medio + 1, fin))
            pendientes.insert(0, (ini, medio))
            continue
        nombre = f"{prefijo}_p{ini + 1:03d}-{fin + 1:03d}.pdf"
        destino = dir_salida / nombre
        temporal.replace(destino)
        partes.append(
            {
                "archivo": nombre,
                "pag_ini": ini + 1,
                "pag_fin": fin + 1,
                "paginas": fin - ini + 1,
                "offset": ini,  # folio = página local + offset (cuando folio = página global)
                "mb": round(tam / 1024 / 1024, 1),
            }
        )
    doc.close()
    partes.sort(key=lambda p: p["pag_ini"])
    return partes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("dir_salida")
    ap.add_argument("--paginas", type=int, default=150)
    ap.add_argument("--prefijo", default="parte")
    args = ap.parse_args()

    partes = trocear(Path(args.entrada), Path(args.dir_salida), args.paginas, args.prefijo)
    print(f"{len(partes)} partes:")
    print(f"{'archivo':<34} {'pags':>10} {'offset':>7} {'MB':>7}")
    for p in partes:
        rango = f"{p['pag_ini']}-{p['pag_fin']}"
        print(f"{p['archivo']:<34} {rango:>10} {p['offset']:>7} {p['mb']:>7}")
    excedidas = [p for p in partes if p["mb"] > 100]
    if excedidas:
        print(f"\n⚠ {len(excedidas)} parte(s) siguen > 100 MB (página individual muy pesada)")


if __name__ == "__main__":
    main()
