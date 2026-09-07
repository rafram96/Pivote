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
import time   # el backoff duerme en errores_red; se deja para parchear `mef.time.sleep`
from datetime import date, datetime
from html import unescape
from typing import Optional
from urllib.parse import urljoin

import requests

from scraping.errores_red import (
    EXPONENCIAL, Politica, RespuestaTransitoria, con_reintentos, corto,
)
from scraping.nombres_empresa import variantes

logger = logging.getLogger(__name__)

BASE = "https://ofi5.mef.gob.pe"
FICHA_08A = BASE + "/invierte/ejecucion/verFichaEjecucion/"
CONTRATOS_DWH = BASE + "/invierteWS/Ssi/traeContratoSeaceDWH"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_RETRIES = 3
_BACKOFF = 1.5
# Reintentos del portal MEF (ADR-014): misma temporización de siempre —
# exponencial 1.5s, 3.0s entre intentos.
_POLITICA = Politica(intentos=_RETRIES, base=_BACKOFF, modo=EXPONENCIAL)

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


def _coinciden_literal(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return len(_tokens(a) & _tokens(b)) >= 2


def _nombres_coinciden(a: str, b: str) -> bool:
    """True si dos nombres refieren (probablemente) a la misma persona/empresa:
    substring de núcleos o ≥2 tokens distintivos en común.

    El CRITERIO es el de siempre (`_coinciden_literal`). Lo que cambió en
    T-REFACTOR-002 es la ENTRADA: el emisor llega tal como lo tipeó el membrete
    del certificado, así que se prueba también su forma prelimpiada (sin la
    composición del consorcio entre paréntesis) y basta que UNA coincida.
    Monótono: lo que antes daba `ok` sigue dando `ok`."""
    return any(_coinciden_literal(x, y)
               for x in variantes(a) for y in variantes(b))


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


def contratos_de_expediente(contratos: list[dict]) -> list[dict]:
    """TODOS los contratos de elaboración de expediente/estudio del CUI (sin los de
    supervisión/evaluación/ejecución de obra), del más barato al más caro. Un CUI
    puede tener varios (original, actualización, componentes): para saber si el
    emisor de un certificado fue contratista hay que mirarlos todos, no solo el
    que elige `contrato_de_expediente` para la ficha. Función PURA."""
    # «Consultoría DE OBRA para la elaboración del expediente» ES un contrato de
    # expediente (así se llama la contratación en OSCE); lo que se excluye es la
    # supervisión/evaluación/ejecución de la obra, no la palabra «obra».
    exp = [c for c in contratos or [] if re.search(r"expediente|estudio", c.get("objeto") or "", re.I)
           and not re.search(r"supervisi|evaluaci|ejecuci[oó]n\s+de\s+(?:la\s+)?obra",
                             c.get("objeto") or "", re.I)]
    return sorted(exp, key=lambda c: (c.get("monto") if c.get("monto") is not None else float("inf")))


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
    # El contratista del MEF es una empresa/persona contratada, no necesariamente
    # quien firma la constancia. En certificados societarios `nombre_emisor` es
    # el firmante (gerente, representante, etc.) y `entidad_emisora` es la razón
    # social que sí debe cotejarse con el adjudicatario. Para consultores persona
    # natural o jobs antiguos sin entidad conservamos el firmante como fallback.
    empresa_emisora = str(exp.get("entidad_emisora") or "").strip()
    firmante = str(exp.get("nombre_emisor") or "").strip()
    identidad_contratista = empresa_emisora or firmante

    bloque: dict = {
        "cui_confirmado": cui,
        "fuentes": [],
        "verificado_en_mef": False,
        "emisor_certificado": {
            "empresa": empresa_emisora or None,
            "ruc": str(exp.get("ruc_emisor") or "").strip() or None,
            "firmante": firmante or None,
            "cargo_firmante": str(exp.get("cargo_emisor") or "").strip() or None,
        },
    }
    # ELECCIÓN DEL CONTRATO (5-sep-2026). Un CUI puede tener VARIOS contratos de
    # expediente (original, actualización, componentes) y cada uno con distinto
    # contratista. Hasta hoy la ficha mostraba siempre el más barato — el que elige
    # `contrato_de_expediente` — aunque estuviera a nombre de otra empresa, y el
    # Excel lo rotulaba «Por confirmar» pese a que la vía CONTRATO ya había
    # resuelto la experiencia mirando TODOS (casos reales 7:3 y 10:3). Ahora se
    # prefiere el contrato cuyo contratista ES el emisor del certificado; si
    # ninguno lo es, se conserva exactamente la elección de antes.
    ces = contratos_de_expediente(contratos)
    c_emisor = next((x for x in ces
                     if _nombres_coinciden(identidad_contratista, x.get("contratista") or "")),
                    None) if identidad_contratista else None
    c = c_emisor or contrato_de_expediente(contratos)
    if c:
        elegido_por = ("emisor" if c_emisor is not None
                       else ("unico" if len(ces) <= 1 else "mas_barato"))
        otros = [f"{x['numero']} — {x.get('contratista') or 'sin contratista'}"
                 for x in ces if x is not c][:5]
        bloque["fuentes"].append("MEF-SEACE")
        bloque["verificado_en_mef"] = True
        ver_ct = ("ok" if _nombres_coinciden(identidad_contratista, c["contratista"])
                  else "no_verificable")
        bloque["contratista"] = {
            "valor": c["contratista"],
            "declarado": identidad_contratista or None,
            "veredicto": ver_ct,
        }
        bloque["contrato"] = {
            "numero": c["numero"], "monto": c["monto"],
            "fecha": c["fecha_suscripcion"].isoformat() if c["fecha_suscripcion"] else None,
            "objeto": c["objeto"][:120] or None,
            # El contrato solo «coincide» si su contratista es el emisor del
            # certificado. Que exista un contrato para el CUI no dice nada sobre
            # ESTE certificado: antes se rotulaba «ok» por mera existencia y el
            # Excel lo mostraba como ✔ Coincide (fragilidad 4, 4-sep-2026).
            # Con `elegido_por == "emisor"` el veredicto es "ok" por construcción
            # (se eligió justamente porque el contratista es el emisor) → el Excel
            # lo pinta «✔ Coincide», que es lo que el evaluador tiene que leer.
            "veredicto": ver_ct,
            # POR QUÉ este contrato y no otro, y cuáles son los otros: sin esto el
            # evaluador no podía saber si el N° mostrado era el del emisor o el de
            # un tercero que también trabajó el mismo CUI.
            "elegido_por": elegido_por,
            "otros_contratos_expediente": otros,
        }
        if c.get("url_pdf"):
            bloque["contrato"]["pdf"] = c["url_pdf"]

    res = ficha.get("resolucion")
    if res:
        bloque["fuentes"].append("MEF-08A")
        bloque["verificado_en_mef"] = True
        bloque["resolucion"] = {"numero": res.get("numero"), "documento": res.get("documento"),
                                # `url` viaja para que la etapa descargue y LEA la
                                # resolución (fecha oficial + consultor nombrado).
                                "url": res.get("url"), "veredicto": "ok"}
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
    """GET/POST con reintentos + backoff. None si el portal no respondió.

    ⚠ El `None` de esta función tapa dos cosas distintas (4xx = no existe · portal
    caído). Se conserva porque es el contrato que consumen sus llamadores; adentro
    la distinción sí existe (`Resultado.respondio`)."""
    metodo = kw.pop("metodo", "GET")
    timeout = kw.pop("timeout", 30)      # una sola vez: antes el pop vivía dentro
                                         # del bucle y el 2º intento perdía el valor

    def _pedir() -> Optional[requests.Response]:
        r = session.request(metodo, url, timeout=timeout, **kw)
        if r.status_code == 200:
            return r
        if r.status_code < 500:
            return None                  # 4xx → respuesta: no existe/entrada inválida
        raise RespuestaTransitoria(f"HTTP {r.status_code}")

    res = con_reintentos(_pedir, politica=_POLITICA,
                         etiqueta=f"MEF {metodo} {url[-40:]}",
                         excepciones=(requests.RequestException, RespuestaTransitoria),
                         log=logger, nivel=logging.INFO)
    if not res.respondio:
        logger.info("MEF %s %s: no respondió tras %d intentos (%s)",
                    metodo, url[-40:], res.intentos, corto(res.error))
    return res.valor_o(None)


class CacheMef:
    """Ficha 08-A y contratos por CUI durante UNA corrida (se crea por job).

    Corrida Muraria del 6-sep-2026: 71 verificaciones sobre unos 30 CUI distintos,
    cada una con ficha + contratos → la mitad de las peticiones repetía la
    anterior (sonda de Codex: 16 → 8 peticiones sobre 8 experiencias, mismos
    resultados). Comparte además la sesión HTTP (keep-alive).

    Memoria de fallos: si el portal no respondió para un CUI, los hermanos que
    llegan dentro de `ttl_fallo` segundos no vuelven a esperar los 3 reintentos;
    pasado ese plazo se vuelve a intentar (el MEF cae por baches, no por horas).
    """

    def __init__(self, session: Optional[requests.Session] = None,
                 ttl_fallo: float = 120.0, reloj=time.monotonic) -> None:
        self.session = crear_session(session)
        self.ttl_fallo = ttl_fallo
        self._reloj = reloj
        self._fichas: dict[str, str] = {}
        self._contratos: dict[tuple[str, str], list] = {}
        self._fallos: dict[str, float] = {}
        self.peticiones = 0
        self.aciertos = 0
        self.evitadas_por_fallo = 0

    def _fallo_reciente(self, cui: str) -> bool:
        t = self._fallos.get(cui)
        return t is not None and (self._reloj() - t) < self.ttl_fallo

    def ficha_08a(self, cui) -> Optional[str]:
        cui = str(cui).strip()
        if cui in self._fichas:
            self.aciertos += 1
            return self._fichas[cui]
        if self._fallo_reciente(cui):
            self.evitadas_por_fallo += 1
            return None
        self.peticiones += 1
        html = fetch_ficha_08a(cui, self.session)
        if html is None:
            self._fallos[cui] = self._reloj()
        else:
            self._fichas[cui] = html
        return html

    def contratos(self, cui, codsnip="") -> list[dict]:
        cui = str(cui).strip()
        k = (cui, str(codsnip or "0"))
        if k in self._contratos:
            self.aciertos += 1
            return self._contratos[k]
        if self._fallo_reciente(cui):
            self.evitadas_por_fallo += 1
            return []
        self.peticiones += 1
        crudo = _fetch_contratos_crudo(cui, codsnip, self.session)
        if crudo is None:
            self._fallos[cui] = self._reloj()
            return []
        self._contratos[k] = crudo
        return crudo

    def resumen(self) -> str:
        return (f"{self.peticiones} peticiones, {self.aciertos} reutilizadas, "
                f"{self.evitadas_por_fallo} evitadas por portal caído")


def fetch_ficha_08a(cui, session: Optional[requests.Session] = None,
                    cache: Optional[CacheMef] = None) -> Optional[str]:
    """HTML del Formato 08-A del CUI, o None si el portal no respondió."""
    if cache is not None:
        return cache.ficha_08a(cui)
    r = _get(crear_session(session), f"{FICHA_08A}{cui}")
    return r.text if r is not None else None


def _fetch_contratos_crudo(cui, codsnip="", session: Optional[requests.Session] = None
                           ) -> Optional[list]:
    """Contratos crudos del DWH; None si el portal NO respondió (distinto de [])."""
    r = _get(crear_session(session), CONTRATOS_DWH, metodo="POST",
             data={"id": str(cui), "codsnip": str(codsnip or "0"), "vers": "v2"},
             headers={"X-Requested-With": "XMLHttpRequest"})
    if r is None:
        return None
    try:
        d = r.json()
        return d if isinstance(d, list) else []
    except ValueError:
        return []


def fetch_contratos(cui, codsnip="", session: Optional[requests.Session] = None,
                    cache: Optional[CacheMef] = None) -> list[dict]:
    """Contratos SEACE del CUI (crudos del DWH). [] si no hay o el portal falló."""
    if cache is not None:
        return cache.contratos(cui, codsnip)
    return _fetch_contratos_crudo(cui, codsnip, session) or []


def descargar_pdf(session: requests.Session, url: str, destino, *, timeout: float = 60.0) -> bool:
    """Descarga en streaming un PDF (resolución o contrato) a `destino`. Rename
    atómico. Los links del 08-A llevan token de sesión → usar la MISMA session."""
    import os
    from pathlib import Path
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".part")

    def _bajar() -> bool:
        try:
            with session.get(url, timeout=timeout, stream=True) as r:
                if r.status_code >= 500:
                    raise RespuestaTransitoria(f"HTTP {r.status_code}")
                if r.status_code != 200:
                    return False         # 4xx → respuesta: el documento no está
                os.makedirs(destino.parent, exist_ok=True)
                n = 0
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        if chunk:
                            f.write(chunk)
                            n += len(chunk)
                if n == 0:
                    raise RespuestaTransitoria("respuesta vacía")
            os.replace(tmp, destino)
            return True
        except (requests.RequestException, OSError):
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    res = con_reintentos(_bajar, politica=_POLITICA,
                         etiqueta=f"MEF descarga {url[-40:]}",
                         excepciones=(requests.RequestException, OSError),
                         log=logger)
    if not res.respondio:
        logger.debug("MEF descarga %s: %s", url[-40:], corto(res.error))
    return res.valor_o(False)


