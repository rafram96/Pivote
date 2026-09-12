"""
generar_excel.py — Genera el Excel "Formato de Evaluación" (5 partes) desde el
JSON espejo. Construcción dinámica (filas variables por profesional), con estilos
calcados del formato del ingeniero (Trujillo).

Estilo (del completado de Trujillo):
  · Títulos PARTE  → negrita, banda gris, merge A:V.
  · Bloque PROFESIONAL → fondo verde (548235) + texto blanco, merge A:V.
  · Sub-título PARTE 4 → fondo verde claro.
  · Headers de tabla → fondo celeste (BDD7EE), negrita, centrado, wrap.
  · Montos → formato #,##0.00 ; meses/años → 0.00 ; días → entero.
  · Anchos de columna → los del formato del ingeniero.

> El backend REGENERA el Excel final enriquecido; este lo produce Claude como
> primera versión humana.

Uso:
    python generar_excel.py [ruta_json] [ruta_salida_xlsx]
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date as _date
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    # La entrada por archivo se usa desde cualquier cwd, también fuera del repo.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from entregables.textos import conciliar_conclusion, sin_jerga as _sin_jerga

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ── Saneo defensivo de celdas (GLOBAL al proceso) ────────────────────────────
# openpyxl lanza IllegalCharacterError al asignar un string con caracteres de
# control (\x00-\x08, \x0b-\x0c, \x0e-\x1f) — comunes en texto de OCR/PDF — y
# revienta el Excel ENTERO. También revienta con list/dict en una celda ("Cannot
# convert [...] to Excel"), y el espejo permite `requisitos`/`total` como
# record(any). Parcheamos `_bind_value` para coercer list/dict→string y quitar los
# chars de control al vuelo. Es process-global (cubre también excel_final, que
# importa este módulo) e idempotente. Cierra los dos vectores de crash de Excel.
from openpyxl.cell import cell as _oc_cell  # noqa: E402

if not getattr(_oc_cell.Cell, "_saneo_controles", False):
    _oc_orig_bind = _oc_cell.Cell._bind_value

    def _oc_bind(self, value):
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(x) for x in value)
        elif isinstance(value, dict):
            value = "; ".join(f"{k}: {v}" for k, v in value.items())
        if isinstance(value, str):
            value = _oc_cell.ILLEGAL_CHARACTERS_RE.sub("", value)
        return _oc_orig_bind(self, value)

    _oc_cell.Cell._bind_value = _oc_bind
    _oc_cell.Cell._saneo_controles = True

NCOLS = 22  # A..V

# ── Estilos ──────────────────────────────────────────────────────────────────
_THIN = Side(style="thin", color="999999")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

F_PARTE = Font(bold=True, size=11, color="15212E")
FILL_PARTE = PatternFill("solid", fgColor="D9D9D9")
F_PROF = Font(bold=True, size=11, color="FFFFFF")
FILL_PROF = PatternFill("solid", fgColor="548235")        # verde (como el ingeniero)
F_SUB = Font(bold=True, size=10, color="375623")
FILL_SUB = PatternFill("solid", fgColor="E2EFDA")         # verde claro
F_HEAD = Font(bold=True, size=9, color="1F3864")
FILL_HEAD = PatternFill("solid", fgColor="BDD7EE")        # celeste (como el ingeniero)
F_CELL = Font(size=9)
F_BOLD = Font(bold=True, size=9)

# Origen del dato (convención del pivote)
FILL_CLAUDE = PatternFill("solid", fgColor="FFFF00")      # amarillo: llenado por Claude
FILL_BACKEND = PatternFill("solid", fgColor="FCE4D6")     # naranja: verificado por backend on-prem

AL_WRAP = Alignment(wrap_text=True, vertical="top")
AL_HEAD = Alignment(wrap_text=True, vertical="center", horizontal="center")
AL_TITLE = Alignment(vertical="center", horizontal="left")

FMT_MONEY = "#,##0.00"
FMT_DEC = "0.00"
FMT_INT = "#,##0"
FMT_FECHA = "dd/mm/yy"   # formato de presentación pedido por el cliente

# ── Estilo de la hoja CLAUDE — formato de Manuel: fondo blanco, bandas azules y
#    verde/rojo SOLO en los veredictos (convención de conditional format de Excel).
#    Las constantes de arriba (FILL_PARTE/PROF/CLAUDE/BACKEND…) se conservan para
#    las OTRAS hojas del Excel final (Base de Datos, por profesional). ─────────────
F_CL_PARTE = Font(bold=True, size=11, color="FFFFFF")
FILL_CL_PARTE = PatternFill("solid", fgColor="1F4E78")    # azul oscuro: banda PARTE
F_CL_PROF = Font(bold=True, size=11, color="FFFFFF")
FILL_CL_PROF = PatternFill("solid", fgColor="2E75B6")     # azul medio: banda PROFESIONAL
F_CL_SUB = Font(bold=True, size=10, color="1F4E78")
FILL_CL_SUB = PatternFill("solid", fgColor="DDEBF7")      # azul claro: subtítulo PARTE 4
FILL_CL_HEAD = PatternFill("solid", fgColor="DDEBF7")     # azul claro: headers de tabla

FILL_CUMPLE = PatternFill("solid", fgColor="C6EFCE")      # verde: cumple / válido
FILL_NO_CUMPLE = PatternFill("solid", fgColor="FFC7CE")   # rojo: no cumple / alerta
FILL_PEND = PatternFill("solid", fgColor="FFF2CC")        # amarillo suave: por verificar
FILL_SUPUESTO = PatternFill("solid", fgColor="E4D7F5")    # violeta: valor inferido

# Marcador sutil de dato verificado/enriquecido por el backend on-prem: borde
# izquierdo azul (coexiste con el verde/rojo del veredicto).
_THICK_BE = Side(style="medium", color="2E75B6")
BORDER_BACKEND = Border(left=_THICK_BE, right=_THIN, top=_THIN, bottom=_THIN)

_RE_WS = re.compile(r"\s+")


def _clasificar_veredicto(value):
    """'si' | 'no' | 'pend' | None según el texto de un campo de veredicto."""
    if value in (None, ""):
        return None
    t = _RE_WS.sub(" ", str(value).strip()).upper()
    if "POR VERIFICAR" in t or "NO APLICA" in t or t in ("-", "N/A", "?"):
        return "pend"
    if t.startswith(("NO", "✘", "✗")):
        return "no"
    if t.startswith(("SI", "SÍ", "CUMPLE", "ACREDITA", "VÁLIDO", "VALIDO", "✔", "✓")):
        return "si"
    return None  # texto libre → sin color


def _fill_veredicto(value, polaridad):
    """Fill verde/rojo/amarillo de un veredicto. polaridad 'pos' → SÍ es bueno;
    'neg' → SÍ es malo (ej. ¿anterior a colegiatura?, ¿certificado antes de
    culminar?)."""
    cl = _clasificar_veredicto(value)
    if cl is None:
        return None
    if cl == "pend":
        return FILL_PEND
    bueno = (cl == "si") if polaridad == "pos" else (cl == "no")
    return FILL_CUMPLE if bueno else FILL_NO_CUMPLE




# ── Conciliación de la cifra de días del veredicto con el total verificado ──────
#
# El texto de la conclusión («CUMPLE — acredita 1267 días…») lo escribe el
# evaluador automático y es LITERAL: se conserva palabra por palabra porque es lo
# que el Comité audita. Su cifra, en cambio, es aritmética, y ahí discrepa: el
# proyecto cuenta INCLUSIVO (fin − inicio + 1, un día más POR PERIODO) en todo el
# libro, así que el mismo profesional mostraba 1269 en la PARTE 5 y 1267 en la
# conclusión de al lado — dos números sin explicación a la vista (job Vitarte
# `7e9306a321ac`, hoja «P1. Contr»: PARTE 5 = 1269, CONCLUSIÓN = 1267).
#
# Aquí NO se reescribe la prosa del evaluador: se antepone el total verificado y
# se declara de dónde sale el otro número. El sistema no corrige al documento, lo
# confronta — pero nunca muestra dos cifras sin explicar.
#
# La conciliación se ABSTIENE salvo que la diferencia sea, demostrablemente, la
# del conteo de bordes: el verificado tiene que ser MAYOR y por como mucho un día
# por periodo declarado. Cualquier otra distancia es otra cosa (un recorte por
# paralizaciones, una suma sobre otro conjunto de constancias, un margen citado
# de pasada como «~7 días sobre el mínimo») y explicarla como conteo de bordes
# sería mentir. En esos casos el texto sale intacto: el Excel ya muestra las
# restas del Paso 5 en sus propias filas.
_RE_DIAS_CITADOS = re.compile(r"(\d[\d.,]*)\s*d[ií]as?\b", re.I)


def _entero_citado(txt: str) -> Optional[int]:
    """"1,267" / "1267" → 1267. Decimales o basura → None (no es un conteo)."""
    limpio = str(txt).replace(",", "").replace(".", "")
    return int(limpio) if limpio.isdigit() else None


def dias_citados(texto) -> list[int]:
    """Conteos de días que menciona un texto de veredicto, en orden de aparición."""
    if not isinstance(texto, str):
        return []
    vistos: list[int] = []
    for m in _RE_DIAS_CITADOS.finditer(texto):
        n = _entero_citado(m.group(1))
        if n is not None and n not in vistos:
            vistos.append(n)
    return vistos




# Un MONTO tiene forma de monto: miles agrupados ("16,670,989.88" / "16.670.989,88")
# o ≥6 dígitos corridos. NUNCA un número suelto como "90" — en la prosa real de
# Lircay, «el límite inferior calculado (90% de la cuantía S/16,670,989.88)»
# hacía que el parser viejo capturara 90.0 como límite inferior (#52).
_RE_MONTO_FORMA = (r"(?:S/\.?\s*)?"
                   r"(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?"      # 16,670,989.88
                   r"|\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?"      # 16.670.989,88
                   r"|\d{6,}(?:[.,]\d{1,2})?)")              # 16670989.88


def _monto_a_float(v: str) -> float | None:
    if not v:
        return None
    clean = re.sub(r"[^\d.,]", "", str(v)).strip()
    if not clean:
        return None
    if "," in clean and "." in clean:
        clean = (clean.replace(",", "") if clean.rfind(".") > clean.rfind(",")
                 else clean.replace(".", "").replace(",", "."))
    elif "," in clean:
        # coma como decimal SOLO si parece decimal (≤2 dígitos al final)
        clean = clean.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", clean) \
            else clean.replace(",", "")
    try:
        val = float(clean)
        return val if val > 0 else None
    except ValueError:
        return None


def _extraer_montos_prosa(detalle: str) -> dict[str, float | None]:
    """Fallback CONSERVADOR (#52): recupera cuantía / límite inferior / propuesta
    de la prosa del DETALLE cuando la skill los dejó ahí en vez de en las celdas.

    Reglas — cada una nace de un fallo real:
      · solo montos CON FORMA de monto (nunca "90" del "90% de la cuantía");
      · cada palabra clave busca en una VENTANA corta hacia adelante (la prosa
        mete palabras entre la clave y el número: «la oferta del postor (S/…»);
      · coherencia: si el "límite inferior" capturó el mismo número que la
        cuantía, es que la ventana pescó el monto equivocado → se descarta;
      · lo que no se encuentra queda None — el candado de integridad lo grita
        (OFERTA_INCOMPLETA); JAMÁS asignación posicional a ciegas ("los
        primeros 3 números del texto"), que es un mal-dato silencioso."""
    if not detalle or not isinstance(detalle, str):
        return {}

    def _ventana(claves: list[str]) -> float | None:
        for kw in claves:
            m = re.search(kw + r"[^0-9]{0,80}?" + _RE_MONTO_FORMA, detalle,
                          re.I | re.S)
            if m:
                return _monto_a_float(m.group(1))
        return None

    cuantia = _ventana([r"cuant[ií]a", r"valor\s+referencial", r"valor\s+estimad[oa]"])
    limite = _ventana([r"l[ií]mite\s+inferior", r"piso\s+legal"])
    propuesta = _ventana([r"propuesta\s+econ[oó]mica", r"oferta\s+del\s+postor",
                          r"propuesta", r"oferta", r"ofertad[oa]"])
    if limite is not None and cuantia is not None and limite == cuantia:
        limite = None            # la ventana del límite pescó la cuantía
    if propuesta is not None and cuantia is not None and propuesta == cuantia \
            and limite != propuesta:
        propuesta = None         # ídem: "oferta" pescó el referencial
    return {"cuantia": cuantia, "limite_inferior": limite, "propuesta": propuesta}



def _num(v):
    """Puntaje como número, o None si la celda trae texto ("NO APLICA")."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def nota_parte5(factores, puntaje_total) -> str:
    """Resumen de la PARTE 5 armado desde las MISMAS celdas que se imprimen.

    Recorre los factores tal como quedaron en la tabla: los que tienen puntaje
    suman, los que dicen «NO APLICA» se listan aparte y los que quedaron sin
    puntaje se declaran por confirmar. Si el total impreso no es la suma de lo
    que la tabla muestra, la nota lo dice en vez de repetir un número que el
    lector no puede reproducir."""
    con_puntaje: list[str] = []
    por_confirmar: list[str] = []
    no_aplican: list[str] = []
    suma = 0.0
    for f in factores or []:
        nombre = str((f or {}).get("factor") or "?").strip() or "?"
        pje = (f or {}).get("puntaje")
        num = _num(pje)
        if num is not None:
            suma += num
            con_puntaje.append(f"{nombre} {num:g}")
        elif str(pje or "").strip().upper().startswith("NO APLICA"):
            no_aplican.append(nombre)
        else:
            por_confirmar.append(nombre)

    total = _num(puntaje_total)
    if total is None:
        cabeza = "Puntaje técnico total: POR VERIFICAR — no se recibió un puntaje total calculable"
    else:
        cabeza = f"Puntaje técnico total {total:g}"
        if con_puntaje:
            cabeza += " = " + " + ".join(con_puntaje)
        if abs(suma - total) > 0.005:
            cabeza += (f" (los factores con puntaje de esta tabla suman {suma:g}: "
                       f"revisar la diferencia)")
    partes = [cabeza + "."]
    if por_confirmar:
        partes.append(f"Por confirmar: {', '.join(por_confirmar)} — su tramo no se "
                      "pudo determinar con el cuadro de las bases, así que no suma.")
    if no_aplican:
        partes.append(f"No aplican (eliminados de las bases): {', '.join(no_aplican)}.")
    return " ".join(partes)


def fecha_excel(v):
    """ISO 'YYYY-MM-DD' → date real (NOTA 13: fechas en formato fecha, se
    muestran dd/mm/yy). Sentinels ('POR VERIFICAR…') y parciales quedan texto."""
    if isinstance(v, _date):
        return v
    if isinstance(v, str) and len(v) == 10:
        try:
            return _date.fromisoformat(v)
        except ValueError:
            return v
    return v

# Anchos del formato del ingeniero (rejilla compartida por las 5 partes)
WIDTHS = {"A": 6, "B": 25, "C": 35, "D": 30, "E": 41, "F": 22, "G": 18, "H": 18,
          "I": 20, "J": 12, "K": 10, "L": 14, "M": 12, "N": 10, "O": 16, "P": 25,
          "Q": 18, "R": 20, "S": 18, "T": 18, "U": 18, "V": 35}


class Builder:
    def __init__(self, ws):
        self.ws = ws
        self.r = 1

    def _band(self, text, font, fill, height=22):
        ws = self.ws
        ws.merge_cells(start_row=self.r, start_column=1, end_row=self.r, end_column=NCOLS)
        c = ws.cell(self.r, 1, text)
        c.font, c.fill, c.alignment = font, fill, AL_TITLE
        ws.row_dimensions[self.r].height = height
        self.r += 1

    def parte(self, text):
        self._band(text, F_CL_PARTE, FILL_CL_PARTE, 24)
        self.blank()

    def profblock(self, text):
        self._band(text, F_CL_PROF, FILL_CL_PROF, 22)

    def subtitle(self, text):
        self._band(text, F_CL_SUB, FILL_CL_SUB, 18)

    def headers(self, values):
        ws = self.ws
        for i, v in enumerate(values, start=1):
            c = ws.cell(self.r, i, v)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_CL_HEAD, BORDER, AL_HEAD
        ws.row_dimensions[self.r].height = 32
        self.r += 1

    def row(self, values, bold=False, fmts=None, verdicts=None, backend_cols=None,
            supuesto_cols=None, fills=None):
        """Escribe una fila. Fondo blanco; verde/rojo SOLO en las columnas de
        veredicto (`verdicts` = {col: 'pos'|'neg'}, según si "SÍ" es bueno o malo)
        y amarillo suave en "POR VERIFICAR". Las columnas en `backend_cols` llevan
        un borde izquierdo azul (dato verificado/enriquecido por el backend).
        `fills` = {col: PatternFill} fuerza un fondo cuando el color no sale de un
        veredicto (ej. el puntaje retirado de la PARTE 5)."""
        ws = self.ws
        fmts = fmts or {}
        verdicts = verdicts or {}
        backend_cols = backend_cols or set()
        supuesto_cols = supuesto_cols or set()
        fills = fills or {}
        for i, v in enumerate(values, start=1):
            c = ws.cell(self.r, i, v)
            c.font = F_BOLD if bold else F_CELL
            c.alignment = AL_WRAP
            c.border = BORDER_BACKEND if i in backend_cols else BORDER
            if i in fmts and isinstance(v, (int, float, _date)):
                c.number_format = fmts[i]
            if i in verdicts:
                fill = _fill_veredicto(v, verdicts[i])
                if fill:
                    c.fill = fill
            if i in fills:
                c.fill = fills[i]
            # La procedencia gana al color semántico: primero debe quedar claro
            # que el valor fue inferido; no se confunde con "por verificar".
            if i in supuesto_cols and v not in (None, ""):
                c.fill = FILL_SUPUESTO
        self.r += 1

    def kv(self, label, value, fmt=None, verdict=None, valor_veredicto=None):
        """`valor_veredicto` clasifica el color a partir de OTRO texto que el que
        se escribe. Se usa cuando la celda lleva un prefijo del equipo evaluador
        (la cifra verificada) delante del veredicto literal: sin esto el color
        se perdería, porque `_clasificar_veredicto` mira el inicio del texto."""
        ws = self.ws
        ws.cell(self.r, 1, label).font = F_BOLD
        ws.merge_cells(start_row=self.r, start_column=2, end_row=self.r, end_column=NCOLS)
        c = ws.cell(self.r, 2, value)
        c.font, c.alignment = F_CELL, AL_WRAP
        if fmt and isinstance(value, (int, float)):
            c.number_format = fmt
        if verdict:
            fill = _fill_veredicto(
                value if valor_veredicto is None else valor_veredicto, verdict)
            if fill:
                c.fill = fill
        self.r += 1

    def leyenda(self):
        ws = self.ws
        ws.cell(self.r, 1, "Leyenda:").font = F_BOLD
        swatches = [
            (2, 3, "Verde = cumple / válido", FILL_CUMPLE, BORDER),
            (4, 5, "Rojo = no cumple / alerta", FILL_NO_CUMPLE, BORDER),
            (6, 8, "Amarillo = por verificar", FILL_PEND, BORDER),
            (9, 12, "Borde azul izq. = verificado automáticamente por el servidor",
             None, BORDER_BACKEND),
            (13, 16, "Violeta = dato supuesto / inferido", FILL_SUPUESTO, BORDER),
        ]
        for ini, fin, txt, fill, border in swatches:
            ws.merge_cells(start_row=self.r, start_column=ini,
                           end_row=self.r, end_column=fin)
            c = ws.cell(self.r, ini, txt)
            c.font, c.border, c.alignment = F_CELL, border, AL_TITLE
            if fill:
                c.fill = fill
        self.r += 1

    def blank(self):
        self.r += 1


def construir_hoja_evaluacion(ws, espejo: dict,
                              confiabilidad: Optional[dict] = None) -> None:
    """Construye la hoja de evaluación (5 partes) en un worksheet existente.
    La usa este script (hoja única) y `entregables/excel_final.py` (hoja CLAUDE
    dentro del Excel final con Base de Datos + hojas por profesional)."""
    for col, w in WIDTHS.items():
        ws.column_dimensions[col].width = w
    b = Builder(ws)
    p = espejo.get("postor", {})

    # ── Encabezado ──
    b.kv("Postor:", p.get("detalle") or espejo["_meta"].get("postor", ""))
    # ADR-010 / #50 · con qué tipo de concurso corrió el análisis, en palabras
    # del evaluador. Un análisis que salió raro tiene que poder explicarse aquí,
    # sin leer logs. Solo cuando la skill lo declaró; los espejos viejos no lo traen.
    _tipo_concurso = {
        "expedientes": "Elaboración de expedientes técnicos — la experiencia se "
                       "verifica contra el contrato y la aprobación del expediente",
        "obras": "Supervisión o ejecución de obra — la experiencia se verifica "
                 "contra las valorizaciones de la obra",
    }.get(str((espejo.get("_meta") or {}).get("tipo_evaluacion") or "").strip().lower())
    if _tipo_concurso:
        b.kv("Tipo de concurso:", _tipo_concurso)
    b.kv("Concurso:", espejo["_meta"].get("concurso", ""))
    meta = espejo.get("_meta") or {}
    if meta.get("estado_entregable"):
        b._band(meta["estado_entregable"], F_BOLD,
                FILL_PEND if "REQUIERE" in meta["estado_entregable"] else FILL_CUMPLE, 30)
        b.kv("Generado:", meta.get("generado_en") or "—")
        b.kv("Huella analítica:", meta.get("huella_analitica") or "—")
    veredicto = str((confiabilidad or {}).get("veredicto") or "").lower()
    rotulos = {
        "confiable": "CONFIABILIDAD: CONFIABLE — sin hallazgos críticos de integridad",
        "revisar": "CONFIABILIDAD: REVISAR — hay observaciones que requieren atención",
        "no_confiable": "CONFIABILIDAD: NO CONFIABLE — no usar sin revisar los hallazgos",
        "no_revisable": "CONFIABILIDAD: NO REVISABLE — no se pudo comprobar la integridad",
    }
    if veredicto in rotulos:
        fill = (FILL_CUMPLE if veredicto == "confiable" else
                FILL_PEND if veredicto == "revisar" else FILL_NO_CUMPLE)
        b._band(rotulos[veredicto], F_BOLD, fill, 30)
        for h in (confiabilidad or {}).get("hallazgos_criticos") or []:
            codigo = h.get("codigo") or "INTEGRIDAD"
            referencia = f" ({h['referencia']})" if h.get("referencia") else ""
            b.kv(f"Hallazgo crítico · {codigo}",
                 _sin_jerga(f"{h.get('mensaje') or 'Revisar el análisis'}{referencia}"))
    b.leyenda()
    b.blank()

    # ── PARTE 1 ──
    b.parte("PARTE 1: FORMULARIOS DEL POSTOR")
    b.headers(["ANEXO", "DESCRIPCIÓN", "OBSERVACIÓN", "FOLIO"])
    for f in p.get("formularios", []):
        b.row([f.get("anexo", ""), f.get("documento") or f.get("descripcion", ""), f.get("observacion", ""), f.get("folio", "")])
    b.blank()
    # ── OFERTA ECONÓMICA (#52): el bloque se pinta SIEMPRE — un bloque ausente
    # era invisible y sin las 3 celdas no hay descalificación por precio ni
    # puntaje. Lo que falte tras el rescate de la prosa queda VISIBLE y ruidoso.
    oe = p.get("oferta_economica") or {}
    cuantia = oe.get("cuantia")
    limite_inf = oe.get("limite_inferior")
    propuesta = oe.get("propuesta")
    detalle = oe.get("detalle", "") or ""

    rescatados = []
    if (cuantia is None or limite_inf is None or propuesta is None) and detalle:
        parsed = _extraer_montos_prosa(detalle)
        if cuantia is None and parsed.get("cuantia") is not None:
            cuantia, _ = parsed["cuantia"], rescatados.append("cuantía")
        if limite_inf is None and parsed.get("limite_inferior") is not None:
            limite_inf, _ = parsed["limite_inferior"], rescatados.append("límite inferior")
        if propuesta is None and parsed.get("propuesta") is not None:
            propuesta, _ = parsed["propuesta"], rescatados.append("propuesta")

    b.headers(["", "CUANTÍA", "LÍMITE INFERIOR", "PROPUESTA", "DETALLE"])
    b.row(["Monto", cuantia, limite_inf, propuesta, _sin_jerga(detalle)],
          fmts={2: FMT_MONEY, 3: FMT_MONEY, 4: FMT_MONEY})
    faltan = [n for n, v in (("CUANTÍA", cuantia), ("LÍMITE INFERIOR", limite_inf),
                             ("PROPUESTA", propuesta)) if v is None]
    if faltan:
        b.row(["", f"⚠ OFERTA INCOMPLETA: falta(n) {', '.join(faltan)} — sin las 3 "
                   "celdas no se puede aplicar la descalificación por precio ni el "
                   "puntaje. Verificar los folios de la oferta.", "", "", ""],
              bold=True)
    if rescatados:
        b.row(["", f"⚠ {', '.join(rescatados).capitalize()} recuperado(s) del texto "
                   "del DETALLE (no venían en sus celdas) — verificar contra el "
                   "folio.", "", "", ""], bold=True)
    b.blank()

    # ── PARTE 2 ──
    b.parte("PARTE 2: EXPERIENCIA DEL POSTOR")
    b.headers(["No", "CLIENTE / EMISOR", "CONTRATO/OS/FACTURA", "PROYECTO", "TIPO ACREDITACIÓN",
               "MONTO", "% OBJETO", "LE CORRESPONDE", "ACREDITA", "FOLIO",
               "¿DENTRO DEL PERIODO ADMITIDO?", "¿TIPO SOLICITADO?", "OBSERVACIONES"])
    m2 = {6: FMT_MONEY, 7: FMT_DEC, 8: FMT_MONEY, 9: FMT_MONEY}
    # ¿últimos 20/25 años? (11) y ¿tipo solicitado? (12) son veredictos "pos";
    # el cómputo de antigüedad (11) lo recalcula el backend.
    V2, BE2 = {11: "pos", 12: "pos"}, {11}
    for e in p.get("experiencia_postor", []):
        b.row([_sin_jerga(x) for x in
               [e.get("n"), e.get("cliente"), e.get("contrato"), e.get("proyecto"), e.get("tipo_acreditacion"),
                e.get("monto"), e.get("pct_objeto"), e.get("le_corresponde"), e.get("acredita"), e.get("folio"),
                 e.get("dentro_periodo_admitido") or e.get("ultimos_20_anios"),
                 e.get("tipo_solicitado"), e.get("observaciones")]],
              fmts=m2, verdicts=V2, backend_cols=BE2)
    tot = p.get("experiencia_postor_total", {})
    if "requisito_estado" in tot or "monto_requerido" in tot:
        fuente_minimo = tot.get("requisito_fuente") or {}
        monto_minimo = tot.get("monto_requerido")
        texto_minimo = (f"{tot.get('requisito_moneda') or 'PEN'} {monto_minimo}"
                        if monto_minimo is not None else
                        "NO APLICA" if tot.get("requisito_estado") == "no_aplica" else "POR VERIFICAR")
        if fuente_minimo.get("pagina_pdf"):
            texto_minimo += f" — bases, página {fuente_minimo['pagina_pdf']}"
        b.kv("MÍNIMO DE EXPERIENCIA DEL POSTOR", texto_minimo)
    if tot:
        b.row(["", "TOTAL", "", "", "", "", "",
               _sin_jerga(tot.get("monto_confirmado") or tot.get("le_corresponde")),
               _sin_jerga(tot.get("monto_maximo_posible") or tot.get("acredita")),
               "", "", "", ""],
              bold=True, fmts={8: FMT_MONEY, 9: FMT_MONEY})
    if p.get("postor_cumple"):
        b.kv("¿POSTOR CUMPLE 3.4?", _sin_jerga(p["postor_cumple"]), verdict="pos")
    b.blank()

    # ── PARTE 3 + 4 ──
    b.parte("PARTE 3 Y 4: INFORMACIÓN GENERAL Y EXPERIENCIA DE CADA PROFESIONAL")
    P4_HEAD = ["No", "ENTIDAD/EMPRESA EMISORA", "PROYECTO U OBRA", "TIPO DOC", "NOMBRE EMISOR",
               "CARGO EMISOR", "¿VÁLIDO EMITIR?", "FECHA INI", "FECHA FIN", "FECHA EMISIÓN", "FOLIO",
               "DÍAS", "MESES", "AÑOS", "¿ANT. COLEG.?", "CARGO OCUPÓ", "¿CARGO BASES?",
               "¿FUNCIONES?", "¿ANTES CULMINAR?", "¿COVID?", "¿TIPO OBRA?", "OBSERVACIONES"]
    m4 = {8: FMT_FECHA, 9: FMT_FECHA, 10: FMT_FECHA, 12: FMT_INT, 13: FMT_DEC, 14: FMT_DEC}
    # Veredictos PARTE 4: 'pos' = SÍ bueno (¿válido emitir?, ¿cargo bases?,
    # ¿funciones?, ¿tipo obra?); 'neg' = SÍ malo (¿anterior a colegiatura?,
    # ¿certificado antes de culminar?). ¿COVID? queda informativo (sin color).
    V4 = {7: "pos", 15: "neg", 17: "pos", 18: "pos", 19: "neg", 21: "pos"}
    # Backend: ¿válido emitir? (SUNAT ALT04), días/meses/años (Paso 5),
    # ¿anterior a colegiatura? (ALT03, recálculo a 25 años).
    BE4 = {7, 12, 13, 14, 15}
    for prof in espejo.get("profesionales", []):
        sup_prof = set(prof.get("supuestos") or [])
        b.profblock(f"PROFESIONAL {prof.get('n_prof')}: {prof.get('cargo', '')}")
        b.headers(["No", "CARGO", "DETALLE", "INFORMACIÓN DE LA PROPUESTA", "FOLIO", "PUNTAJE"])
        # Estas 5 celdas también las escribe el análisis y también las lee el
        # evaluador: pasan por `_sin_jerga` como el resto del libro. Sin esto se
        # colaba texto de programador ("Verificar folio/título (backend/evaluador)",
        # celda D161 del job Vitarte).
        b.row([prof.get("n_prof"), _sin_jerga(prof.get("cargo")), "NOMBRE DEL PROFESIONAL", _sin_jerga(prof.get("nombre")), prof.get("folio_nombre"), ""], supuesto_cols={2 if "cargo" in sup_prof else 0, 4 if "nombre" in sup_prof else 0})
        b.row(["", "", "TÍTULO PROFESIONAL", _sin_jerga(prof.get("titulo")), prof.get("folio_titulo"), ""], supuesto_cols={4} if "titulo" in sup_prof else set())
        b.row(["", "", "¿La profesión es la indicada?", _sin_jerga(prof.get("profesion_valida")), "", ""], verdicts={4: "pos"}, supuesto_cols={4} if "profesion_valida" in sup_prof else set())
        b.row(["", "", "No de COLEGIATURA / Fecha", _sin_jerga(prof.get("colegiatura")), prof.get("folio_colegiatura"), ""], supuesto_cols={4} if "colegiatura" in sup_prof else set())
        b.row(["", "", "B. CERTIFICACIONES", _sin_jerga(prof.get("certificaciones")), "", ""], supuesto_cols={4} if "certificaciones" in sup_prof else set())
        b.blank()
        b.subtitle(f"PARTE 4 - EXPERIENCIA DEL PROFESIONAL: {prof.get('cargo', '')}")
        b.headers(P4_HEAD)
        # ── La celda HABLA, nunca queda muda (pedido de Rafael, 28-jul) ──────
        # Una abstención en blanco obliga a ir a buscar el porqué a las
        # observaciones del job (caso real: L86-N87 de urgente1 — la fecha final
        # del cert de Tingo María salió ilegible y días/meses/años + TOTAL
        # quedaron vacíos sin explicación EN la hoja). Si el backend se abstuvo
        # por una fecha no verificable, la celda lo dice.
        def _fecha_pendiente(*fechas):
            return any(str(f or "").upper().startswith("POR VERIFICAR")
                       for f in fechas)

        def _abst(valor, pendiente, texto="POR VERIFICAR"):
            return texto if (valor is None and pendiente) else valor

        exps = prof.get("experiencias", [])
        for e in exps:
            sup = set(e.get("supuestos") or [])
            pend = _fecha_pendiente(e.get("fecha_inicial"), e.get("fecha_final"))
            b.row([_sin_jerga(x) for x in
                  [e.get("n"), e.get("entidad_emisora"), e.get("proyecto"), e.get("tipo_documento"),
                   e.get("nombre_emisor"), e.get("cargo_emisor"), e.get("cargo_valido_emitir"),
                   fecha_excel(e.get("fecha_inicial")), fecha_excel(e.get("fecha_final")),
                   fecha_excel(e.get("fecha_emision")), e.get("folio"),
                   _abst(e.get("dias"), pend), _abst(e.get("meses"), pend),
                   _abst(e.get("anios"), pend),
                   _abst(e.get("anterior_colegiatura"),
                         _fecha_pendiente(prof.get("fecha_colegiatura"))),
                   e.get("cargo_ocupado"), e.get("cargo_bases_valido"),
                   e.get("funciones_similares") if e.get("funciones_similares") is not None
                   else "No constan en el certificado",
                   e.get("cert_antes_culminar"), e.get("incluye_covid"), e.get("tipo_obra_valido"),
                   e.get("observaciones")]], fmts=m4, verdicts=V4, backend_cols=BE4,
                  supuesto_cols={col for campo, col in {
                      "entidad_emisora": 2, "proyecto": 3, "tipo_documento": 4,
                      "nombre_emisor": 5, "cargo_emisor": 6,
                      "cargo_valido_emitir": 7, "fecha_inicial": 8,
                      "fecha_final": 9, "fecha_emision": 10, "folio": 11,
                      "cargo_ocupado": 16, "cargo_bases_valido": 17,
                      "funciones_similares": 18, "cert_antes_culminar": 19,
                      "incluye_covid": 20, "tipo_obra_valido": 21,
                  }.items() if campo in sup})
        t = prof.get("total", {})
        # el TOTAL en blanco parecería "sin experiencias"; si la causa es que N
        # de M no tienen días calculables, la celda lo declara con el conteo.
        sin_dias = sum(1 for e in exps if e.get("dias") is None)
        txt_tot = (f"POR VERIFICAR ({sin_dias} de {len(exps)} sin fechas verificables)"
                   if exps and sin_dias else "POR VERIFICAR")
        b.row(["", "", "", "", "", "", "", "", "", "", "TOTAL DECLARADO (suma de filas)",
               _abst(t.get("dias"), bool(sin_dias), txt_tot),
               _abst(t.get("meses"), bool(sin_dias), txt_tot),
               _abst(t.get("anios"), bool(sin_dias), txt_tot),
               "", "", "", "", "", "", "", ""],
              bold=True, fmts=m4, backend_cols={12, 13, 14})
        tb = prof.get("total_backend") or {}
        if tb:
            b.row(["", "", "", "", "", "", "", "", "", "",
                   "(−) Paralizaciones / periodos sin respaldo",
                   tb.get("dias_paralizados"), "", "", "", "", "", "", "", "", "", ""],
                  bold=True, fmts=m4, backend_cols={12})
            b.row(["", "", "", "", "", "", "", "", "", "",
                   "(−) Traslapes entre experiencias", tb.get("dias_traslape"),
                   "", "", "", "", "", "", "", "", "", ""],
                  bold=True, fmts=m4, backend_cols={12})
            b.row(["", "", "", "", "", "", "", "", "", "",
                   "TOTAL EFECTIVO VERIFICADO", tb.get("dias_efectivos"), "",
                   tb.get("anios_efectivos"), "", "", "", "", "", "", "", ""],
                  bold=True, fmts=m4, backend_cols={12, 14})
        # El veredicto lo escribe el LLM sobre los días DECLARADOS; el backend calcula
        # los EFECTIVOS (menos paralizaciones y traslapes, recortados a la ventana de
        # valorizaciones). Cuando el backend contradice al veredicto, la celda se pinta
        # como alerta y el motivo va debajo: antes el CUMPLE salía en verde y el número
        # que lo desmentía vivía 500 filas más abajo, en otra hoja (#51).
        vb = prof.get("cumple_backend")
        _vb_up = str(vb or "").strip().upper()
        _dice_cumple = str(prof.get("cumple", "")).upper().startswith("CUMPLE")
        # Contradice SOLO si el backend concluye NO CUMPLE. Un «POR VERIFICAR» del
        # backend no desmiente el CUMPLE: lo deja pendiente (amarillo), no en rojo.
        # Antes cualquier texto del backend pintaba de rojo un CUMPLE (6 de 12
        # veredictos en rojo en la corrida real del 5-sep-2026).
        contradice = _dice_cumple and _vb_up.startswith("NO CUMPLE")
        pendiente = _dice_cumple and _vb_up.startswith(("POR VERIFICAR", "POR CONFIRMAR"))
        if prof.get("cumple"):
            # El veredicto del evaluador cuenta los días por su cuenta; la fila
            # TOTAL DECLARADO de arriba los cuenta inclusivos. Si discrepan, la
            # celda antepone el verificado en vez de dejar dos cifras sueltas.
            _cumple = _sin_jerga(prof["cumple"])
            b.kv("¿EL PROFESIONAL CUMPLE?",
                 conciliar_conclusion(_cumple, t.get("dias"), len(exps) - sin_dias),
                 verdict="neg" if contradice else "pos",
                 valor_veredicto="POR VERIFICAR" if pendiente else _cumple)
        if vb:
            # `pos` sobre el TEXTO del backend: su "NO CUMPLE" se pinta rojo y su
            # "POR VERIFICAR" amarillo. Con `neg` un NO CUMPLE saldría VERDE.
            # No se concilia: esta línea ya la escribe el equipo evaluador con su
            # propia cifra (los días EFECTIVOS, no el total declarado).
            b.kv("⚠ Verificación del tiempo efectivo:" if contradice
                 else "Verificación del tiempo efectivo:", _sin_jerga(vb), verdict="pos")
        if prof.get("anios_adicionales"):
            b.kv("Años adicionales (Factor A):", prof["anios_adicionales"])
        b.blank()

    # ── PARTE 5 ──
    re_ = espejo.get("resumen_evaluacion", {})
    b.parte("PARTE 5: RESUMEN DE LA EVALUACIÓN")
    b.headers(["FACTOR", "CRITERIO", "FOLIO", "DETALLE / OBSERVACIONES", "PUNTAJE"])
    for fac in re_.get("factores", []):
        # Un factor sin puntaje NO deja la celda muda. `_recalcular_factor_a`
        # retira el puntaje heredado cuando la rúbrica no viaja estructurada
        # (`orquestador/etapas_reales.py`), y la celda en blanco al lado de un
        # total distinto de cero se leía como un error del archivo (E317 del job
        # Vitarte). Ahora dice lo que pasó, en amarillo de «por verificar».
        _pje = fac.get("puntaje")
        _pendiente = _pje in (None, "")
        _min = fac.get("puntaje_confirmado")
        _max = fac.get("puntaje_maximo_posible")
        # Un límite ausente no equivale a cero ni permite presentar un rango.
        if (_pendiente and isinstance(_min, (int, float))
                and isinstance(_max, (int, float))):
            _pje = f"{_min:g}–{_max:g}"
        b.row([fac.get("factor"), fac.get("criterio"), fac.get("folio"),
               fac.get("detalle"), "POR CONFIRMAR" if _pje in (None, "") else _pje],
              fmts={5: FMT_INT}, fills={5: FILL_PEND} if _pendiente else None)
    if re_.get("puntaje_total") is not None:
        b.row(["PUNTAJE TÉCNICO TOTAL", "", "", "", re_.get("puntaje_total")], bold=True, fmts={5: FMT_INT})
    else:
        _min = re_.get("puntaje_confirmado")
        _max = re_.get("puntaje_maximo_posible")
        _rango = f"{_min:g}–{_max:g}" if isinstance(_min, (int, float)) and isinstance(_max, (int, float)) else "POR VERIFICAR"
        b.row(["PUNTAJE TÉCNICO TOTAL", "", "",
               "POR VERIFICAR — total condicionado por factores pendientes",
               _rango], bold=True, verdicts={5: "pos"})
    # La NOTA se ARMA con lo que la tabla de arriba muestra. Antes se imprimía el
    # texto que venía redactado en el análisis y podía contradecirla a la vista
    # («Puntaje técnico total 80/100 (A=40…)» sobre una tabla que mostraba 40 y
    # el Factor A sin puntaje). Un resumen que no cuadra con su propia tabla
    # obliga a desconfiar del libro entero.
    b.kv("NOTA:", nota_parte5(re_.get("factores"), re_.get("puntaje_total")))


def generar_excel(espejo: dict, salida: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "CLAUDE"
    construir_hoja_evaluacion(ws, espejo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    return salida


if __name__ == "__main__":
    base = Path(__file__).resolve().parents[2]
    json_path = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "fixtures" / "trujillo" / "trujillo_espejo_full.json"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else base / "fixtures" / "trujillo" / "_generado_full.xlsx"
    espejo = json.loads(json_path.read_text(encoding="utf-8"))
    res = generar_excel(espejo, out_path)
    nprof = len(espejo.get("profesionales", []))
    nexp = sum(len(p.get("experiencias", [])) for p in espejo.get("profesionales", []))
    print(f"OK · {nprof} profesionales · {nexp} experiencias · {res}")
