#!/usr/bin/env python3
"""OCR local, reanudable y auditable para propuestas escaneadas grandes.

La ruta principal renderiza cada página con PyMuPDF. Si PyMuPDF no está
disponible, usa Poppler (`pdfimages` + `pdfinfo`) y concatena todas las imágenes
útiles de la página. Las máscaras PPM y los sellos diminutos no pueden pisar el
texto principal. Tesseract usa PSM 1 para detectar orientación automáticamente.

Uso:
  python ocr_propuesta.py <pdf> <salida> [budget_seg] [dpi] [nprocs]
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from multiprocessing import Pool
from pathlib import Path


MIN_CHARS = int(os.environ.get("PIVOTE_OCR_MIN_CHARS", "40"))
MIN_IMAGE_BYTES = 2_048

_DOC = None
_PDF = ""
_OUT = ""
_DPI = 120
_TESS = ""
_MODO = "fitz"
_PDFIMAGES = None
_PDFTOPPM = None


def encontrar_binario(nombre: str, candidatos: tuple[str, ...] = ()) -> str | None:
    cmd = shutil.which(nombre)
    if cmd:
        return cmd
    return next((ruta for ruta in candidatos if os.path.exists(ruta)), None)


def find_tesseract() -> str | None:
    return encontrar_binario(
        "tesseract",
        (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
         r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    )


def ensure_tessdata(tess: str, out: str) -> bool:
    """Garantiza español + OSD, necesarios para `--psm 1`."""
    cands: list[str] = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        cands.append(env)
    base = os.path.dirname(tess)
    cands += [
        os.path.join(base, "tessdata"),
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tesseract-ocr/tessdata",
        "/usr/share/tessdata",
    ]
    requeridos = ("spa.traineddata", "osd.traineddata")
    for directorio in cands:
        if directorio and all(os.path.isfile(os.path.join(directorio, f)) for f in requeridos):
            os.environ["TESSDATA_PREFIX"] = directorio
            return True

    prefix = os.path.join(os.path.dirname(os.path.abspath(out)) or ".", "_tessdata")
    os.makedirs(prefix, exist_ok=True)
    for directorio in cands:
        if not directorio or not os.path.isdir(directorio):
            continue
        for nombre in os.listdir(directorio):
            if not nombre.endswith(".traineddata"):
                continue
            destino = os.path.join(prefix, nombre)
            if not os.path.exists(destino):
                try:
                    shutil.copyfile(os.path.join(directorio, nombre), destino)
                except OSError:
                    pass
        break

    for modelo in ("spa", "osd"):
        destino = os.path.join(prefix, f"{modelo}.traineddata")
        if os.path.isfile(destino) and os.path.getsize(destino) > 1_000_000:
            continue
        for url in (
            f"https://github.com/tesseract-ocr/tessdata_fast/raw/main/{modelo}.traineddata",
            f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{modelo}.traineddata",
        ):
            try:
                urllib.request.urlretrieve(url, destino)
                if os.path.getsize(destino) > 1_000_000:
                    break
            except (OSError, urllib.error.URLError):
                pass
    os.environ["TESSDATA_PREFIX"] = prefix
    return all(os.path.isfile(os.path.join(prefix, f)) for f in requeridos)


def comando_tesseract(tess: str, imagen: str) -> list[str]:
    """PSM 1 = segmentación automática con detección de orientación (OSD)."""
    return [tess, imagen, "stdout", "-l", "spa", "--psm", "1"]


def imagenes_utiles(rutas: list[str], minimo: int = MIN_IMAGE_BYTES) -> list[str]:
    """Conserva imágenes OCR-eables; descarta máscaras PPM y sellos/logos chicos."""
    utiles = []
    for ruta in sorted(rutas):
        if Path(ruta).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            if os.path.getsize(ruta) >= minimo:
                utiles.append(ruta)
        except OSError:
            continue
    return utiles


def paginas_bajo_umbral(out: str, total: int, minimo: int = MIN_CHARS) -> list[int]:
    bajas = []
    for pagina in range(1, total + 1):
        ruta = os.path.join(out, f"p{pagina:04d}.txt")
        try:
            texto = Path(ruta).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue  # todavía no procesada; no confundir con OCR vacío
        caracteres = len(re.sub(r"\s+", "", texto))
        if caracteres < minimo:
            bajas.append(pagina)
    return bajas


def _paginas_pdfinfo(pdf: str, pdfinfo: str) -> int:
    r = subprocess.run(
        [pdfinfo, pdf], capture_output=True, text=True, timeout=30, check=False,
    )
    m = re.search(r"^Pages:\s*(\d+)\s*$", r.stdout, flags=re.MULTILINE | re.IGNORECASE)
    if not m:
        raise RuntimeError("pdfinfo no devolvió el número de páginas")
    return int(m.group(1))


def _init_worker(pdf: str, out: str, dpi: int, tess: str, modo: str,
                 pdfimages: str | None, pdftoppm: str | None) -> None:
    global _DOC, _PDF, _OUT, _DPI, _TESS, _MODO, _PDFIMAGES, _PDFTOPPM
    os.environ["OMP_THREAD_LIMIT"] = "1"
    _PDF, _OUT, _DPI, _TESS, _MODO = pdf, out, dpi, tess, modo
    _PDFIMAGES, _PDFTOPPM = pdfimages, pdftoppm
    if modo == "fitz":
        import fitz
        _DOC = fitz.open(pdf)


def _imagenes_fitz(indice: int) -> tuple[list[str], list[str]]:
    import fitz
    ruta = os.path.join(_OUT, f"._ocr_{indice + 1:04d}_{os.getpid()}.png")
    zoom = _DPI / 72.0
    _DOC[indice].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(ruta)
    return [ruta], [ruta]


def _imagenes_poppler(indice: int) -> tuple[list[str], list[str]]:
    pagina = indice + 1
    prefijo = os.path.join(_OUT, f"._ocr_{pagina:04d}_{os.getpid()}")
    subprocess.run(
        [_PDFIMAGES, "-f", str(pagina), "-l", str(pagina), "-j", "-p", _PDF, prefijo],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False,
    )
    generadas = glob.glob(prefijo + "-*")
    utiles = imagenes_utiles(generadas)
    if not utiles and _PDFTOPPM:
        render = prefijo + "-render"
        subprocess.run(
            [_PDFTOPPM, "-f", str(pagina), "-l", str(pagina), "-r", str(_DPI),
             "-png", "-singlefile", _PDF, render],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False,
        )
        generadas.extend(glob.glob(render + "*"))
        utiles = imagenes_utiles(generadas, minimo=1)
    return utiles, generadas


def _ocr_imagen(ruta: str) -> str:
    r = subprocess.run(
        comando_tesseract(_TESS, ruta), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90, check=False,
    )
    return r.stdout.strip()


def proc(indice: int) -> int:
    generadas: list[str] = []
    destino = os.path.join(_OUT, f"p{indice + 1:04d}.txt")
    temporal = destino + f".{os.getpid()}.tmp"
    try:
        imagenes, generadas = (
            _imagenes_fitz(indice) if _MODO == "fitz" else _imagenes_poppler(indice)
        )
        textos = [texto for texto in (_ocr_imagen(img) for img in imagenes) if texto]
        Path(temporal).write_text("\n\n".join(textos).strip() + ("\n" if textos else ""), encoding="utf-8")
        os.replace(temporal, destino)
    except Exception:
        # Publicar vacío evita un bucle infinito en reanudaciones. El resumen lo
        # lista como página bajo umbral para revisión por visión.
        try:
            Path(temporal).write_text("", encoding="utf-8")
            os.replace(temporal, destino)
        except OSError:
            pass
    finally:
        for ruta in generadas:
            try:
                os.remove(ruta)
            except OSError:
                pass
        try:
            os.remove(temporal)
        except OSError:
            pass
    return indice


def _imprimir_estado(out: str, total: int) -> None:
    hechas = sum(os.path.isfile(os.path.join(out, f"p{i:04d}.txt")) for i in range(1, total + 1))
    bajas = paginas_bajo_umbral(out, total)
    detalle = ",".join(f"p{i:04d}" for i in bajas[:50])
    sufijo = f" · bajo_umbral={len(bajas)}" + (f" [{detalle}]" if detalle else "")
    print(("ALLDONE" if hechas == total else f"progress: {hechas}/{total}") + sufijo)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("USO: ocr_propuesta.py <pdf> <out> [budget_seg] [dpi] [nproc]")
        return 2
    pdf, out = args[0], args[1]
    budget = float(args[2]) if len(args) > 2 else 33.0
    dpi = int(args[3]) if len(args) > 3 else 120
    nproc = int(args[4]) if len(args) > 4 else (os.cpu_count() or 2)

    tess = find_tesseract()
    if not tess:
        print("NO_TESSERACT")
        return 3
    os.makedirs(out, exist_ok=True)
    if not ensure_tessdata(tess, out):
        print("NO_TESSDATA")
        return 3

    try:
        import fitz
        total, modo = fitz.open(pdf).page_count, "fitz"
        pdfimages = pdftoppm = None
    except ImportError:
        pdfimages = encontrar_binario("pdfimages")
        pdfinfo = encontrar_binario("pdfinfo")
        pdftoppm = encontrar_binario("pdftoppm")
        if not pdfimages or not pdfinfo:
            print("NO_RENDERER")
            return 3
        try:
            total = _paginas_pdfinfo(pdf, pdfinfo)
        except (OSError, RuntimeError, subprocess.SubprocessError):
            print("NO_RENDERER")
            return 3
        modo = "pdfimages"

    hechas = {i for i in range(1, total + 1) if os.path.isfile(os.path.join(out, f"p{i:04d}.txt"))}
    pendientes = [i for i in range(total) if i + 1 not in hechas]
    if not pendientes:
        _imprimir_estado(out, total)
        return 0

    t0 = time.time()
    with Pool(
        nproc, initializer=_init_worker,
        initargs=(pdf, out, dpi, tess, modo, pdfimages, pdftoppm),
    ) as pool:
        for _ in pool.imap_unordered(proc, pendientes):
            if time.time() - t0 > budget:
                pool.terminate()
                break
    _imprimir_estado(out, total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
