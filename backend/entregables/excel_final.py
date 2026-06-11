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

import re
from datetime import date
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from reglas import anios, dias_efectivos_profesional, dias_inclusivos, restar_paralizaciones
from scripts.generar_excel import (
    AL_HEAD, AL_WRAP, BORDER, F_BOLD, F_CELL, F_HEAD, F_PARTE, F_PROF,
    FILL_BACKEND, FILL_CLAUDE, FILL_HEAD, FILL_PARTE, FILL_PROF,
    FMT_DEC, FMT_INT, construir_hoja_evaluacion,
)

Paralizaciones = dict[tuple[int, int], list[tuple[date, date]]]

# Paleta de fondos por profesional para la hoja Base de Datos (suaves, ciclan)
_PALETA_PROF = ["FFF2CC", "DDEBF7", "E2EFDA", "FCE4D6", "EDEDED", "D9E1F2",
                "FBE2D5", "E4DFEC"]


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
                e.get("fecha_inicial"), e.get("fecha_final"),
                e.get("dias"), e.get("meses"), e.get("anios"),
                e.get("cargo_ocupado"), e.get("incluye_covid"), e.get("traslape"),
                e.get("folio"), e.get("observaciones"),
            ]
            for i, v in enumerate(valores, start=1):
                c = ws.cell(r, i, v)
                c.font, c.border, c.alignment, c.fill = F_CELL, BORDER, AL_WRAP, fill
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


def construir_hoja_profesional(ws, prof: dict, paralizaciones: Paralizaciones) -> None:
    anchos = {"A": 52, "B": 14, "C": 14, "D": 10}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    n_prof = prof.get("n_prof")
    r = 1

    def banda(texto, font=F_PROF, fill=FILL_PROF, h=20):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, texto)
        c.font, c.fill = font, fill
        c.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = h
        r += 1

    def fila(hito, desde, hasta, dias_v, *, bold=False, backend=False):
        nonlocal r
        valores = [hito, desde, hasta, dias_v]
        for i, v in enumerate(valores, start=1):
            c = ws.cell(r, i, v)
            c.font = F_BOLD if bold else F_CELL
            c.border, c.alignment = BORDER, AL_WRAP
            if i == 4 and isinstance(v, (int, float)):
                c.number_format = FMT_INT
            if v not in (None, ""):
                c.fill = FILL_BACKEND if backend else FILL_CLAUDE
        r += 1

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
        titulo = f"EXPERIENCIA {n_exp}: {str(e.get('proyecto') or '')[:80]}"
        extra = " · ".join(x for x in [
            f"CUI {e['cui']}" if e.get("cui") else "",
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
            continue

        fila("Periodo certificado", ini.isoformat(), fin.isoformat(),
             dias_inclusivos(ini, fin))

        paral = paralizaciones.get((n_prof, n_exp), [])
        for k, (p_ini, p_fin) in enumerate(paral, start=1):
            fila(f"Paralización {k} de la obra (InfoObras)", p_ini.isoformat(),
                 p_fin.isoformat(), dias_inclusivos(p_ini, p_fin), backend=True)

        tramos = restar_paralizaciones((ini, fin), paral)
        for k, (t_ini, t_fin) in enumerate(tramos, start=1):
            fila(f"Tramo efectivo {k}", t_ini.isoformat(), t_fin.isoformat(),
                 dias_inclusivos(t_ini, t_fin), backend=bool(paral))
        efectivo = sum(dias_inclusivos(a, b) for a, b in tramos)
        fila(f"EFECTIVO EXPERIENCIA {n_exp}", "", "", efectivo, bold=True,
             backend=bool(paral))
        r += 1

        idx = len(periodos_validos)
        periodos_validos.append((ini, fin))
        if paral:
            paral_por_idx[idx] = paral

    # Resumen del profesional (Paso 5 completo, con fusión de traslapes ALT11)
    if periodos_validos:
        res = dias_efectivos_profesional(periodos_validos, paral_por_idx)
        banda("RESUMEN PASO 5 — DÍAS EFECTIVOS DEL PROFESIONAL", F_PARTE, FILL_PARTE, 18)
        fila("Días brutos (suma de certificados)", "", "", res.dias_brutos, bold=True)
        fila("(−) Paralizaciones de obra (InfoObras)", "", "", res.dias_paralizados,
             bold=True, backend=True)
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
) -> Path:
    """Construye el Excel final: CLAUDE + Base de Datos + 1 hoja por profesional.

    `paralizaciones`: {(n_prof, n_exp): [(inicio, fin), …]} — las ventanas de
    paralización de la obra de cada experiencia, resueltas por la etapa
    INFOOBRAS. Sin ellas, los cuadros muestran brutos = efectivos.
    """
    paralizaciones = paralizaciones or {}
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "CLAUDE"
    construir_hoja_evaluacion(ws, espejo)

    construir_hoja_base_datos(wb.create_sheet("Base de Datos"), espejo)

    for prof in espejo.get("profesionales", []):
        nombre = _nombre_hoja(prof.get("n_prof", 0), prof.get("cargo", ""))
        construir_hoja_profesional(wb.create_sheet(nombre), prof, paralizaciones)

    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    return salida
