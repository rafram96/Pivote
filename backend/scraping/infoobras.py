"""
Scraper de InfoObras (Contraloría General de la República).

Endpoints usados:
  [1] POST /infobrasweb/Mapa/busqueda/obrasBasic → búsqueda por CUI
  [5] GET /InfobrasWeb/Mapa/DatosEjecucion?ObraId={id} → datos de ejecución

Los datos de ejecución vienen como variables JavaScript embebidas en el HTML:
  var lAvances = [...];     → avances mensuales con estado/paralización
  var lSupervisor = [...];  → histórico de supervisores
  var lResidente = [...];   → histórico de residentes
  var lContratista = [...]; → contratista ejecutor

Sin CAPTCHA, sin Playwright — solo requests + regex.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html import unescape as _unescape
from urllib.parse import parse_qs, unquote, urlsplit
from typing import Callable, Optional

import requests

from scraping.errores_red import LINEAL, Politica, con_reintentos, corto, reintentar

# Reintentos de las tres consultas al portal (ADR-014): la temporización es la
# que ya tenían los bucles artesanales — 1.5s, 3.0s entre intentos.
_POLITICA = Politica(intentos=3, base=1.5, modo=LINEAL)

logger = logging.getLogger(__name__)

BASE_MAPA = "https://infobras.contraloria.gob.pe/infobrasweb"
BASE_WEB = "https://infobras.contraloria.gob.pe/InfobrasWeb"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{BASE_WEB}/Mapa/Index",
}

# Regex para localizar el INICIO de cada declaracion `var lXxx = ...`.
# El JSON real (que puede contener arrays anidados, comillas, etc.) se parsea
# despues con json.JSONDecoder.raw_decode para no depender de regex no-greedy.
_JS_VAR_START_RE = re.compile(r"var\s+(l[A-Z]\w*)\s*=\s*", re.MULTILINE)
_JSON_DECODER = json.JSONDecoder()

# Meses en español → número
_MES_NUM = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4,
    "MAYO": 5, "JUNIO": 6, "JULIO": 7, "AGOSTO": 8,
    "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
    "NOVIEMBRE": 11, "DICIEMBRE": 12,
}

# Rate limiting: segundos entre requests
_DELAY = 2.0


# ---------------------------------------------------------------------------
# Modelos de datos
# ---------------------------------------------------------------------------

@dataclass
class SupervisorInfo:
    """Un supervisor/inspector registrado en InfoObras."""
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str]
    tipo: str                          # "Inspector" / "Supervisor"
    tipo_persona: str                  # "Natural" / "Juridica"
    empresa: Optional[str]
    ruc: Optional[str]
    dni: Optional[str]
    fecha_inicio: Optional[date]
    fecha_fin: Optional[date]


@dataclass
class ResidenteInfo:
    """Un residente registrado en InfoObras."""
    nombre: str
    apellido_paterno: str
    apellido_materno: Optional[str]
    fecha_inicio: Optional[date]
    fecha_fin: Optional[date]


@dataclass
class AvanceMensual:
    """Un avance mensual de la obra."""
    anio: int
    mes: int
    estado: str                        # "En ejecución" / "Paralizado" / "Finalizado"
    tipo_paralizacion: Optional[str]   # "Total" / "Parcial" / None
    fecha_paralizacion: Optional[date]
    dias_paralizado: int
    causal: Optional[str]
    # Campos financieros del cronograma (todos opcionales — no siempre vienen)
    avance_fisico_programado: Optional[float] = None  # %
    avance_fisico_real: Optional[float] = None        # %
    valorizado_programado: Optional[float] = None     # S/.
    valorizado_real: Optional[float] = None           # S/.
    pct_ejecucion_financiera: Optional[float] = None  # %
    monto_ejecucion_financiera: Optional[float] = None  # S/.
    num_documentos: int = 0            # documentos de valorización adjuntos (van al ZIP)


@dataclass
class ContratistaInfo:
    """Un contratista ejecutor registrado en InfoObras."""
    tipo_empresa: str                  # "Consorcio" / "Individual"
    ruc: Optional[str]                 # RUC con prefijo "C" si es consorcio
    nombre_empresa: str
    monto_soles: Optional[float]
    numero_contrato: Optional[str]
    fecha_contrato: Optional[date]
    fecha_fin_contrato: Optional[date]


@dataclass
class ModificacionPlazoInfo:
    """Una modificación de plazo (ampliación o suspensión)."""
    tipo: str                          # "Ampliación del plazo" / "Suspensión del plazo"
    causal: Optional[str]
    dias_aprobados: int
    fecha_aprobacion: Optional[date]
    fecha_fin: Optional[date]


@dataclass
class EntregaTerrenoInfo:
    """Registro de entrega de terreno."""
    fecha_entrega: Optional[date]
    porcentaje: Optional[float]
    tipo_entrega: Optional[str] = None     # "Total" / "Parcial"


@dataclass
class AdendaInfo:
    """Adenda al contrato (modificacion contractual formal)."""
    numero: Optional[str]
    fecha: Optional[date]
    descripcion: Optional[str] = None


@dataclass
class TransferenciaFinancieraInfo:
    """Transferencia financiera recibida por la entidad ejecutora."""
    ambito: Optional[str]
    entidad_origen: Optional[str]
    monto: Optional[float]
    documento: Optional[str] = None


@dataclass
class AdelantoInfo:
    """Garantia de adelanto (directo, materiales, etc.)."""
    tipo: Optional[str]                    # "Directo" / "Materiales" / etc.
    monto: Optional[float]
    fecha_entrega: Optional[date]
    documento_aprobacion: Optional[str] = None


@dataclass
class CronogramaInfo:
    """Cronograma vigente o actualizacion del cronograma."""
    tipo: Optional[str]                    # "Original" / "Actualizado" / "Reformulado"
    fecha_aprobacion: Optional[date]
    documento: Optional[str] = None
    nueva_fecha_termino: Optional[date] = None


@dataclass
class AdicionalDeductivoInfo:
    """Adicional, deductivo o reduccion al contrato."""
    numero: Optional[str]
    tipo: Optional[str]                    # "Adicional" / "Deductivo" / "Reduccion"
    subtipo: Optional[str]                 # subcategoria si existe
    causal: Optional[str]
    fecha_aprobacion: Optional[date]
    porcentaje: Optional[float]
    monto: Optional[float]
    documento: Optional[str] = None


@dataclass
class ControversiaInfo:
    """Controversia o proceso de solucion de controversias."""
    mecanismo: Optional[str]               # "Arbitraje" / "Junta de Resolucion" / etc.
    estado: Optional[str]
    fecha_inicio: Optional[date]
    fecha_fin: Optional[date]
    documento: Optional[str] = None


@dataclass
class WorkInfo:
    """Datos completos de una obra de InfoObras."""
    cui: str
    obra_id: int
    nombre: Optional[str] = None
    estado: Optional[str] = None
    tipo_obra: Optional[str] = None
    entidad: Optional[str] = None
    ejecutor: Optional[str] = None
    ruc_ejecutor: Optional[str] = None
    monto_contrato: Optional[float] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    plazo_dias: Optional[int] = None
    # Campos de cabecera adicionales
    codigo_infoobras: Optional[str] = None              # ej: "169628"
    porcentaje_avance_fisico: Optional[float] = None   # del ultimo avance real
    monto_ejecutado_acumulado: Optional[float] = None  # S/. acumulado
    # Colecciones existentes
    supervisores: list[SupervisorInfo] = field(default_factory=list)
    residentes: list[ResidenteInfo] = field(default_factory=list)
    avances: list[AvanceMensual] = field(default_factory=list)
    contratistas: list[ContratistaInfo] = field(default_factory=list)
    modificaciones_plazo: list[ModificacionPlazoInfo] = field(default_factory=list)
    entregas_terreno: list[EntregaTerrenoInfo] = field(default_factory=list)
    suspension_periods: list[tuple[date, date]] = field(default_factory=list)
    # Colecciones nuevas (refinacion 2026-04)
    adendas: list[AdendaInfo] = field(default_factory=list)
    transferencias: list[TransferenciaFinancieraInfo] = field(default_factory=list)
    adelantos: list[AdelantoInfo] = field(default_factory=list)
    cronogramas: list[CronogramaInfo] = field(default_factory=list)
    adicionales_deductivos: list[AdicionalDeductivoInfo] = field(default_factory=list)
    controversias: list[ControversiaInfo] = field(default_factory=list)
    raw_busqueda: dict = field(default_factory=dict)
    # Aprobación del EXPEDIENTE técnico (hito "Aprobación del proyecto" de la Línea de
    # tiempo, página Mapa/Sumario). Solo se busca cuando la obra NO tiene valorizaciones
    # (posible experiencia de expediente). {url, filename, nombre, extension, fecha} | None
    aprobacion_expediente: Optional[dict] = None


# ---------------------------------------------------------------------------
# Parseo de fechas
# ---------------------------------------------------------------------------

def _parse_fecha_ddmmyyyy(texto: Optional[str]) -> Optional[date]:
    """Parsea 'DD/MM/YYYY' a date."""
    if not texto or not texto.strip():
        return None
    try:
        return datetime.strptime(texto.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _parse_timestamp_json(ts_str: Optional[str]) -> Optional[date]:
    """Parsea '/Date(1574485200000)/' a date."""
    if not ts_str:
        return None
    m = re.search(r"/Date\((\d+)\)/", ts_str)
    if not m:
        return None
    ts = int(m.group(1)) / 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


# ---------------------------------------------------------------------------
# Session y requests
# ---------------------------------------------------------------------------

def _crear_session() -> requests.Session:
    """Crea una session HTTP con cookies y headers de InfoObras.

    El GET de calentamiento (obtiene las cookies ASP.NET) se reintenta: si caía
    por una microcaída/DNS del portal, el resolver abortaba toda la consulta
    devolviendo None aunque la obra existiera."""
    s = requests.Session()
    s.headers.update(HEADERS)

    def _calentar() -> requests.Session:
        s.get(f"{BASE_WEB}/", timeout=10)
        return s

    res = con_reintentos(_calentar, politica=_POLITICA,
                         etiqueta="InfoObras warmup",
                         excepciones=(requests.RequestException,), log=logger)
    res.relanzar()          # nunca contestó → propaga, como antes
    return res.valor


def _buscar_por_cui(session: requests.Session, cui: str) -> list[dict]:
    """
    Busca obras por CUI en InfoObras.
    Retorna lista de dicts crudos de la API.
    """
    params_json = {
        "codDepartamento": "", "codProvincia": None, "codDistrito": None,
        "codigoObra": "", "estadoRegistro": "", "nobrCodmodejec": "",
        "cobrCodentpub": "", "codtipobrnv1": "", "codtipobrnv2": None,
        "nombrObra": "", "codSnip": cui,
        "fechaIniObraDesde": "", "fechaIniObraHasta": "",
        "tieneMonitor": "", "estObra": "", "codNivel3": None,
        "codMarca": "", "modServControl": "", "servControl": "",
        "nombreEntidad": "", "getFavoritos": 0,
    }
    url = f"{BASE_MAPA}/Mapa/busqueda/obrasBasic"
    query = {
        "page": 0,
        "rowsPerPage": 20,
        "Parameters": json.dumps(params_json, separators=(",", ":")),
    }
    # El portal es NO determinístico: ante un hipo responde 200 con lista VACÍA
    # (no por ausencia real — "las tablas varían entre corridas"). Como un CUI
    # citado debería existir, se reintenta tanto ante excepción de red COMO ante
    # resultado vacío, con backoff. Solo se concluye "no está" si sigue vacío tras
    # agotar los intentos. (Antes solo reintentaba en excepción → un 200-vacío
    # daba "sin candidato fiable" para un CUI que sí existe; resolución no estable.)
    def _consultar() -> list[dict]:
        r = session.post(url, params=query, timeout=15)
        r.raise_for_status()
        data = r.json()
        result = data.get("Result", data)
        if isinstance(result, list):
            obras = result
        elif isinstance(result, dict):
            obras = result.get("data", result.get("obras", [result]))
        else:
            obras = []
        # filtro exacto: la API matchea codSnip por substring (buscar '95555' trae
        # '2595555'). Quedarse solo con los registros del código pedido.
        encontradas = [o for o in obras if coincide_codigo(o, cui)]
        if encontradas:
            return encontradas
        # 200 pero vacío para un código específico: casi siempre es hipo del
        # portal → reintentar; si sigue vacío al agotar, el vacío ES el dato.
        return reintentar([])

    res = con_reintentos(_consultar, politica=_POLITICA,
                         etiqueta=f"InfoObras búsqueda CUI {cui}",
                         excepciones=(requests.RequestException,), log=logger)
    res.relanzar()          # siempre falló la red → relanzar (como antes)
    return res.valor        # contestó: la lista (vacía = no está)


def _parse_js_vars(html: str) -> dict[str, list]:
    """
    Parsea TODAS las declaraciones `var lXxx = [...];` del HTML.

    Usa json.JSONDecoder.raw_decode para soportar correctamente arrays
    con sub-arrays anidados (ej: `lSupervisor = [{Documentos: [...]}]`),
    cosa que un regex no-greedy no maneja bien.

    Retorna {nombre_variable: lista_de_dicts}.
    Variables `null` o no-arrays se omiten silenciosamente.
    """
    variables: dict[str, list] = {}
    nulls: list[str] = []  # vars que aparecen como `null` (existen pero vacias)
    fallidas: list[str] = []  # vars que existen pero no se pudieron parsear

    for match in _JS_VAR_START_RE.finditer(html):
        nombre = match.group(1)
        pos = match.end()
        # Saltar whitespace antes del valor
        while pos < len(html) and html[pos] in " \t\r\n":
            pos += 1
        if pos >= len(html):
            continue
        ch = html[pos]
        if ch == "n":
            if html[pos:pos + 4] == "null":
                variables[nombre] = []
                nulls.append(nombre)
            continue
        if ch != "[" and ch != "{":
            continue
        try:
            obj, _ = _JSON_DECODER.raw_decode(html, pos)
        except json.JSONDecodeError:
            fallidas.append(nombre)
            logger.warning("InfoObras: no se pudo parsear var %s en pos %d", nombre, pos)
            continue
        if isinstance(obj, list):
            variables[nombre] = obj
        elif isinstance(obj, dict):
            variables[nombre] = [obj]

    # Log diagnostico: que variables se encontraron y con cuantos registros
    if logger.isEnabledFor(logging.INFO):
        resumen = ", ".join(
            f"{n}={len(v)}" for n, v in sorted(variables.items())
        )
        logger.info("InfoObras [vars JS]: %s", resumen or "(ninguna)")
        if nulls:
            logger.info("InfoObras [vars null]: %s", ", ".join(sorted(nulls)))
        if fallidas:
            logger.warning("InfoObras [vars no parseadas]: %s", ", ".join(fallidas))

    return variables


def _extraer_datos_ejecucion(session: requests.Session, obra_id: int) -> dict[str, list]:
    """
    Descarga DatosEjecucion y extrae las variables JS embebidas (incluye
    lAvances = las valorizaciones). Retorna {nombre_variable: lista_de_dicts}.

    Reintenta ante caídas transitorias del portal (RemoteDisconnected/5xx): es
    el dato CRÍTICO de la obra, y un solo drop hacía perder la obra entera (se
    veían tablas de valorización vacías al azar entre corridas).
    """
    url = f"{BASE_WEB}/Mapa/DatosEjecucion"

    def _bajar() -> dict[str, list]:
        session.headers["Accept"] = "text/html,*/*"
        try:
            r = session.get(url, params={"ObraId": obra_id}, timeout=30)
            r.raise_for_status()
            variables = _parse_js_vars(r.text)
            # modificaciones de plazo y contratista ejecutor van como tabla HTML,
            # no como var JS (lModificacionPlazo/lContratista vacíos en plantilla nueva)
            variables["_modificaciones_plazo"] = _parsear_modificaciones_html(r.text)
            variables["_contratistas_html"] = _parsear_contratistas_html(r.text)
            variables["_supervisores_html"] = _parsear_supervisores_html(r.text)
            return variables
        finally:
            session.headers["Accept"] = "application/json, text/javascript, */*; q=0.01"

    res = con_reintentos(_bajar, politica=_POLITICA,
                         etiqueta=f"InfoObras DatosEjecucion obra {obra_id}",
                         excepciones=(requests.RequestException,), log=logger)
    res.relanzar()
    return res.valor


def _extraer_datos_preparacion(session: requests.Session, obra_id: int) -> dict[str, list]:
    """
    Descarga DatosPreparacion y extrae las variables JS embebidas.

    Aunque el SCRAPER.md original decia que este endpoint cargaba todo
    via AJAX, en realidad expone como variables JS embebidas:
      - lSupervisor (historico completo de supervisores/inspectores)
      - lResidente (historico completo de residentes)
      - lPersonal (otros profesionales clave)
      - lRevisionET (revisiones del expediente tecnico)

    Para obras con plantilla nueva (PRONIS, hospitalarias 2023+), estos
    datos NO aparecen en /Mapa/DatosEjecucion (solo lAvances), por lo
    que es necesario consultar este endpoint complementario.
    """
    url = f"{BASE_WEB}/Mapa/DatosPreparacion"
    session.headers["Accept"] = "text/html,*/*"
    try:
        r = session.get(url, params={"ObraId": obra_id}, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.debug("InfoObras: DatosPreparacion ObraId %s: %s", obra_id, corto(e))
        return {}
    finally:
        session.headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
    return _parse_js_vars(r.text)


def _extraer_todos_los_datos(session: requests.Session, obra_id: int) -> dict[str, list]:
    """
    Descarga DatosEjecucion + DatosPreparacion y mergea sus variables JS.

    DatosEjecucion → lAvances (+ lContratista, lModificacionPlazo, etc. en
                     plantilla vieja; solo lAvances en plantilla nueva)
    DatosPreparacion → lSupervisor, lResidente, lPersonal, lRevisionET

    Si una variable aparece en ambos endpoints, prevalece la que tenga
    mas registros (defensa contra arrays vacios en uno de los dos).
    """
    datos_ejecucion = _extraer_datos_ejecucion(session, obra_id)
    time.sleep(_DELAY)
    datos_preparacion = _extraer_datos_preparacion(session, obra_id)

    merged = dict(datos_ejecucion)
    for var_name, lista in datos_preparacion.items():
        existente = merged.get(var_name, [])
        if len(lista) > len(existente):
            merged[var_name] = lista
    return merged


# ---------------------------------------------------------------------------
# Procesamiento de datos crudos → modelos
# ---------------------------------------------------------------------------

def _procesar_supervisores(raw_list: list[dict]) -> list[SupervisorInfo]:
    """Convierte la lista cruda de lSupervisor a SupervisorInfo."""
    supervisores = []
    for r in raw_list:
        supervisores.append(SupervisorInfo(
            nombre=r.get("NombreRep", ""),
            apellido_paterno=r.get("ApellidoPaterno", ""),
            apellido_materno=r.get("ApellidoMaterno"),
            tipo=r.get("TipoSupervisor", ""),
            tipo_persona=r.get("TipoPersona", ""),
            empresa=r.get("NombreEmpresa"),
            ruc=r.get("Ruc"),
            dni=r.get("NumeroDocRep"),
            fecha_inicio=_parse_fecha_ddmmyyyy(r.get("FechaInicio")),
            fecha_fin=_parse_fecha_ddmmyyyy(r.get("FechaFin")),
        ))
    return supervisores


def _procesar_residentes(raw_list: list[dict]) -> list[ResidenteInfo]:
    """Convierte la lista cruda de lResidente a ResidenteInfo."""
    residentes = []
    for r in raw_list:
        residentes.append(ResidenteInfo(
            nombre=r.get("NombreRep", ""),
            apellido_paterno=r.get("ApellidoPaterno", ""),
            apellido_materno=r.get("ApellidoMaterno"),
            fecha_inicio=_parse_fecha_ddmmyyyy(r.get("FechaInicio")),
            fecha_fin=_parse_fecha_ddmmyyyy(r.get("FechaFin")),
        ))
    return residentes


def _to_float(v) -> Optional[float]:
    """Convierte a float aceptando None, '', strings con coma, etc."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _procesar_avances(raw_list: list[dict]) -> list[AvanceMensual]:
    """Convierte la lista cruda de lAvances a AvanceMensual."""
    if raw_list and logger.isEnabledFor(logging.INFO):
        logger.info(
            "InfoObras [lAvances][1] keys: %s",
            sorted(raw_list[0].keys()),
        )
    avances = []
    for r in raw_list:
        anio_raw = r.get("Anio", "0")
        anio_str = str(anio_raw)
        mes_str = (r.get("Mes") or "").upper().strip()
        anio = int(anio_str) if anio_str.isdigit() else 0
        mes = _MES_NUM.get(mes_str, 0)

        avances.append(AvanceMensual(
            anio=anio,
            mes=mes,
            estado=r.get("Estado", ""),
            tipo_paralizacion=r.get("TipoParalizacion"),
            fecha_paralizacion=_parse_fecha_ddmmyyyy(r.get("FechaParalizacion")),
            dias_paralizado=int(r.get("DiasParalizado", 0) or 0),
            causal=r.get("Causal"),
            # Nombres confirmados via probe contra CUI 2427358 (Tambobamba):
            avance_fisico_programado=_to_float(r.get("PorcProgramadoFisico")),
            avance_fisico_real=_to_float(r.get("PorcRealFisico")),
            valorizado_programado=_to_float(r.get("ProgramadoFinanc")),
            valorizado_real=_to_float(r.get("RealFinanc")),
            pct_ejecucion_financiera=_to_float(r.get("PorcEjecFinanc")),
            monto_ejecucion_financiera=_to_float(r.get("MontoEjecFinanc")),
            # documentos de valorización adjuntos a este avance (los que el ZIP
            # baja a la carpeta del hito); 'lImgFisico' son imágenes, no van al ZIP
            num_documentos=len(r.get("lImgValorizacion") or []),
        ))
    return avances


