"""
SEACE por DATOS ABIERTOS — Bases Integradas + Contrato firmado, sin captcha (T-004).

Dos fuentes oficiales, complementarias (sondas 18-21 jul, `tools/fuentes_estado/`):

  CONOSCE  Excel anuales por dataset (contratos, convocatorias, consorcios…),
           descargables por URL directa. Se cachean UNA VEZ en
           `datos_pivote/referencia/conosce/` y se consultan offline — el host
           `conosce.osce.gob.pe` es intermitente (caído en vivo el 27-jul), así
           que NINGUNA consulta por experiencia depende de él.
  OCDS     API del OECE: procesos de un CUI (`records?projectID=`) con sus
           documentos (Bases Integradas en PDF/ZIP/RAR, contrato firmado).
           Única llamada en vivo por experiencia; best-effort.

El requisito N°1 del cliente (reunión 29-jul) es la SEGMENTACIÓN: un mismo CUI
tiene hasta 4 juegos de bases (preinversión / expediente / supervisión /
ejecución) y jamás debe cruzarse el tipo — «si estamos en expediente, buscamos
solo expediente». La selección (`seleccionar_proceso`) es pura y testeable; el
solape de fechas solo desempata entre procesos del MISMO tipo (la trampa de
circularidad está documentada en docs/plan-integracion-bases-contrato.md §5).

Mismo patrón que scraping/mef.py: parseo/clasificación/selección PUROS (tests
offline en tests/test_seace_abierto.py); solo fetch/descarga tocan red.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time   # el backoff duerme en errores_red; se deja para parchear `.time.sleep`
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests

from scraping.errores_red import (
    LINEAL, Politica, RespuestaTransitoria, con_reintentos, corto,
)

logger = logging.getLogger(__name__)

# ── constantes de fuente ─────────────────────────────────────────────────────

CONOSCE_ASSETS = "https://conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes"
# nombre de carpeta → nombre dentro del archivo (convención del portal)
DATASETS = {
    "contratos": "CONTRATOS",
    "convocatorias": "CONVOCATORIAS",
    "adjudicaciones": "ADJUDICACIONES",
    "consorcios": "CONSORCIO",
}
ANIO_MIN = 2018            # seacev3 con projectID; antes no hay datos abiertos

OCDS_API = "https://contratacionesabiertas.oece.gob.pe/api/v1"
OCID_PREFIJO = "ocds-dgv273-seacev3-"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/144 Safari/537.36")
_RETRIES = 3
_BACKOFF = 1.5
# Reintentos de datos abiertos (ADR-014): lineal 1.5s, 3.0s, como estaba.
_POLITICA = Politica(intentos=_RETRIES, base=_BACKOFF, modo=LINEAL)
# Los certificados de conosce/oece fallan en cadenas estrictas (verificado en
# las sondas) → verify=False como en aquellas, silenciando SOLO ese warning.
import urllib3  # noqa: E402

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def crear_session(session: Optional[requests.Session] = None) -> requests.Session:
    s = session or requests.Session()
    # OJO: setdefault NO sirve para User-Agent — requests ya trae
    # "python-requests/x.y" de fábrica y el WAF de prodN.seace.gob.pe
    # responde 403 instantáneo a ese UA (medido 30-jul).
    if s.headers.get("User-Agent", "").startswith("python-requests"):
        s.headers["User-Agent"] = _UA
    s.headers.setdefault("Referer", "https://bi.seace.gob.pe/")
    return s


def _get(session: requests.Session, url: str, **kw) -> Optional[requests.Response]:
    """GET con reintentos + backoff. None si el portal no respondió (nunca lanza)."""
    timeout = kw.pop("timeout", 45)      # una sola vez: antes el pop vivía dentro
                                         # del bucle y el 2º intento perdía el valor

    def _pedir() -> requests.Response:
        r = session.get(url, timeout=timeout, verify=False, **kw)
        if r.status_code == 200 or r.status_code == 404:
            return r              # 404 es respuesta, no caída: el llamador decide
        raise RespuestaTransitoria(f"HTTP {r.status_code}")

    res = con_reintentos(_pedir, politica=_POLITICA,
                         etiqueta=f"SEACE abierto {url[:80]}", log=logger)
    if res.respondio:
        return res.valor
    logger.warning("SEACE abierto: %s no respondió (%s)", url[:80], corto(res.error))
    return None


# ══ 1 · CONOSCE: cache local de datasets anuales ═════════════════════════════

def _dir_por_defecto() -> Path:
    from config import data_dir
    return data_dir() / "referencia" / "conosce"


def _norm_col(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _col(fieldnames: list, *candidatos: str) -> Optional[int]:
    """Índice de la primera columna cuyo nombre normalizado contenga alguno de
    los candidatos (los encabezados del portal cambian de caso/espacios)."""
    normales = [_norm_col(f) for f in fieldnames]
    for cand in candidatos:
        c = _norm_col(cand)
        for i, f in enumerate(normales):
            if c and c in f:
                return i
    return None


class CacheConosce:
    """Datasets anuales de CONOSCE en disco, consultables offline.

    `actualizar()` descarga los años que falten (y refresca el año corriente si
    envejeció); todo lo demás lee SOLO del disco. Tolerante a fallo parcial: un
    año que no baja no impide usar los demás — el resumen lo deja dicho.
    """

    def __init__(self, dir_base: Optional[Path] = None):
        self._dir = Path(dir_base) if dir_base else _dir_por_defecto()
        self._contratos: Optional[dict[str, dict]] = None

    # ── actualización (RED, best-effort) ────────────────────────────────────

    def _f_meta(self) -> Path:
        return self._dir / "metadata.json"

    def _f(self, ds: str, anio: int) -> Path:
        return self._dir / f"{ds}_{anio}.xlsx"

    def actualizar(self, datasets: tuple = ("contratos",), anios: Optional[range] = None,
                   session: Optional[requests.Session] = None,
                   dias_frescura: int = 35, forzar: bool = False) -> dict:
        """Baja lo que falte. Años cerrados no se re-descargan jamás; el año
        corriente se refresca si su copia tiene más de `dias_frescura` días
        (el portal publica mensual con ~3 semanas de rezago)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        s = crear_session(session)
        meta = {}
        if self._f_meta().exists():
            try:
                meta = json.loads(self._f_meta().read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                meta = {}
        hoy = date.today()
        anios = anios or range(ANIO_MIN, hoy.year + 1)
        resumen = {"descargados": [], "vigentes": [], "fallidos": []}
        for ds in datasets:
            for anio in anios:
                destino = self._f(ds, anio)
                clave = destino.name
                if destino.exists() and not forzar:
                    es_corriente = anio == hoy.year
                    edad = None
                    if clave in meta:
                        try:
                            edad = (hoy - date.fromisoformat(meta[clave]["fecha"])).days
                        except Exception:  # noqa: BLE001
                            edad = None
                    if not es_corriente or (edad is not None and edad <= dias_frescura):
                        resumen["vigentes"].append(clave)
                        continue
                url = f"{CONOSCE_ASSETS}/{ds}/{anio}/CONOSCE_{DATASETS[ds]}{anio}_0.xlsx"
                r = _get(s, url, timeout=180)
                if r is None or r.status_code != 200 or not r.content:
                    resumen["fallidos"].append(clave)
                    continue
                tmp = destino.with_name(destino.name + ".part")
                tmp.write_bytes(r.content)
                os.replace(tmp, destino)          # atómico: nunca un xlsx a medias
                meta[clave] = {"fecha": hoy.isoformat(), "bytes": len(r.content),
                               "fuente": url}
                resumen["descargados"].append(clave)
        tmp_meta = self._f_meta().with_name("metadata.json.part")
        tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_meta, self._f_meta())
        if resumen["fallidos"]:
            logger.warning("CONOSCE: %d archivo(s) no bajaron (%s) — se sigue con lo local",
                           len(resumen["fallidos"]), ", ".join(resumen["fallidos"][:4]))
        self._contratos = None                    # invalida el índice en memoria
        return resumen

    # ── consulta (OFFLINE) ──────────────────────────────────────────────────

    def contratos(self) -> dict[str, dict]:
        """Índice codigoconvocatoria → contrato (campos normalizados), de TODOS
        los años presentes en disco. Carga perezosa, una vez por proceso."""
        if self._contratos is not None:
            return self._contratos
        import openpyxl
        indice: dict[str, dict] = {}
        for f in sorted(self._dir.glob("contratos_*.xlsx")):
            try:
                wb = openpyxl.load_workbook(f, read_only=True)
                ws = wb.active
                it = ws.iter_rows(values_only=True)
                hdr = list(next(it, []) or [])
                cols = {
                    "codigoconvocatoria": _col(hdr, "codigoconvocatoria"),
                    "num_contrato": _col(hdr, "numcontrato", "num_contrato", "contrato"),
                    "ruc_contratista": _col(hdr, "ruccontratista", "ruc_contratista"),
                    "monto": _col(hdr, "montocontratadototal", "monto_contratado"),
                    "fecha_suscripcion": _col(hdr, "fechasuscripcion"),
                    "vigencia_ini": _col(hdr, "fechavigenciainicial", "vigenciainicial"),
                    "vigencia_fin": _col(hdr, "fechavigenciafinal", "vigenciafinal"),
                    "urlcontrato": _col(hdr, "urlcontrato"),
                }
                if cols["codigoconvocatoria"] is None:
                    logger.warning("CONOSCE %s: sin columna codigoconvocatoria — se omite", f.name)
                    continue
                for row in it:
                    cod = row[cols["codigoconvocatoria"]]
                    if cod in (None, ""):
                        continue
                    d = {"anio_dataset": f.stem.split("_")[-1]}
                    for k, i in cols.items():
                        if k != "codigoconvocatoria" and i is not None and i < len(row):
                            d[k] = row[i]
                    # un proceso puede tener varios contratos (ítems); el índice
                    # conserva la lista completa
                    indice.setdefault(str(cod).strip(), []).append(d)
                wb.close()
            except Exception as e:  # noqa: BLE001
                logger.warning("CONOSCE %s: no se pudo leer (%s) — se omite", f.name, e)
        self._contratos = indice
        return indice

    def contrato(self, codigoconvocatoria) -> list[dict]:
        """Contratos del proceso (lista; [] si no está en los años cacheados)."""
        return self.contratos().get(str(codigoconvocatoria).strip(), [])


