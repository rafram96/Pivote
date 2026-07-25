"""
Medición de tamaños de descarga InfoObras (punto 1 — riesgo de escala).

Dos fases, ambas contra el portal en vivo (datos públicos, solo lectura):

  FASE A (barata): por cada obra, inventaría los documentos y lee el
    Content-Length de cada uno con un GET en streaming SIN bajar el cuerpo.
    Así detecta los PDFs grandes (el de 48 MB que preocupaba) sin descargar
    gigas. Reporta por obra: nº docs, total, archivo máximo.

  FASE B (real, solo la obra más pesada): descarga completa con
    descargar_documentos_obra_por_hito y mide el tiempo de pared real,
    fallos y el ZIP resultante. Es la prueba de que la escala aguanta.

Uso:
    python tools/medir_descargas.py 83130 68513 138999 33900
    python tools/medir_descargas.py            # set por defecto (obras pesadas del demo)
"""
from __future__ import annotations

import shutil
import sys
import time
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests  # noqa: E402

from entregables.zip_infoobras import (  # noqa: E402
    DESCARGA, PAGINA,
    construir_zip_infoobras,
    descargar_documentos_obra_por_hito,
    inventariar_por_avance,
)

# Obras más pesadas por nº de valorizaciones en el demo 4816fbdf3bea.
DEFAULT = ["83130", "68513", "138999", "33900"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "Chrome/124 Safari/537.36")


def _docs_de(obra_id, sess):
    r = sess.get(PAGINA, params={"obraId": obra_id}, timeout=90)
    r.raise_for_status()
    inv = inventariar_por_avance(r.text)
    docs = []
    for av in inv["avances"]:
        docs += av["documentos"]
    docs += inv["obra"]["documentos"]
    return docs


def _size_de(it, sess):
    """Content-Length sin bajar el cuerpo (stream=True + close)."""
    ext = it["extension"]
    try:
        r = sess.get(DESCARGA, params={
            "filename": it["filename"], "name": it["nombre"],
            "contentType": "application/pdf" if ext == "pdf" else "application/octet-stream",
            "extension": "." + ext,
        }, timeout=90, stream=True)
        cl = r.headers.get("Content-Length")
        r.close()
        return int(cl) if cl and cl.isdigit() else None
    except requests.RequestException as e:
        return f"ERR {e.__class__.__name__}"


def _mb(n):
    return f"{n/1e6:.1f} MB" if isinstance(n, int) else str(n)


def main() -> int:
    obras = sys.argv[1:] or DEFAULT
    sess = requests.Session()
    sess.headers["User-Agent"] = UA

    print(f"FASE A · midiendo Content-Length de {len(obras)} obra(s) (sin descargar)\n")
    resumen = []
    max_global = (0, None, None)  # (size, obra, nombre)
    for oid in obras:
        try:
            docs = _docs_de(oid, sess)
        except Exception as e:  # noqa: BLE001
            print(f"  obra {oid}: ERROR inventario {e!r}")
            continue
        sizes = [(d["nombre"], _size_de(d, sess)) for d in docs]
        nums = [s for _, s in sizes if isinstance(s, int)]
        errs = [s for _, s in sizes if not isinstance(s, int)]
        total = sum(nums)
        mx = max(nums) if nums else 0
        resumen.append((oid, len(docs), total, mx))
        for nombre, s in sizes:
            if isinstance(s, int) and s > max_global[0]:
                max_global = (s, oid, nombre)
        print(f"  obra {oid:>8}: {len(docs):>3} doc(s) · total {_mb(total):>9} · "
              f"máx {_mb(mx):>9}" + (f" · {len(errs)} sin Content-Length" if errs else ""))

    print(f"\n  ARCHIVO MÁS GRANDE del barrido: {_mb(max_global[0])} "
          f"(obra {max_global[1]})")
    if not resumen:
        return 1

    # FASE B: descarga real de la obra más pesada por total
    pesada = max(resumen, key=lambda r: r[2])[0]
    print(f"\nFASE B · descarga REAL de la obra más pesada: {pesada}")
    trabajo = RAIZ / "tools" / f"_medicion_{pesada}"
    if trabajo.exists():
        shutil.rmtree(trabajo)
    dest = trabajo / "descarga"
    dest.mkdir(parents=True)

    t0 = time.monotonic()
    res = descargar_documentos_obra_por_hito(pesada, dest, session=sess)
    dt = time.monotonic() - t0
    print(f"  descargados={res['descargados']} fallidos={res['fallidos']} en {dt:.1f}s")

    espejo = {"_meta": {"concurso": "MEDICIÓN ESCALA", "postor": "—"},
              "profesionales": [{"n_prof": 1, "cargo": "OBRA PESADA",
                                 "experiencias": [{"n": 1, "proyecto": f"obra {pesada}", "cui": pesada}]}]}
    zip_path = trabajo / "sustentos.zip"
    construir_zip_infoobras(espejo, {(1, 1): dest}, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        vacios = sum(1 for i in infos if i.file_size == 0 and not i.filename.endswith("/"))
    print(f"  ZIP {zip_path.stat().st_size/1e6:.1f} MB · {len(infos)} entradas · vacíos={vacios}")
    sess.close()
    print(f"\n(carpeta de trabajo: {trabajo.relative_to(RAIZ)} — borrar tras revisar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
