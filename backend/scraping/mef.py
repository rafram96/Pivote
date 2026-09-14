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
import inspect
import re
import time   # el backoff duerme en errores_red; se deja para parchear `mef.time.sleep`
from datetime import date, datetime, timedelta
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
_RE_ACTO_CONTRACTUAL = re.compile(
    r"resoluci[oó]n\s+(?:(?:total|parcial)\s+)?(?:del?\s+)?contrato\b|carta\s+notarial\b",
    re.I,
)


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

# SECCIONES DEL 08-A (13-sep-2026). La ficha de ejecución del Banco de Inversiones
# no es una lista plana de adjuntos: cada enlace vive en una fila de una sección.
#   B. «Datos de la fase de Ejecución: Expediente técnico o documento equivalente»
#      → el documento que APROBÓ el expediente técnico, con su fecha entre
#        paréntesis, y en las filas de costo («EXPEDIENTE TÉCNICO: S/…») el
#        contrato con que se elaboró.
#   C. «Datos de la fase de Ejecución durante la ejecución física»
#      → modificaciones posteriores (actualizaciones, adicionales, ampliaciones
#        de plazo, liquidación): OTRA FASE respecto del certificado de elaboración.
# Elegir la aprobación por etiqueta, sin la sección, tomaba el acto más reciente:
# auditoría documental de 23 expedientes (13-sep), 7 de 10 «otra fase» por esto.
_RE_H4_SECCION = re.compile(r"<h4[^>]*>\s*(?:<strong>)?\s*([A-F])\.\s*Datos de la fase", re.I)
_RE_FECHA_PARENT = re.compile(r"\((\d{1,2})/(\d{1,2})/(\d{4})\)\s*$")
_RE_CONCEPTO_COSTO_ET = re.compile(r"^\s*EXPEDIENTE\s+T[EÉ]CNICO\b", re.I)


def _fecha_parentesis(texto: str) -> Optional[str]:
    """«N° 018-2016-GRJ/GRI (27/01/2016)» → '2016-01-27' (o None)."""
    m = _RE_FECHA_PARENT.search(texto or "")
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mth, d).isoformat()
    except ValueError:
        return None


def _contexto_enlaces_08a(html: str) -> dict:
    """idArchivo → {seccion, concepto, fecha} leyendo la sección (último <h4>
    «X. Datos de la fase…» anterior) y la fila <tr> que contiene cada enlace.
    Primera aparición manda (un mismo archivo puede repetirse en varias filas)."""
    secciones = [(m.start(), m.group(1).upper()) for m in _RE_H4_SECCION.finditer(html)]
    out: dict = {}
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        fila = tr.group(1)
        if "downloadArchivoPublico" not in fila:
            continue
        seccion = "otra"
        for pos, letra in secciones:
            if pos < tr.start():
                seccion = letra
        celdas = [_RE_WS.sub(" ", unescape(_RE_TAG.sub(" ", c))).strip()
                  for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, re.S | re.I)]
        concepto = next((c for c in celdas if c), "")
        # la fecha «(dd/mm/aaaa)» va en la CELDA del enlace, a veces fuera del <a>
        for celda in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, re.S | re.I):
            if "downloadArchivoPublico" not in celda:
                continue
            texto_celda = _RE_WS.sub(" ", unescape(_RE_TAG.sub(" ", celda))).strip()
            fecha = _fecha_parentesis(texto_celda)
            for m in re.finditer(
                r'href="[^"]*downloadArchivoPublico\?idArchivo=([^"&]*)[^"]*"[^>]*>(.*?)</a>',
                celda, re.S | re.I,
            ):
                idar = m.group(1).strip()
                texto = _RE_WS.sub(" ", unescape(_RE_TAG.sub(" ", m.group(2)))).strip()
                if idar and idar not in out:
                    out[idar] = {"seccion": seccion, "concepto": concepto,
                                 "fecha": _fecha_parentesis(texto) or fecha}
    return out


