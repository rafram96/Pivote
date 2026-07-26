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
import logging
import re
import time
from datetime import date
from typing import Optional, Protocol

from observabilidad.traza import actual as _traza

# `norm`, `expandir_abrev` y la tabla `ABREV` viven ahora en `resolucion.texto`
# (extraídas para que la base local del MEF las reutilice sin arrastrar cui.py).
# Se re-exportan aquí con el mismo nombre: los tests y `etapas_reales` siguen
# importándolas desde `resolucion.cui`, y `_sim`/`establecimiento`/etc. las usan.
from resolucion.texto import ABREV, expandir_abrev, norm  # noqa: F401  (re-export)

logger = logging.getLogger(__name__)


class PortalNoResponde(Exception):
    """El portal de InfoObras no respondió tras los reintentos. Es DISTINTO de
    'la búsqueda no tuvo resultados': permite al resolver mandar la experiencia a
    revisión con un motivo honesto en vez de degradar al fragmento genérico."""


# rapidfuzz es dependencia DURA (requirements.txt). El fallback a difflib daba
# scores distintos (token_set_ratio vs ratio), así que la resolución de CUI
# variaba entre la laptop y el servidor — mejor fallar al importar que degradar
# en silencio la selección de obras.
from rapidfuzz import fuzz


def _sim(a: str, b: str) -> float:
    return fuzz.token_set_ratio(a, b)


# ── normalización y limpieza (idéntico al prototipo medido) ─────────────────
# `norm` se importa arriba de `resolucion.texto` (re-exportada en este namespace).

PREFIJOS = [
    r"consultor[ií]a de obra para la supervisi[oó]n de la obra\s*:?",
    r"elaboraci[oó]n del expediente t[eé]cnico y ejecuci[oó]n de la obra\s*:?",
    r"elaboraci[oó]n del expediente t[eé]cnico\s*:?",
    r"supervisi[oó]n de la obra\s*:?",
    r"construcci[oó]n del plan de contingencia del proyecto\s*",
    r"implementaci[oó]n del plan de contingencia.*?obra\s*:?",
    r"ejecuci[oó]n de (?:la )?obra\s*:?",
    r"supervisi[oó]n\s*:?",
    # Envoltorio de CONSULTORÍA/EXPEDIENTE/ESTUDIO: el proyecto real va adentro y SÍ
    # está en InfoObras bajo su nombre. Quitar el envoltorio mejora el recall de las
    # experiencias de expediente (que hoy caen en "sin candidato"). El chequeo de
    # cobertura evita que limpiar de más meta un CUI equivocado.
    r"consultor[ií]a para la elaboraci[oó]n de (?:\w+\s+)?(?:\(\s*\d+\s*\)\s*)?expedientes? t[eé]cnicos?(?:\s+de)?\s*:?",
    r"expedientes? t[eé]cnicos?(?:\s+definitivos?)?(?:\s+integral(?:es)?)?(?:\s+agroindustrial)?\s*(?:de\s+|para\s+(?:la\s+|el\s+)?|:\s*)",
    r"estudio de (?:pre\s?inversi[oó]n|factibilidad|ingenier[ií]a)(?:\s+a nivel(?:\s+de\s+\w+)?)?\s*(?:de\s+|del\s+|:\s*)?",
    r"proyecto definitivo(?:\s+integral)?\s+",
    r"anteproyecto y proyecto arquitect[oó]nico de\s+",
    # sufijo entre paréntesis: "... (Expediente Técnico)", "... (Estudio de Preinversión ...)"
    r"\((?:expediente t[eé]cnico|estudio de pre\s?inversi[oó]n[^)]*|desarrollo del proyecto[^)]*|dise[ñn]o arquitect[oó]nico[^)]*)\)",
    r"^para (?:la|el|los|las)\s+",   # remanente tras quitar "expediente técnico para..."
]
DEPTOS = [
    "AMAZONAS", "ANCASH", "APURIMAC", "AREQUIPA", "AYACUCHO", "CAJAMARCA",
    "CALLAO", "CUSCO", "HUANCAVELICA", "HUANUCO", "ICA", "JUNIN", "LA LIBERTAD",
    "LAMBAYEQUE", "LIMA", "LORETO", "MADRE DE DIOS", "MOQUEGUA", "PASCO",
    "PIURA", "PUNO", "SAN MARTIN", "TACNA", "TUMBES", "UCAYALI"
]

# Abreviaturas de departamento que aparecen en certificados / nomenclatura OSCE
# (p.ej. "GOB.REG.HVCA"). Se expanden al nombre completo antes de detectar el
# departamento, para que "Lircay - HVCA" cuente como Huancavelica.
DEPTO_ALIAS = {"HVCA": "HUANCAVELICA"}

# `ABREV` y `expandir_abrev` se importan arriba de `resolucion.texto`.

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
    t = _META.sub("", t).strip(" ;,–-.")
    # Envoltorio de estudio/expediente con ":" → el proyecto real va DESPUÉS del ":"
    # (p.ej. "…Definitivo Agroindustrial: CONSTRUCCIÓN DE UNA PLANTA"). Solo si lo de
    # antes es corto y trae vocabulario de estudio — para NO cortar nombres reales.
    if ":" in t:
        antes, despues = t.split(":", 1)
        if (len(antes.split()) <= 5 and len(despues.strip()) >= 12
                and re.search(r"expediente|estudio|definitiv|preinversi|t[eé]cnic|agroindustrial",
                              antes, re.I)):
            t = despues
    t = re.sub(r"\(\s*\)", "", t)                      # paréntesis vacío que dejó un sufijo
    return re.sub(r"\s{2,}", " ", t).strip(" ;,–-.")


# Experiencia de EXPEDIENTE técnico (o estudio/consultoría de proyecto): NO tiene
# valorizaciones en InfoObras, su respaldo es el hito "Aprobación del proyecto".
# Solo estas experiencias aceptan esa aprobación como sustento; una obra de
# construcción sin valorizaciones sigue yendo a revisión (no es un expediente).
_RE_EXPEDIENTE = re.compile(
    r"expediente\s+t[eé]cnico"
    r"|consultor[ií]a\s+para\s+la\s+elaboraci[oó]n"
    r"|estudio\s+de\s+(?:pre\s?inversi[oó]n|factibilidad|ingenier[ií]a|perfil)"
    r"|proyecto\s+definitivo"
    r"|anteproyecto\b"
    r"|elaboraci[oó]n\s+del\s+(?:expediente|proyecto|estudio)",
    re.I)


def _es_experiencia_expediente(proyecto: str) -> bool:
    """True si el nombre de la experiencia es de expediente técnico / estudio /
    consultoría de proyecto (no una obra ejecutada). Se apoya en el nombre crudo
    y en el expandido de abreviaturas para no depender del OCR."""
    if not proyecto:
        return False
    return bool(_RE_EXPEDIENTE.search(proyecto)
                or _RE_EXPEDIENTE.search(expandir_abrev(proyecto)))


def es_expediente_exp(exp: dict) -> bool:
    """Clasificación expediente/obra mirando TODA la evidencia de la experiencia,
    no solo `proyecto`. Caso real (San Isidro P1:E2): el certificado dice "se ha
    desempeñado … en la Elaboración del Expediente Técnico: «MEJORAMIENTO …»" y
    la skill guarda en `proyecto` solo el nombre entre comillas — la palabra
    "expediente" vive en el DESEMPEÑO (objeto/cargo), y clasificar solo por el
    nombre enruta el expediente como obra (descarga valorizaciones en vez del
    contrato/resolución del MEF). Campos: proyecto + objeto + cargo_ocupado
    (NO observaciones: mencionan "expediente" de pasada)."""
    texto = " ".join(str(exp.get(k) or "") for k in
                     ("proyecto", "objeto", "cargo_ocupado"))
    return _es_experiencia_expediente(texto)


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
    for ab, full in DEPTO_ALIAS.items():
        cola = re.sub(rf"\b{ab}\b", full, cola)
    # límite de palabra: evita que "ICA" matchee dentro de "HUANCAVELICA"
    return {d for d in DEPTOS if re.search(rf"\b{d}\b", cola)}


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


_RE_NUM_INST = re.compile(
    r"(?:n[°º]|i\.?\s?e\.?i?\.?|c\.?\s?e\.?|educativ\w*|escolar|inicial|"
    r"primaria|secundaria|colegio)\s*n?[°º]?\s*(\d{3,6})", re.I)


def _numero_obra(texto: str) -> set[str]:
    """Números de institución (I.E./C.E./colegio, p. ej. '1452', '14078') en un
    nombre de obra. Es la señal MÁS distintiva de una obra educativa: matchea
    aunque el nombre tenga otro formato ('N°1452.' vs 'N° 1452') y distingue
    instituciones (I.E. 359 ≠ I.E. 1435). Devuelve el set (sin ceros a la izq)."""
    return {str(int(m.group(1))) for m in _RE_NUM_INST.finditer(texto or "")}


def fragmentos(proyecto: str) -> list[str]:
    t = _sin_prefijo(proyecto)
    frags: list[str] = []
    # número de I.E./C.E. → fragmento de búsqueda distintivo (los de ≥4 díg pasan
    # el filtro de abajo; los de 3 caen pero igual puntúan en _puntuar)
    frags.extend(sorted(_numero_obra(proyecto)))
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