def _nombre_archivo(base: str, ext: str = "pdf") -> str:
    """Nombre de archivo seguro (sin caracteres ilegales, capado)."""
    s = re.sub(r'[<>:"/\\|?*]', "-", (base or "documento").strip())
    s = _RE_WS.sub(" ", s)[:80].strip(" .-")
    return f"{s or 'documento'}.{ext}"


def descargar_documentos_expediente(cui, destino, codsnip="",
                                    session: Optional[requests.Session] = None) -> dict:
    """Descarga a `destino/` la resolución de aprobación (del 08-A) y el PDF del
    contrato de expediente (del DWH). RE-CONSULTA en fresco: los links del 08-A
    llevan token de sesión que caduca, así que no sirve un URL guardado antes.
    Best-effort: devuelve {resolucion, contrato} con lo que logró bajar. RED."""
    from pathlib import Path
    s = crear_session(session)
    destino = Path(destino)
    hecho = {"resolucion": 0, "contrato": 0}

    html = fetch_ficha_08a(cui, s)
    if html:
        ficha = parsear_ficha_08a(html)
        res = ficha.get("resolucion")
        if res and res.get("url"):
            nom = _nombre_archivo(res.get("numero") or res.get("documento") or "Resolucion aprobacion")
            if descargar_pdf(s, res["url"], destino / nom):
                hecho["resolucion"] += 1

    c = contrato_de_expediente(normalizar_contratos(fetch_contratos(cui, codsnip, s)))
    if c and c.get("url_pdf"):
        nom = _nombre_archivo(f"Contrato {c['numero']}")
        if descargar_pdf(s, c["url_pdf"], destino / nom):
            hecho["contrato"] += 1
    return hecho


def verificar_cui(exp: dict, cui, codsnip="", session: Optional[requests.Session] = None,
                  cache: Optional[CacheMef] = None) -> dict:
    """Orquesta el fetch (RED) + parseo + contraste para un CUI. Devuelve el
    bloque `verificacion_expediente`. Best-effort: si el portal falla, degrada a
    'no verificable' sin lanzar. Con `cache` (una por corrida) no repite ficha ni
    contratos de un CUI ya consultado."""
    s = cache.session if cache is not None else crear_session(session)
    html = fetch_ficha_08a(cui, s, cache=cache)
    ficha = parsear_ficha_08a(html) if html else {}
    contratos = normalizar_contratos(fetch_contratos(cui, codsnip, s, cache=cache))
    b = verificar_expediente(exp, ficha, contratos)
    # el CUI CONSULTADO (7 díg., codUniqInv) manda sobre el del espejo: el skill a
    # veces escribe el SNIP (6 díg.) y el backend lo corrige al resolver.
    b["cui_confirmado"] = str(cui).strip() or b.get("cui_confirmado")
    return b
