"""
Normalización y expansión de abreviaturas de nombres de obra/proyecto.

COPIA EXACTA de `norm()` y `expandir_abrev()` (con su tabla `ABREV`) desde
`resolucion/cui.py`. Se extraen aquí para que otros módulos (la base local del
MEF, `base_mef.py`) los reutilicen sin arrastrar todo `cui.py` ni tocar la red.

En una fase posterior `cui.py` pasará a IMPORTAR de este módulo; por ahora ambos
conviven con las definiciones duplicadas (no se edita `cui.py`).

Nota de diseño — `norm_basica()`: NO se añade. `norm()` de `cui.py` es genérica
(NFKD → ascii → mayúsculas → colapsar espacios); no trae lógica específica de
certificados que estorbe a los nombres del MEF, así que un segundo normalizador
sería ruido. La limpieza de puntuación propia de los nombres MEF (comas, guiones
y paréntesis del Banco de Inversiones) vive en `base_mef.py`, donde se necesita.
"""
from __future__ import annotations

import re
import unicodedata


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


ABREV = [
    (re.compile(r"\bEE\.?\s?SS\.?\b", re.I), "Establecimientos de Salud"),
    (re.compile(r"\bC\.\s?S\.?\b", re.I), "Centro de Salud"),
    (re.compile(r"\bE\.\s?S\.?\b", re.I), "Establecimiento de Salud"),
    (re.compile(r"\bP\.\s?S\.?\b", re.I), "Puesto de Salud"),
    (re.compile(r"\bCMI\b", re.I), "Centro Materno Infantil"),
    (re.compile(r"\bH\.\s?R\.?\b", re.I), "Hospital Regional"),
    (re.compile(r"\bH\.\s(?=\w)", re.I), "Hospital "),
]


def expandir_abrev(t: str) -> str:
    for pat, full in ABREV:
        t = pat.sub(full, t)
    return t