# Palabras que NO identifican una obra (aparecen en miles de nombres). Sin esto,
# un certificado educativo matcheaba cualquier obra con MEJORAMIENTO+INFRAESTRUCTURA
# +EDUCATIVA aunque el nombre propio (KREAR, CATHOLIC…) no apareciera — queja real
# del cliente 14-jul: "reporta un mal resultado / nada tiene que ver".
_STOP = {"HOSPITAL", "PUESTO", "SALUD", "CENTRO", "ESTABLECIMIENTO", "REGIONAL",
         "DE", "DEL", "LA", "EL", "LOS", "Y", "APOYO", "NIVEL",
         # verbos/genéricas de obra
         "MEJORAMIENTO", "AMPLIACION", "CONSTRUCCION", "CREACION", "REHABILITACION",
         "RECUPERACION", "INSTALACION", "IMPLEMENTACION", "EQUIPAMIENTO",
         "MANTENIMIENTO", "REMODELACION", "SUPERVISION", "EJECUCION", "ELABORACION",
         # sustantivos genéricos
         "INFRAESTRUCTURA", "SERVICIO", "SERVICIOS", "SISTEMA", "OBRA", "PROYECTO",
         "EXPEDIENTE", "TECNICO", "INTEGRAL", "ETAPA", "CALIDAD", "CAPACIDAD",
         "RESOLUTIVA", "ATENCION", "COBERTURA",
         # educación (tan genéricas como 'salud' en su rubro)
         "INSTITUCION", "EDUCATIVA", "EDUCATIVO", "EDUCACION", "INICIAL",
         "PRIMARIA", "SECUNDARIA", "COLEGIO", "ESCUELA",
         # geografía administrativa (no identifican al establecimiento)
         "DISTRITO", "PROVINCIA", "DEPARTAMENTO", "REGION", "LOCALIDAD", "SECTOR",
         # "CENTRO POBLADO" es tan genérico como "localidad" — con POBLADO como
         # token, un Puesto de Salud del C.P. X matcheaba la losa deportiva del
         # mismo C.P. X (caso Chinchinga, auditoría 20-jul)
         "POBLADO"}


# ── RUBRO del servicio: compuerta ORTOGONAL a los tokens ─────────────────────
# Las palabras de rubro (SALUD, EDUCATIVA…) están en _STOP a propósito: dentro de
# su rubro no identifican la obra (queja 14-jul). Pero descartarlas del todo dejó
# al resolver CIEGO al TIPO de servicio: un Puesto de SALUD resolvió a una losa
# DEPORTIVA del mismo centro poblado (caso Chinchinga — error SILENCIOSO, quedó
# como BAJO riesgo). El rubro no suma puntos: VETA contradicciones. Un candidato
# de rubro contradictorio jamás puede ganar, sin importar el score de topónimos.
_RUBROS: dict[str, re.Pattern] = {
    "salud": re.compile(r"\b(SALUD|HOSPITAL(ES)?|POSTA|CLINICA|ESSALUD)\b"),
    "educacion": re.compile(r"\b(EDUCATIV[AO]S?|EDUCACION|ESCUELA|COLEGIO|PRONOEI|"
                            r"INICIAL|PRIMARIA|SECUNDARIA|UNIVERSIDAD|PEDAGOGIC\w*|"
                            r"I\s?E\s?[PS]?\b|INSTITUTO)\b"),
    "deporte": re.compile(r"\b(DEPORTIV[AO]S?|RECREATIV[AO]S?|ESTADIO|COLISEO|"
                          r"LOSA(S)?|GRADERI\w*|POLIDEPORTIVO)\b"),
    "saneamiento": re.compile(r"\b(SANEAMIENTO|ALCANTARILLADO|DESAGUE|LETRINA(S)?|"
                              r"AGUA POTABLE|RESIDUOS)\b"),
    "vial": re.compile(r"\b(CARRETERA|CAMINO(S)?|TRANSITABILIDAD|VECINAL(ES)?|"
                       r"PUENTE(S)?|PAVIMENT\w*|PISTAS|VEREDAS|TROCHA|VIAL)\b"),
    "riego": re.compile(r"\b(RIEGO|IRRIGACION|REPRESA)\b"),
    "electrico": re.compile(r"\b(ELECTRIFICACION|REDES (PRIMARIAS|SECUNDARIAS))\b"),
}


def rubros_de(texto: str) -> set[str]:
    """Rubros de servicio detectados en un nombre de obra/certificado (puede ser
    más de uno; vacío = indeterminado, que NUNCA veta)."""
    n = norm(texto or "")
    return {r for r, pat in _RUBROS.items() if pat.search(n)}


def _rubro_contradice(rub_cert: set[str], texto_obra: str) -> bool:
    """True si ambos lados declaran rubro y NO comparten ninguno. Un lado
    indeterminado (set vacío) jamás veta — el veto exige contradicción positiva."""
    if not rub_cert:
        return False
    rub_obra = rubros_de(texto_obra)
    return bool(rub_obra) and not (rub_cert & rub_obra)


# ── UBIGEO del certificado: provincia/distrito (veto de ubicación, F8) ────────
# Señal ORTOGONAL al DEPARTAMENTO: dos obras del MISMO departamento pero de
# PROVINCIAS distintas son proyectos DISTINTOS (auditoría job c9c769976750:
# San Agustín-Huancayo→El Tambo, Jaén-Cajamarca→Magdalena-Lima, PTAR Jauja→Tarma).
# El MEF trae prov/dist por CUI (base_mef); el certificado los declara en el texto
# ("provincia de X", "Municipalidad Distrital de Y") y en su cola geográfica
# ("…, Jauja, Junín") o el campo `ubicacion` del espejo.
#
# CUIDADO (documentado, ver _puntuar): el MEF a veces registra la inversión bajo la
# sede de la entidad EJECUTORA, no la ubicación física de la obra. Por eso:
#   • el VETO exige contradicción de PROVINCIA con AMBAS partes declaradas
#     explícitamente (nunca por ausencia de datos de un lado);
#   • una contradicción SOLO de distrito (misma provincia) PENALIZA (−25), no veta
#     (obras intermunicipales existen);
#   • sin ficha MEF del candidato la señal es INERTE (no cambia nada).
_DEPTOS_SET = set(DEPTOS)

_RE_PROV_KW = re.compile(
    r"provincia(?:l)?\s+de\s+([A-Za-zÁÉÍÓÚÜÑ.' ]+?)"
    r"(?=\s*[,;\-–|(/]|\s+provincia|\s+distrit|\s+departamento|\s+regi[oó]n|\s+dpto|$)",
    re.I)
_RE_DIST_KW = re.compile(
    r"distrit(?:o|al)\s+de\s+([A-Za-zÁÉÍÓÚÜÑ.' ]+?)"
    r"(?=\s*[,;\-–|(/]|\s+provincia|\s+distrit|\s+departamento|\s+regi[oó]n|\s+dpto|$)",
    re.I)

# rótulos que preceden a un topónimo en la cola geográfica; se quitan para dejar
# el nombre limpio ("PROVINCIA DE JAUJA" → "JAUJA")
_RE_ROTULO_GEO = re.compile(
    r"^(provincia|prov|distrito|dist|departamento|dpto|regi[oó]n|reg|localidad|"
    r"sector|centro poblado|c\.?p\.?)\s+(de\s+)?", re.I)


def _deptos_en(texto: str) -> set[str]:
    """Departamentos nombrados en un texto (con alias HVCA→HUANCAVELICA)."""
    n = norm(texto or "")
    for ab, full in DEPTO_ALIAS.items():
        n = re.sub(rf"\b{ab}\b", full, n)
    return {d for d in DEPTOS if re.search(rf"\b{d}\b", n)}


def _terminos_geo(texto: str) -> list[str]:
    """Términos de ubicación (limpios de rótulo) en el orden del texto, partiendo
    por separadores geográficos (coma, guion, barra, paréntesis)."""
    t = norm(expandir_abrev(texto or ""))
    for ab, full in DEPTO_ALIAS.items():
        t = re.sub(rf"\b{ab}\b", full, t)
    out: list[str] = []
    for p in re.split(r"[,;\-–|()/]", t):
        p = _RE_ROTULO_GEO.sub("", p.strip()).strip(" .-")
        p = re.sub(r"^DE\s+", "", p).strip()
        if p:
            out.append(p)
    return out


def _provincia_desde_cola(terminos: list[str]) -> set[str]:
    """Provincia por ANCLA de departamento: en "…, <dist>, <prov>, <depto>" el
    término inmediatamente ANTES de un departamento conocido es la provincia.
    Exige al menos TRES niveles (algo, prov, depto): con solo dos ("…HUARI,
    ANCASH") el término previo puede ser distrito o localidad y un falso
    positivo de provincia VETA — mejor no inferir."""
    provs: set[str] = set()
    for i, t in enumerate(terminos):
        if (t in _DEPTOS_SET and i - 2 >= 0
                and terminos[i - 1] not in _DEPTOS_SET
                and terminos[i - 2] not in _DEPTOS_SET):
            provs.add(terminos[i - 1])
    return provs


