"""
Lectura de la RESOLUCIÓN QUE APROBÓ EL EXPEDIENTE TÉCNICO (Formato 08-A del MEF).

Qué es: cuando la consultora termina el expediente, la entidad lo aprueba con
una resolución (gerencial, de alcaldía, jefatural) que sube al Banco de
Inversiones. Es un documento oficial que dice qué expediente aprueba, cuándo y,
muchas veces, quién lo elaboró.

Qué se extrae (medido sobre una corrida real de expedientes, 5-sep-2026):
  · la FECHA de la resolución — la traen todas las legibles; es la fecha oficial
    de aprobación que la Regla B (término declarado ≤ aprobación) no tenía;
  · el/los CONSULTORES que nombra — y si alguno es el emisor del certificado
    (confirma), es otro (nombra_otro: evidencia negativa útil) o no nombra a nadie;
  · si cita el CUI.

Trampas que esta implementación evita (todas vistas en la medición):
  · los consorcios se llaman como el LUGAR de la obra («Consorcio Santiago» vs
    «distrito de Santiago»): se compara el nombre COMPLETO como frase, nunca por
    palabras sueltas;
  · el OCR deforma símbolos («&» → «8», «$:»): se normaliza antes de comparar;
  · el nombre puede ir ANTES del rol («MENDOZA & TAPIA S.A.C. - ENTIDAD PRIVADA
    SUPERVISORA»): se mira la ventana a ambos lados del rol;
  · un CUI puede tener varios expedientes (original, saldo de obra): la fecha se
    entrega como dato; el contraste con el periodo lo hace la Regla B, que ya
    se abstiene ante incoherencias;
  · la fecha del encabezado puede ser IMPOSIBLE (una resolución «…-2025» leída
    con fecha 22/03/2011, porque el OCR tomó una fecha citada en el cuerpo):
    `plausibilidad_fecha` la descarta contra el año del número, la firma del
    contrato y el día de hoy, y se sigue con la siguiente candidata; si ninguna
    sirve, `fecha` va en None y el motivo queda en `fecha_motivo` (mejor sin
    fecha que con una que dispare una alerta roja falsa de miles de días).

Funciones PURAS salvo `leer_resolucion`, que descarga y lee (red + OCR) con
descargador y extractor inyectables para los tests.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SETIEMBRE": 9, "SEPTIEMBRE": 9, "OCTUBRE": 10,
         "NOVIEMBRE": 11, "DICIEMBRE": 12}
_RE_FECHA_LARGA = re.compile(
    r"\b(\d{1,2})\s+DE\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SETIEMBRE|"
    r"SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE(?:L)?\s+(\d{4})\b")
_RE_FECHA_CORTA = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
# Año declarado por el número de la resolución: «274-2019-GRH/GR» → 2019;
# si no hay año de 4 cifras, un segmento de 2 («123-25-GM» → 2025).
_RE_ANIO_4 = re.compile(r"\b(19\d{2}|20\d{2})\b")
_RE_ANIO_2 = re.compile(r"-(\d{2})(?=$|[^0-9])")
_RE_SUFIJO_LEGAL = re.compile(
    r"\b(S\.?\s?A\.?\s?C\.?|S\.?\s?A\.?|E\.?\s?I\.?\s?R\.?\s?L\.?|S\.?\s?R\.?\s?L\.?|"
    r"SOCIEDAD ANONIMA CERRADA|SOCIEDAD ANONIMA|EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA)\b\.?")
# Roles que preceden (o siguen) al nombre de quien elaboró/supervisó el expediente.
_ROLES = (r"CONSULTOR(?:A|IA)?(?:\s+DE\s+OBRA)?|CONTRATISTA|PROYECTISTA|ELABORAD[OA]\s+POR|"
          r"ENTIDAD\s+PRIVADA\s+SUPERVISORA|EMPRESA\s+PRIVADA|A\s+FAVOR\s+DE(?:L|\s+LA)?|"
          r"SUSCRITO\s+CON|SUSCRIBIO\s+EL\s+CONTRATO\s+CON")
_RE_ROL = re.compile(rf"\b({_ROLES})\b")
# Roles tras los que el texto escribe un NOMBRE («el consultor X», «a favor del
# contratista Y»). «Entidad privada supervisora» y «empresa privada» quedan fuera
# de esta lista: en resoluciones de obras por impuestos son términos genéricos
# seguidos de oración, y capturaban verbos como nombres.
_ROLES_CON_NOMBRE = (r"CONSULTOR(?:A|IA)?(?:\s+DE\s+OBRA)?|CONTRATISTA|PROYECTISTA|"
                     r"ELABORAD[OA]\s+POR|A\s+FAVOR\s+DE(?:L|\s+LA)?|SUSCRIBIO\s+EL\s+CONTRATO\s+CON")
_ARTICULOS = r"(?:EL|LA|LOS|LAS|DEL|DE\s+LA|EMPRESA|ING\.?|ARQ\.?|SR\.?|SRA\.?|CONSULTOR(?:A)?)?\s*"
_RE_NOMBRE_TRAS_ROL = re.compile(
    rf"\b(?:{_ROLES_CON_NOMBRE})\s*[:,*\"]?\s*{_ARTICULOS}"
    r"([A-Z][A-Z0-9 .&+\-]{3,90}?)(?=\s*[,;()\"*]|\s+(?:QUE|CON|PARA|POR|MEDIANTE|SEGUN|EN|Y|DEL|DE|"
    r"CELEBRAN|SUSCRIBEN|SUSCRIBIO|REMITE|PRESENTA|SOLICITA|COMUNICA|INFORMA|EL|LA)\s|$)")
_RE_NOMBRE_ANTES_ROL = re.compile(
    r"([A-Z][A-Z0-9 .&+\-]{3,80}?)\s*[-–,]?\s*(?:ENTIDAD\s+PRIVADA\s+SUPERVISORA|"
    r"COMO\s+CONSULTOR(?:A)?|EN\s+CALIDAD\s+DE\s+CONSULTOR(?:A)?)")
_GENERICOS = {"OBRA", "PARA", "ELABORACION", "EXPEDIENTE", "TECNICO", "SERVICIO",
              "CONSULTORIA", "PROYECTO", "INVERSION", "ENTIDAD", "UNIDAD", "ESPECIALISTA",
              "RESPONSABLE", "OFICINA", "GERENCIA", "SUPERVISION", "EJECUCION", "PUBLICA",
              "PRIVADA", "DE", "LA", "EL", "DEL", "LOS", "LAS", "QUE", "REPRESENTANTE",
              "LEGAL", "COMUN", "SUPERVISOR", "SUPERVISORA", "CONTRATO", "FINANCIA",
              "EMPRESA", "CONSULTOR", "CONSULTORA", "CONTRATISTA", "PROYECTISTA",
              "CUANDO", "ASI", "HAYA", "DETERMINADO", "MEDIANTE", "SEGUN", "DICHO", "DICHA",
              # verbos y conectores que el texto pone justo después del rol
              "TRASLADA", "CUMPLIRA", "CUMPLE", "REMITE", "REMITEN", "PRESENTA", "PRESENTO",
              "SOLICITA", "COMUNICA", "INFORMA", "SUSCRIBE", "APRUEBA", "DECLARA", "DISPONE",
              "RESUELVE", "OTORGA", "SENALA", "INDICA", "ADJUNTA", "DESIGNADO", "DESIGNADA",
              "ARTICULO", "REALIZA", "EJECUTA", "ELABORA", "ELABORO", "EMITE", "DEBERA", "DEBE",
              "PUEDE", "SALVO", "CASOS", "EQUIPO", "EVALUADOR", "EXTREMOS", "IMPREVISIBLE",
              "IMPREVISIBLES", "PARTE", "TRAVES", "EFECTOS", "CONFORME", "PLAZO", "DIAS"}
_SUFIJO_EMPRESA = re.compile(r"\b(S\s?A\s?C|S\s?A|E\s?I\s?R\s?L|S\s?R\s?L|CONSORCIO|CIA|LTDA|CORPORATION|INC)\b")


def _plausible_nombre(n: str) -> bool:
    """¿Parece una razón social o una persona, y no un pedazo de oración? Exige
    sufijo legal/consorcio o al menos dos palabras con contenido, y que la
    primera palabra no sea un conector ni un verbo."""
    toks = [t for t in re.split(r"[^A-Z0-9]+", n) if t]
    if not toks or toks[0] in _GENERICOS or len(toks[0]) < 2:
        return False
    if re.search(r"\.\s+[A-Z]{3,}", n):        # «… CULMINADOS. LA SUPERVISION …» = otra oración
        return False
    if any(t in _PROSA for t in toks):          # una razón social no lleva verbos ni pronombres
        return False
    contenido = [t for t in toks if t not in _GENERICOS and len(t) >= 3]
    return bool(_SUFIJO_EMPRESA.search(n)) or len(contenido) >= 2


# Palabras de oración que NO aparecen dentro de una razón social ni de un nombre
# de persona: si el fragmento capturado las trae, es prosa, no un nombre.
_PROSA = {"SE", "QUE", "REQUIERE", "PREVIAMENTE", "OPINION", "FAVORABLE", "PARA", "CON",
          "POR", "SUS", "SU", "ESTE", "ESTA", "ESTOS", "ESTAS", "DONDE", "CUAL", "CUALES",
          "SERA", "SERAN", "HA", "HAN", "SIDO", "SER", "ESTAR", "FUE", "FUERON", "TIENE",
          "TIENEN", "TENDRA", "HACE", "HACER", "ANTE", "BAJO", "SOBRE", "TRAS", "ENTRE",
          "MISMO", "MISMA", "CADA", "TODO", "TODA", "TODOS", "TODAS", "ASIMISMO", "ADEMAS",
          "TAMBIEN", "LUEGO", "ENTONCES", "SIN", "COMO", "CUANDO", "PORQUE", "AUNQUE"}
UMBRAL_FRASE = 88          # parecido mínimo del nombre COMPLETO dentro de la ventana
VENTANA_ROL = 140          # caracteres a cada lado de un rol donde buscar el nombre


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().upper()
    # ruido típico del OCR en razones sociales
    t = t.replace("$:", " ").replace("&", " ").replace("+", " ").replace(" 8 ", " ")
    return re.sub(r"\s+", " ", t).strip()


def limpiar_razon_social(nombre: str) -> str:
    """Nombre comparable: sin sufijos legales ni símbolos; «CONSORCIO» se conserva
    porque distingue al consorcio del topónimo homónimo."""
    t = _RE_SUFIJO_LEGAL.sub(" ", normalizar(nombre))
    t = re.sub(r"[^A-Z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def fechas_en_texto(T: str) -> list[tuple[int, date]]:
    """Todas las fechas legibles con su posición, en orden de aparición."""
    out: list[tuple[int, date]] = []
    for m in _RE_FECHA_LARGA.finditer(T):
        try:
            out.append((m.start(), date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))))
        except ValueError:
            pass
    for m in _RE_FECHA_CORTA.finditer(T):
        try:
            out.append((m.start(), date(int(m.group(3)), int(m.group(2)), int(m.group(1)))))
        except ValueError:
            pass
    return sorted(out)


def _a_fecha(valor: Any) -> Optional[date]:
    """`date` desde un `date`, un `datetime` o un ISO («2025-04-29»). None si no."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (ValueError, TypeError):
        return None


