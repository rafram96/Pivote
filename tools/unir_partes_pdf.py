#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unir_partes_pdf.py — Une las partes de un expediente OSCE en SOLO DOS PDFs
(bases + propuesta), para que la skill `analizar-licitacion-osce` reciba
siempre el par `bases.pdf` + `propuesta.pdf` con folios continuos.

Por qué: el SEACE entrega la propuesta partida en varios archivos (la técnica
en PARTE 1..N por el límite de tamaño + la económica aparte). La skill espera
una sola propuesta. Unir respeta la foliación (pdfunite solo concatena páginas,
no re-numera), así el folio impreso sigue ≈ al número de página del PDF unido.

Convención de nombres (como los descarga el SEACE):
    00.xx … → BASES      → se unen en  bases.pdf      (bases integradas + TDR)
    01.xx … → PROPUESTA  → se unen en  propuesta.pdf  (técnica PARTE 1..N + económica)
Si no hay prefijo numérico, cae a palabras clave del nombre (BASES/TDR vs
PROPUESTA/TÉCNICA/ECONÓMICA).

Uso:
    python tools/unir_partes_pdf.py "<carpeta>" [--salida "<carpeta_salida>"] [--dry-run]
    python tools/unir_partes_pdf.py "C:\\Users\\Holbi\\Documents\\Freelance\\proyectos\\InfoObras\\Pivote\\fixtures\\vitarte"

Salida por defecto: <carpeta>/_unido/{bases.pdf,propuesta.pdf}
Requiere: poppler en el PATH  (pdfunite, pdfinfo).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

# --- clasificación de archivos -------------------------------------------------

RE_PREFIJO = re.compile(r"^\s*(\d{1,2})[._]")        # "00.01 ...", "1.2 ..."
KEYS_BASES = ("bases", "termino", "tdr", "requerimiento")
KEYS_PROP = ("propuesta", "tecnica", "técnica", "economica", "económica", "oferta")


def clave_natural(nombre):
    """Orden natural: '01.2' antes que '01.10'."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", nombre)]


def clasificar(nombre):
    """Devuelve 'bases' | 'propuesta' | None."""
    m = RE_PREFIJO.match(nombre)
    if m:
        mayor = int(m.group(1))
        if mayor == 0:
            return "bases"
        if mayor == 1:
            return "propuesta"
        # Otros prefijos (02, 03…): se deciden por palabra clave abajo.
    bajo = nombre.lower()
    if any(k in bajo for k in KEYS_BASES):
        return "bases"
    if any(k in bajo for k in KEYS_PROP):
        return "propuesta"
    return None


# --- utilidades poppler --------------------------------------------------------

def requiere(binario):
    ruta = shutil.which(binario)
    if not ruta:
        sys.exit(f"ERROR: falta '{binario}' en el PATH (instala poppler-utils).")
    return ruta


def n_paginas(pdf):
    try:
        out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
        m = re.search(r"Pages:\s+(\d+)", out.stdout)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def mb(path):
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


def unir(archivos, salida):
    """pdfunite in1 in2 ... salida (sin shell: maneja espacios en los nombres)."""
    if len(archivos) == 1:
        shutil.copy2(archivos[0], salida)          # una sola parte → copia directa
        return True, "copiado (1 parte)"
    r = subprocess.run(["pdfunite", *archivos, salida],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "pdfunite falló").strip()
    return True, "unido"


# --- main ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Une las partes OSCE en bases.pdf + propuesta.pdf")
    ap.add_argument("carpeta", help="Carpeta con las partes (PDFs 00.* y 01.*)")
    ap.add_argument("--salida", help="Carpeta de salida (def: <carpeta>/_unido)")
    ap.add_argument("--dry-run", action="store_true", help="Solo muestra el agrupamiento, no une")
    args = ap.parse_args()

    carpeta = os.path.abspath(args.carpeta)
    if not os.path.isdir(carpeta):
        sys.exit(f"ERROR: no existe la carpeta: {carpeta}")
    requiere("pdfunite")
    requiere("pdfinfo")

    pdfs = [f for f in os.listdir(carpeta)
            if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(carpeta, f))]
    grupos = {"bases": [], "propuesta": [], "sin_clasificar": []}
    for f in pdfs:
        grupos[clasificar(f) or "sin_clasificar"].append(f)
    for g in grupos.values():
        g.sort(key=clave_natural)

    print(f"Carpeta: {carpeta}")
    for g in ("bases", "propuesta", "sin_clasificar"):
        if not grupos[g]:
            continue
        print(f"\n[{g}]  ({len(grupos[g])} archivo(s))")
        for f in grupos[g]:
            print(f"   {f}  ({mb(os.path.join(carpeta, f)):,.1f} MB)")

    if grupos["sin_clasificar"]:
        print("\n⚠ Sin clasificar (renómbralos con prefijo 00./01. o revisa): "
              + ", ".join(grupos["sin_clasificar"]))
    if not grupos["bases"] or not grupos["propuesta"]:
        sys.exit("\nERROR: falta el grupo de bases o el de propuesta; no hay nada que unir.")

    salida = os.path.abspath(args.salida) if args.salida else os.path.join(carpeta, "_unido")
    plan = [("bases.pdf", grupos["bases"]), ("propuesta.pdf", grupos["propuesta"])]
    print(f"\nSalida: {salida}")
    for nombre, _ in plan:
        print(f"   → {nombre}")

    if args.dry_run:
        print("\n(dry-run: no se unió nada)")
        return

    os.makedirs(salida, exist_ok=True)
    ok = True
    for nombre, archivos in plan:
        rutas = [os.path.join(carpeta, f) for f in archivos]
        destino = os.path.join(salida, nombre)
        print(f"\nUniendo {nombre} ({len(rutas)} parte(s))…", flush=True)
        exito, msg = unir(rutas, destino)
        if not exito:
            ok = False
            print(f"   ✗ {nombre}: {msg}")
            continue
        print(f"   ✓ {nombre}: {n_paginas(destino)} páginas · {mb(destino):,.1f} MB · {msg}")

    print("\n== LISTO ==" if ok else "\n== TERMINÓ CON ERRORES ==")
    print(f"La skill puede analizar:\n  bases:     {os.path.join(salida, 'bases.pdf')}"
          f"\n  propuesta: {os.path.join(salida, 'propuesta.pdf')}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
