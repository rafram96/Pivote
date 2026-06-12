"""
Pydantic v2 — Capa de control: el orquestador del pipeline backend.

El orquestador secuencia las 8 etapas (ingesta → validación → resolución CUI →
InfoObras ∥ SUNAT → reglas → Excel → persistencia) como una **máquina de estados**
con checkpoint por etapa, reintentos y human-in-the-loop. Diseño en
`docs/backend/orquestador.md`.

Invariantes de diseño:
- La **experiencia** es la unidad de fan-out (resolución + cruces corren por-item,
  con límite de concurrencia por fuente).
- Una etapa **nunca tumba el job entero** por un item: marca `ERROR_PARCIAL` y sigue.
  Solo un fallo estructural (schema inválido, DB caída) → `JobEstado.ERROR`.
- Cada etapa escribe un **checkpoint** (`ResultadoEtapa`) → el job es **reanudable**.
- Items sin resolver no bloquean: van a `items_revision`; el humano pega el dato y se
  re-ejecutan **solo las etapas aguas abajo** de esa experiencia.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _ModelLax(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ── Etapas del pipeline (orden canónico) ─────────────────────────────────────
class Etapa(str, Enum):
    INGESTA = "ingesta"               # 0 · recibe, valida schema, crea job
    VALIDACION = "validacion"         # 1 · verifica lo que Claude afirma (15 notas)
    RESOLUCION_CUI = "resolucion_cui" # 2 · cada experiencia → CUI de obra
    INFOOBRAS = "infoobras"           # 3a · vía CUI: paralizaciones, códigos, ZIP
    SUNAT = "sunat"                   # 3b · vía RUC: ALT04, ALT12, vinculación
    REGLAS = "reglas"                 # 4 · Paso 5 días efectivos, ALT03 25 años
    EXCEL = "excel"                   # 5 · regenera el Excel final enriquecido
    PERSISTENCIA = "persistencia"     # 6 · PostgreSQL + notifica panel

    @classmethod
    def orden(cls) -> list["Etapa"]:
        return [cls.INGESTA, cls.VALIDACION, cls.RESOLUCION_CUI, cls.INFOOBRAS,
                cls.SUNAT, cls.REGLAS, cls.EXCEL, cls.PERSISTENCIA]


# ── Máquina de estados del job ───────────────────────────────────────────────
class JobEstado(str, Enum):
    RECIBIDO = "recibido"
    EN_PROCESO = "en_proceso"
    REQUIERE_REVISION = "requiere_revision"  # terminó el pipeline, pero hay items para humano
    COMPLETADO = "completado"                # todo resuelto, Excel final listo
    ERROR = "error"                          # fallo estructural → abortó


class EstadoEtapa(str, Enum):
    PENDIENTE = "pendiente"
    EN_CURSO = "en_curso"
    OK = "ok"
    OK_CON_REVISION = "ok_con_revision"      # corrió, pero dejó items a revisar
    ERROR_PARCIAL = "error_parcial"          # algunos items fallaron; el resto continuó
    ERROR = "error"                          # la etapa entera falló (estructural)


# ── Observaciones y alertas ──────────────────────────────────────────────────
class Severidad(str, Enum):
    INFO = "info"
    ADVERTENCIA = "advertencia"
    ALERTA = "alerta"
    CRITICA = "critica"


class Observacion(_Model):
    """Hallazgo del validador o de los cruces. El sistema señala, no juzga."""
    codigo: Optional[str] = None          # ALT04, ALT12, ALT03, ALT11, NOTA1...
    severidad: Severidad = Severidad.INFO
    mensaje: str
    origen: Etapa
    referencia: Optional[str] = None      # "prof=3 exp=2 folio=001495"


# ── Human-in-the-loop ────────────────────────────────────────────────────────
class ItemRevision(_Model):
    """Unidad que requiere intervención humana. NO bloquea el job: se entrega lo que
    se tiene + esta lista. Cuando el humano resuelve, se re-ejecuta aguas abajo."""
    n_prof: int = Field(ge=1)
    n_exp: int = Field(ge=1)
    etapa: Etapa
    motivo: str                            # "CUI sin candidato fiable", "emisor sin RUC consultable"
    candidatos: list[dict] = Field(default_factory=list)  # para que el humano elija o confirme
    accion_sugerida: Optional[str] = None  # "pegar CUI", "confirmar firmante facultado"
    resuelto: bool = False
    # Contexto para que el humano decida sin abrir nada más (lo muestra el panel):
    profesional: Optional[str] = None
    cargo: Optional[str] = None
    proyecto: Optional[str] = None
    fechas: Optional[str] = None


# ── Métrica y resultado por etapa (el checkpoint) ────────────────────────────
class MetricaEtapa(_Model):
    items_total: int = Field(default=0, ge=0)
    items_ok: int = Field(default=0, ge=0)
    items_revision: int = Field(default=0, ge=0)
    items_error: int = Field(default=0, ge=0)
    reintentos: int = Field(default=0, ge=0)       # transitorios reintentados (scrapers)
    duracion_ms: Optional[int] = Field(default=None, ge=0)


class ResultadoEtapa(_Model):
    """Checkpoint persistente de una etapa. Reanudar = saltar las etapas con estado OK."""
    etapa: Etapa
    estado: EstadoEtapa = EstadoEtapa.PENDIENTE
    metrica: MetricaEtapa = Field(default_factory=MetricaEtapa)
    observaciones: list[Observacion] = Field(default_factory=list)
    iniciado_en: Optional[datetime] = None
    terminado_en: Optional[datetime] = None
    error: Optional[str] = None            # traza si estado == ERROR


# ── Evento de progreso (websocket) ───────────────────────────────────────────
class ProgresoJob(_Model):
    """Lo que el orquestador empuja al panel tras cada etapa/lote de items."""
    job_id: str
    estado: JobEstado
    etapa_actual: Optional[Etapa] = None
    pct: float = Field(default=0, ge=0, le=100)
    mensaje: Optional[str] = None


# ── El concurso (la unidad mental del usuario; el job es plomería) ───────────
class Concurso(_ModelLax):
    """Entidad central del panel (decisión: modelarla desde el día 1 — ver
    docs/frontend/README.md). Un concurso agrupa los análisis (jobs) de sus
    N postores y habilita el cuadro comparativo y el histórico."""
    concurso_id: str
    nomenclatura: str                      # "CP-02-2025/GOB.REG.HVCA/C"
    entidad: Optional[str] = None          # entidad convocante
    fecha_presentacion: Optional[datetime] = None
    creado_en: Optional[datetime] = None


# ── El registro del job (PostgreSQL) ─────────────────────────────────────────
class Job(_ModelLax):
    """Estado persistente del análisis. El orquestador lo actualiza tras cada etapa
    (checkpoint) → si el proceso muere, reanuda desde la última etapa OK.
    El JSON espejo enriquecido y los `EnriquecimientoExperiencia` se referencian
    aparte (no se embeben aquí para mantener el registro liviano)."""
    job_id: str
    analisis_id: str
    concurso_id: Optional[str] = None      # FK a Concurso (panel agrupa por esto)
    concurso: Optional[str] = None         # texto libre del espejo (_meta.concurso)
    postor: Optional[str] = None
    origen: Optional[str] = None           # "mcp" (automático desde Claude) | "dropzone"
    estado: JobEstado = JobEstado.RECIBIDO
    etapas: list[ResultadoEtapa] = Field(default_factory=list)
    observaciones: list[Observacion] = Field(default_factory=list)
    items_revision: list[ItemRevision] = Field(default_factory=list)
    excel_final: Optional[str] = None      # ruta/ref del Excel regenerado
    zip_infoobras: Optional[str] = None    # ref del ZIP de archivos (⏳ futuro)
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None

    def etapa(self, etapa: "Etapa") -> Optional[ResultadoEtapa]:
        return next((e for e in self.etapas if e.etapa == etapa), None)

    @property
    def pendientes_humano(self) -> int:
        return sum(1 for it in self.items_revision if not it.resuelto)
