# Schema Pydantic v2 — código ejecutable

Clases Pydantic v2 que validan los 3 JSONs producidos por la skill
`analizar-licitacion-osce`. Listas para portar a
`Alpamayo-InfoObras/src/api/schemas/analizar.py` cuando se implemente.

Referencia: [`schema_canonico.md`](schema_canonico.md) (documentación) y
[`skill_design.md`](skill_design.md) (orquestador).

---

## 1 · Estructuras compartidas

```python
# schemas/shared.py
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ─── Pydantic v2 config base ─────────────────────────────────────────────────

class _StrictModel(BaseModel):
    """Base con configuración estricta y campos extra rechazados."""
    model_config = ConfigDict(
        extra="forbid",          # rechaza campos no declarados
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ─── Meta ────────────────────────────────────────────────────────────────────

SubagenteName = Literal["agent-bases", "agent-propuesta"]


class Meta(_StrictModel):
    """Identificación común de cada JSON producido por la skill."""
    analisis_id: str = Field(
        pattern=r"^[a-z0-9-]+--\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$",
        description="Formato: {nomenclatura_slug}--{ISO timestamp filesystem-safe}",
    )
    subagente: SubagenteName
    version_skill: str = Field(pattern=r"^\d+\.\d+\.\d+$")  # SemVer
    fecha_extraccion: datetime
    fuente_pdf: str = Field(min_length=1)


# ─── Observaciones ───────────────────────────────────────────────────────────

ObsTipo = Literal[
    "ilegibilidad",
    "ambiguedad",
    "duplicado_posible",
    "inconsistencia",
    "calidad_documento",
    "hallazgo_relevante",
    "alerta_manual",
    "extraccion_parcial",
]

Severidad = Literal["info", "warning", "critical"]
Origen = Literal["claude", "backend"]

ItemTipo = Literal["cargo", "profesional", "experiencia", "factor"]


class ReferenciaItem(_StrictModel):
    """Apunta a un item específico dentro del JSON donde está la observación."""
    item_tipo: ItemTipo | None = None
    item_id: int | str | list[int] | None = None
    campo: str | None = None
    folio_pdf: str | None = None
    pagina_pdf: int | None = Field(default=None, ge=1)


class Observacion(_StrictModel):
    """Observación cualitativa que Claude (o el backend) emite."""
    codigo: str = Field(min_length=3, max_length=80)
    tipo: ObsTipo
    severidad: Severidad
    origen: Origen
    mensaje: str = Field(min_length=1)
    referencia: ReferenciaItem | None = None
```

---

## 2 · `bases.json` (Paso 1)

