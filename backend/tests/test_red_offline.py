"""Garantía de que la suite normal nunca consulta servicios externos."""
from __future__ import annotations

import os
import socket

import pytest


@pytest.mark.skipif(
    os.getenv("PIVOTE_PERMITIR_RED_TESTS") == "1",
    reason="la red externa fue habilitada explícitamente",
)
def test_red_externa_bloqueada_por_defecto():
    conexion = socket.socket()
    try:
        with pytest.raises(AssertionError, match="red externa"):
            conexion.connect(("203.0.113.1", 80))
    finally:
        conexion.close()