def anio_de_numero(numero: str) -> Optional[int]:
    """Año que declara el número de una resolución («005401-2025-R/UNMSM» → 2025).

    Primero un año de 4 dígitos (19xx/20xx); si no hay, un segmento de 2 dígitos
    («-25-», «-25» al final) que se lee como 20YY solo cuando está entre 00 y 49
    («-75» sería un correlativo, no un año)."""
    n = normalizar(numero or "")
    m = _RE_ANIO_4.search(n)
    if m:
        return int(m.group(1))
    for m2 in _RE_ANIO_2.finditer(n):
        yy = int(m2.group(1))
        if 0 <= yy <= 49:
            return 2000 + yy
    return None


def plausibilidad_fecha(fecha: Any, *, numero: Optional[str] = None,
                        fecha_contrato: Any = None,
                        hoy: Any = None) -> tuple[bool, Optional[str]]:
    """¿Esa fecha puede ser la de ESTA resolución? `(plausible, motivo)`. Pura.

    Nació de dos lecturas reales imposibles: una resolución «…-2025» fechada en
    2011 (el OCR tomó una fecha citada en el cuerpo) y otra «…-2026» fechada en
    2025. Esas fechas alimentan la Regla B y produjeron una alerta roja falsa de
    miles de días, así que se descartan antes de publicarlas.

    Descarta cuando: el año no cuadra con el año del número (±1 año, porque una
    resolución de enero puede numerarse con el año anterior), la fecha es previa
    a la firma del contrato del expediente, es futura, o es anterior a
    Invierte.pe (2000). `motivo` es texto llano para el evaluador."""
    f = _a_fecha(fecha)
    if f is None:
        return False, "no hay una fecha legible"
    anio = anio_de_numero(numero) if numero else None
    # La numeración de resoluciones se reinicia cada año: una «002-2026» se emite en
    # 2026 (o en los días de cambio de año: diciembre anterior / enero siguiente).
    # Aceptar ±1 año completo dejaba pasar «002-2026» fechada 29/04/2025 (caso real).
    _anio_ok = (anio is None or f.year == anio
                or (f.year == anio - 1 and f.month == 12)
                or (f.year == anio + 1 and f.month == 1))
    if not _anio_ok:
        return False, ("el año de la fecha no corresponde al año del número de "
                       f"la resolución ({anio})")
    fc = _a_fecha(fecha_contrato)
    if fc is not None and f < fc:
        return False, ("la fecha es anterior a la firma del contrato del "
                       f"expediente ({fc.strftime('%d/%m/%Y')})")
    if f > (_a_fecha(hoy) or date.today()):
        return False, "la fecha es posterior a hoy"
    if f.year < 2000:
        return False, "fecha fuera del rango de Invierte.pe"
    return True, None