# ══ 2 · OCDS: procesos y documentos de un CUI (RED, best-effort) ═════════════

def procesos_por_cui(cui, session: Optional[requests.Session] = None) -> Optional[list[dict]]:
    """Procesos (compiledRelease) del CUI. [] = el CUI no tiene procesos en la
    fuente (dato); None = el portal no respondió (incertidumbre — distinguir
    SIEMPRE, regla del proyecto)."""
    s = crear_session(session)
    r = _get(s, f"{OCDS_API}/records", params={"projectID": str(cui).strip()})
    if r is None:
        return None
    if r.status_code == 404:
        return []
    try:
        data = r.json()
    except ValueError:
        logger.warning("OCDS: respuesta no-JSON para CUI %s", cui)
        return None
    recs = data.get("records") or []
    out = []
    for rec in recs:
        comp = rec.get("compiledRelease") or rec
        if comp.get("tender") or comp.get("contracts"):
            out.append(comp)
    return out


def codigo_convocatoria(comp: dict) -> Optional[str]:
    """El ocid termina en el codigoconvocatoria — la llave de cruce con CONOSCE."""
    ocid = str(comp.get("ocid") or "")
    if ocid.startswith(OCID_PREFIJO):
        cod = ocid[len(OCID_PREFIJO):]
        return cod or None
    m = re.search(r"(\d{5,})$", ocid)
    return m.group(1) if m else None