def ubigeo_cert(exp: dict) -> dict:
    """Señales de ubicación DECLARADAS por el certificado: provincia(s),
    distrito(s), departamento(s) y el pool completo de términos de ubicación.
    Mira `proyecto` + `ubicacion` + `entidad_contratante` del espejo."""
    proyecto = str(exp.get("proyecto") or "")
    ubic = str(exp.get("ubicacion") or "")
    ent = str(exp.get("entidad_contratante") or "")
    texto = " || ".join((proyecto, ubic, ent))
    prov = {norm(m) for m in _RE_PROV_KW.findall(texto) if len(norm(m)) >= 3}
    dist = {norm(m) for m in _RE_DIST_KW.findall(texto) if len(norm(m)) >= 3}
    terms_proj = _terminos_geo(proyecto)
    terms_ubic = _terminos_geo(ubic)
    prov |= _provincia_desde_cola(terms_proj)
    prov |= _provincia_desde_cola(terms_ubic)
    depto = ubicacion(proyecto) | _deptos_en(ubic) | _deptos_en(ent)
    loc = set(prov) | set(dist) | set(terms_proj) | set(terms_ubic) | set(depto)
    return {"prov": prov, "dist": dist, "depto": depto, "loc": loc}


_RE_MUNI = re.compile(r"\bMUNICIPALIDAD\s+(DISTRITAL|PROVINCIAL)\s+DE\s+"
                      r"([A-Z' ]+?)(?=\s*[,;()/|]|\s+PROVINCIA|\s+DISTRITO|"
                      r"\s+DEPARTAMENTO|\s+REGION|$)")


def _munis_de(texto_norm: str) -> set[tuple[str, str]]:
    """Municipalidades (tipo, nombre) mencionadas en un texto YA normalizado.
    "MUNICIPALIDAD DISTRITAL DE SAN AGUSTIN" → {("DISTRITAL", "SAN AGUSTIN")}."""
    return {(t, n.strip()) for t, n in _RE_MUNI.findall(texto_norm or "") if n.strip()}


def _muni_contradice(exp: dict, ficha: Optional[dict]) -> bool:
    """True si el CONTRATANTE del certificado es una municipalidad y la entidad
    MEF del candidato es OTRA municipalidad del mismo tipo (distrital vs distrital):
    dos municipalidades distintas no contratan la misma obra (caso auditado
    San Agustín→El Tambo). Exige municipalidad EN AMBOS lados; cualquier otra
    combinación (gobierno regional, ministerio, ausencia) es inerte."""
    if not ficha:
        return False
    munis_cert = _munis_de(norm(str(exp.get("entidad_contratante") or "")))
    if not munis_cert:
        return False
    munis_mef = _munis_de(norm(str(ficha.get("entidad") or "")))
    if not munis_mef:
        return False
    for tc, nc in munis_cert:
        for tm, nm in munis_mef:
            if tc == tm and _loc_eq(nc, nm):
                return False           # misma municipalidad → sin contradicción
    return True


def _loc_eq(a: str, b: str) -> bool:
    """Igualdad de topónimo: normalizado idéntico o uno contenido en el otro (con
    largo ≥ 4 para evitar coincidencias triviales)."""
    if not a or not b:
        return False
    if a == b:
        return True
    corto, largo = (a, b) if len(a) <= len(b) else (b, a)
    return len(corto) >= 4 and re.search(rf"\b{re.escape(corto)}\b", largo) is not None


def _ubigeo_contra(sig: dict, ficha: Optional[dict]) -> tuple[bool, bool, bool]:
    """(prov_contra, dist_contra, depto_contra) del certificado vs la ficha MEF de
    un candidato. Cada contradicción exige AMBAS partes declaradas y que el valor
    del MEF no aparezca en NINGÚN término de ubicación del certificado (evita vetar
    cuando el MEF registra la provincia donde el cert la nombró como distrito)."""
    if not ficha:
        return (False, False, False)
    loc = sig["loc"]
    prov_mef = norm(ficha.get("prov") or "")
    dist_mef = norm(ficha.get("dist") or "")
    depto_mef = norm(ficha.get("dpto") or "")

    def _contra(cert_set: set[str], val_mef: str) -> bool:
        if not cert_set or not val_mef:
            return False
        if any(_loc_eq(c, val_mef) for c in cert_set):
            return False               # el MEF coincide con lo declarado
        if any(_loc_eq(x, val_mef) for x in loc):
            return False               # el MEF aparece en otra parte de la ubicación
        return True

    return (_contra(sig["prov"], prov_mef),
            _contra(sig["dist"], dist_mef),
            _contra(sig["depto"], depto_mef))


def _palabras(s: str) -> set[str]:
    return set(re.findall(r"[A-Z]+", norm(s)))


# La cola geográfica del nombre ("…, distrito de Trujillo - Trujillo - La Libertad")
# NO identifica al establecimiento: mil obras comparten distrito. Sin este corte,
# "TRUJILLO" contaba como token distintivo y una obra ajena del mismo distrito
# pasaba el gate (queja del cliente: matches "que nada tienen que ver").
_RE_COLA_GEO = re.compile(
    r"[,;]?\s*[–\-]?\s*\b(distrito|provincia|departamento|regi[oó]n|localidad(es)?)\b.*$",
    re.I)


def _tokens_clave(est_key: str) -> set[str]:
    sin_geo = _RE_COLA_GEO.sub("", est_key or "")
    return {t for t in _palabras(sin_geo) if len(t) >= 4 and t not in _STOP}


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


def _puntuar(cand: dict, proyecto_norm: str, deptos_hint: set[str],
             anio_cert: Optional[int], nums_cert: frozenset = frozenset()) -> float:
    nombre = norm(cand.get("nombrObra") or "")
    score = _sim(proyecto_norm, nombre)
    # número de institución: la señal MÁS fuerte para obras educativas. Mismo N° de
    # I.E./C.E. → casi seguro la misma obra; N° distinto → otra institución (precisión).
    if nums_cert:
        nums_cand = _numero_obra(cand.get("nombrObra") or "")
        if nums_cand:
            score += 40 if (nums_cert & nums_cand) else -15
    dep = norm(cand.get("nombrDepartamento") or "")
    if deptos_hint:
        if dep and dep in deptos_hint:
            score += 15
        elif dep:
            # penalización SUAVE: el MEF a veces registra la obra bajo el
            # departamento de la sede/entidad ejecutora, no el de la obra física,
            # así que un mismatch no debe enterrar a la obra correcta. El veredicto
            # final lo protegen la cobertura de valorizaciones y `loc_contra`.
            score -= 10
    if "SALUD" in nombre or "HOSPITAL" in nombre or "ESTABLECIMIENTO" in nombre:
        score += 5
    a = _anio_de(cand.get("fechaIniObra"))
    if anio_cert and a and abs(a - anio_cert) <= 3:
        score += 8
    return round(score, 1)


def _mef_desactivada(ficha: Optional[dict]) -> bool:
    """True si la ficha del MEF corresponde a una inversión DESACTIVADA.

    El dato ya viajaba en la base local (`estado_dataset`) desde F3 y NADIE lo leía:
    229k de las 494k filas son desactivadas y competían de igual a igual con las
    vivas. Se usa como DESEMPATE y como orden del presupuesto de consultas al
    portal — nunca como filtro que borra un candidato: un CUI reformulado queda
    desactivado y el certificado bien puede citar al viejo (15 de 191 verdades
    auditadas viven en filas DESACTIVADA)."""
    return bool(ficha) and (ficha.get("estado_dataset") or "") == "DESACTIVADA"


def _ficha_mef(cui: Optional[str], base, fichas_mef: dict) -> Optional[dict]:
    """Ficha MEF de un CUI: primero el mapa recolectado en la fusión
    (`exp['_fichas_mef']`), luego `base.existe_cui` (rescata CUIs que InfoObras
    trajo por nombre pero la fusión no fetcheó). None si no hay base o no existe."""
    if not cui:
        return None
    f = (fichas_mef or {}).get(cui)
    if f is not None:
        return f
    if base and base.disponible():
        return base.existe_cui(cui)
    return None