def _candidatas_encabezado(T: str) -> list[date]:
    """Fechas del encabezado en orden de preferencia: primero las que NO vienen
    precedidas de «DE FECHA» (esas citan otros documentos), después el resto de
    la ventana. Si el encabezado no trae ninguna, la primera del texto."""
    fechas = fechas_en_texto(T)
    if not fechas:
        return []
    propias, citadas = [], []
    for pos, f in fechas:
        if pos > 1500:
            break
        antes = T[max(0, pos - 14):pos]
        (citadas if ("DE FECHA" in antes or "FECHA " in antes) else propias).append(f)
    orden = propias + citadas
    return orden or [fechas[0][1]]


def _emision_con_traza(T: str, *, numero: Optional[str] = None,
                       fecha_contrato: Any = None
                       ) -> tuple[Optional[date], Optional[date], Optional[str]]:
    """`(fecha, fecha_descartada, motivo)`: la primera candidata PLAUSIBLE del
    encabezado y, si antes se descartó alguna, cuál fue y por qué."""
    descartada: Optional[date] = None
    motivo: Optional[str] = None
    for f in _candidatas_encabezado(T):
        ok, por_que = plausibilidad_fecha(f, numero=numero, fecha_contrato=fecha_contrato)
        if ok:
            return f, descartada, motivo
        if descartada is None:
            descartada, motivo = f, por_que
    return None, descartada, motivo


