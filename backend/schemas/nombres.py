"""Nombres de los entregables que descarga el evaluador (Excel y ZIP).

Antes se armaban con el `analisis_id` crudo del espejo — un string LIBRE que
inventa la skill y que no tiene formato definido:

    Formato_Evaluacion_divino-nino-2026-07-14.xlsx
    InfoObras_cp001-2025-mdh-huachocolpa.zip

Largos, con la fecha o el código del procedimiento metidos dentro, y distintos
entre corridas del mismo concurso. Ahora:

    Analisis_huachocolpa_cons-vial.xlsx
    Analisis_huachocolpa_cons-vial.zip

El **postor va en el nombre** a propósito: el flujo del Comité es comparar varios
postores del MISMO concurso, y sin él los dos Excel colisionan en la carpeta de
Descargas (el segundo cae como "… (1).xlsx").

De dónde sale el slug del concurso, en orden:
  1. `_meta.slug` — lo emite la skill, que es quien leyó las bases y sabe cuál es
     el nombre corto con criterio. Es la vía buena.
  2. heurística sobre el `analisis_id` — fallback para los espejos que no lo
     traen (todos los anteriores a esta versión). Ver `_slug_desde_id`.

Nada de esto toca los archivos en disco (siguen siendo `{job_id}.final.xlsx`):
es solo el nombre que viaja en el `Content-Disposition`.
"""
from __future__ import annotations

import re
import unicodedata

# Formas societarias: ruido puro en el nombre de un archivo.
_FORMAS_LEGALES = {"sac", "sa", "srl", "eirl", "saa", "ltda", "srltda"}
# Lo único que el cliente pidió abreviar del postor (es el prefijo de casi todos).
_ABREV_POSTOR = {"consorcio": "cons", "consorcios": "cons"}

_MAX_SLUG = 24
_MAX_POSTOR = 20


def _sin_tildes(txt: str) -> str:
    """'DIVINO NIÑO' → 'DIVINO NINO'. Los nombres de archivo viajan por HTTP y se
    guardan en Windows: mejor ASCII plano."""
    nfkd = unicodedata.normalize("NFKD", str(txt or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _unir(palabras: list[str], max_len: int) -> str:
    """Une con '-' sin pasarse de `max_len`, cortando en límite de palabra."""
    out = ""
    for p in palabras:
        cand = f"{out}-{p}" if out else p
        if len(cand) > max_len:
            break
        out = cand
    return out or (palabras[0][:max_len] if palabras else "")


def _slug_desde_id(analisis_id: str, max_len: int = _MAX_SLUG) -> str:
    """Heurística de fallback: saca el nombre del concurso del `analisis_id`.

    Descarta lo que NO identifica al concurso: cualquier token con dígitos (año,
    fecha, código del procedimiento — 'cp001', '2025', '20260707') y las siglas de
    entidad de ≤3 letras ('mdh', 'grj', 'grc'). Lo que queda es el nombre:

        cp001-2025-mdh-huachocolpa    → huachocolpa
        divino-nino-2026-07-14        → divino-nino
        essalud-vitarte-cp02-2025     → essalud-vitarte
        pichanaqui-cp36-2025-grj      → pichanaqui

    Acierta en 12 de los 14 análisis reales que hay en disco; cuando no queda nada
    (`001-2025-MDH-CS1__IDC`) cae al id saneado, que es lo que había antes.
    """
    crudo = _sin_tildes(analisis_id).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", crudo) if t]
    utiles = [t for t in tokens if not any(c.isdigit() for c in t) and len(t) > 3]
    if utiles:
        return _unir(utiles, max_len)
    return _unir([t for t in tokens if t], max_len)


def slug_concurso(espejo=None, analisis_id: str = "", max_len: int = _MAX_SLUG) -> str:
    """Nombre corto del concurso: `_meta.slug` de la skill, o la heurística."""
    meta = espejo.get("_meta") or {} if isinstance(espejo, dict) else {}
    explicito = str(meta.get("slug") or "").strip()
    if explicito:
        limpio = re.sub(r"[^a-z0-9-]+", "-", _sin_tildes(explicito).lower()).strip("-")
        if limpio:
            return _unir([p for p in limpio.split("-") if p], max_len)
    return _slug_desde_id(analisis_id or str(meta.get("analisis_id") or ""), max_len)


def slug_postor(postor: str, max_len: int = _MAX_POSTOR) -> str:
    """'CONSORCIO VIAL HUANCAVELICA' → 'cons-vial'. Fuera la forma societaria,
    'consorcio' a 'cons', y las 2 primeras palabras que quedan."""
    crudo = _sin_tildes(postor).lower()
    palabras: list[str] = []
    for p in re.split(r"[^a-z0-9]+", crudo):
        if not p or p in _FORMAS_LEGALES:
            continue
        palabras.append(_ABREV_POSTOR.get(p, p))
    return _unir(palabras[:2], max_len)


def nombre_descarga(job, espejo=None, ext: str = "xlsx") -> str:
    """`Analisis_{concurso}_{postor}.{ext}` — el nombre que ve el evaluador.

    Excel y ZIP comparten nombre base (solo cambia la extensión) para que queden
    juntos al ordenar la carpeta de Descargas."""
    meta = espejo.get("_meta") or {} if isinstance(espejo, dict) else {}
    slug = slug_concurso(espejo, getattr(job, "analisis_id", "") or "")
    postor = slug_postor(getattr(job, "postor", "") or str(meta.get("postor") or ""))
    partes = [p for p in ("Analisis", slug, postor) if p]
    return f"{'_'.join(partes)}.{ext}"