def _procesar_contratistas(raw_list: list[dict]) -> list[ContratistaInfo]:
    """Convierte la lista cruda de lContratista a ContratistaInfo."""
    if raw_list and logger.isEnabledFor(logging.INFO):
        logger.info(
            "InfoObras [lContratista][1] keys: %s",
            sorted(raw_list[0].keys()),
        )
    contratistas = []
    for r in raw_list:
        contratistas.append(ContratistaInfo(
            tipo_empresa=r.get("TipoEmpresa", ""),
            ruc=r.get("Ruc"),
            nombre_empresa=r.get("NombreEmpresa", ""),
            monto_soles=r.get("MontoSoles"),
            numero_contrato=r.get("NumeroContrato"),
            fecha_contrato=_parse_fecha_ddmmyyyy(r.get("FechaContrato")),
            fecha_fin_contrato=_parse_fecha_ddmmyyyy(r.get("FechaFinContrato")),
        ))
    return contratistas


def _sintetizar_contratista_de_busqueda(obra_raw: dict) -> Optional[ContratistaInfo]:
    """
    Cuando lContratista viene vacio pero el endpoint de busqueda si tiene
    los datos del ejecutor, sintetiza un registro para que la UI no
    muestre 'Contratistas: 0' incorrectamente.
    """
    nombre = obra_raw.get("nombreEjecutor") or obra_raw.get("ejecutor")
    if not nombre:
        return None
    return ContratistaInfo(
        tipo_empresa="",
        ruc=obra_raw.get("rucEjecutor") or obra_raw.get("ruc"),
        nombre_empresa=str(nombre).strip(),
        monto_soles=obra_raw.get("montoObraSoles"),
        numero_contrato=None,
        fecha_contrato=_parse_timestamp_json(obra_raw.get("fechaIniObra")),
        fecha_fin_contrato=_parse_timestamp_json(obra_raw.get("fechaFinObra")),
    )


