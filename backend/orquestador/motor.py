"""
Motor del orquestador — la máquina de estados del pipeline.

Implementa las garantías de docs/backend/orquestador.md §4:
  - Checkpoint tras cada etapa → el job es REANUDABLE (correr() salta las OK).
  - Una etapa que falla por items NO tumba el job (ERROR_PARCIAL y sigue);
    solo ErrorEstructural (o excepción no controlada) → JobEstado.ERROR.
  - INFOOBRAS ∥ SUNAT corren en paralelo (ambas dependen de RESOLUCION_CUI;
    REGLAS espera a las dos).
  - Human-in-the-loop: resolver_revision() re-ejecuta SOLO esa experiencia
    desde la etapa del item hacia abajo (solo_items), sin tocar el resto.
  - Progreso: notifica ProgresoJob tras cada etapa (callback inyectable —
    el websocket del panel se conecta ahí).
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional, Sequence

from schemas import pipeline
from schemas.cargo import normalizar_cargos_espejo
from .etapas import Contexto, ErrorEstructural, EtapaBase
from .repositorio import Repositorio

logger = logging.getLogger(__name__)

# Las dos ramas que corren en paralelo tras RESOLUCION_CUI.
_RAMA_PARALELA = (pipeline.Etapa.INFOOBRAS, pipeline.Etapa.SUNAT)

Notificador = Callable[[pipeline.ProgresoJob], None]
# Progreso fino por ítem: (job_id, etapa, item_actual, items_total, descripcion).
# Lo escribe el RegistroProgreso de la API; el motor solo lo reenvía a las etapas.
ReporteProgreso = Callable[[str, pipeline.Etapa, int, int, str], None]


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Motor:
    def __init__(
        self,
        etapas: Sequence[EtapaBase],
        repositorio: Repositorio,
        notificar: Optional[Notificador] = None,
        reportar: Optional[ReporteProgreso] = None,
    ):
        self._etapas: dict[pipeline.Etapa, EtapaBase] = {e.nombre: e for e in etapas}
        faltantes = [e for e in pipeline.Etapa.orden() if e not in self._etapas]
        if faltantes:
            raise ValueError(f"faltan etapas: {[e.value for e in faltantes]}")
        self._repo = repositorio
        self._notificar = notificar or (lambda _p: None)
        self._reportar = reportar or (lambda *_: None)

    def _reporter_de(self, job_id: str):
        """Adapta el reporter de proceso (con job_id) a la firma que espera el
        Contexto (sin job_id) — cierra sobre el job actual."""
        return lambda etapa, i, total, desc: self._reportar(job_id, etapa, i, total, desc)

    # ── Ciclo de vida ────────────────────────────────────────────────────────

    def crear_job(self, espejo: dict, *, concurso_id: Optional[str] = None) -> pipeline.Job:
        """Registra el job (estado RECIBIDO) y guarda el espejo. No corre nada."""
        # B · cargo atómico: si la skill incrustó la correspondencia de bases en
        # el nombre del cargo, sepárala a `cargo_bases_num/nombre` antes de
        # persistir (idempotente; no toca lo que la skill ya separó).
        if isinstance(espejo, dict):
            normalizar_cargos_espejo(espejo)
        meta = espejo.get("_meta", {}) if isinstance(espejo, dict) else {}
        job = pipeline.Job(
            job_id=uuid.uuid4().hex[:12],
            analisis_id=str(meta.get("analisis_id") or "(sin analisis_id)"),
            slug=meta.get("slug"),
            concurso_id=concurso_id,
            concurso=meta.get("concurso"),
            postor=meta.get("postor"),
            estado=pipeline.JobEstado.RECIBIDO,
            creado_en=_ahora(),
            actualizado_en=_ahora(),
        )
        self._repo.guardar(job)
        self._repo.guardar_espejo(job.job_id, espejo)
        return job

    def correr(self, job_id: str) -> pipeline.Job:
        """Corre el pipeline completo. REANUDABLE: las etapas con checkpoint OK
        se saltan, así que re-llamar tras una caída continúa donde quedó."""
        job = self._cargar(job_id)
        espejo = self._repo.cargar_espejo(job_id) or {}
        ctx = Contexto(job=job, espejo=espejo,
                       enriquecimiento=self._repo.cargar_enriquecimiento(job_id),
                       reportar=self._reporter_de(job_id))

        job.estado = pipeline.JobEstado.EN_PROCESO
        self._checkpoint(job)

        orden = pipeline.Etapa.orden()
        i = 0
        while i < len(orden):
            nombre = orden[i]

            if nombre == _RAMA_PARALELA[0]:
                # INFOOBRAS ∥ SUNAT — solo las que no estén ya OK (reanudación)
                pendientes = [e for e in _RAMA_PARALELA if not self._etapa_ok(job, e)]
                if pendientes:
                    with ThreadPoolExecutor(max_workers=len(pendientes)) as pool:
                        futuros = [pool.submit(self._ejecutar, nombre_e, ctx) for nombre_e in pendientes]
                        resultados = [f.result() for f in futuros]
                    abortar = False
                    for res in resultados:
                        self._registrar(job, res)
                        abortar = abortar or res.estado == pipeline.EstadoEtapa.ERROR
                    self._repo.guardar_enriquecimiento(job.job_id, ctx.enriquecimiento)
                    self._checkpoint(job, etapa_actual=nombre)
                    if abortar:
                        return self._abortar(job)
                i += len(_RAMA_PARALELA)
                continue

            if self._etapa_ok(job, nombre):
                i += 1
                continue

            res = self._ejecutar(nombre, ctx)
            self._registrar(job, res)
            self._repo.guardar_enriquecimiento(job.job_id, ctx.enriquecimiento)
            self._checkpoint(job, etapa_actual=nombre)
            if res.estado == pipeline.EstadoEtapa.ERROR:
                return self._abortar(job)
            i += 1

        self._log_resumen(job)
        job.estado = (
            pipeline.JobEstado.REQUIERE_REVISION
            if job.pendientes_humano
            else pipeline.JobEstado.COMPLETADO
        )
        self._checkpoint(job)
        return job

    def resolver_revision(
        self, job_id: str, n_prof: int, n_exp: int, dato: dict
    ) -> pipeline.Job:
        """Human-in-the-loop: el humano resuelve UN ItemRevision (p. ej. pega el
        CUI) y se re-ejecuta SOLO esa experiencia desde la etapa del item hacia
        abajo. El resto del job no se toca."""
        job = self._cargar(job_id)
        item = next(
            (it for it in job.items_revision
             if it.n_prof == n_prof and it.n_exp == n_exp and not it.resuelto),
            None,
        )
        if item is None:
            raise ValueError(f"no hay ItemRevision pendiente para prof={n_prof} exp={n_exp}")

        item.resuelto = True
        espejo = self._repo.cargar_espejo(job_id) or {}
        ctx = Contexto(
            job=job,
            espejo=espejo,
            solo_items={(n_prof, n_exp)},
            datos_humano={(n_prof, n_exp): dato},
            enriquecimiento=self._repo.cargar_enriquecimiento(job_id),
            reportar=self._reporter_de(job_id),
        )

        orden = pipeline.Etapa.orden()
        aguas_abajo = orden[orden.index(item.etapa):]
        for nombre in aguas_abajo:
            # La rama paralela se corre secuencial en el re-disparo (1 item: no
            # vale la pena el pool) — y solo si la etapa pertenece al tramo.
            res = self._ejecutar(nombre, ctx)
            self._registrar(job, res, parcial=True)
            self._repo.guardar_enriquecimiento(job.job_id, ctx.enriquecimiento)
            if res.estado == pipeline.EstadoEtapa.ERROR:
                self._checkpoint(job)
                return self._abortar(job)

        job.estado = (
            pipeline.JobEstado.REQUIERE_REVISION
            if job.pendientes_humano
            else pipeline.JobEstado.COMPLETADO
        )
        self._checkpoint(job)
        return job

    # ── Internos ─────────────────────────────────────────────────────────────

    def _cargar(self, job_id: str) -> pipeline.Job:
        job = self._repo.cargar(job_id)
        if job is None:
            raise ValueError(f"job no existe: {job_id}")
        return job

    def _etapa_ok(self, job: pipeline.Job, nombre: pipeline.Etapa) -> bool:
        res = job.etapa(nombre)
        return res is not None and res.estado in (
            pipeline.EstadoEtapa.OK, pipeline.EstadoEtapa.OK_CON_REVISION,
        )

    def _log_resumen(self, job: pipeline.Job) -> None:
        """Línea de resumen para detectar cuellos de botella: duración por etapa +
        descargas/reintentos de InfoObras. (infoobras∥sunat van en paralelo, así que
        el 'wall' descuenta el solape de la más corta de las dos.)"""
        durs = {r.etapa.value: (r.metrica.duracion_ms or 0) for r in job.etapas}
        wall = sum(durs.values()) - min(durs.get("infoobras", 0), durs.get("sunat", 0))
        partes = " · ".join(f"{k} {v / 1000:.0f}s"
                            for k, v in sorted(durs.items(), key=lambda x: -x[1]) if v >= 1000)
        logger.info("RESUMEN job %s · %s · wall≈%.0fs · %s · descargas: diferidas (ver línea DESCARGAS)",
                    job.job_id, getattr(job.estado, "value", job.estado),
                    wall / 1000, partes or "(todo <1s)")

    def _ejecutar(self, nombre: pipeline.Etapa, ctx: Contexto) -> pipeline.ResultadoEtapa:
        """Corre una etapa con cronómetro y contención de errores. Una excepción
        cualquiera NO mata el proceso: se convierte en ResultadoEtapa(ERROR)."""
        etapa = self._etapas[nombre]
        inicio = _ahora()
        try:
            res = etapa.correr(ctx)
        except ErrorEstructural as e:
            res = pipeline.ResultadoEtapa(
                etapa=nombre, estado=pipeline.EstadoEtapa.ERROR, error=str(e))
        except Exception as e:  # noqa: BLE001 — contención: el motor nunca revienta
            logger.exception("etapa %s reventó", nombre.value)
            res = pipeline.ResultadoEtapa(
                etapa=nombre, estado=pipeline.EstadoEtapa.ERROR,
                error=f"excepción no controlada: {e!r}")
        res.iniciado_en = inicio
        res.terminado_en = _ahora()
        res.metrica.duracion_ms = int((res.terminado_en - inicio).total_seconds() * 1000)

        # Si la etapa dejó items a revisión y terminó OK, refleja OK_CON_REVISION.
        if res.estado == pipeline.EstadoEtapa.OK and any(
            not it.resuelto and it.etapa == nombre for it in ctx.job.items_revision
        ):
            res.estado = pipeline.EstadoEtapa.OK_CON_REVISION
        return res

    def _registrar(
        self, job: pipeline.Job, res: pipeline.ResultadoEtapa, *, parcial: bool = False
    ) -> None:
        """Acumula el resultado en el job. En corrida normal el checkpoint de la
        etapa se REEMPLAZA (la etapa es idempotente); en re-disparo parcial se
        FUSIONA: contadores se suman al checkpoint existente y, si ya no quedan
        pendientes de esa etapa, su estado sube a OK."""
        job.observaciones.extend(res.observaciones)
        idx = next((i for i, e in enumerate(job.etapas) if e.etapa == res.etapa), None)
        if idx is None:
            job.etapas.append(res)
            return
        existente = job.etapas[idx]
        if not parcial:
            job.etapas[idx] = res
            return
        m, mr = existente.metrica, res.metrica
        m.items_ok += mr.items_ok
        m.items_error += mr.items_error
        m.reintentos += mr.reintentos
        m.items_revision = sum(
            1 for it in job.items_revision if it.etapa == res.etapa and not it.resuelto)
        existente.observaciones.extend(res.observaciones)
        existente.terminado_en = res.terminado_en
        if (existente.estado == pipeline.EstadoEtapa.OK_CON_REVISION
                and m.items_revision == 0):
            existente.estado = pipeline.EstadoEtapa.OK

    def _checkpoint(
        self, job: pipeline.Job, *, etapa_actual: Optional[pipeline.Etapa] = None
    ) -> None:
        job.actualizado_en = _ahora()
        self._repo.guardar(job)
        total = len(pipeline.Etapa.orden())
        completas = sum(1 for e in job.etapas if e.estado in (
            pipeline.EstadoEtapa.OK, pipeline.EstadoEtapa.OK_CON_REVISION,
            pipeline.EstadoEtapa.ERROR_PARCIAL))
        self._notificar(pipeline.ProgresoJob(
            job_id=job.job_id,
            estado=job.estado,
            etapa_actual=etapa_actual,
            pct=round(100 * completas / total, 1),
            mensaje=None,
        ))

    def _abortar(self, job: pipeline.Job) -> pipeline.Job:
        job.estado = pipeline.JobEstado.ERROR
        self._checkpoint(job)
        return job
