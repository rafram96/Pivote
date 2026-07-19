"""
seace.py — Esqueleto único del scraper SEACE (SEACE v3 · JSF/PrimeFaces).

╔══════════════════════════════════════════════════════════════════════════╗
║  SONDA GO/NO-GO (2026-07-18) — LEER ANTES DE USAR                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Veredicto: el POST directo de requests YA NO trae resultados. El buscador ║
║  de Procedimientos de Selección añadió un CANDADO reCAPTCHA v3:            ║
║                                                                            ║
║    · El botón visible "Buscar" es `btnBuscarSelToken`, con                 ║
║      onclick="cargaTokenBuscadorProSel()". Esa función ejecuta             ║
║      grecaptcha.execute(siteKey 6Lfhnb0p…, {action}) → obtiene un token    ║
║      (~2300 chars) → lo mete en el campo `tokenBusProSel` → recién ahí     ║
║      dispara el btnBuscarSel real.                                         ║
║    · Sin ese token el server responde 200 pero "total 0" (falso vacío      ║
║      silencioso). Verificado en vivo: mismo filtro da 0 sin token y        ║
║      15 filas con token generado por grecaptcha en el navegador.          ║
║    · requests NO puede generar el token (necesita ejecutar el JS de        ║
║      Google con la site key en contexto de navegador con dominio válido). ║
║                                                                            ║
║  → NO-GO para el scraper puro-requests de abajo (queda como referencia de  ║
║    la mecánica JSF: payloads, ficha, resolución de docs Oracle/Alfresco,   ║
║    que SIGUEN siendo válidos una vez que hay sesión con búsqueda hecha).   ║
║                                                                            ║
║  Camino viable para T-004 (integración real): búsqueda DRIVEN-BY-BROWSER.  ║
║    Un navegador headless (o el Chrome MCP de la corrida) abre el buscador, ║
║    corre cargaTokenBuscadorProSel() para que grecaptcha emita el token,    ║
║    ejecuta la búsqueda, y de ahí en adelante se reusa la sesión/cookies    ║
║    para navegar la ficha y descargar docs con la mecánica de requests de   ║
║    este archivo. Es el patrón "browser resuelve el captcha → requests hace ║
║    el resto", exactamente lo previsto en la cláusula NO-GO del plan.       ║
║                                                                            ║
║  Nota extra de la sonda: el portal abre por defecto en la pestaña          ║
║  "Anuncio de Contratación Futura" (idFormbuscarACF); el buscador que       ║
║  interesa es "Procedimientos de Selección" (idFormBuscarProceso, tab1).    ║
║  Objeto de Contratación es OBLIGATORIO. Los j_idt de los <select> del      ║
║  form de proceso SIGUEN siendo 179/188/214/242/269 (los 211/220/… que      ║
║  aparecen en el HTML crudo son de otra pestaña).                          ║
╚══════════════════════════════════════════════════════════════════════════╝


Condensa TODO el núcleo reutilizable del scraping en un solo archivo:

    1. SessionManager  → sesión HTTP, cookies, ViewState/token, POST JSF, descarga
    2. SearchEngine    → búsqueda del proceso + paginación + parseo de resultados
    3. FichaScraper    → navegación a la ficha + navegación genérica por botón JSF
                         + extracción y RESOLUCIÓN de documentos (Oracle + Alfresco CMS)
    4. Seace           → fachada de alto nivel. Aquí cuelgan los alcances concretos.

Metodología (idéntica para cualquier alcance nuevo):
    capturar POST real → replicar con requests → parsear HTML → resolver + descargar.
    Lo único que cambia entre alcances es *qué botón* se pulsa y *qué documento* se filtra.

Alcances cableados como extension points (sección "ALCANCES"):
    · Bases Integradas   → cuelgan de la ficha; solo hay que filtrar los docs.
    · Contrato firmado   → vive en Ejecución Contractual; clon de "navegar por botón".
      (Selectores exactos marcados con TODO: confirmar contra output/debug/*.html)

Dependencias: requests, beautifulsoup4, lxml
"""
from __future__ import annotations

