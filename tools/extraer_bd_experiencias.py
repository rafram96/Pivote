"""
extraer_bd_experiencias.py — Extrae un JSON espejo desde el Excel BD_Experiencias
(formato Paso 3: una hoja, filas planas, 1 fila = 1 experiencia, agrupadas por
'N° Prof'). Distinto al new_format (hoja CLAUDE) y al de Trujillo.

Produce la estructura que consume el matcher / la métrica:
  {"_meta": {...}, "profesionales": [{"cargo","nombre","n_prof","experiencias":[...]}]}

Cada experiencia trae: proyecto, fecha_inicial/final (ISO), entidad_emisora (con el
RUC embebido para el cruce RUC), folio, ubicacion, nivel, area_m2, monto.

Uso: python tools/extraer_bd_experiencias.py <fuente.xlsx> [destino.json]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path(r"C:\Users\Holbi\Downloads\BD_Experiencias_Paso3_CP02-2025 (1).xlsx")
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else \
    Path(__file__).resolve().parents[1] / "fixtures" / "cp02_lircay" / "bd_experiencias_espejo.json"

# índices 0-based de columnas (ver inspección del Excel)
C_NPROF, C_CARGO, C_NOMBRE, C_DNI = 1, 2, 3, 4
C_EMISORA, C_RUC = 9, 10
C_CARGO_DES, C_OBRA, C_CONTRATANTE, C_UBIC, C_NIVEL, C_AREA, C_MONTO = 13, 14, 15, 16, 17, 18, 19
C_INI, C_FIN, C_FIRMANTE, C_EMISION, C_FOLIO = 20, 21, 22, 23, 24


def s(v):
    if v is None:
        return None
    t = str(v).strip()
    return t or None


def iso_fecha(v):
    """DD/MM/YYYY o datetime → 'YYYY-MM-DD'."""
    if v is None:
        return None
    if not isinstance(v, str) and hasattr(v, "year"):  # datetime/date
        return f"{v.year:04d}-{v.month:02d}-{v.day:02d}"
    t = str(v).strip()
    m = re.match(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", t)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    return t[:10] if m else None


def main() -> int:
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb.active
    profs: dict[str, dict] = {}
    orden: list[str] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[C_OBRA] is None and row[C_NPROF] is None:
            continue
        np = s(row[C_NPROF]) or s(row[C_NOMBRE]) or "?"
        np = re.sub(r"\.0$", "", np)
        if np not in profs:
            profs[np] = {
                "n_prof": np,
                "cargo": s(row[C_CARGO]),
                "nombre": s(row[C_NOMBRE]),
                "dni": s(row[C_DNI]),
                "experiencias": [],
            }
            orden.append(np)
        emisora = s(row[C_EMISORA]) or ""
        ruc = s(row[C_RUC]) or ""
        entidad_emisora = (f"{emisora} RUC {ruc}".strip() if ruc else emisora) or None
        if s(row[C_OBRA]):  # solo filas con obra
            profs[np]["experiencias"].append({
                "proyecto": s(row[C_OBRA]),
                "cargo_desempenado": s(row[C_CARGO_DES]),
                "entidad_contratante": s(row[C_CONTRATANTE]),
                "entidad_emisora": entidad_emisora,
                "ubicacion": s(row[C_UBIC]),
                "nivel": s(row[C_NIVEL]),
                "area_m2": s(row[C_AREA]),
                "monto": s(row[C_MONTO]),
                "fecha_inicial": iso_fecha(row[C_INI]),
                "fecha_final": iso_fecha(row[C_FIN]),
                "firmante": s(row[C_FIRMANTE]),
                "folio": s(row[C_FOLIO]),
            })

    espejo = {
        "_meta": {
            "fuente": SRC.name,
            "concurso": "CP-02-2025 (Lircay / Huancavelica)",
            "formato": "BD_Experiencias_Paso3 (filas planas)",
            "n_profesionales": len(orden),
            "n_experiencias": sum(len(profs[k]["experiencias"]) for k in orden),
        },
        "profesionales": [profs[k] for k in orden],
    }
    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(json.dumps(espejo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {DST}")
    print(f"  profesionales: {espejo['_meta']['n_profesionales']}  ·  "
          f"experiencias: {espejo['_meta']['n_experiencias']}")
    for p in espejo["profesionales"]:
        print(f"    [{p['n_prof']:>2}] {(p['cargo'] or '')[:34]:34} · {len(p['experiencias'])} exp · "
              f"{(p['nombre'] or '')[:28]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
