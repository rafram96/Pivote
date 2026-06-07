"""
Lectura y resumen de los 3 Excels que Manuel produjo con Claude.

Estrategia: leer con header=None (raw) porque los Excels tienen filas-título
encima del header real. Mostrar primeras filas como matriz para entender
estructura, luego conteo de no-nulos por columna.

Uso:
    venv/Scripts/python.exe src/tools/leer_excels.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Forzar UTF-8 en stdout (Windows console usa cp1252 por default)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[2] / "docs" / "files"

FILES = [
    ("Paso 1 - Cuadro_Personal_Clave (bases)", "Cuadro_Personal_Clave_CP02-2025.xlsx"),
    ("Paso 3 - BD_Experiencias (propuesta)",   "BD_Experiencias_Paso3_CP02-2025 (1).xlsx"),
    ("Paso 4 - Evaluacion_RTM (cruce)",        "Evaluacion_RTM_Paso4_CP02-2025 (1).xlsx"),
]

PREVIEW_ROWS = 6
SAMPLE_VAL_LEN = 70


def fmt(v, mx: int = SAMPLE_VAL_LEN) -> str:
    """repr compacto de un valor."""
    if pd.isna(v):
        return "—"
    s = repr(v) if not isinstance(v, str) else v.replace("\n", "⏎")
    return s if len(s) <= mx else s[: mx - 1] + "…"


def reporte(label: str, fname: str) -> None:
    path = BASE / fname
    print("=" * 100)
    print(label)
    print(f"  archivo: {fname}")
    print("=" * 100)

    if not path.exists():
        print(f"  NO EXISTE: {path}")
        return

    sheets = pd.read_excel(path, sheet_name=None, header=None)

    for sn, df in sheets.items():
        print(f"\n  Hoja: {sn!r}  ·  {df.shape[0]} filas × {df.shape[1]} columnas\n")

        # Preview: primeras N filas como matriz columna por columna
        print(f"  PREVIEW (primeras {PREVIEW_ROWS} filas):")
        for r in range(min(PREVIEW_ROWS, df.shape[0])):
            print(f"    fila {r}:")
            for c in range(df.shape[1]):
                val = df.iat[r, c]
                print(f"       [c{c}] {fmt(val, 90)}")

        # Conteo de no-nulos por columna (en todo el dataset)
        print(f"\n  CONTEO no-nulos por columna ({df.shape[0]} filas):")
        for c in range(df.shape[1]):
            nn = int(df.iloc[:, c].notna().sum())
            samples = df.iloc[:, c].dropna().head(2).tolist()
            sample_str = " || ".join(fmt(s, 45) for s in samples) if samples else "—"
            print(f"    c{c}: {nn:3d}/{df.shape[0]:3d}    {sample_str}")

    print()


def main() -> None:
    for label, fname in FILES:
        reporte(label, fname)


if __name__ == "__main__":
    main()