def _procesar_modificaciones_plazo(raw_list: list[dict]) -> list[ModificacionPlazoInfo]:
    """Convierte la lista cruda de lModificacionPlazo a ModificacionPlazoInfo."""
    modificaciones = []
    for r in raw_list:
        modificaciones.append(ModificacionPlazoInfo(
            tipo=r.get("TipoModificacion", ""),
            causal=r.get("Causal"),
            dias_aprobados=int(r.get("DiasAprobados", 0) or 0),
            fecha_aprobacion=_parse_fecha_ddmmyyyy(r.get("FechaAprob")),
            fecha_fin=_parse_fecha_ddmmyyyy(r.get("FechaFin")),
        ))
    return modificaciones


_RE_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_RE_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_RE_TAGS = re.compile(r"<[^>]+>")


def _parsear_modificaciones_html(html_txt: str) -> list[ModificacionPlazoInfo]:
    """Las modificaciones de plazo NO vienen como var JS (lModificacionPlazo está
    vacío en la mayoría de obras) — vienen como TABLA HTML en DatosEjecucion.
    8 columnas: N° · tipo · número · causal · días · fecha aprobación · fecha fin
    · documento. Se identifican las filas cuyo 'tipo' es ampliación/suspensión."""
    out: list[ModificacionPlazoInfo] = []
    for tr in _RE_TR.findall(html_txt or ""):
        celdas = _RE_TD.findall(tr)
        if len(celdas) != 8:
            continue
        txt = [_unescape(_RE_TAGS.sub(" ", c)).strip() for c in celdas]
        if not re.search(r"(Ampliaci|Suspensi)", txt[1], re.I):
            continue
        out.append(ModificacionPlazoInfo(
            tipo=txt[1],
            causal=txt[3] or None,
            dias_aprobados=int(txt[4]) if txt[4].isdigit() else 0,
            fecha_aprobacion=_parse_fecha_ddmmyyyy(txt[5]),
            fecha_fin=_parse_fecha_ddmmyyyy(txt[6]),
        ))
    return out