def fecha_emision(T: str, *, numero: Optional[str] = None,
                  fecha_contrato: Any = None) -> Optional[date]:
    """Fecha de la resolución: la primera del encabezado («Lima, 23 de mayo de
    2017») que NO venga precedida de «DE FECHA» (esas citan otros documentos).
    Si no hay ninguna así en las primeras 1.500 letras, la primera del texto.

    Con `numero` y/o `fecha_contrato` recorre esas candidatas en orden y devuelve
    la primera PLAUSIBLE (ver `plausibilidad_fecha`); None si ninguna lo es. Sin
    esos datos el comportamiento es el de siempre."""
    return _emision_con_traza(T, numero=numero, fecha_contrato=fecha_contrato)[0]


def consultores_nombrados(T: str) -> list[str]:
    """Nombres que el texto asocia a un rol de consultor/contratista/supervisor.
    Se descartan los que son solo palabras genéricas («…de obra para la…»)."""
    vistos: list[str] = []

    def _agregar(nombre: str) -> None:
        n = re.sub(r"\s+", " ", nombre).strip(" .,-*\"")
        # «CONTRATISTA JORGE …» (rol pegado al nombre) → quitar los genéricos iniciales
        toks = n.split(" ")
        while toks and toks[0] in _GENERICOS:
            toks.pop(0)
        n = " ".join(toks)
        if len(n) < 4 or not _plausible_nombre(n):
            return
        if all(fuzz.ratio(n, v) < 90 for v in vistos):
            vistos.append(n[:90])

    for m in _RE_NOMBRE_TRAS_ROL.finditer(T):
        _agregar(m.group(1))
    for m in _RE_NOMBRE_ANTES_ROL.finditer(T):
        _agregar(m.group(1))
    return vistos[:6]