def documentos(comp: dict) -> list[dict]:
    docs = list((comp.get("tender") or {}).get("documents") or [])
    for c in comp.get("contracts") or []:
        docs += c.get("documents") or []
    return docs


def doc_bases_integradas(comp: dict) -> Optional[dict]:
    """El PDF de Bases INTEGRADAS. Las 'Administrativas' son la versión previa
    («la administrativa es la previa» — cliente, 29-jul): solo sirven las
    integradas; si no están, se devuelve None y el estado lo dice."""
    for d in documentos(comp):
        if (d.get("documentType") == "biddingDocuments"
                and "integrada" in _minusculas(d.get("title"))):
            return d
    return None


def doc_contrato_firmado(comp: dict) -> Optional[dict]:
    for d in documentos(comp):
        if d.get("documentType") == "contractSigned":
            return d
    return None


def extension_documento(doc: Optional[dict]) -> str:
    """Extensión honesta del documento OCDS. Las Bases Integradas reales pueden
    publicarse como PDF, ZIP o RAR; nunca se les fuerza extensión `.pdf`.

    Acepta las DOS formas del documento: la de la fuente (`format`, inglés) y la
    que se persiste en `enriquecimiento[…]["seace"]["docs"]` (`formato`). La
    descarga diferida trabaja sobre la persistida, así que leer solo `format`
    devolvía `.pdf` siempre; el archivo bajaba bien pero la validación por magia
    lo rechazaba por no empezar con `%PDF` y quedaba un `*_ERROR.txt`. Es la
    causa REAL de los 3 errores de Bases Integradas de la corrida Vitarte
    (verificado el 2026-08-05: con la extensión correcta, el ZIP baja en 428,781
    bytes y el RAR en 1,515,008) — no era el host.
    """
    doc = doc or {}
    formato = _minusculas(doc.get("format") or doc.get("formato"))
    url = _minusculas(doc.get("url"))
    if "rar" in formato or url.endswith(".rar"):
        return ".rar"
    if "zip" in formato or url.endswith(".zip"):
        return ".zip"
    return ".pdf"


