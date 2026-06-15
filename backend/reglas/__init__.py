"""Motor de reglas (Paso 5 + ALT03) — funciones puras, sin I/O."""
from .calculo import (
    CUTOFF_ANIOS_ALT03,
    alerta_experiencia_antigua,
    anios,
    dias_efectivos_profesional,
    dias_inclusivos,
    fecha_cutoff,
    fusionar_traslapes,
    meses,
    periodo_fechas,
    restar_paralizaciones,
)

__all__ = [
    "CUTOFF_ANIOS_ALT03", "alerta_experiencia_antigua", "anios",
    "dias_efectivos_profesional", "dias_inclusivos", "fecha_cutoff",
    "fusionar_traslapes", "meses", "periodo_fechas", "restar_paralizaciones",
]
