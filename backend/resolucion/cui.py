"""
Resolución de CUI — portado del prototipo `tools/buscar_cui_por_nombre.py`
(medido: Libertador 100% · Trujillo 94% · Lircay 50% sin humano).

Método por experiencia:
  0. campo `cui` de la skill o "CUI/SNIP NNN" en el texto → determinístico
     (verificando nombre/ubicación contra la obra del código).
  1. nombre: limpiar boilerplate → fragmentos (establecimiento + nombre propio)
     → buscar en InfoObras → puntuar (similitud + departamento + fecha + RUC)
     → compuerta de tokens distintivos → AUTO / PROBABLE / REVISIÓN.
  2. dedup por folio: el "2º periodo del mismo certificado" hereda el CUI.

La red está detrás de `ConsultaInfoObras` (inyectable): los tests usan fakes,
solo la etapa en vivo toca el portal.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Optional, Protocol

try:
    from rapidfuzz import fuzz

    def _sim(a: str, b: str) -> float:
        return fuzz.token_set_ratio(a, b)
except ImportError:  # degradación sin rapidfuzz
    from difflib import SequenceMatcher

    def _sim(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio() * 100


# ── normalización y limpieza (idéntico al prototipo medido) ─────────────────

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


PREFIJOS = [
    r"consultor[ií]a de obra para la supervisi[oó]n de la obra\s*:?",
    r"elaboraci[oó]n del expediente t[eé]cnico y ejecuci[oó]n de la obra\s*:?",
    r"elaboraci[oó]n del expediente t[eé]cnico\s*:?",
    r"supervisi[oó]n de la obra\s*:?",
    r"construcci[oó]n del plan de contingencia del proyecto\s*",
    r"implementaci[oó]n del plan de contingencia.*?obra\s*:?",
    r"ejecuci[oó]n de (?:la )?obra\s*:?",
    r"supervisi[oó]n\s*:?",
]
DEPTOS = ["HUANUCO", "PASCO", "LIMA", "CUSCO", "PIURA", "JUNIN", "ANCASH", "LA LIBERTAD",
          "AMAZONAS", "LORETO", "UCAYALI", "APURIMAC", "PUNO", "CAJAMARCA", "AYACUCHO"]

ABREV = [
    (re.compile(r"\bEE\.?\s?SS\.?\b", re.I), "Establecimientos de Salud"),
    (re.compile(r"\bC\.\s?S\.?\b", re.I), "Centro de Salud"),
    (re.compile(r"\bE\.\s?S\.?\b", re.I), "Establecimiento de Salud"),
    (re.compile(r"\bP\.\s?S\.?\b", re.I), "Puesto de Salud"),
    (re.compile(r"\bCMI\b", re.I), "Centro Materno Infantil"),
    (re.compile(r"\bH\.\s?R\.?\b", re.I), "Hospital Regional"),
    (re.compile(r"\bH\.\s(?=\w)", re.I), "Hospital "),
]


def expandir_abrev(t: str) -> str:
    for pat, full in ABREV:
        t = pat.sub(full, t)
    return t


_SALUD = re.compile(r"(salud|hospital|essalud|asistencial|policl[ií]nico|materno|"
                    r"\binsn\b|\binen\b|\bcmi\b|"
                    r"\bc\.\s?s\.|\be\.\s?s\.|\bp\.\s?s\.)", re.I)


def es_aplicable(proyecto: str) -> bool:
    """False = obra privada/ajena a salud: no está en InfoObras, no se cruza."""
    return bool(_SALUD.search(expandir_abrev(proyecto or "")))


_RE_EST = re.compile(
    r"(hospital[^,(]*|puesto de salud[^,(]*|centro de salud[^,(]*|"
    r"establecimiento de salud[^,(]*|centro asistencial[^,(]*|"
    r"policl[ií]nico[^,(;]*|centro materno[^,(;]*|"
    r"\binsn\b[^,(;]*|\binen\b[^,(;]*)", re.I)

_META = re.compile(
    r"(;.*$"
    r"|\s[–\-]\s*SNIP\b.*$|\s[–\-]\s*CUI\b.*$"
    r"|,\s*S/\..*$"
    r"|,?\s*\d[\d.,]*\s*(m²|m2|camas)\b.*$)", re.I)


def _sin_prefijo(proyecto: str) -> str:
    t = expandir_abrev(proyecto)
    for pat in PREFIJOS:
        t = re.sub(pat, "", t, flags=re.I).strip()
    return _META.sub("", t).strip(" ;,–-.")


def establecimiento(proyecto: str) -> str:
    t = _sin_prefijo(proyecto)
    m = _RE_EST.search(t)
    return m.group(1).strip(" :,-.") if m else t


def ubicacion(proyecto: str) -> set[str]:
    t = _sin_prefijo(proyecto)
    tn = norm(t)
    m = _RE_EST.search(t)
    if m:
        est = norm(m.group(1).strip(" :,-."))
        i = tn.find(est)
        cola = tn[i + len(est):] if i >= 0 else tn
    else:
        cola = tn
    return {d for d in DEPTOS if d in cola}


_LEAD = re.compile(
    r"^(hospital regional|hospital|puesto de salud|centro de salud|"
    r"establecimiento de salud|centro asistencial|policl[ií]nico|centro materno|"
    r"especializado|regional|nuevo|de apoyo|de emergencias|"
    r"en la red asistencial|de la red asistencial|red asistencial|nivel\s*[\w-]+)\b\s*", re.I)
_COLA = re.compile(r"\s*[-–]\s*(es\s?salud|essalud|diresa|geresa|minsa)\b.*$", re.I)


def _nucleo(est: str) -> str:
    p, prev = est, None
    while p != prev:
        prev = p
        p = _LEAD.sub("", p).strip(" :,-.")
    p = _COLA.sub("", p).strip(" :,-.")
    p = re.split(r"\s+(diresa|geresa)\b", p, flags=re.I)[0].strip(" :,-.")
    p = re.split(r"\s+de\s+[A-Z][a-záéíóú]+\s*$", p)[0].strip(" :,-.")
    return p


def fragmentos(proyecto: str) -> list[str]:
    t = _sin_prefijo(proyecto)
    frags: list[str] = []
    m = _RE_EST.search(t)
    if m:
        est = m.group(1).strip(" :,-.")
        frags.append(est)
        proper = re.sub(r"^(hospital|puesto de salud|centro de salud|establecimiento de salud|"
                        r"centro asistencial|policl[ií]nico|centro materno|"
                        r"regional|de apoyo|de emergencias|nivel\s*[\w-]+)\s*", "", est, flags=re.I).strip()
        proper = re.split(r"\s+de\s+[A-Z][a-záéíóú]+\s*$", proper)[0].strip()
        if proper and norm(proper) != norm(est):
            frags.append(proper)
        nucleo = _nucleo(est)
        if nucleo and len(nucleo) >= 4 and norm(nucleo) not in DEPTOS \
                and norm(nucleo) not in (norm(est), norm(proper)):
            frags.append(nucleo)
    if len(t) > 20:
        frags.append(" ".join(t.split()[:7]))
    out: list[str] = []
    for f in frags:
        f = f.strip(" :,-.")
        if len(f) >= 4 and norm(f) not in [norm(x) for x in out]:
            out.append(f)
    return out


RE_CODIGO = re.compile(r"\b(?:SNIP|CUI|C[oó]digo(?:\s+(?:SNIP|[uú]nico))?)\s*[:N°ºo.\-]*\s*(\d{4,8})\b", re.I)
RE_RUC = re.compile(r"\b(\d{11})\b")

_STOP = {"HOSPITAL", "PUESTO", "SALUD", "CENTRO", "ESTABLECIMIENTO", "REGIONAL",
         "DE", "DEL", "LA", "EL", "LOS", "Y", "APOYO", "NIVEL"}


def _palabras(s: str) -> set[str]:
    return set(re.findall(r"[A-Z]+", norm(s)))


def _tokens_clave(est_key: str) -> set[str]:
    return {t for t in _palabras(est_key) if len(t) >= 4 and t not in _STOP}


def _anio_de(fecha_iniobra) -> Optional[int]:
    if not fecha_iniobra:
        return None
    m = re.search(r"(\d{10,13})", str(fecha_iniobra))
    if m:
        try:
            return 1970 + int(int(m.group(1)) / (1000 * 60 * 60 * 24 * 365.25))
        except (ValueError, OverflowError):
            return None
    return None


def _puntuar(cand: dict, proyecto_norm: str, deptos_hint: set[str], anio_cert: Optional[int]) -> float:
    nombre = norm(cand.get("nombrObra") or "")
    score = _sim(proyecto_norm, nombre)
    dep = norm(cand.get("nombrDepartamento") or "")
    if deptos_hint:
        if dep and dep in deptos_hint:
            score += 15
        elif dep:
            score -= 20
    if "SALUD" in nombre or "HOSPITAL" in nombre or "ESTABLECIMIENTO" in nombre:
        score += 5
    a = _anio_de(cand.get("fechaIniObra"))
    if anio_cert and a and abs(a - anio_cert) <= 3:
        score += 8
    return round(score, 1)


# ── acceso a InfoObras (inyectable) ──────────────────────────────────────────

class Consulta(Protocol):
    def por_codigo(self, codigo: str) -> list[dict]: ...
    def buscar(self, nombre: str) -> list[dict]: ...


class ConsultaInfoObras:
    """Implementación real (en vivo) sobre el scraper del backend. La sesión se
    crea perezosamente: instanciar la clase no toca la red."""

    def __init__(self):
        self._session = None
        self._cache: dict[tuple, list] = {}

    def _ses(self):
        if self._session is None:
            from scraping.infoobras import _crear_session
            self._session = _crear_session()
        return self._session

    def _query(self, nombre="", codsnip=""):
        key = (nombre, codsnip)
        if key in self._cache:
            return self._cache[key]
        from scraping.infoobras import BASE_MAPA
        params = {"codDepartamento": "", "codProvincia": None, "codDistrito": None,
                  "codigoObra": "", "estadoRegistro": "", "nobrCodmodejec": "",
                  "cobrCodentpub": "", "codtipobrnv1": "", "codtipobrnv2": None,
                  "nombrObra": nombre, "codSnip": codsnip, "fechaIniObraDesde": "",
                  "fechaIniObraHasta": "", "tieneMonitor": "", "estObra": "",
                  "codNivel3": None, "codMarca": "", "modServControl": "",
                  "servControl": "", "nombreEntidad": "", "getFavoritos": 0}
        q = {"page": 0, "rowsPerPage": 20,
             "Parameters": json.dumps(params, separators=(",", ":"))}
        for intento in range(3):
            try:
                r = self._ses().post(f"{BASE_MAPA}/Mapa/busqueda/obrasBasic",
                                     params=q, timeout=25)
                r.raise_for_status()
                res = r.json().get("Result", [])
                res = res if isinstance(res, list) else []
                self._cache[key] = res
                return res
            except Exception:  # noqa: BLE001 — API pública intermitente
                if intento == 2:
                    return []
        return []

    def por_codigo(self, codigo: str) -> list[dict]:
        return self._query(codsnip=str(codigo))

    def buscar(self, nombre: str) -> list[dict]:
        return self._query(nombre=nombre)


# ── resolución ───────────────────────────────────────────────────────────────

def resolver(exp: dict, consulta: Consulta) -> dict:
    """Resuelve UNA experiencia. Devuelve:
    {estado: 'resuelto'|'revision'|'na', cui, via, decision, candidatos[], obra}
    candidatos = [{cui, nombre_obra, departamento, score}] para la cola humana."""
    proyecto = exp.get("proyecto") or ""
    if not es_aplicable(proyecto):
        return {"estado": "na", "cui": None, "via": "NA",
                "decision": "obra privada o ajena a salud (no está en InfoObras)",
                "candidatos": [], "obra": None}

    # PASO 0 · CUI/SNIP explícito → determinístico (verificado)
    cui_campo = re.sub(r"\D", "", str(exp.get("cui") or ""))
    mcod = RE_CODIGO.search(proyecto)
    codigo = cui_campo if 4 <= len(cui_campo) <= 8 else (mcod.group(1) if mcod else None)
    if codigo:
        obras = consulta.por_codigo(codigo)
        if obras:
            o = obras[0]
            full = norm(o.get("nombrObra") or "")
            toks = _tokens_clave(establecimiento(proyecto))
            n_hit = len(toks & _palabras(full))
            depmatch = norm(o.get("nombrDepartamento") or "") in ubicacion(proyecto)
            obra = {"cui": codigo, "nombre_obra": o.get("nombrObra"),
                    "departamento": o.get("nombrDepartamento"),
                    "obra_id": o.get("codigoObra") or o.get("obraId")}
            if (toks and n_hit >= max(1, (len(toks) + 1) // 2)) or depmatch:
                return {"estado": "resuelto", "cui": codigo, "via": "CUI_TEXTO",
                        "decision": "código CUI verificado contra la obra",
                        "candidatos": [], "obra": obra}
            return {"estado": "revision", "cui": None, "via": "CUI_TEXTO",
                    "decision": "el código CUI del certificado no coincide con la obra — confirmar",
                    "candidatos": [{"cui": codigo, "nombre_obra": (o.get("nombrObra") or "")[:90],
                                    "departamento": o.get("nombrDepartamento"), "score": 50}],
                    "obra": None}

    # PASO 2 · por nombre + RUC + ubicación
    pn = norm(proyecto)
    deptos_hint = ubicacion(proyecto)
    fi = str(exp.get("fecha_inicial") or "")
    anio_cert = int(fi[:4]) if fi[:4].isdigit() else None
    mruc = RE_RUC.search(str(exp.get("ruc_emisor") or "") + " " + str(exp.get("entidad_emisora") or ""))
    ruc_cert = mruc.group(1) if mruc else None
    toks = _tokens_clave(establecimiento(proyecto))

    cands: dict[str, dict] = {}
    for f in fragmentos(proyecto):
        for o in consulta.buscar(f):
            cui = str(o.get("codSnip") or "").strip()
            if cui.isdigit() and len(cui) >= 3 and int(cui) != 0:
                cands.setdefault(cui, o)

    ranked = []
    for cui, o in cands.items():
        rej = str(o.get("rucEjecutor") or "").strip()
        rsup = str(o.get("rucSupervisor") or "").strip()
        ruc_match = bool(ruc_cert and ruc_cert in (rej, rsup))
        sc = _puntuar(o, pn, deptos_hint, anio_cert) + (30 if ruc_match else 0)
        ranked.append({"cui": cui, "nombre_obra": (o.get("nombrObra") or "")[:90],
                       "full": norm(o.get("nombrObra") or ""),
                       "departamento": o.get("nombrDepartamento"),
                       "obra_id": o.get("codigoObra") or o.get("obraId"),
                       "ruc_match": ruc_match, "score": round(sc, 1)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    best = ranked[0] if ranked else None

    n_hit = len(toks & _palabras(best["full"])) if best else 0
    gate = bool(best and toks and n_hit >= max(1, (len(toks) + 1) // 2))
    loc_contra = bool(deptos_hint and best and best.get("departamento")
                      and norm(best["departamento"]) not in deptos_hint
                      and not best.get("ruc_match"))

    candidatos = [{k: c[k] for k in ("cui", "nombre_obra", "departamento", "score")}
                  for c in ranked[:3]]
    obra_best = best and {"cui": best["cui"], "nombre_obra": best["nombre_obra"],
                          "departamento": best["departamento"], "obra_id": best.get("obra_id")}

    if best and best.get("ruc_match"):
        return {"estado": "resuelto", "cui": best["cui"], "via": "RUC",
                "decision": "el RUC del emisor es ejecutor/supervisor de la obra",
                "candidatos": candidatos, "obra": obra_best}
    if best and gate and best["score"] >= 70:
        return {"estado": "resuelto", "cui": best["cui"], "via": "NOMBRE",
                "decision": "establecimiento verificado por nombre",
                "candidatos": candidatos, "obra": obra_best}
    if best and (gate or best["score"] >= 90) and not loc_contra:
        return {"estado": "resuelto", "cui": best["cui"], "via": "PROBABLE",
                "decision": "candidato fuerte (conviene un vistazo)",
                "candidatos": candidatos, "obra": obra_best}
    motivo = ("la ubicación del certificado contradice al candidato"
              if loc_contra else "sin candidato fiable en InfoObras")
    return {"estado": "revision", "cui": None, "via": "NOMBRE",
            "decision": motivo, "candidatos": candidatos, "obra": None}


def _folio_base(folio) -> Optional[str]:
    m = re.search(r"\d{2,}", str(folio or ""))
    return m.group(0) if m else None


def resolver_con_dedup(experiencias: list[tuple[dict, object]], consulta: Consulta):
    """Itera [(exp, clave), …] resolviendo con herencia por folio (el '2º periodo
    del mismo certificado' hereda el CUI del hermano). Yields (clave, resultado)."""
    por_folio: dict[str, dict] = {}
    for exp, clave in experiencias:
        r = resolver(exp, consulta)
        fb = _folio_base(exp.get("folio"))
        if r["estado"] == "revision" and fb and fb in por_folio:
            heredado = por_folio[fb]
            r = {"estado": "resuelto", "cui": heredado["cui"], "via": "DEDUP",
                 "decision": "mismo certificado que otra experiencia ya identificada",
                 "candidatos": [], "obra": heredado.get("obra")}
        if r["estado"] == "resuelto" and fb:
            por_folio.setdefault(fb, r)
        yield clave, r