def _parsear_contratistas_html(html_txt: str) -> list[ContratistaInfo]:
    """El contratista ejecutor tampoco viene como var JS en la plantilla nueva —
    viene como TABLA HTML en DatosEjecucion (sección "Representante de obra").
    7 columnas: N° · tipo empresa · RUC · razón social · monto · fecha inicio ·
    fecha fin. Se aíslan las filas cuya 3ª celda es un RUC de 11 dígitos."""
    out: list[ContratistaInfo] = []
    for tr in _RE_TR.findall(html_txt or ""):
        celdas = _RE_TD.findall(tr)
        if len(celdas) != 7:
            continue
        txt = [_unescape(_RE_TAGS.sub(" ", c)).strip() for c in celdas]
        if not re.search(r"\b\d{11}\b", txt[2]):
            continue
        monto = re.sub(r"[^\d.]", "", txt[4])
        out.append(ContratistaInfo(
            tipo_empresa=txt[1],
            ruc=txt[2],
            nombre_empresa=txt[3],
            monto_soles=float(monto) if monto else None,
            numero_contrato=None,
            fecha_contrato=_parse_fecha_ddmmyyyy(txt[5]),
            fecha_fin_contrato=_parse_fecha_ddmmyyyy(txt[6]),
        ))
    return out


def _parsear_supervisores_html(html_txt: str) -> list[dict]:
    """Supervisores/inspectores de la sección "Representante de obra" de
    DatosEjecucion (tabla de 9 columnas): N° · tipo · tipo persona · documento ·
    razón social · monto · fecha inicio · fecha fin · documento designación.
    Aporta el MONTO y el documento de designación que `lSupervisor`
    (DatosPreparacion) no trae. Devuelve dicts (no dataclass) para fusionar."""
    out: list[dict] = []
    for tr in _RE_TR.findall(html_txt or ""):
        celdas = _RE_TD.findall(tr)
        if len(celdas) != 9:
            continue
        txt = [_unescape(_RE_TAGS.sub(" ", c)).strip() for c in celdas]
        if not re.search(r"supervisor|inspector", txt[1], re.I):
            continue
        monto = re.sub(r"[^\d.]", "", txt[5])
        # documento de designación: link "Ver documento" si existe, si no "-"
        m = (re.search(r'(?:href|onclick)\s*=\s*["\']([^"\']*(?:srvDownload|ViewPDF|\.pdf|https?)[^"\']*)',
                       celdas[8], re.I)
             or re.search(r'(https?://[^"\'\s<>]+)', celdas[8]))
        out.append({
            "tipo": txt[1] or None,
            "tipo_persona": txt[2] or None,
            "documento": txt[3] or None,
            "razon_social": txt[4] or None,
            "monto_soles": float(monto) if monto else None,
            "fecha_inicio": _parse_fecha_ddmmyyyy(txt[6]),
            "fecha_fin": _parse_fecha_ddmmyyyy(txt[7]),
            "doc_designacion": m.group(1) if m else None,
        })
    return out


