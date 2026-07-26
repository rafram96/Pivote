"""
Scraper de SUNAT (e-consultaruc.sunat.gob.pe) — consulta directa sin browser.

Resuelve la verificación automática de fecha de inscripción de empresas emisoras,
necesaria para ALT04 (empresa emisora constituida después del inicio de la
experiencia declarada).

El "reCAPTCHA" del portal público de SUNAT es un stub que acepta cualquier token
de 52 chars como válido — generamos uno aleatorio en cada llamada.

Sin CAPTCHA real, sin Playwright, sin Selenium. Solo `requests` + `re`.

Basado en el PoC en JS:
  C:/Users/Holbi/Documents/Freelance/variedad/prueba-externos/sunat-playwright/sunat.js

Endpoints:
  [1] GET  /cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp → cookies de sesión
  [2] POST /cl-ti-itmrconsruc/jcrS00Alias  → consulta (RUC | DNI | razón social)

Las consultas secundarias del emisor son acciones del MISMO POST, encadenadas
tras la ficha de detalle: `getRepLeg` (representantes legales) y `getinfHis`
(información histórica).
"""
from __future__ import annotations

import html as html_module
import json
import logging
import os
import random
import re
import secrets
import ssl
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.ssl_ import create_urllib3_context
except ImportError:  # urllib3 muy viejo
    create_urllib3_context = None  # type: ignore

# rapidfuzz es dependencia DURA (requirements.txt): el cruce por razón social
# debe puntuar igual en la laptop y en el servidor.
from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

HOST = "https://e-consultaruc.sunat.gob.pe"
FORM_PATH = "/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp"
SEARCH_PATH = "/cl-ti-itmrconsruc/jcrS00Alias"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ─── TLS adapter custom ──────────────────────────────────────────────────────
# Portales .gob.pe (incluyendo SUNAT) a veces rechazan los ciphers default de
# Python/urllib3. Forzamos un context TLS más permisivo que acepte ciphers
# legacy que estos portales gubernamentales aún sirven.
#
# Si SUNAT cierra conexiones activamente con el adapter default (RemoteDisconnected
# en handshake), este SUNATTlsAdapter resuelve el problema en >90% de los casos.
_LEGACY_CIPHERS = (
    "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:"
    "ECDH+AESGCM:DH+AESGCM:ECDH+AES:DH+AES:"
    "RSA+AESGCM:RSA+AES:!aNULL:!MD5:!DSS:@SECLEVEL=1"
)


class _SUNATTlsAdapter(HTTPAdapter):
    """HTTPAdapter con ciphers legacy + SECLEVEL=1 para portales .gob.pe."""

    def init_poolmanager(self, *args, **kwargs):
        if create_urllib3_context is None:
            return super().init_poolmanager(*args, **kwargs)
        ctx = create_urllib3_context()
        try:
            ctx.set_ciphers(_LEGACY_CIPHERS)
        except ssl.SSLError:
            # Algunos OpenSSL no soportan SECLEVEL=1, intentar sin él
            ctx.set_ciphers(_LEGACY_CIPHERS.replace(":@SECLEVEL=1", ""))
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        if create_urllib3_context is None:
            return super().proxy_manager_for(*args, **kwargs)
        ctx = create_urllib3_context()
        try:
            ctx.set_ciphers(_LEGACY_CIPHERS)
        except ssl.SSLError:
            ctx.set_ciphers(_LEGACY_CIPHERS.replace(":@SECLEVEL=1", ""))
        kwargs["ssl_context"] = ctx
        return super().proxy_manager_for(*args, **kwargs)


def _crear_session_sunat() -> requests.Session:
    """Crea una session con el TLS adapter custom + headers de browser real."""
    session = requests.Session()
    session.mount("https://", _SUNATTlsAdapter())
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return session

# Retry config — SUNAT a veces cierra conexiones en mass o devuelve 5xx.
# Configurable via env.
SUNAT_MAX_RETRIES = int(os.getenv("SUNAT_MAX_RETRIES", "3"))
SUNAT_RETRY_BASE_DELAY = float(os.getenv("SUNAT_RETRY_BASE_DELAY", "0.5"))  # segundos
SUNAT_THROTTLE_DELAY = float(os.getenv("SUNAT_THROTTLE_DELAY", "0.3"))  # entre RUCs


def _request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    description: str,
    **kwargs,
) -> Optional[requests.Response]:
    """
    Ejecuta una request con reintento + backoff exponencial + jitter.
    Devuelve Response si tuvo éxito, None si todos los intentos fallaron.

    Reintenta en:
      - ConnectionError (RemoteDisconnected, etc.)
      - Timeout
      - HTTP 5xx
    """
    last_exc: Optional[Exception] = None
    for intento in range(SUNAT_MAX_RETRIES):
        try:
            r = session.request(method, url, timeout=timeout, **kwargs)
            if r.status_code < 500:
                return r
            last_exc = Exception(f"HTTP {r.status_code}")
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc

        if intento < SUNAT_MAX_RETRIES - 1:
            # Backoff exponencial con jitter: 0.5s → 1s → 2s + 0..0.3s random
            delay = SUNAT_RETRY_BASE_DELAY * (2 ** intento) + random.uniform(0, 0.3)
            logger.debug(
                "SUNAT %s intento %d/%d fallo (%s), reintentando en %.1fs",
                description, intento + 1, SUNAT_MAX_RETRIES, last_exc, delay,
            )
            time.sleep(delay)

    logger.warning("SUNAT %s fallo tras %d intentos: %s",
                   description, SUNAT_MAX_RETRIES, last_exc)
    return None

