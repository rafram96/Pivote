"""
Fixtures comunes de los tests offline del backend.

Los tests de parseo usan los dumps HTML reales guardados en
backend/exploracion/_sunat_dump/ (gitignored — viven solo en máquinas de dev).
Si no están, esos tests se saltan en vez de fallar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

DUMP_SUNAT = BACKEND / "exploracion" / "_sunat_dump"


@pytest.fixture
def dump_sunat():
    """Carga un dump HTML de SUNAT por nombre; salta el test si no existe."""
    def _cargar(nombre: str) -> str:
        ruta = DUMP_SUNAT / nombre
        if not ruta.exists() or ruta.stat().st_size == 0:
            pytest.skip(f"dump local no disponible o vacío: {ruta.name}")
        return ruta.read_text(encoding="utf-8", errors="replace")
    return _cargar