def _procesar_entregas_terreno(raw_list: list[dict]) -> list[EntregaTerrenoInfo]:
    """Convierte la lista cruda de lEntregaTerreno a EntregaTerrenoInfo."""
    entregas = []
    for r in raw_list:
        entregas.append(EntregaTerrenoInfo(
            fecha_entrega=_parse_fecha_ddmmyyyy(r.get("FechaEntrega")),
            porcentaje=_to_float(r.get("Porcentaje")),
            tipo_entrega=r.get("TipoEntrega") or r.get("Tipo"),
        ))
    return entregas


def _procesar_adendas(raw_list: list[dict]) -> list[AdendaInfo]:
    """Convierte la lista cruda de lAdenda a AdendaInfo."""
    adendas = []
    for r in raw_list:
        adendas.append(AdendaInfo(
            numero=str(r.get("NumeroAdenda") or r.get("Numero") or "").strip() or None,
            fecha=_parse_fecha_ddmmyyyy(r.get("FechaAdenda") or r.get("Fecha")),
            descripcion=r.get("Descripcion") or r.get("Detalle"),
        ))
    return adendas


def _procesar_transferencias(raw_list: list[dict]) -> list[TransferenciaFinancieraInfo]:
    """Convierte la lista cruda de lTransferenciaFinanciera."""
    transferencias = []
    for r in raw_list:
        transferencias.append(TransferenciaFinancieraInfo(
            ambito=r.get("Ambito") or r.get("ambito"),
            entidad_origen=(
                r.get("EntidadOrigen") or r.get("UnidadEjecutora")
                or r.get("NombreEntidad")
            ),
            monto=_to_float(r.get("MontoTransferencia") or r.get("Monto")),
            documento=r.get("DocumentoTransferencia") or r.get("Documento"),
        ))
    return transferencias


def _procesar_adelantos(raw_list: list[dict]) -> list[AdelantoInfo]:
    """Convierte la lista cruda de lAdelanto a AdelantoInfo (garantias de adelanto)."""
    adelantos = []
    for r in raw_list:
        adelantos.append(AdelantoInfo(
            tipo=r.get("TipoGarantia") or r.get("TipoAdelanto") or r.get("Tipo"),
            monto=_to_float(
                r.get("MontoGarantia") or r.get("MontoAdelanto") or r.get("Monto")
            ),
            fecha_entrega=_parse_fecha_ddmmyyyy(
                r.get("FechaEntrega") or r.get("FechaDesembolso")
            ),
            documento_aprobacion=(
                r.get("DocumentoAprobacion") or r.get("Documento")
            ),
        ))
    return adelantos


def _procesar_cronogramas(raw_list: list[dict]) -> list[CronogramaInfo]:
    """Convierte la lista cruda de lCronograma a CronogramaInfo."""
    cronogramas = []
    for r in raw_list:
        cronogramas.append(CronogramaInfo(
            tipo=r.get("TipoCronograma") or r.get("Tipo"),
            fecha_aprobacion=_parse_fecha_ddmmyyyy(
                r.get("FechaAprobacion") or r.get("FechaAprob")
            ),
            documento=r.get("DocumentoAprobacion") or r.get("Documento"),
            nueva_fecha_termino=_parse_fecha_ddmmyyyy(
                r.get("NuevaFechaTermino") or r.get("FechaTermino")
            ),
        ))
    return cronogramas


def _procesar_adicionales_deductivos(raw_list: list[dict]) -> list[AdicionalDeductivoInfo]:
    """Convierte la lista cruda de lAdicionalDeduc."""
    items = []
    for r in raw_list:
        items.append(AdicionalDeductivoInfo(
            numero=str(
                r.get("NumeroAdicional") or r.get("Numero") or ""
            ).strip() or None,
            tipo=r.get("Tipo") or r.get("TipoAdicional"),
            subtipo=r.get("Subtipo") or r.get("SubTipo"),
            causal=r.get("Causal"),
            fecha_aprobacion=_parse_fecha_ddmmyyyy(
                r.get("FechaAprobacion") or r.get("FechaAprob")
            ),
            porcentaje=_to_float(r.get("Porcentaje") or r.get("PctAprobado")),
            monto=_to_float(r.get("MontoAprobado") or r.get("Monto")),
            documento=r.get("DocumentoAprobacion") or r.get("Documento"),
        ))
    return items


def _procesar_controversias(raw_list: list[dict]) -> list[ControversiaInfo]:
    """Convierte la lista cruda de lControversia a ControversiaInfo."""
    controversias = []
    for r in raw_list:
        controversias.append(ControversiaInfo(
            mecanismo=(
                r.get("MecanismoSolucion") or r.get("Mecanismo")
                or r.get("TipoControversia")
            ),
            estado=r.get("Estado") or r.get("EstadoControversia"),
            fecha_inicio=_parse_fecha_ddmmyyyy(
                r.get("FechaInicio") or r.get("FechaInicioProceso")
            ),
            fecha_fin=_parse_fecha_ddmmyyyy(
                r.get("FechaFin") or r.get("FechaFinProceso")
            ),
            documento=r.get("DocumentoSustento") or r.get("Documento"),
        ))
    return controversias


def _derivar_avance_actual(
    avances: list[AvanceMensual],
) -> tuple[Optional[float], Optional[float]]:
    """
    Toma el avance mas reciente con datos fisicos/financieros y devuelve
    (porcentaje_avance_fisico_real, monto_ejecutado_acumulado).

    Asume que la lista viene ordenada de mas reciente a mas antiguo
    (que es como InfoObras la entrega).
    """
    pct = None
    monto = None
    for av in avances:
        if pct is None and av.avance_fisico_real is not None:
            pct = av.avance_fisico_real
        if monto is None and av.monto_ejecucion_financiera is not None:
            monto = av.monto_ejecucion_financiera
        if pct is not None and monto is not None:
            break
    return pct, monto


def _extraer_periodos_suspension(avances: list[AvanceMensual]) -> list[tuple[date, date]]:
    """
    Extrae periodos continuos de paralización/suspensión desde los avances.

    Agrupa meses consecutivos con estado "Paralizado" en un solo periodo.
    """
    periodos: list[tuple[date, date]] = []
    inicio_actual: Optional[date] = None
    fin_actual: Optional[date] = None

    for av in sorted(avances, key=lambda a: (a.anio, a.mes)):
        if "paraliz" in av.estado.lower() or "suspend" in av.estado.lower():
            # Inicio del mes
            if av.anio and av.mes:
                mes_inicio = date(av.anio, av.mes, 1)
                # Fin del mes (aprox)
                if av.mes == 12:
                    mes_fin = date(av.anio, 12, 31)
                else:
                    mes_fin = date(av.anio, av.mes + 1, 1)

                # Si hay fecha exacta de paralización, usarla como inicio
                if av.fecha_paralizacion:
                    mes_inicio = av.fecha_paralizacion

                if inicio_actual is None:
                    inicio_actual = mes_inicio
                    fin_actual = mes_fin
                else:
                    # ¿Es continuación del periodo actual?
                    if mes_inicio <= fin_actual or (mes_inicio - fin_actual).days <= 31:
                        fin_actual = max(fin_actual, mes_fin)
                    else:
                        periodos.append((inicio_actual, fin_actual))
                        inicio_actual = mes_inicio
                        fin_actual = mes_fin
        else:
            # Mes activo → cerrar periodo si hay uno abierto
            if inicio_actual is not None:
                periodos.append((inicio_actual, fin_actual))
                inicio_actual = None
                fin_actual = None

    # Cerrar último periodo si quedó abierto
    if inicio_actual is not None:
        periodos.append((inicio_actual, fin_actual))

    return periodos


