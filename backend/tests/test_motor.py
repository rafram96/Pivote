"""
Tests del motor del orquestador — las garantías de la máquina de estados.

Usan etapas fake (registran sus llamadas) para probar el CONTROL, no la
lógica de negocio: checkpoints, reanudación, ERROR_PARCIAL que no tumba,
rama paralela, human-in-the-loop con re-disparo acotado.
"""
from __future__ import annotations

from typing import Optional

import pytest

from orquestador import EtapaIngesta, Motor, RepositorioMemoria
from orquestador.etapas import Contexto, ErrorEstructural
from schemas import pipeline
from schemas.pipeline import Etapa, EstadoEtapa, JobEstado

ESPEJO_MIN = {
    "_meta": {"analisis_id": "test-001", "concurso": "CP-TEST", "postor": "POSTOR X"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN",
         "experiencias": [{"n": 1}, {"n": 2}]},
    ],
}


class EtapaFake:
    """Etapa configurable que registra cada llamada: (etapa, solo_items)."""

    def __init__(self, nombre: Etapa, registro: list, *,
                 estado: EstadoEtapa = EstadoEtapa.OK,
                 deja_revision: Optional[list[tuple[int, int]]] = None,
                 lanza: Optional[Exception] = None):
        self.nombre = nombre
        self.registro = registro
        self.estado = estado
        self.deja_revision = deja_revision or []
        self.lanza = lanza

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        self.registro.append((self.nombre, set(ctx.solo_items) if ctx.solo_items else None))
        if self.lanza:
            raise self.lanza
        for (np, ne) in self.deja_revision:
            ya = any(it.n_prof == np and it.n_exp == ne for it in ctx.job.items_revision)
            if not ya:
                ctx.job.items_revision.append(pipeline.ItemRevision(
                    n_prof=np, n_exp=ne, etapa=self.nombre,
                    motivo="CUI sin candidato fiable", accion_sugerida="pegar CUI"))
        return pipeline.ResultadoEtapa(
            etapa=self.nombre, estado=self.estado,
            metrica=pipeline.MetricaEtapa(items_total=2, items_ok=2))


def hacer_motor(registro, *, overrides=None, repo=None, notificaciones=None):
    etapas = {e: EtapaFake(e, registro) for e in Etapa.orden()}
    if overrides:
        etapas.update(overrides)
    repo = repo if repo is not None else RepositorioMemoria()
    notificar = notificaciones.append if notificaciones is not None else None
    return Motor(list(etapas.values()), repo, notificar=notificar), repo


# ── Flujo feliz ───────────────────────────────────────────────────────────────

def test_flujo_feliz_completa_las_8_etapas_en_orden():
    registro, notas = [], []
    motor, repo = hacer_motor(registro, notificaciones=notas)
    job = motor.crear_job(ESPEJO_MIN)
    job = motor.correr(job.job_id)

    assert job.estado == JobEstado.COMPLETADO
    assert [r.etapa for r in job.etapas] == Etapa.orden()
    assert all(r.estado == EstadoEtapa.OK for r in job.etapas)
    # la rama paralela corre en pool: el orden global respeta los tramos
    nombres = [n for n, _ in registro]
    assert nombres.index(Etapa.RESOLUCION_CUI) < nombres.index(Etapa.INFOOBRAS)
    assert nombres.index(Etapa.SUNAT) < nombres.index(Etapa.REGLAS)
    assert {Etapa.INFOOBRAS, Etapa.SUNAT} <= set(nombres)
    # progreso: la última notificación llega al 100%
    assert notas[-1].pct == 100.0
    # checkpoint persistido
    assert repo.cargar(job.job_id).estado == JobEstado.COMPLETADO


# ── Ingesta real ──────────────────────────────────────────────────────────────

def test_ingesta_real_acepta_espejo_minimo():
    registro = []
    motor, _ = hacer_motor(registro, overrides={Etapa.INGESTA: EtapaIngesta()})
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)
    assert job.estado == JobEstado.COMPLETADO
    assert job.etapa(Etapa.INGESTA).metrica.items_total == 2  # 2 experiencias


def test_ingesta_real_espejo_invalido_aborta_sin_correr_nada_mas():
    registro = []
    motor, _ = hacer_motor(registro, overrides={Etapa.INGESTA: EtapaIngesta()})
    espejo_roto = {"_meta": {"analisis_id": "x"}, "postor": {}, "profesionales": []}
    job = motor.correr(motor.crear_job(espejo_roto).job_id)

    assert job.estado == JobEstado.ERROR
    assert job.etapa(Etapa.INGESTA).estado == EstadoEtapa.ERROR
    assert "espejo inválido" in job.etapa(Etapa.INGESTA).error
    assert registro == []  # ninguna etapa posterior corrió


# ── Contención de fallos ──────────────────────────────────────────────────────