def descargar_archivo(url: str, destino, session: Optional[requests.Session] = None,
                      timeout=(30.0, 480.0)) -> bool:
    """Streaming + rename atómico; rechaza HTML/JSON y valida PDF/ZIP/RAR por magia.

    El timeout es (conexión, lectura): `prod1.seace.gob.pe` (Bases Integradas
    vía SdescargarArchivoAlfresco) tarda 3-4 minutos en emitir el primer byte
    — medido en vivo el 30-jul (200 en 168-242 s). Con 120 s este host parecía
    siempre caído. Su WAF además exige User-Agent de navegador (403 instantáneo
    sin él) y castiga el header Referer: con `Referer: bi.seace.gob.pe` la
    conexión queda colgada indefinidamente o devuelve 403 (medido 30-jul), así
    que para los hosts `prodN.seace.gob.pe` se manda la petición SIN Referer."""
    s = crear_session(session)
    headers_extra = (
        {"Referer": None}
        if re.match(r"https?://prod\d*\.seace\.gob\.pe/", url)
        else {}
    )
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".part")

    def _bajar() -> bool:
        try:
            with s.get(url, timeout=timeout, stream=True, verify=False,
                       allow_redirects=True, headers=headers_extra) as r:
                if r.status_code != 200:
                    raise RespuestaTransitoria(f"HTTP {r.status_code}")
                with open(tmp, "wb") as f:
                    primeros = b""
                    for chunk in r.iter_content(1 << 16):
                        if not primeros:
                            primeros = chunk[:8]
                        f.write(chunk)
            ext = destino.suffix.lower()
            valido = (
                (ext == ".pdf" and primeros.startswith(b"%PDF"))
                or (ext == ".zip" and primeros.startswith(b"PK\x03\x04"))
                or (ext == ".rar" and primeros.startswith(b"Rar!\x1a\x07"))
            )
            if not valido:
                tmp.unlink(missing_ok=True)
                return False      # respondió algo que no es el archivo → no reintentar
            os.replace(tmp, destino)
            return True
        except Exception:  # noqa: BLE001 — se relanza tras limpiar el parcial
            tmp.unlink(missing_ok=True)
            raise

    res = con_reintentos(_bajar, politica=_POLITICA,
                         etiqueta=f"SEACE descarga {destino.name}", log=logger)
    if res.respondio:
        return res.valor
    logger.warning("SEACE abierto: descarga falló (%s) — %s",
                   destino.name, corto(res.error))
    return False


