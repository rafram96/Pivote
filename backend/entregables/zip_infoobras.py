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
import os
import random
import re
import time
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlsplit

import requests

logger = logging.getLogger(__name__)

# El portal corta la conexión en archivos grandes (IncompleteRead): obras
# pesadas tienen PDFs de ~50 MB y >700 MB en total. Sin reintento + streaming,
# esos sustentos (los más importantes) se perdían en silencio del ZIP.
_DL_RETRIES = int(os.getenv("INFOOBRAS_DOWNLOAD_RETRIES", "3"))
_DL_BASE_DELAY = float(os.getenv("INFOOBRAS_DOWNLOAD_BASE_DELAY", "1.0"))

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


_MES_NUM = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def _etiqueta_hito(anio: int, mes_nombre: str) -> str:
    """Nombre de carpeta del hito/valorización: 'AAAA-MM MES' (ordena cronológico)."""
    mes = (mes_nombre or "").upper().strip()
    mes_n = _MES_NUM.get(mes, 0)
    if anio and mes_n:
        return f"{anio:04d}-{mes_n:02d} {mes}"
    return mes or "sin fecha"


def inventariar_por_avance(html: str) -> dict[str, Any]:
    """Inventario LIGADO a cada avance: por cada valorización (mes/año) sus
    documentos. Más los documentos obra-level (expediente, cronograma, …) que NO
    pertenecen a un mes. Para descargar agrupando por hito/valorización.

    Devuelve {avances:[{anio,mes,documentos[],imagenes[]}], obra:{documentos,imagenes}}.
    """
    vistos: set[str] = set()

    def _mk(it: dict, es_fisico_default: int) -> Optional[dict]:
        url_img = (it.get("UrlImg") or "").strip()
        if not url_img or url_img in vistos:
            return None
        vistos.add(url_img)
        seccion, tipo = _seccion(url_img, it.get("EsFisico", es_fisico_default))
        return {
            "filename": url_img,
            "nombre": it.get("nombreArchivo") or url_img.rsplit("/", 1)[-1],
            "extension": (it.get("Extension") or url_img.rsplit(".", 1)[-1]).lstrip("."),
            "seccion": seccion, "tipo": tipo,
        }

    avances_out: list[dict] = []
    m = re.search(r"var\s+lAvances\s*=\s*(\[.*?\]);", html, re.S)
    avances = []
    if m:
        try:
            avances = json.loads(m.group(1))
        except json.JSONDecodeError:
            logger.warning("InfoObras: lAvances no parseable (por_avance)")
    for av in avances:
        anio_str = str(av.get("Anio") or "")
        anio = int(anio_str) if anio_str.isdigit() else 0
        docs: list[dict] = []
        imgs: list[dict] = []
        for it in (av.get("lImgValorizacion") or []):
            d = _mk(it, 0)
            if d:
                (docs if d["tipo"] == "documento" else imgs).append(d)
        for it in (av.get("lImgFisico") or []):
            d = _mk(it, 1)
            if d:
                (docs if d["tipo"] == "documento" else imgs).append(d)
        if docs or imgs:
            avances_out.append({"anio": anio, "mes": (av.get("Mes") or "").strip(),
                                "documentos": docs, "imagenes": imgs})

    # obra-level (data-download-url), excluyendo los ya vistos en los avances
    obra_docs: list[dict] = []
    obra_imgs: list[dict] = []
    for raw in re.findall(r'data-download-url="([^"]+)"', html):
        qs = parse_qs(urlsplit(unquote(raw.replace("&amp;", "&"))).query)
        fn = (qs.get("filename", [""])[0] or "").strip()
        if not fn or fn in vistos:
            continue
        vistos.add(fn)
        seccion, tipo = _seccion(fn, None)
        item = {"filename": fn,
                "nombre": qs.get("name", [""])[0] or fn.rsplit("/", 1)[-1],
                "extension": (qs.get("extension", [""])[0] or fn.rsplit(".", 1)[-1]).lstrip("."),
                "seccion": seccion, "tipo": tipo}
        (obra_docs if tipo == "documento" else obra_imgs).append(item)

    return {"avances": avances_out, "obra": {"documentos": obra_docs, "imagenes": obra_imgs}}