import re
import json
import time
import random
import logging
from pathlib import Path
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  CONFIG — valores confirmados del HTML real del portal                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

BASE_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"
FICHA_URL = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/fichaSeleccion/fichaSeleccion.xhtml"
HOST = "https://prod2.seace.gob.pe"

# Formularios JSF
FORM_PREFIX = "tbBuscador:idFormBuscarProceso"      # buscador
FICHA_FORM = "tbFicha:idFormFichaSeleccion"          # ficha de selección

# Almacenamiento de documentos
ORACLE_STORAGE_BASE = (
    "https://objectstorage.us-ashburn-1.oraclecloud.com"
    "/p/Dzntd99-p_tkMvf4fBb84XnTuATEnKSVs5kmqURV5UKjaREd6MlLfIx6a30XDwUP"
    "/n/axx9tnhijsfw/b/BUCKET_PROD_SEACE/o"
)
ALFRESCO_CLOUD = "https://alfprod.seace.gob.pe/alfresco"
ALFRESCO_ONPREM = "https://prodcont2.seace.gob.pe/alfresco"
CMS_DOWNLOAD_PATH = "/service/osce/downloadDoc"

# Rate limiting (respeto al servidor)
MIN_DELAY, MAX_DELAY, PAGE_DELAY = 2.0, 4.0, 3.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
)
AJAX_HEADERS = {
    "Faces-Request": "partial/ajax",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/xml, text/xml, */*; q=0.01",
}

# Objeto de contratación (value="" del <option>)
OBJETO = {"bien": "62", "consultoria_obra": "63", "obra": "64", "servicio": "65"}

# Departamentos (value="" del <option>)
DEPARTAMENTOS = {
    "AMAZONAS": "2", "ANCASH": "3", "APURIMAC": "4", "AREQUIPA": "5", "AYACUCHO": "6",
    "CAJAMARCA": "7", "CALLAO": "8", "CUSCO": "9", "EXTERIOR": "9997",
    "HUANCAVELICA": "10", "HUANUCO": "11", "ICA": "12", "JUNIN": "13", "LA LIBERTAD": "14",
    "LAMBAYEQUE": "15", "LIMA": "16", "LORETO": "17", "MADRE DE DIOS": "18", "MOQUEGUA": "19",
    "MULTIDEPARTAMENTAL": "9994", "PASCO": "20", "PIURA": "21", "PUNO": "22",
    "SAN MARTIN": "23", "TACNA": "24", "TUMBES": "25", "UCAYALI": "26",
}

# Campos JSF del buscador
F = {
    "btn_buscar": f"{FORM_PREFIX}:btnBuscarSel",
    "anio": f"{FORM_PREFIX}:anioConvocatoria_input",
    "objeto": f"{FORM_PREFIX}:j_idt188_input",
    "tipo_seleccion": f"{FORM_PREFIX}:j_idt179_input",
    "descripcion": f"{FORM_PREFIX}:descripcionObjeto",
    "departamento": f"{FORM_PREFIX}:departamento_input",
    "provincia": f"{FORM_PREFIX}:provincia_input",
    "distrito": f"{FORM_PREFIX}:distrito_input",
    "ruc": f"{FORM_PREFIX}:hddNumeroRuc",
    "entidad": f"{FORM_PREFIX}:nombreEntidad",
    "numero_seleccion": f"{FORM_PREFIX}:numeroSeleccion",
    "codigo_snip": f"{FORM_PREFIX}:codigoSnip",
    "cui": f"{FORM_PREFIX}:CUI",
    "version": f"{FORM_PREFIX}:j_idt214_input",
    "token": f"{FORM_PREFIX}:tokenBusProSel",
    "ip_cliente": f"{FORM_PREFIX}:ipClienteIpify",
    "modalidad": f"{FORM_PREFIX}:j_idt242_input",
    "tipo_compra": f"{FORM_PREFIX}:j_idt269_input",
    "numero_convocatoria": f"{FORM_PREFIX}:numeroConvocatoria",
    "fecha_inicio": f"{FORM_PREFIX}:dfechaInicio_input",
    "fecha_fin": f"{FORM_PREFIX}:dfechaFin_input",
    "collapsed": f"{FORM_PREFIX}:j_idt232_collapsed",
    "panel_resultados": f"{FORM_PREFIX}:pnlGrdResultadosProcesos",
    "panel_buscar": f"{FORM_PREFIX}:pnlBuscarProceso",
    "footer": f"{FORM_PREFIX}:footerBuscador",
    "mensajes": "frmMesajes:gPrincipal",
    "datatable": f"{FORM_PREFIX}:dtProcesos",
}

# Directorios de salida (convención del repo: artefactos de sondas bajo tools/)
OUTPUT_DIR = Path(__file__).parent / "_sonda_seace"
DOCS_DIR = OUTPUT_DIR / "documentos"
for _d in (DOCS_DIR, OUTPUT_DIR / "debug"):
    _d.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("seace")

_VIEWSTATE_RE = re.compile(r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"')


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  MODELOS DE DATOS                                                           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

@dataclass
class SearchFilters:
    """Filtros del buscador público de procesos."""
    anio: str = "2025"
    descripcion: str = ""
    objeto: str = ""            # "64" obra, "62" bien, "65" servicio, "63" consultoría
    version: str = "3"          # "2" o "3"
    departamento: str = ""
    entidad: str = ""
    ruc_entidad: str = ""
    numero_seleccion: str = ""
    codigo_snip: str = ""
    cui: str = ""


@dataclass
class ProcessResult:
    """Un proceso de la tabla de resultados. `extras` lleva los nid_* de navegación."""
    numero: str = ""
    entidad: str = ""
    fecha_publicacion: str = ""
    nomenclatura: str = ""
    objeto: str = ""
    descripcion: str = ""
    valor_referencial: str = ""
    moneda: str = ""
    version_seace: str = ""
    extras: dict = field(default_factory=dict)


@dataclass
class Documento:
    """Un documento resuelto y listo para descargar."""
    nombre: str = ""
    url: str = ""
    tipo: str = ""       # "2" oracle, "3" cms alfresco
    origen: str = ""     # ficha, contrato, oracle_directo, ...


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  1. SESSION MANAGER — sesión, ViewState/token, POST JSF, descarga          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class SessionManager:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "es-419,es;q=0.6"})
        self.viewstate: str | None = None
        self.token: str = ""
        self._last_request = 0.0

    def initialize(self) -> bool:
        """GET inicial: cookies + ViewState + token de búsqueda."""
        log.info("Inicializando sesión contra SEACE...")
        try:
            r = self.session.get(BASE_URL, timeout=30)
            r.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Error al conectar con SEACE: {e}")
            return False

        soup = BeautifulSoup(r.text, "html.parser")
        vs = soup.find("input", {"name": "javax.faces.ViewState"})
        if not vs or not vs.get("value"):
            log.error("No se encontró javax.faces.ViewState")
            return False
        self.viewstate = vs["value"]

        tok = soup.find("input", {"name": f"{FORM_PREFIX}:tokenBusProSel"})
        self.token = tok["value"] if tok and tok.get("value") else ""
        log.info(f"Sesión lista (ViewState {self.viewstate[:24]}... token {'ok' if self.token else 'vacío'})")
        return True

    # ── Rate limiting ────────────────────────────────────────────────────────
    def _rate_limit(self, custom: float | None = None):
        delay = custom if custom else random.uniform(MIN_DELAY, MAX_DELAY)
        elapsed = time.time() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.time()

    # ── POST AJAX (partial-response JSF) ──────────────────────────────────────
    def ajax_post(self, payload: dict, custom_delay: float | None = None) -> str | None:
        self._rate_limit(custom_delay)
        payload["javax.faces.ViewState"] = self.viewstate
        try:
            r = self.session.post(BASE_URL, data=payload, headers=AJAX_HEADERS, timeout=60)
            r.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Error en POST AJAX: {e}")
            return None
        # Refrescar ViewState si vino en el partial-response
        m = re.search(r'<update\s+id="[^"]*ViewState[^"]*">\s*<!\[CDATA\[(.*?)\]\]>', r.text, re.DOTALL)
        if m and m.group(1).strip():
            self.viewstate = m.group(1).strip()
        return r.text

    # ── POST FORM (full submit, sigue redirect) ───────────────────────────────
    def form_post(self, url: str, payload: dict, custom_delay: float | None = None) -> tuple[str | None, str]:
        """Simula PrimeFaces.submit(): POST completo que sigue el 302."""
        self._rate_limit(custom_delay)
        payload.setdefault("javax.faces.ViewState", self.viewstate)
        try:
            r = self.session.post(url, data=payload, timeout=60, allow_redirects=True)
            r.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Error en POST form: {e}")
            return None, ""
        m = _VIEWSTATE_RE.search(r.text)
        if m:
            self.viewstate = m.group(1)
        return r.text, r.url

    # ── Descarga de archivos ──────────────────────────────────────────────────
    def download_file(self, url: str, dest: Path) -> bool:
        self._rate_limit()
        try:
            r = self.session.get(url, timeout=60, stream=True)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            log.info(f"Descargado: {dest.name}")
            return True
        except requests.RequestException as e:
            log.error(f"Error descargando {url}: {e}")
            return False


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  2. SEARCH ENGINE — búsqueda + paginación + parseo                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class SearchEngine:
    def __init__(self, session: SessionManager):
        self.s = session
        self.total_resultados = 0

    def search(self, filters: SearchFilters) -> list[ProcessResult]:
        resp = self.s.ajax_post(self._payload(filters))
        if not resp:
            return []
        if '"validationFailed":true' in resp:
            for msg in re.findall(r'"summary":"([^"]+)"', resp):
                log.error(f"Validación JSF: {msg}")
            return []
        results = self._parse(resp)
        log.info(f"Encontrados {len(results)} (total {self.total_resultados})")
        return results

    def search_all_pages(self, filters: SearchFilters, max_pages: int = 50) -> list[ProcessResult]:
        acc = self.search(filters)
        if not acc:
            return []
        page = 0
        while len(acc) < self.total_resultados and page + 1 < max_pages:
            page += 1
            batch = self._next_page(page)
            if not batch:
                break
            acc.extend(batch)
            log.info(f"Acumulados {len(acc)}/{self.total_resultados}")
        return acc

    # ── Payloads ───────────────────────────────────────────────────────────────
    def _payload(self, ft: SearchFilters) -> dict:
        focus = lambda k: F[k].replace("_input", "_focus")
        return {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": F["btn_buscar"],
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render": (
                f"{F['panel_resultados']} {F['footer']} {F['mensajes']} "
                f"{F['btn_buscar']} {F['panel_buscar']}"
            ),
            F["btn_buscar"]: F["btn_buscar"], "submit": "S",
            FORM_PREFIX: FORM_PREFIX, f"{FORM_PREFIX}:numPositionTabView": "1",
            F["ruc"]: ft.ruc_entidad, F["entidad"]: ft.entidad,
            F["tipo_seleccion"]: "", focus("tipo_seleccion"): "",
            F["objeto"]: ft.objeto, focus("objeto"): "",
            F["numero_seleccion"]: ft.numero_seleccion,
            F["descripcion"]: ft.descripcion,
            F["anio"]: ft.anio, focus("anio"): "",
            F["version"]: ft.version, focus("version"): "",
            F["codigo_snip"]: ft.codigo_snip, F["cui"]: ft.cui,
            F["modalidad"]: "", focus("modalidad"): "",
            F["departamento"]: ft.departamento, focus("departamento"): "",
            F["provincia"]: "", focus("provincia"): "",
            F["distrito"]: "", focus("distrito"): "",
            F["numero_convocatoria"]: "",
            F["tipo_compra"]: "", focus("tipo_compra"): "",
            F["fecha_inicio"]: "", F["fecha_fin"]: "",
            F["collapsed"]: "true",
            F["token"]: self.s.token, F["ip_cliente"]: "",
            f"{FORM_PREFIX}:txtNombreEntidad": "", f"{FORM_PREFIX}:txtRucEntidad": "",
            f"{FORM_PREFIX}:txtsigla": "",
        }

    def _next_page(self, page: int) -> list[ProcessResult]:
        dt = F["datatable"]
        payload = {
            "javax.faces.partial.ajax": "true", "javax.faces.source": dt,
            "javax.faces.partial.execute": dt, "javax.faces.partial.render": dt,
            "javax.faces.behavior.event": "page", "javax.faces.partial.event": "page",
            FORM_PREFIX: FORM_PREFIX,
            f"{dt}_pagination": "true", f"{dt}_first": str(page * 15), f"{dt}_rows": "15",
        }
        resp = self.s.ajax_post(payload, custom_delay=PAGE_DELAY)
        return self._parse(resp) if resp else []

    # ── Parseo del partial-response ───────────────────────────────────────────
    def _parse(self, xml: str) -> list[ProcessResult]:
        results: list[ProcessResult] = []
        for block in re.findall(r'<!\[CDATA\[(.*?)\]\]>', xml, re.DOTALL):
            if "dtProcesos" not in block and "ui-datatable" not in block:
                continue
            soup = BeautifulSoup(block, "lxml")
            tbody = soup.find("tbody", {"id": re.compile(r"dtProcesos_data")}) \
                or soup.find("tbody", class_="ui-datatable-data")
            if not tbody:
                continue
            if tbody.find("td", string=re.compile(r"No se encontraron", re.I)):
                self.total_resultados = 0
                return []
            for row in tbody.find_all("tr", recursive=False):
                r = self._parse_row(row)
                if r:
                    results.append(r)
            self._parse_pagination(soup)
        return results

    def _parse_row(self, row) -> ProcessResult | None:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 7:
            return None
        txt = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)).strip() for c in cells]
        r = ProcessResult(
            numero=txt[0] if len(txt) > 0 else "",
            entidad=txt[1] if len(txt) > 1 else "",
            fecha_publicacion=txt[2] if len(txt) > 2 else "",
            nomenclatura=txt[3] if len(txt) > 3 else "",
            objeto=txt[5] if len(txt) > 5 else "",
            descripcion=txt[6] if len(txt) > 6 else "",
            valor_referencial=txt[9] if len(txt) > 9 else "",
            moneda=txt[10] if len(txt) > 10 else "",
            version_seace=txt[11] if len(txt) > 11 else "",
        )
        # Parámetros de navegación a la ficha (del onclick con nidProceso)
        for cell in cells:
            for elem in cell.find_all(attrs={"onclick": True}):
                oc = elem.get("onclick", "")
                if "nidProceso" not in oc:
                    continue
                r.extras["ficha_onclick"] = oc
                for key, pat in (
                    ("nid_proceso", r"'nidProceso':'(\d+)'"),
                    ("nid_convocatoria", r"'nidConvocatoria':'([^']+)'"),
                    ("nid_sistema", r"'nidSistema':'(\d+)'"),
                    ("ntipo", r"'ntipo':'(\d+)'"),
                ):
                    m = re.search(pat, oc)
                    if m:
                        r.extras[key] = m.group(1)
                idx = re.search(r"dtProcesos:(\d+):", oc)
                jidt = re.search(r"(j_idt\d+)", oc)
                if idx:
                    r.extras["row_index"] = int(idx.group(1))
                if jidt:
                    r.extras["j_idt"] = jidt.group(1)
        if not (r.nomenclatura or r.descripcion or r.entidad):
            return None
        return r

    def _parse_pagination(self, soup):
        span = soup.find("span", class_="ui-paginator-current")
        if span:
            m = re.search(r"total\s+(\d+)", span.get_text(strip=True), re.I)
            if m:
                self.total_resultados = int(m.group(1))
        for script in soup.find_all("script"):
            m = re.search(r"rowCount:(\d+)", script.get_text())
            if m:
                self.total_resultados = int(m.group(1))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  3. FICHA SCRAPER — navegación genérica por botón + resolución de docs      ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class FichaScraper:
    """
    Núcleo reutilizable. La metodología completa vive aquí:

        open_ficha()        → resultados → ficha (POST + 302)
        find_button()       → localiza el j_idt de un enlace por su texto
        navigate_button()   → pulsa ese botón (clon de "Ver Ofertas Presentadas")
        extract_documents() → saca Oracle + descargaDocGeneral de cualquier HTML
        resolve_cms_url()   → UUID Alfresco → URL descargable (JSONP)
        download()          → baja una lista de Documento a disco

    Un alcance nuevo = open_ficha → (opcional) navigate_button → extract → filtrar → download.
    """

    def __init__(self, session: SessionManager):
        self.s = session

    # ── Navegación: resultados → ficha ────────────────────────────────────────
    def open_ficha(self, proc: ProcessResult) -> tuple[str | None, str]:
        """POST al buscador simulando el click en el ícono 'Ficha de Selección'."""
        e = proc.extras
        if "nid_proceso" not in e:
            log.warning(f"Proceso sin nid_proceso: {proc.nomenclatura}")
            return None, ""
        self.s.initialize()  # ViewState fresco antes de navegar
        row_key = f"{FORM_PREFIX}:dtProcesos:{e.get('row_index', 0)}:{e.get('j_idt', '')}"
        payload = {
            FORM_PREFIX: FORM_PREFIX, row_key: row_key,
            "ntipo": e.get("ntipo", "1"),
            "nidConvocatoria": e.get("nid_convocatoria", ""),
            "nidProceso": e["nid_proceso"],
            "nidSistema": e.get("nid_sistema", "3"),
            "ptoRetorno": "LOCAL",
        }
        html, url = self.s.form_post(BASE_URL, payload)
        if not html:
            log.error(f"No se pudo abrir ficha: {proc.nomenclatura}")
        return html, url

    # ── Navegación genérica por botón JSF ─────────────────────────────────────
    @staticmethod
    def find_button(html: str, link_text: str) -> str | None:
        """
        Localiza el component-id (j_idt) de un enlace por su texto visible.
        Generaliza el patrón de 'Ver Ofertas Presentadas':
            onclick="...{'form:j_idtNNN':'form:j_idtNNN'}...">Texto del enlace
        """
        m = re.search(
            r'onclick="([^"]+)"[^>]*>\s*' + re.escape(link_text),
            html, re.IGNORECASE,
        )
        if not m:
            log.warning(f"No se encontró el botón: {link_text!r}")
            return None
        cm = re.search(r"'([\w:]+:j_idt\d+)'\s*:\s*'\1'", m.group(1))
        return cm.group(1) if cm else None

    def navigate_button(
        self, html: str, form_id: str, component_id: str,
        post_url: str | None = None, extra: dict | None = None,
    ) -> tuple[str | None, str]:
        """
        Pulsa un botón JSF: reusa el ViewState del HTML dado y sigue el redirect.
        `post_url` se deduce del action del form si no se pasa.
        """
        vs = _VIEWSTATE_RE.search(html)
        if not vs:
            log.error("No se encontró ViewState para navegar el botón")
            return None, ""
        if post_url is None:
            am = re.search(rf'<form[^>]*id="{re.escape(form_id)}"[^>]*action="([^"]+)"', html)
            post_url = f"{HOST}{am.group(1)}" if am else FICHA_URL
        payload = {form_id: form_id, component_id: component_id, "javax.faces.ViewState": vs.group(1)}
        if extra:
            payload.update(extra)
        return self.s.form_post(post_url, payload)

    # ── Extracción + resolución de documentos ─────────────────────────────────
    def extract_documents(self, html: str, origen: str = "ficha") -> list[Documento]:
        """
        Extrae y RESUELVE todos los documentos descargables de un HTML:
            · URLs directas de Oracle Object Storage
            · descargaDocGeneral('id', tipo, 'path')   tipo 2=Oracle · tipo 3=Alfresco CMS
        """
        docs: list[Documento] = []

        # 1) Oracle directo
        for url in set(re.findall(r'https?://objectstorage[^\s"\'<>]+', html)):
            url = url.rstrip(")\"';")
            nombre = url.split("/o/")[-1].split("?")[0] if "/o/" in url else url.split("/")[-1]
            docs.append(Documento(nombre=nombre, url=url, tipo="2", origen=f"{origen}_oracle"))

        # 2) descargaDocGeneral / descargaDoc* → resolver por tipo
        for m in re.finditer(
            r"descargaDoc\w*\(\s*'([^']*)'\s*,\s*'?(\d+)'?\s*,\s*'([^']*)'\s*\)", html
        ):
            doc_id, tipo, path = m.groups()
            if not doc_id and not path:   # declaración de función / llamada vacía
                continue
            url = ""
            if tipo == "2":
                url = path if path.startswith("http") else f"{ORACLE_STORAGE_BASE}{path}"
            elif tipo == "3":
                url = self.resolve_cms_url(doc_id) or ""
                if not url:
                    continue
            else:
                url = path
            if url:
                docs.append(Documento(nombre=path or doc_id, url=url, tipo=tipo, origen=origen))

        # Deduplicar por URL
        seen, out = set(), []
        for d in docs:
            if d.url and d.url not in seen:
                seen.add(d.url)
                out.append(d)
        return out

    def resolve_cms_url(self, uuid: str, guest: bool = False) -> str | None:
        """
        Resuelve un UUID de Alfresco a URL descargable (replica jsCmsSeaceUtil.descargaPriv):
            GET .../downloadDoc?id=UUID → JSONP {result, downloadUrl}
            result 200 → cloud · 201 → on-prem
        """
        if not uuid:
            return None
        cb = f"c{random.randint(1, 99999999)}"
        url = f"{ALFRESCO_CLOUD}{CMS_DOWNLOAD_PATH}?id={uuid}&doc={cb}&guest={'true' if guest else 'false'}"
        try:
            r = self.s.session.get(url, timeout=30)
            r.raise_for_status()
            text = r.text.strip()
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end < 0:
                return None
            data = json.loads(text[start:end + 1])
            code, dl = str(data.get("result", "")), data.get("downloadUrl", "")
            if code == "200" and dl:
                return f"{ALFRESCO_CLOUD}{dl}"
            if code == "201" and dl:
                return f"{ALFRESCO_ONPREM}{dl}"
            log.warning(f"CMS result={code} para {uuid[:16]}")
            return None
        except Exception as e:
            log.error(f"CMS error: {e}")
            return None

    # ── Descarga a disco ──────────────────────────────────────────────────────
    def download(self, docs: list[Documento], dest_dir: Path) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        for i, d in enumerate(docs):
            if not d.url.startswith("http"):
                continue
            name = d.nombre or ""
            if not name or len(name) < 3:
                name = d.url.split("/o/")[-1].split("?")[0] if "/o/" in d.url \
                    else d.url.split("/")[-1].split("?")[0]
            name = re.sub(r"[^\w\-.]", "_", name) or f"doc_{i}"
            if "." not in name:
                name += ".pdf"
            path, n = dest_dir / name, 1
            while path.exists():
                path = dest_dir / f"{path.stem}_{n}{path.suffix}"
                n += 1
            if self.s.download_file(d.url, path):
                saved.append(path)
        return saved


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  4. SEACE — fachada de alto nivel + ALCANCES                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝

class Seace:
    """Punto de entrada único. Compone sesión + búsqueda + ficha."""

    def __init__(self):
        self.session = SessionManager()
        self.search_engine = SearchEngine(self.session)
        self.ficha = FichaScraper(self.session)

    def connect(self) -> bool:
        return self.session.initialize()

    def buscar(self, filters: SearchFilters, all_pages: bool = False, max_pages: int = 50) -> list[ProcessResult]:
        return (self.search_engine.search_all_pages(filters, max_pages)
                if all_pages else self.search_engine.search(filters))

    # ─────────────────────────────────────────────────────────────────────────
    #  ALCANCES  ·  mismo método, distinto botón
    # ─────────────────────────────────────────────────────────────────────────

    def descargar_bases_integradas(self, proc: ProcessResult, dest: Path | None = None) -> list[Path]:
        """
        Bases Integradas → cuelgan directamente de la ficha.
        Flujo: open_ficha → extract_documents → filtrar 'bases integradas' → download.

        TODO(selector): confirmar el texto/columna literal contra output/debug/ficha_*.html
                        (algunas fichas etiquetan 'Bases Integradas', otras solo 'Bases').
        """
        html, _ = self.ficha.open_ficha(proc)
        if not html:
            return []
        docs = self.ficha.extract_documents(html, origen="bases")
        bases = [d for d in docs if "bases" in d.nombre.lower()]
        if not bases:
            log.info(f"Sin Bases descargables: {proc.nomenclatura}")
        dest = dest or (DOCS_DIR / _slug(proc.nomenclatura) / "bases")
        return self.ficha.download(bases, dest)

    def descargar_contrato(self, proc: ProcessResult, dest: Path | None = None) -> list[Path]:
        """
        Contrato firmado → vive en Ejecución Contractual (solo si el proceso ya está contratado).
        Flujo: open_ficha → find_button(Ejecución Contractual) → navigate_button
               → extract_documents → filtrar 'contrato' → download.

        MATIZ DE ESTADO: el contrato firmado solo existe si el proceso ya llegó a
        'Buena Pro consentida → Contratado'. Un proceso todavía en convocatoria NO
        tendrá contrato. Por eso el pipeline debe DETECTAR EL ESTADO antes de intentar
        bajarlo — misma lógica de "detectar opción → navegar si existe" con la que hoy
        se detecta `tiene_ofertas` antes de ir a ofertas. Aquí ese chequeo lo hace
        `find_button`: si el botón de Ejecución Contractual no está, el proceso aún no
        tiene contrato y se retorna vacío sin error.

        TODO(selector): confirmar el label real del botón y el nombre del doc de contrato
                        contra un HTML de ficha que YA haya llegado a contrato.
        """
        html, _ = self.ficha.open_ficha(proc)
        if not html:
            return []
        boton = self.ficha.find_button(html, "Ejecución Contractual")  # TODO: confirmar label
        if not boton:
            log.info(f"Proceso sin contrato aún (o botón distinto): {proc.nomenclatura}")
            return []
        contrato_html, _ = self.ficha.navigate_button(html, FICHA_FORM, boton)
        if not contrato_html:
            return []
        docs = self.ficha.extract_documents(contrato_html, origen="contrato")
        contrato = [d for d in docs if "contrato" in d.nombre.lower()]
        dest = dest or (DOCS_DIR / _slug(proc.nomenclatura) / "contrato")
        return self.ficha.download(contrato, dest)


def _slug(text: str) -> str:
    return re.sub(r"[^\w\-]", "_", text)[:80] or "proceso"


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  DEMO / CLI mínimo                                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _demo():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    seace = Seace()
    if not seace.connect():
        return

    filtros = SearchFilters(anio="2025", descripcion="hospital", objeto=OBJETO["obra"], version="3")
    procesos = seace.buscar(filtros)
    log.info(f"== {len(procesos)} procesos ==")

    for p in procesos[:3]:
        log.info(f"→ {p.nomenclatura} | {p.entidad}")
        bases = seace.descargar_bases_integradas(p)
        contrato = seace.descargar_contrato(p)
        log.info(f"   bases={len(bases)} contrato={len(contrato)}")


if __name__ == "__main__":
    _demo()
