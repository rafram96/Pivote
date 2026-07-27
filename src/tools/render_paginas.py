"""Renderiza las páginas de un PDF a JPEG para leerlas con visión (Camino B).

En esta laptop el `Read` del harness NO rasteriza PDFs (falta poppler en su PATH) y
NO hay Tesseract, así que para leer un escaneo hay que pre-renderizar a imagen.

Renderiza la **página completa** con PyMuPDF (no `pdfimages`): así no se pierden las
páginas que traen 2 capas (JPEG del escaneo + stencil CCITT con el formulario
impreso), que al extraer solo la imagen embebida salían **en blanco** — el bug que
apareció en HuachoColpa.

Avisa de las páginas que quedan casi blancas (posible página vacía real, o un
render que falló) para revisarlas a mano.

Uso:
  venv/Scripts/python.exe src/tools/render_paginas.py <entrada.pdf> <dir_salida> [--dpi 150] [--desde 1] [--hasta 0]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import fitz

UMBRAL_BLANCO = 0.998  # fracción de píxeles claros para considerar la página vacía


def _fraccion_clara(pix: fitz.Pixmap) -> float:
    """Fracción de bytes de muestra por encima de 245 (aprox. blanco)."""
    datos = pix.samples
    if not datos:
        return 1.0
    paso = max(1, len(datos) // 20000)  # muestreo, no hace falta contar todo
    muestra = datos[::paso]
    claros = sum(1 for b in muestra if b > 245)
    return claros / len(muestra)


def renderizar(ruta: Path, dir_salida: Path, dpi: int, desde: int, hasta: int) -> dict:
    doc = fitz.open(ruta)
    dir_salida.mkdir(parents=True, exist_ok=True)
    ultima = hasta if hasta else doc.page_count
    ultima = min(ultima, doc.page_count)

    casi_blancas: list[int] = []
    generadas = 0
    for n in range(desde, ultima + 1):
        pagina = doc[n - 1]
        pix = pagina.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        destino = dir_salida / f"p{n:04d}.jpg"
        pix.save(destino, jpg_quality=72)
        if _fraccion_clara(pix) >= UMBRAL_BLANCO:
            casi_blancas.append(n)
        generadas += 1
    doc.close()
    return {"generadas": generadas, "casi_blancas": casi_blancas}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada")
    ap.add_argument("dir_salida")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--desde", type=int, default=1)
    ap.add_argument("--hasta", type=int, default=0)
    args = ap.parse_args()

    r = renderizar(Path(args.entrada), Path(args.dir_salida), args.dpi, args.desde, args.hasta)
    mb = sum(f.stat().st_size for f in Path(args.dir_salida).glob("*.jpg")) / 1024 / 1024
    # La consola de Windows es cp1252: nada de flechas ni acentos en el print.
    print(f"{r['generadas']} paginas -> {args.dir_salida} ({mb:.0f} MB, {args.dpi} dpi)")
    if r["casi_blancas"]:
        print(f"casi blancas ({len(r['casi_blancas'])}): {r['casi_blancas']}")


if __name__ == "__main__":
    main()