def _documentos_08a(html: str) -> list[dict]:
    """Extrae los documentos descargables (downloadArchivoPublico) con etiqueta.
    Descarta los de idArchivo o etiqueta vacíos (ruido de la plantilla). Marca
    `es_aprobacion` por el texto del enlace y añade la SECCIÓN del 08-A en que
    aparece el enlace, el concepto de su fila y la fecha entre paréntesis
    (ver `_contexto_enlaces_08a`)."""
    out, vistos = [], set()
    contexto = _contexto_enlaces_08a(html)
    # El texto del enlace puede venir precedido por un icono (<i class="fa
    # fa-paperclip">): se toma TODO el interior del <a> sin etiquetas. Con el
    # regex anterior ([^<]*) esos enlaces quedaban con etiqueta vacía y se
    # descartaban como ruido (los «documentos de sustento» de la sección A).
    for m in re.finditer(
        r'href="([^"]*downloadArchivoPublico\?idArchivo=([^"&]*)[^"]*)"[^>]*>(.*?)</a>',
        html, re.S | re.I,
    ):
        url, idar = m.group(1), m.group(2).strip()
        label = _RE_WS.sub(" ", unescape(_RE_TAG.sub(" ", m.group(3)))).strip()
        if not idar or not label or idar in vistos:
            continue
        vistos.add(idar)
        contractual = bool(_RE_ACTO_CONTRACTUAL.search(label))
        ctx = contexto.get(idar) or {}
        out.append({
            "label": label,
            "url": urljoin(BASE, url.replace("&amp;", "&")),
            "es_aprobacion": bool(_RE_APROB.search(label)) and not contractual,
            "tipo_indicado": "acto_contractual" if contractual else "por_identificar",
            "seccion": ctx.get("seccion") or "otra",
            "concepto": ctx.get("concepto") or "",
            "fecha": ctx.get("fecha"),
        })
    return out


def _aprobacion_por_seccion_b(docs: list[dict]) -> Optional[dict]:
    """El documento de aprobación del expediente según la sección B: el de las
    filas de componentes (excluidas las filas de costo «EXPEDIENTE TÉCNICO: S/…»,
    que citan el contrato). Empate → el que más se ve como resolución. None si
    la sección B no trae enlaces."""
    b = [d for d in docs if d.get("seccion") == "B" and d.get("tipo_indicado") != "acto_contractual"]
    if not b:
        return None
    componentes = [d for d in b if not _RE_CONCEPTO_COSTO_ET.search(d.get("concepto") or "")]
    candidatos = componentes or b
    return sorted(candidatos, key=lambda d: -_score_aprobacion(d["label"]))[0]


