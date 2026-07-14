"""
Verificación de EXPEDIENTES técnicos contra el MEF (Banco de Inversiones / SSI).

Todo por `requests`, sin navegador ni captcha (validado en vivo 13-jul sobre 13
CUIs; ver docs/plan-integracion-verificacion-expedientes.md). Fuentes:

  GET  /invierte/ejecucion/verFichaEjecucion/{CUI}   → Formato 08-A (HTML server-rendered)
  POST /invierteWS/Ssi/traeContratoSeaceDWH          → contratos SEACE (JSON limpio)
  downloadArchivoPublico / URL_CONTRATO              → PDFs (resolución de aprobación, contrato)

Diseño: las funciones de PARSEO/CONTRASTE son PURAS (testeables offline con
tests/fixtures/mef/). Solo los fetch/descarga tocan red → NO corren en tests offline.
Mismo patrón que scraping/infoobras.py (session con UA, reintentos, `corto`).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from html import unescape
from typing import Optional
from urllib.parse import urljoin

import requests

from scraping.errores_red import corto

logger = logging.getLogger(__name__)

BASE = "https://ofi5.mef.gob.pe"
FICHA_08A = BASE + "/invierte/ejecucion/verFichaEjecucion/"
CONTRATOS_DWH = BASE + "/invierteWS/Ssi/traeContratoSeaceDWH"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_RETRIES = 3
_BACKOFF = 1.5

_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
# etiquetas que delatan la resolución de aprobación del expediente (varía por entidad)
_RE_APROB = re.compile(r"resoluci[oó]n|R\.?\s?G\.?\s?R\.?|aprobaci[oó]n|acta de aprob", re.I)
_RE_NUM_RES = re.compile(r"N[°ºo]?\s*(\d[\w.\-/]*)")   # exige dígito tras la N°


def _score_aprobacion(label: str) -> int:
    """Rankea qué tan 'resolución de aprobación' se ve una etiqueta: preferimos las
    que arrancan con RESOLUCIÓN/RGR/APROBACIÓN y traen número; penalizamos las que
    arrancan con CONTRATO (son del contrato, no de la resolución)."""
    s = 0
    if re.match(r"\s*(resoluci[oó]n|r\.?\s?g\.?\s?r|aprobaci[oó]n)", label, re.I):
        s += 2
    if _RE_NUM_RES.search(label):
        s += 1
    if re.match(r"\s*contrato", label, re.I):
        s -= 1
    return s


# ── helpers puros ────────────────────────────────────────────────────────────

def _texto(html: str) -> str:
    """HTML → texto plano: des-escapa entidades, quita tags, colapsa espacios."""
    return _RE_WS.sub(" ", _RE_TAG.sub(" ", unescape(html or ""))).strip()


def _num(v) -> Optional[float]:
    """Coacciona a float un valor del JSON (int/float/str) o de texto con
    formato peruano '21,676,278.41'. None si no hay número."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d[\d.,]*", str(v))   # ancla en un dígito (evita el '.' de 'S/.')
    if not m:
        return None
    s = m.group(0).replace(",", "")   # coma = miles en formato peruano
    try:
        return float(s)
    except ValueError:
        return None


def _fecha(texto) -> Optional[date]:
    """'DD/MM/YYYY' → date. None si no parsea."""
    if not texto:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(texto))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(0), "%d/%m/%Y").date()
    except ValueError:
        return None


_SUFIJOS = re.compile(
    r"\b(s\.?a\.?c\.?|e\.?i\.?r\.?l\.?|s\.?r\.?l\.?|s\.?a\.?|sociedad|comercial|"
    r"de responsabilidad limitada|anonima|cerrada|contratistas?|generales?|"
    r"consultor(?:a|es)?|ingenieros?|constructora?)\b", re.I)


def _norm(s: str) -> str:
    """Normaliza un nombre para comparar: sin tildes, mayúsculas, sin sufijos
    societarios ni puntuación → deja el núcleo (apellidos/razón distintiva)."""
    s = (s or "").upper()
    for a, b in zip("ÁÉÍÓÚÜÑ", "AEIOUUN"):
        s = s.replace(a, b)
    s = _SUFIJOS.sub(" ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return _RE_WS.sub(" ", s).strip()


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) >= 3}


