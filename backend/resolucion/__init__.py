"""Resolución de CUI por experiencia (portado del prototipo medido)."""
from .cui import (
    Consulta, ConsultaInfoObras, resolver, resolver_con_dedup, resolver_obras,
    rubros_mixtos)

__all__ = ["Consulta", "ConsultaInfoObras", "resolver", "resolver_con_dedup",
           "resolver_obras", "rubros_mixtos"]
