"""Cargo atómico — separa la etiqueta del cargo de la correspondencia con bases.

La skill a veces incrusta la correspondencia con el cargo oficial de las bases
dentro del nombre del cargo del profesional:

    "Especialista en Supervisión de Estructuras N° 1 (cargo bases N°5 ESPECIALISTA EN ESTRUCTURAS)"

Es dato correcto (mapea el cargo de la propuesta al cargo del Cuadro de Personal
de las bases, que decide a qué factor aplica) pero mal ubicado: se lee como ruido
en el panel y en el Excel, y solo aparece en algunas filas. `partir_cargo` lo lleva
a campos atómicos (`cargo_bases_num`, `cargo_bases_nombre`) dejando `cargo` con la
etiqueta literal de la propuesta.

Lo usan el ingest del motor (normaliza al recibir — pieza "B") y el backfill de
espejos viejos. Idempotente: un cargo ya limpio no se toca.
"""
from __future__ import annotations

import re

# "(cargo bases N°5 ESPECIALISTA EN ESTRUCTURAS)" o "(cargo bases N°12)", al final.
_RE_CARGO_BASES = re.compile(
    r"\s*\(\s*cargo\s+bases\s*N[°º]?\s*(\d+)\s*([^)]*)\)\s*$", re.I
)


def partir_cargo(cargo):
    """`cargo` → `(etiqueta_limpia, num_bases:int|None, nombre_bases:str|None)`.

    Si no hay correspondencia incrustada, devuelve el cargo tal cual (stripped) y
    `None, None`."""
    if not isinstance(cargo, str) or not cargo.strip():
        return cargo, None, None
    m = _RE_CARGO_BASES.search(cargo)
    if not m:
        return cargo.strip(), None, None
    nombre = cargo[: m.start()].strip()
    num = int(m.group(1))
    resto = (m.group(2) or "").strip(" .·-—") or None
    return nombre, num, resto


def normalizar_cargo_profesional(prof: dict) -> bool:
    """Aplica `partir_cargo` a un dict de profesional in-place. Solo rellena los
    campos `cargo_bases_*` si están vacíos (no pisa lo que la skill ya separó).
    Devuelve True si cambió algo."""
    if not isinstance(prof, dict):
        return False
    cargo = prof.get("cargo")
    nombre, num, nombre_bases = partir_cargo(cargo or "")
    cambio = False
    if isinstance(cargo, str) and nombre != cargo:
        prof["cargo"] = nombre
        cambio = True
    if num is not None and not prof.get("cargo_bases_num"):
        prof["cargo_bases_num"] = num
        cambio = True
    if nombre_bases and not prof.get("cargo_bases_nombre"):
        prof["cargo_bases_nombre"] = nombre_bases
        cambio = True
    return cambio


def normalizar_cargos_espejo(espejo: dict) -> int:
    """Normaliza el `cargo` de todos los profesionales del espejo in-place.
    Devuelve cuántos cambiaron. Idempotente."""
    n = 0
    if isinstance(espejo, dict):
        for prof in espejo.get("profesionales") or []:
            if normalizar_cargo_profesional(prof):
                n += 1
    return n


# ── Etiqueta corta para la pestaña del Excel ─────────────────────────────────
# El cargo completo no cabe en una pestaña: el límite de 31 chars de Excel lo
# cortaba a media frase ("P4 ESPECIALISTA PLANEAMIENTO Y"). Regla determinística,
# sin tabla de abreviaturas que mantener sincronizada:
#   1. fuera el prefijo genérico — TODOS son "especialistas", no distingue. "Jefe"
#      SÍ se conserva: marca jerarquía y es lo que separa al jefe de los demás.
#   2. fuera los conectores (y, de, en…).
#   3. cada palabra a la mitad, con piso de 5 letras (las de ≤5 quedan enteras).
#   4. Title Case fijo → la pestaña deja de depender de cómo escribió el cargo el
#      postor en su PDF ("INSTALACIONES SANITARIAS" vs "Instalaciones Sanitarias"
#      daban pestañas distintas para el mismo cargo).
# El cargo COMPLETO no se pierde: sigue en la banda "PROFESIONAL N: <cargo>" de la
# propia hoja y en la columna "CARGO AL QUE POSTULA" de la hoja Base de Datos.
_RE_PREFIJO_GENERICO = re.compile(
    r"^\s*(?:esp\.?|especialista|ingeniero|ing\.?|responsable|gerente)"
    r"(?:\s+(?:en|de|del|para)\b)?\s+",
    re.I,
)
# Excel rechaza estos caracteres en el nombre de una hoja.
_RE_INVALIDO_HOJA = re.compile(r"[\\/*?:\[\]]")
_CONECTORES = {"y", "e", "o", "u", "de", "del", "la", "el", "los", "las",
               "en", "para", "con", "a", "al"}
_MIN_PALABRA = 5        # piso: "Costos" → "Costo", no "Cos"
_LIMITE_HOJA = 31       # límite duro de Excel


def _mitad(palabra: str) -> str:
    """Palabra recortada a la mitad (redondeando hacia arriba), nunca por debajo
    de `_MIN_PALABRA`: 'Supervisión' → 'Superv', 'Jefe' → 'Jefe'."""
    corte = max(_MIN_PALABRA, -(-len(palabra) // 2))    # ceil(len/2)
    return palabra[:corte].rstrip(" -.,;")


def abreviar_cargo(cargo: str) -> str:
    """'Jefe de Supervisión' → 'Jefe Superv' · 'ESPECIALISTA EN ESTRUCTURAS' →
    'Estruc' · 'ESP. PLANEAMIENTO Y COSTOS' → 'Planea Costo'. Devuelve "" si no
    queda nada legible."""
    txt = _RE_INVALIDO_HOJA.sub(" ", str(cargo or "")).strip()
    if not txt:
        return ""
    # Si el cargo es SOLO el prefijo genérico ("Especialista"), quitarlo lo dejaría
    # vacío → en ese caso se conserva el original.
    sin_prefijo = _RE_PREFIJO_GENERICO.sub("", txt, count=1).strip()
    palabras = [p for p in (sin_prefijo or txt).split()
                if p.lower().strip(".") not in _CONECTORES]
    return " ".join(_mitad(p.capitalize()) for p in palabras if p).strip()


def etiqueta_hoja(n_prof: int, cargo: str) -> str:
    """Nombre de la pestaña del profesional: `P{n}. {cargo abreviado}`.

    El prefijo `P{n}` garantiza unicidad aunque dos profesionales compartan cargo.
    El clamp a 31 es una guardia (la regla ya deja ~15 chars) y corta en límite de
    palabra, nunca a media palabra."""
    abrev = abreviar_cargo(cargo)
    base = f"P{n_prof}. {abrev}".strip() if abrev else f"P{n_prof}"
    if len(base) <= _LIMITE_HOJA:
        return base
    cut = base[:_LIMITE_HOJA]
    if base[_LIMITE_HOJA] != " ":            # solo retrocede si cortó a media palabra
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;-.")
