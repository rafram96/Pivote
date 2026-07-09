"""
Tests del progreso FINO en memoria (RegistroProgreso) y su cableado en el motor.
Offline puro: no tocan red ni disco.
"""
from __future__ import annotations

import threading
import time

from orquestador import Motor, RepositorioMemoria
from orquestador.etapas import Contexto
from orquestador.progreso import RegistroProgreso
from schemas import pipeline
from schemas.pipeline import Etapa, EstadoEtapa, JobEstado

ESPEJO_MIN = {
    "_meta": {"analisis_id": "prog-001"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN",
         "experiencias": [{"n": 1}, {"n": 2}]},
    ],
}


# ── RegistroProgreso ──────────────────────────────────────────────────────────

def test_reportar_y_leer_una_etapa():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 3, 10, "Verificando la obra 3 de 10")
    assert reg.etapas("j1") == {
        "infoobras": {"item_actual": 3, "items_total": 10,
                      "descripcion": "Verificando la obra 3 de 10"}}


def test_dos_etapas_coexisten_rama_paralela():
    """INFOOBRAS ∥ SUNAT reportan a la vez sobre el mismo job — ambas conviven."""
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 3, 10, "obra 3")
    reg.reportar("j1", "sunat", 5, 8, "emisor 5")
    etapas = reg.etapas("j1")
    assert set(etapas) == {"infoobras", "sunat"}
    assert etapas["sunat"]["item_actual"] == 5


def test_etapas_devuelve_copia_defensiva():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 1, 2, "x")
    snap = reg.etapas("j1")
    snap["infoobras"]["item_actual"] = 99          # mutar la copia
    assert reg.etapas("j1")["infoobras"]["item_actual"] == 1   # el interno no cambió


def test_reporte_pisa_al_anterior_de_la_misma_etapa():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 1, 10, "obra 1")
    reg.reportar("j1", "infoobras", 2, 10, "obra 2")
    assert reg.etapas("j1")["infoobras"]["item_actual"] == 2


def test_limpiar_olvida_el_job():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 1, 2, "x")
    reg.limpiar("j1")
    assert reg.etapas("j1") == {}
    reg.limpiar("j1")   # idempotente: no revienta si ya no está


def test_purgar_viejos_descarta_por_ttl():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 1, 2, "x")
    for viva in reg._jobs["j1"].values():          # backdate del reloj monotónico
        viva.actualizado_en = time.monotonic() - (reg._TTL_S + 10)
    reg.purgar_viejos()
    assert reg.etapas("j1") == {}


def test_purgar_no_toca_jobs_recientes():
    reg = RegistroProgreso()
    reg.reportar("j1", "infoobras", 1, 2, "x")
    reg.purgar_viejos()
    assert reg.etapas("j1") != {}


def test_concurrencia_dos_hilos_no_corrompen():
    reg = RegistroProgreso()

    def escribir(etapa):
        for i in range(200):
            reg.reportar("j1", etapa, i, 200, f"{etapa} {i}")

    t1 = threading.Thread(target=escribir, args=("infoobras",))
    t2 = threading.Thread(target=escribir, args=("sunat",))
    t1.start(); t2.start(); t1.join(); t2.join()
    etapas = reg.etapas("j1")
    assert etapas["infoobras"]["item_actual"] == 199
    assert etapas["sunat"]["item_actual"] == 199


# ── Cableado en el motor ──────────────────────────────────────────────────────

class _EtapaOk:
    """Etapa mínima que termina OK sin lógica."""
    def __init__(self, nombre):
        self.nombre = nombre

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        return pipeline.ResultadoEtapa(etapa=self.nombre, estado=EstadoEtapa.OK,
                                       metrica=pipeline.MetricaEtapa())


class _EtapaReporta(_EtapaOk):
    """Etapa que reporta progreso fino a través de ctx.reportar."""
    def __init__(self, nombre, capturas):
        super().__init__(nombre)
        self._capturas = capturas

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ctx.reportar(self.nombre, 1, 3, "probando")
        self._capturas.append("corrio")
        return super().correr(ctx)


def _juego(override_nombre, etapa_obj):
    etapas = [_EtapaOk(e) for e in Etapa.orden()]
    etapas[Etapa.orden().index(override_nombre)] = etapa_obj
    return etapas


def test_motor_pasa_reporter_a_las_etapas():
    reg = RegistroProgreso()
    etapas = _juego(Etapa.INFOOBRAS, _EtapaReporta(Etapa.INFOOBRAS, []))

    def reporter(job_id, etapa, i, total, desc):
        reg.reportar(job_id, etapa.value, i, total, desc)

    motor = Motor(etapas, RepositorioMemoria(), reportar=reporter)
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)

    assert job.estado == JobEstado.COMPLETADO
    # el reporter recibió la etapa correcta (su .value) y quedó registrado
    assert reg.etapas(job.job_id).get("infoobras") == {
        "item_actual": 1, "items_total": 3, "descripcion": "probando"}


def test_reporter_default_no_rompe_sin_cablear():
    """Motor sin `reportar=`: ctx.reportar es no-op, la etapa que reporta no falla."""
    capturas = []
    etapas = _juego(Etapa.SUNAT, _EtapaReporta(Etapa.SUNAT, capturas))
    motor = Motor(etapas, RepositorioMemoria())    # sin reporter
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)
    assert job.estado == JobEstado.COMPLETADO
    assert capturas == ["corrio"]
