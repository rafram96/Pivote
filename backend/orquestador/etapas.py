"""
Contrato de etapa del orquestador + etapas del esqueleto.

Reglas del contrato (docs/backend/orquestador.md §3):
  1. Idempotente: correr dos veces con la misma entrada = mismo resultado.
  2. NO lanza por item: un item que falla suma a `metrica.items_error` y la
     etapa termina ERROR_PARCIAL. Solo un fallo estructural (schema inválido,
     BD caída) lanza `ErrorEstructural` → el motor aborta el job.
  3. Acumula, no pisa: agrega Observacion (vía ResultadoEtapa) e ItemRevision
     (directo en ctx.job.items_revision); nunca borra lo previo.
  4. El checkpoint lo escribe el MOTOR (no la etapa) tras cada corrida.

En el esqueleto, las etapas 2-6 son stubs cableables: definen la interfaz y
el comportamiento de control (métricas, revisión, solo_items) sin la lógica
de negocio, que se conecta después (validador 15 NOTAS, resolución CUI,
scrapers, reglas, Excel).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from pydantic import ValidationError

from schemas import pipeline
from schemas.espejo import JsonEspejo


class ErrorEstructural(Exception):
    """El job entero no puede continuar (schema inválido, BD caída, etc.)."""


@dataclass
class Contexto:
    """Lo que el motor le pasa a cada etapa."""
    job: pipeline.Job
    espejo: dict                          # espejo crudo; tipar con JsonEspejo si se necesita
    # Re-disparo acotado (human-in-the-loop): si no es None, la etapa procesa
    # SOLO esas experiencias [(n_prof, n_exp), ...].
    solo_items: Optional[set[tuple[int, int]]] = None
    # Dato que el humano aportó al resolver un ItemRevision:
    # {(n_prof, n_exp): {"cui": "...", ...}}
    datos_humano: dict = field(default_factory=dict)
    # Lo que las etapas van llenando (CUI, paralizaciones, SUNAT, días efectivos).
    # Claves string para serializar: "n_prof:n_exp" por experiencia, "prof:n" por
    # profesional. El motor lo persiste tras cada etapa (sobrevive reanudaciones).
    enriquecimiento: dict = field(default_factory=dict)

    def items_experiencia(self):
        """Itera (exp_dict, (n_prof, n_exp)) respetando `solo_items`."""
        for p in self.espejo.get("profesionales", []):
            for e in p.get("experiencias", []):
                clave = (p.get("n_prof"), e.get("n"))
                if self.solo_items is not None and clave not in self.solo_items:
                    continue
                yield e, clave


@runtime_checkable
class EtapaBase(Protocol):
    nombre: pipeline.Etapa

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa: ...


# ── Etapa 0 · INGESTA (real desde el esqueleto) ──────────────────────────────

class EtapaIngesta:
    """Valida el espejo contra el schema Pydantic. Espejo inválido = fallo
    estructural: el job no tiene con qué continuar."""

    nombre = pipeline.Etapa.INGESTA

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        try:
            espejo = JsonEspejo.model_validate(ctx.espejo)
        except ValidationError as e:
            detalle = "; ".join(
                f"[{'.'.join(str(x) for x in err['loc'])}] {err['msg']}"
                for err in e.errors()[:10]
            )
            raise ErrorEstructural(
                f"espejo inválido ({e.error_count()} errores): {detalle}"
            ) from e

        n_exp = sum(len(p.experiencias) for p in espejo.profesionales)
        return pipeline.ResultadoEtapa(
            etapa=self.nombre,
            estado=pipeline.EstadoEtapa.OK,
            metrica=pipeline.MetricaEtapa(items_total=n_exp, items_ok=n_exp),
        )


# ── Etapas 1-6 · stubs cableables ────────────────────────────────────────────

class EtapaStub:
    """Stub de etapa: recorre las experiencias (respetando `solo_items`) y las
    marca OK. Sirve para correr el motor end-to-end mientras se cablea la
    lógica real de cada componente."""

    def __init__(self, nombre: pipeline.Etapa):
        self.nombre = nombre

    def _items(self, ctx: Contexto) -> list[tuple[int, int]]:
        pares = [
            (p.get("n_prof", 0), e.get("n", 0))
            for p in ctx.espejo.get("profesionales", [])
            for e in p.get("experiencias", [])
        ]
        if ctx.solo_items is not None:
            pares = [par for par in pares if par in ctx.solo_items]
        return pares

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        items = self._items(ctx)
        return pipeline.ResultadoEtapa(
            etapa=self.nombre,
            estado=pipeline.EstadoEtapa.OK,
            metrica=pipeline.MetricaEtapa(
                items_total=len(items), items_ok=len(items),
            ),
        )


def etapas_esqueleto() -> list[EtapaBase]:
    """El juego completo de etapas del esqueleto: ingesta real + stubs."""
    return [
        EtapaIngesta(),
        EtapaStub(pipeline.Etapa.VALIDACION),
        EtapaStub(pipeline.Etapa.RESOLUCION_CUI),
        EtapaStub(pipeline.Etapa.INFOOBRAS),
        EtapaStub(pipeline.Etapa.SUNAT),
        EtapaStub(pipeline.Etapa.REGLAS),
        EtapaStub(pipeline.Etapa.EXCEL),
        EtapaStub(pipeline.Etapa.PERSISTENCIA),
    ]