def _contrato_et_por_seccion_b(docs: list[dict], aprobacion: Optional[dict]) -> Optional[dict]:
    """Documento citado en la fila «EXPEDIENTE TÉCNICO: S/…» de la sección B cuando
    NO es la misma aprobación: suele ser el contrato con que se elaboró el
    expediente (número y fecha de suscripción)."""
    for d in docs:
        if d.get("seccion") == "B" and _RE_CONCEPTO_COSTO_ET.search(d.get("concepto") or "") \
                and (aprobacion is None or d["url"] != aprobacion["url"]):
            return d
    return None


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
    # PRIMERO la sección B: es donde el 08-A registra qué documento aprobó el
    # expediente técnico y cuándo. Solo si la ficha no la trae con enlaces se cae
    # a la elección por etiqueta de siempre (el acto que «más se ve» como
    # resolución), que en fichas con modificaciones elegía la más reciente.
    elegido = _aprobacion_por_seccion_b(docs)
    origen_aprobacion = "seccion_b" if elegido else None
    if elegido is None:
        aprobs = sorted((d for d in docs if d["es_aprobacion"]),
                        key=lambda d: -_score_aprobacion(d["label"]))
        elegido = aprobs[0] if aprobs else None
        origen_aprobacion = "etiqueta" if elegido else None
    resolucion = None
    if elegido:
        mnum = _RE_NUM_RES.search(elegido["label"])
        resolucion = {"documento": elegido["label"], "url": elegido["url"],
                      "numero": mnum.group(1).strip() if mnum else None,
                      "fecha": elegido.get("fecha"), "origen": origen_aprobacion}
    contrato_et = _contrato_et_por_seccion_b(docs, elegido)
    modificaciones = [{"documento": d["label"], "url": d["url"], "fecha": d.get("fecha"),
                       "concepto": d.get("concepto")}
                      for d in docs if d.get("seccion") == "C"]

    return {
        "etapa": etapa,
        "estado_registro": estado,
        "seccion_b": seccion_b,
        "costo_total": costo_total,
        "monto_expediente": monto_exp,
        "documentos": docs,
        "resolucion": resolucion,
        # contrato con que se elaboró el ET según la fila de costo de la sección B
        "contrato_et_08a": ({"documento": contrato_et["label"], "url": contrato_et["url"],
                             "fecha": contrato_et.get("fecha")} if contrato_et else None),
        # actos de la sección C: modificaciones durante la ejecución física
        "modificaciones_08a": modificaciones,
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


# ENCARGO DEL CERTIFICADO (13-sep-2026). Un certificado puede acreditar la
# ELABORACIÓN del expediente o su SUPERVISIÓN; son contratos distintos del mismo
# CUI, con contratistas distintos. `contratos_de_expediente` excluía la
# supervisión a propósito (evita confundir obra con expediente), y por eso a un
# certificado de supervisión se le adjuntaba el contrato del proyectista
# (auditoría documental: 4:2, 5:2, 6:1, 10:6).
_RE_SUPERVISION_ET = re.compile(
    r"supervisi[oó]n.*\b(expediente|estudio)\b|\b(expediente|estudio)\b.*supervisi[oó]n", re.I)
_RE_SUPERVISION_OBRA = re.compile(r"supervisi[oó]n\s+de\s+(?:la\s+)?(?:obra|ejecuci)", re.I)


def encargo_declarado(exp: dict) -> str:
    """'supervision' | 'elaboracion' según lo que acredita el certificado: el
    tipo estructurado de `servicio_declarado` y, si no lo trae, el texto del
    proyecto («Supervisión de la elaboración del expediente…»)."""
    tipo = str(((exp or {}).get("servicio_declarado") or {}).get("tipo") or "")
    if tipo == "supervision_expediente":
        return "supervision"
    if tipo == "elaboracion_expediente":
        return "elaboracion"
    texto = " ".join(str((exp or {}).get(k) or "") for k in ("proyecto", "cargo_ocupado"))
    if _RE_SUPERVISION_ET.search(texto) and not _RE_SUPERVISION_OBRA.search(texto):
        return "supervision"
    return "elaboracion"


def contratos_de_supervision_expediente(contratos: list[dict]) -> list[dict]:
    """Contratos de SUPERVISIÓN de la elaboración del expediente/estudio (no de
    supervisión de obra), del más barato al más caro. Función PURA."""
    sup = [c for c in contratos or []
           if _RE_SUPERVISION_ET.search(c.get("objeto") or "")
           and not _RE_SUPERVISION_OBRA.search(c.get("objeto") or "")]
    return sorted(sup, key=lambda c: (c.get("monto") if c.get("monto") is not None else float("inf")))


_RE_FECHA_FLEX = re.compile(r"^\s*(\d{4})-(\d{2})(?:-(\d{2}))?")


def _fecha_iso_a_date(v) -> Optional[date]:
    """Fecha flexible del espejo → date. Acepta «2018-01 (Enero del 2018)» (toma
    el ÚLTIMO día del mes: es una cota superior) y «2019-06-11». None si no
    hay fecha reconocible («POR VERIFICAR…»)."""
    m = _RE_FECHA_FLEX.match(str(v or ""))
    if not m:
        return None
    y, mth = int(m.group(1)), int(m.group(2))
    try:
        if m.group(3):
            return date(y, mth, int(m.group(3)))
        siguiente = date(y + (mth == 12), (mth % 12) + 1, 1)
        return siguiente - timedelta(days=1)
    except ValueError:
        return None


def contratos_no_posteriores(contratos: list[dict], fecha_final, fecha_emision=None) -> tuple[list[dict], list[dict]]:
    """Separa los contratos suscritos DESPUÉS de que terminó el certificado: un
    servicio no pudo prestarse bajo un contrato firmado cuando ya había
    terminado (caso real: el contrato del propio concurso en curso, 2026,
    adjunto a un certificado anterior). Si el certificado no trae fecha de fin
    legible, la cota es su fecha de EMISIÓN: un certificado emitido en 2018 no
    puede descansar en un contrato de 2026. Devuelve (válidos, posteriores)."""
    fin = _fecha_iso_a_date(fecha_final) or _fecha_iso_a_date(fecha_emision)
    if not fin:
        return list(contratos or []), []
    validos, posteriores = [], []
    for c in contratos or []:
        fs = c.get("fecha_suscripcion")
        (posteriores if (fs and fs > fin) else validos).append(c)
    return validos, posteriores


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
    # ENCARGO y CRONOLOGÍA (13-sep-2026): primero se apartan los contratos
    # suscritos después del fin del certificado; luego, si el certificado
    # acredita la SUPERVISIÓN del expediente, el pool son los contratos de
    # supervisión del expediente (con caída al de elaboración, rotulada, si el
    # MEF no publica el de supervisión); si acredita la elaboración, el pool de
    # siempre. El contrato del emisor manda dentro del pool.
    encargo = encargo_declarado(exp)
    vigentes, posteriores = contratos_no_posteriores(contratos, exp.get("fecha_final"),
                                                     exp.get("fecha_emision"))
    encargo_contrato = encargo
    if encargo == "supervision":
        ces = contratos_de_supervision_expediente(vigentes)
        if not ces:
            ces = contratos_de_expediente(vigentes)
            encargo_contrato = "elaboracion" if ces else encargo
    else:
        ces = contratos_de_expediente(vigentes)
    c_emisor = next((x for x in ces
                     if _nombres_coinciden(identidad_contratista, x.get("contratista") or "")),
                    None) if identidad_contratista else None
    c = c_emisor or (ces[0] if encargo_contrato == "supervision" and ces
                     else contrato_de_expediente(vigentes) if encargo_contrato == "elaboracion"
                     else None)
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
            # qué acredita el certificado y de qué encargo es el contrato: si no
            # coinciden, el contrato no sustenta el encargo (solo el proyecto).
            "encargo_certificado": encargo,
            "encargo_contrato": encargo_contrato,
        }
        if encargo_contrato != encargo:
            bloque["contrato"]["veredicto"] = "no_verificable"
            bloque["contrato"]["nota_encargo"] = (
                "el certificado acredita la supervisión del expediente y el MEF solo "
                "publica el contrato de elaboración — confirma el proyecto, no el encargo")
    if posteriores:
        bloque["contratos_posteriores_al_certificado"] = [
            f"{x['numero']} — {x.get('contratista') or 'sin contratista'} "
            f"({x['fecha_suscripcion'].isoformat()})" for x in posteriores][:5]
        if c.get("url_pdf"):
            bloque["contrato"]["pdf"] = c["url_pdf"]

    res = ficha.get("resolucion")
    bloque["documentos_08a"] = ficha.get("documentos") or []
    # La etiqueta separa estas piezas de la aprobación, sin verificar el contenido.
    bloque["documentos_contractuales"] = [d for d in ficha.get("documentos", [])
                                           if d.get("tipo_indicado") == "acto_contractual"]
    if res:
        bloque["fuentes"].append("MEF-08A")
        bloque["verificado_en_mef"] = True
        bloque["resolucion"] = {"numero": res.get("numero"), "documento": res.get("documento"),
                                # `url` viaja para que la etapa descargue y LEA la
                                # resolución (fecha oficial + consultor nombrado).
                                "url": res.get("url"), "veredicto": "ok",
                                # fecha y procedencia según el propio 08-A (sección B
                                # = aprobación del expediente; etiqueta = elección
                                # por nombre, como antes del 13-sep-2026).
                                "fecha_08a": res.get("fecha"), "origen": res.get("origen")}
    if ficha.get("contrato_et_08a"):
        bloque["contrato_et_08a"] = ficha["contrato_et_08a"]
    if ficha.get("modificaciones_08a"):
        bloque["modificaciones_08a"] = ficha["modificaciones_08a"]
    else:
        bloque["resolucion"] = {"veredicto": "no_verificable",
                                "detalle": "sin documento de aprobación en el 08-A del MEF"}

    if not bloque["verificado_en_mef"]:
        bloque["detalle"] = ("El 08-A contiene adjuntos, pero no se identificó contrato ni candidato a aprobación."
                             if bloque["documentos_08a"] else
                             "No se obtuvo contrato ni candidato a aprobación en la consulta MEF; no demuestra inexistencia.")
    return bloque