# Etiquetas del HTML de detalle SUNAT. Cada una tiene un patrón:
#   <h4>Etiqueta:</h4>
#     ...
#   <p class="list-group-item-text">VALOR</p>
# (algunos campos usan <h4 class="list-group-item-heading"> en lugar de <p>)
_FIELDS = [
    "Número de RUC",
    "Tipo Contribuyente",
    "Nombre Comercial",
    "Fecha de Inscripción",
    "Fecha de Inicio de Actividades",
    "Estado del Contribuyente",
    "Condición del Contribuyente",
    "Domicilio Fiscal",
    "Sistema Emisión de Comprobante",
    "Actividad Comercio Exterior",
    "Sistema Contabilidad",
    "Sistema de Emisión Electrónica",
    "Emisor electrónico desde",
    "Comprobantes Electrónicos",
    "Afiliado al PLE desde",
    "Padrones",
]


# ============================================================================
# Modelo de datos
# ============================================================================

@dataclass
class EmpresaSUNAT:
    """Datos de un contribuyente SUNAT relevantes para el motor de reglas."""

    ruc: str
    razon_social: Optional[str] = None
    nombre_comercial: Optional[str] = None
    tipo_contribuyente: Optional[str] = None
    fecha_inscripcion: Optional[date] = None
    fecha_inicio_actividades: Optional[date] = None
    estado: Optional[str] = None
    condicion: Optional[str] = None
    domicilio_fiscal: Optional[str] = None
    actividades_economicas: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Serializar dates a ISO string para JSON
        if self.fecha_inscripcion:
            d["fecha_inscripcion"] = self.fecha_inscripcion.isoformat()
        if self.fecha_inicio_actividades:
            d["fecha_inicio_actividades"] = self.fecha_inicio_actividades.isoformat()
        # raw queda fuera del dump por defecto (ruidoso)
        d.pop("raw", None)
        return d


# ============================================================================
# Normalización y fuzzy match de nombres de empresa
# ============================================================================

# Sufijos legales que aparecen al final del nombre y deben quitarse para
# comparar nombres "INSTITUTO DE CONSULTORIA" vs "INSTITUTO DE CONSULTORIA S.A."
_SUFIJOS_LEGALES_RE = re.compile(
    r"\b(?:"
    r"S\.?\s?A\.?\s?C\.?|"   # S.A.C. / SAC / S A C
    r"S\.?\s?A\.?\s?A\.?|"   # S.A.A.
    r"S\.?\s?A\.?|"           # S.A. / SA
    r"E\.?\s?I\.?\s?R\.?\s?L\.?|"  # E.I.R.L.
    r"S\.?\s?R\.?\s?L\.?|"   # S.R.L.
    r"S\.?\s?C\.?\s?R\.?\s?L\.?|"  # S.C.R.L.
    r"LTDA|LIMITADA|"
    r"SOCIEDAD\s+ANONIMA(?:\s+CERRADA|\s+ABIERTA)?|"
    r"EMPRESA\s+INDIVIDUAL\s+DE\s+RESPONSABILIDAD\s+LIMITADA"
    r")\b\.?",
    re.IGNORECASE,
)


def normalizar_nombre_empresa(s: str) -> str:
    """
    Normaliza un nombre de empresa para comparación fuzzy.

    Aplica:
      1. Strip de acentos (Ñ → N, á → a, etc.)
      2. Eliminación de sufijos legales (S.A., S.A.C., E.I.R.L., etc.)
      3. Eliminación de puntuación y símbolos
      4. Colapso de whitespace
      5. UPPERCASE

    Ejemplos:
      "INSTITUTO DE CONSULTORÍA S.A.C." → "INSTITUTO DE CONSULTORIA"
      "INDECONSULT  E.I.R.L."           → "INDECONSULT"
    """
    if not s:
        return ""
    # Quitar acentos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Quitar sufijos legales
    s = _SUFIJOS_LEGALES_RE.sub("", s)
    # Quitar puntuación que no sea letra/número/espacio
    s = re.sub(r"[^\w\s]", " ", s)
    # Colapsar whitespace y uppercase
    s = re.sub(r"\s+", " ", s).strip().upper()
    return s


def score_match_empresa(declarado: str, sunat: str) -> int:
    """
    Compara dos nombres de empresa con fuzzy matching.

    Returns:
        Score 0-100. Interpretación recomendada:
          ≥ 85: match fuerte (misma empresa, posible diferencia de sufijo)
          70-84: match parcial (probablemente misma pero verificar)
          < 70: mismatch (probablemente empresas distintas o RUC declarado mal)

    """
    norm_decl = normalizar_nombre_empresa(declarado or "")
    norm_sunat = normalizar_nombre_empresa(sunat or "")
    if not norm_decl or not norm_sunat:
        return 0
    # token_sort_ratio maneja bien orden distinto y palabras extra
    return int(fuzz.token_sort_ratio(norm_decl, norm_sunat))