def _huecos_de_valorizacion(avances: list[AvanceMensual]) -> list[tuple[date, date]]:
    """Periodos SIN valorización: meses ausentes en la serie de avances.

    Si InfoObras tiene valorización hasta dic-2017 y la siguiente es abr-2018,
    los meses ene/feb/mar-2018 NO existen como filas → la obra estuvo parada,
    aunque NINGUNA fila diga 'Paralizado'. El postor cuenta ese tramo como
    experiencia; en realidad no vale (hallazgo reunión 2026-06-07).

    Devuelve (primer día del primer mes ausente, último día del último ausente).
    """
    meses = sorted({(a.anio, a.mes) for a in avances if a.anio and a.mes})
    huecos: list[tuple[date, date]] = []
    for (a1, m1), (a2, m2) in zip(meses, meses[1:]):
        sig_y, sig_m = (a1, m1 + 1) if m1 < 12 else (a1 + 1, 1)
        if (sig_y, sig_m) == (a2, m2):
            continue  # meses consecutivos: no hay hueco
        inicio = date(sig_y, sig_m, 1)
        fin = date(a2, m2, 1) - timedelta(days=1)  # último día del mes previo a la reanudación
        if fin >= inicio:
            huecos.append((inicio, fin))
    return huecos


def periodos_inactividad(avances: list[AvanceMensual]) -> list[dict]:
    """TODOS los periodos en que la obra NO avanzó, cada uno con su tipo:
      - 'paralizado'        → meses con estado 'Paralizado'/'Suspendido'
      - 'sin_valorizacion'  → huecos: meses ausentes entre valorizaciones
    Ambos se descuentan igual de la experiencia; el tipo es para el reporte.
    Cada dict: {'inicio': date, 'fin': date, 'tipo': str}. Ordenados por inicio.
    """
    out: list[dict] = []
    for a, b in _extraer_periodos_suspension(avances):
        out.append({"inicio": a, "fin": b, "tipo": "paralizado"})
    for a, b in _huecos_de_valorizacion(avances):
        out.append({"inicio": a, "fin": b, "tipo": "sin_valorizacion"})
    out.sort(key=lambda p: p["inicio"])
    return out


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def _estado_obra(o: dict) -> str:
    return (o.get("estObra") or o.get("estadoObra") or "").strip().upper()


def _ventana_obra(
    o: dict,
    rango_valorizaciones: Optional[Callable[[object], tuple]] = None,
) -> tuple[Optional[date], Optional[date]]:
    """Ventana REAL de actividad de una obra. Las valorizaciones son la verdad:
    si están disponibles, ESE es el rango (la obra solo avanzó esos meses). La
    cabecera (fechaIniObra/fechaFinObra) miente en AMBOS sentidos y solo sirve de
    fallback cuando no hay valorizaciones:
      - 133630/33900: cabecera fin 2015-02, pero valoriza hasta 2016-07 (corta).
      - 2192844/41414: cabecera fin 2019-07, pero valoriza solo hasta 2017-03
        (larga) → un max(cabecera, valoriz) le daba un solape FALSO con el
        certificado 2018-2019 y le robaba el match a la obra 83130 que sí cubre.
    """
    if rango_valorizaciones:
        vi, vf = rango_valorizaciones(o.get("codigoObra"))
        if vi and vf:
            return vi, vf
    oi = _parse_timestamp_json(o.get("fechaIniObra"))
    of = _parse_timestamp_json(o.get("fechaFinObra")) or oi
    return oi, of


def coincide_codigo(o: dict, codigo: str) -> bool:
    """¿El registro corresponde EXACTAMENTE al código buscado? La búsqueda de
    InfoObras hace match por substring sobre `codSnip`: buscar '95555' trae
    '2595555' (obra ajena). Solo es válido si el código coincide exacto con el
    SNIP (`codSnip`) o con el CUI único (`codUniqInv`)."""
    codigo = str(codigo or "").strip()
    if not codigo:
        return True  # sin código que comparar → no filtrar
    return any(str(o.get(c) or "").strip() == codigo for c in ("codSnip", "codUniqInv"))


def _cod_obra(o: dict) -> int:
    """Desempate DETERMINÍSTICO entre obras del mismo CUI: el orden que devuelve
    el portal NO es estable entre corridas, así que se rompe por menor codigoObra
    (cae a obraId, luego 0)."""
    try:
        return int(o.get("codigoObra") or o.get("obraId") or 0)
    except (TypeError, ValueError):
        return 0


def seleccionar_obra(
    obras: list[dict],
    cert_inicio: Optional[date] = None,
    cert_fin: Optional[date] = None,
    rango_valorizaciones: Optional[Callable[[object], tuple]] = None,
) -> Optional[dict]:
    """Elige la obra correcta cuando un CUI devuelve varias (caso real: CUI con
    varios registros: ejecución, contingencia, supervisión, re-registros).

    Sin fechas del certificado: compat — finalizada primero, luego la primera.

    Con fechas del certificado [cert_inicio, cert_fin]:
      P1. Si alguna obra SOLAPA (días de solape > 0) la ventana real de
          valorizaciones con el certificado, solo se consideran esas, ordenadas
          por mayor solape (FINALIZADA como desempate).
      P2. Si NINGUNA solapa, se ordenan TODAS por cercanía del inicio de su
          ventana al inicio del certificado (sin excluir las no finalizadas:
          el caso Egoavil 66057 es una obra paralizada que debe ganarle a una
          contingencia finalizada antigua). FINALIZADA como desempate.

    La ventana se mide sobre `_ventana_obra` (cabecera + rango de valorizaciones
    si `rango_valorizaciones` lo provee; inyectable y perezoso).
    """
    if not obras:
        return None
    if len(obras) == 1:
        return obras[0]

    if not (cert_inicio and cert_fin):
        finalizadas = [o for o in obras if "FINALIZAD" in _estado_obra(o)]
        # determinístico también sin fechas: menor codigoObra (el orden del
        # portal no es estable entre corridas).
        return min(finalizadas or obras, key=_cod_obra)

    def _fin(o: dict) -> int:
        return 1 if "FINALIZAD" in _estado_obra(o) else 0

    _cod = _cod_obra  # mismo desempate determinístico (menor codigoObra)

    # P1 · obras con solape positivo: mayor solape, finalizada, menor codigoObra
    con_solape: list[tuple[dict, int]] = []
    for o in obras:
        oi, of = _ventana_obra(o, rango_valorizaciones)
        if not oi:
            continue
        dias = (min(of, cert_fin) - max(oi, cert_inicio)).days
        if dias > 0:
            con_solape.append((o, dias))
    if con_solape:
        con_solape.sort(key=lambda od: (od[1], _fin(od[0]), -_cod(od[0])), reverse=True)
        return con_solape[0][0]

    # P2 · nadie solapa → la ventana más cercana al inicio del certificado
    def _dist(o: dict) -> int:
        oi, _ = _ventana_obra(o, rango_valorizaciones)
        return abs((oi - cert_inicio).days) if oi else 10 ** 9

    return sorted(obras, key=lambda o: (_dist(o), -_fin(o), _cod(o)))[0]


