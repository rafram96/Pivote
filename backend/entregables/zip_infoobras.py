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

import hashlib
import json
import logging
import os
import re
import threading
import time   # el backoff duerme en errores_red, pero los tests parchean `z.time.sleep`
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

from scraping.errores_red import (
    EXPONENCIAL, Politica, RespuestaTransitoria, clasificar, con_reintentos, corto,
    permanente,
)
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from entregables.certeza import normalizar_motivo_fuente
from entregables.identidad import proyectar_identidad
from entregables.estado_fuentes import proyectar_estado_fuentes, lineas_estado_fuentes
from entregables.procedencia import rotulo_cui
from entregables.servicio_experiencia import lineas_contraste_servicio

logger = logging.getLogger(__name__)

# El portal corta la conexión en archivos grandes (IncompleteRead): obras
# pesadas tienen PDFs de ~50 MB y >700 MB en total. Sin reintento + streaming,
# esos sustentos (los más importantes) se perdían en silencio del ZIP.
_DL_RETRIES = int(os.getenv("INFOOBRAS_DOWNLOAD_RETRIES", "3"))
_DL_BASE_DELAY = float(os.getenv("INFOOBRAS_DOWNLOAD_BASE_DELAY", "1.0"))


def _politica(intentos: int) -> Politica:
    """Reintentos de descarga (ADR-014): exponencial 1s, 2s + jitter 0-0.5s —
    la misma temporización que tenían los cinco bucles artesanales."""
    return Politica(intentos=max(1, intentos), base=_DL_BASE_DELAY,
                    modo=EXPONENCIAL, jitter=0.5)

# Contador de reintentos de descarga, por HILO: la etapa InfoObras corre en su
# propio hilo del pool y descarga sincrónicamente, así que `reset` al inicio y
# `descargas_stats` al cierre (mismo hilo) son seguros incluso con jobs concurrentes.
_dl_local = threading.local()


def reset_descargas_stats() -> dict:
    _dl_local.v = {"reintentos": 0, "fallidos": []}
    return _dl_local.v


def descargas_stats() -> dict:
    v = getattr(_dl_local, "v", None)
    if v is None:
        v = reset_descargas_stats()
    return v


def _registrar_fallo(e, etiqueta: str) -> tuple[str, str]:
    """Clasifica un fallo DEFINITIVO (agotados los reintentos) y lo guarda para el
    resumen final. Devuelve (categoria, mensaje)."""
    cat, msg = clasificar(e)
    descargas_stats().setdefault("fallidos", []).append((etiqueta, cat, msg))
    return cat, msg