def test_error_parcial_no_tumba_el_job():
    registro = []
    motor, _ = hacer_motor(registro, overrides={
        Etapa.REGLAS: EtapaFake(Etapa.REGLAS, registro, estado=EstadoEtapa.ERROR_PARCIAL),
    })
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)

    assert job.etapa(Etapa.REGLAS).estado == EstadoEtapa.ERROR_PARCIAL
    assert job.estado == JobEstado.COMPLETADO  # siguió y terminó
    assert job.etapa(Etapa.PERSISTENCIA) is not None


def test_excepcion_no_controlada_se_contiene_como_error_de_etapa():
    registro = []
    motor, _ = hacer_motor(registro, overrides={
        Etapa.VALIDACION: EtapaFake(Etapa.VALIDACION, registro, lanza=RuntimeError("boom")),
    })
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)

    assert job.estado == JobEstado.ERROR
    assert "excepción no controlada" in job.etapa(Etapa.VALIDACION).error
    # no corrió nada después de VALIDACION
    assert {n for n, _ in registro} == {Etapa.INGESTA, Etapa.VALIDACION}


# ── Reanudación (checkpoints) ─────────────────────────────────────────────────

def test_reanudacion_salta_las_etapas_ya_ok():
    registro1 = []
    repo = RepositorioMemoria()
    motor1, _ = hacer_motor(registro1, repo=repo, overrides={
        Etapa.SUNAT: EtapaFake(Etapa.SUNAT, registro1,
                               lanza=ErrorEstructural("SUNAT caído")),
    })
    job = motor1.correr(motor1.crear_job(ESPEJO_MIN).job_id)
    assert job.estado == JobEstado.ERROR
    assert job.etapa(Etapa.INFOOBRAS).estado == EstadoEtapa.OK  # su rama sí terminó

    # "Nuevo proceso": mismo repo, etapa SUNAT reparada
    registro2 = []
    motor2, _ = hacer_motor(registro2, repo=repo)
    job2 = motor2.correr(job.job_id)

    assert job2.estado == JobEstado.COMPLETADO
    corridas = {n for n, _ in registro2}
    # reanudó: NO re-corrió lo que ya estaba OK
    assert Etapa.INGESTA not in corridas
    assert Etapa.INFOOBRAS not in corridas
    # sí corrió la fallida y lo que faltaba aguas abajo
    assert {Etapa.SUNAT, Etapa.REGLAS, Etapa.EXCEL, Etapa.PERSISTENCIA} <= corridas


# ── Human-in-the-loop ─────────────────────────────────────────────────────────

def test_items_revision_dejan_el_job_en_requiere_revision():
    registro = []
    motor, _ = hacer_motor(registro, overrides={
        Etapa.RESOLUCION_CUI: EtapaFake(Etapa.RESOLUCION_CUI, registro,
                                        deja_revision=[(1, 2)]),
    })
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)

    assert job.estado == JobEstado.REQUIERE_REVISION
    assert job.pendientes_humano == 1
    assert job.etapa(Etapa.RESOLUCION_CUI).estado == EstadoEtapa.OK_CON_REVISION
    # el pipeline NO se detuvo: el Excel salió con lo que había
    assert job.etapa(Etapa.EXCEL).estado == EstadoEtapa.OK


def test_resolver_revision_redispara_solo_esa_experiencia_aguas_abajo():
    registro = []
    motor, repo = hacer_motor(registro, overrides={
        Etapa.RESOLUCION_CUI: EtapaFake(Etapa.RESOLUCION_CUI, registro,
                                        deja_revision=[(1, 2)]),
    })
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)
    assert job.estado == JobEstado.REQUIERE_REVISION

    registro.clear()
    job = motor.resolver_revision(job.job_id, n_prof=1, n_exp=2, dato={"cui": "2338373"})

    # corrió desde RESOLUCION_CUI hasta el final, acotado al item
    assert [n for n, _ in registro] == [
        Etapa.RESOLUCION_CUI, Etapa.INFOOBRAS, Etapa.SUNAT,
        Etapa.REGLAS, Etapa.EXCEL, Etapa.PERSISTENCIA]
    assert all(items == {(1, 2)} for _, items in registro)
    # el item quedó resuelto y el job completo
    assert job.pendientes_humano == 0
    assert job.estado == JobEstado.COMPLETADO
    assert job.etapa(Etapa.RESOLUCION_CUI).estado == EstadoEtapa.OK  # subió de OK_CON_REVISION
    assert repo.cargar(job.job_id).estado == JobEstado.COMPLETADO


def test_resolver_revision_inexistente_falla_claro():
    registro = []
    motor, _ = hacer_motor(registro)
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)
    with pytest.raises(ValueError, match="no hay ItemRevision"):
        motor.resolver_revision(job.job_id, n_prof=9, n_exp=9, dato={})
