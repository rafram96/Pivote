"""
Excel FINAL enriquecido — el entregable del backend (formato definitivo
confirmado por el cliente 2026-06-10):

  1. Hoja **CLAUDE** — la extracción/evaluación (5 partes, igual al de la skill).
  2. Hoja **Base de Datos** — todas las experiencias consolidadas, cargo al que
     postula en la primera columna, con auto-filtro y un color de fondo
     distinto por profesional (convención de la skill `propuestas` de Manuel).
  3. **Una hoja por profesional** con el CUADRO DE HITOS de sus experiencias:
     periodo certificado → paralizaciones de la obra (InfoObras) → tramos
     efectivos → resumen brutos/paralizados/traslapes/EFECTIVOS (Paso 5,
     calculado con `reglas.calculo` — el mismo motor con goldens de las hojas
     manuales JEFE/Estructura).

Las paralizaciones llegan del enriquecimiento (etapa INFOOBRAS); si una
experiencia no las tiene, su cuadro muestra brutos = efectivos.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from reglas import (
    anios, dias_efectivos_profesional, dias_inclusivos, periodo_fechas,
    restar_paralizaciones,
)
from scripts.generar_excel import (
    AL_HEAD, AL_WRAP, BORDER, F_BOLD, F_CELL, F_HEAD, F_PARTE, F_PROF,
    FILL_BACKEND, FILL_CLAUDE, FILL_HEAD, FILL_PARTE, FILL_PROF,
    FMT_DEC, FMT_FECHA, FMT_INT, construir_hoja_evaluacion, fecha_excel,
)

Paralizaciones = dict[tuple[int, int], list[tuple[date, date]]]

# Paleta de fondos por profesional para la hoja Base de Datos (suaves, ciclan)
_PALETA_PROF = ["FFF2CC", "DDEBF7", "E2EFDA", "FCE4D6", "EDEDED", "D9E1F2",
                "FBE2D5", "E4DFEC"]

# Amarillo para resaltar las valorizaciones que caen dentro del certificado
FILL_VALOR = PatternFill("solid", fgColor="FFFF00")
FMT_SOLES = '#,##0.00'
FMT_PCT = '0.00%'

_MES_ES = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO",
           6: "JUNIO", 7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE",
           10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}


def _mes_en_rango(anio: int, mes: int, ini: Optional[date], fin: Optional[date]) -> bool:
    """True si el mes (anio, mes) solapa con el periodo del certificado [ini, fin]."""
    if not (ini and fin and anio and mes):
        return False
    m_ini = date(anio, mes, 1)
    m_fin = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return m_ini <= fin and m_fin >= ini


def _fecha_iso(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) == 10:
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _nombre_hoja(n_prof: int, cargo: str) -> str:
    """Nombre de hoja Excel válido (≤31 chars, sin caracteres prohibidos)."""
    limpio = re.sub(r'[\\/*?:\[\]]', "", cargo or "").strip()
    return f"P{n_prof} {limpio}"[:31].rstrip()


# ── Hoja 2 · Base de Datos ───────────────────────────────────────────────────

_BD_HEAD = ["CARGO AL QUE POSTULA", "N° PROF", "PROFESIONAL", "N° EXP",
            "ENTIDAD / EMPRESA EMISORA", "PROYECTO U OBRA", "CUI",
            "FECHA INICIAL", "FECHA FINAL", "DÍAS", "MESES", "AÑOS",
            "CARGO OCUPADO", "¿COVID?", "¿TRASLAPE?", "FOLIO", "OBSERVACIONES"]
_BD_WIDTHS = [34, 8, 28, 7, 34, 50, 10, 12, 12, 8, 8, 8, 28, 9, 11, 10, 50]


def construir_hoja_base_datos(ws, espejo: dict) -> int:
    """Construye la hoja "Base de Datos". Devuelve el nº de filas de datos."""
    for i, w in enumerate(_BD_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for i, h in enumerate(_BD_HEAD, start=1):
        c = ws.cell(1, i, h)
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
    ws.row_dimensions[1].height = 30

    r = 2
    for idx, prof in enumerate(espejo.get("profesionales", [])):
        fill = PatternFill("solid", fgColor=_PALETA_PROF[idx % len(_PALETA_PROF)])
        for e in prof.get("experiencias", []):
            valores = [
                prof.get("cargo"), prof.get("n_prof"), prof.get("nombre"), e.get("n"),
                e.get("entidad_emisora"), e.get("proyecto"), e.get("cui"),
                fecha_excel(e.get("fecha_inicial")), fecha_excel(e.get("fecha_final")),
                e.get("dias"), e.get("meses"), e.get("anios"),
                e.get("cargo_ocupado"), e.get("incluye_covid"), e.get("traslape"),
                e.get("folio"), e.get("observaciones"),
            ]
            for i, v in enumerate(valores, start=1):
                c = ws.cell(r, i, v)
                c.font, c.border, c.alignment, c.fill = F_CELL, BORDER, AL_WRAP, fill
                if i in (8, 9) and isinstance(v, date):
                    c.number_format = FMT_FECHA
                if i == 10 and isinstance(v, (int, float)):
                    c.number_format = FMT_INT
                if i in (11, 12) and isinstance(v, (int, float)):
                    c.number_format = FMT_DEC
            r += 1

    ws.auto_filter.ref = f"A1:{get_column_letter(len(_BD_HEAD))}{max(r - 1, 1)}"
    ws.freeze_panes = "A2"
    return r - 2


# ── Hojas por profesional · cuadro de hitos ──────────────────────────────────

_HITO_HEAD = ["HITO", "DESDE", "HASTA", "DÍAS"]


def construir_hoja_profesional(
    ws, prof: dict, paralizaciones: Paralizaciones,
    cuis: Optional[dict] = None,
    fichas: Optional[dict] = None,
    revisiones: Optional[dict] = None,
) -> None:
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    # A:D = cuadro de hitos (izquierda) · F:J = ficha de obra + valorizaciones
    anchos = {"A": 52, "B": 14, "C": 14, "D": 10, "E": 2,
              "F": 5, "G": 18, "H": 14, "I": 18, "J": 14}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    n_prof = prof.get("n_prof")
    r = 1

    # ancho útil (caracteres aprox.) de la banda combinada A:D, para envolver
    # títulos largos sin truncarlos.
    _ancho_banda = sum({"A": 52, "B": 14, "C": 14, "D": 10}.values())

    def banda(texto, font=F_PROF, fill=FILL_PROF, h=20):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, texto)
        c.font, c.fill = font, fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
        # altura proporcional al nº de líneas que ocupará el texto envuelto
        lineas = max(1, -(-len(str(texto)) // _ancho_banda))  # ceil
        ws.row_dimensions[r].height = max(h, lineas * 15 + 4)
        r += 1

    def fila(hito, desde, hasta, dias_v, *, bold=False, backend=False):
        nonlocal r
        valores = [hito, desde, hasta, dias_v]
        for i, v in enumerate(valores, start=1):
            c = ws.cell(r, i, v)
            c.font = F_BOLD if bold else F_CELL
            c.border, c.alignment = BORDER, AL_WRAP
            if i in (2, 3) and isinstance(v, date):
                c.number_format = FMT_FECHA   # presentación dd/mm/yy
            if i == 4 and isinstance(v, (int, float)):
                c.number_format = FMT_INT
            if v not in (None, ""):
                c.fill = FILL_BACKEND if backend else FILL_CLAUDE
        r += 1

    def render_obra(top: int, fx: dict, ini, fin) -> int:
        """Ficha de la obra + TODAS sus valorizaciones, en columnas F:J desde la
        fila `top`. Resalta en amarillo los meses dentro del periodo del
        certificado. Devuelve la última fila usada."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "OBRA EN INFOOBRAS (origen del análisis)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def kv(label, value, fmt=None):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=7)
            cl = ws.cell(rr, 6, label); cl.font, cl.border = F_BOLD, BORDER
            ws.merge_cells(start_row=rr, start_column=8, end_row=rr, end_column=10)
            cv = ws.cell(rr, 8, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fmt and isinstance(value, (int, float, date)):
                cv.number_format = fmt
            rr += 1

        kv("Código InfoObras", fx.get("codigo_infobras") or "—")
        kv("CUI", fx.get("cui") or "—")
        kv("Estado de obra", fx.get("estado") or "—")
        kv("Monto ejecutado (S/)", fx.get("monto") if fx.get("monto") is not None else "—", FMT_SOLES)
        kv("Inicio de obra", _fecha_iso(fx.get("fecha_inicio")) or "—", FMT_FECHA)
        kv("Fin de obra", _fecha_iso(fx.get("fecha_fin")) or "—", FMT_FECHA)
        rr += 1

        vals = sorted(fx.get("valorizaciones") or [],
                      key=lambda v: (v.get("anio") or 0, v.get("mes") or 0), reverse=True)
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "VALORIZACIONES — en amarillo, las del periodo del certificado")
        c.font, c.fill = F_PARTE, FILL_PARTE
        c.alignment = Alignment(vertical="center", wrap_text=True)
        rr += 1
        for i, h in enumerate(["N°", "AÑO / MES", "AVANCE FÍSICO REAL",
                               "VALORIZADO REAL (S/)", "ESTADO"], start=6):
            cc = ws.cell(rr, i, h)
            cc.font, cc.fill, cc.border, cc.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
        rr += 1
        for n, v in enumerate(vals, start=1):
            anio, mes = v.get("anio") or 0, v.get("mes") or 0
            resaltar = _mes_en_rango(anio, mes, ini, fin)
            celdas = [n, f"{anio} / {_MES_ES.get(mes, mes)}",
                      v.get("fisico_real"), v.get("valorizado_real"), v.get("estado") or ""]
            for i, val in enumerate(celdas, start=6):
                cc = ws.cell(rr, i, val)
                cc.font, cc.border, cc.alignment = F_CELL, BORDER, AL_WRAP
                if i == 8 and isinstance(val, (int, float)):
                    cc.number_format = FMT_PCT
                if i == 9 and isinstance(val, (int, float)):
                    cc.number_format = FMT_SOLES
                if resaltar:
                    cc.fill = FILL_VALOR
            rr += 1
        if not vals:
            ws.cell(rr, 6, "Sin valorizaciones registradas en InfoObras").font = F_CELL
            rr += 1
        return rr - 1

    def render_revision(top: int, motivo: str) -> int:
        """Bloque para una experiencia que NO se cruzó: explica por qué quedó en
        revisión humana, en vez de dejar la columna de la obra vacía."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "EXPERIENCIA EN REVISIÓN")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr + 3, end_column=10)
        c = ws.cell(rr, 6, f"{str(motivo).capitalize()}.\n\nAcción: confirmar la obra "
                           f"o pegar el CUI correcto en el panel para completar el cruce.")
        c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
        rr += 4
        return rr - 1

    banda(f"PROFESIONAL {n_prof}: {prof.get('cargo', '')}")
    ws.cell(r, 1, f"Nombre: {prof.get('nombre') or '—'}").font = F_BOLD; r += 1
    ws.cell(r, 1, f"Colegiatura: {prof.get('colegiatura') or '—'}").font = F_CELL; r += 1
    r += 1
    banda("CUADRO DE HITOS DE LAS EXPERIENCIAS (días efectivos — Paso 5)",
          F_PARTE, FILL_PARTE, 18)

    periodos_validos: list[tuple[date, date]] = []
    paral_por_idx: dict[int, list[tuple[date, date]]] = {}

    for e in prof.get("experiencias", []):
        n_exp = e.get("n")
        ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
        fx = fichas.get((n_prof, n_exp))
        r_top = r  # fila del título: el bloque de obra (F:J) arranca alineado aquí
        titulo = f"EXPERIENCIA {n_exp}: {str(e.get('proyecto') or '')}"  # nombre VERBATIM, sin truncar
        # CUI resuelto por el backend (etapa InfoObras); si no, el del espejo
        cui = cuis.get((n_prof, n_exp)) or (fx or {}).get("cui") or e.get("cui")
        extra = " · ".join(x for x in [
            f"CUI {cui}" if cui else "",
            f"folio {e['folio']}" if e.get("folio") else ""] if x)
        banda(titulo + (f"  ({extra})" if extra else ""), F_HEAD, FILL_HEAD, 16)

        for i, h in enumerate(_HITO_HEAD, start=1):
            c = ws.cell(r, i, h)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
        r += 1

        if not (ini and fin):
            fila("Fechas no computables (parciales o POR VERIFICAR) — revisar espejo",
                 e.get("fecha_inicial"), e.get("fecha_final"), None)
            r += 1
        else:
            fila("Periodo certificado", ini, fin, dias_inclusivos(ini, fin))

            # periodos inactivos de la obra (dict con tipo, o tupla legacy=paralizado)
            # SOLO los que caen dentro del periodo que supervisó este profesional;
            # InfoObras trae las paralizaciones de toda la vida de la obra, pero las
            # de antes/después de su ventana no le aplican. Se recortan a [ini, fin].
            periodos = paralizaciones.get((n_prof, n_exp), [])
            n_par = n_gap = n_fv = 0
            tuplas: list[tuple[date, date]] = []
            for p in periodos:
                p_ini, p_fin = periodo_fechas(p)
                c_ini, c_fin = max(p_ini, ini), min(p_fin, fin)
                if c_fin < c_ini:
                    continue  # paralización fuera del periodo del profesional → se omite
                tuplas.append((c_ini, c_fin))
                tipo = p.get("tipo", "paralizado") if isinstance(p, dict) else "paralizado"
                if tipo == "sin_valorizacion":
                    n_gap += 1
                    etiqueta = f"Sin valorización {n_gap} — obra parada (InfoObras)"
                elif tipo == "fuera_de_ventana":
                    n_fv += 1
                    etiqueta = f"Sin valorización {n_fv} — fuera del periodo de la obra (InfoObras)"
                else:
                    n_par += 1
                    etiqueta = f"Paralización {n_par} de la obra (InfoObras)"
                fila(etiqueta, c_ini, c_fin, dias_inclusivos(c_ini, c_fin), backend=True)

            tramos = restar_paralizaciones((ini, fin), tuplas)
            for k, (t_ini, t_fin) in enumerate(tramos, start=1):
                fila(f"Tramo efectivo {k}", t_ini, t_fin,
                     dias_inclusivos(t_ini, t_fin), backend=bool(tuplas))
            efectivo = sum(dias_inclusivos(a, b) for a, b in tramos)
            fila(f"EFECTIVO EXPERIENCIA {n_exp}", "", "", efectivo, bold=True,
                 backend=bool(tuplas))
            r += 1

            idx = len(periodos_validos)
            periodos_validos.append((ini, fin))
            if tuplas:
                paral_por_idx[idx] = tuplas

        # lado derecho: ficha de la obra; si la experiencia está en revisión, un
        # bloque que lo explica (en vez de dejar la columna vacía).
        if fx:
            r_right = render_obra(r_top, fx, ini, fin)
            r = max(r, r_right + 1)
        elif (n_prof, n_exp) in revisiones:
            r_right = render_revision(r_top, revisiones[(n_prof, n_exp)])
            r = max(r, r_right + 1)

    # Resumen del profesional (Paso 5 completo, con fusión de traslapes ALT11)
    if periodos_validos:
        res = dias_efectivos_profesional(periodos_validos, paral_por_idx)
        banda("RESUMEN PASO 5 — DÍAS EFECTIVOS DEL PROFESIONAL", F_PARTE, FILL_PARTE, 18)
        fila("Días brutos (suma de certificados)", "", "", res.dias_brutos, bold=True)
        fila("(−) Periodos sin avance en obra (paralización / sin valorización)", "", "",
             res.dias_paralizados, bold=True, backend=True)
        fila("(−) Traslapes entre experiencias (ALT11)", "", "", res.dias_traslape,
             bold=True, backend=True)
        fila("DÍAS EFECTIVOS", "", "", res.dias_efectivos, bold=True, backend=True)
        c = ws.cell(r, 1, "AÑOS EFECTIVOS (días/365)")
        c.font = F_BOLD
        c2 = ws.cell(r, 4, round(anios(res.dias_efectivos), 2))
        c2.font, c2.fill, c2.border = F_BOLD, FILL_BACKEND, BORDER
        c2.number_format = FMT_DEC


# ── Entregable completo ──────────────────────────────────────────────────────

def generar_excel_final(
    espejo: dict,
    salida: Path,
    paralizaciones: Optional[Paralizaciones] = None,
    cuis: Optional[dict] = None,
    fichas: Optional[dict] = None,
    revisiones: Optional[dict] = None,
) -> Path:
    """Construye el Excel final: CLAUDE + Base de Datos + 1 hoja por profesional.

    `paralizaciones`: {(n_prof, n_exp): [(inicio, fin), …]} — las ventanas de
    paralización de la obra de cada experiencia, resueltas por la etapa
    INFOOBRAS. Sin ellas, los cuadros muestran brutos = efectivos.
    `cuis`: {(n_prof, n_exp): "2418877"} — el CUI que el backend resolvió por
    experiencia (la etapa InfoObras). Sin él, se usa el CUI del espejo si existe.
    `fichas`: {(n_prof, n_exp): {codigo_infobras, cui, estado, monto,
    fecha_inicio, fecha_fin, valorizaciones:[…]}} — la ficha de la obra y todas
    sus valorizaciones, para el bloque de la derecha en la hoja del profesional.
    """
    paralizaciones = paralizaciones or {}
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "CLAUDE"
    construir_hoja_evaluacion(ws, espejo)

    construir_hoja_base_datos(wb.create_sheet("Base de Datos"), espejo)

    for prof in espejo.get("profesionales", []):
        nombre = _nombre_hoja(prof.get("n_prof", 0), prof.get("cargo", ""))
        construir_hoja_profesional(wb.create_sheet(nombre), prof, paralizaciones,
                                   cuis, fichas, revisiones)

    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    return salida