def _descargar_a_carpeta(
    sess: requests.Session,
    it: dict,
    carpeta: Path,
    *,
    timeout: float,
    intentos: int = _DL_RETRIES,
    prefijo_nombre: str = "",
) -> bool:
    """Descarga `it` a `carpeta/<prefijo_nombre><nombre>` con streaming a disco +
    reintentos.

    `prefijo_nombre` se antepone al nombre del archivo (p.ej. "2025-09 SEPTIEMBRE · ")
    para que un documento de valorización se identifique por su fecha aunque se
    saque de su carpeta. Robusto ante los cortes del portal en archivos grandes
    (IncompleteRead / ConnectionError): baja a un `.part`, verifica Content-Length
    y reintenta con backoff exponencial. Devuelve True si quedó un archivo íntegro;
    False si se agotaron los intentos o el archivo no está disponible (4xx). No
    relanza: el llamador cuenta ok/fallido.
    """
    ext = it["extension"]
    nombre = it["nombre"]
    if not nombre.lower().endswith("." + ext.lower()):
        nombre = f"{nombre}.{ext}"
    destino = carpeta / _ruta_segura(f"{prefijo_nombre}{nombre}")
    tmp = destino.with_name(destino.name + ".part")
    params = {
        "filename": it["filename"], "name": it["nombre"],
        "contentType": "application/pdf" if ext == "pdf" else "application/octet-stream",
        "extension": "." + ext,
    }
    for intento in range(max(1, intentos)):
        try:
            with sess.get(DESCARGA, params=params, timeout=timeout, stream=True) as resp:
                if resp.status_code >= 500:
                    raise OSError(f"HTTP {resp.status_code}")   # transitorio → reintentar
                if resp.status_code != 200:
                    return False                                 # 4xx → no disponible
                carpeta.mkdir(parents=True, exist_ok=True)
                n = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                            n += len(chunk)
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit() and n < int(cl):
                    raise OSError(f"descarga incompleta {n}/{cl} bytes")
                if n == 0:
                    raise OSError("respuesta vacía")
            tmp.replace(destino)
            return True
        except (requests.RequestException, OSError) as e:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            if intento < intentos - 1:
                delay = _DL_BASE_DELAY * (2 ** intento) + random.uniform(0, 0.5)
                logger.warning("InfoObras descarga %s intento %d/%d: %s — reintento en %.1fs",
                               it["nombre"], intento + 1, intentos, e, delay)
                time.sleep(delay)
            else:
                logger.warning("InfoObras descarga %s falló tras %d intentos: %s",
                               it["nombre"], intentos, e)
    return False


def _get_inventario(
    sess: requests.Session,
    obra_id: int | str,
    *,
    timeout: float,
    intentos: int = _DL_RETRIES,
) -> str:
    """GET de la página `DatosEjecucion` con reintento + backoff.

    El portal devuelve 503 transitorios (y a veces corta la conexión) también en
    esta página; sin reintento, un fallo pasajero abortaba la descarga de TODA la
    obra. Devuelve el HTML. Reintenta en 5xx/ConnectionError/Timeout; un 4xx es
    permanente (relanza de inmediato). Si agota los intentos, relanza el último
    error para que el llamador lo trate como obra no disponible.
    """
    ultima: Optional[Exception] = None
    for intento in range(max(1, intentos)):
        try:
            r = sess.get(PAGINA, params={"obraId": obra_id}, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            ultima = e
        else:
            if r.status_code < 500:
                r.raise_for_status()   # 2xx → no-op · 4xx → error permanente
                return r.text
            ultima = requests.HTTPError(f"HTTP {r.status_code}", response=r)
        if intento < intentos - 1:
            delay = _DL_BASE_DELAY * (2 ** intento) + random.uniform(0, 0.5)
            logger.warning("InfoObras inventario obra %s intento %d/%d: %s — reintento en %.1fs",
                           obra_id, intento + 1, intentos, ultima, delay)
            time.sleep(delay)
    raise ultima or requests.HTTPError("inventario no disponible")


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
    inv = inventariar(_get_inventario(sess, obra_id, timeout=timeout))
    objetivos = inv["documentos"] + (inv["imagenes"] if incluir_imagenes else [])

    destino.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    for it in objetivos:
        carpeta = destino / _ruta_segura(it["seccion"])
        if _descargar_a_carpeta(sess, it, carpeta, timeout=timeout):
            ok += 1
        else:
            fail += 1
    return {"descargados": ok, "fallidos": fail, "inventario": inv}


def descargar_documentos_obra_por_hito(
    obra_id: int | str,
    destino: Path,
    *,
    session: Optional[requests.Session] = None,
    incluir_imagenes: bool = False,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Como `descargar_documentos_obra`, pero los documentos de cada valorización
    van a una carpeta POR HITO:  destino/Valorizaciones/<AAAA-MM MES>/<documento>,
    y el archivo se PREFIJA con la fecha del hito ("<AAAA-MM MES> · <nombre>") para
    identificarse aunque se saque de su carpeta. Los documentos obra-level
    (expediente, cronograma, …) van a su sección, sin prefijo.
    Devuelve {descargados, fallidos, inventario}. NO corre en tests offline."""
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    )
    inv = inventariar_por_avance(_get_inventario(sess, obra_id, timeout=timeout))
    destino.mkdir(parents=True, exist_ok=True)
    cont = {"ok": 0, "fail": 0}

    def _bajar(it: dict, carpeta: Path, prefijo: str = "") -> None:
        if _descargar_a_carpeta(sess, it, carpeta, timeout=timeout, prefijo_nombre=prefijo):
            cont["ok"] += 1
        else:
            cont["fail"] += 1

    # valorizaciones agrupadas por hito (mes/año), con la fecha en el nombre
    for av in inv["avances"]:
        etiqueta = _etiqueta_hito(av["anio"], av["mes"])
        carpeta = destino / "Valorizaciones" / _ruta_segura(etiqueta)
        for it in av["documentos"] + (av["imagenes"] if incluir_imagenes else []):
            _bajar(it, carpeta, prefijo=f"{etiqueta} · ")
    # documentos obra-level → su sección (sin prefijo: no pertenecen a un mes)
    for it in inv["obra"]["documentos"] + (inv["obra"]["imagenes"] if incluir_imagenes else []):
        _bajar(it, destino / _ruta_segura(it["seccion"]))

    return {"descargados": cont["ok"], "fallidos": cont["fail"], "inventario": inv}


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