```python
# schemas/bases.py
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .shared import Meta, Observacion, _StrictModel


# ─── metadata_concurso ───────────────────────────────────────────────────────

class MetadataConcurso(_StrictModel):
    nomenclatura: str = Field(min_length=1)
    entidad: str = Field(min_length=1)
    objeto: str = Field(min_length=1)
    fuente_bases: str = Field(min_length=1)
    especialidad: str = Field(min_length=1)
    subespecialidad: str | None = None
    fecha_presentacion_oferta: date | None = None


# ─── factores_evaluacion ─────────────────────────────────────────────────────

FactorAplicaA = Literal["profesional_individual", "grupo_profesionales", "postor"]


class FactorEvaluacion(_StrictModel):
    codigo: str = Field(min_length=1, max_length=8)         # "A", "B", "J", "G"
    nombre: str = Field(min_length=1)
    max_pts: int = Field(ge=0, le=200)
    aplica_a: FactorAplicaA
    criterios: list[str] = Field(default_factory=list)
    aplica_a_cargos: list[int] = Field(default_factory=list)


class FactoresEvaluacion(_StrictModel):
    factor_a: FactorEvaluacion
    factor_b: FactorEvaluacion
    factor_j: FactorEvaluacion | None = None
    factor_g: FactorEvaluacion | None = None
    otros: list[FactorEvaluacion] = Field(default_factory=list)


# ─── personal_clave ──────────────────────────────────────────────────────────

ExpUnidad = Literal["meses", "anos"]


class CargoBases(_StrictModel):
    numero: int = Field(ge=1, le=99)
    cargo: str = Field(min_length=1)
    profesiones_aceptadas: list[str] = Field(min_length=1)

    anos_colegiado_min: int | None = Field(default=None, ge=0, le=99)
    requiere_titulo_y_colegiatura: bool = True

    experiencia_minima_unidad: ExpUnidad
    experiencia_minima_cantidad: int = Field(ge=0)
    cargos_similares_validos: list[str] = Field(default_factory=list)

    tipo_experiencia_similar: str = Field(min_length=1)
    tipos_obra_validos: list[str] = Field(default_factory=list)

    factor_a_aplica: bool
    factor_a_detalle: str | None = None

    factor_b_aplica: bool
    es_lider_equipo: bool = False
    certificaciones_factor_b: list[str] = Field(default_factory=list)
    factor_b_puntaje_individual: int = Field(default=0, ge=0)

    certificaciones_postor: list[str] = Field(default_factory=list)


# ─── Schema raíz ─────────────────────────────────────────────────────────────

class BasesSchema(_StrictModel):
    """Output esperado de agent-bases. Validación raíz para bases.json"""
    meta: Meta = Field(alias="_meta")
    metadata_concurso: MetadataConcurso
    factores_evaluacion: FactoresEvaluacion
    personal_clave: list[CargoBases] = Field(min_length=1)
    observaciones_claude: list[Observacion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_subagente(self):
        if self.meta.subagente != "agent-bases":
            raise ValueError(
                f"bases.json debe tener _meta.subagente='agent-bases', "
                f"recibido: {self.meta.subagente}"
            )
        return self

    @model_validator(mode="after")
    def _check_cargos_unique_numero(self):
        numeros = [c.numero for c in self.personal_clave]
        if len(numeros) != len(set(numeros)):
            raise ValueError(
                f"personal_clave tiene números de cargo duplicados: {numeros}"
            )
        return self

    @model_validator(mode="after")
    def _check_factor_a_referencias(self):
        # Si factor_a.aplica_a_cargos no está vacío, todos deben existir en personal_clave
        if self.factores_evaluacion.factor_a.aplica_a_cargos:
            valid_numeros = {c.numero for c in self.personal_clave}
            invalid = set(self.factores_evaluacion.factor_a.aplica_a_cargos) - valid_numeros
            if invalid:
                raise ValueError(
                    f"factor_a.aplica_a_cargos referencia cargos inexistentes: {invalid}"
                )
        return self
```

---

## 3 · `profesionales.json` (Paso 2)

```python
# schemas/profesionales.py
from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .shared import Meta, Observacion, _StrictModel


class ProfesionalPropuesto(_StrictModel):
    n_prof: int = Field(ge=1)
    nombre: str = Field(min_length=1)
    profesion: str = Field(min_length=1)
    # Acepta ISO date O string libre (cuando es ilegible: "Ilegible / Año 1978")
    fecha_colegiacion: date | str | None = None
    especialidad_postulada: str = Field(min_length=1)

    # 2 folios distintos (convención del ingeniero)
    folio_colegiatura: str = Field(min_length=1)
    folio_nombre_propuesta: str = Field(min_length=1)

    # Claude NO rellena estos campos típicamente
    universidad_titulacion: str | None = None
    fecha_titulacion: date | None = None

    # Marcadores estructurales binarios
    _flags: dict[str, str] = Field(default_factory=dict)


class ProfesionalesSchema(_StrictModel):
    """Output esperado de agent-propuesta para profesionales.json"""
    meta: Meta = Field(alias="_meta")
    profesionales: list[ProfesionalPropuesto] = Field(min_length=1)
    observaciones_claude: list[Observacion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_subagente(self):
        if self.meta.subagente != "agent-propuesta":
            raise ValueError(
                f"profesionales.json debe tener _meta.subagente='agent-propuesta', "
                f"recibido: {self.meta.subagente}"
            )
        return self

    @model_validator(mode="after")
    def _check_n_prof_unique_contiguous(self):
        n_profs = [p.n_prof for p in self.profesionales]
        if n_profs != list(range(1, len(n_profs) + 1)):
            raise ValueError(
                f"n_prof debe ser 1..N contiguo y único, recibido: {n_profs}"
            )
        return self
```