def elegir_obra_raw(
    obras: list[dict],
    cert_inicio: Optional[date],
    cert_fin: Optional[date],
    obra_id: Optional[int],
    rango_valorizaciones: Optional[Callable[[object], tuple]] = None,
) -> Optional[dict]:
    """Elige el registro de obra. Respeta el bypass por `obra_id` (la obra que
    eligió el resolver por nombre/RUC) SOLO si esa obra cubre el certificado; si
    no cubre —o no se pasó obra_id— delega en `seleccionar_obra` (solape real).

    El resolver puede caer en una obra con 0% de solape: Valdizán por nombre
    idéntico (33900 vs 71173), o re-registros del mismo CUI. La validación por
    cobertura evita que el bypass fuerce una obra equivocada. Sin fechas del
    certificado no hay con qué validar → se respeta el bypass."""
    if not obras:
        return None
    if obra_id:
        cand = next((o for o in obras
                     if (o.get("codigoObra") or o.get("obraId")) == obra_id), None)
        if cand is not None:
            if not (cert_inicio and cert_fin):
                return cand  # sin fechas no se puede validar → respetar bypass
            oi, of = _ventana_obra(cand, rango_valorizaciones)
            if oi and (min(of, cert_fin) - max(oi, cert_inicio)).days > 0:
                return cand  # cubre el certificado → respetar bypass
            # no cubre → cae a selección por solape (puede haber un hermano que sí)
    return seleccionar_obra(obras, cert_inicio, cert_fin, rango_valorizaciones)


# ── Aprobación del EXPEDIENTE técnico (página Mapa/Sumario) ───────────────────
# El hito "Aprobación del proyecto" de la Línea de tiempo tiene un botón de descarga
# cuyo filename empieza por 'expediente/'. Mismo mecanismo data-download-url →
# /Mapa/DownloadFile que DatosEjecucion. Solo se consulta para obras SIN valorizaciones
# (posible experiencia de expediente). OJO: validar en vivo que los <button
# data-download-url> vengan en el HTML del servidor (no pintados por JS).
_SUMARIO = BASE_WEB + "/Mapa/Sumario"
_RE_DL_URL = re.compile(r'data-download-url="([^"]+)"')
_RE_APROB_PROY = re.compile(r"Aprobaci[oó]n\s+del\s+proyecto", re.I)


def _url_a_item(raw: str) -> Optional[dict]:
    """data-download-url → {url, filename, nombre, extension, fecha}. Des-escapa
    &amp;, decodifica %2F/%20/%C2%B0 (unquote) y parte el query."""
    raw = (raw or "").replace("&amp;", "&")
    qs = parse_qs(urlsplit(unquote(raw)).query)
    filename = (qs.get("filename", [""])[0] or "").strip()
    if not filename:
        return None
    base = filename.rsplit("/", 1)[-1]
    nombre = (qs.get("name", [""])[0] or "").strip() or base
    ext = ((qs.get("extension", [""])[0] or "").lstrip(".")
           or (base.rsplit(".", 1)[-1] if "." in base else "") or "pdf")
    url = raw if raw.lower().startswith("http") else BASE_WEB.rsplit("/InfobrasWeb", 1)[0] + raw
    fecha = None
    m = re.search(r"(20\d{2})(\d{2})(\d{2})\d*", filename)   # documentoYYYYMMDD… → fecha
    if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
        fecha = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", nombre)
        if m:
            fecha = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return {"url": url, "filename": filename, "nombre": nombre, "extension": ext, "fecha": fecha}


def parsear_aprobacion_expediente(html: str) -> Optional[dict]:
    """Del HTML de Mapa/Sumario extrae el documento del hito 'Aprobación del proyecto':
    {url, filename, nombre, extension, fecha} | None. Vía (a): el botón más cercano al
    rótulo 'Aprobación del proyecto'. Vía (b) fallback: filename que empieza en
    'expediente/' o nombre tipo resolución de aprobación."""
    if not html:
        return None
    m = _RE_APROB_PROY.search(html)
    if m:
        ventana = html[max(0, m.start() - 4000): m.end() + 4000]
        cands = sorted(_RE_DL_URL.findall(ventana),
                       key=lambda u: 0 if "expediente" in u.lower() else 1)
        for raw in cands:
            it = _url_a_item(raw)
            if it:
                return it
    mejor = None
    for raw in _RE_DL_URL.findall(html):
        it = _url_a_item(raw)
        if not it:
            continue
        fn, nom = it["filename"].lower(), it["nombre"].lower()
        if fn.startswith("expediente/") or fn.startswith("expediente\\"):
            return it
        if re.search(r"aprob|res(oluci[oó]n)?\.?\s*gerenc", nom):
            mejor = mejor or it
    return mejor