def descargar_pdf(url: str, destino, session: Optional[requests.Session] = None,
                  timeout=(30.0, 480.0)) -> bool:
    """Compatibilidad para contratos y demás documentos que deben ser PDF."""
    return descargar_archivo(url, Path(destino).with_suffix(".pdf"),
                             session=session, timeout=timeout)


# ══ 3 · Clasificación y selección del proceso (PURO — el requisito N°1) ══════

TIPO_PREINVERSION = "preinversion"
TIPO_EXPEDIENTE = "expediente"
TIPO_SUPERVISION = "supervision"
TIPO_EJECUCION = "ejecucion"
TIPO_OTRO = "otro"


def _minusculas(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


_RE_SALDO = re.compile(r"\bsaldo\b")
_RE_PREINV = re.compile(r"preinversion|perfil de|estudio de preinversion|ficha tecnica")
_RE_SUPERV = re.compile(r"supervis")
_RE_EXPED = re.compile(r"expediente tecnico|elaboracion del expediente|estudio definitivo")
_RE_EJEC = re.compile(r"ejecucion de|construccion|obra:")


def clasificar_proceso(comp: dict) -> tuple[str, bool]:
    """(tipo, es_saldo) desde el título/descripcion del tender.

    La taxonomía es la del cliente (29-jul): preinversión / expediente /
    supervisión / ejecución. «Supervisión» gana sobre «expediente» a propósito:
    un proceso de "supervisión de la elaboración del expediente" usa bases DE
    SUPERVISIÓN, que es lo que se está buscando cuando se pide ese tipo."""
    t = comp.get("tender") or {}
    texto = _minusculas(f"{t.get('title') or ''} {t.get('description') or ''} "
                        f"{t.get('procurementMethodDetails') or ''}")
    es_saldo = bool(_RE_SALDO.search(texto))
    if _RE_PREINV.search(texto):
        return TIPO_PREINVERSION, es_saldo
    if _RE_SUPERV.search(texto):
        return TIPO_SUPERVISION, es_saldo
    if _RE_EXPED.search(texto):
        return TIPO_EXPEDIENTE, es_saldo
    if _RE_EJEC.search(texto) or (t.get("mainProcurementCategory") == "works"):
        return TIPO_EJECUCION, es_saldo
    return TIPO_OTRO, es_saldo


def tipo_esperado(es_expediente: bool, texto_experiencia: str = "") -> str:
    """Qué tipo de proceso busca ESTA experiencia. Camino A → expediente.
    Camino B: supervisión salvo que el certificado acredite ejecución."""
    if es_expediente:
        return TIPO_EXPEDIENTE
    tx = _minusculas(texto_experiencia)
    if _RE_SUPERV.search(tx):
        return TIPO_SUPERVISION
    if re.search(r"residente|ejecucion|construccion", tx):
        return TIPO_EJECUCION
    return TIPO_SUPERVISION      # los concursos del cliente son de supervisión


def _periodo_proceso(comp: dict) -> Optional[tuple[date, date]]:
    """Ventana temporal del proceso, de contracts[].period o dateSigned."""
    fechas: list[date] = []
    for c in comp.get("contracts") or []:
        for k in ("startDate", "endDate"):
            f = _fecha_iso((c.get("period") or {}).get(k))
            if f:
                fechas.append(f)
        f = _fecha_iso(c.get("dateSigned"))
        if f:
            fechas.append(f)
    if not fechas:
        return None
    return min(fechas), max(fechas)


def _fecha_iso(v) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except ValueError:
        return None


def _solape_dias(a: tuple[date, date], b: tuple[date, date]) -> int:
    ini, fin = max(a[0], b[0]), min(a[1], b[1])
    return max(0, (fin - ini).days + 1)


def seleccionar_proceso(procesos: list[dict], tipo: str,
                        periodo: Optional[tuple[date, date]] = None) -> dict:
    """El proceso del CUI que corresponde al tipo buscado — SIN cruzar jamás de
    tipo (requisito N°1 del cliente). Devuelve:

      {"elegido": comp|None, "tipo": …, "seleccion": "objeto"|"objeto+vigencia"|None,
       "motivo": str, "candidatos": [(ocid, tipo, es_saldo), …]}

    El solape con el periodo declarado SOLO desempata dentro del mismo tipo
    (obra vs su saldo) — nunca elige contra tipo (§5 del diseño)."""
    candidatos = [(p, *clasificar_proceso(p)) for p in procesos]
    resumen = [(p.get("ocid"), t, s) for (p, t, s) in candidatos]
    del_tipo = [(p, s) for (p, t, s) in candidatos if t == tipo]
    if not del_tipo:
        vistos = ", ".join(sorted({t for (_, t, _) in candidatos})) or "ninguno"
        return {"elegido": None, "tipo": tipo, "seleccion": None,
                "motivo": f"el CUI no tiene proceso de {tipo} en datos abiertos "
                          f"(procesos vistos: {vistos})",
                "candidatos": resumen}
    if len(del_tipo) == 1:
        return {"elegido": del_tipo[0][0], "tipo": tipo, "seleccion": "objeto",
                "motivo": f"único proceso de {tipo} del CUI", "candidatos": resumen}
    # varios del mismo tipo (típico: proceso madre + saldo) → desempate
    if periodo:
        puntuados = []
        for (p, _s) in del_tipo:
            ven = _periodo_proceso(p)
            puntuados.append((_solape_dias(ven, periodo) if ven else 0, p))
        puntuados.sort(key=lambda x: x[0], reverse=True)
        if puntuados[0][0] > 0:
            return {"elegido": puntuados[0][1], "tipo": tipo,
                    "seleccion": "objeto+vigencia",
                    "motivo": f"{len(del_tipo)} procesos de {tipo}; se eligió el que "
                              f"solapa el periodo del certificado "
                              f"({puntuados[0][0]} días) — verificable en el ZIP",
                    "candidatos": resumen}
    # sin periodo o sin solape: preferir el proceso madre (no-saldo) y, entre
    # varios, el MÁS RECIENTE — determinista y explícito, nunca "el primero de
    # la lista" (caso real 2279396: supervisiones de 2017 y 2022 sin vigencias).
    madre = [p for (p, s) in del_tipo if not s] or [p for (p, _s) in del_tipo]

    def _recencia(p: dict):
        ven = _periodo_proceso(p)
        if ven:
            return ven[1]
        f = _fecha_iso((p.get("tender") or {}).get("tenderPeriod", {}).get("startDate")) \
            or _fecha_iso(p.get("date"))
        return f or date.min

    madre.sort(key=_recencia, reverse=True)
    ambiguo = len(madre) > 1
    return {"elegido": madre[0], "tipo": tipo, "seleccion": "objeto",
            "ambiguo": ambiguo,
            "motivo": (f"{len(del_tipo)} procesos de {tipo} sin solape que desempate; "
                       f"se eligió el más reciente — VERIFICAR contra el certificado"
                       if ambiguo else
                       f"{len(del_tipo)} procesos de {tipo}; se eligió el principal (no-saldo)"),
            "candidatos": resumen}