---

## 4 · `experiencias.json` (Paso 3)

```python
# schemas/experiencias.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .shared import Meta, Observacion, _StrictModel


PublicaPrivada = Literal["Pública", "Privada"]


class ExperienciaPeriodo(_StrictModel):
    n_correlativo: int = Field(ge=1)
    n_prof: int = Field(ge=1)

    # ── Datos del proyecto ──────────────────────────────────────────────────
    proyecto: str = Field(min_length=1)
    cargo_desempenado: str = Field(min_length=1)

    # ── Emisor del certificado ──────────────────────────────────────────────
    empresa_emisora: str = Field(min_length=1)
    ruc_emisor: str | None = Field(default=None, pattern=r"^\d{11}$|^-$")

    # ── Clasificación ───────────────────────────────────────────────────────
    publica_o_privada: PublicaPrivada | None = None
    tipo_acreditacion: str = Field(min_length=1)

    # ── Fechas ──────────────────────────────────────────────────────────────
    fecha_inicio: date
    fecha_culminacion: date | None = None
    alerta_covid: str | None = None

    # ── Certificado ─────────────────────────────────────────────────────────
    fecha_emision_cert: date
    n_folio: str = Field(min_length=1)
    firmante_certificado: str = Field(min_length=1)
    cargo_firmante: str | None = None
    tipo_documento: str = Field(min_length=1)

    # ── Capacidades nuevas (extrae Claude) ──────────────────────────────────
    nivel_categoria: str | None = None
    area_construida_m2: Decimal | None = Field(default=None, ge=0)
    monto_contrato_soles: Decimal | None = Field(default=None, ge=0)
    ubicacion: str = Field(min_length=1)
    entidad_contratante: str = Field(min_length=1)

    # ── Alertas que SÍ calcula Claude ───────────────────────────────────────
    alerta_exp_antes_titulacion: str | None = None
    alerta_cert_antes_culminacion: str | None = None
    observaciones_fila: str | None = None

    # Marcadores estructurales binarios
    _flags: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_fechas(self):
        if self.fecha_culminacion and self.fecha_culminacion < self.fecha_inicio:
            raise ValueError(
                f"fecha_culminacion ({self.fecha_culminacion}) < "
                f"fecha_inicio ({self.fecha_inicio})"
            )
        # fecha_emision_cert idealmente ≥ fecha_culminacion, pero NO se valida
        # (Claude emite alerta_cert_antes_culminacion cuando aplica)
        return self

    @model_validator(mode="after")
    def _check_alerta_covid_consistency(self):
        """Si alerta_covid se rellena, debe corresponder a la regla real."""
        import datetime as dt
        covid_start = dt.date(2020, 3, 15)
        atraviesa_covid = (
            self.fecha_culminacion is not None
            and self.fecha_inicio <= covid_start <= self.fecha_culminacion
        )
        if self.alerta_covid and not atraviesa_covid:
            raise ValueError(
                "alerta_covid presente pero el periodo no atraviesa 15/03/2020"
            )
        # No exigimos lo opuesto (sí permite null aunque atraviese — backend valida)
        return self


class ExperienciasSchema(_StrictModel):
    """Output esperado de agent-propuesta para experiencias.json"""
    meta: Meta = Field(alias="_meta")
    experiencias: list[ExperienciaPeriodo] = Field(min_length=1)
    observaciones_claude: list[Observacion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_subagente(self):
        if self.meta.subagente != "agent-propuesta":
            raise ValueError(
                f"experiencias.json debe tener _meta.subagente='agent-propuesta', "
                f"recibido: {self.meta.subagente}"
            )
        return self

    @model_validator(mode="after")
    def _check_n_correlativo_contiguous(self):
        correlativos = [e.n_correlativo for e in self.experiencias]
        if correlativos != list(range(1, len(correlativos) + 1)):
            raise ValueError(
                f"n_correlativo debe ser 1..N contiguo y único, recibido: {correlativos}"
            )
        return self

    @model_validator(mode="after")
    def _check_orden_cronologico(self):
        """Dentro de cada n_prof, fecha_culminacion debe estar ordenada ascendente."""
        by_prof: dict[int, list[ExperienciaPeriodo]] = {}
        for e in self.experiencias:
            by_prof.setdefault(e.n_prof, []).append(e)
        for n_prof, exps in by_prof.items():
            fechas = [e.fecha_culminacion for e in exps if e.fecha_culminacion]
            if fechas != sorted(fechas):
                raise ValueError(
                    f"experiencias de n_prof={n_prof} no están en orden "
                    f"cronológico ascendente por fecha_culminacion"
                )
        return self
```