def coincide_emisor(T: str, emisor: str) -> tuple[str, Optional[str]]:
    """`("confirma" | "nombra_otro" | "no_nombra", detalle)`.

    `confirma`: el nombre COMPLETO del emisor aparece (parecido ≥ UMBRAL_FRASE)
    en la ventana de algún rol. Por eso «CONSORCIO SANTIAGO» no confirma con
    «DISTRITO DE SANTIAGO»: la frase completa no se parece."""
    nombre = limpiar_razon_social(emisor)
    if len(nombre) < 6:
        return "no_nombra", None
    mejor, ventana_mejor = 0.0, None
    for m in _RE_ROL.finditer(T):
        ventana = T[max(0, m.start() - VENTANA_ROL): m.end() + VENTANA_ROL]
        ventana_cmp = re.sub(r"[^A-Z0-9 ]", " ", _RE_SUFIJO_LEGAL.sub(" ", ventana))
        sc = fuzz.partial_ratio(nombre, re.sub(r"\s+", " ", ventana_cmp))
        if sc > mejor:
            mejor, ventana_mejor = sc, ventana
    if mejor >= UMBRAL_FRASE:
        return "confirma", re.sub(r"\s+", " ", ventana_mejor or "")[:200]
    otros = consultores_nombrados(T)
    if otros:
        return "nombra_otro", "; ".join(otros[:3])
    return "no_nombra", None


