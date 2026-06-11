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
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

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
        self._band(text, F_PARTE, FILL_PARTE, 24)
        self.blank()

    def profblock(self, text):
        self._band(text, F_PROF, FILL_PROF, 22)

    def subtitle(self, text):
        self._band(text, F_SUB, FILL_SUB, 18)

    def headers(self, values):
        ws = self.ws
        for i, v in enumerate(values, start=1):
            c = ws.cell(self.r, i, v)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
        ws.row_dimensions[self.r].height = 32
        self.r += 1

    def row(self, values, bold=False, fmts=None, backend_cols=None):
        """Escribe una fila de datos. Las celdas con valor se resaltan según
        origen: amarillo (Claude) por defecto; naranja si la columna está en
        `backend_cols` (la verifica/llena el backend on-prem)."""
        ws = self.ws
        fmts = fmts or {}
        backend_cols = backend_cols or set()
        for i, v in enumerate(values, start=1):
            c = ws.cell(self.r, i, v)
            c.font = F_BOLD if bold else F_CELL
            c.border, c.alignment = BORDER, AL_WRAP
            if i in fmts and isinstance(v, (int, float)):
                c.number_format = fmts[i]
            if v not in (None, ""):
                c.fill = FILL_BACKEND if i in backend_cols else FILL_CLAUDE
        self.r += 1

    def kv(self, label, value, fmt=None):
        ws = self.ws
        ws.cell(self.r, 1, label).font = F_BOLD
        ws.merge_cells(start_row=self.r, start_column=2, end_row=self.r, end_column=NCOLS)
        c = ws.cell(self.r, 2, value)
        c.font, c.alignment = F_CELL, AL_WRAP
        if fmt and isinstance(value, (int, float)):
            c.number_format = fmt
        if value not in (None, ""):
            c.fill = FILL_CLAUDE
        self.r += 1

    def leyenda(self):
        ws = self.ws
        ws.cell(self.r, 1, "Leyenda:").font = F_BOLD
        ws.merge_cells(start_row=self.r, start_column=2, end_row=self.r, end_column=4)
        a = ws.cell(self.r, 2, "Amarillo = llenado por Claude")
        a.fill, a.font, a.border, a.alignment = FILL_CLAUDE, F_CELL, BORDER, AL_TITLE
        ws.merge_cells(start_row=self.r, start_column=5, end_row=self.r, end_column=9)
        b = ws.cell(self.r, 5, "Naranja = verificado/enriquecido por el backend on-prem")
        b.fill, b.font, b.border, b.alignment = FILL_BACKEND, F_CELL, BORDER, AL_TITLE
        self.r += 1

    def blank(self):
        self.r += 1


