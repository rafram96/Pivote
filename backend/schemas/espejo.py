"""
Pydantic v2 — JSON espejo de la skill `analizar-licitacion-osce`.

Valida el artefacto consolidado que la skill emite (la otra cara del Excel).
Refleja la forma **plana** que realmente fluye por el pipeline (la misma que
consume `scripts/generar_excel.py` y que se validó round-trip contra Trujillo).

El bloque `_backend` es opcional y, en la salida de Claude, va vacío/null — es el
contrato explícito de lo que el servidor on-prem llena después.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _ModelLax(BaseModel):
    """Para sub-objetos donde toleramos campos extra (evolución del contrato)."""
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ── Meta ─────────────────────────────────────────────────────────────────────
class Meta(_ModelLax):
    analisis_id: str = Field(min_length=1)
    concurso: Optional[str] = None
    postor: Optional[str] = None
    version_contrato: Optional[str] = None
    generado_por: Optional[str] = None
    representante_comun: Optional[str] = None


# ── Postor (Partes 1-2) ──────────────────────────────────────────────────────
class Formulario(_Model):
    anexo: str = ""
    descripcion: str = ""
    observacion: str = ""
    folio: str = ""


class OfertaEconomica(_ModelLax):
    cuantia: Optional[float] = None
    limite_inferior: Optional[float] = None
    propuesta: Optional[float] = None
    detalle: Optional[str] = None


class ExperienciaPostor(_Model):
    n: int = Field(ge=1)
    cliente: Optional[str] = None
    contrato: Optional[str] = None
    proyecto: Optional[str] = None
    tipo_acreditacion: Optional[str] = None
    monto: Optional[float] = Field(default=None, ge=0)
    pct_objeto: Optional[float] = Field(default=None, ge=0, le=1)
    le_corresponde: Optional[float] = Field(default=None, ge=0)
    acredita: Optional[float] = Field(default=None, ge=0)
    folio: Optional[str] = None
    ultimos_20_anios: Optional[str] = None
    tipo_solicitado: Optional[str] = None
    observaciones: Optional[str] = None


class Postor(_ModelLax):
    detalle: Optional[str] = None
    formularios: list[Formulario] = Field(default_factory=list)
    oferta_economica: OfertaEconomica = Field(default_factory=OfertaEconomica)
    experiencia_postor: list[ExperienciaPostor] = Field(default_factory=list)
    experiencia_postor_total: dict = Field(default_factory=dict)
    postor_cumple: Optional[str] = None


# ── Bloque _backend (lo llena el servidor; Claude lo deja null) ──────────────
class Backend(_ModelLax):
    fecha_creacion_emisor: Optional[date] = None
    alerta_antiguedad_emisor: Optional[str] = None
    firmante_facultado_sunat: Optional[bool] = None
    vinculacion_postor_emisor: Optional[str] = None
    codigo_ciu: Optional[str] = None
    codigo_infoobras: Optional[str] = None
    paralizaciones: Optional[list] = None
    alerta_experiencia_antigua: Optional[str] = None


# ── Experiencia del profesional (Parte 4) ────────────────────────────────────
class ExperienciaProf(_Model):
    n: int = Field(ge=1)
    entidad_emisora: Optional[str] = None
    ruc_emisor: Optional[str] = None      # RUC (11 díg.) del emisor del cert → cruce ejecutor/supervisor + ALT12
    proyecto: Optional[str] = None        # nombre de obra VERBATIM y completo (sin abreviar ni meter metadata)
    cui: Optional[str] = None             # CUI/SNIP citado en el cert (solo dígitos) → Paso 0 determinístico
    tipo_documento: Optional[str] = None
    nombre_emisor: Optional[str] = None
    cargo_emisor: Optional[str] = None
    cargo_valido_emitir: Optional[str] = None
    fecha_inicial: Optional[date] = None
    fecha_final: Optional[date] = None
    fecha_emision: Optional[date] = None
    folio: Optional[str] = None
    dias: Optional[float] = Field(default=None, ge=0)
    meses: Optional[float] = Field(default=None, ge=0)
    anios: Optional[float] = Field(default=None, ge=0)
    anterior_colegiatura: Optional[str] = None
    cargo_ocupado: Optional[str] = None
    cargo_bases_valido: Optional[str] = None
    funciones_similares: Optional[str] = None
    cert_antes_culminar: Optional[str] = None
    incluye_covid: Optional[str] = None
    tipo_obra_valido: Optional[str] = None
    observaciones: Optional[str] = None
    backend: Backend = Field(default_factory=Backend, alias="_backend")

    @model_validator(mode="after")
    def _fechas_coherentes(self):
        if self.fecha_inicial and self.fecha_final and self.fecha_final < self.fecha_inicial:
            raise ValueError(f"exp {self.n}: fecha_final < fecha_inicial")
        return self


class Profesional(_ModelLax):
    n_prof: int = Field(ge=1)
    cargo: str = Field(min_length=1)
    nombre: Optional[str] = None
    folio_nombre: Optional[str] = None
    titulo: Optional[str] = None
    folio_titulo: Optional[str] = None
    profesion_valida: Optional[str] = None
    colegiatura: Optional[str] = None
    folio_colegiatura: Optional[str] = None
    certificaciones: Optional[str] = None
    experiencias: list[ExperienciaProf] = Field(default_factory=list)
    total: dict = Field(default_factory=dict)
    cumple: Optional[str] = None
    anios_adicionales: Optional[str] = None

    @model_validator(mode="after")
    def _exp_contiguas(self):
        ns = [e.n for e in self.experiencias]
        if ns and ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"profesional {self.n_prof}: 'n' de experiencias no es 1..N contiguo: {ns}")
        return self


# ── Resumen (Parte 5) ────────────────────────────────────────────────────────
class Factor(_Model):
    factor: str = Field(min_length=1)
    criterio: Optional[str] = None
    folio: Optional[str] = None
    detalle: Optional[str] = None
    puntaje: Optional[float] = Field(default=None, ge=0)


class ResumenEvaluacion(_ModelLax):
    factores: list[Factor] = Field(default_factory=list)
    puntaje_total: Optional[float] = Field(default=None, ge=0)
    nota: Optional[str] = None


# ── Raíz ─────────────────────────────────────────────────────────────────────
class JsonEspejo(_ModelLax):
    meta: Meta = Field(alias="_meta")
    postor: Postor
    profesionales: list[Profesional] = Field(min_length=1)
    resumen_evaluacion: ResumenEvaluacion = Field(default_factory=ResumenEvaluacion)

    @model_validator(mode="after")
    def _n_prof_contiguos(self):
        ns = [p.n_prof for p in self.profesionales]
        if ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"n_prof debe ser 1..N contiguo y único: {ns}")
        return self