def interpretar_resolucion(texto: str, emisor: str, cui: Optional[str] = None,
                           numero_citado: Optional[str] = None,
                           fecha_contrato: Any = None, *,
                           numero: Optional[str] = None) -> dict:
    """Interpreta el texto (capa u OCR) de una resolución de aprobación. Puro.

    `numero` (por defecto el `numero_citado`) y `fecha_contrato` solo se usan
    para descartar fechas imposibles (`plausibilidad_fecha`); si la fecha leída
    no es plausible, `fecha` queda en None y el motivo se publica en
    `fecha_descartada` / `fecha_motivo` para que el evaluador lo vea."""
    T = normalizar(texto)
    numero_ref = numero or numero_citado
    if len(T) < 200:
        return {"legible": False, "fecha": None, "consultores": [],
                "coincide_emisor": "sin_texto", "detalle_emisor": None,
                "cita_cui": False, "numero_citado_coincide": None,
                "fecha_descartada": None, "fecha_motivo": None,
                "resumen": "El documento no se pudo leer (escaneo sin texto reconocible)."}
    f, descartada, motivo = _emision_con_traza(T, numero=numero_ref,
                                               fecha_contrato=fecha_contrato)
    consultores = consultores_nombrados(T)
    veredicto, detalle = coincide_emisor(T, emisor)
    cita_cui = bool(cui) and re.sub(r"\D", "", str(cui)) in T
    numero_ok = None
    if numero_citado:
        nc = re.sub(r"[^A-Z0-9]", "", normalizar(numero_citado))
        if len(nc) >= 3:
            numero_ok = nc in re.sub(r"[^A-Z0-9]", "", T)
    partes = []
    if f:
        partes.append(f"Resolución de aprobación del {f.strftime('%d/%m/%Y')}.")
    elif not descartada:
        partes.append("La resolución no muestra una fecha legible.")
    if descartada:
        de_la_res = f" para la resolución {numero_ref}" if numero_ref else ""
        partes.append(f"La fecha leída ({descartada.strftime('%d/%m/%Y')}) no es "
                      f"plausible{de_la_res} y se omitió.")
    if veredicto == "confirma":
        partes.append("Nombra al emisor del certificado como consultor del expediente.")
    elif veredicto == "nombra_otro":
        partes.append(f"Nombra a otro consultor ({detalle}), no al emisor del certificado.")
    else:
        partes.append("No nombra a quien elaboró el expediente.")
    if numero_ok is True:
        partes.append("El número de resolución citado en el certificado coincide.")
    elif numero_ok is False:
        partes.append("El número de resolución citado en el certificado NO aparece en este documento.")
    return {"legible": True, "fecha": f.isoformat() if f else None,
            "consultores": consultores, "coincide_emisor": veredicto,
            "detalle_emisor": detalle, "cita_cui": cita_cui,
            "numero_citado_coincide": numero_ok,
            "fecha_descartada": descartada.isoformat() if descartada else None,
            "fecha_motivo": motivo, "resumen": " ".join(partes)}


# Versión del extractor/formato del sidecar: subirla invalida todo texto guardado
# (cambio de DPI, PSM, idioma o de la forma de leer la capa de texto).
VERSION_TEXTO = 2


def _ruta_texto(ruta_pdf: Path) -> Path:
    return ruta_pdf.with_name(ruta_pdf.name + ".texto.json")


def _huella_pdf(ruta_pdf: Path) -> str:
    """SHA-256 del contenido: dos PDF distintos del mismo tamaño no se confunden
    (revisión de Codex, 7-sep: sustituir el PDF por otro de igual tamaño
    reutilizaba la fecha del anterior)."""
    h = hashlib.sha256()
    with ruta_pdf.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _leer_texto_guardado(ruta_pdf: Path, max_pag: int) -> Optional[tuple[str, str, int]]:
    """Texto ya extraído de este PDF, si el sidecar corresponde al mismo contenido
    (huella), a la misma versión del extractor y al mismo tope de páginas. Un
    «sin_texto» (host sin Tesseract) no se reutiliza: instalar el OCR debe bastar
    para que la siguiente lectura lo use."""
    try:
        p = _ruta_texto(ruta_pdf)
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        if (d.get("version") != VERSION_TEXTO or d.get("max_pag") != max_pag
                or d.get("fuente") == "sin_texto"
                or d.get("huella") != _huella_pdf(ruta_pdf)):
            return None
        return str(d.get("texto") or ""), str(d.get("fuente") or ""), int(d.get("paginas") or 0)
    except (OSError, ValueError, TypeError):
        return None


