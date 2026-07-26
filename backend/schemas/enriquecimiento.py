"""
Pydantic v2 — Enriquecimiento que el backend on-prem produce por cada experiencia.

Cada experiencia del JSON espejo pasa por: resolución de CUI (componente 2) →
InfoObras vía CUI (3a) ∥ SUNAT vía RUC (3b) → motor de reglas (4). El resultado
estructurado es `EnriquecimientoExperiencia`: la forma **tipada** del bloque
`_backend` una vez que el servidor lo llena (reemplaza el placeholder plano
`Backend` de `espejo.py`, que es solo el contrato vacío que Claude emite).

Convención de estado por capa (ver `pipeline.py`): cada sub-resultado puede marcar
`requiere_humano` sin tumbar el job — el orquestador lo manda a `items_revision`.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _ModelLax(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ════════════════════════════════════════════════════════════════════════════
# Componente 2 · Resolución de CUI (el "selector")
# ════════════════════════════════════════════════════════════════════════════
class ViaResolucion(str, Enum):
    CUI_TEXTO = "cui_texto"   # CUI citado en el cert (campo o texto) → determinístico
    RUC = "ruc"               # cruce RUC ejecutor/supervisor de la obra → determinístico
    DEDUP = "dedup"           # heredado de un hermano con el mismo folio (mismo cert)
    NOMBRE = "nombre"         # ranking difuso + compuerta de establecimiento
    MANUAL = "manual"         # el humano pegó el CUI tras revisión
    NA = "na"                 # obra privada/ajena a salud → no está en InfoObras


class DecisionResolucion(str, Enum):
    DETERMINISTICO = "deterministico"  # CUI/RUC verificado → confianza máxima
    AUTO = "auto"                      # nombre verificado → sin humano
    PROBABLE = "probable"              # candidato fuerte → spot-check opcional
    REVISION = "revision"              # sin candidato fiable → humano pega el CUI
    NA = "na"                          # fuera de scope (no cruzable)


class Candidato(_Model):
    """Una obra candidata del ranking — se muestra al humano en spot-check/revisión."""
    cui: str
    nombre_obra: Optional[str] = None
    departamento: Optional[str] = None
    score: float
    ruc_match: bool = False


class ResolucionObra(_Model):
    cui: Optional[str] = None          # CUI resuelto (None si REVISION / NA)
    via: ViaResolucion
    decision: DecisionResolucion
    requiere_humano: bool = False
    candidatos: list[Candidato] = Field(default_factory=list)  # top-N para confirmar/pegar
    detalle: Optional[str] = None      # razón literal de la decisión


# ════════════════════════════════════════════════════════════════════════════
# Componente 3a · InfoObras (vía CUI)
# ════════════════════════════════════════════════════════════════════════════
class EstadoParalizacion(str, Enum):
    VIGENTE = "vigente"
    LEVANTADA = "levantada"
    DESCONOCIDO = "desconocido"


class Paralizacion(_Model):
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    dias: Optional[int] = Field(default=None, ge=0)
    motivo: Optional[str] = None
    estado: EstadoParalizacion = EstadoParalizacion.DESCONOCIDO


class InfoObrasResultado(_Model):
    codigo_ciu: Optional[str] = None
    codigo_infoobras: Optional[str] = None      # obraId de InfoObras
    nombre_obra_oficial: Optional[str] = None   # nombre como lo registra InfoObras
    estado_obra: Optional[str] = None
    departamento: Optional[str] = None
    paralizaciones: list[Paralizacion] = Field(default_factory=list)  # alimentan Paso 5
    obras_multiples: bool = False               # ⚠ el CUI devolvió >1 obra → desambiguar
    advertencia: Optional[str] = None
    archivos_zip: Optional[str] = None          # ref del ZIP por experiencia (⏳ alcance futuro)


# ════════════════════════════════════════════════════════════════════════════
# Componente 3b · SUNAT (vía RUC del emisor)
# ════════════════════════════════════════════════════════════════════════════
class Representante(_Model):
    tipo_documento: Optional[str] = None
    nro_documento: Optional[str] = None
    nombre: Optional[str] = None
    cargo: Optional[str] = None                 # "APODERADO", "GERENTE GENERAL"...
    fecha_desde: Optional[date] = None


class TramoCondicion(_Model):
    """Un tramo del histórico de condición del contribuyente (getinfHis)."""
    condicion: Optional[str] = None             # HABIDO / NO HABIDO / NO HALLADO / …
    desde: Optional[date] = None                # None = extremo abierto ("-")
    hasta: Optional[date] = None


class HistoricoSunat(_Model):
    """Información histórica del emisor (getinfHis): lo que cambió y desde cuándo."""
    razones_sociales: list[dict] = Field(default_factory=list)   # {nombre, fecha_baja}
    condiciones: list[TramoCondicion] = Field(default_factory=list)
    domicilios: list[dict] = Field(default_factory=list)         # {direccion, fecha_baja}


class HabidoEmisor(_Model):
    """¿El emisor estaba HABIDO cuando emitió el certificado y durante la obra?
    `ok=None` = no se puede afirmar (sin histórico o sin fechas)."""
    emision: Optional[dict] = None      # {fecha, condicion, ok}
    periodo: Optional[dict] = None      # {desde, hasta, condiciones, tramos, tramos_no_habido, ok}


class SunatResultado(_Model):
    ruc: Optional[str] = None
    razon_social: Optional[str] = None
    fecha_creacion_emisor: Optional[date] = None       # ALT04
    antiguedad_anios: Optional[float] = Field(default=None, ge=0)
    alerta_antiguedad_emisor: Optional[bool] = None    # ALT04
    # informativo (issue #30): quiénes representan al emisor. NO alimenta reglas —
    # ADR-008 descartó ALT-12 (firmante ≠ representante).
    representantes: list[Representante] = Field(default_factory=list)  # getRepLeg
    historico: Optional[HistoricoSunat] = None         # getinfHis
    habido: Optional[HabidoEmisor] = None              # la pregunta del evaluador
    firmante_facultado_sunat: Optional[bool] = None    # ALT12 (descartada, ADR-008)
    firmante_match_detalle: Optional[str] = None       # equivalencia de cargo + vigencia temporal
    vinculacion_postor_emisor: Optional[bool] = None   # autocertificación intragrupo (bandera)
    requiere_humano: bool = False                      # ej. emisor persona natural sin RUC consultable


# ════════════════════════════════════════════════════════════════════════════
# Componente 4 · Motor de reglas / recálculos
# ════════════════════════════════════════════════════════════════════════════
class Intervalo(_Model):
    inicio: date
    fin: date


class DiasEfectivos(_Model):
    """Paso 5: días brutos descontando paralizaciones (InfoObras) y traslapes (ALT11)."""
    dias_brutos: int = Field(ge=0)
    dias_paralizados: int = Field(default=0, ge=0)     # de InfoObras
    dias_traslape: int = Field(default=0, ge=0)        # ALT11: no estar en 2 obras a la vez
    dias_efectivos: int = Field(ge=0)
    intervalos_fusionados: list[Intervalo] = Field(default_factory=list)


class ReglasResultado(_Model):
    dias_efectivos: Optional[DiasEfectivos] = None     # Paso 5 (por experiencia / por profesional)
    cutoff_anios: int = 25                             # ALT03 — Claude usó 20; el backend recalcula con 25
    alerta_experiencia_antigua: Optional[bool] = None  # ALT03


# ════════════════════════════════════════════════════════════════════════════
# El bloque _backend tipado (filled) — lo que produce el orquestador
# ════════════════════════════════════════════════════════════════════════════
class EnriquecimientoExperiencia(_ModelLax):
    """Forma TIPADA del bloque `_backend` una vez enriquecido por el servidor.
    Sustituye el placeholder plano `Backend` de `espejo.py`. Cada sub-bloque puede
    ser `None` si su etapa aún no corrió o quedó a revisión."""
    n_prof: int = Field(ge=1)
    n_exp: int = Field(ge=1)
    resolucion: Optional[ResolucionObra] = None
    infoobras: Optional[InfoObrasResultado] = None
    sunat: Optional[SunatResultado] = None
    reglas: Optional[ReglasResultado] = None