def _nombres_coinciden(a: str, b: str) -> bool:
    """True si dos nombres refieren (probablemente) a la misma persona/empresa:
    substring de núcleos o ≥2 tokens distintivos en común."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return len(_tokens(a) & _tokens(b)) >= 2


# ── parseo del Formato 08-A (puro) ───────────────────────────────────────────

def _documentos_08a(html: str) -> list[dict]:
    """Extrae los documentos descargables (downloadArchivoPublico) con etiqueta.
    Descarta los de idArchivo o etiqueta vacíos (ruido de la plantilla). Marca
    `es_aprobacion` por el texto del enlace."""
    out, vistos = [], set()
    for m in re.finditer(
        r'href="([^"]*downloadArchivoPublico\?idArchivo=([^"&]*)[^"]*)"[^>]*>([^<]*)',
        html,
    ):
        url, idar, label = m.group(1), m.group(2).strip(), unescape(m.group(3)).strip()
        if not idar or not label or idar in vistos:
            continue
        vistos.add(idar)
        out.append({
            "label": label,
            "url": urljoin(BASE, url.replace("&amp;", "&")),
            "es_aprobacion": bool(_RE_APROB.search(label)),
        })
    return out


def parsear_ficha_08a(html: str) -> dict:
    """Formato 08-A (HTML) → dict con lo que importa para verificar un expediente:
    etapa/estado del registro, presencia de la sección B, costo total, los
    documentos descargables y la mejor candidata a resolución de aprobación.
    Función PURA (tests offline)."""
    txt = _texto(html)
    etapa = estado = None
    m = re.search(r"ETAPA:\s*(.*?)\s*ESTADO:", txt, re.I)
    if m:
        etapa = m.group(1).strip() or None
    m = re.search(r"ESTADO:\s*([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚ ]{2,40})", txt)
    if m:
        estado = m.group(1).strip() or None

    costo_total = None
    m = re.search(r"Costo total de la inversi[oó]n actualizado:?\s*S/\.?\s*([\d.,]+)", txt, re.I)
    if m:
        costo_total = _num(m.group(1))
    monto_exp = None
    m = re.search(r"EXPEDIENTE T[EÉ]CNICO:?\s*S/\.?\s*([\d.,]+)", txt, re.I)
    if m:
        monto_exp = _num(m.group(1))

    seccion_b = bool(re.search(r"B\.\s*Datos de la fase de Ejecuci[oó]n", txt, re.I))
    docs = _documentos_08a(html)
    # entre los documentos de aprobación (puede haber varios: original + modificaciones),
    # el mejor candidato a resolución es el que más se ve como tal.
    aprobs = sorted((d for d in docs if d["es_aprobacion"]),
                    key=lambda d: -_score_aprobacion(d["label"]))
    resolucion = None
    if aprobs:
        elegido = aprobs[0]
        mnum = _RE_NUM_RES.search(elegido["label"])
        resolucion = {"documento": elegido["label"], "url": elegido["url"],
                      "numero": mnum.group(1).strip() if mnum else None}

    return {
        "etapa": etapa,
        "estado_registro": estado,
        "seccion_b": seccion_b,
        "costo_total": costo_total,
        "monto_expediente": monto_exp,
        "documentos": docs,
        "resolucion": resolucion,
        "tiene_ficha": bool(etapa or estado or seccion_b or docs),
    }


# ── parseo de los contratos SEACE (puro) ─────────────────────────────────────

def normalizar_contratos(raw: list) -> list[dict]:
    """Lista cruda del endpoint DWH → contratos normalizados y DEDUPLICADOS
    (el DWH repite filas). Función PURA (tests offline)."""
    out, vistos = [], set()
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        numero = (c.get("NUM_CONTRATO") or "").strip()
        if not numero:
            continue
        monto = _num(c.get("MTO_TOTAL"))
        clave = (numero, monto)
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append({
            "numero": numero,
            "contratista": (c.get("NOM_CONTRATISTA") or "").strip(),
            "monto": monto,
            "objeto": (c.get("DES_PROCESO") or c.get("DES_ITEM") or "").strip(),
            "nomenclatura": (c.get("NOMENCLATURA") or "").strip(),
            "fecha_suscripcion": _fecha(c.get("FEC_SUSCRIPCION")),
            "valor_referencial": _num(c.get("VALOR_REFER")),
            "url_pdf": (c.get("URL_CONTRATO") or "").strip() or None,
        })
    return out


def contrato_de_expediente(contratos: list[dict]) -> Optional[dict]:
    """Entre los contratos del CUI, elige el de ELABORACIÓN del expediente (no el
    de supervisión/ejecución de obra). Prefiere objeto 'expediente' sin
    'supervisi/evaluaci/ejecucion/obra'; a igualdad, el de menor monto (el
    expediente suele ser el más barato). Función PURA."""
    exp = [c for c in contratos if re.search(r"expediente|estudio", c["objeto"], re.I)]
    if not exp:
        return None
    puros = [c for c in exp if not re.search(r"supervisi|evaluaci|ejecuci[oó]n|de obra", c["objeto"], re.I)]
    pool = puros or exp
    return min(pool, key=lambda c: (c["monto"] if c["monto"] is not None else float("inf")))


# ── contraste certificado × MEF (puro) ───────────────────────────────────────

def verificar_expediente(exp: dict, ficha: dict, contratos: list[dict]) -> dict:
    """Contrasta una experiencia de expediente (del espejo) contra los datos del
    MEF ya parseados. Devuelve el bloque `verificacion_expediente` con veredicto
    por campo (ok | discrepancia | no_verificable). Función PURA (tests offline).

    Conservador: `ok` solo con match positivo; `no_verificable` cuando el dato no
    está o no se puede cotejar; `discrepancia` solo ante conflicto claro."""
    ficha = ficha or {}
    contratos = contratos or []
    cui = str(exp.get("cui") or "").strip() or None
    emisor = exp.get("nombre_emisor") or exp.get("entidad_emisora") or ""

    bloque: dict = {"cui_confirmado": cui, "fuentes": [], "verificado_en_mef": False}
    c = contrato_de_expediente(contratos)
    if c:
        bloque["fuentes"].append("MEF-SEACE")
        bloque["verificado_en_mef"] = True
        ver_ct = "ok" if _nombres_coinciden(emisor, c["contratista"]) else "no_verificable"
        bloque["contratista"] = {"valor": c["contratista"], "veredicto": ver_ct}
        bloque["contrato"] = {
            "numero": c["numero"], "monto": c["monto"],
            "fecha": c["fecha_suscripcion"].isoformat() if c["fecha_suscripcion"] else None,
            "objeto": c["objeto"][:120] or None,
            "veredicto": "ok",   # el contrato existe en el MEF (autoritativo)
        }
        if c.get("url_pdf"):
            bloque["contrato"]["pdf"] = c["url_pdf"]

    res = ficha.get("resolucion")
    if res:
        bloque["fuentes"].append("MEF-08A")
        bloque["verificado_en_mef"] = True
        bloque["resolucion"] = {"numero": res.get("numero"), "documento": res.get("documento"),
                                "veredicto": "ok"}
    else:
        bloque["resolucion"] = {"veredicto": "no_verificable",
                                "detalle": "sin documento de aprobación en el 08-A del MEF"}

    if not bloque["verificado_en_mef"]:
        bloque["detalle"] = "el CUI no expone contratos ni 08-A en el MEF (¿entidad no cargó?)"
    return bloque


# ── fetch / descarga (RED — no corre en tests offline) ───────────────────────

def crear_session(session: Optional[requests.Session] = None) -> requests.Session:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", _UA)
    return s


def _get(session: requests.Session, url: str, **kw) -> Optional[requests.Response]:
    """GET/POST con reintentos + backoff. None si el portal no respondió."""
    metodo = kw.pop("metodo", "GET")
    for intento in range(_RETRIES):
        try:
            r = session.request(metodo, url, timeout=kw.pop("timeout", 30), **kw)
            if r.status_code == 200:
                return r
            if r.status_code < 500:
                return None   # 4xx → no existe/entrada inválida
        except requests.RequestException as e:
            logger.debug("MEF %s %s intento %d/%d: %s", metodo, url[-40:], intento + 1, _RETRIES, corto(e))
        if intento < _RETRIES - 1:
            time.sleep(_BACKOFF * (2 ** intento))
    return None


def fetch_ficha_08a(cui, session: Optional[requests.Session] = None) -> Optional[str]:
    """HTML del Formato 08-A del CUI, o None si el portal no respondió."""
    r = _get(crear_session(session), f"{FICHA_08A}{cui}")
    return r.text if r is not None else None


def fetch_contratos(cui, codsnip="", session: Optional[requests.Session] = None) -> list[dict]:
    """Contratos SEACE del CUI (crudos del DWH). [] si no hay o el portal falló."""
    r = _get(crear_session(session), CONTRATOS_DWH, metodo="POST",
             data={"id": str(cui), "codsnip": str(codsnip or "0"), "vers": "v2"},
             headers={"X-Requested-With": "XMLHttpRequest"})
    if r is None:
        return []
    try:
        d = r.json()
        return d if isinstance(d, list) else []
    except ValueError:
        return []


def descargar_pdf(session: requests.Session, url: str, destino, *, timeout: float = 60.0) -> bool:
    """Descarga en streaming un PDF (resolución o contrato) a `destino`. Rename
    atómico. Los links del 08-A llevan token de sesión → usar la MISMA session."""
    import os
    from pathlib import Path
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".part")
    for intento in range(_RETRIES):
        try:
            with session.get(url, timeout=timeout, stream=True) as r:
                if r.status_code >= 500:
                    raise OSError(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    return False
                os.makedirs(destino.parent, exist_ok=True)
                n = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
                            n += len(chunk)
                if n == 0:
                    raise OSError("respuesta vacía")
            os.replace(tmp, destino)
            return True
        except (requests.RequestException, OSError) as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            if intento < _RETRIES - 1:
                time.sleep(_BACKOFF * (2 ** intento))
            else:
                logger.debug("MEF descarga %s: %s", url[-40:], corto(e))
    return False


def verificar_cui(exp: dict, cui, codsnip="", session: Optional[requests.Session] = None) -> dict:
    """Orquesta el fetch (RED) + parseo + contraste para un CUI. Devuelve el
    bloque `verificacion_expediente`. Best-effort: si el portal falla, degrada a
    'no verificable' sin lanzar."""
    s = crear_session(session)
    html = fetch_ficha_08a(cui, s)
    ficha = parsear_ficha_08a(html) if html else {}
    contratos = normalizar_contratos(fetch_contratos(cui, codsnip, s))
    return verificar_expediente(exp, ficha, contratos)
