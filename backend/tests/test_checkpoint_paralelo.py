"""Contratos del checkpoint paralelo del motor.

Las etapas fake solo modelan control: nunca consultan red ni escriben fuera del
repositorio temporal. Estos casos deben fallar contra el motor previo porque
compartía Contexto y esperaba a las tres ramas antes de persistir.
"""
from __future__ import annotations

from copy import deepcopy
from threading import Event, Thread

import pytest

from orquestador import Motor
from orquestador.etapas import ErrorEstructural
from orquestador.repositorio import RepositorioArchivos
from schemas import pipeline
from schemas.pipeline import Etapa, EstadoEtapa, JobEstado, ItemRevision

from tests.test_motor import ESPEJO_MIN, EtapaFake


class FuenteFake:
    def __init__(self, nombre, registro, *, listo=None, liberar=None,
                 delta=None, error=None, revisiones=None, accion=None):
        self.nombre, self.registro = nombre, registro
        self.listo, self.liberar, self.delta, self.error = listo, liberar, delta or {}, error
        self.revisiones = revisiones or []
        self.accion = accion

    def correr(self, ctx):
        self.registro.append(self.nombre)
        if self.accion:
            self.accion(ctx)
        if self.listo:
            self.listo.set()
        if self.liberar:
            assert self.liberar.wait(timeout=15), f"la fuente {self.nombre} no fue liberada"
        if self.error:
            raise self.error
        for np_, ne in self.revisiones:
            ctx.job.items_revision.append(ItemRevision(
                n_prof=np_, n_exp=ne, etapa=self.nombre,
                motivo=f"revisión {self.nombre.value}", accion_sugerida="revisar"))
        for clave, valores in self.delta.items():
            ctx.enriquecimiento.setdefault(clave, {}).update(valores)
        return pipeline.ResultadoEtapa(
            etapa=self.nombre, estado=EstadoEtapa.OK,
            metrica=pipeline.MetricaEtapa(items_total=1, items_ok=1))


def motor_paralelo(tmp_path, registro, *, info=None, sunat=None, renipress=None,
                   reglas=None, notificar=None, clase_motor=Motor):
    etapas = {e: EtapaFake(e, registro) for e in Etapa.orden()}
    etapas[Etapa.INFOOBRAS] = info or FuenteFake(Etapa.INFOOBRAS, registro)
    etapas[Etapa.SUNAT] = sunat or FuenteFake(Etapa.SUNAT, registro)
    etapas[Etapa.RENIPRESS] = renipress or FuenteFake(Etapa.RENIPRESS, registro)
    if reglas is not None:
        etapas[Etapa.REGLAS] = reglas
    return clase_motor(list(etapas.values()), RepositorioArchivos(tmp_path),
                       notificar=notificar)


def arrancar(motor, espejo=ESPEJO_MIN):
    job = motor.crear_job(deepcopy(espejo))
    salida = {}
    def ejecutar():
        try:
            salida["job"] = motor.correr(job.job_id)
        except Exception as ex:
            salida["error"] = ex
    hilo = Thread(target=ejecutar)
    hilo.start()
    return job.job_id, hilo, salida


def test_checkpoint_parcial_persiste_sunat_mientras_infoobras_esta_bloqueada(tmp_path):
    registro, sunat_guardada, liberar_info = [], Event(), Event()
    def notificar(progreso):
        if progreso.etapa_actual == Etapa.SUNAT:
            sunat_guardada.set()
    def escritura_en_curso(ctx):
        ctx.enriquecimiento.setdefault("1:1", {})["info_en_curso"] = True
    info = FuenteFake(Etapa.INFOOBRAS, registro, liberar=liberar_info,
                      delta={"1:1": {"infoobras": "ok"}}, accion=escritura_en_curso)
    sunat = FuenteFake(Etapa.SUNAT, registro,
                       delta={"1:1": {"sunat": "ok"}})
    motor = motor_paralelo(tmp_path, registro, info=info, sunat=sunat, notificar=notificar)
    jid, hilo, salida = arrancar(motor)
    try:
        assert sunat_guardada.wait(timeout=10)
        parcial = motor._repo.cargar_enriquecimiento(jid)
        job = motor._repo.cargar(jid)
        assert parcial["1:1"]["sunat"] == "ok"
        assert "infoobras" not in parcial.get("1:1", {})
        assert "info_en_curso" not in parcial.get("1:1", {})
        assert job.etapa(Etapa.SUNAT).estado == EstadoEtapa.OK
        assert job.etapa(Etapa.INFOOBRAS) is None
        assert not any(x == (Etapa.REGLAS, None) for x in registro)
    finally:
        liberar_info.set()
        hilo.join(timeout=10)
    assert not hilo.is_alive() and "error" not in salida
    assert salida["job"].estado == JobEstado.COMPLETADO
    assert [r.etapa for r in salida["job"].etapas] == Etapa.orden()