# ── fetch / descarga (RED — no corre en tests offline) ───────────────────────

def crear_session(session: Optional[requests.Session] = None) -> requests.Session:
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", _UA)
    return s


def _get(session: requests.Session, url: str, **kw) -> Optional[requests.Response]:
    """GET/POST con reintentos + backoff. None si el portal no respondió.

    `None` conserva la API histórica; el canal diagnóstico optativo registra
    consulta no completada. Un HTTP 4xx no prueba inexistencia documental."""
    diagnostico = kw.pop("diagnostico", None)
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
    respuesta = res.valor_o(None)
    if isinstance(diagnostico, dict) and respuesta is None:
        diagnostico.update(estado="fuente_no_disponible",
                           motivo="el portal no respondió o devolvió un HTTP no utilizable")
    return respuesta


def _diagnostico(diagnostico: Optional[dict], estado: str, motivo: str) -> None:
    if isinstance(diagnostico, dict):
        diagnostico.update(estado=estado, motivo=motivo)


def _llamar_con_diagnostico(func, *args, diagnostico: dict, **kwargs):
    """Llama adaptadores antiguos sin reenviarles el keyword nuevo."""
    try:
        parametros = inspect.signature(func).parameters
        acepta = ("diagnostico" in parametros or
                  any(p.kind == inspect.Parameter.VAR_KEYWORD
                      for p in parametros.values()))
    except (TypeError, ValueError):
        acepta = False
    if acepta:
        return func(*args, diagnostico=diagnostico, **kwargs)
    return func(*args, **kwargs)