# ============================================================================
# Helpers privados
# ============================================================================

def _fake_captcha_token(length: int = 52) -> str:
    """
    Genera un token aleatorio de la longitud que SUNAT espera.

    El campo `token` del POST se valida contra un stub que acepta cualquier
    string del largo correcto, así que cualquier valor random sirve.
    """
    # token_hex(26) → 52 chars hex
    return secrets.token_hex(length // 2)[:length]


def _parse_fecha_sunat(value: Optional[str]) -> Optional[date]:
    """Parsea fechas SUNAT en formato '15.06.2010' o '15/06/2010' o '15-06-2010'."""
    if not value:
        return None
    value = value.strip()
    if not value or value == "-":
        return None
    for sep in (".", "/", "-"):
        if sep in value:
            try:
                return datetime.strptime(value, f"%d{sep}%m{sep}%Y").date()
            except ValueError:
                continue
    return None


def _strip_tags(s: str) -> str:
    """Quita HTML tags y colapsa whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _parse_detalle(html: str) -> dict[str, Any]:
    """Extrae los campos del HTML de detalle SUNAT."""
    decoded = html_module.unescape(html)
    out: dict[str, Any] = {}

    for label in _FIELDS:
        pattern = (
            re.escape(label)
            + r":<\/h4>[\s\S]{0,300}?"
            + r"<(?:p|h4)[^>]*list-group-item-(?:text|heading)[^>]*>"
            + r"([\s\S]*?)<\/(?:p|h4)>"
        )
        m = re.search(pattern, decoded)
        if m:
            out[label] = _strip_tags(m.group(1))

    # Actividades económicas (pueden ser varias líneas en una tabla)
    act_block = re.search(
        r"Actividad\(es\) Económica\(s\):<\/h4>[\s\S]*?<table[\s\S]*?<\/table>",
        decoded,
    )
    if act_block:
        actividades = [
            _strip_tags(m.group(1))
            for m in re.finditer(r"<td[^>]*>([\s\S]*?)<\/td>", act_block.group(0))
        ]
        out["Actividades Económicas"] = [a for a in actividades if a]

    return out


def _parse_lista(html: str) -> list[dict[str, str]]:
    """Extrae items cuando la búsqueda devuelve múltiples resultados (razón social)."""
    decoded = html_module.unescape(html)
    items: list[dict[str, str]] = []

    pattern = re.compile(
        r"RUC:\s*<\/h4>[\s\S]*?<h4[^>]*>(\d{11})<\/h4>"
        r"[\s\S]*?<h4[^>]*>([^<]+)<\/h4>"
        r"[\s\S]*?Ubicaci[oó]n[^<]*:[^<]*<\/h4>[\s\S]*?<h4[^>]*>([^<]+)<\/h4>"
        r"[\s\S]*?Estado[^<]*:[^<]*<\/h4>[\s\S]*?<h4[^>]*>([^<]+)<\/h4>"
    )
    for m in pattern.finditer(decoded):
        items.append({
            "ruc": m.group(1).strip(),
            "razon_social": _strip_tags(m.group(2)),
            "ubicacion": _strip_tags(m.group(3)),
            "estado": _strip_tags(m.group(4)),
        })

    if not items:
        # Fallback: pattern más simple (solo RUC + razón social)
        for m in re.finditer(r"RUC:\s*(\d{11})[\s\S]*?<h4[^>]*>([^<]+)<\/h4>", decoded):
            items.append({
                "ruc": m.group(1).strip(),
                "razon_social": _strip_tags(m.group(2)),
            })

    return items


def _detectar_encoding(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "iso-8859-1" in ct or "latin1" in ct or "windows-1252" in ct:
        return "latin-1"
    return "utf-8"


# Markers de un reCAPTCHA real (no el stub actual). Si SUNAT activa captcha de
# verdad, el scraper deja de funcionar — esto lo hace detectable en logs/etapa
# en vez de un None silencioso.
_CAPTCHA_REAL_RE = re.compile(
    r"g-recaptcha|grecaptcha\.(?:execute|render)|data-sitekey|hcaptcha|cf-turnstile",
    re.IGNORECASE,
)


def diagnosticar_html_sunat(html: str) -> Optional[str]:
    """
    Clasifica por qué un HTML de SUNAT no es parseable.

    Devuelve:
      - None: estructura conocida (detalle o lista parseables) — no hay anomalía.
      - "ruc_inexistente": el portal respondió NORMAL con su mensaje nativo de
        "el número de RUC ... no es válido" → no es un fallo del scraper, es un
        RUC que no existe. No debe generar alerta operativa.
      - "captcha_real": la página trae un captcha de verdad (reCAPTCHA/hCaptcha/
        Turnstile). El stub actual dejó de bastar → requiere intervención.
      - "estructura_desconocida": no hay captcha pero tampoco los labels/patrones
        conocidos → SUNAT cambió el HTML; hay que recalibrar los parsers.
    """
    if not html:
        return "estructura_desconocida"
    if _parse_detalle(html).get("Número de RUC") or _parse_lista(html):
        return None
    # captcha PRIMERO: es la señal operativa más grave, no debe quedar enmascarada
    # por una frase genérica.
    if _CAPTCHA_REAL_RE.search(html):
        return "captcha_real"
    # mensaje nativo del portal para un RUC que no existe (respuesta normal).
    # Anclado a la frase específica "no es válido" — NO a substrings amplias como
    # "no registr"/"no existe", que matchean frases legítimas de páginas SUNAT
    # ("no registra operaciones/representantes") y enmascararían una rotura real.
    bajo = html.lower()
    if "no es válido" in bajo or "no es valido" in bajo:
        return "ruc_inexistente"
    return "estructura_desconocida"


# ============================================================================
# API pública
# ============================================================================

def consultar_ruc(
    ruc: str,
    *,
    timeout: float = 15.0,
    session: Optional[requests.Session] = None,
) -> Optional[EmpresaSUNAT]:
    """
    Consulta SUNAT por RUC (11 dígitos) y devuelve los datos del contribuyente.

    Devuelve `None` si:
      - SUNAT no responde 200
      - El RUC no existe
      - El HTML no es parseable

    El llamador es responsable de cachear el resultado por RUC (los datos SUNAT
    cambian muy poco — TTL razonable: 30 días).

    Args:
        ruc: número de RUC (11 dígitos)
        timeout: timeout HTTP por request, en segundos
        session: opcional, para reusar cookies/keep-alive entre llamadas

    Raises:
        ValueError: si el RUC no es 11 dígitos
    """
    if not re.match(r"^\d{11}$", ruc):
        raise ValueError(f"RUC debe ser 11 digitos: {ruc!r}")

    own_session = session is None
    if session is None:
        session = _crear_session_sunat()

    try:
        # Bootstrap con retry: GET para obtener cookies de sesion
        r_form = _request_with_retry(
            session, "GET", HOST + FORM_PATH,
            timeout=timeout, description=f"bootstrap RUC {ruc}",
        )
        if r_form is None or r_form.status_code >= 400:
            return None

        # POST con retry
        body = {
            "accion": "consPorRuc",
            "razSoc": "",
            "nroRuc": ruc,
            "nrodoc": "",
            "search1": ruc,
            "search2": "",
            "search3": "",
            "tipdoc": "1",
            "rbtnTipo": "1",
            "codigo": "",
            "contexto": "ti-it",
            "modo": "1",
            "token": _fake_captcha_token(),
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": HOST + FORM_PATH,
            "Origin": HOST,
        }
        r_search = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH,
            data=body, headers=headers,
            timeout=timeout, description=f"search RUC {ruc}",
        )
        if r_search is None or r_search.status_code >= 400:
            return None

        r_search.encoding = _detectar_encoding(r_search.headers.get("Content-Type", ""))
        html = r_search.text

        # Throttling suave para no martillar SUNAT
        if SUNAT_THROTTLE_DELAY > 0:
            time.sleep(SUNAT_THROTTLE_DELAY)
    finally:
        if own_session:
            session.close()

    # ¿Vino lista o detalle? La búsqueda por RUC siempre devuelve detalle,
    # pero defendemos por si SUNAT cambia.
    if "Relación de contribuyentes" in html or "Relaci&oacute;n de contribuyentes" in html:
        logger.info("SUNAT devolvio lista para RUC %s (inesperado)", ruc)
        return None

    raw = _parse_detalle(html)
    if not raw or not raw.get("Número de RUC"):
        diagnostico = diagnosticar_html_sunat(html)
        if diagnostico == "ruc_inexistente":
            # respuesta NORMAL del portal: el RUC no existe. Info, no alerta.
            logger.info("SUNAT: RUC %s no es válido / no existe (respuesta normal del portal)", ruc)
        elif diagnostico:
            # "captcha_real" / "estructura_desconocida" SÍ es un problema del
            # scraper (alerta operativa).
            logger.warning(
                "SUNAT no devolvio detalle parseable para RUC %s · diagnostico=%s",
                ruc, diagnostico,
            )
        else:
            logger.info("SUNAT no devolvio detalle parseable para RUC %s", ruc)
        return None

    # El campo "Número de RUC" viene como "12345 - RAZON SOCIAL"
    nro_ruc_full = raw.get("Número de RUC", "")
    razon_social = None
    if " - " in nro_ruc_full:
        razon_social = nro_ruc_full.split(" - ", 1)[1].strip()

    return EmpresaSUNAT(
        ruc=ruc,
        razon_social=razon_social,
        nombre_comercial=raw.get("Nombre Comercial") or None,
        tipo_contribuyente=raw.get("Tipo Contribuyente"),
        fecha_inscripcion=_parse_fecha_sunat(raw.get("Fecha de Inscripción")),
        fecha_inicio_actividades=_parse_fecha_sunat(raw.get("Fecha de Inicio de Actividades")),
        estado=raw.get("Estado del Contribuyente"),
        condicion=raw.get("Condición del Contribuyente"),
        domicilio_fiscal=raw.get("Domicilio Fiscal"),
        actividades_economicas=raw.get("Actividades Económicas", []),
        raw=raw,
    )


def buscar_por_razon_social(
    razon_social: str,
    *,
    timeout: float = 15.0,
    session: Optional[requests.Session] = None,
) -> list[dict[str, str]]:
    """
    Busca contribuyentes por razón social (puede devolver múltiples).

    Útil cuando la propuesta tiene el nombre de la empresa pero no el RUC, o
    para validar que un RUC declarado realmente coincida con el nombre.

    Devuelve lista de dicts con `ruc`, `razon_social`, `ubicacion`, `estado`.
    """
    own_session = session is None
    if session is None:
        session = _crear_session_sunat()

    try:
        r_form = _request_with_retry(
            session, "GET", HOST + FORM_PATH,
            timeout=timeout, description=f"bootstrap razon '{razon_social[:30]}'",
        )
        if r_form is None or r_form.status_code >= 400:
            return []

        body = {
            "accion": "consPorRazonSoc",
            "razSoc": razon_social,
            "nroRuc": "",
            "nrodoc": "",
            "search1": "",
            "search2": "",
            "search3": razon_social,
            "tipdoc": "1",
            "rbtnTipo": "3",
            "codigo": "",
            "contexto": "ti-it",
            "modo": "1",
            "token": _fake_captcha_token(),
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": HOST + FORM_PATH,
            "Origin": HOST,
        }
        r_search = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH,
            data=body, headers=headers,
            timeout=timeout, description=f"search razon '{razon_social[:30]}'",
        )
        if r_search is None or r_search.status_code >= 400:
            return []

        r_search.encoding = _detectar_encoding(r_search.headers.get("Content-Type", ""))
        html = r_search.text

        if SUNAT_THROTTLE_DELAY > 0:
            time.sleep(SUNAT_THROTTLE_DELAY)
    finally:
        if own_session:
            session.close()

    return _parse_lista(html)


# ============================================================================
# Representantes legales (acción getRepLeg) — insumo de ALT12
# ============================================================================

@dataclass
class RepresentanteLegal:
    """Representante legal declarado ante SUNAT (consulta getRepLeg)."""

    tipo_documento: str
    nro_documento: str
    nombre: str
    cargo: str
    fecha_desde: Optional[date] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.fecha_desde:
            d["fecha_desde"] = self.fecha_desde.isoformat()
        return d


_TIPOS_DOC_REP = ("DNI", "CE", "C.E.", "CARNET EXT.", "PASAPORTE", "RUC", "OTROS")


def _parse_representantes(html: str) -> list[RepresentanteLegal]:
    """
    Extrae la tabla de representantes del HTML de getRepLeg.

    Estructura observada (dump 25_getRepLeg.html):
      <table class="table"> con columnas
      Documento | Nro. Documento | Nombre | Cargo | Fecha Desde
    """
    decoded = html_module.unescape(html)
    reps: list[RepresentanteLegal] = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", decoded, re.I):
        celdas = [
            _strip_tags(td)
            for td in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr.group(1), re.I)
        ]
        celdas = [c for c in celdas if c]
        # Fila de datos: 5 columnas y la 1.ª es un tipo de documento conocido
        if len(celdas) == 5 and celdas[0].upper().rstrip(".") in (
            t.rstrip(".") for t in _TIPOS_DOC_REP
        ):
            reps.append(RepresentanteLegal(
                tipo_documento=celdas[0].upper(),
                nro_documento=celdas[1],
                nombre=celdas[2],
                cargo=celdas[3],
                fecha_desde=_parse_fecha_sunat(celdas[4]),
            ))
    return reps


def consultar_representantes(
    ruc: str,
    *,
    timeout: float = 20.0,
    session: Optional[requests.Session] = None,
) -> list[RepresentanteLegal]:
    """
    Consulta los representantes legales de un RUC (acción getRepLeg).

    Dato INFORMATIVO del bloque emisor (nombre, cargo y fecha desde de cada
    representante). No alimenta ninguna regla automática: ADR-008 descartó
    ALT-12 (firmante ≠ representante) por falsos positivos sistemáticos.
    Requiere encadenar dos consultas: consPorRuc (para obtener `numRnd` y la
    razón social) y luego getRepLeg.

    Devuelve [] si el RUC no existe, no tiene representantes declarados, o
    SUNAT no respondió (el detalle queda en logs, ver diagnosticar_html_sunat).
    """
    if not re.match(r"^\d{11}$", ruc):
        raise ValueError(f"RUC debe ser 11 digitos: {ruc!r}")

    own_session = session is None
    if session is None:
        session = _crear_session_sunat()

    try:
        r_form = _request_with_retry(
            session, "GET", HOST + FORM_PATH,
            timeout=timeout, description=f"bootstrap repleg {ruc}",
        )
        if r_form is None or r_form.status_code >= 400:
            return []

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": HOST + FORM_PATH,
            "Origin": HOST,
        }
        body_ruc = {
            "accion": "consPorRuc", "razSoc": "", "nroRuc": ruc, "nrodoc": "",
            "search1": ruc, "search2": "", "search3": "", "tipdoc": "1",
            "rbtnTipo": "1", "codigo": "", "contexto": "ti-it", "modo": "1",
            "token": _fake_captcha_token(),
        }
        r_det = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, data=body_ruc, headers=headers,
            timeout=timeout, description=f"detalle repleg {ruc}",
        )
        if r_det is None or r_det.status_code >= 400:
            return []
        r_det.encoding = _detectar_encoding(r_det.headers.get("Content-Type", ""))
        html_det = r_det.text

        # getRepLeg exige el numRnd de la página de detalle + la razón social
        m_rnd = re.search(r'name="numRnd"\s+value="([^"]*)"', html_det)
        m_raz = re.search(r"\d{11}\s*-\s*([^<]+)<", html_det)
        body_rep = {
            "accion": "getRepLeg", "nroRuc": ruc,
            "desRuc": _strip_tags(m_raz.group(1)) if m_raz else "",
            "contexto": "ti-it", "modo": "1",
            "numRnd": m_rnd.group(1) if m_rnd else "",
            "token": _fake_captcha_token(),
        }
        r_rep = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, data=body_rep, headers=headers,
            timeout=timeout, description=f"getRepLeg {ruc}",
        )
        if r_rep is None or r_rep.status_code >= 400:
            return []
        r_rep.encoding = _detectar_encoding(r_rep.headers.get("Content-Type", ""))

        if SUNAT_THROTTLE_DELAY > 0:
            time.sleep(SUNAT_THROTTLE_DELAY)

        reps = _parse_representantes(r_rep.text)
        if not reps:
            diagnostico = diagnosticar_html_sunat(r_rep.text)
            if diagnostico == "captcha_real":
                logger.warning("SUNAT getRepLeg %s · diagnostico=captcha_real", ruc)
        return reps
    finally:
        if own_session:
            session.close()


# ============================================================================
# Información histórica (acción getinfHis) — ¿el emisor estaba HABIDO cuando
# emitió el certificado y mientras duró la obra que certifica?
# ============================================================================
#
# El portal devuelve SIEMPRE tres tablas, en este orden:
#   1. Nombre o Razón Social  | Fecha de Baja
#   2. Condición del Contribuyente | Fecha Desde | Fecha Hasta
#   3. Dirección del Domicilio Fiscal | Fecha de Baja
# Cuando una no tiene datos, su única fila dice "No hay Información".
#
# OJO (sondeo 25-jul-2026): la respuesta declara `charset=ISO-8859-1` en el
# header pero manda UTF-8 → se decodifica a mano, NO con _detectar_encoding.

CONDICION_HABIDO = "HABIDO"

_SIN_DATOS = "no hay informaci"


@dataclass
class TramoCondicion:
    """Un tramo de la condición del contribuyente (HABIDO, NO HABIDO, NO HALLADO,
    PENDIENTE, POR VERIFICAR). `desde`/`hasta` en None = extremo abierto ("-")."""

    condicion: str
    desde: Optional[date] = None
    hasta: Optional[date] = None

    def cubre(self, f: date) -> bool:
        return (self.desde is None or f >= self.desde) and \
               (self.hasta is None or f <= self.hasta)

    def solapa(self, ini: date, fin: date) -> bool:
        return (self.desde is None or self.desde <= fin) and \
               (self.hasta is None or self.hasta >= ini)

    def to_dict(self) -> dict[str, Any]:
        return {"condicion": self.condicion,
                "desde": self.desde.isoformat() if self.desde else None,
                "hasta": self.hasta.isoformat() if self.hasta else None}


@dataclass
class HistoricoSUNAT:
    """Información histórica de un contribuyente (razón social, condición y
    domicilio fiscal anteriores, con sus vigencias)."""

    ruc: str
    razones_sociales: list[dict[str, Any]] = field(default_factory=list)
    condiciones: list[TramoCondicion] = field(default_factory=list)
    domicilios: list[dict[str, Any]] = field(default_factory=list)

    def vacio(self) -> bool:
        return not (self.razones_sociales or self.condiciones or self.domicilios)

    def to_dict(self) -> dict[str, Any]:
        return {"ruc": self.ruc,
                "razones_sociales": self.razones_sociales,
                "condiciones": [t.to_dict() for t in self.condiciones],
                "domicilios": self.domicilios}


def _filas_tabla(tabla_html: str) -> list[list[str]]:
    filas = []
    for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", tabla_html, re.I):
        filas.append([
            _strip_tags(c)
            for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr.group(1), re.I)
        ])
    return filas


def _parse_historico(html: str, ruc: str = "") -> HistoricoSUNAT:
    """Extrae las tres tablas del HTML de getinfHis.

    Devuelve un HistoricoSUNAT posiblemente vacío (el portal responde con las
    tablas armadas y "No hay Información" cuando el contribuyente no tiene
    historia) — eso NO es un fallo de parseo.
    """
    decoded = html_module.unescape(html)
    hist = HistoricoSUNAT(ruc=ruc)

    for t in re.finditer(r"<table[\s\S]*?</table>", decoded, re.I):
        filas = _filas_tabla(t.group(0))
        if not filas:
            continue
        cabecera = " ".join(filas[0]).lower()
        datos = [f for f in filas[1:]
                 if f and f[0] and not f[0].lower().startswith(_SIN_DATOS)]

        if "raz" in cabecera and "social" in cabecera:
            for f in datos:
                baja = _parse_fecha_sunat(f[1]) if len(f) > 1 else None
                hist.razones_sociales.append(
                    {"nombre": f[0], "fecha_baja": baja.isoformat() if baja else None})
        elif "condici" in cabecera:
            for f in datos:
                hist.condiciones.append(TramoCondicion(
                    condicion=f[0].upper(),
                    desde=_parse_fecha_sunat(f[1]) if len(f) > 1 else None,
                    hasta=_parse_fecha_sunat(f[2]) if len(f) > 2 else None))
        elif "domicilio" in cabecera:
            for f in datos:
                baja = _parse_fecha_sunat(f[1]) if len(f) > 1 else None
                # el portal a veces antepone guiones a la dirección ("----AV. …")
                hist.domicilios.append(
                    {"direccion": f[0].lstrip("- ").strip(),
                     "fecha_baja": baja.isoformat() if baja else None})

    return hist


def consultar_historico(
    ruc: str,
    *,
    timeout: float = 20.0,
    session: Optional[requests.Session] = None,
) -> Optional[HistoricoSUNAT]:
    """
    Consulta la "Información Histórica" de un RUC (acción getinfHis).

    Devuelve `None` si SUNAT no respondió o el RUC no existe (el portal devuelve
    una página de error genérica); un HistoricoSUNAT —posiblemente vacío— si la
    consulta salió bien.
    """
    if not re.match(r"^\d{11}$", ruc):
        raise ValueError(f"RUC debe ser 11 digitos: {ruc!r}")

    own_session = session is None
    if session is None:
        session = _crear_session_sunat()

    try:
        r_form = _request_with_retry(
            session, "GET", HOST + FORM_PATH,
            timeout=timeout, description=f"bootstrap hist {ruc}",
        )
        if r_form is None or r_form.status_code >= 400:
            return None

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": HOST + FORM_PATH,
            "Origin": HOST,
        }
        # getinfHis necesita la razón social (desRuc) de la ficha de detalle.
        # `numRnd` va vacío: la ficha lo trae vacío y el portal lo acepta así.
        body_ruc = {
            "accion": "consPorRuc", "razSoc": "", "nroRuc": ruc, "nrodoc": "",
            "search1": ruc, "search2": "", "search3": "", "tipdoc": "1",
            "rbtnTipo": "1", "codigo": "", "contexto": "ti-it", "modo": "1",
            "token": _fake_captcha_token(),
        }
        r_det = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, data=body_ruc, headers=headers,
            timeout=timeout, description=f"detalle hist {ruc}",
        )
        if r_det is None or r_det.status_code >= 400:
            return None
        r_det.encoding = _detectar_encoding(r_det.headers.get("Content-Type", ""))
        m_rnd = re.search(r'name="numRnd"\s+value="([^"]*)"', r_det.text)
        m_raz = re.search(r"\d{11}\s*-\s*([^<]+)<", r_det.text)

        r_his = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, headers=headers,
            data={"accion": "getinfHis", "nroRuc": ruc,
                  "desRuc": _strip_tags(m_raz.group(1)) if m_raz else "",
                  "contexto": "ti-it", "modo": "1",
                  "numRnd": m_rnd.group(1) if m_rnd else "",
                  "token": _fake_captcha_token()},
            timeout=timeout, description=f"getinfHis {ruc}",
        )
        if r_his is None or r_his.status_code >= 400:
            return None

        if SUNAT_THROTTLE_DELAY > 0:
            time.sleep(SUNAT_THROTTLE_DELAY)

        # el header miente el charset (dice ISO-8859-1, manda UTF-8)
        html = r_his.content.decode("utf-8", errors="replace")
    finally:
        if own_session:
            session.close()

    if "Pagina de Error" in html or "<table" not in html.lower():
        # RUC inexistente o el portal cortó: no hay histórico que parsear.
        logger.info("SUNAT getinfHis %s sin tablas (RUC inexistente o error del portal)", ruc)
        return None

    return _parse_historico(html, ruc)


def condicion_en_fecha(
    tramos: list[TramoCondicion],
    f: date,
    *,
    condicion_actual: Optional[str] = None,
) -> Optional[str]:
    """Condición del contribuyente vigente en la fecha `f`.

    Fechas posteriores al último tramo histórico caen en `condicion_actual` (la
    de la ficha): SUNAT cierra el histórico y no repite la condición vigente.
    Si dos tramos se pisan el mismo día (pasa: altas y bajas del mismo día),
    gana el más reciente de la lista.
    """
    cubren = [t for t in tramos if t.cubre(f)]
    if cubren:
        return cubren[-1].condicion
    ultimo = max((t.hasta for t in tramos if t.hasta), default=None)
    if ultimo and f > ultimo:
        return (condicion_actual or "").upper() or None
    if not tramos:
        return (condicion_actual or "").upper() or None
    return None


def condiciones_en_rango(
    tramos: list[TramoCondicion],
    ini: date,
    fin: date,
    *,
    condicion_actual: Optional[str] = None,
) -> list[TramoCondicion]:
    """Tramos de condición que tocan el rango [ini, fin], recortados al rango.

    Si el rango se extiende más allá del histórico, agrega un tramo final con la
    condición actual (ver `condicion_en_fecha`).
    """
    fuera: list[TramoCondicion] = []
    for t in tramos:
        if t.solapa(ini, fin):
            fuera.append(TramoCondicion(
                condicion=t.condicion,
                desde=max(t.desde, ini) if t.desde else ini,
                hasta=min(t.hasta, fin) if t.hasta else fin))
    ultimo = max((t.hasta for t in tramos if t.hasta), default=None)
    actual = (condicion_actual or "").upper()
    if actual and (not tramos or (ultimo and fin > ultimo)):
        desde = max(ultimo + timedelta(days=1), ini) if ultimo else ini
        if desde <= fin:
            fuera.append(TramoCondicion(condicion=actual, desde=desde, hasta=fin))
    return fuera


def _dias_sin_condicion(cubiertos: list[TramoCondicion],
                        ini: date, fin: date) -> list[tuple[date, date]]:
    """Sub-rangos de [ini, fin] donde NINGÚN tramo aporta condición.

    La cobertura parcial es la trampa del veredicto por rango: un solo tramo
    HABIDO que TOCA el periodo no dice nada del resto (cabeza antes del primer
    tramo, huecos intermedios, cola cuando la ficha no trae condición actual).
    Los `cubiertos` vienen de `condiciones_en_rango`, ya recortados al rango
    (desde/hasta siempre presentes)."""
    huecos: list[tuple[date, date]] = []
    cursor = ini
    for t in sorted(cubiertos, key=lambda t: t.desde or ini):
        if t.desde and t.desde > cursor:
            huecos.append((cursor, t.desde - timedelta(days=1)))
        siguiente = (t.hasta or fin) + timedelta(days=1)
        if siguiente > cursor:
            cursor = siguiente
        if cursor > fin:
            return huecos
    huecos.append((cursor, fin))
    return huecos


def evaluar_habido(
    tramos: list[TramoCondicion],
    *,
    fecha_emision: Optional[date] = None,
    ini: Optional[date] = None,
    fin: Optional[date] = None,
    condicion_actual: Optional[str] = None,
) -> dict[str, Any]:
    """Responde las dos preguntas del evaluador con el histórico SUNAT:

      · ¿estaba HABIDO el día que emitió el certificado?
      · ¿estuvo HABIDO durante todo el periodo de la experiencia?

    Cada respuesta trae `ok` (True/False/None si no se puede saber), la condición
    encontrada y —para el periodo— los tramos que no fueron HABIDO.
    """
    out: dict[str, Any] = {"emision": None, "periodo": None}

    if fecha_emision:
        cond = condicion_en_fecha(tramos, fecha_emision,
                                  condicion_actual=condicion_actual)
        out["emision"] = {
            "fecha": fecha_emision.isoformat(),
            "condicion": cond,
            "ok": None if not cond else cond == CONDICION_HABIDO,
        }

    if ini and fin and fin >= ini:
        cubiertos = condiciones_en_rango(tramos, ini, fin,
                                         condicion_actual=condicion_actual)
        malos = [t for t in cubiertos if t.condicion != CONDICION_HABIDO]
        huecos = _dias_sin_condicion(cubiertos, ini, fin)
        # "Sí" exige cobertura COMPLETA del periodo: HABIDO en los tramos con
        # dato + días sin condición = "no verificable", nunca un verde. Un tramo
        # NO HABIDO sí es veredicto duro aunque haya huecos (eso ya se sabe).
        out["periodo"] = {
            "desde": ini.isoformat(), "hasta": fin.isoformat(),
            "condiciones": sorted({t.condicion for t in cubiertos}),
            # tramos recortados al periodo: es lo que se muestra en el cuadro
            # histórico del Excel (el histórico completo puede traer 30 filas)
            "tramos": [t.to_dict() for t in cubiertos],
            "tramos_no_habido": [t.to_dict() for t in malos],
            "sin_dato": [{"desde": a.isoformat(), "hasta": b.isoformat()}
                         for a, b in huecos],
            "ok": (False if malos
                   else True if cubiertos and not huecos else None),
        }

    return out


def sondear(timeout: float = 6.0) -> tuple[bool, Optional[str]]:
    """Sondeo LIGERO de disponibilidad de SUNAT para el endpoint /salud. Hace un
    solo GET a la página de consulta (NO una búsqueda real) y reporta
    (ok, diagnostico). Nunca lanza: ante cualquier fallo devuelve (False, motivo)."""
    # OJO: la página de consulta de SUNAT trae captcha POR DISEÑO (el scraper real
    # lo sortea). Por eso el sondeo mide solo REACHABILITY (que cargue), NO corre
    # diagnosticar_html_sunat — eso daría un falso "caído".
    try:
        session = _crear_session_sunat()
        try:
            r = session.get(f"{HOST}/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp",
                            timeout=timeout)
            return (True, None) if r.status_code < 400 else (False, f"HTTP {r.status_code}")
        finally:
            session.close()
    except Exception:  # noqa: BLE001 — sondeo no debe propagar
        return False, "sin conexion"


# ============================================================================
# CLI util — `python -m src.scraping.sunat <RUC>`
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) != 2:
        print("Uso: python -m src.scraping.sunat <RUC|razon social>", file=sys.stderr)
        sys.exit(1)

    arg = sys.argv[1]
    if re.match(r"^\d{11}$", arg):
        empresa = consultar_ruc(arg)
        if not empresa:
            print(json.dumps({"error": "RUC no encontrado o error al consultar"}))
            sys.exit(2)
        print(json.dumps(empresa.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        items = buscar_por_razon_social(arg)
        print(json.dumps({"resultados": items}, ensure_ascii=False, indent=2))
