"""
ZIP de documentos InfoObras — entregable confirmado en alcance (2026-06-10):
sobre estos documentos se hace el análisis humano.

Dos piezas:
  1. `descargar_documentos_obra(obra_id, destino)` — baja los DOCUMENTOS de una
     obra (no las imágenes de avance físico). Portado del prototipo
     `tools/descargar_documentos_infoobras.py` (endpoints descubiertos contra
     la obra 72056: inventario inline en `var lAvances` + botones
     `data-download-url`; descarga por `/Mapa/DownloadFile`).
  2. `construir_zip_infoobras(espejo, descargas, salida)` — arma el ZIP con el
     árbol de 4 niveles definido por el cliente:
         Proyecto → Profesional → Experiencia → archivos
     Las experiencias sin documentos llevan una nota SIN_DOCUMENTOS.txt con el
     motivo (queda documentado, no desaparecen en silencio).
"""
from __future__ import annotations

import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlsplit

import requests

logger = logging.getLogger(__name__)

BASE = "https://infobras.contraloria.gob.pe/InfobrasWeb"
PAGINA = BASE + "/Mapa/DatosEjecucion"
DESCARGA = BASE + "/Mapa/DownloadFile"

# La SECCIÓN (prefijo de carpeta del UrlImg) define documento vs imagen — no la
# extensión (una foto puede venir como PDF). Verificado contra obraId=72056.
SECCIONES: dict[str, tuple[str, str]] = {
    "doc":           ("Documentos adjuntos del avance (valorizaciones)", "documento"),
    "expediente":    ("Expediente técnico", "documento"),
    "calendario":    ("Cronograma", "documento"),
    "ampliaciones":  ("Modificaciones en plazo - Ampliaciones", "documento"),
    "adenda":        ("Adendas", "documento"),
    "designacion":   ("Designación de supervisor - residente", "documento"),
    "aprobacion":    ("Documento de aprobación", "documento"),
    "sustento":      ("Documento sustento", "documento"),
    "transferencia": ("Transferencia financiera", "documento"),
    "entrega":       ("Entrega de terreno", "documento"),
    "img":           ("Imágenes adjuntas del avance", "imagen"),
    "imagen":        ("Galería de imágenes", "imagen"),
}
_EXT_IMAGEN = ("jpg", "jpeg", "png", "gif", "bmp", "tif", "tiff", "webp")


def _seccion(url_img: str, es_fisico: Optional[int]) -> tuple[str, str]:
    carpeta = url_img.split("/", 1)[0].strip().lower() if "/" in url_img else ""
    if carpeta in SECCIONES:
        return SECCIONES[carpeta]
    if es_fisico == 1:
        return SECCIONES["img"]
    if es_fisico == 0:
        return SECCIONES["doc"]
    ext = url_img.lower().rsplit(".", 1)[-1]
    tipo = "imagen" if ext in _EXT_IMAGEN else "documento"
    return (carpeta or "(sin sección)", tipo)


def inventariar(html: str) -> dict[str, list[dict[str, Any]]]:
    """Inventario de archivos de la página DatosEjecucion (sin descargar)."""
    documentos: list[dict[str, Any]] = []
    imagenes: list[dict[str, Any]] = []
    vistos: set[str] = set()

    def add(url_img: str, nombre: str, extension: str, es_fisico: Optional[int]) -> None:
        url_img = (url_img or "").strip()
        if not url_img or url_img in vistos:
            return
        vistos.add(url_img)
        seccion, tipo = _seccion(url_img, es_fisico)
        item = {
            "filename": url_img,
            "nombre": nombre or url_img.rsplit("/", 1)[-1],
            "extension": (extension or url_img.rsplit(".", 1)[-1]).lstrip("."),
            "seccion": seccion,
            "tipo": tipo,
        }
        (documentos if tipo == "documento" else imagenes).append(item)

    m = re.search(r"var\s+lAvances\s*=\s*(\[.*?\]);", html, re.S)
    if m:
        try:
            avances = json.loads(m.group(1))
        except json.JSONDecodeError:
            avances = []
            logger.warning("InfoObras: lAvances no parseable en inventario")
        for avance in avances:
            for it in (avance.get("lImgValorizacion") or []):
                add(it.get("UrlImg", ""), it.get("nombreArchivo", ""),
                    it.get("Extension", ""), it.get("EsFisico", 0))
            for it in (avance.get("lImgFisico") or []):
                add(it.get("UrlImg", ""), it.get("nombreArchivo", ""),
                    it.get("Extension", ""), it.get("EsFisico", 1))

    for raw in re.findall(r'data-download-url="([^"]+)"', html):
        qs = parse_qs(urlsplit(unquote(raw.replace("&amp;", "&"))).query)
        add(qs.get("filename", [""])[0], qs.get("name", [""])[0],
            qs.get("extension", [""])[0], None)

    return {"documentos": documentos, "imagenes": imagenes}