def _bonus_mef(cand: dict, cui: Optional[str], exp: dict, base, fichas_mef: dict,
               proyecto_norm: str, deptos_hint: set[str]) -> float:
    """F3 · Señales de identidad de la ficha MEF del CUI (delta ADITIVO al score):

      1. Nombre: si el nombre OFICIAL del MEF se parece más al certificado que el
         (a veces corrupto) de InfoObras, se suma la diferencia → el score de nombre
         efectivo es max(sim_infoobras, sim_mef) (rescata el caso Chinchinga).
      2. Dpto/ubigeo oficial: +10 si el dpto de la ficha MEF coincide con los hints
         del certificado; −10 EXTRA (una sola vez) solo si InfoObras Y MEF contradicen.
      3. Entidad: +15 si la entidad de la ficha MEF calza (token_set_ratio ≥ 90) con
         `entidad_contratante` del certificado. NUNCA resta (la UEI puede diferir).

    Devuelve 0.0 sin base/ficha → comportamiento actual intacto."""
    ficha = _ficha_mef(cui, base, fichas_mef)
    if not ficha:
        return 0.0
    bonus = 0.0
    nombre_mef = norm(ficha.get("nombre") or "")
    if nombre_mef:
        sim_io = _sim(proyecto_norm, norm(cand.get("nombrObra") or ""))
        sim_mef = _sim(proyecto_norm, nombre_mef)
        if sim_mef > sim_io:
            bonus += sim_mef - sim_io
    dpto_mef = norm(ficha.get("dpto") or "")
    dpto_io = norm(cand.get("nombrDepartamento") or "")
    if deptos_hint and dpto_mef:
        if dpto_mef in deptos_hint:
            bonus += 10
        elif dpto_io and dpto_io not in deptos_hint:
            # tanto InfoObras como MEF contradicen la ubicación del cert → −10 extra
            bonus -= 10
    ent_cert = norm(exp.get("entidad_contratante") or "")
    ent_mef = norm(ficha.get("entidad") or "")
    if ent_cert and ent_mef and fuzz.token_set_ratio(ent_cert, ent_mef) >= 90:
        bonus += 15
    return round(bonus, 1)


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
        self._rango_cache: dict[object, tuple] = {}

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
                _t0 = time.perf_counter()
                r = self._ses().post(f"{BASE_MAPA}/Mapa/busqueda/obrasBasic",
                                     params=q, timeout=25)
                r.raise_for_status()
                res = r.json().get("Result", [])
                res = res if isinstance(res, list) else []
                _traza().ev("infoobras_query", nombre=nombre or None,
                            codsnip=codsnip or None, hits=len(res), intento=intento + 1,
                            ms=round((time.perf_counter() - _t0) * 1000, 1))
                # solo al buscar por código: filtro exacto (la API matchea
                # codSnip por substring; '95555' traería '2595555'). En la
                # búsqueda por nombre NO se filtra (el código no es la query).
                if codsnip:
                    from scraping.infoobras import coincide_codigo
                    res = [o for o in res if coincide_codigo(o, codsnip)]
                self._cache[key] = res
                return res
            except Exception as e:  # noqa: BLE001 — API pública intermitente
                # Backoff entre reintentos: una microcaída del portal hacía
                # fallar los 3 intentos en milisegundos → el resolver asumía
                # "sin resultados" y degradaba al fragmento genérico (caso 6:1).
                # Se loguea para que el fallo deje de ser silencioso.
                logger.warning("InfoObras búsqueda (nombre=%r codsnip=%r) intento %d/3: %r",
                               nombre, codsnip, intento + 1, e)
                if intento < 2:
                    time.sleep(1.5 * (intento + 1))
        # agotados los reintentos: el portal no respondió. Se SEÑALA (≠ vacío)
        # para que el resolver no degrade al fragmento genérico.
        raise PortalNoResponde(f"InfoObras no respondió (nombre={nombre!r} codsnip={codsnip!r})")

    def por_codigo(self, codigo: str) -> list[dict]:
        return self._query(codsnip=str(codigo))

    def buscar(self, nombre: str) -> list[dict]:
        return self._query(nombre=nombre)

    def rango(self, obra_id) -> tuple:
        """Rango REAL de valorizaciones (min, max mes) de una obra, desde
        DatosEjecucion/lAvances — el dato que dice CUÁNDO la obra tuvo plata
        moviéndose (a diferencia de `fechaIniObra`, que miente). Devuelve
        (None, None) si no hay avances o el portal no respondió. Cacheado por obra.

        YA NO participa en la SELECCIÓN de CUI (se eliminó el re-rank por solape:
        usaba el periodo declarado —el dato bajo auditoría— para reordenar). Solo
        queda para consumidores externos (p. ej. `scripts/golden_cui.py`)."""
        if obra_id in self._rango_cache:
            return self._rango_cache[obra_id]
        r: tuple = (None, None)
        try:
            from scraping.infoobras import _extraer_datos_ejecucion, _procesar_avances
            avs = _procesar_avances(
                _extraer_datos_ejecucion(self._ses(), obra_id).get("lAvances", []))
            meses = [date(a.anio, a.mes, 1) for a in avs
                     if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
            if meses:
                r = (min(meses), max(meses))
        except Exception:  # noqa: BLE001 — portal intermitente → rango desconocido
            pass
        self._rango_cache[obra_id] = r
        return r


# ── selección de obra cuando un CUI trae varias ──────────────────────────────

def _fecha_cert(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _elegir_obra(obras: list[dict], cert_ini=None, cert_fin=None) -> dict:
    """Prefiere la obra FINALIZADA que cubre el periodo del certificado. Delega
    en el selector del scraper; si no está disponible, cae a la primera."""
    try:
        from scraping.infoobras import seleccionar_obra
        return seleccionar_obra(obras, cert_ini, cert_fin) or obras[0]
    except Exception:  # noqa: BLE001 — entorno sin el scraper
        return obras[0]


# ── resolución ───────────────────────────────────────────────────────────────

def _cui_de(o: dict) -> Optional[str]:
    """CUI oficial de un registro: se prefiere `codUniqInv` (CUI único, 7 díg)
    sobre `codSnip` (SNIP heredado, 5-6 díg). El de 7 díg es clave estable y
    evita colisiones por substring en la API (buscar '95555' trae '2595555')."""
    for campo in ("codUniqInv", "codSnip"):
        v = str(o.get(campo) or "").strip()
        if v.isdigit() and len(v) >= 3 and int(v) != 0:
            return v
    return None


def _num(v) -> int:
    """Entero de un id/código para desempates DETERMINÍSTICOS. Los no numéricos
    van al final (sentinela alto) para que el orden sea total y reproducible."""
    s = str(v if v is not None else "").strip()
    return int(s) if s.isdigit() else 10 ** 18


# Cliente/obra PRIVADA: InfoObras solo registra obra PÚBLICA. Una experiencia con
# promotor privado ("Institución Educativa Particular X", "I.E.P.", colegios
# privados…) NO debe buscarse por nombre: siempre matchea alguna obra pública
# parecida y reporta basura (queja real del cliente, 14-jul: Catholic High School
# → una carretera; Trinity College → obra ajena).
#
# La señal debe ser PRECISA: la palabra "privada/particular" suelta dispara falsos
# positivos en obra pública ("predios de PROPIEDAD PRIVADA", "asociación PÚBLICO
# PRIVADA", "obra por impuestos con INVERSIÓN PRIVADA"), y "I.E.P. N° 70480" es una
# primaria PÚBLICA. Por eso se exige:
#   1. el adjetivo pegado a un sustantivo de colegio (educativa/colegio/…/gestión),
#      lo que descarta propiedad/inversión/público privada; o
#   2. la sigla I.E.P./C.E.P. SOLO cuando le sigue un NOMBRE (no un número: los
#      colegios públicos se citan por número, los privados por nombre).
# Mira proyecto + entidad_contratante (el emisor NO cuenta: en obra pública el
# emisor es un privado — el contratista — siempre).
_RE_PRIVADA = re.compile(
    r"\b(?:educativ[ao]|colegio|escuela|jard[ií]n|nido|instituto|gesti[oó]n)\s+"
    r"(?:particular(?:es)?|privad[ao]s?)\b"
    r"|\b[ic]\.?\s?e\.?\s?p\b(?!\.?\s*n?[°º]?\s*\d)", re.I)


def _es_experiencia_privada(exp: dict) -> bool:
    """True si el CLIENTE/promotor de la experiencia es privado (no una entidad
    pública). Mira proyecto + entidad_contratante (+ ubicación textual del cert);
    NO mira al emisor (el contratista privado es lo normal en obra pública)."""
    campos = " ".join(str(exp.get(k) or "") for k in
                      ("proyecto", "entidad_contratante", "objeto"))
    return bool(_RE_PRIVADA.search(campos))


def resolver(exp: dict, consulta: Consulta, base=None) -> dict:
    """Resuelve UNA experiencia. Devuelve:
    {estado: 'resuelto'|'revision'|'na', cui, via, decision, candidatos[], obra}
    candidatos = [{cui, nombre_obra, departamento, score}] para la cola humana.

    `base` (opcional) es la costura para la base local del MEF; las fases F3+ la
    cablearán — por ahora se arrastra por la cadena sin usarse.

    Trazado: cada resolución deja su historia en la traza del job (span
    `resolver_cui` + evento `decision` con el porqué) — ver observabilidad/."""
    tr = _traza()
    with tr.span("resolver_cui", proyecto=str(exp.get("proyecto") or "")):
        r = _resolver(exp, consulta, base)
        tr.ev("decision", estado=r.get("estado"), via=r.get("via"),
              cui=r.get("cui"), motivo=str(r.get("decision")),
              n_candidatos=len(r.get("candidatos") or []))
        return r


def _resolver(exp: dict, consulta: Consulta, base=None) -> dict:
    """Secuencia legible de los pasos de resolución. Cada helper devuelve el
    resultado final o `None`/una tupla para que este orquestador continúe.
    `base` es la costura del MEF (F3+): se arrastra por la cadena, aún sin usar."""
    # PASO 0 · CUI/SNIP citado
    r = _paso_codigo_citado(exp, consulta, base)
    if r is not None:
        return r

    # PÚBLICO-PRIMERO: ya NO hay gate de PRIVADAS aquí. Antes se cortaba por léxico
    # (_gate_privada) ANTES de buscar; ahora se agota SIEMPRE toda la resolución
    # pública y la clasificación de privada ocurre al FINAL (_clasificar_privada),
    # solo cuando no hubo candidato público fiable. Una experiencia privada busca en
    # InfoObras primero (decisión del cliente); el veto de rubro, el gate de tokens y
    # el candado de entidad la protegen de resolverse mal (caso Catholic High School).
    #
    # Sin gate de alcance por RUBRO: se resuelve TODO rubro y TODO tipo (obras y
    # consultorías/expedientes, que SÍ están en InfoObras — muchos con valorizaciones,
    # confirmado 2026-07-02). Un CUI citado ya se intentó arriba (PASO 0); acá se
    # intenta por nombre. Si no hay match fiable o la obra no tiene valorizaciones,
    # cae a revisión por su estado REAL, no por un bloqueo previo.

    # PASO 2 · por nombre + RUC + ubicación
    vistos, fallo_red = _recolectar_candidatos(exp, consulta, base)
    # si NINGÚN fragmento trajo nada y hubo caída de red, no degradar: es
    # "el portal no respondió", no "sin candidato" (motivo de revisión honesto).
    if not vistos and fallo_red:
        return {"estado": "revision", "cui": None, "via": "PORTAL",
                "decision": "el portal de InfoObras no respondió — reintentar",
                "candidatos": [], "obra": None}

    ranked, vetados = _rankear(vistos, exp, base)
    # El ranking queda 100% por IDENTIDAD (score + orden determinístico). El solape
    # de valorizaciones se ELIMINÓ de la selección: usaba el periodo DECLARADO por el
    # certificado —el dato bajo auditoría— para reordenar candidatos, así un periodo
    # mentiroso podía hacer ganar a un homónimo que "le cuadre" (circularidad). El
    # caso del homónimo viejo cae ahora a revisión por cobertura <50% aguas abajo
    # (clamp de valorizaciones, intacto): ruido seguro, nunca un falso CUMPLE.
    best = ranked[0] if ranked else None
    return _compuertas(best, ranked, vetados, exp, base)


def _paso_codigo_citado(exp: dict, consulta: Consulta, base=None) -> Optional[dict]:
    """PASO 0 · CUI/SNIP citado → SIEMPRE primero. Un CUI en el certificado es
    autoritativo: se intenta sin importar el tipo de obra (el filtro de tipo solo
    acota la búsqueda POR NOMBRE, más abajo). Si el CUI no resuelve, cae al filtro.
    Devuelve el dict resultado, o `None` para continuar con el siguiente paso."""
    proyecto = exp.get("proyecto") or ""
    cui_campo = re.sub(r"\D", "", str(exp.get("cui") or ""))
    mcod = RE_CODIGO.search(proyecto)
    codigo = cui_campo if 4 <= len(cui_campo) <= 8 else (mcod.group(1) if mcod else None)
    if not codigo:
        return None
    try:
        obras = consulta.por_codigo(codigo)
    except PortalNoResponde:
        return {"estado": "revision", "cui": None, "via": "PORTAL",
                "decision": "el portal de InfoObras no respondió — reintentar",
                "candidatos": [], "obra": None}
    _traza().ev("paso0_codigo_citado", codigo=codigo, hits=len(obras))
    if not obras:
        # el CUI citado no está en InfoObras, pero la base MEF puede tener su ficha:
        # NO se resuelve por ello (InfoObras es la fuente del cruce), pero el nombre
        # oficial del MEF se guarda como PISTA para el motivo de revisión y como
        # ficha para el scoring por nombre (más abajo). Solo con base disponible.
        if base and base.disponible():
            ficha = base.existe_cui(codigo)
            if ficha:
                _traza().ev("cui_citado_solo_en_mef", cui=codigo,
                            nombre=ficha.get("nombre"))
                exp["_ficha_mef_citado"] = ficha
                exp.setdefault("_fichas_mef", {}).setdefault(codigo, ficha)
        return None
    # un CUI puede traer varias obras: preferir la finalizada que cubre
    # el periodo del certificado (de ahí salen los hitos correctos)
    ci, cf = _fecha_cert(exp.get("fecha_inicial")), _fecha_cert(exp.get("fecha_final"))
    o = _elegir_obra(obras, ci, cf)
    cui_out = _cui_de(o) or codigo  # preferir CUI único de 7 díg
    full = norm(o.get("nombrObra") or "")
    toks = _tokens_clave(establecimiento(proyecto))
    n_hit = len(toks & _palabras(full))
    depmatch = norm(o.get("nombrDepartamento") or "") in ubicacion(proyecto)
    obra = {"cui": cui_out, "nombre_obra": o.get("nombrObra"),
            "departamento": o.get("nombrDepartamento"),
            "obra_id": o.get("codigoObra") or o.get("obraId")}
    # ¿el CUI citado coincide EXACTO con el de la obra hallada? El CUI
    # (codUniqInv 7 díg / codSnip) es código único nacional → autoritativo:
    # si calza exacto, ES la obra, aunque el nombre difiera (el certificado
    # suele citar un componente, p.ej. "C.S. Fortaleza", dentro de la red
    # integrada). Solo el chequeo por nombre podía rechazar un CUI correcto.
    cui_exacto = bool(codigo) and codigo in {
        re.sub(r"\D", "", str(o.get("codUniqInv") or "")),
        re.sub(r"\D", "", str(o.get("codSnip") or "")),
    }
    # el rubro contradictorio VETA la aceptación por nombre/depto (un CUI
    # citado exacto sigue siendo autoritativo aunque el rubro difiera:
    # el certificado suele citar un componente del proyecto integral)
    nombre_ok = ((toks and n_hit >= max(1, (len(toks) + 1) // 2)) or depmatch) \
        and not _rubro_contradice(rubros_de(proyecto), o.get("nombrObra") or "")
    # F8 · DECISIÓN sobre el CUI citado (caso 2:27, COAR Cusco → CUI Pasco): NO se
    # degrada por contradicción de ubicación. Un CUI escrito en el certificado y
    # hallado EXACTO en InfoObras es un código único nacional → autoritativo, aunque
    # su ubicación oficial (MEF) difiera de la del certificado: las concesiones
    # multi-región (COAR) y las inversiones registradas bajo la sede de la entidad
    # ejecutora hacen que provincia/departamento legítimamente NO coincidan con la
    # obra física. El golden auditado confirma este CUI como CORRECTO (verdad=2429909
    # vía PROBABLE). El veto de ubicación (F8) actúa SOLO sobre resoluciones POR
    # NOMBRE, donde la evidencia es inferida, nunca sobre un CUI citado exacto.
    if cui_exacto or nombre_ok:
        via = "CUI_TEXTO" if nombre_ok else "PROBABLE"
        decision = ("código CUI verificado contra la obra" if nombre_ok else
                    "CUI exacto hallado en InfoObras; el nombre de la obra difiere — verificar")
        return {"estado": "resuelto", "cui": cui_out, "via": via,
                "decision": decision, "candidatos": [], "obra": obra}
    return {"estado": "revision", "cui": None, "via": "CUI_TEXTO",
            "decision": "el código CUI del certificado no coincide con la obra — confirmar",
            "candidatos": [{"cui": cui_out, "nombre_obra": (o.get("nombrObra") or ""),
                            "departamento": o.get("nombrDepartamento"), "score": 50}],
            "obra": None}


def _con_pista_mef(exp: dict, motivo: str) -> str:
    """Anexa al motivo de revisión el nombre oficial del MEF del CUI citado, si el
    certificado citó un CUI que InfoObras no tenía pero el MEF sí (F3 · A1). Ayuda
    al humano a confirmar en la cola de revisión."""
    fmc = exp.get("_ficha_mef_citado")
    if fmc and fmc.get("nombre"):
        motivo += f" (según el MEF, el CUI citado corresponde a: {fmc['nombre']})"
    return motivo


def _clasificar_privada(exp: dict, candidatos: list, vetados: list, base=None) -> dict:
    """PÚBLICO-PRIMERO · clasificación de PRIVADA al FINAL. Se invoca SOLO cuando la
    resolución pública ya se agotó sin candidato fiable (no en loc_contra ni en
    vetados-por-rubro, que conservan su propio motivo). Decide entre:

      a. léxico `_RE_PRIVADA` (cliente/promotor privado explícito) → 'na' vía PRIVADA
         (mismo retorno que el antiguo gate; el marcador lo consume el Excel/ZIP).
      b. base MEF disponible + entidad_contratante NO vacía que NO se reconoce como
         pública → revisión con `posible_privada=True` (posible obra privada sin
         señal léxica: S.A.C., ONG, "ORDEN DE SAN AGUSTIN"…).
      c. resto → revisión normal ("sin candidato fiable en InfoObras").
    """
    # a. señal léxica de cliente/obra privada (colegios particulares, I.E.P. + nombre…)
    if _es_experiencia_privada(exp):
        _traza().ev("gate_privada")
        return {"estado": "na", "cui": None, "via": "PRIVADA",
                "decision": "cliente/obra privada — InfoObras solo registra obra "
                            "pública; verificación documental del certificado",
                "candidatos": [], "obra": None}
    # b. sin señal léxica, pero la entidad contratante no se reconoce como pública
    entidad = str(exp.get("entidad_contratante") or "").strip()
    if base and base.disponible() and entidad and not base.es_entidad_publica(entidad)[0]:
        _, score = base.es_entidad_publica(entidad)
        _traza().ev("posible_privada", entidad=entidad, score=score)
        motivo = _con_pista_mef(exp,
                                "sin candidato público fiable; la entidad contratante "
                                "no se reconoce como pública — posible obra privada")
        return {"estado": "revision", "cui": None, "via": "NOMBRE",
                "decision": motivo, "candidatos": candidatos, "obra": None,
                "posible_privada": True}
    # c. revisión normal
    return {"estado": "revision", "cui": None, "via": "NOMBRE",
            "decision": _con_pista_mef(exp, "sin candidato fiable en InfoObras"),
            "candidatos": candidatos, "obra": None}


def _recolectar_candidatos(exp: dict, consulta: Consulta, base=None) -> tuple[dict, bool]:
    """Recolecta TODOS los registros distintos por fragmentos de nombre (sin
    descartar por CUI todavía: un CUI puede tener varias obras y la 1ª devuelta no
    es la mejor). Devuelve (vistos, fallo_red).

    Con `base` disponible (F3) fusiona además los candidatos de la base local del
    MEF: rescata CUIs que InfoObras NO trajo por nombre (nombres corruptos, cola
    geográfica que despistó al buscador). Cada registro queda marcado con `_origen`
    ('infoobras' / 'mef' / 'ambos')."""
    proyecto = exp.get("proyecto") or ""
    vistos: dict = {}
    fallo_red = False
    for f in fragmentos(proyecto):
        try:
            resultados = consulta.buscar(f)
        except PortalNoResponde:
            fallo_red = True  # un fragmento cayó; quizá otros respondan
            _traza().ev("busqueda", fragmento=f, resultado="portal_no_responde")
            continue
        _traza().ev("busqueda", fragmento=f, hits=len(resultados))
        for o in resultados:
            if _cui_de(o):
                vistos.setdefault(o.get("codigoObra") or o.get("obraId"), o)
    if base and base.disponible():
        _fusionar_mef(exp, consulta, base, vistos)
    return vistos, fallo_red


def _codigos_de(o: dict) -> set[str]:
    """CUI y SNIP normalizados (solo dígitos, sin ceros) de un registro InfoObras."""
    out: set[str] = set()
    for campo in ("codUniqInv", "codSnip"):
        v = re.sub(r"\D", "", str(o.get(campo) or ""))
        if v and int(v) != 0:
            out.add(v)
    return out


def _fusionar_mef(exp: dict, consulta: Consulta, base, vistos: dict) -> None:
    """F3 · Fusión con la base local del MEF. Solo se invoca con `base` disponible.
    Marca el origen de cada registro y trae por código (`por_codigo`) los CUIs que
    el MEF sugiere y que InfoObras no encontró por nombre — tope de 5 fetches por
    experiencia, PRIORIZANDO las inversiones vivas sobre las desactivadas y
    capturando `PortalNoResponde` POR candidato (se descarta ese, la experiencia
    sigue). Guarda las fichas MEF por CUI en `exp['_fichas_mef']` para el paso de
    scoring (señal de nombre/dpto/entidad)."""
    proyecto = exp.get("proyecto") or ""
    fichas_mef = exp.setdefault("_fichas_mef", {})
    # todo lo ya recolectado vino de InfoObras (por nombre)
    for o in vistos.values():
        o.setdefault("_origen", "infoobras")
    ya = set().union(*(_codigos_de(o) for o in vistos.values())) if vistos else set()

    utiles: list[tuple[str, dict]] = []
    for c in base.buscar_candidatos(_sin_prefijo(proyecto), topn=10):
        cui = re.sub(r"\D", "", str(c.get("cui") or "")) \
            or re.sub(r"\D", "", str(c.get("snip") or ""))
        if not cui or int(cui) == 0 or float(c.get("score") or 0) < 75:
            continue
        fichas_mef.setdefault(cui, c)  # ficha MEF por CUI → scoring (aunque no se fetchee)
        if cui in ya:
            # el CUI ya estaba en InfoObras (por nombre): pasa a origen 'ambos'. Se
            # marca ACÁ, fuera del presupuesto de fetches: que el MEF corrobore un
            # CUI es un hecho, no depende de cuántas consultas quepan.
            for o in vistos.values():
                if cui in _codigos_de(o):
                    o["_origen"] = "ambos"
            continue
        utiles.append((cui, c))
    # ORDEN DEL PRESUPUESTO DE FETCHES: los proyectos DESACTIVADOS del MEF van al
    # FINAL de la cola. El tope de 5 consultas al portal es escaso y hoy se gasta en
    # inversiones que nunca se ejecutaron (medido sobre los 277 casos auditados:
    # 420 de 1303 fetches potenciales, 32%, apuntan a desactivadas). `sort` es
    # ESTABLE → dentro de cada grupo se conserva el orden por score.
    # NO se descartan: un CUI reformulado queda desactivado y el certificado puede
    # citar al viejo (15 de 191 verdades auditadas viven en filas DESACTIVADA), así
    # que si el presupuesto alcanza igual se consultan — solo pierden la prioridad.
    utiles.sort(key=lambda par: _mef_desactivada(par[1]))

    fetches = 0
    for cui, c in utiles:
        if fetches >= 5:
            break  # tope de fetches al portal por experiencia
        fetches += 1
        try:
            registros = consulta.por_codigo(cui)
        except PortalNoResponde:
            _traza().ev("fusion_mef_portal", cui=cui)
            continue  # se descarta ESTE candidato; la experiencia sigue
        if not registros:
            _traza().ev("fusion_mef_sin_obra", cui=cui, nombre=c.get("nombre"))
            continue
        nuevos = 0
        for o in registros:
            if not _cui_de(o):
                continue
            key = o.get("codigoObra") or o.get("obraId")
            if key in vistos:
                vistos[key]["_origen"] = "ambos"
            else:
                o["_origen"] = "mef"
                vistos[key] = o
                nuevos += 1
        _traza().ev("fusion_mef_candidato", cui=cui, score=c.get("score"),
                    nombre=c.get("nombre"), nuevos=nuevos)


def _rankear(vistos: dict, exp: dict, base=None) -> tuple[list, list]:
    """Puntúa cada registro, aplica el VETO de rubro, agrupa por CUI (representante
    de mayor score) y ordena determinísticamente. Devuelve (ranked, vetados).

    VETO DE RUBRO: un candidato cuyo rubro contradice al del certificado (salud vs
    deportivo, etc.) NO compite — se aparta a `vetados` para que la cola de revisión
    pueda mostrarlo, pero jamás gana en silencio."""
    proyecto = exp.get("proyecto") or ""
    pn = norm(proyecto)
    deptos_hint = ubicacion(proyecto)
    fi = str(exp.get("fecha_inicial") or "")
    anio_cert = int(fi[:4]) if fi[:4].isdigit() else None
    mruc = RE_RUC.search(str(exp.get("ruc_emisor") or "") + " " + str(exp.get("entidad_emisora") or ""))
    ruc_cert = mruc.group(1) if mruc else None
    nums_cert = frozenset(_numero_obra(proyecto))   # N° de I.E./C.E. del certificado
    rub_cert = rubros_de(proyecto)
    base_ok = bool(base) and base.disponible()
    fichas_mef = exp.get("_fichas_mef") if base_ok else None
    sig_geo = ubigeo_cert(exp) if base_ok else None   # señales prov/dist del cert (F8)
    porcui: dict[str, dict] = {}
    origenes: dict[str, set] = {}          # orígenes vistos por CUI (para 'ambos')
    vetados: list[dict] = []
    for o in vistos.values():
        cui = _cui_de(o)
        rej = str(o.get("rucEjecutor") or "").strip()
        rsup = str(o.get("rucSupervisor") or "").strip()
        ruc_match = bool(ruc_cert and ruc_cert in (rej, rsup))
        sc = _puntuar(o, pn, deptos_hint, anio_cert, nums_cert) + (30 if ruc_match else 0)
        full = norm(o.get("nombrObra") or "")
        # señales DURAS de identidad (para la corroboración del candado mef, abajo):
        # el N° de institución del cert que también está en la obra, y la entidad
        # contratante que calza con la ficha MEF. El RUC (ruc_match) ya se calculó.
        nums_cand = _numero_obra(o.get("nombrObra") or "")
        num_match = bool(nums_cert and nums_cand and (nums_cert & nums_cand))
        ent_match = False
        ficha = None
        veto_geo = False
        if base_ok:
            # el score de nombre y la compuerta de tokens se apoyan también en el
            # nombre OFICIAL del MEF (rescata nombres corruptos en InfoObras)
            sc += _bonus_mef(o, cui, exp, base, fichas_mef, pn, deptos_hint)
            ficha = _ficha_mef(cui, base, fichas_mef)
            if ficha and ficha.get("nombre"):
                full = (full + " " + norm(ficha["nombre"])).strip()
            ent_cert = norm(exp.get("entidad_contratante") or "")
            ent_mef = norm((ficha or {}).get("entidad") or "")
            if ent_cert and ent_mef and fuzz.token_set_ratio(ent_cert, ent_mef) >= 90:
                ent_match = True
            # F8 · ubicación: contradicción de PROVINCIA (ambas declaradas) → veto;
            # solo de DISTRITO (misma provincia) → penaliza, no veta (obras
            # intermunicipales; y el MEF a veces registra la sede de la entidad).
            prov_c, dist_c, _dep_c = _ubigeo_contra(sig_geo, ficha)
            if prov_c and not ruc_match:
                veto_geo = True
            elif dist_c:
                sc -= 25
            # contratante municipal ≠ entidad municipal del CUI (mismo tipo):
            # dos municipalidades distintas no contratan la misma obra
            if not veto_geo and not ruc_match and _muni_contradice(exp, ficha):
                veto_geo = True
        cand = {"cui": cui, "nombre_obra": (o.get("nombrObra") or ""),
                "full": full,
                "departamento": o.get("nombrDepartamento"),
                "obra_id": o.get("codigoObra") or o.get("obraId"),
                "ruc_match": ruc_match, "num_match": num_match,
                "ent_match": ent_match, "score": round(sc, 1),
                # estado del MEF: "" = el CUI NO está en la base local (desconocido,
                # que no es lo mismo que vivo — ver `_estado_separa`).
                "mef_estado": ((ficha or {}).get("estado_dataset") or ""),
                "mef_desactivada": _mef_desactivada(ficha)}
        if o.get("_origen"):
            cand["origen"] = o["_origen"]
            origenes.setdefault(cui, set()).add(o["_origen"])
        # el RUC del emisor en la obra es evidencia más fuerte que el rubro
        # inferido del texto → el veto no aplica a ruc_match
        if not ruc_match and _rubro_contradice(rub_cert, cand["nombre_obra"]):
            cand["veto"] = "rubro"
            _traza().ev("veto_rubro", cui=cui, score=cand["score"],
                        rubro_cert=sorted(rub_cert),
                        rubro_obra=sorted(rubros_de(cand["nombre_obra"])),
                        obra=cand["nombre_obra"])
            vetados.append(cand)
            continue
        if veto_geo:
            cand["veto"] = "ubigeo"
            _traza().ev("veto_ubigeo", cui=cui, score=cand["score"],
                        prov_cert=sorted(sig_geo["prov"]),
                        prov_mef=(ficha or {}).get("prov"),
                        obra=cand["nombre_obra"])
            vetados.append(cand)
            continue
        prev = porcui.get(cui)
        # representante de cada CUI = el de mayor score; ante EMPATE, menor
        # obra_id (el orden que devuelve la API no es estable entre corridas).
        if (prev is None
                or cand["score"] > prev["score"]
                or (cand["score"] == prev["score"]
                    and _num(cand["obra_id"]) < _num(prev["obra_id"]))):
            porcui[cui] = cand

    # un CUI presente en InfoObras Y en el MEF se marca 'ambos' aunque su
    # representante (mayor score) venga de un solo lado.
    for cui, cand in porcui.items():
        origs = origenes.get(cui)
        if origs:
            cand["origen"] = "ambos" if len(origs) > 1 else next(iter(origs))

    # orden DETERMINÍSTICO: score desc; ante EMPATE de score gana la inversión VIVA
    # sobre la DESACTIVADA en el MEF y, recién después, menor CUI y menor obra_id.
    # Sin la clave secundaria, dos CUIs con el mismo score quedaban en el orden de
    # inserción de `porcui` (no reproducible) → `best` variaba entre corridas.
    # El estado entra DESPUÉS del score (nunca lo pisa): un desactivado que puntúa
    # más alto sigue arriba — solo se rompen los empates.
    ranked = sorted(porcui.values(),
                    key=lambda x: (-x["score"], x.get("mef_desactivada", False),
                                   _num(x["cui"]), _num(x["obra_id"])))
    return ranked, vetados


def _compuertas(best, ranked: list, vetados: list, exp: dict, base=None) -> dict:
    """Bloque final de decisión: compuerta de tokens, RUC, NOMBRE, PROBABLE,
    loc_contra y motivos de revisión. Emite el evento `ranking` y devuelve el
    dict resultado."""
    proyecto = exp.get("proyecto") or ""
    deptos_hint = ubicacion(proyecto)
    toks = _tokens_clave(establecimiento(proyecto))

    _traza().ev("ranking", top=[f"{c['cui']}·{c['score']}" for c in ranked[:3]],
                vetados=len(vetados))

    # ── CANDADO MEF (F7) ─────────────────────────────────────────────────────
    # Un candidato de origen 'mef' (solo la FUSIÓN lo trajo; InfoObras NO lo
    # devolvió por nombre) NO es elegible como `best` para RESOLVER salvo una señal
    # DURA que lo confirme: RUC del emisor en la obra, N° de institución del cert
    # presente en la obra, o entidad contratante ≈ ficha MEF (token_set_ratio ≥ 90).
    #
    # Diagnóstico F7: la fusión mete homónimos estatales con nombre oficial limpio;
    # `_bonus_mef` les subía el score Y les prestaba tokens al `full`, así el
    # homónimo (mismo departamento, otra obra) pasaba la compuerta y ganaba por puro
    # nombre → +15 mal-resueltos silenciosos, casi todos via=NOMBRE sobre prefijos
    # genéricos ("MEJORAMIENTO DE LA CAPACIDAD RESOLUTIVA…", "…EDUCACIÓN… I.E. N°…").
    # El departamento NO corrobora: los homónimos estatales viven en el MISMO dpto
    # que la obra real, así que un match de dpto no los distingue (medido en el golden).
    #
    # Se DEMOTA, no se descarta: el candidato mef sigue visible en `candidatos` para
    # la cola humana; el mejor candidato ELEGIBLE de más abajo ocupa el lugar de best.
    # Esto además DESBLOQUEA correctos que un mef sin compuerta tapaba en el #1
    # (p. ej. Pichanaki, San Ignacio: el mef gate=0 quedaba #1 por 0.3 pts y hundía
    # al InfoObras correcto a revisión).
    def _mef_sin_corroborar(c: dict) -> bool:
        return (c.get("origen") == "mef"
                and not (c.get("ruc_match") or c.get("num_match") or c.get("ent_match")))

    best = next((c for c in ranked if not _mef_sin_corroborar(c)), None)
    if ranked and (best is None or ranked[0] is not best):
        _traza().ev("candado_mef_demote", best=(best or {}).get("cui"),
                    demotados=[f"{c['cui']}·{c['score']}" for c in ranked
                               if _mef_sin_corroborar(c)][:3])

    n_hit = len(toks & _palabras(best["full"])) if best else 0
    gate = bool(best and toks and n_hit >= max(1, (len(toks) + 1) // 2))
    loc_contra = bool(deptos_hint and best and best.get("departamento")
                      and norm(best["departamento"]) not in deptos_hint
                      and not best.get("ruc_match"))

    def _proj(c: dict) -> dict:
        # `origen` (F3) viaja ADITIVO: solo si el candidato lo trae (con base=None
        # nunca está → proyección idéntica a la histórica).
        d = {k: c[k] for k in ("cui", "nombre_obra", "departamento", "score")}
        if "origen" in c:
            d["origen"] = c["origen"]
        return d

    candidatos = [_proj(c) for c in ranked[:3]]
    obra_best = best and {"cui": best["cui"], "nombre_obra": best["nombre_obra"],
                          "departamento": best["departamento"], "obra_id": best.get("obra_id")}

    if best and best.get("ruc_match"):
        return {"estado": "resuelto", "cui": best["cui"], "via": "RUC",
                "decision": "el RUC del emisor es ejecutor/supervisor de la obra",
                "candidatos": candidatos, "obra": obra_best}

    # ── GUARD DE EMPATE ENTRE CUIs DISTINTOS (F7) ────────────────────────────
    # Si el mejor candidato ELEGIBLE y otro CUI distinto quedan a ≤ DELTA puntos y
    # NINGUNA señal DURA los separa (RUC / N° de institución / entidad ≈ ficha MEF
    # en exactamente uno), NO se resuelve: son proyectos homónimos con nombre casi
    # idéntico (mismo prefijo genérico "MEJORAMIENTO DE LA CAPACIDAD RESOLUTIVA…" o
    # "…EDUCACIÓN… I.E. N°…") y el orden entre ellos es ruido de similitud, no
    # identidad. Se manda a revisión con los candidatos visibles para que el humano
    # elija. El departamento NO cuenta como señal separadora (los homónimos viven en
    # el mismo dpto). DELTA=4 calibrado contra el golden: corta 6 mal-resueltos y
    # solo roza 3 correctos contestados (best==verdad a <4 pts de un gemelo), coste
    # honesto — un falso "a revisión" cuesta minutos; un falso CUMPLE, el producto.
    #
    # El ESTADO del MEF sí es señal separadora: si el mejor está VIVO y el rival
    # está DESACTIVADO, no son "dos gemelos indistinguibles" — uno de los dos nunca
    # se ejecutó. Ese rival no dispara el guard (medido sobre los 277 casos
    # auditados: cero verdades desactivadas tienen un rival vivo a ≤4 pts, así que
    # esta puerta no sacrifica ningún correcto). Al revés NO aplica: si el mejor es
    # el desactivado, la duda sigue viva y se manda a revisión como siempre.
    _DELTA_EMPATE = 4.0
    if best and not _es_experiencia_privada(exp):
        def _senal_dura(c: dict) -> bool:
            return bool(c.get("ruc_match") or c.get("num_match") or c.get("ent_match"))

        def _estado_separa(a: dict, b: dict) -> bool:
            """`a` está VIVO en el MEF y `b` DESACTIVADO. Exige el dato en AMBOS: un
            CUI ausente de la base local es DESCONOCIDO, no vivo — resolver contra
            un rival muerto apoyándose en la ausencia de información sería adivinar."""
            return (b.get("mef_estado") == "DESACTIVADA"
                    and a.get("mef_estado") in ("ACTIVO", "CERRADA"))

        elegibles = [c for c in ranked if not _mef_sin_corroborar(c)]
        rivales = [c for c in elegibles
                   if c["cui"] != best["cui"] and not _estado_separa(best, c)]
        descartados_estado = [c for c in elegibles if c["cui"] != best["cui"]
                              and _estado_separa(best, c)
                              and (best["score"] - c["score"]) <= _DELTA_EMPATE]
        if descartados_estado:
            _traza().ev("empate_roto_por_estado", best=best["cui"],
                        desactivados=[f"{c['cui']}·{c['score']}"
                                      for c in descartados_estado][:3])
        otro = next(iter(rivales), None)
        if (otro is not None
                and (best["score"] - otro["score"]) <= _DELTA_EMPATE
                and _senal_dura(best) == _senal_dura(otro)):
            _traza().ev("guard_empate", best=best["cui"], otro=otro["cui"],
                        gap=round(best["score"] - otro["score"], 1))
            return {"estado": "revision", "cui": None, "via": "NOMBRE",
                    "decision": _con_pista_mef(exp,
                        "varios proyectos homónimos sin señal que los distinga "
                        "(nombres casi idénticos) — elegir el candidato correcto"),
                    "candidatos": candidatos, "obra": None}
        # Un gemelo VETADO POR UBICACIÓN a punto similar también es ambigüedad: el
        # veto pudo apartar al correcto (el MEF a veces registra la sede de la
        # entidad, no la obra física — golden F8: 2131082, 2186244) y dejar ganar
        # al homónimo equivocado. Peor que abstenerse → revisión con ambos visibles.
        rival_geo = next((c for c in vetados
                          if c.get("veto") == "ubigeo" and c["cui"] != best["cui"]
                          and not _estado_separa(best, c)
                          and (best["score"] - c["score"]) <= _DELTA_EMPATE), None)
        if rival_geo is not None and not _senal_dura(best):
            _traza().ev("guard_empate_geo", best=best["cui"], vetado=rival_geo["cui"],
                        gap=round(best["score"] - rival_geo["score"], 1))
            return {"estado": "revision", "cui": None, "via": "NOMBRE",
                    "decision": _con_pista_mef(exp,
                        "un proyecto homónimo quedó apartado por estar en otra "
                        "provincia y ninguna señal separa a los candidatos — "
                        "confirmar cuál corresponde"),
                    "candidatos": candidatos + [_proj(rival_geo)], "obra": None}

    if best and gate and best["score"] >= 70:
        return {"estado": "resuelto", "cui": best["cui"], "via": "NOMBRE",
                "decision": "establecimiento verificado por nombre",
                "candidatos": candidatos, "obra": obra_best}
    # PROBABLE exige al menos UN token distintivo compartido (n_hit≥1): un score
    # alto de similitud entre dos nombres puramente genéricos ("mejoramiento del
    # servicio educativo…" de dos lugares distintos) NO identifica la obra — de ahí
    # salían los matches "que nada tienen que ver" (queja del cliente 14-jul).
    if best and (gate or (best["score"] >= 90 and n_hit >= 1)) and not loc_contra:
        # CANDADO DE ENTIDAD PÚBLICA (público-primero): un candidato fuerte SOLO por
        # similitud de nombre, cuya entidad contratante NO se reconoce como pública,
        # se degrada a revisión — la evidencia de PROBABLE es más débil que RUC/NOMBRE.
        # Las vías RUC y NOMBRE (arriba) no pasan por aquí: su evidencia es más fuerte.
        # Sin base o entidad vacía → comportamiento actual (resuelve PROBABLE).
        entidad = str(exp.get("entidad_contratante") or "").strip()
        if base and base.disponible() and entidad \
                and not base.es_entidad_publica(entidad)[0]:
            _traza().ev("candado_entidad_probable", cui=best["cui"], entidad=entidad)
            return {"estado": "revision", "cui": None, "via": "NOMBRE",
                    "decision": "candidato fuerte pero la entidad contratante no se "
                                "reconoce como pública — confirmar",
                    "candidatos": candidatos, "obra": None}
        return {"estado": "resuelto", "cui": best["cui"], "via": "PROBABLE",
                "decision": "candidato fuerte (conviene un vistazo)",
                "candidatos": candidatos, "obra": obra_best}
    if loc_contra:
        motivo = _con_pista_mef(exp, "la ubicación del certificado contradice al candidato")
        return {"estado": "revision", "cui": None, "via": "NOMBRE",
                "decision": motivo, "candidatos": candidatos, "obra": None}
    if not ranked and vetados:
        # todos los candidatos fueron vetados: por RUBRO (deportivo vs salud, caso
        # Chinchinga) o por UBICACIÓN (provincia contradictoria, F8) — revisión con
        # los vetados visibles; antes esto era un mal-resuelto SILENCIOSO.
        # Una experiencia PRIVADA con todos sus candidatos vetados sigue siendo
        # privada (Trinity College): clasificarla, no mandarla a revisión de CUI.
        if _es_experiencia_privada(exp):
            return _clasificar_privada(exp, [_proj(c) for c in vetados[:3]],
                                       vetados, base)
        if all(c.get("veto") == "rubro" for c in vetados):
            motivo = "los candidatos hallados son de otro rubro de servicio — confirmar"
        elif all(c.get("veto") == "ubigeo" for c in vetados):
            motivo = ("los candidatos hallados están en otra provincia que la del "
                      "certificado — confirmar")
        else:
            motivo = ("los candidatos hallados contradicen el rubro o la ubicación "
                      "del certificado — confirmar")
        motivo = _con_pista_mef(exp, motivo)
        vetados.sort(key=lambda c: -c["score"])
        return {"estado": "revision", "cui": None, "via": "NOMBRE",
                "decision": motivo, "candidatos": [_proj(c) for c in vetados[:3]],
                "obra": None}
    if best is None and ranked and not _es_experiencia_privada(exp):
        # todos los candidatos de arriba son de origen 'mef' sin corroborar (candado
        # F7): no se resuelve, pero quedan visibles para que el humano elija.
        motivo = _con_pista_mef(exp, "el/los candidato(s) hallados provienen solo de "
                                "la base MEF y ninguna señal (RUC, N° de institución o "
                                "entidad) los confirma en InfoObras — elegir en revisión")
        return {"estado": "revision", "cui": None, "via": "NOMBRE",
                "decision": motivo, "candidatos": candidatos, "obra": None}
    # Sin candidato público fiable: recién AQUÍ, agotada la resolución pública, se
    # clasifica la PRIVADA (léxico → 'na'; entidad no-pública → posible_privada).
    return _clasificar_privada(exp, candidatos, vetados, base)


def resolver_obras(obras: list[dict], consulta: Consulta, base=None) -> list[dict]:
    """Resuelve cada sub-obra de un cert MULTI-OBRA por su CUI citado (por_codigo,
    DETERMINÍSTICO — sin adivinar por nombre). Un cert de rol de gestión/portafolio
    lista N obras bajo un mismo vínculo; el tiempo se cuenta una vez (en la
    experiencia), esto solo VERIFICA que cada obra exista en InfoObras.

    Devuelve [{proyecto, cui, estado, obra}] con estado:
      'resuelto'      → el código existe en InfoObras (`obra` = datos)
      'no_encontrado' → el código no está en InfoObras (p. ej. un estudio/plan, no obra)
      'sin_cui'       → el sub-proyecto no cita CUI en el cert
      'portal'        → InfoObras no respondió (reintentar)
    Cachea por CUI (el mismo código puede repetirse entre sub-proyectos)."""
    out: list[dict] = []
    cache: dict[str, dict] = {}
    for o in obras or []:
        o = o or {}
        # se ARRASTRAN proyecto + fechas POR obra (si el cert las dio): la etapa
        # InfoObras las usa para el cruce de cobertura por sub-obra.
        extra = {"proyecto": o.get("proyecto"),
                 "fecha_inicial": o.get("fecha_inicial"),
                 "fecha_final": o.get("fecha_final")}
        cui = re.sub(r"\D", "", str(o.get("cui") or ""))
        if not 4 <= len(cui) <= 8:
            out.append({"cui": None, "estado": "sin_cui", "obra": None, **extra})
            continue
        if cui in cache:
            out.append({**cache[cui], **extra})
            continue
        try:
            registros = consulta.por_codigo(cui)
        except PortalNoResponde:
            out.append({"cui": cui, "estado": "portal", "obra": None, **extra})
            continue
        if registros:
            ob = _elegir_obra(registros)
            cui_out = _cui_de(ob) or cui
            res = {"cui": cui_out, "estado": "resuelto",
                   "obra": {"cui": cui_out, "nombre_obra": ob.get("nombrObra"),
                            "departamento": ob.get("nombrDepartamento"),
                            "obra_id": ob.get("codigoObra") or ob.get("obraId")}}
        else:
            res = {"cui": cui, "estado": "no_encontrado", "obra": None}
        cache[cui] = res
        out.append({**res, **extra})
    return out


def _folio_base(folio) -> Optional[str]:
    m = re.search(r"\d{2,}", str(folio or ""))
    return m.group(0) if m else None


def resolver_con_dedup(experiencias: list[tuple[dict, object]], consulta: Consulta,
                       base=None):
    """Itera [(exp, clave), …] resolviendo con herencia por folio (el '2º periodo
    del mismo certificado' hereda el CUI del hermano). Yields (clave, resultado).
    `base` (opcional) se arrastra a `resolver` — costura del MEF para F3+."""
    por_folio: dict[str, dict] = {}
    for exp, clave in experiencias:
        r = resolver(exp, consulta, base)
        fb = _folio_base(exp.get("folio"))
        if r["estado"] == "revision" and fb and fb in por_folio:
            heredado = por_folio[fb]
            r = {"estado": "resuelto", "cui": heredado["cui"], "via": "DEDUP",
                 "decision": "mismo certificado que otra experiencia ya identificada",
                 "candidatos": [], "obra": heredado.get("obra")}
        if r["estado"] == "resuelto" and fb:
            por_folio.setdefault(fb, r)
        yield clave, r
