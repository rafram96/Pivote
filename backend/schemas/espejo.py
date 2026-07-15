"""
Pydantic v2 — JSON espejo de la skill `analizar-licitacion-osce`.

Contrato **v1.2.0**. Valida el artefacto consolidado que la skill emite (la otra
cara del Excel). Refleja la forma **plana** que realmente fluye por el pipeline
(la misma que consume `scripts/generar_excel.py` y que se validó round-trip
contra Trujillo y Libertador).

El bloque `_backend` es opcional y, en la salida de Claude, va vacío/null — es el
contrato explícito de lo que el servidor on-prem llena después.

Cambios v1.2.0 (lecciones de los espejos reales Libertador/Trujillo — ver
docs/backend/validador.md §4):
- Folios aceptan número o rango → se coercionan a str (paridad con zod `folioT`).
- `Formulario.documento` (new_format) convive con `descripcion` (Trujillo).
- `ExperienciaPostor.acredita` es el consorciado que acredita (texto) o un monto.
- Fechas flexibles: ISO, parcial "YYYY-MM (anotación)" o sentinel "POR VERIFICAR…"
  (NOTA 12). Todo lo demás se rechaza.
- `Factor.puntaje` admite "NO APLICA"; nuevo `Factor.aplica`.
- Profesional formaliza lo que el extractor ya emitía y Pydantic descartaba:
  `fecha_colegiatura`, `experiencia_total_declarada`, `requisitos`,
  `cross_checks` (NOTA 1), `notas`.
- `ExperienciaProf.traslape` (NOTA 9) y `Postor.consorciados` (NOTA 14).
- Capacidades nuevas del pivote en ExperienciaProf: `nivel_categoria` (comparación
  II-1 ≤ II-2), `area_construida_m2`, `monto_contrato_soles`, y los insumos de la
  resolución de CUI por nombre: `entidad_contratante`, `ubicacion`.
- `observaciones_claude` formalizado a nivel raíz.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Optional, Union

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _ModelLax(BaseModel):
    """Para sub-objetos donde toleramos campos extra (evolución del contrato)."""
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ── Tipos flexibles (datos reales) ───────────────────────────────────────────
# Sentinel de la NOTA 12: dato ilegible/no consignado tras reintentos.
SENTINEL_POR_VERIFICAR = "POR VERIFICAR"
# Fecha parcial: el certificado solo consigna mes/año → "2015-11 (sin día)".
_RE_FECHA_PARCIAL = re.compile(r"^\d{4}-\d{2}(\D.*)?$")
_RE_FECHA_ISO = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _coerce_folio(v):
    """Folios reales vienen como número (596), rango ('14-32 y 39-41') o texto."""
    if isinstance(v, bool):  # bool es subclase de int; nunca es un folio
        raise ValueError("folio no puede ser booleano")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(v)
    return v


def _coerce_fecha(v):
    """date | 'YYYY-MM-DD…' → date · parcial/sentinel → str · resto → error."""
    if v is None or isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        m = _RE_FECHA_ISO.match(s)
        if m and len(s) == 10:
            return date.fromisoformat(m.group(1))
        if s.startswith(SENTINEL_POR_VERIFICAR) or _RE_FECHA_PARCIAL.match(s):
            return s
        raise ValueError(
            f"fecha inválida: {s!r} (se espera YYYY-MM-DD, "
            f"'YYYY-MM (anotación)' o '{SENTINEL_POR_VERIFICAR}…')"
        )
    raise ValueError(f"fecha inválida: {v!r}")


FolioT = Annotated[Optional[str], BeforeValidator(_coerce_folio)]
FechaFlexible = Annotated[Optional[Union[date, str]], BeforeValidator(_coerce_fecha)]


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
    documento: Optional[str] = None       # new_format (columna "DOCUMENTO")
    descripcion: Optional[str] = None     # formato Trujillo (compat)
    observacion: str = ""
    folio: FolioT = ""


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
    acredita: Optional[Union[float, str]] = None  # consorciado que acredita (texto) o monto
    folio: FolioT = None
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
    # NOTA 14: quiénes integran el consorcio (para exigir ISO de TODOS).
    consorciados: Optional[list[dict]] = None


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


# Sub-proyecto de un cert MULTI-OBRA: un cert de rol de gestión/portafolio lista N
# obras bajo un mismo vínculo continuo, cada una con su CUI. El tiempo se cuenta una
# sola vez (el periodo de la experiencia); estas obras las verifica el backend por
# código, cada una por separado. Genérico (no atado a un formato de cert).
class SubObra(_Model):
    proyecto: Optional[str] = None    # nombre del sub-proyecto/obra
    cui: Optional[str] = None         # CUI/SNIP del sub-proyecto (solo dígitos) o None


# ── Experiencia del profesional (Parte 4) ────────────────────────────────────
class ExperienciaProf(_Model):
    n: int = Field(ge=1)
    entidad_emisora: Optional[str] = None
    ruc_emisor: Optional[str] = None      # RUC (11 díg.) del emisor del cert → cruce ejecutor/supervisor + ALT12
    proyecto: Optional[str] = None        # nombre de obra VERBATIM y completo (sin abreviar ni meter metadata)
    cui: Optional[str] = None             # CUI/SNIP citado en el cert (solo dígitos) → Paso 0 determinístico
    # De dónde salió el CUI: "certificado" (citado en la constancia) o "skill"
    # (Claude lo resolvió buscando en la web en el Paso 4.5 — SOLO tras confirmarlo
    # contra InfoObras). El backend lo trata igual (por_codigo autoritativo).
    cui_fuente: Optional[str] = None
    tipo_documento: Optional[str] = None
    nombre_emisor: Optional[str] = None
    cargo_emisor: Optional[str] = None
    cargo_valido_emitir: Optional[str] = None
    fecha_inicial: FechaFlexible = None
    fecha_final: FechaFlexible = None
    fecha_emision: FechaFlexible = None
    folio: FolioT = None
    # páginas FÍSICAS del PDF de la constancia (1-indexadas, principal 1ª); el folio
    # impreso ≠ página NO siempre → con esto el recorte toma la hoja correcta.
    paginas_pdf: Optional[list[int]] = None
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
    traslape: Optional[str] = None        # NOTA 9: SÍ/NO/null — Claude marca, backend re-verifica
    nivel_categoria: Optional[str] = None  # nivel hospitalario del proyecto ("II-1", "Centro de Salud"…)
    area_construida_m2: Optional[float] = Field(default=None, ge=0)
    monto_contrato_soles: Optional[float] = Field(default=None, ge=0)
    entidad_contratante: Optional[str] = None  # dueño de la obra (≠ emisor del cert) → score CUI
    ubicacion: Optional[str] = None       # dpto/prov/distrito si el cert lo cita → score CUI
    observaciones: Optional[str] = None
    # Sub-proyectos si el cert es multi-obra (1 vínculo, N obras). None/vacío en el
    # caso normal (1 experiencia = 1 obra, va en `cui`). Ver SubObra.
    obras: Optional[list[SubObra]] = None
    backend: Backend = Field(default_factory=Backend, alias="_backend")

    @model_validator(mode="after")
    def _fechas_coherentes(self):
        ini, fin = self.fecha_inicial, self.fecha_final
        if isinstance(ini, date) and isinstance(fin, date) and fin < ini:
            raise ValueError(f"exp {self.n}: fecha_final < fecha_inicial")
        return self


class CrossCheck(_ModelLax):
    """NOTA 1: cross-check contra el cuadro resumen del Anexo 16."""
    label: Optional[str] = None
    valor: Optional[Union[str, dict]] = None


class Profesional(_ModelLax):
    n_prof: int = Field(ge=1)
    cargo: str = Field(min_length=1)    # etiqueta LITERAL del cargo en la propuesta (sin la cola "(cargo bases N°…)")
    cargo_bases_num: Optional[int] = None      # nº del cargo equivalente en el Cuadro de Personal de las bases (decide a qué factor aplica)
    cargo_bases_nombre: Optional[str] = None   # nombre de ese cargo de bases ("ESPECIALISTA EN ESTRUCTURAS")
    nombre: Optional[str] = None        # SOLO el nombre limpio (sin DNI ni notas de OCR)
    dni: Optional[str] = None           # SOLO dígitos; caveats → notas
    folio_nombre: FolioT = None
    titulo: Optional[str] = None
    folio_titulo: FolioT = None
    profesion_valida: Optional[str] = None
    colegiatura: Optional[str] = None
    fecha_colegiatura: FechaFlexible = None
    folio_colegiatura: FolioT = None
    certificaciones: Optional[str] = None
    # NOTA 1/5: lo autodeclarado en el Anexo 16 (número o texto literal del cuadro).
    experiencia_total_declarada: Optional[Union[float, str]] = None
    # Requisitos de las bases para este cargo (cargos_validos, tipo_obra, …).
    requisitos: Optional[dict] = None
    experiencias: list[ExperienciaProf] = Field(default_factory=list)
    total: dict = Field(default_factory=dict)
    cross_checks: list[CrossCheck] = Field(default_factory=list)
    notas: list[str] = Field(default_factory=list)
    cumple: Optional[str] = None
    anios_adicionales: Optional[str] = None

    @model_validator(mode="after")
    def _exp_contiguas(self):
        ns = [e.n for e in self.experiencias]
        if ns and ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"profesional {self.n_prof}: 'n' de experiencias no es 1..N contiguo: {ns}")
        return self


# ── Resumen (Parte 5) ────────────────────────────────────────────────────────
def _valida_puntaje(v):
    if isinstance(v, str) and not v.strip().upper().startswith("NO APLICA"):
        raise ValueError(f"puntaje inválido: {v!r} (número, null o 'NO APLICA…')")
    return v


class Factor(_Model):
    factor: str = Field(min_length=1)
    criterio: Optional[str] = None
    folio: FolioT = None
    detalle: Optional[str] = None
    aplica: Optional[bool] = None         # false ⇔ puntaje "NO APLICA"
    puntaje: Annotated[Optional[Union[float, str]], BeforeValidator(_valida_puntaje)] = None


class ResumenEvaluacion(_ModelLax):
    factores: list[Factor] = Field(default_factory=list)
    puntaje_total: Optional[float] = Field(default=None, ge=0)
    nota: Optional[str] = None


# ── Raíz ─────────────────────────────────────────────────────────────────────
class Observacion(_ModelLax):
    """Hallazgo cualitativo de los subagentes (ambigüedad, ilegibilidad, …)."""
    severidad: Optional[str] = None       # info | warning | critical
    tipo: Optional[str] = None
    mensaje: Optional[str] = None
    referencia: Optional[str] = None


class JsonEspejo(_ModelLax):
    meta: Meta = Field(alias="_meta")
    postor: Postor
    profesionales: list[Profesional] = Field(min_length=1)
    resumen_evaluacion: ResumenEvaluacion = Field(default_factory=ResumenEvaluacion)
    observaciones_claude: list[Observacion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _n_prof_contiguos(self):
        ns = [p.n_prof for p in self.profesionales]
        if ns != list(range(1, len(ns) + 1)):
            raise ValueError(f"n_prof debe ser 1..N contiguo y único: {ns}")
        return self
