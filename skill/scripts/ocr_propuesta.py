#!/usr/bin/env python3
"""
OCR reanudable (español) para PDFs escaneados grandes (cientos/miles de páginas).

Camino A del Paso 0 de la skill `analizar-licitacion-osce`. Saca el OCR del MODELO
(visión = caro, consume el límite de Claude) y lo hace LOCAL con Tesseract
(CPU = gratis). Produce un .txt por página `pNNNN.txt`, que es a la vez el índice
por folio: página física N -> pNNNN.txt. El mapa y los agentes por profesional
leen ese texto (barato) en vez de las imágenes.

Aprendizajes incorporados (del flujo manual del ingeniero):
- Tesseract con idioma 'spa' (descarga tessdata_fast si falta, en un TESSDATA_PREFIX
  escribible).
- OMP_THREAD_LIMIT=1 por proceso => evita la sobre-suscripción de hilos de
  Tesseract; paraleliza con un Pool = nº de CPUs.  <- el gran salto de velocidad.
- Idempotente y auto-limitado por tiempo: cada corrida procesa las páginas que
  falten hasta agotar un presupuesto de segundos, y al re-invocarse retoma donde
  quedó. Pensado para shells con timeout corto (~45 s) que NO conservan procesos
  de fondo entre llamadas.

Endurecimientos respecto al original:
- Si NO hay binario de tesseract (o falta pymupdf) en el entorno, imprime
  "NO_TESSERACT" / "NO_PYMUPDF" y sale con código 3: la skill debe caer al
  Camino B (OCR nativo de Claude por visión). No falla ruidoso ni pide instalar.
- Detección cross-platform del binario y del tessdata (Linux + Windows).
- Abre el PDF UNA vez por worker (initializer), no por página.

Uso:
  python3 ocr_propuesta.py "<ruta.pdf>" "<carpeta_salida>" [budget_seg] [dpi] [nprocs]
  # Llamar repetidamente hasta que imprima ALLDONE. Cada página -> <salida>/pNNNN.txt

Requisitos: pip install pymupdf ; binario tesseract-ocr instalado (con idioma spa).
"""
import os, sys, shutil, time, subprocess, urllib.request
from multiprocessing import Pool

PDF    = sys.argv[1] if len(sys.argv) > 1 else ""
OUT    = sys.argv[2] if len(sys.argv) > 2 else ""
BUDGET = float(sys.argv[3]) if len(sys.argv) > 3 else 33.0
DPI    = int(sys.argv[4]) if len(sys.argv) > 4 else 120     # 110-130 basta para nombres/fechas/folios
NPROC  = int(sys.argv[5]) if len(sys.argv) > 5 else (os.cpu_count() or 2)


def find_tesseract():
    """Ruta al binario de tesseract, o None si no está en el entorno."""
    cmd = shutil.which("tesseract")
    if cmd:
        return cmd
    for c in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(c):
            return c
    return None


def ensure_spa(tess):
    """Garantiza spa.traineddata accesible. Prefiere el tessdata propio de la
    instalación; si no, arma uno escribible y descarga spa (tessdata_fast)."""
    cands = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        cands.append(env)
    base = os.path.dirname(tess)
    cands += [os.path.join(base, "tessdata"),               # Windows: junto al .exe
              "/usr/share/tesseract-ocr/5/tessdata",
              "/usr/share/tesseract-ocr/4.00/tessdata",
              "/usr/share/tesseract-ocr/tessdata",
              "/usr/share/tessdata"]
    # ¿la instalación ya trae spa? entonces úsalo y no toques nada (offline-friendly).
    for d in cands:
        if d and os.path.exists(os.path.join(d, "spa.traineddata")):
            os.environ["TESSDATA_PREFIX"] = d
            return True
    # no estaba: arma un prefix escribible, copia lo que exista y baja spa
    prefix = os.path.join(os.path.dirname(os.path.abspath(OUT)) or ".", "_tessdata")
    os.makedirs(prefix, exist_ok=True)
    for d in cands:
        if d and os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".traineddata"):
                    dst = os.path.join(prefix, f)
                    if not os.path.exists(dst):
                        try:
                            shutil.copyfile(os.path.join(d, f), dst)
                        except Exception:
                            pass
            break
    spa = os.path.join(prefix, "spa.traineddata")
    if not os.path.exists(spa):
        for url in ("https://github.com/tesseract-ocr/tessdata_fast/raw/main/spa.traineddata",
                    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/spa.traineddata"):
            try:
                urllib.request.urlretrieve(url, spa)
                if os.path.getsize(spa) > 1_000_000:
                    break
            except Exception:
                pass
    os.environ["TESSDATA_PREFIX"] = prefix
    return os.path.exists(spa)


_DOC = None


def _init_worker(pdf_path):
    """Una apertura del PDF por proceso (no por página) + 1 hilo por Tesseract."""
    global _DOC
    os.environ["OMP_THREAD_LIMIT"] = "1"   # clave de velocidad
    import fitz
    _DOC = fitz.open(pdf_path)


def proc(args):
    i, out, dpi, tess = args
    import fitz
    png = os.path.join(out, f"_g{i}.png")
    try:
        zoom = dpi / 72.0
        _DOC[i].get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(png)   # compat. con PyMuPDF viejo y nuevo
        subprocess.run([tess, png, os.path.join(out, f"p{i + 1:04d}"),
                        "-l", "spa", "--psm", "6"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
    except Exception:
        pass
    finally:
        try:
            os.remove(png)
        except Exception:
            pass
    return i


def main():
    if not PDF or not OUT:
        print("USO: ocr_propuesta.py <pdf> <out> [budget_seg] [dpi] [nproc]")
        sys.exit(2)
    tess = find_tesseract()
    if not tess:
        print("NO_TESSERACT")        # -> la skill cae al Camino B (visión de Claude)
        sys.exit(3)
    try:
        import fitz
    except Exception:
        print("NO_PYMUPDF")          # -> idem Camino B
        sys.exit(3)
    os.makedirs(OUT, exist_ok=True)
    ensure_spa(tess)
    N = fitz.open(PDF).page_count
    done = set()
    for f in os.listdir(OUT):
        if f.startswith("p") and f.endswith(".txt") and os.path.getsize(os.path.join(OUT, f)) > 3:
            try:
                done.add(int(f[1:5]))
            except ValueError:
                pass
    todo = [i for i in range(N) if (i + 1) not in done]
    if not todo:
        print("ALLDONE")
        return
    t0 = time.time()
    with Pool(NPROC, initializer=_init_worker, initargs=(PDF,)) as p:
        for _ in p.imap_unordered(proc, ((i, OUT, DPI, tess) for i in todo)):
            if time.time() - t0 > BUDGET:
                p.terminate()
                break
    nd = len([f for f in os.listdir(OUT) if f.startswith("p") and f.endswith(".txt")])
    print(f"progress: {nd}/{N}")


if __name__ == "__main__":
    main()
