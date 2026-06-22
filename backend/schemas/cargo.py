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