def _fetch_aprobacion_expediente(session: requests.Session, obra_id) -> Optional[dict]:
    """GET Mapa/Sumario?obraId= → parsea la 'Aprobación del proyecto'. Best-effort:
    si el portal falla o no hay hito, devuelve None (la experiencia cae a revisión)."""
    try:
        r = session.get(_SUMARIO, params={"obraId": obra_id}, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        logger.debug("InfoObras Sumario obra %s: %s", obra_id, corto(e))
        return None
    return parsear_aprobacion_expediente(r.text)


def fetch_by_cui(
    cui: str,
    cert_inicio: Optional[date] = None,
    cert_fin: Optional[date] = None,
    obra_id: Optional[int] = None,
) -> Optional[WorkInfo]:
    """
    Consulta InfoObras por CUI y retorna datos completos de la obra.

    Ejecuta 2 requests:
      1. Búsqueda por CUI → obtiene obra_id + datos básicos
      2. DatosEjecucion → avances, supervisores, residentes, paralizaciones

    Retorna None si no se encuentra la obra.
    """
    try:
        session = _crear_session()

        # [1] Buscar por CUI
        logger.info("InfoObras: buscando CUI %s", cui)
        obras = _buscar_por_cui(session, cui)

        if not obras:
            logger.info("InfoObras: CUI %s no encontrado", cui)
            return None

        # Rango real de valorizaciones por obra (perezoso, con cache). El solape
        # se mide sobre la ventana real (las fechas de cabecera mienten: caso
        # 133630/33900). Sirve para validar el bypass Y para seleccionar_obra.
        _cache_rango: dict[object, tuple] = {}

        def _rango_val(oid):
            if oid in _cache_rango:
                return _cache_rango[oid]
            rango = (None, None)
            try:
                avs = _procesar_avances(
                    _extraer_datos_ejecucion(session, oid).get("lAvances", []))
                meses = [date(a.anio, a.mes, 1) for a in avs
                         if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
                if meses:
                    rango = (min(meses), max(meses))
            except Exception as e:  # noqa: BLE001 — portal intermitente
                logger.debug("InfoObras: rango valorizaciones ObraId %s: %s", oid, corto(e))
            _cache_rango[oid] = rango
            return rango

        # Un CUI puede traer varias obras (ejecución, contingencia, supervisión,
        # re-registros). Se respeta el bypass por obra_id del resolver solo si esa
        # obra cubre el certificado; si no, se elige por solape real.
        if len(obras) > 1:
            logger.info(
                "InfoObras: CUI %s devolvió %d obras (estados: %s) — seleccionando",
                cui, len(obras),
                ", ".join(sorted({_estado_obra(o) or "?" for o in obras})),
            )
        obra_id_req = obra_id  # el obra_id que pidió el resolver (para el reintento)
        obra_raw = elegir_obra_raw(obras, cert_inicio, cert_fin, obra_id, _rango_val)
        obra_id = obra_raw.get("codigoObra")

        # InfoObras a veces devuelve la obra sin codigoObra en el 1er request
        # (warmup de session). Reintentar 1 vez con un pequeno delay — respetando
        # el mismo bypass-validado-por-cobertura que la ruta normal.
        if not obra_id:
            logger.info(
                "InfoObras: 1er request sin codigoObra para CUI %s, reintentando", cui)
            time.sleep(2.0)
            obras_retry = _buscar_por_cui(session, cui)
            if obras_retry:
                obra_raw = elegir_obra_raw(obras_retry, cert_inicio, cert_fin, obra_id_req, _rango_val)
                obra_id = obra_raw.get("codigoObra")

        if not obra_id:
            logger.warning(
                "InfoObras: obra sin codigoObra para CUI %s tras reintento", cui,
            )
            return None

        logger.info(
            "InfoObras: CUI %s → ObraId %s — %s",
            cui, obra_id, obra_raw.get("nombrObra", "")[:60],
        )

        time.sleep(_DELAY)

        # [5+4] Datos de ejecución + Datos de preparación.
        # Mergeamos ambos endpoints: ejecucion trae lAvances (+ otras en
        # plantilla vieja); preparacion trae lSupervisor, lResidente,
        # lPersonal, lRevisionET (criticos para obras nuevas tipo PRONIS
        # donde DatosEjecucion solo expone lAvances).
        logger.info("InfoObras: descargando DatosEjecucion+Preparacion ObraId %s", obra_id)
        datos = _extraer_todos_los_datos(session, obra_id)

        # Procesar datos
        supervisores = _procesar_supervisores(datos.get("lSupervisor", []))
        residentes = _procesar_residentes(datos.get("lResidente", []))
        avances = _procesar_avances(datos.get("lAvances", []))
        contratistas = _procesar_contratistas(datos.get("lContratista", []))
        # Fallback: si el array embebido viene vacio pero el endpoint de
        # busqueda trae nombreEjecutor + rucEjecutor, sintetizar 1 entrada.
        if not contratistas:
            sint = _sintetizar_contratista_de_busqueda(obra_raw)
            if sint:
                contratistas = [sint]
                logger.info(
                    "InfoObras: lContratista vacio, sintetizado desde busqueda: %s",
                    sint.nombre_empresa,
                )
        modificaciones_plazo = (_procesar_modificaciones_plazo(datos.get("lModificacionPlazo", [])) or datos.get("_modificaciones_plazo", []))
        entregas_terreno = _procesar_entregas_terreno(datos.get("lEntregaTerreno", []))
        adendas = _procesar_adendas(datos.get("lAdenda", []))
        transferencias = _procesar_transferencias(datos.get("lTransferenciaFinanciera", []))
        adelantos = _procesar_adelantos(datos.get("lAdelanto", []))
        cronogramas = _procesar_cronogramas(datos.get("lCronograma", []))
        adicionales_deductivos = _procesar_adicionales_deductivos(datos.get("lAdicionalDeduc", []))
        controversias = _procesar_controversias(datos.get("lControversia", []))
        suspension_periods = _extraer_periodos_suspension(avances)

        # Cabecera derivada del avance mas reciente con avance fisico real
        avance_pct_real, monto_ejecutado = _derivar_avance_actual(avances)

        logger.info(
            "InfoObras: ObraId %s — %d avances (%.2f%% real), %d sup, %d res, "
            "%d cont, %d modPlazo, %d terreno, %d adendas, %d transf, "
            "%d adelantos, %d cron, %d adic/deduc, %d contr, %d susp",
            obra_id, len(avances), avance_pct_real or 0.0,
            len(supervisores), len(residentes), len(contratistas),
            len(modificaciones_plazo), len(entregas_terreno), len(adendas),
            len(transferencias), len(adelantos), len(cronogramas),
            len(adicionales_deductivos), len(controversias), len(suspension_periods),
        )

        # Obra SIN valorizaciones → puede ser una experiencia de EXPEDIENTE técnico.
        # Buscar el hito "Aprobación del proyecto" en Mapa/Sumario (best-effort; None si
        # no hay o el portal falla). La decisión de ACEPTARLA la toma el orquestador y
        # solo si la experiencia es de expediente (por nombre).
        aprobacion_exp = _fetch_aprobacion_expediente(session, obra_id) if not avances else None

        return WorkInfo(
            cui=cui,
            obra_id=obra_id,
            nombre=obra_raw.get("nombrObra"),
            estado=obra_raw.get("estObra"),
            tipo_obra=obra_raw.get("nomTipoObra"),
            entidad=obra_raw.get("nombreEntidad"),
            ejecutor=obra_raw.get("nombreEjecutor"),
            ruc_ejecutor=obra_raw.get("rucEjecutor"),
            monto_contrato=obra_raw.get("montoObraSoles"),
            fecha_inicio=_parse_timestamp_json(obra_raw.get("fechaIniObra")),
            fecha_fin=_parse_timestamp_json(obra_raw.get("fechaFinObra")),
            plazo_dias=obra_raw.get("plazoObra"),
            # El "Código InfoObras" de la ficha es `codigoObra` (= obra_id); la
            # búsqueda no trae ninguna clave `codigo(I|i)nfobras`. Verificado en
            # vivo con el CUI 133630 (devolvía None → Excel mostraba "—").
            codigo_infoobras=str(obra_id).strip() or None,
            porcentaje_avance_fisico=avance_pct_real,
            monto_ejecutado_acumulado=monto_ejecutado,
            supervisores=supervisores,
            residentes=residentes,
            avances=avances,
            contratistas=contratistas,
            modificaciones_plazo=modificaciones_plazo,
            entregas_terreno=entregas_terreno,
            suspension_periods=suspension_periods,
            adendas=adendas,
            transferencias=transferencias,
            adelantos=adelantos,
            cronogramas=cronogramas,
            adicionales_deductivos=adicionales_deductivos,
            controversias=controversias,
            raw_busqueda=obra_raw,
            aprobacion_expediente=aprobacion_exp,
        )

    except requests.RequestException as e:
        logger.warning("InfoObras: CUI %s no resuelto — %s", cui, corto(e))
        return None
    except Exception as e:
        logger.exception("InfoObras: error inesperado para CUI %s", cui)
        return None


def sondear(timeout: float = 6.0) -> tuple[bool, Optional[str]]:
    """Sondeo LIGERO de disponibilidad de InfoObras para /salud. Reusa el warmup
    de session (que ya hace un GET a BASE_WEB) + un GET al mapa. Nunca lanza."""
    try:
        s = _crear_session()
        try:
            r = s.get(f"{BASE_WEB}/Mapa/Index", timeout=timeout)
            return (True, None) if r.status_code < 400 else (False, f"HTTP {r.status_code}")
        finally:
            s.close()
    except Exception:  # noqa: BLE001 — el warmup puede fallar si el portal cae
        return False, "sin conexion"
