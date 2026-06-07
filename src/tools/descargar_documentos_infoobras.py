"""
Descarga de DOCUMENTOS (no imágenes) de una obra en InfoObras.

Investiga/automatiza el TODO de `docs/descarga_infoobras_experiencias.md`:
descubrir los endpoints de descarga de binarios de InfoObras y bajar SOLO los
documentos (actas, expediente, cronograma, ampliaciones, valorizaciones), NO las
fotos de avance físico — aunque algunas fotos puedan venir como PDF.

─────────────────────────────────────────────────────────────────────────────
CÓMO FUNCIONA INFOOBRAS (descubierto scrapeando obraId=72056)
─────────────────────────────────────────────────────────────────────────────
La página `Mapa/DatosEjecucion?obraId=N` trae TODO el inventario de archivos
embebido inline (no hace falta AJAX extra para los avances):

1. `var lAvances = [...]` inline en el HTML. Cada avance tiene 2 listas:
     - `lImgValorizacion`  → DOCUMENTOS  (EsFisico=0, carpeta `Doc/`,  .pdf)
     - `lImgFisico`        → IMÁGENES    (EsFisico=1, carpeta `Img/`,  .jpg/.png)
2. Botones estáticos con `data-download-url=...` en el body → documentos sueltos
   de la obra (expediente, calendario/cronograma, ampliaciones, adenda,
   designación, aprobación, sustento).

Todo se descarga por el MISMO endpoint:
    GET /InfobrasWeb/Mapa/DownloadFile
        ?filename=<UrlImg>           p.ej. Doc/documento20190129080229.pdf
        &name=<nombreArchivo>
        &contentType=application/pdf
        &extension=.pdf

DISTINCIÓN DOCUMENTO vs IMAGEN (lo que pidió el cliente):
  El criterio ROBUSTO NO es la extensión (una foto podría venir como pdf), sino:
    • el campo `EsFisico` (0=documento, 1=imagen), o equivalentemente
    • la lista de origen (`lImgValorizacion` vs `lImgFisico`), o
    • el prefijo de carpeta del `UrlImg` (`Doc/`,`expediente/`,… vs `Img/`).
  Este script usa ese criterio, así que una imagen-en-PDF queda EXCLUIDA igual.

Uso (datos públicos; sólo lectura/descarga):
    python src/tools/descargar_documentos_infoobras.py --obra-id 72056
    python src/tools/descargar_documentos_infoobras.py --obra-id 72056 --salida ./mis_docs
    python src/tools/descargar_documentos_infoobras.py --obra-id 72056 --solo-inventario
    python src/tools/descargar_documentos_infoobras.py --obra-id 72056 --incluir-imagenes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, parse_qs, urlsplit

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "https://infobras.contraloria.gob.pe/InfobrasWeb"
PAGINA = BASE + "/Mapa/DatosEjecucion"
DESCARGA = BASE + "/Mapa/DownloadFile"

# ─────────────────────────────────────────────────────────────────────────────
# MAPA DE SECCIONES de InfoObras (la SECCIÓN define si es documento o imagen,
# NO el contenido del archivo). El prefijo de carpeta del `UrlImg`/`filename`
# es el marcador de sección que usa el portal. Verificado en obraId=72056:
#   • cada avance trae 2 sub-secciones rotuladas: "Documento(s) adjuntos"
#     (carpeta Doc/, EsFisico=0) vs "Imágenes adjuntas" (carpeta Img/, EsFisico=1).
#   • botones del cuerpo: Cronograma→expediente/+calendario/, Modificaciones
#     en plazo→ampliaciones/.
# tipo: "documento" = legible/parseable · "imagen" = evidencia fotográfica.
# ─────────────────────────────────────────────────────────────────────────────
SECCIONES: dict[str, tuple[str, str]] = {
    # carpeta              (nombre de sección visible,                 tipo)
    "doc":           ("Documentos adjuntos del avance (valorizaciones)", "documento"),
    "expediente":    ("Expediente técnico",                              "documento"),
    "calendario":    ("Cronograma",                                      "documento"),
    "ampliaciones":  ("Modificaciones en plazo / Ampliaciones",          "documento"),
    "adenda":        ("Adendas",                                         "documento"),
    "designacion":   ("Designación de supervisor / residente",           "documento"),
    "aprobacion":    ("Documento de aprobación",                         "documento"),
    "sustento":      ("Documento sustento",                              "documento"),
    "transferencia": ("Transferencia financiera",                        "documento"),
    "entrega":       ("Entrega de terreno",                              "documento"),
    # Secciones de IMÁGENES / EVIDENCIA fotográfica (no son documentos a leer):
    "img":           ("Imágenes adjuntas del avance (evidencia física)", "imagen"),
    "imagen":        ("Galería de imágenes / Imágenes aéreas",           "imagen"),
}
EXT_IMAGEN = ("jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "es-PE,es;q=0.9",
    })
    return s


def _seccion(url_img: str, es_fisico: int | None) -> tuple[str, str]:
    """Devuelve (nombre_seccion, tipo) según la SECCIÓN de origen.

    Prioridad: carpeta declarada → EsFisico → extensión (último recurso).
    """
    carpeta = url_img.split("/", 1)[0].strip().lower() if "/" in url_img else ""
    if carpeta in SECCIONES:
        return SECCIONES[carpeta]
    if es_fisico == 1:
        return SECCIONES["img"]
    if es_fisico == 0:
        return SECCIONES["doc"]
    # carpeta desconocida y sin EsFisico: clasificar por extensión, conservando el
    # nombre de carpeta como sección para no perder trazabilidad.
    ext = url_img.lower().rsplit(".", 1)[-1]
    tipo = "imagen" if ext in EXT_IMAGEN else "documento"
    return (carpeta or "(sin sección)", tipo)


def inventariar(html: str) -> dict[str, list[dict[str, Any]]]:
    """Extrae el inventario de archivos (documentos + imágenes) del HTML."""
    documentos: list[dict[str, Any]] = []
    imagenes: list[dict[str, Any]] = []
    vistos: set[str] = set()

    def add(url_img: str, nombre: str, extension: str, es_fisico: int | None) -> None:
        url_img = (url_img or "").strip()
        if not url_img or url_img in vistos:
            return
        vistos.add(url_img)
        seccion, tipo = _seccion(url_img, es_fisico)
        item = {
            "filename": url_img,                 # lo que espera DownloadFile
            "nombre": nombre or url_img.rsplit("/", 1)[-1],
            "extension": (extension or url_img.rsplit(".", 1)[-1]).lstrip("."),
            "carpeta": url_img.split("/", 1)[0] if "/" in url_img else "",
            "seccion": seccion,
            "tipo": tipo,
        }
        (documentos if tipo == "documento" else imagenes).append(item)

    # 1) lAvances inline -> lImgValorizacion (docs) + lImgFisico (imágenes)
    m = re.search(r"var\s+lAvances\s*=\s*(\[.*?\]);", html, re.S)
    if m:
        for avance in json.loads(m.group(1)):
            for it in (avance.get("lImgValorizacion") or []):
                add(it.get("UrlImg", ""), it.get("nombreArchivo", ""),
                    it.get("Extension", ""), it.get("EsFisico", 0))
            for it in (avance.get("lImgFisico") or []):
                add(it.get("UrlImg", ""), it.get("nombreArchivo", ""),
                    it.get("Extension", ""), it.get("EsFisico", 1))

    # 2) Botones estáticos data-download-url -> documentos sueltos de la obra
    for raw in re.findall(r'data-download-url="([^"]+)"', html):
        qs = parse_qs(urlsplit(unquote(raw.replace("&amp;", "&"))).query)
        add(qs.get("filename", [""])[0], qs.get("name", [""])[0],
            qs.get("extension", [""])[0], None)

    return {"documentos": documentos, "imagenes": imagenes}


def descargar(sess: requests.Session, item: dict[str, Any], destino: Path) -> tuple[bool, str]:
    ext = item["extension"]
    params = {
        "filename": item["filename"],
        "name": item["nombre"],
        "contentType": "application/pdf" if ext == "pdf" else "application/octet-stream",
        "extension": "." + ext,
    }
    try:
        r = sess.get(DESCARGA, params=params, timeout=90)
    except requests.RequestException as e:
        return False, f"error de red: {e}"
    if r.status_code != 200 or not r.content:
        return False, f"HTTP {r.status_code} (archivo no disponible)"
    nombre = item["nombre"]
    if not nombre.lower().endswith("." + ext.lower()):
        nombre = f"{nombre}.{ext}"
    salida = destino / nombre
    salida.write_bytes(r.content)
    return True, f"{len(r.content):,} bytes → {salida.name}"


def clasificar_pdf(ruta: Path) -> dict[str, Any]:
    """Distingue PDF de TEXTO (vale leer) vs PDF-IMAGEN (escaneo / imágenes
    pegadas en Word→PDF, sin texto extraíble).

    Señal robusta = caracteres de texto extraíble por página. NO el peso del
    archivo (poco fiable) ni la sección/carpeta (un escaneo puede estar en
    cualquier item). Requiere PyMuPDF (`pip install pymupdf`).

    Devuelve {paginas, chars, chars_por_pagina, pct_area_imagen, tipo}.
    tipo ∈ {"texto", "mixto", "imagen", "vacio"}.
    """
    import fitz  # import perezoso: sólo si se pide clasificar

    doc = fitz.open(ruta)
    paginas = doc.page_count
    npg = paginas or 1
    total_chars = 0
    cobertura = 0.0
    for pg in doc:
        total_chars += len(pg.get_text("text").strip())
        parea = abs(pg.rect.width * pg.rect.height) or 1
        cub = sum(abs((b[2] - b[0]) * (b[3] - b[1]))
                  for im in pg.get_image_info() if (b := im.get("bbox")))
        cobertura += min(cub / parea, 1.0)
    doc.close()
    cpp = total_chars / npg
    pimg = cobertura / npg * 100
    if cpp >= 80 and pimg <= 60:
        tipo = "texto"               # documento legible → vale la pena leer/parsear
    elif cpp >= 80:
        tipo = "mixto"               # texto + imágenes grandes (revisar)
    elif pimg > 60:
        tipo = "imagen"             # escaneo / Word con imágenes → requiere OCR
    else:
        tipo = "vacio"              # sin texto ni imagen clara
    return {
        "paginas": paginas,
        "chars": total_chars,
        "chars_por_pagina": round(cpp),
        "pct_area_imagen": round(pimg),
        "tipo": tipo,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Descarga documentos (no imágenes) de una obra InfoObras.")
    ap.add_argument("--obra-id", required=True, help="obraId de la URL DatosEjecucion")
    ap.add_argument("--salida", default=None, help="directorio destino (def: ./descargas_infoobras/<obraId>)")
    ap.add_argument("--solo-inventario", action="store_true", help="lista archivos sin descargar")
    ap.add_argument("--incluir-imagenes", action="store_true", help="también baja las imágenes físicas")
    ap.add_argument("--clasificar", action="store_true",
                    help="tras descargar, clasifica cada PDF en texto/imagen (PyMuPDF)")
    args = ap.parse_args()

    sess = _session()
    print(f"→ Cargando {PAGINA}?obraId={args.obra_id}")
    r = sess.get(PAGINA, params={"obraId": args.obra_id}, timeout=90)
    r.raise_for_status()
    inv = inventariar(r.text)
    docs, imgs = inv["documentos"], inv["imagenes"]

    print(f"\n  DOCUMENTOS encontrados: {len(docs)}")
    for d in docs:
        print(f"    • [{d['seccion']:<46}] {d['nombre']} (.{d['extension']})")
    print(f"  IMÁGENES / EVIDENCIA (excluidas por defecto): {len(imgs)}")
    secs_img = sorted({i["seccion"] for i in imgs})
    for s in secs_img:
        print(f"    – sección: {s}")

    if args.solo_inventario:
        destino = Path(args.salida) if args.salida else Path.cwd()
        (destino / f"inventario_{args.obra_id}.json").write_text(
            json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Inventario → inventario_{args.obra_id}.json")
        return 0

    destino = Path(args.salida) if args.salida else Path("descargas_infoobras") / str(args.obra_id)
    destino.mkdir(parents=True, exist_ok=True)
    objetivos = docs + (imgs if args.incluir_imagenes else [])
    print(f"\n→ Descargando {len(objetivos)} archivo(s) en {destino}")
    ok = fail = 0
    bajados: list[Path] = []
    for it in objetivos:
        exito, msg = descargar(sess, it, destino)
        print(f"    {'✓' if exito else '✗'} {it['nombre']}: {msg}")
        ok += exito
        fail += not exito
        if exito:
            nombre = it["nombre"]
            if not nombre.lower().endswith("." + it["extension"].lower()):
                nombre = f"{nombre}.{it['extension']}"
            bajados.append(destino / nombre)
    print(f"\n  Listo: {ok} descargados, {fail} fallidos → {destino}")

    if args.clasificar:
        print("\n  CLASIFICACIÓN (texto vale leer · imagen requiere OCR):")
        print(f"    {'archivo':<30}{'pgs':>4}{'c/pág':>7}{'%img':>6}  tipo")
        leer = []
        for ruta in bajados:
            if ruta.suffix.lower() != ".pdf":
                continue
            c = clasificar_pdf(ruta)
            print(f"    {ruta.name:<30}{c['paginas']:>4}{c['chars_por_pagina']:>7}"
                  f"{c['pct_area_imagen']:>6}  {c['tipo']}")
            if c["tipo"] in ("texto", "mixto"):
                leer.append(ruta.name)
        print(f"\n    → {len(leer)} PDF(s) con texto legible; "
              f"{len(bajados) - len(leer)} sólo-imagen (OCR si se necesita su contenido).")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