def descargar_documentos_obra(
    obra_id: int | str,
    destino: Path,
    *,
    session: Optional[requests.Session] = None,
    incluir_imagenes: bool = False,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Descarga los documentos de UNA obra a `destino` (subcarpeta por sección).
    Devuelve {descargados, fallidos, inventario}. NO corre en tests offline."""
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    )
    r = sess.get(PAGINA, params={"obraId": obra_id}, timeout=timeout)
    r.raise_for_status()
    inv = inventariar(r.text)
    objetivos = inv["documentos"] + (inv["imagenes"] if incluir_imagenes else [])

    destino.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    for it in objetivos:
        ext = it["extension"]
        try:
            resp = sess.get(DESCARGA, params={
                "filename": it["filename"], "name": it["nombre"],
                "contentType": "application/pdf" if ext == "pdf" else "application/octet-stream",
                "extension": "." + ext,
            }, timeout=timeout)
        except requests.RequestException as e:
            logger.warning("InfoObras descarga %s: %s", it["nombre"], e)
            fail += 1
            continue
        if resp.status_code != 200 or not resp.content:
            fail += 1
            continue
        nombre = it["nombre"]
        if not nombre.lower().endswith("." + ext.lower()):
            nombre = f"{nombre}.{ext}"
        carpeta = destino / _ruta_segura(it["seccion"])
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / _ruta_segura(nombre)).write_bytes(resp.content)
        ok += 1
    return {"descargados": ok, "fallidos": fail, "inventario": inv}


# ── Construcción del ZIP (árbol de 4 niveles) ────────────────────────────────

def _ruta_segura(s: str) -> str:
    """Nombre de carpeta/archivo seguro para ZIP y Windows."""
    s = re.sub(r'[<>:"/\\|?*]', "-", str(s or "")).strip(" .")
    s = re.sub(r"\s+", " ", s)
    return s or "(sin nombre)"


def construir_zip_infoobras(
    espejo: dict,
    descargas: dict[tuple[int, int], Path],
    salida: Path,
) -> Path:
    """Arma el ZIP del análisis: Proyecto → Profesional → Experiencia → archivos.

    `descargas`: {(n_prof, n_exp): directorio con los documentos descargados de
    la obra de esa experiencia}. Las experiencias sin entrada (obra sin CUI,
    fuera de InfoObras, o descarga fallida) llevan SIN_DOCUMENTOS.txt.
    """
    raiz = _ruta_segura(espejo.get("_meta", {}).get("concurso") or "concurso")
    indice: list[str] = [f"ZIP InfoObras · {raiz}",
                         f"Postor: {espejo.get('_meta', {}).get('postor') or '—'}", ""]

    salida.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for prof in espejo.get("profesionales", []):
            n_prof = prof.get("n_prof")
            nivel2 = _ruta_segura(f"{n_prof:02d} - {prof.get('cargo', '')}")
            for e in prof.get("experiencias", []):
                n_exp = e.get("n")
                nivel3 = _ruta_segura(
                    f"Exp {n_exp} - {str(e.get('proyecto') or 'sin proyecto')[:60]}")
                base = f"{raiz}/{nivel2}/{nivel3}"

                origen = descargas.get((n_prof, n_exp))
                if origen and Path(origen).is_dir():
                    archivos = [p for p in sorted(Path(origen).rglob("*")) if p.is_file()]
                    for p in archivos:
                        rel = p.relative_to(origen)
                        partes = "/".join(_ruta_segura(x) for x in rel.parts)
                        zf.write(p, f"{base}/{partes}")
                    indice.append(f"[{n_prof:02d}.{n_exp}] {nivel3}: {len(archivos)} archivo(s)")
                else:
                    motivo = (
                        "Obra sin CUI resuelto o fuera de InfoObras "
                        "(ESSALUD/privada), o descarga no disponible."
                    )
                    cui = e.get("cui")
                    zf.writestr(
                        f"{base}/SIN_DOCUMENTOS.txt",
                        f"Sin documentos descargados para esta experiencia.\n"
                        f"CUI: {cui or '(no resuelto)'}\nMotivo: {motivo}\n",
                    )
                    indice.append(f"[{n_prof:02d}.{n_exp}] {nivel3}: SIN DOCUMENTOS")

        zf.writestr(f"{raiz}/indice.txt", "\n".join(indice) + "\n")
    return salida