def construir_hoja_evaluacion(ws, espejo: dict) -> None:
    """Construye la hoja de evaluación (5 partes) en un worksheet existente.
    La usa este script (hoja única) y `entregables/excel_final.py` (hoja CLAUDE
    dentro del Excel final con Base de Datos + hojas por profesional)."""
    for col, w in WIDTHS.items():
        ws.column_dimensions[col].width = w
    b = Builder(ws)
    p = espejo.get("postor", {})

    # ── Encabezado ──
    b.kv("Postor:", p.get("detalle") or espejo["_meta"].get("postor", ""))
    b.kv("Concurso:", espejo["_meta"].get("concurso", ""))
    b.leyenda()
    b.blank()

    # ── PARTE 1 ──
    b.parte("PARTE 1: FORMULARIOS DEL POSTOR")
    b.headers(["ANEXO", "DESCRIPCIÓN", "OBSERVACIÓN", "FOLIO"])
    for f in p.get("formularios", []):
        b.row([f.get("anexo", ""), f.get("descripcion", ""), f.get("observacion", ""), f.get("folio", "")])
    b.blank()
    oe = p.get("oferta_economica", {})
    if oe:
        b.headers(["", "CUANTÍA", "LÍMITE INFERIOR", "PROPUESTA", "DETALLE"])
        b.row(["Monto", oe.get("cuantia"), oe.get("limite_inferior"), oe.get("propuesta"), oe.get("detalle", "")],
              fmts={2: FMT_MONEY, 3: FMT_MONEY, 4: FMT_MONEY})
    b.blank()

    # ── PARTE 2 ──
    b.parte("PARTE 2: EXPERIENCIA DEL POSTOR")
    b.headers(["No", "CLIENTE / EMISOR", "CONTRATO/OS/FACTURA", "PROYECTO", "TIPO ACREDITACIÓN",
               "MONTO", "% OBJETO", "LE CORRESPONDE", "ACREDITA", "FOLIO",
               "¿ÚLTIMOS 20 AÑOS?", "¿TIPO SOLICITADO?", "OBSERVACIONES"])
    m2 = {6: FMT_MONEY, 7: FMT_DEC, 8: FMT_MONEY, 9: FMT_MONEY}
    for e in p.get("experiencia_postor", []):
        b.row([e.get("n"), e.get("cliente"), e.get("contrato"), e.get("proyecto"), e.get("tipo_acreditacion"),
               e.get("monto"), e.get("pct_objeto"), e.get("le_corresponde"), e.get("acredita"), e.get("folio"),
               e.get("ultimos_20_anios"), e.get("tipo_solicitado"), e.get("observaciones")], fmts=m2)
    tot = p.get("experiencia_postor_total", {})
    if tot:
        b.row(["", "TOTAL", "", "", "", "", "", tot.get("le_corresponde"), tot.get("acredita"), "", "", "", ""],
              bold=True, fmts={8: FMT_MONEY, 9: FMT_MONEY})
    if p.get("postor_cumple"):
        b.kv("¿POSTOR CUMPLE 3.4?", p["postor_cumple"])
    b.blank()

    # ── PARTE 3 + 4 ──
    b.parte("PARTE 3 Y 4: INFORMACIÓN GENERAL Y EXPERIENCIA DE CADA PROFESIONAL")
    P4_HEAD = ["No", "ENTIDAD/EMPRESA EMISORA", "PROYECTO U OBRA", "TIPO DOC", "NOMBRE EMISOR",
               "CARGO EMISOR", "¿VÁLIDO EMITIR?", "FECHA INI", "FECHA FIN", "FECHA EMISIÓN", "FOLIO",
               "DÍAS", "MESES", "AÑOS", "¿ANT. COLEG.?", "CARGO OCUPÓ", "¿CARGO BASES?",
               "¿FUNCIONES?", "¿ANTES CULMINAR?", "¿COVID?", "¿TIPO OBRA?", "OBSERVACIONES"]
    m4 = {12: FMT_INT, 13: FMT_DEC, 14: FMT_DEC}
    for prof in espejo.get("profesionales", []):
        b.profblock(f"PROFESIONAL {prof.get('n_prof')}: {prof.get('cargo', '')}")
        b.headers(["No", "CARGO", "DETALLE", "INFORMACIÓN DE LA PROPUESTA", "FOLIO", "PUNTAJE"])
        b.row([prof.get("n_prof"), prof.get("cargo"), "NOMBRE DEL PROFESIONAL", prof.get("nombre"), prof.get("folio_nombre"), ""])
        b.row(["", "", "TÍTULO PROFESIONAL", prof.get("titulo"), prof.get("folio_titulo"), ""])
        b.row(["", "", "¿La profesión es la indicada?", prof.get("profesion_valida"), "", ""])
        b.row(["", "", "No de COLEGIATURA / Fecha", prof.get("colegiatura"), prof.get("folio_colegiatura"), ""])
        b.row(["", "", "B. CERTIFICACIONES", prof.get("certificaciones"), "", ""])
        b.blank()
        b.subtitle(f"PARTE 4 - EXPERIENCIA DEL PROFESIONAL: {prof.get('cargo', '')}")
        b.headers(P4_HEAD)
        for e in prof.get("experiencias", []):
            b.row([e.get("n"), e.get("entidad_emisora"), e.get("proyecto"), e.get("tipo_documento"),
                   e.get("nombre_emisor"), e.get("cargo_emisor"), e.get("cargo_valido_emitir"),
                   e.get("fecha_inicial"), e.get("fecha_final"), e.get("fecha_emision"), e.get("folio"),
                   e.get("dias"), e.get("meses"), e.get("anios"), e.get("anterior_colegiatura"),
                   e.get("cargo_ocupado"), e.get("cargo_bases_valido"), e.get("funciones_similares"),
                   e.get("cert_antes_culminar"), e.get("incluye_covid"), e.get("tipo_obra_valido"),
                   e.get("observaciones")], fmts=m4)
        t = prof.get("total", {})
        b.row(["", "", "", "", "", "", "", "", "", "", "TOTAL",
               t.get("dias"), t.get("meses"), t.get("anios"), "", "", "", "", "", "", "", ""],
              bold=True, fmts=m4)
        if prof.get("cumple"):
            b.kv("¿EL PROFESIONAL CUMPLE?", prof["cumple"])
        if prof.get("anios_adicionales"):
            b.kv("Años adicionales (Factor A):", prof["anios_adicionales"])
        b.blank()

    # ── PARTE 5 ──
    re_ = espejo.get("resumen_evaluacion", {})
    b.parte("PARTE 5: RESUMEN DE LA EVALUACIÓN")
    b.headers(["FACTOR", "CRITERIO", "FOLIO", "DETALLE / OBSERVACIONES", "PUNTAJE"])
    for fac in re_.get("factores", []):
        b.row([fac.get("factor"), fac.get("criterio"), fac.get("folio"), fac.get("detalle"), fac.get("puntaje")],
              fmts={5: FMT_INT})
    if re_.get("puntaje_total") is not None:
        b.row(["PUNTAJE TÉCNICO TOTAL", "", "", "", re_.get("puntaje_total")], bold=True, fmts={5: FMT_INT})
    if re_.get("nota"):
        b.kv("NOTA:", re_["nota"])


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