def _guardar_texto(ruta_pdf: Path, max_pag: int, texto: str, fuente: str, paginas: int) -> None:
    """Best-effort: no poder guardar el sidecar jamás afecta la lectura."""
    try:
        _ruta_texto(ruta_pdf).write_text(json.dumps({
            "version": VERSION_TEXTO, "max_pag": max_pag,
            "huella": _huella_pdf(ruta_pdf), "bytes": ruta_pdf.stat().st_size,
            "fuente": fuente, "paginas": paginas, "texto": texto,
        }, ensure_ascii=False), encoding="utf-8")
    except (OSError, TypeError, ValueError) as ex:
        logger.debug("sidecar de texto %s: %s", ruta_pdf.name, ex)


def leer_resolucion(url: str, destino_dir, *, emisor: str, cui: Optional[str],
                    numero: Optional[str] = None, numero_citado: Optional[str] = None,
                    fecha_contrato: Any = None,
                    descargar: Optional[Callable[[str, Path], bool]] = None,
                    extraer_texto: Optional[Callable[[Path], tuple[str, str, int]]] = None,
                    max_pag: int = 4) -> Optional[dict]:
    """Descarga (o reutiliza) el PDF de la resolución y lo interpreta.

    Best-effort: cualquier fallo de red/lectura devuelve None y el análisis sigue.
    `descargar(url, ruta) -> bool` y `extraer_texto(ruta) -> (texto, fuente, paginas)`
    son inyectables (tests offline); por defecto usan `scraping.mef.descargar_pdf`
    y `scraping.ocr_local.texto_pdf`.

    `numero` (el del 08-A) y `fecha_contrato` (date o ISO de la firma del contrato
    del expediente) se usan para descartar fechas imposibles: ver
    `plausibilidad_fecha` y los campos `fecha_descartada` / `fecha_motivo`.
    """
    try:
        destino_dir = Path(destino_dir)
        destino_dir.mkdir(parents=True, exist_ok=True)
        base = re.sub(r"[^A-Za-z0-9]+", "_", f"{cui or 'sin_cui'}_{numero or 'resolucion'}")[:80]
        ruta = destino_dir / f"{base}.pdf"
        if not ruta.exists():
            if descargar is None:
                from scraping import mef
                sesion = mef.crear_session()
                descargar = lambda u, r: mef.descargar_pdf(sesion, u, r)  # noqa: E731
            if not descargar(url, ruta):
                return None
        if extraer_texto is None:
            from scraping.ocr_local import texto_pdf
            extraer_texto = lambda r: texto_pdf(r, max_pag=max_pag)  # noqa: E731
        # El texto (capa u OCR) se guarda junto al PDF: la misma resolución la leen
        # todas las experiencias que comparten CUI (Muraria 6-sep: 34 lecturas
        # sobre 11 archivos, 19 pasadas de OCR sobre 7) y el OCR es lo caro.
        previo = _leer_texto_guardado(ruta, max_pag)
        if previo is not None:
            texto, fuente, paginas = previo
        else:
            texto, fuente, paginas = extraer_texto(ruta)
            _guardar_texto(ruta, max_pag, texto, fuente, paginas)
        out = interpretar_resolucion(texto, emisor, cui, numero_citado, fecha_contrato,
                                     numero=numero or numero_citado)
        out.update({"numero": numero, "url": url, "archivo": ruta.name,
                    "paginas": paginas, "texto_fuente": fuente,
                    "texto_reutilizado": previo is not None})
        return out
    except Exception as ex:  # noqa: BLE001 — leer un PDF jamás tumba el análisis
        logger.debug("resolución de aprobación %s: %s", url, ex)
        return None