def _estado_ficha_html(html: str) -> dict:
    """Clasifica HTML sin confundir una página de error con ficha sin datos."""
    if not html.strip():
        return {"estado": "respuesta_no_reconocida", "motivo": "HTML vacío"}
    ficha = parsear_ficha_08a(html)
    if ficha.get("tiene_ficha"):
        return {"estado": "con_resultados", "motivo": "ficha 08-A reconocida"}
    if re.search(r"<title>[^<]*(?:error|login|mantenimiento)[^<]*</title>|"
                 r"(?:sesión|sesion)\s+expirada|servicio\s+no\s+disponible|"
                 r"class=[\"'][^\"']*(?:error|login)[^\"']*[\"']", html, re.I):
        return {"estado": "respuesta_no_reconocida", "motivo": "HTML de error o autenticación"}
    if re.search(r"ETAPA\s*:|ESTADO\s*:|Datos de la fase", html, re.I):
        return {"estado": "sin_resultados", "motivo": "ficha 08-A reconocida sin datos ni adjuntos"}
    return {"estado": "respuesta_no_reconocida", "motivo": "HTML sin estructura reconocida de 08-A"}


class CacheMef:
    """Ficha 08-A y contratos por CUI durante UNA corrida (se crea por job).

    Corrida Muraria del 6-sep-2026: 71 verificaciones sobre unos 30 CUI distintos,
    cada una con ficha + contratos → la mitad de las peticiones repetía la
    anterior (sonda de Codex: 16 → 8 peticiones sobre 8 experiencias, mismos
    resultados). Comparte además la sesión HTTP (keep-alive).

    Memoria de fallos POR RECURSO: si la ficha de un CUI no respondió, los hermanos
    que llegan dentro de `ttl_fallo` segundos no vuelven a esperar los 3 reintentos
    de ESE recurso; pasado el plazo se reintenta (el MEF cae por baches, no por
    horas). Un fallo de ficha no presume caída del endpoint de contratos, y una
    respuesta inválida (no JSON, no lista) es fallo, nunca «sin contratos».
    """

    def __init__(self, session: Optional[requests.Session] = None,
                 ttl_fallo: float = 120.0, reloj=time.monotonic) -> None:
        self.session = crear_session(session)
        self.ttl_fallo = ttl_fallo
        self._reloj = reloj
        self._fichas: dict[str, str] = {}
        self._contratos: dict[tuple[str, str], list] = {}
        self._estado_fichas: dict[str, dict] = {}
        self._estado_contratos: dict[tuple[str, str], dict] = {}
        self._fallo_fichas: dict[str, dict] = {}
        self._fallo_contratos: dict[tuple[str, str], dict] = {}
        self._fallos: dict[tuple, float] = {}          # (recurso, clave) → instante
        self.peticiones = 0
        self.aciertos = 0
        self.evitadas_por_fallo = 0

    def _fallo_reciente(self, clave: tuple) -> bool:
        t = self._fallos.get(clave)
        return t is not None and (self._reloj() - t) < self.ttl_fallo

    def ficha_08a(self, cui, *, diagnostico: Optional[dict] = None) -> Optional[str]:
        cui = str(cui).strip()
        if cui in self._fichas:
            self.aciertos += 1
            if diagnostico is not None:
                diagnostico.update(self._estado_fichas.get(cui, {
                    "estado": "no_registrado", "motivo": "estado no conservado"}))
            return self._fichas[cui]
        k = ("ficha", cui)
        if self._fallo_reciente(k):
            self.evitadas_por_fallo += 1
            estado = self._fallo_fichas.get(cui, {
                "estado": "fuente_no_disponible", "motivo": "fallo de ficha vigente en TTL"})
            if diagnostico is not None:
                diagnostico.update(estado)
            return None
        self.peticiones += 1
        estado = {}
        html = _llamar_con_diagnostico(fetch_ficha_08a, cui, self.session,
                                       diagnostico=estado)
        if html is None:
            self._fallos[k] = self._reloj()
            _diagnostico(estado, "fuente_no_disponible", "ficha 08-A no disponible")
            self._fallo_fichas[cui] = dict(estado)
        elif not estado:
            estado.update(_estado_ficha_html(html))
        if html is not None and estado.get("estado") == "respuesta_no_reconocida":
            self._fallos[k] = self._reloj()
            self._fallo_fichas[cui] = dict(estado)
        elif html is not None:
            self._fichas[cui] = html
            self._estado_fichas[cui] = dict(estado or {
                "estado": "no_registrado", "motivo": "estado no conservado"})
        if diagnostico is not None:
            diagnostico.update(estado)
        return html

    def contratos(self, cui, codsnip="", *, diagnostico: Optional[dict] = None) -> list[dict]:
        cui = str(cui).strip()
        k = (cui, str(codsnip or "0"))
        if k in self._contratos:
            self.aciertos += 1
            if diagnostico is not None:
                diagnostico.update(self._estado_contratos.get(k, {
                    "estado": "no_registrado", "motivo": "estado no conservado"}))
            return self._contratos[k]
        kf = ("contratos",) + k
        if self._fallo_reciente(kf):
            self.evitadas_por_fallo += 1
            estado = self._fallo_contratos.get(kf, {
                "estado": "fuente_no_disponible", "motivo": "fallo de contratos vigente en TTL"})
            if diagnostico is not None:
                diagnostico.update(estado)
            return []
        self.peticiones += 1
        estado = {}
        crudo = _llamar_con_diagnostico(_fetch_contratos_crudo, cui, codsnip,
                                        self.session, diagnostico=estado)
        if crudo is None:                              # sin respuesta o respuesta inválida
            self._fallos[kf] = self._reloj()
            self._fallo_contratos[kf] = dict(estado or {
                "estado": "fuente_no_disponible", "motivo": "endpoint de contratos no disponible"})
            if diagnostico is not None:
                diagnostico.update(self._fallo_contratos[kf])
            return []
        if not estado:
            _diagnostico(estado, "con_resultados" if crudo else "sin_resultados",
                         "contratos recibidos" if crudo else "lista contractual vacía")
        self._contratos[k] = crudo                     # lista (vacía o no) = dato
        self._estado_contratos[k] = dict(estado or {
            "estado": "no_registrado", "motivo": "estado no conservado"})
        if diagnostico is not None:
            diagnostico.update(estado)
        return crudo

    def resumen(self) -> str:
        return (f"{self.peticiones} peticiones, {self.aciertos} reutilizadas, "
                f"{self.evitadas_por_fallo} evitadas por portal caído")


