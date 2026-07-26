"""Validador determinístico — verificaciones puras de las 15 NOTAS."""
from .cargo_nucleo import anotar_cargo_nucleo
from .notas import verificar_espejo
from .recalculo import observaciones_recalculo, recalcular_espejo

__all__ = ["verificar_espejo", "anotar_cargo_nucleo",
           "recalcular_espejo", "observaciones_recalculo"]