def test_fusiona_deltas_de_fuentes_y_conserva_revision_previa(tmp_path):
    registro, repo = [], RepositorioArchivos(tmp_path)
    def resolver_previa(ctx):
        ctx.job.items_revision[0].resuelto = True
        ctx.job.items_revision[0].motivo = "resuelta por la fuente"
    info = FuenteFake(Etapa.INFOOBRAS, registro, delta={"1:1": {"infoobras": "ok"}},
                      revisiones=[(1, 1)], accion=resolver_previa)
    sunat = FuenteFake(Etapa.SUNAT, registro, delta={"1:1": {"sunat": "ok"}})
    reni = FuenteFake(Etapa.RENIPRESS, registro, delta={"1:1": {"renipress": "ok"}})
    motor = motor_paralelo(tmp_path, registro, info=info, sunat=sunat, renipress=reni)
    job = motor.crear_job(ESPEJO_MIN)
    job.items_revision.append(ItemRevision(
        n_prof=1, n_exp=2, etapa=Etapa.RESOLUCION_CUI,
        motivo="revisión previa", accion_sugerida="pegar CUI"))
    repo.guardar(job)
    repo.guardar_enriquecimiento(job.job_id, {"1:1": {"cui": "123", "previo": True}})
    job = motor.correr(job.job_id)
    datos = repo.cargar_enriquecimiento(job.job_id)["1:1"]
    assert datos == {"cui": "123", "previo": True, "infoobras": "ok", "sunat": "ok", "renipress": "ok"}
    guardado = repo.cargar(job.job_id)
    assert {(x.n_prof, x.n_exp) for x in guardado.items_revision} == {(1, 1), (1, 2)}
    assert guardado.items_revision[0].resuelto is True
    assert guardado.items_revision[0].motivo == "resuelta por la fuente"


def test_error_de_fuente_conserva_hermanas_y_no_entra_a_reglas(tmp_path):
    registro, sunat_lista = [], Event()
    reglas = EtapaFake(Etapa.REGLAS, registro)
    info = FuenteFake(Etapa.INFOOBRAS, registro, listo=Event(),
                      delta={"1:1": {"info_parcial": True}},
                      error=ErrorEstructural("InfoObras caído"))
    sunat = FuenteFake(Etapa.SUNAT, registro, listo=sunat_lista,
                       delta={"1:1": {"sunat": "ok"}})
    motor = motor_paralelo(tmp_path, registro, info=info, sunat=sunat, reglas=reglas)
    jid, hilo, salida = arrancar(motor)
    hilo.join(timeout=5)
    assert not hilo.is_alive() and salida["job"].estado == JobEstado.ERROR
    datos = motor._repo.cargar_enriquecimiento(jid).get("1:1", {})
    assert datos.get("sunat") == "ok"
    assert "info_parcial" not in datos
    assert Etapa.REGLAS not in registro