---

## 5 · Validación cross-JSON

```python
# schemas/cross.py
from __future__ import annotations

from .bases import BasesSchema
from .profesionales import ProfesionalesSchema
from .experiencias import ExperienciasSchema


class CrossJSONValidationError(Exception):
    pass


def validate_cross_json(
    bases: BasesSchema,
    profesionales: ProfesionalesSchema,
    experiencias: ExperienciasSchema,
) -> None:
    """
    Validaciones que cruzan los 3 JSONs. Llamada por la main skill después
    de validar cada uno individualmente.
    """
    # 1. analisis_id idéntico en los 3
    ids = {
        bases.meta.analisis_id,
        profesionales.meta.analisis_id,
        experiencias.meta.analisis_id,
    }
    if len(ids) != 1:
        raise CrossJSONValidationError(
            f"analisis_id inconsistente entre los 3 JSONs: {ids}"
        )

    # 2. version_skill idéntico (los 2 subagentes corren la misma versión)
    versions = {
        bases.meta.version_skill,
        profesionales.meta.version_skill,
        experiencias.meta.version_skill,
    }
    if len(versions) != 1:
        raise CrossJSONValidationError(
            f"version_skill inconsistente: {versions}"
        )

    # 3. FK lógica: cada experiencias[i].n_prof existe en profesionales[]
    valid_n_profs = {p.n_prof for p in profesionales.profesionales}
    huerfanos = [
        e.n_correlativo for e in experiencias.experiencias
        if e.n_prof not in valid_n_profs
    ]
    if huerfanos:
        raise CrossJSONValidationError(
            f"experiencias con n_prof huérfano (correlativos): {huerfanos}"
        )

    # 4. Profesionales declarados pero sin experiencias: WARNING (no error)
    # → el backend lo manejará. No es invariante.

    # 5. Cargos de profesionales declarados deben matchear con personal_clave[].cargo
    # Esta validación es laxa (Claude puede normalizar texto) — solo warning si no hay
    # match para algún cargo postulado.
    cargos_bases = {c.cargo.upper().strip() for c in bases.personal_clave}
    cargos_propuestos = {
        p.especialidad_postulada.upper().strip()
        for p in profesionales.profesionales
    }
    sin_match = cargos_propuestos - cargos_bases
    if sin_match:
        # No es error, pero se loggea
        import warnings
        warnings.warn(
            f"Cargos postulados sin match exacto en bases.personal_clave: "
            f"{sin_match}. Backend hará match fuzzy."
        )
```

---

## 6 · Uso en la skill