def fetch_ficha_08a(cui, session: Optional[requests.Session] = None,
                    cache: Optional[CacheMef] = None,
                    diagnostico: Optional[dict] = None) -> Optional[str]:
    """HTML del Formato 08-A del CUI, o None si el portal no respondió."""
    if cache is not None:
        return cache.ficha_08a(cui, diagnostico=diagnostico)
    estado = diagnostico if isinstance(diagnostico, dict) else {}
    r = _llamar_con_diagnostico(_get, crear_session(session), f"{FICHA_08A}{cui}",
                                diagnostico=estado)
    if r is None:
        _diagnostico(estado, "fuente_no_disponible", "ficha 08-A no disponible")
        return None
    html = r.text
    estado.update(_estado_ficha_html(html))
    if diagnostico is not None:
        diagnostico.update(estado)
    return html


def _fetch_contratos_crudo(cui, codsnip="", session: Optional[requests.Session] = None,
                           diagnostico: Optional[dict] = None) -> Optional[list]:
    """Contratos crudos del DWH; None si el portal NO respondió o respondió algo
    que no es la lista esperada (HTML de error, JSON de otra forma). Solo una
    lista es dato; `[]` de la fuente significa «sin contratos»."""
    estado = diagnostico if isinstance(diagnostico, dict) else {}
    r = _llamar_con_diagnostico(
        _get, crear_session(session), CONTRATOS_DWH, metodo="POST",
        data={"id": str(cui), "codsnip": str(codsnip or "0"), "vers": "v2"},
        headers={"X-Requested-With": "XMLHttpRequest"}, diagnostico=estado)
    if r is None:
        if estado.get("estado") != "fuente_no_disponible":
            _diagnostico(estado, "fuente_no_disponible", "endpoint de contratos no disponible")
        return None
    try:
        d = r.json()
    except ValueError:
        _diagnostico(estado, "respuesta_no_reconocida", "respuesta no JSON")
        return None
    if not isinstance(d, list):
        _diagnostico(estado, "respuesta_no_reconocida", "JSON no es una lista de contratos")
        return None
    if any(not isinstance(registro, dict) for registro in d):
        _diagnostico(estado, "respuesta_no_reconocida", "La lista contractual contiene registros no interpretables")
        return None
    _diagnostico(estado, "con_resultados" if d else "sin_resultados",
                 "contratos recibidos" if d else "lista contractual vacía")
    if diagnostico is not None:
        diagnostico.update(estado)
    return d


