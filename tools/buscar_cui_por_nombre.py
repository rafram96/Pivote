"""
buscar_cui_por_nombre.py — PROTOTIPO del método para resolver CUI desde el nombre.

Método (opción 2 del análisis): por cada experiencia,
  1. limpiar el nombre (quitar boilerplate de supervisión/contingencia),
  2. extraer fragmentos de búsqueda (establecimiento + nombre propio + arranque),
  3. buscar en InfoObras con cada fragmento (substring) y unir candidatos,
  4. PUNTUAR cada candidato: similitud de nombre + departamento + "salud" + fecha,
  5. decidir: AUTO si el mejor supera umbral con margen, si no → REVISIÓN.

Reusa el scraper de Alpamayo (NO clona). Prueba con las 4 experiencias del
Jefe de Supervisión del caso Libertador.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras\Alpamayo-InfoObras")
from src.scraping.infoobras import _crear_session, BASE_MAPA  # noqa: E402

try:
    from rapidfuzz import fuzz
    def sim(a, b): return fuzz.token_set_ratio(a, b)
except Exception:
    from difflib import SequenceMatcher
    def sim(a, b): return SequenceMatcher(None, a, b).ratio() * 100


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
    (re.compile(r"\bH\.\s(?=\w)", re.I), "Hospital "),  # H. genérico → Hospital (tras H.R.)
]


def expandir_abrev(t: str) -> str:
    for pat, full in ABREV:
        t = pat.sub(full, t)
    return t


_SALUD = re.compile(r"(salud|hospital|essalud|asistencial|policl[ií]nico|materno|"
                    r"\binsn\b|\binen\b|\bcmi\b|"
                    r"\bc\.\s?s\.|\be\.\s?s\.|\bp\.\s?s\.)", re.I)


def es_aplicable(proyecto: str) -> bool:
    """True si la obra es de salud pública (cruzable en InfoObras). False para
    obras privadas o ajenas a salud (cárcel, edificio comercial), que no están en
    InfoObras y no deben contar en la métrica de resolución. Expande abreviaturas
    primero ('H.'→Hospital, 'CMI'→Centro Materno) para no marcar falsos N/A."""
    return bool(_SALUD.search(expandir_abrev(proyecto or "")))


_RE_EST = re.compile(
    r"(hospital[^,(]*|puesto de salud[^,(]*|centro de salud[^,(]*|"
    r"establecimiento de salud[^,(]*|centro asistencial[^,(]*|"
    r"policl[ií]nico[^,(;]*|centro materno[^,(;]*|"
    r"\binsn\b[^,(;]*|\binen\b[^,(;]*)", re.I)


# Cola de metadata embebida en el nombre (formato BD_Experiencias): se corta para
# que no contamine el establecimiento ni la búsqueda. El código SNIP/CUI ya lo
# extrajo Paso 0 del texto crudo, así que cortarlo aquí es seguro.
_META = re.compile(
    r"(;.*$"                                   # todo tras el primer ';' (área, camas, monto, SNIP…)
    r"|\s[–\-]\s*SNIP\b.*$|\s[–\-]\s*CUI\b.*$"  # '– SNIP NNN' / '– CUI NNN'
    r"|,\s*S/\..*$"                            # ', S/.monto'
    r"|,?\s*\d[\d.,]*\s*(m²|m2|camas)\b.*$)", re.I)


def _sin_prefijo(proyecto: str) -> str:
    t = expandir_abrev(proyecto)
    for pat in PREFIJOS:
        t = re.sub(pat, "", t, flags=re.I).strip()
    t = _META.sub("", t).strip(" ;,–-.")
    return t


def establecimiento(proyecto: str) -> str:
    """Devuelve SOLO la frase del establecimiento (ej. 'Centro de Salud Ambo').
    De aquí salen los tokens distintivos para la compuerta — robusto a nombres
    propios cortos ('Ambo') que el armado de fragmentos podría descartar."""
    t = _sin_prefijo(proyecto)
    m = _RE_EST.search(t)
    return m.group(1).strip(" :,-.") if m else t


def ubicacion(proyecto: str) -> set[str]:
    """Departamento(s) explícito(s), tomados de las palabras DESPUÉS del
    establecimiento. Evita confundir el NOMBRE del establecimiento con un
    departamento homónimo (ej. 'E.S. La Libertad' que está en Junín, no en el
    departamento La Libertad). Si NO se reconoce un establecimiento (prefijo
    genérico), usa todo el texto para no perder el departamento."""
    t = _sin_prefijo(proyecto)
    tn = norm(t)
    m = _RE_EST.search(t)
    if m:
        est = norm(m.group(1).strip(" :,-."))
        i = tn.find(est)
        cola = tn[i + len(est):] if i >= 0 else tn
    else:
        cola = tn  # sin establecimiento extraído → todo el texto (no perder el depto)
    return {d for d in DEPTOS if d in cola}


_LEAD = re.compile(
    r"^(hospital regional|hospital|puesto de salud|centro de salud|"
    r"establecimiento de salud|centro asistencial|policl[ií]nico|centro materno|"
    r"especializado|regional|nuevo|de apoyo|de emergencias|"
    r"en la red asistencial|de la red asistencial|red asistencial|nivel\s*[\w-]+)\b\s*", re.I)
_COLA = re.compile(r"\s*[-–]\s*(es\s?salud|essalud|diresa|geresa|minsa)\b.*$", re.I)


def _nucleo(est: str) -> str:
    """Nombre propio 'limpio' del establecimiento (ej. 'Sicuani', 'Villa El
    Salvador', 'Chincheros'): quita iterativamente prefijos institucionales y
    colas tipo '- ESSALUD'. Mejora el recall de la búsqueda por substring."""
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
        nucleo = _nucleo(est)  # nombre propio limpio (Sicuani / Villa El Salvador / Chincheros)
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


_CACHE: dict[tuple, list] = {}  # (nombre, codsnip) -> resultados (evita re-consultar obras repetidas)


def _query(session, nombre="", codsnip=""):
    key = (nombre, codsnip)
    if key in _CACHE:
        return _CACHE[key]
    params = {"codDepartamento": "", "codProvincia": None, "codDistrito": None, "codigoObra": "",
              "estadoRegistro": "", "nobrCodmodejec": "", "cobrCodentpub": "", "codtipobrnv1": "",
              "codtipobrnv2": None, "nombrObra": nombre, "codSnip": codsnip, "fechaIniObraDesde": "",
              "fechaIniObraHasta": "", "tieneMonitor": "", "estObra": "", "codNivel3": None,
              "codMarca": "", "modServControl": "", "servControl": "", "nombreEntidad": "", "getFavoritos": 0}
    q = {"page": 0, "rowsPerPage": 20, "Parameters": json.dumps(params, separators=(",", ":"))}
    # Retry ante timeouts/errores transitorios de la API en vivo (no cachear el fallo).
    for intento in range(3):
        try:
            r = session.post(f"{BASE_MAPA}/Mapa/busqueda/obrasBasic", params=q, timeout=25)
            r.raise_for_status()
            res = r.json().get("Result", [])
            res = res if isinstance(res, list) else []
            _CACHE[key] = res
            return res
        except Exception:
            if intento == 2:
                return []  # sin cachear: que un próximo intento pueda reconsultar
    return []


def buscar(session, nombre: str) -> list[dict]:
    return _query(session, nombre=nombre)


def por_codigo(session, codigo: str) -> list[dict]:
    return _query(session, codsnip=str(codigo))


def anio_de(fecha_iniobra) -> int | None:
    if not fecha_iniobra:
        return None
    m = re.search(r"(\d{10,13})", str(fecha_iniobra))
    if m:
        try:
            return 1970 + int(int(m.group(1)) / (1000 * 60 * 60 * 24 * 365.25))
        except Exception:
            return None
    return None


def puntuar(cand: dict, proyecto_norm: str, deptos_hint: set[str], anio_cert: int | None) -> float:
    nombre = norm(cand.get("nombrObra") or "")
    score = sim(proyecto_norm, nombre)
    dep = norm(cand.get("nombrDepartamento") or "")
    if deptos_hint:
        if dep and dep in deptos_hint:
            score += 15            # ubicación explícita coincide → señal fuerte
        elif dep:
            score -= 20            # ubicación explícita NO coincide → penaliza (desambigua homónimos)
    if "SALUD" in nombre or "HOSPITAL" in nombre or "ESTABLECIMIENTO" in nombre:
        score += 5
    a = anio_de(cand.get("fechaIniObra"))
    if anio_cert and a and abs(a - anio_cert) <= 3:
        score += 8
    return round(score, 1)


_STOP = {"HOSPITAL", "PUESTO", "SALUD", "CENTRO", "ESTABLECIMIENTO", "REGIONAL",
         "DE", "DEL", "LA", "EL", "LOS", "Y", "APOYO", "NIVEL"}


def _palabras(s: str) -> set[str]:
    """Palabras alfabéticas SIN puntuación pegada (norm → split por no-letras)."""
    return set(re.findall(r"[A-Z]+", norm(s)))


def _tokens_clave(est_key: str) -> set[str]:
    return {t for t in _palabras(est_key) if len(t) >= 4 and t not in _STOP}


def resolver(exp: dict, session) -> dict:
    proyecto = exp["proyecto"]
    # ── Fuera de scope: obra privada o ajena a salud (no está en InfoObras) ──
    if not es_aplicable(proyecto):
        return {"via": "NA", "decision": "N/A (privado/ajeno a salud · sin cruce InfoObras)",
                "best": None, "frags": [], "toks": set(), "n_cands": 0, "ranked": []}
    # ── PASO 0: ¿CUI/SNIP? → determinístico. Prioriza el campo `cui` que extrae
    #            la skill; si no viene, lo busca en el texto del nombre. ─────────
    cui_campo = re.sub(r"\D", "", str(exp.get("cui") or ""))
    mcod = RE_CODIGO.search(proyecto)
    codigo = cui_campo if 4 <= len(cui_campo) <= 8 else (mcod.group(1) if mcod else None)
    if codigo:
        obras = por_codigo(session, codigo)
        if obras:
            o = obras[0]
            full = norm(o.get("nombrObra") or "")
            est = fragmentos(proyecto)
            est_key = establecimiento(proyecto)
            toks = _tokens_clave(est_key)
            n_hit = len(toks & _palabras(full))
            depmatch = norm(o.get("nombrDepartamento") or "") in ubicacion(proyecto)
            if toks and n_hit >= max(1, (len(toks) + 1) // 2):
                dec = "DETERMINÍSTICO ✅ (CUI en texto · nombre verificado)"
            elif depmatch:
                dec = "DETERMINÍSTICO ✅ (CUI en texto · ubicación verificada)"
            else:
                dec = "REVISIÓN 🔍 (CUI en texto NO verifica · código sospechoso)"
            return {"via": "CUI_TEXTO", "decision": dec,
                    "best": {"cui": codigo, "nombre": (o.get("nombrObra") or "")[:50],
                             "dep": o.get("nombrDepartamento"), "score": f"{n_hit}/{len(toks)}tok", "ruc": ""},
                    "frags": est, "toks": toks, "n_cands": len(obras), "ranked": []}

    # ── PASO 2: nombre + cruce RUC + ubicación ──────────────────────────────
    pn = norm(proyecto)
    deptos_hint = ubicacion(proyecto)  # departamento explícito (tras el establecimiento) → desambigua homónimos
    fi = exp.get("fecha_inicial") or ""
    anio_cert = int(fi[:4]) if fi[:4].isdigit() else None
    mruc = RE_RUC.search(exp.get("entidad_emisora", "") or "")
    ruc_cert = mruc.group(1) if mruc else None
    frags = fragmentos(proyecto)
    est_key = establecimiento(proyecto)
    toks = _tokens_clave(est_key)
    cands: dict[str, dict] = {}
    for f in frags:
        for o in buscar(session, f):
            cui = str(o.get("codSnip") or "").strip()
            if cui.isdigit() and len(cui) >= 3 and int(cui) != 0:
                cands.setdefault(cui, o)
    ranked = []
    for cui, o in cands.items():
        rej, rsup = str(o.get("rucEjecutor") or "").strip(), str(o.get("rucSupervisor") or "").strip()
        ruc_match = bool(ruc_cert and ruc_cert in (rej, rsup))
        sc = puntuar(o, pn, deptos_hint, anio_cert) + (30 if ruc_match else 0)
        ranked.append({"cui": cui, "nombre": (o.get("nombrObra") or "")[:42], "full": norm(o.get("nombrObra") or ""),
                       "dep": o.get("nombrDepartamento"), "ruc": "RUC✅" if ruc_match else "",
                       "ruc_match": ruc_match, "score": round(sc, 1)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    best = ranked[0] if ranked else None
    segundo = ranked[1]["score"] if len(ranked) > 1 else 0
    # Compuerta relajada: mayoría de tokens distintivos del establecimiento (no todos).
    n_hit = len(toks & _palabras(best["full"])) if best else 0
    gate = bool(best and toks and n_hit >= max(1, (len(toks) + 1) // 2))
    # Ubicación explícita contradice al mejor candidato → no confiar (salvo RUC).
    loc_contra = bool(deptos_hint and best and best.get("dep")
                      and norm(best["dep"]) not in deptos_hint
                      and not best.get("ruc_match"))
    if best and best.get("ruc_match"):
        decision = "DETERMINÍSTICO ✅ (RUC ejecutor/supervisor)"
    elif best and gate and best["score"] >= 70:
        # Gate de tokens fuerte manda aunque el departamento registrado discrepe.
        decision = "AUTO ✅ (establecimiento verificado)"
    elif best and (gate or best["score"] >= 90) and not loc_contra:
        decision = "PROBABLE ⚠ (candidato fuerte · spot-check)"
    elif loc_contra:
        decision = "REVISIÓN 🔍 (ubicación explícita contradice al candidato)"
    else:
        decision = "REVISIÓN 🔍 (sin candidato fiable)"
    return {"via": "NOMBRE", "decision": decision, "frags": frags, "est_key": est_key, "toks": toks,
            "ruc_cert": ruc_cert, "n_cands": len(cands), "ranked": ranked[:3], "best": best}


def _folio_base(folio) -> str | None:
    m = re.search(r"\d{2,}", str(folio or ""))
    return m.group(0) if m else None


def dias_efectivos(experiencias: list[dict]) -> dict | None:
    """Suma de días descontando traslapes (el profesional no está en 2 obras a la vez · ALT11)."""
    ivs = []
    for e in experiencias:
        a, b = str(e.get("fecha_inicial") or "")[:10], str(e.get("fecha_final") or "")[:10]
        try:
            ivs.append((date.fromisoformat(a), date.fromisoformat(b)))
        except Exception:
            pass
    if not ivs:
        return None
    ivs.sort()
    bruto = sum((b - a).days + 1 for a, b in ivs)
    merged = [list(ivs[0])]
    for a, b in ivs[1:]:
        if a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    efectivos = sum((b - a).days + 1 for a, b in merged)
    return {"bruto": bruto, "efectivos": efectivos, "traslape": bruto - efectivos}


def resolver_lote(experiencias: list[dict], session) -> list[dict]:
    """Resuelve una lista de experiencias con cache + dedup por folio (mismo certificado).
    Si una experiencia va a revisión pero un 'hermano' con el mismo folio ya resolvió un
    CUI, lo hereda (caso 'mismo certificado, 2º periodo')."""
    por_folio: dict[str, str] = {}
    resultados = []
    for e in experiencias:
        r = resolver(e, session)
        fb = _folio_base(e.get("folio"))
        cui = r["best"]["cui"] if r.get("best") else None
        if (cui is None or "REVISIÓN" in r["decision"]) and fb and fb in por_folio:
            cui = por_folio[fb]
            r = {"via": "DEDUP", "decision": "DEDUP ✅ (mismo certificado · hereda hermano)",
                 "best": {"cui": cui, "nombre": "(heredado)", "dep": ""},
                 "n_cands": 0, "ranked": [], "frags": [], "toks": set()}
        if cui and fb:
            por_folio.setdefault(fb, cui)
        resultados.append(r)
    return resultados


EXPERIENCIAS = [
    {"proyecto": "Mejoramiento de la Capacidad Resolutiva de los Servicios de Salud del Hospital Regional Hermilio Valdizan de Huanuco, Nivel II-1, Item 02: Ejecucion del Plan de Contingencia - Obras Complementarias", "fecha_inicial": "2016-06-10", "esperado": "37621?"},
    {"proyecto": "Construccion del Plan de Contingencia del proyecto Mejoramiento de la Cobertura de los Servicios de Salud del Hospital Ernesto Guzman Gonzales, Oxapampa, Pasco", "fecha_inicial": "2019-05-01", "esperado": "?"},
    {"proyecto": "Supervision de la obra: Mejoramiento de los Servicios de Salud del Puesto de Salud San Pedro de Cholon, Maranon, Huanuco", "fecha_inicial": "2021-05-13", "esperado": "361125"},
    {"proyecto": "Supervision: Mejora de la Capacidad Resolutiva y Operativa del Hospital Roman Egoavil Pando, Villa Rica, Oxapampa, Pasco", "fecha_inicial": "2023-11-22", "esperado": "95555"},
]


def main() -> int:
    session = _crear_session()
    aciertos = 0
    for i, exp in enumerate(EXPERIENCIAS, 1):
        r = resolver(exp, session)
        print(f"\n{'='*72}\nEXP {i} · esperado≈{exp['esperado']}")
        print(f"  proyecto: {exp['proyecto'][:64]}…")
        print(f"  fragmentos: {r['frags']}")
        print(f"  tokens clave del establecimiento: {sorted(r['toks'])}")
        print(f"  candidatos únicos: {r['n_cands']}")
        for c in r["ranked"]:
            print(f"    score={c['score']:>6} | cui={c['cui']:>7} | {c['nombre']} | {c['dep']}")
        print(f"  → DECISIÓN: {r['decision']}"
              + (f"  →  CUI {r['best']['cui']}" if r['best'] and ('AUTO' in r['decision'] or 'PROBABLE' in r['decision']) else ""))
        if r["best"] and exp["esperado"].rstrip("?") and r["best"]["cui"] == exp["esperado"].rstrip("?"):
            aciertos += 1
    print(f"\n{'='*72}\nResumen: {aciertos}/{len(EXPERIENCIAS)} con CUI esperado en el top-1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