def test_reanudacion_desde_checkpoint_de_sunat_no_la_repite(tmp_path):
    registro, guardada, liberar = [], Event(), Event()
    def interrumpir(progreso):
        if progreso.etapa_actual == Etapa.SUNAT:
            guardada.set()
            raise RuntimeError("interrupción tras checkpoint")
    info = FuenteFake(Etapa.INFOOBRAS, registro, liberar=liberar)
    reni = FuenteFake(Etapa.RENIPRESS, registro, liberar=liberar)
    sunat = FuenteFake(Etapa.SUNAT, registro, delta={"1:1": {"sunat": "ok"}})
    motor1 = motor_paralelo(tmp_path, registro, info=info, sunat=sunat,
                            renipress=reni, notificar=interrumpir)
    jid, hilo, salida = arrancar(motor1)
    try:
        assert guardada.wait(timeout=10)
        assert motor1._repo.cargar(jid).etapa(Etapa.SUNAT).estado == EstadoEtapa.OK
    finally:
        liberar.set()
        hilo.join(timeout=10)
    assert not hilo.is_alive() and "interrupción tras checkpoint" in str(salida["error"])
    assert motor1._repo.cargar_enriquecimiento(jid)["1:1"]["sunat"] == "ok"
    registro.clear()
    motor2 = motor_paralelo(tmp_path, registro)
    job2 = motor2.correr(jid)
    assert job2.estado == JobEstado.COMPLETADO
    assert Etapa.SUNAT not in registro
    assert {Etapa.INFOOBRAS, Etapa.RENIPRESS}.issubset(registro)
    assert motor2._repo.cargar_enriquecimiento(jid)["1:1"]["sunat"] == "ok"


def test_conflicto_de_misma_hoja_es_error_y_no_pisa_silenciosamente(tmp_path):
    registro = []
    info = FuenteFake(Etapa.INFOOBRAS, registro, delta={"1:1": {"hoja": "info"}})
    sunat = FuenteFake(Etapa.SUNAT, registro, delta={"1:1": {"hoja": "sunat"}})
    motor = motor_paralelo(tmp_path, registro, info=info, sunat=sunat)
    job = motor.correr(motor.crear_job(ESPEJO_MIN).job_id)
    assert job.estado == JobEstado.ERROR
    assert job.etapa(Etapa.REGLAS) is None
    assert job.etapa(Etapa.EXCEL) is None
    assert motor._repo.cargar_enriquecimiento(job.job_id).get("1:1", {}).get("hoja") in {"info", "sunat"}
    antes = motor._repo.cargar_enriquecimiento(job.job_id)
    registro.clear()
    repetido = motor.correr(job.job_id)
    assert repetido.estado == JobEstado.ERROR and registro == []
    assert motor._repo.cargar_enriquecimiento(job.job_id) == antes


@pytest.mark.parametrize("fallo", ["datos", "checkpoint"])
def test_fallo_al_guardar_nunca_deja_ok_sin_datos_y_reintenta(tmp_path, fallo):
    class DiscoInterrumpido(RepositorioArchivos):
        fallar = True

        def guardar_enriquecimiento(self, jid, datos):
            if self.fallar and fallo == "datos" and datos.get("1:1", {}).get("sunat"):
                raise OSError("disco interrumpido")
            return super().guardar_enriquecimiento(jid, datos)

        def guardar(self, job):
            if self.fallar and fallo == "checkpoint" and job.etapa(Etapa.SUNAT):
                raise OSError("disco interrumpido")
            return super().guardar(job)

    registro = []
    repo = DiscoInterrumpido(tmp_path)
    sunat = FuenteFake(Etapa.SUNAT, registro, delta={"1:1": {"sunat": "ok"}})
    motor = motor_paralelo(tmp_path, registro, sunat=sunat)
    motor._repo = repo
    jid = motor.crear_job(deepcopy(ESPEJO_MIN)).job_id
    with pytest.raises(OSError, match="disco interrumpido"):
        motor.correr(jid)
    assert repo.cargar(jid).etapa(Etapa.SUNAT) is None
    if fallo == "checkpoint":
        assert repo.cargar_enriquecimiento(jid)["1:1"]["sunat"] == "ok"
    repo.fallar = False
    registro.clear()
    job = motor.correr(jid)
    assert job.estado == JobEstado.COMPLETADO
    assert Etapa.SUNAT in registro
    assert repo.cargar_enriquecimiento(jid)["1:1"]["sunat"] == "ok"
