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
    se abstiene ante incoherencias.

Funciones PURAS salvo `leer_resolucion`, que descarga y lee (red + OCR) con
descargador y extractor inyectables para los tests.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SETIEMBRE": 9, "SEPTIEMBRE": 9, "OCTUBRE": 10,
         "NOVIEMBRE": 11, "DICIEMBRE": 12}
_RE_FECHA_LARGA = re.compile(
    r"\b(\d{1,2})\s+DE\s+(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SETIEMBRE|"
    r"SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+DE(?:L)?\s+(\d{4})\b")
_RE_FECHA_CORTA = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
_RE_SUFIJO_LEGAL = re.compile(
    r"\b(S\.?\s?A\.?\s?C\.?|S\.?\s?A\.?|E\.?\s?I\.?\s?R\.?\s?L\.?|S\.?\s?R\.?\s?L\.?|"
    r"SOCIEDAD ANONIMA CERRADA|SOCIEDAD ANONIMA|EMPRESA INDIVIDUAL DE RESPONSABILIDAD LIMITADA)\b\.?")
# Roles que preceden (o siguen) al nombre de quien elaboró/supervisó el expediente.
_ROLES = (r"CONSULTOR(?:A|IA)?(?:\s+DE\s+OBRA)?|CONTRATISTA|PROYECTISTA|ELABORAD[OA]\s+POR|"
          r"ENTIDAD\s+PRIVADA\s+SUPERVISORA|EMPRESA\s+PRIVADA|A\s+FAVOR\s+DE(?:L|\s+LA)?|"
          r"SUSCRITO\s+CON|SUSCRIBIO\s+EL\s+CONTRATO\s+CON")
_RE_ROL = re.compile(rf"\b({_ROLES})\b")
_ARTICULOS = r"(?:EL|LA|LOS|LAS|DEL|DE\s+LA|EMPRESA|ING\.?|ARQ\.?|SR\.?|SRA\.?|CONSULTOR(?:A)?)?\s*"
_RE_NOMBRE_TRAS_ROL = re.compile(
    rf"\b(?:{_ROLES})\s*[:,]?\s*{_ARTICULOS}"
    r"([A-Z][A-Z0-9 .&+\-]{3,90}?)(?=\s*[,;()\"*]|\s+(?:QUE|CON|PARA|POR|MEDIANTE|SEGUN|EN|Y|DEL|DE)\s|$)")
_RE_NOMBRE_ANTES_ROL = re.compile(
    r"([A-Z][A-Z0-9 .&+\-]{3,80}?)\s*[-–,]?\s*(?:ENTIDAD\s+PRIVADA\s+SUPERVISORA|"
    r"COMO\s+CONSULTOR(?:A)?|EN\s+CALIDAD\s+DE\s+CONSULTOR(?:A)?)")
_GENERICOS = {"OBRA", "PARA", "ELABORACION", "EXPEDIENTE", "TECNICO", "SERVICIO",
              "CONSULTORIA", "PROYECTO", "INVERSION", "ENTIDAD", "UNIDAD", "ESPECIALISTA",
              "RESPONSABLE", "OFICINA", "GERENCIA", "SUPERVISION", "EJECUCION", "PUBLICA",
              "PRIVADA", "DE", "LA", "EL", "DEL", "LOS", "LAS"}
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


def fecha_emision(T: str) -> Optional[date]:
    """Fecha de la resolución: la primera del encabezado («Lima, 23 de mayo de
    2017») que NO venga precedida de «DE FECHA» (esas citan otros documentos).
    Si no hay ninguna así en las primeras 1.500 letras, la primera del texto."""
    fechas = fechas_en_texto(T)
    if not fechas:
        return None
    for pos, f in fechas:
        if pos > 1500:
            break
        antes = T[max(0, pos - 14):pos]
        if "DE FECHA" in antes or "FECHA " in antes:
            continue
        return f
    return fechas[0][1]


def consultores_nombrados(T: str) -> list[str]:
    """Nombres que el texto asocia a un rol de consultor/contratista/supervisor.
    Se descartan los que son solo palabras genéricas («…de obra para la…»)."""
    vistos: list[str] = []

    def _agregar(nombre: str) -> None:
        n = re.sub(r"\s+", " ", nombre).strip(" .,-")
        toks = [t for t in re.split(r"[^A-Z0-9]+", n) if t]
        if len(n) < 4 or not any(t not in _GENERICOS and len(t) >= 3 for t in toks):
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
                           numero_citado: Optional[str] = None) -> dict:
    """Interpreta el texto (capa u OCR) de una resolución de aprobación. Puro."""
    T = normalizar(texto)
    if len(T) < 200:
        return {"legible": False, "fecha": None, "consultores": [],
                "coincide_emisor": "sin_texto", "detalle_emisor": None,
                "cita_cui": False, "numero_citado_coincide": None,
                "resumen": "El documento no se pudo leer (escaneo sin texto reconocible)."}
    f = fecha_emision(T)
    consultores = consultores_nombrados(T)
    veredicto, detalle = coincide_emisor(T, emisor)
    cita_cui = bool(cui) and re.sub(r"\D", "", str(cui)) in T
    numero_ok = None
    if numero_citado:
        nc = re.sub(r"[^A-Z0-9]", "", normalizar(numero_citado))
        if len(nc) >= 3:
            numero_ok = nc in re.sub(r"[^A-Z0-9]", "", T)
    partes = []
    partes.append(f"Resolución de aprobación del {f.strftime('%d/%m/%Y')}." if f
                  else "La resolución no muestra una fecha legible.")
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
            "numero_citado_coincide": numero_ok, "resumen": " ".join(partes)}


def leer_resolucion(url: str, destino_dir, *, emisor: str, cui: Optional[str],
                    numero: Optional[str] = None, numero_citado: Optional[str] = None,
                    descargar: Optional[Callable[[str, Path], bool]] = None,
                    extraer_texto: Optional[Callable[[Path], tuple[str, str, int]]] = None,
                    max_pag: int = 4) -> Optional[dict]:
    """Descarga (o reutiliza) el PDF de la resolución y lo interpreta.

    Best-effort: cualquier fallo de red/lectura devuelve None y el análisis sigue.
    `descargar(url, ruta) -> bool` y `extraer_texto(ruta) -> (texto, fuente, paginas)`
    son inyectables (tests offline); por defecto usan `scraping.mef.descargar_pdf`
    y `scraping.ocr_local.texto_pdf`.
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
        texto, fuente, paginas = extraer_texto(ruta)
        out = interpretar_resolucion(texto, emisor, cui, numero_citado)
        out.update({"numero": numero, "url": url, "archivo": ruta.name,
                    "paginas": paginas, "texto_fuente": fuente})
        return out
    except Exception as ex:  # noqa: BLE001 — leer un PDF jamás tumba el análisis
        logger.debug("resolución de aprobación %s: %s", url, ex)
        return None