def resumen_descargas() -> str:
    """Una sola línea con el balance de la etapa (reintentos + ítems no descargados
    por categoría), en vez de cientos de líneas crudas."""
    st = descargas_stats()
    fall = st.get("fallidos", [])
    linea = f"{st.get('reintentos', 0)} reintento(s)"
    if fall:
        from collections import Counter
        c = Counter(cat for _, cat, _ in fall)
        desg = " · ".join(f"{n} {k}" for k, n in c.most_common())
        linea += f" · {len(fall)} ítem(s) NO descargados ({desg})"
    else:
        linea += " · sin fallos definitivos"
    return linea

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
    def _bajar() -> bool:
        try:
            with sess.get(DESCARGA, params=params, timeout=timeout, stream=True) as resp:
                if resp.status_code >= 500:
                    raise RespuestaTransitoria(f"HTTP {resp.status_code}")  # → reintentar
                if resp.status_code != 200:
                    _registrar_fallo(OSError(f"HTTP {resp.status_code}"), it["nombre"])
                    return False                                 # 4xx → no disponible
                os.makedirs(_wlong(carpeta), exist_ok=True)
                n = 0
                with open(_wlong(tmp), "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                            n += len(chunk)
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit() and n < int(cl):
                    raise RespuestaTransitoria(f"descarga incompleta {n}/{cl} bytes")
                if n == 0:
                    raise RespuestaTransitoria("respuesta vacía")
            os.replace(_wlong(tmp), _wlong(destino))
            return True
        except (requests.RequestException, OSError):
            try:
                os.remove(_wlong(tmp))
            except OSError:
                pass
            raise

    def _contar(_intento, _err) -> None:
        # el contador por hilo alimenta el índice del entregable: vive dentro del
        # bucle, así que viaja como gancho del helper.
        descargas_stats()["reintentos"] += 1

    res = con_reintentos(_bajar, politica=_politica(intentos),
                         etiqueta=f"InfoObras descarga «{it['nombre']}»",
                         excepciones=(requests.RequestException, OSError),
                         al_reintentar=_contar, log=logger)
    if res.respondio:
        return res.valor
    cat, msg = _registrar_fallo(res.error, it["nombre"])
    logger.warning("InfoObras ✗ «%s»: [%s] %s (tras %d intentos)",
                   it["nombre"], cat, msg, res.intentos)
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
    def _pedir() -> str:
        r = sess.get(PAGINA, params={"obraId": obra_id}, timeout=timeout)
        if r.status_code >= 500:
            raise RespuestaTransitoria(f"HTTP {r.status_code}")
        with permanente():
            r.raise_for_status()       # 2xx → no-op · 4xx → error permanente
        return r.text

    res = con_reintentos(_pedir, politica=_politica(intentos),
                         etiqueta=f"InfoObras inventario obra {obra_id}",
                         excepciones=(requests.ConnectionError, requests.Timeout,
                                      RespuestaTransitoria),
                         log=logger)
    res.relanzar(requests.HTTPError("inventario no disponible"))
    return res.valor


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
    van a una carpeta POR HITO:  destino/Valorizaciones/<AAAA-MM MES>/<documento>.
    Los nombres se sanitizan y CAPAN (`_ruta_segura`) para no reventar el límite de
    260 de Windows (las obras de educación traen nombres larguísimos). Los
    documentos obra-level (expediente, cronograma, …) van a su sección.
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
            _bajar(it, carpeta)   # sin prefijo del mes: ya es la carpeta (acorta la ruta)
    # documentos obra-level → su sección (sin prefijo: no pertenecen a un mes)
    for it in inv["obra"]["documentos"] + (inv["obra"]["imagenes"] if incluir_imagenes else []):
        _bajar(it, destino / _ruta_segura(it["seccion"]))

    return {"descargados": cont["ok"], "fallidos": cont["fail"], "inventario": inv}


# ── Informes de control (Contraloría) ────────────────────────────────────────
# Cada obra tiene "informes de control" (auditorías de la Contraloría) en una
# página aparte (/Mapa/InformeControl?obraId=…), embebidos en un JSON
# `var lInformeControl`. Descargamos SOLO los relevantes al periodo de la
# experiencia: un informe de 2019 no aporta a una experiencia que terminó en
# 2018. El PDF principal es TIPOARCHIVO=IS (campo RutaInforme).
INFORME_CONTROL = BASE + "/Mapa/InformeControl"


def _parse_fecha_informe(s: Optional[str]) -> Optional[date]:
    """'11/04/2018' → date. None si no parsea."""
    m = re.match(r"\s*(\d{2})/(\d{2})/(\d{4})", str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _anio_informe(inf: dict) -> Optional[int]:
    a = str(inf.get("Anio") or "").strip()
    if a.isdigit():
        return int(a)
    fe = _parse_fecha_informe(inf.get("FechaEmision"))
    return fe.year if fe else None


def obtener_informes_control(
    sess: requests.Session, obra_id: int | str, *, timeout: float = 60.0,
    intentos: int = _DL_RETRIES,
) -> list[dict]:
    """Lista los informes de control de una obra (parsea `var lInformeControl`).
    Cada item: {Codigo, Anio, NroInforme, TituloInforme, TipoServicio,
    FechaEmision, FechaPublicacion, RutaInforme, RutaPublicacion}. [] si no hay."""
    def _pedir() -> list[dict]:
        r = sess.get(INFORME_CONTROL, params={"obraId": obra_id}, timeout=timeout)
        if r.status_code == 200:
            m = re.search(r"var\s+lInformeControl\s*=\s*(\[.*?\])\s*;", r.text, re.S)
            if not m:
                return []
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                logger.warning("InfoObras: lInformeControl no parseable (obra %s)", obra_id)
                return []
        if r.status_code < 500:
            return []       # 4xx → no hay página de informes
        raise RespuestaTransitoria(f"HTTP {r.status_code}")

    res = con_reintentos(_pedir, politica=_politica(intentos),
                         etiqueta=f"InfoObras informes obra {obra_id}",
                         excepciones=(requests.ConnectionError, requests.Timeout,
                                      RespuestaTransitoria),
                         log=logger)
    if not res.respondio:
        # ⚠ conflación heredada: el llamador no distingue «no hay informes» de
        # «el portal no respondió». Se conserva porque cambiar el retorno mueve
        # lo que ve el índice del ZIP (ADR-014 §Pendientes conscientes).
        logger.debug("InfoObras informes obra %s: %s", obra_id, corto(res.error))
    return res.valor_o([])


def informes_relevantes(
    informes: list[dict], fecha_ini: Optional[date], fecha_fin: Optional[date],
) -> list[dict]:
    """Filtra los informes cuyo AÑO cae dentro del periodo de la experiencia
    (inclusive): exp 2016–2018 + informes 2018–2022 → solo el de 2018. Sin periodo
    conocido, los devuelve todos (mejor incluir que perder un sustento)."""
    a_ini = fecha_ini.year if fecha_ini else None
    a_fin = fecha_fin.year if fecha_fin else None
    if a_ini is None or a_fin is None:
        return list(informes)
    lo, hi = min(a_ini, a_fin), max(a_ini, a_fin)
    out = []
    for inf in informes:
        a = _anio_informe(inf)
        if a is None or lo <= a <= hi:   # sin año legible → incluir por las dudas
            out.append(inf)
    return out


def _descargar_url(sess: requests.Session, url: str, destino: Path, *,
                   timeout: float, intentos: int = _DL_RETRIES) -> bool:
    """Descarga directa de una URL (PDF de Contraloría) con streaming + reintentos."""
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".part")

    def _bajar() -> bool:
        try:
            with sess.get(url, timeout=timeout, stream=True) as resp:
                if resp.status_code >= 500:
                    raise RespuestaTransitoria(f"HTTP {resp.status_code}")
                if resp.status_code != 200:
                    _registrar_fallo(OSError(f"HTTP {resp.status_code}"), destino.name)
                    return False
                os.makedirs(_wlong(destino.parent), exist_ok=True)
                n = 0
                with open(_wlong(tmp), "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
                            n += len(chunk)
                if n == 0:
                    raise RespuestaTransitoria("respuesta vacía")
            os.replace(_wlong(tmp), _wlong(destino))
            return True
        except (requests.RequestException, OSError):
            try:
                os.remove(_wlong(tmp))
            except OSError:
                pass
            raise

    res = con_reintentos(_bajar, politica=_politica(intentos),
                         etiqueta=f"InfoObras informe (control) {destino.name}",
                         excepciones=(requests.RequestException, OSError),
                         log=logger)
    if not res.respondio:
        _registrar_fallo(res.error, destino.name)
        logger.debug("InfoObras informe (control) falló: %s", corto(res.error))
    return res.valor_o(False)


def descargar_informes_control(
    obra_id: int | str, destino: Path, *, fecha_ini: Optional[date] = None,
    fecha_fin: Optional[date] = None, session: Optional[requests.Session] = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Descarga a `destino/Informes de control/` los informes de control de la
    obra RELEVANTES al periodo [fecha_ini, fecha_fin] de la experiencia. Devuelve
    {encontrados, relevantes, descargados, anios}. ``anios`` conserva el
    inventario completo para filtrar localmente una caché por obra. NO corre en
    tests offline."""
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    )
    informes = obtener_informes_control(sess, obra_id, timeout=timeout)
    rel = informes_relevantes(informes, fecha_ini, fecha_fin)
    carpeta = Path(destino) / "Informes de control"
    ok = 0
    for inf in rel:
        url = inf.get("RutaInforme") or inf.get("RutaPublicacion")
        if not url:
            continue
        anio = _anio_informe(inf) or "s-f"
        nro = str(inf.get("NroInforme") or inf.get("Codigo") or "informe")
        titulo = str(inf.get("TituloInforme") or "")[:50]
        nombre = _ruta_segura(f"{anio} - {nro} - {titulo}".strip(" -")) + ".pdf"
        if _descargar_url(sess, url, carpeta / nombre, timeout=timeout):
            ok += 1
    if informes:
        logger.info("InfoObras informes obra %s: %d encontrados, %d relevantes, %d descargados",
                    obra_id, len(informes), len(rel), ok)
    return {
        "encontrados": len(informes),
        "relevantes": len(rel),
        "descargados": ok,
        "anios": [_anio_informe(informe) for informe in informes],
    }


# ── Datos de cierre (Recepción, Liquidación, Resolución de contrato) ──────────
# Página aparte (/Mapa/DatosCierre?obraId=…) con los documentos del CIERRE de la
# obra: acta de recepción, aprobación de liquidación, resolución de contrato,
# transferencia. Botones "Descargar" con data-download-url → /Mapa/DownloadFile,
# el mismo mecanismo que DatosEjecucion (lo verifica `inventariar`).
DATOS_CIERRE = BASE + "/Mapa/DatosCierre"


def _items_descarga(html: str) -> list[dict]:
    """Items {filename, nombre, extension} desde los botones de descarga de una
    página (data-download-url o href a DownloadFile). Dedup por filename."""
    out: list[dict] = []
    vistos: set[str] = set()
    urls = re.findall(r'data-download-url="([^"]+)"', html)
    urls += re.findall(r'href="([^"]*DownloadFile[^"]*)"', html)
    for raw in urls:
        qs = parse_qs(urlsplit(unquote(raw.replace("&amp;", "&"))).query)
        fn = (qs.get("filename", [""])[0]).strip()
        if not fn or fn in vistos:
            continue
        vistos.add(fn)
        base = fn.rsplit("/", 1)[-1]
        nombre = (qs.get("name", [""])[0]).strip() or base
        ext = ((qs.get("extension", [""])[0] or "").lstrip(".")
               or (base.rsplit(".", 1)[-1] if "." in base else "")
               or "pdf")
        out.append({"filename": fn, "nombre": nombre, "extension": ext})
    return out


def descargar_datos_cierre(
    obra_id: int | str, destino: Path, *,
    session: Optional[requests.Session] = None, timeout: float = 60.0,
    intentos: int = _DL_RETRIES,
) -> dict[str, int]:
    """Descarga a `destino/Datos de cierre/` los documentos del cierre de la obra
    (acta de recepción, liquidación, resolución de contrato, transferencia) desde
    `/Mapa/DatosCierre`. Devuelve {encontrados, descargados}. NO corre en tests offline."""
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    )
    def _pedir() -> Optional[str]:
        r = sess.get(DATOS_CIERRE, params={"obraId": obra_id}, timeout=timeout)
        if r.status_code == 200:
            return r.text
        if r.status_code < 500:
            return None      # 4xx → respuesta: no hay página de cierre
        raise RespuestaTransitoria(f"HTTP {r.status_code}")

    res = con_reintentos(_pedir, politica=_politica(intentos),
                         etiqueta=f"InfoObras datos de cierre obra {obra_id}",
                         excepciones=(requests.ConnectionError, requests.Timeout,
                                      RespuestaTransitoria),
                         log=logger)
    html = res.valor_o(None)
    if not html:
        # ⚠ misma conflación heredada que `obtener_informes_control`: el {0,0} no
        # distingue «sin cierre» de «portal caído» (ADR-014 §Pendientes).
        if not res.respondio:
            logger.debug("InfoObras datos de cierre obra %s: %s",
                         obra_id, corto(res.error))
        return {"encontrados": 0, "descargados": 0}

    items = _items_descarga(html)
    carpeta = Path(destino) / "Datos de cierre"
    ok = sum(1 for it in items if _descargar_a_carpeta(sess, it, carpeta, timeout=timeout))
    if items:
        logger.info("InfoObras datos de cierre obra %s: %d encontrados, %d descargados",
                    obra_id, len(items), ok)
    return {"encontrados": len(items), "descargados": ok}


def descargar_aprobacion_expediente(
    aprob: dict, destino: Path, *,
    session: Optional[requests.Session] = None, timeout: float = 60.0,
    intentos: int = _DL_RETRIES,
) -> bool:
    """Descarga el documento de la 'Aprobación del proyecto' (experiencias de
    EXPEDIENTE técnico sin valorizaciones) a `destino/`. `aprob` es el dict que
    arma `parsear_aprobacion_expediente` ({url, filename, nombre, extension, fecha}),
    con las mismas claves que espera `_descargar_a_carpeta`. Devuelve True si bajó."""
    if not aprob or not aprob.get("filename"):
        return False
    sess = session or requests.Session()
    sess.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    )
    carpeta = Path(destino) / "Aprobación del expediente"
    return _descargar_a_carpeta(sess, aprob, carpeta, timeout=timeout, intentos=intentos)


# ── Construcción del ZIP (árbol de 4 niveles) ────────────────────────────────

_MAXLEN_RUTA = 64  # tope por componente (carpeta/archivo) → la ruta cabe en 260


def _ruta_segura(s: str, maxlen: int = _MAXLEN_RUTA) -> str:
    """Nombre de carpeta/archivo seguro para ZIP y Windows: sin caracteres
    ilegales y CAPADO a `maxlen`. Si trunca, preserva la extensión y añade un hash
    corto (determinístico → no rompe la reanudación, no colisiona). Componentes
    cortos = la ruta cabe en el límite de 260 de Windows al CREAR y al EXTRAER el
    ZIP en cualquier máquina (los nombres de obras de educación son larguísimos y
    reventaban el límite)."""
    s = re.sub(r'[<>:"/\\|?*]', "-", str(s or "")).strip(" .")
    s = re.sub(r"\s+", " ", s)
    s = s or "(sin nombre)"
    if len(s) <= maxlen:
        return s
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:6]
    stem, dot, ext = s.rpartition(".")
    if dot and 1 <= len(ext) <= 5 and " " not in ext:          # archivo con extensión
        keep = max(1, maxlen - len(ext) - 8)                   # sitio para "~hash.ext"
        return f"{stem[:keep].rstrip()}~{h}.{ext}"
    return f"{s[:max(1, maxlen - 7)].rstrip()}~{h}"            # carpeta / sin extensión


def _wlong(p) -> str:
    """Ruta como str, con prefijo \\\\?\\ en Windows para saltar el límite de 260
    al crear/escribir/renombrar (red de seguridad si la carpeta base es muy
    profunda). No-op en Linux/Mac. Lo principal es que los nombres ya van capados;
    esto garantiza que la CREACIÓN nunca falle por largo."""
    s = os.path.abspath(str(p))
    if os.name == "nt" and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + s
    return s


def _motivo_sin_docs(via: Optional[str], cui: Optional[str]) -> str:
    """Ausencia de archivos, sin equiparar CUI utilizado con confirmado."""
    v = (via or "").upper()
    if v == "PRIVADA":
        return ("Cliente/obra privada: InfoObras solo registra obra pública — "
                "el respaldo es el certificado presentado (verificación documental).")
    if v == "NA":
        return "No aplica: sin cruce InfoObras para esta experiencia."
    if v == "NO_EXISTE":
        return "Obra no encontrada en InfoObras (marcada por el evaluador)."
    if cui:
        return (f"CUI {cui} utilizado (vía {via or 'no informada'}); no hay "
                "documentos incorporados a esta entrega. Esto no prueba su inexistencia.")
    return ("No hay CUI utilizado registrado ni documentos incorporados a esta entrega. "
            "La identificación y la obtención de documentos son estados distintos.")


def _cargo_corto(cargo: str) -> str:
    """Parte distintiva del cargo para la carpeta del ZIP: quita el prefijo
    genérico ('Especialista en', 'Jefe de'...) y deja lo que identifica
    ('Estructuras', 'Supervisión'...). El cargo completo va en el indice.txt."""
    c = re.sub(r"^\s*(especialista en|especialista|jefe de|jefe|ingeniero|"
               r"responsable de|gerente de|gerente)\s+", "", str(cargo or ""),
               flags=re.I).strip()
    return c or str(cargo or "").strip() or "Profesional"


def _corto(txt: str, maxlen: int) -> str:
    """Trunca limpio (sin sufijo hash) a `maxlen`. La unicidad la garantiza el
    prefijo P{nn}/E{n}, así que aquí no hace falta anticolisión."""
    t = re.sub(r'[<>:"/\\|?*]', "-", str(txt or "")).strip()
    t = re.sub(r"\s+", " ", t)
    return t[:maxlen].strip() or "(sin nombre)"


def _carpeta_experiencia(n: int, proyecto: str) -> str:
    """Etiqueta humana; n sigue siendo la única clave de asociación.

    Acota el nombre para no consumir el presupuesto de rutas Windows. El
    proyecto completo sigue disponible en el espejo/Excel/índice Markdown.
    """
    nombre = re.sub(r"[\x00-\x1f]", " ", str(proyecto or ""))
    nombre = _corto(nombre, 36).rstrip(" .") or "(sin nombre)"
    return f"E{n} {nombre}"


def _sha256_archivo(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _manifiestos_activos() -> bool:
    """¿Se escribe el `MANIFIESTO_DOCUMENTOS.txt` de cada experiencia?

    `PIVOTE_MANIFIESTOS_ZIP` sin definir o "1" → SÍ (default; conserva el contrato
    actual del ZIP, spec D5 de la issue #80). "0" → NO: el manifiesto es un
    documento de verificación TÉCNICA (para el desarrollador) y el entregable lo
    consume un equipo de evaluación no técnico. El SHA-256 se sigue calculando
    siempre: el índice depende de él para los conteos de compartidos/propios.

    Se lee en cada llamada (no al importar) para que el valor del `.env` se
    respete sin reiniciar el proceso y para que los tests puedan monkeypatchearlo.
    """
    return (os.getenv("PIVOTE_MANIFIESTOS_ZIP") or "1").strip() not in ("0", "false", "no")


_FORMATOS_INDICE = ("txt", "md", "json")


def _formatos_indice() -> list[str]:
    """Formatos del índice del ZIP, según `PIVOTE_INDICE_ZIP`.

    Lista separada por comas con `txt`, `md` y/o `json` (`md,json`,
    `txt,md,json`…). Sin definir → `["txt"]`: el `indice.txt` de siempre, byte a
    byte. `"0"` (o una lista que no deja ningún formato, p.ej. `","`) → SIN
    índice. Un valor vacío se trata como "sin definir" (el `.env`/compose dejan
    variables vacías; no queremos que eso borre el índice en silencio).

    Un formato desconocido se ignora con warning; si NINGUNO es válido cae al
    default `txt` — un typo no puede dejar el entregable sin índice. El orden de
    salida es canónico (txt → md → json), no el que traiga la variable.
    """
    raw = os.getenv("PIVOTE_INDICE_ZIP")
    if raw is None or not raw.strip():
        return ["txt"]
    if raw.strip().lower() in ("0", "false", "no"):
        return []
    pedidos, desconocidos = set(), []
    for parte in raw.split(","):
        f = parte.strip().lower()
        if not f:
            continue
        if f in _FORMATOS_INDICE:
            pedidos.add(f)
        else:
            desconocidos.append(f)
    if desconocidos:
        logger.warning("PIVOTE_INDICE_ZIP: formato(s) desconocido(s) %s (válidos: %s)",
                       ", ".join(desconocidos), ", ".join(_FORMATOS_INDICE))
    if not pedidos and desconocidos:
        return ["txt"]
    return [f for f in _FORMATOS_INDICE if f in pedidos]


def _cabecera_indice(manifiestos: bool) -> list[str]:
    """Párrafo introductorio del índice (explica por qué un documento se repite
    entre experiencias de la misma obra). La línea del manifiesto solo aparece si
    el manifiesto se está generando (`PIVOTE_MANIFIESTOS_ZIP`)."""
    lineas = [
        "Cada experiencia contiene su árbol completo de documentos; los que",
        "se comparten entre experiencias de una misma obra se repiten para",
        "navegación directa y el índice lo indica.",
    ]
    if manifiestos:
        lineas.append("El MANIFIESTO_DOCUMENTOS.txt de cada carpeta lista "
                      "su contenido con la huella SHA-256.")
    return lineas


# Campos del registro por experiencia que se publican en `indice.json` (el
# registro lleva además claves internas con "_" que no son parte del contrato).
_CAMPOS_INDICE_JSON = (
    "n_prof", "cargo", "n_exp", "proyecto", "documentos", "compartidos",
    "propios", "notas", "sin_documentos", "motivo", "secciones_incompletas",
    "advertencias", "seace", "procedencia", "identificacion", "estado_fuentes",
)


def _linea_candado_seace(info: dict) -> Optional[str]:
    """Separar coincidencia de datos del proceso de revisión de sus archivos."""
    seace = info.get("seace") if isinstance(info.get("seace"), dict) else {}
    candado = seace.get("candado") if isinstance(seace.get("candado"), dict) else {}
    from validacion.candado_seace import observaciones_temporales, rotulo
    texto = rotulo(candado.get("resultado"))
    if not texto:
        if seace.get("estado") != "seleccionado":
            return None
        texto = "Por confirmar — sin cotejo de datos del proceso registrado"
    if candado.get("resultado") == "confirmado":
        texto = "Coincidencias en los datos del proceso"
    observaciones = observaciones_temporales(candado)
    if observaciones:
        texto += "\nObservación de fechas: " + " ".join(observaciones)
    return (f"Proceso SEACE (datos de contratación): {texto}\n"
            "Contenido de los documentos: por confirmar el tipo de documento "
            "y su vínculo con el encargo. Descargar no equivale a verificar.")


def _indice_txt(meta: dict, registros: list[dict], cabecera: list[str]) -> str:
    """Conserva la línea histórica y añade procedencia sin cambiar los conteos."""
    lineas = [f"ZIP InfoObras · {meta['concurso']}",
              f"Postor: {meta['postor']}", ""]
    if cabecera:
        lineas += cabecera + [""]
    for r in registros:
        prefijo = (f"[P{r['n_prof']:02d} / E{r['n_exp']}]  {r['cargo']} · "
                   f"{r['proyecto'][:70]}: ")
        if r["sin_documentos"]:
            lineas.append(f"{prefijo}SIN DOCUMENTOS — {r['motivo']}")
        else:
            if r["compartidos"]:
                detalle = (f"{r['documentos']} documento(s) · "
                           f"{r['compartidos']} compartido(s) con otras "
                           f"experiencias de esta obra · "
                           f"{r['propios']} propio(s) del periodo")
            else:
                detalle = f"{r['documentos']} documento(s)"
            nota_txt = f" + {r['notas']} nota(s)" if r["notas"] else ""
            lineas.append(f"{prefijo}{detalle}{nota_txt}")
        lineas.append(f"  {rotulo_cui(r['procedencia'])}")
        if r.get("identificacion"):
            lineas.append(f"  Identificación: {r['identificacion']['etiqueta']}")
        if r.get("seace"):
            lineas.append(f"  {r['seace']}")
        for s in r["secciones_incompletas"]:
            lineas.append(f"  SECCIÓN {s['seccion']}: {s['estado']}")
        for aviso in r["advertencias"]:
            lineas.append(f"  ADVERTENCIA: {aviso}")
    return "\n".join(lineas) + "\n"


def _indice_md(meta: dict, registros: list[dict], cabecera: list[str]) -> str:
    """Índice LEGIBLE para el evaluador: una sección por profesional y una
    subsección por experiencia, con el nombre COMPLETO del proyecto (en el txt
    se recorta a 70 y quedaba un muro de líneas kilométricas)."""
    out = [f"# ZIP InfoObras · {meta['concurso']}", "",
           f"**Postor:** {meta['postor']}", ""]
    if cabecera:
        out += cabecera + [""]
    prof_actual: Any = object()
    vistas: dict[str, int] = {}
    for r in registros:
        if r["n_prof"] != prof_actual:
            prof_actual = r["n_prof"]
            vistas = {}          # "misma obra que E…" se compara dentro del profesional
            out += [f"## P{r['n_prof']:02d} · {r['cargo']}", ""]
        grupo = r.get("_grupo_obra")
        previa = vistas.get(grupo) if grupo else None
        if previa is not None:
            out += [f"### E{r['n_exp']} · misma obra que E{previa}", "",
                    f"*{r['proyecto']}*", ""]
        else:
            out += [f"### E{r['n_exp']} · {r['proyecto']}", ""]
            if grupo:
                vistas[grupo] = r["n_exp"]
        if r["sin_documentos"]:
            out.append(f"- **Sin documentos** — {r['motivo']}")
        else:
            nota = ""
            if r["notas"]:
                nota = f" (+{r['notas']} nota{'s' if r['notas'] != 1 else ''})"
            if r["compartidos"]:
                out.append(f"- **Documentos:** {r['documentos']} — "
                           f"{r['compartidos']} compartidos con otras experiencias "
                           f"de esta obra, {r['propios']} propios del periodo{nota}")
            else:
                out.append(f"- **Documentos:** {r['documentos']}{nota}")
        out.append(f"- {rotulo_cui(r['procedencia'])}")
        if r.get("identificacion"):
            out.append(f"- Identificación: {r['identificacion']['etiqueta']}")
        if r.get("seace"):
            out.append(f"- {r['seace']}")
        for s in r["secciones_incompletas"]:
            out.append(f"- {s['seccion']}: {s['estado']}")
        for aviso in r["advertencias"]:
            out.append(f"- ⚠ {aviso}")
        out.append("")
    return "\n".join(out) + "\n"


def _indice_json(meta: dict, registros: list[dict]) -> str:
    """Índice ESTRUCTURADO (para integraciones y para depurar un entregable sin
    abrirlo): los mismos datos que ven el txt y el md, sin formato."""
    datos = {
        "concurso": meta["concurso"],
        "postor": meta["postor"],
        "experiencias": [{c: r[c] for c in _CAMPOS_INDICE_JSON} for r in registros],
    }
    return json.dumps(datos, ensure_ascii=False, indent=2) + "\n"


def _estado_seccion_legible(estado: dict, nombre: str = "documentos") -> str:
    """Estado del manifiesto en lenguaje de evaluador, sin nombres internos.

    `publicados` (inventario COMPLETO de la sección en la fuente) distingue dos
    ausencias que antes se leían igual: la obra no tiene nada publicado, o sí
    tiene pero todo de años ajenos al periodo del certificado (issue #81, R3).
    """
    estado = estado or {}
    e = estado.get("estado")
    bajados = int(estado.get("descargados") or 0)
    esperados = int(estado.get("esperados") or 0)
    publicados = int(estado.get("publicados") or 0)
    if e == "sin_documentos":
        if publicados:
            detalle = (f"{publicados} publicados, todos de otros años"
                       if publicados != 1 else "1 publicado, de otro año")
            return (f"los {nombre.lower()} publicados no corresponden al periodo "
                    f"de este certificado ({detalle})")
        return "sin documentos recuperados en la consulta (0 disponibles)"
    if e == "completa":
        return f"completa ({bajados}/{esperados})"
    if e == "parcial":
        return f"incompleta ({bajados}/{esperados} descargados)"
    if e == "error":
        if not esperados and not bajados:
            # La consulta ni siquiera pudo listar qué había: un (0/0) no dice nada.
            return "la fuente no respondió en la única consulta realizada"
        return f"consulta fallida ({bajados}/{esperados} descargados)"
    return f"por verificar ({bajados}/{esperados} descargados)"


def _lineas_ficha_infoobras(info: dict) -> list[str]:
    """Procedencia de la ficha, separada de la identidad CUI y del éxito de red."""
    ficha = info.get("obra_ficha") or info.get("ficha") or {}
    consultada = ficha.get("obra_id") or ficha.get("codigo_infoobras")
    inicial = (info.get("obra_inicial") or info.get("obra") or {}).get("obra_id")
    lineas = []
    if consultada:
        lineas.append(f"Ficha InfoObras consultada para el contraste: {consultada}")
    if inicial and consultada and str(inicial) != str(consultada):
        lineas.append(f"Ficha de la búsqueda inicial: {inicial} (no es la ficha del contraste)")
    documental = (info.get("descargas_reales") or {}).get("obra_id")
    if documental:
        lineas.append(f"Ficha InfoObras utilizada para solicitar documentos: {documental}")
    return lineas


def construir_zip_infoobras(
    espejo: dict,
    descargas: dict[tuple[int, int], Path],
    salida: Path,
    enriquecimiento: Optional[dict] = None,
) -> Path:
    """Arma el ZIP del análisis: Proyecto → Profesional → Experiencia → archivos.

    `descargas`: {(n_prof, n_exp): directorio con los documentos descargados}.
    Las experiencias sin entrada llevan SIN_DOCUMENTOS.txt. IDENTIFICACION.txt
    conserva la procedencia aun sin índice o PDFs; no cuenta como descarga.
    `enriquecimiento`: {"n_prof:n_exp": {cui, via, ...}}. Sin enriquecimiento
    no se presenta el CUI declarado como utilizado por el backend.

    Dos variables de entorno ajustan el entregable sin tocar el árbol:
    `PIVOTE_MANIFIESTOS_ZIP` (manifiesto SHA-256 por experiencia, default sí) y
    `PIVOTE_INDICE_ZIP` (formatos del índice: `txt` por default, más `md` y/o
    `json`). Ninguna cambia qué documentos entran al ZIP.
    """
    enr = enriquecimiento or {}
    # Import diferido: el paquete orquestador importa a su vez entregables.
    from orquestador.descargas_seace import (
        es_archivo_seace, nota_seace_ausencia, NOTA_SEACE_DESCARGA_FALLIDA,
    )
    from resolucion.cui import TIPO_EXPEDIENTES, tipo_evaluacion_del_espejo
    es_expediente = tipo_evaluacion_del_espejo(espejo) == TIPO_EXPEDIENTES
    manifiestos = _manifiestos_activos()   # PIVOTE_MANIFIESTOS_ZIP (default: 1)
    formatos = _formatos_indice()          # PIVOTE_INDICE_ZIP     (default: txt)
    raiz = _ruta_segura(espejo.get("_meta", {}).get("concurso") or "concurso")
    meta_indice = {"concurso": raiz,
                   "postor": espejo.get("_meta", {}).get("postor") or "—"}
    # Una entrada por experiencia con los DATOS del índice (no texto): cada
    # formato se renderiza después desde aquí. Antes se armaban las líneas del
    # txt en el bucle y agregar un formato obligaba a duplicar la lógica.
    registros: list[dict] = []

    salida.parent.mkdir(parents=True, exist_ok=True)
    # Se arma en un `.tmp` único y se renombra atómicamente al final → `salida`
    # SOLO aparece cuando está completo. Sin esto, una descarga concurrente sirve
    # el ZIP a medio escribir y h11 aborta ("Too much data for declared Content-Length").
    tmp = salida.with_name(f"{salida.name}.{os.urandom(4).hex()}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Cada experiencia lleva su árbol COMPLETO de documentos: el evaluador
        # navega P/E con doble clic, sin indirecciones (correctivo issue #80 —
        # la deduplicación pertenece a la DESCARGA, no a la entrega). El índice
        # sí explica qué contenidos se comparten entre experiencias de la misma
        # obra, y el MANIFIESTO de cada carpeta deja la huella SHA-256
        # (opcional: `PIVOTE_MANIFIESTOS_ZIP=0` lo omite, ver `_manifiestos_activos`).
        vistos_por_obra: dict[str, set[str]] = {}
        for prof in espejo.get("profesionales", []):
            n_prof = prof.get("n_prof")
            # Carpeta corta y navegable: "P08 Estructuras" en vez del cargo completo
            # (hasta 80 chars). Se elimina además el nivel del concurso (lo aportan el
            # nombre del ZIP y el indice.txt) → la ruta total queda holgada bajo el
            # límite de 260 de Windows al EXTRAER (antes reventaba al copiar/descomprimir).
            nivel2 = _corto(f"P{n_prof:02d} {_cargo_corto(prof.get('cargo', ''))}", 22)
            for e in prof.get("experiencias", []):
                n_exp = e.get("n")
                nivel3 = _carpeta_experiencia(n_exp, e.get("proyecto"))
                base = f"{nivel2}/{nivel3}"
                proyecto = str(e.get("proyecto") or "sin proyecto")

                origen = descargas.get((n_prof, n_exp))
                info = enr.get(f"{n_prof}:{n_exp}") or {}
                proyeccion = proyectar_identidad(
                    e, info, "expedientes" if es_expediente else "obras")
                procedencia = proyeccion["procedencia"]
                identificacion = proyeccion["identificacion"]
                detalle_cui = proyeccion["rotulo_cui"]
                lineas_identidad = [detalle_cui,
                                    f"Vía: {procedencia['via'] or 'no informada'}"]
                lineas_identidad.extend(_lineas_ficha_infoobras(info))
                lineas_identidad.extend(lineas_contraste_servicio(espejo, e))
                lineas_identidad.extend(lineas_estado_fuentes(info))
                if identificacion:
                    lineas_identidad.append(f"Identificación: {identificacion['etiqueta']}")
                datos_subobras = [s for s in (info.get("sub_obras") or [])
                                  if isinstance(s, dict)]
                for pos, sub in enumerate(procedencia['sub_obras'], 1):
                    lineas_identidad.append(
                        f"Sub-obra {pos}: {sub['nombre'] or 'sin nombre registrado'} · "
                        f"CUI: {sub['cui'] or 'no registrado'} · "
                        f"Estado: {sub['estado'] or 'no informado'}")
                    datos_sub = datos_subobras[pos - 1]
                    lineas_identidad.extend(
                        f"  {linea}" for linea in _lineas_ficha_infoobras(datos_sub))
                zf.writestr(f"{base}/IDENTIFICACION.txt", "\n".join(lineas_identidad) + "\n")
                manifiesto = (info.get("descargas_reales")
                              if isinstance(info.get("descargas_reales"), dict) else {})
                reg: dict[str, Any] = {
                    "n_prof": n_prof, "cargo": prof.get("cargo", ""),
                    "n_exp": n_exp, "proyecto": proyecto,
                    "documentos": 0, "compartidos": 0, "propios": 0, "notas": 0,
                    "sin_documentos": True, "motivo": None,
                    "secciones_incompletas": [], "advertencias": [],
                    "seace": _linea_candado_seace(info),
                    "procedencia": procedencia, "identificacion": identificacion,
                    "estado_fuentes": proyectar_estado_fuentes(info),
                    "_grupo_obra": None,
                }
                registros.append(reg)
                if origen and Path(origen).is_dir():
                    # Un temporal nunca es un entregable. Las notas de error sí se
                    # incluyen, pero no cuentan como documentos descargados.
                    archivos = [p for p in sorted(Path(origen).rglob("*"))
                                if p.is_file() and p.suffix.lower() != ".part"
                                and p.name.upper() != "IDENTIFICACION.TXT"]
                    reales = [p for p in archivos
                              if not p.name.upper().endswith(
                                  ("_ERROR.TXT", "_NO_DISPONIBLE.TXT", "SIN_DOCUMENTOS.TXT",
                                   "DOCUMENTOS_MEF.JSON", "DOCUMENTOS_MEF.TXT",
                                   "DOCUMENTOS_SEACE.JSON", "DOCUMENTOS_SEACE.TXT"))]
                    notas = [p for p in archivos if p not in reales]
                    # Notas y documentos van AMBOS al árbol de la experiencia,
                    # conservando sus subcarpetas de sección.
                    for p in archivos:
                        rel = p.relative_to(origen)
                        partes = "/".join(_ruta_segura(x, 38) for x in rel.parts)
                        info_archivo = info
                        sub_match = re.fullmatch(r"Subobra (\d+)", rel.parts[0])
                        if len(rel.parts) > 1 and sub_match:
                            sub_pos = int(sub_match.group(1)) - 1
                            sub_obras = info.get("sub_obras") or []
                            if 0 <= sub_pos < len(sub_obras):
                                info_archivo = sub_obras[sub_pos]
                        # Las notas generadas no son evidencia original. Al armar
                        # el entregable se actualiza su explicación, sin tocar la
                        # carpeta histórica ni los documentos descargados.
                        if p.name.upper() == "SIN_DOCUMENTOS.TXT":
                            if info_archivo is not info:
                                # La nota de la sub-obra conserva su identidad y
                                # motivo; no reemplazarla por el total del padre.
                                zf.write(p, f"{base}/{partes}")
                            else:
                                zf.writestr(f"{base}/{partes}",
                                            f"{detalle_cui}\nDocumentos incorporados: {len(reales)}.\n"
                                            "La ausencia de archivos no demuestra que no estén publicados.\n")
                        elif es_archivo_seace(p.name) and p.name.upper().endswith("_NO_DISPONIBLE.TXT"):
                            seace = info_archivo.get("seace") or {}
                            zf.writestr(f"{base}/{partes}", nota_seace_ausencia(seace.get("estado")) + "\n")
                        elif es_archivo_seace(p.name) and p.name.upper().endswith("_ERROR.TXT"):
                            # Se conservan detalles técnicos, neutralizando la
                            # explicación antigua de publicación, si la hubiera.
                            texto = p.read_text(encoding="utf-8", errors="replace")
                            texto = texto.replace(
                                "No se pudo obtener este documento en la única consulta realizada. "
                                "El proceso sí lo publica, pero el archivo no quedó disponible.",
                                NOTA_SEACE_DESCARGA_FALLIDA)
                            zf.writestr(f"{base}/{partes}", texto)
                        else:
                            zf.write(p, f"{base}/{partes}")
                    manifiesto_docs: list[str] = [
                        "Documento técnico de verificación — el equipo de "
                        "evaluación puede ignorarlo.",
                        "DOCUMENTOS DE ESTA EXPERIENCIA",
                        "Cada línea conserva: ruta -> SHA-256 (huella del contenido).",
                        "Un mismo SHA-256 en otra experiencia = el mismo documento.",
                        "",
                    ]
                    obra = info.get("obra") if isinstance(info.get("obra"), dict) else {}
                    obra_id = obra.get("obra_id")
                    # Sin obra resuelta no se atribuye una coincidencia casual de
                    # hash a otra experiencia: cada P/E forma su propio grupo.
                    grupo_obra = str(obra_id) if obra_id else f"P{n_prof}:E{n_exp}"
                    reg["_grupo_obra"] = str(obra_id) if obra_id else None
                    reg["notas"] = len(notas)
                    vistos_antes = vistos_por_obra.setdefault(grupo_obra, set())
                    digests: list[str] = []
                    for p in reales:
                        digest = _sha256_archivo(p)
                        digests.append(digest)
                        rel = "/".join(str(x) for x in p.relative_to(origen).parts)
                        manifiesto_docs.append(f"{rel} -> {digest}")
                    if reales and manifiestos:
                        zf.writestr(f"{base}/MANIFIESTO_DOCUMENTOS.txt",
                                    "\n".join(manifiesto_docs) + "\n")
                    if not reales:
                        motivo = ("la carpeta no contiene documentos utilizables; "
                                  "ver estados de consulta y descarga en IDENTIFICACION.txt")
                        if not any(p.name.upper() == "SIN_DOCUMENTOS.TXT" for p in archivos):
                            zf.writestr(
                                f"{base}/SIN_DOCUMENTOS.txt",
                                f"Sin documentos descargados para esta experiencia.\n"
                                f"{detalle_cui}\nMotivo: {motivo}\n",
                            )
                        reg["motivo"] = motivo
                    else:
                        compartidos_n = sum(digest in vistos_antes for digest in digests)
                        reg.update(sin_documentos=False, documentos=len(reales),
                                   compartidos=compartidos_n,
                                   propios=len(reales) - compartidos_n)
                    vistos_antes.update(digests)

                    for nombre, estado in (manifiesto.get("secciones") or {}).items():
                        if (estado or {}).get("estado") != "completa":
                            reg["secciones_incompletas"].append(
                                {"seccion": nombre,
                                 "estado": _estado_seccion_legible(estado, nombre)})
                    reg["advertencias"] = [normalizar_motivo_fuente(aviso)
                                           for aviso in manifiesto.get("avisos") or []]
                else:
                    motivo = _motivo_sin_docs(info.get("via"), procedencia['cui_utilizado'])
                    zf.writestr(
                        f"{base}/SIN_DOCUMENTOS.txt",
                        f"Sin documentos descargados para esta experiencia.\n"
                        f"{detalle_cui}\nMotivo: {motivo}\n",
                    )
                    reg["motivo"] = motivo

        cabecera = _cabecera_indice(manifiestos) if any(vistos_por_obra.values()) else []
        if "txt" in formatos:
            zf.writestr("indice.txt", _indice_txt(meta_indice, registros, cabecera))
        if "md" in formatos:
            zf.writestr("indice.md", _indice_md(meta_indice, registros, cabecera))
        if "json" in formatos:
            zf.writestr("indice.json", _indice_json(meta_indice, registros))
    os.replace(tmp, salida)   # atómico: recién aquí `salida` existe y está completo
    return salida


# ── Descarga de UN solo CUI (endpoint suelto, sin correr un análisis) ─────────

def _zip_carpeta(carpeta: Path, salida: Path, titulo: str = "") -> Path:
    """ZIP plano de `carpeta` conservando su árbol relativo, con rename atómico. Cada
    componente de ruta se sanea y capa (`_ruta_segura`) para no reventar el límite de
    260 de Windows al extraer. Usado por la descarga por CUI (sin espejo/profesionales)."""
    carpeta = Path(carpeta)
    salida.parent.mkdir(parents=True, exist_ok=True)
    tmp = salida.with_name(f"{salida.name}.{os.urandom(4).hex()}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if titulo:
            zf.writestr("indice.txt", titulo + "\n")
        if carpeta.is_dir():
            for p in sorted(carpeta.rglob("*")):
                if p.is_file() and p.suffix.lower() != ".part":
                    partes = "/".join(_ruta_segura(x, 38) for x in p.relative_to(carpeta).parts)
                    zf.write(p, partes)
    os.replace(tmp, salida)
    return salida


def descargar_cui(
    cui: str,
    destino: Path,
    *,
    fecha_inicio: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    fetch=None,
    session: Optional[requests.Session] = None,
    timeout: float = 90.0,
    dir_cache: Optional[Path] = None,
    progreso=None,
) -> dict:
    """Resuelve el obra_id del CUI y baja TODOS sus documentos de InfoObras a `destino/`
    con el mismo árbol que el ZIP de un análisis: valorizaciones por hito + documentos
    obra-level + informes de control del periodo + datos de cierre + aprobación de
    expediente (si la obra es de expediente). Es el motor del endpoint "descargar por
    un solo CUI", desacoplado del pipeline.

    Corre sobre `CacheDescargasInfoObras` (issue #81, R5), igual que el pipeline:
    el corpus se baja a una entrada de caché, se publica de forma atómica y recién
    entonces se materializa en `destino` (los informes se filtran localmente por el
    periodo). El alcance de esa caché es la DESCARGA en curso — `dir_cache` por
    defecto es una carpeta hermana de `destino`, jamás una caché global compartida
    entre pedidos (decisión D3 de la issue #80: nada de datos que caducan a
    espaldas de quien pide).

    Devuelve `{cui, obra_id, nombre, descargados, fallidos, secciones, avisos,
    error}`. `descargados`/`fallidos` cubren TODAS las secciones, no solo las
    valorizaciones. `fetch` es inyectable para tests; con red real usa
    `fetch_by_cui`. NO corre en tests offline salvo con `fetch` inyectado (y las
    descargas monkeypatcheadas).

    `progreso` es un callable opcional que recibe UNA frase en castellano por
    tramo ("Descargando los informes de control…"). Existe porque esto tarda
    minutos y quien espera merece saber en qué va; si falla, no se lleva la
    descarga por delante (un contador roto no puede costar el corpus)."""
    def _paso(mensaje: str) -> None:
        if progreso is None:
            return
        try:
            progreso(mensaje)
        except Exception:  # noqa: BLE001 — informar el avance jamás rompe la descarga
            logger.debug("descargar_cui %s: fallo al reportar progreso", cui)

    if fetch is None:
        from scraping.infoobras import fetch_by_cui as fetch
    _paso("Buscando la obra en InfoObras a partir del CUI.")
    obra = fetch(str(cui).strip(), fecha_inicio, fecha_fin, None)
    obra_id = getattr(obra, "obra_id", None) if obra is not None else None
    if obra_id is None:
        return {"cui": cui, "obra_id": None, "nombre": None,
                "descargados": 0, "fallidos": 0, "secciones": {}, "avisos": [],
                "error": "el CUI no resolvió a ninguna obra en InfoObras"}

    from orquestador.descargas_infoobras import CacheDescargasInfoObras
    sess = session or requests.Session()
    destino = Path(destino)
    aprob = getattr(obra, "aprobacion_expediente", None)

    def _bajar(ruta: Path, pendientes) -> dict:
        """Corpus completo de la obra en la caché; cada sección informa su estado
        y una caída se registra (antes se perdía en un `logger.debug`)."""
        def _toca(seccion: str) -> bool:
            return pendientes is None or seccion in pendientes

        estado: dict = {"secciones": {}, "avisos": [], "informes_anios": []}
        if _toca("InfoObras"):
            _paso("Descargando las valorizaciones y los documentos de la obra.")
            try:
                r = descargar_documentos_obra_por_hito(
                    obra_id, ruta, session=sess, timeout=timeout)
                estado["secciones"]["InfoObras"] = {
                    "esperados": (r.get("descargados") or 0) + (r.get("fallidos") or 0),
                    "descargados": r.get("descargados") or 0,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("descargar_cui %s documentos de obra: %s", cui, corto(e))
                estado["secciones"]["InfoObras"] = {"error": True}
                estado["avisos"].append(
                    "InfoObras: la consulta de documentos de la obra no pudo "
                    "completarse.")
        if _toca("Informes de control"):
            # Se bajan TODOS y el filtro por periodo lo hace la materialización
            # (misma semántica anual inclusiva que el pipeline).
            _paso("Descargando los informes de control de la Contraloría.")
            try:
                control = descargar_informes_control(obra_id, ruta, session=sess) or {}
                estado["informes_anios"] = control.get("anios") or []
                estado["secciones"]["Informes de control"] = {
                    "esperados": control.get("encontrados") or 0,
                    "descargados": control.get("descargados") or 0,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("descargar_cui %s informes de control: %s", cui, corto(e))
                estado["secciones"]["Informes de control"] = {"error": True}
                estado["avisos"].append(
                    "Informes de control: la consulta no pudo completarse.")
        if _toca("Datos de cierre"):
            _paso("Descargando los datos de cierre de la obra.")
            try:
                cierre = descargar_datos_cierre(obra_id, ruta, session=sess) or {}
                estado["secciones"]["Datos de cierre"] = {
                    "esperados": cierre.get("encontrados") or 0,
                    "descargados": cierre.get("descargados") or 0,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("descargar_cui %s datos de cierre: %s", cui, corto(e))
                estado["secciones"]["Datos de cierre"] = {"error": True}
                estado["avisos"].append(
                    "Datos de cierre: la consulta no pudo completarse.")
        if aprob and _toca("Aprobación del expediente"):
            _paso("Descargando la aprobación del expediente técnico.")
            try:
                bajo = descargar_aprobacion_expediente(aprob, ruta, session=sess)
                estado["secciones"]["Aprobación del expediente"] = {
                    "esperados": 1, "descargados": int(bool(bajo)),
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("descargar_cui %s aprobación: %s", cui, corto(e))
                estado["secciones"]["Aprobación del expediente"] = {"error": True}
                estado["avisos"].append(
                    "Aprobación del expediente: la descarga falló.")
        return estado

    raiz_cache = (Path(dir_cache) if dir_cache is not None
                  else destino.parent / f"{destino.name}.cache")
    cache = CacheDescargasInfoObras(raiz_cache)
    cache.recolectar_temporales()
    resultado = cache.obtener(obra_id, descargar=_bajar)
    _paso("Ordenando los documentos descargados.")
    cache.materializar(resultado, destino,
                       fecha_ini=fecha_inicio, fecha_fin=fecha_fin)

    secciones = (resultado.estado.get("secciones") or {})
    descargados = sum(int(s.get("descargados") or 0) for s in secciones.values())
    # Un fallo es un documento que la fuente publicaba y no llegó, MÁS cada
    # sección que ni siquiera pudo consultarse.
    fallidos = sum(
        max(0, int(s.get("esperados") or 0) - int(s.get("descargados") or 0))
        for s in secciones.values() if not s.get("error")
    ) + sum(1 for s in secciones.values() if s.get("error"))
    return {"cui": cui, "obra_id": obra_id, "nombre": getattr(obra, "nombre", None),
            "descargados": descargados, "fallidos": fallidos,
            "secciones": secciones,
            "avisos": list(resultado.estado.get("avisos") or []),
            "error": None}