def fetch_contratos(cui, codsnip="", session: Optional[requests.Session] = None,
                    cache: Optional[CacheMef] = None,
                    diagnostico: Optional[dict] = None) -> list[dict]:
    """Contratos SEACE del CUI (crudos del DWH). [] si no hay o el portal falló."""
    if cache is not None:
        return cache.contratos(cui, codsnip, diagnostico=diagnostico)
    return _fetch_contratos_crudo(cui, codsnip, session, diagnostico=diagnostico) or []


# Los contratos del expediente que el 08-A enlaza al SEACE antiguo
# (`prodapp2.seace.gob.pe`, servlet DownloadContratosFileServlet) llegan con una
# cadena de certificados incompleta: la verificación estricta falla con
# «unable to get local issuer certificate» y 14 de 27 contratos de una
# propuesta real (13-sep-2026) quedaban sin descargar. Misma salida que
# `scraping/seace_abierto.py` para los hosts del SEACE: verify=False SOLO en
# esos hosts, con el aviso silenciado allí. El MEF (ofi5) y el almacenamiento
# nuevo del SEACE (Oracle) siguen verificándose.
_HOSTS_SIN_VERIFICAR_TLS = ("seace.gob.pe",)
import urllib3  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _verificar_tls(url: str) -> bool:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return not any(host == h or host.endswith("." + h) for h in _HOSTS_SIN_VERIFICAR_TLS)


def descargar_pdf(session: requests.Session, url: str, destino, *, timeout: float = 60.0) -> bool:
    """Descarga en streaming un PDF (resolución o contrato) a `destino`. Rename
    atómico. Los links del 08-A llevan token de sesión → usar la MISMA session."""
    import os
    from pathlib import Path
    destino = Path(destino)
    tmp = destino.with_name(destino.name + ".part")

    def _bajar() -> bool:
        try:
            with session.get(url, timeout=timeout, stream=True,
                             verify=_verificar_tls(url)) as r:
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
    consultas = {
        "mef_ficha": {"estado": "no_registrado", "motivo": "adaptador no informó estado"},
        "mef_contratos": {"estado": "no_registrado", "motivo": "adaptador no informó estado"},
    }
    html = _llamar_con_diagnostico(fetch_ficha_08a, cui, s,
                                   diagnostico=consultas["mef_ficha"], cache=cache)
    ficha = parsear_ficha_08a(html) if html else {}
    contratos = normalizar_contratos(_llamar_con_diagnostico(
        fetch_contratos, cui, codsnip, s, diagnostico=consultas["mef_contratos"], cache=cache))
    b = verificar_expediente(exp, ficha, contratos)
    # el CUI CONSULTADO (7 díg., codUniqInv) manda sobre el del espejo: el skill a
    # veces escribe el SNIP (6 díg.) y el backend lo corrige al resolver.
    b["cui_confirmado"] = str(cui).strip() or b.get("cui_confirmado")
    b["consultas_fuentes"] = consultas
    return b