```python
# main.py (extracto)
from pydantic import ValidationError

from schemas.bases import BasesSchema
from schemas.profesionales import ProfesionalesSchema
from schemas.experiencias import ExperienciasSchema
from schemas.cross import validate_cross_json


def parse_and_validate(raw_dict, schema_cls):
    """Parsea + valida; lanza ValidationError con detalles para retry."""
    return schema_cls.model_validate(raw_dict)


def main_skill(bases_pdf, propuesta_pdf):
    bases = parse_and_validate(agent_bases_output, BasesSchema)
    profs = parse_and_validate(profesionales_output, ProfesionalesSchema)
    exps  = parse_and_validate(experiencias_output, ExperienciasSchema)
    validate_cross_json(bases, profs, exps)

    # Serializar de vuelta a JSON (Pydantic respeta los aliases _meta)
    bases.model_dump(by_alias=True, mode="json")
    # ...
```

---

## 7 · Notas de portabilidad al backend

Cuando este schema se mueva a `Alpamayo-InfoObras/src/api/schemas/analizar.py`:

1. **Import path**: ajustar `from .shared import ...` a `from src.api.schemas.shared`.
2. **Decimal serialization**: configurar Pydantic para serializar `Decimal` como string en JSON (no float) — `ConfigDict(ser_json_inf_nan="strings")`.
3. **Date format**: por default Pydantic acepta `YYYY-MM-DD`. Para tolerar el formato del ingeniero (`11.05.2024`), agregar `@field_validator` que parse formatos alternos.
4. **Enriquecimiento**: el backend NO debería usar estas clases directamente para escribir el JSON enriquecido — debe usar **subclases** que agregan los campos del backend:
   ```python
   class ExperienciaPeriodoEnriquecida(ExperienciaPeriodo):
       fecha_creacion_emisor: date | None = None
       alerta_antiguedad_emisor: str | None = None
       alerta_firmante_no_representante: str | None = None
       duracion_meses: Decimal | None = None
       codigo_ciu: str | None = None
       codigo_infoobras: str | None = None
       alerta_experiencia_antigua: str | None = None
   ```

---

## 8 · Tests sugeridos

```python
# tests/test_schemas.py
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas.bases import BasesSchema
from schemas.profesionales import ProfesionalesSchema
from schemas.experiencias import ExperienciasSchema
from schemas.cross import validate_cross_json, CrossJSONValidationError


EXAMPLES = Path(__file__).parents[1] / "docs" / "examples"


def test_bases_example_valida():
    raw = json.loads((EXAMPLES / "lircay_bases.json").read_text())
    BasesSchema.model_validate(raw)


def test_profesionales_example_valida():
    raw = json.loads((EXAMPLES / "lircay_profesionales.json").read_text())
    ProfesionalesSchema.model_validate(raw)


def test_experiencias_example_valida():
    raw = json.loads((EXAMPLES / "lircay_experiencias.json").read_text())
    ExperienciasSchema.model_validate(raw)


def test_cross_json_lircay():
    bases = BasesSchema.model_validate(json.loads((EXAMPLES / "lircay_bases.json").read_text()))
    profs = ProfesionalesSchema.model_validate(json.loads((EXAMPLES / "lircay_profesionales.json").read_text()))
    exps  = ExperienciasSchema.model_validate(json.loads((EXAMPLES / "lircay_experiencias.json").read_text()))
    validate_cross_json(bases, profs, exps)


def test_n_prof_huerfano_falla():
    """Si n_prof en experiencias no existe en profesionales, debe fallar."""
    # ... fixture con n_prof huérfano ...
    with pytest.raises(CrossJSONValidationError, match="huérfano"):
        validate_cross_json(bases, profs, exps_huerfano)


def test_alerta_covid_inconsistente_falla():
    """Si alerta_covid se rellena pero el periodo no toca covid → falla."""
    # ... fixture con periodo fuera de covid pero con alerta_covid set ...
    with pytest.raises(ValidationError, match="no atraviesa"):
        ExperienciaPeriodo.model_validate(data_invalida)
```
