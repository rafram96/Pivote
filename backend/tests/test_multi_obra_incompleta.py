"""
Certificados MULTI-OBRA cuya identificación quedó INCOMPLETA (5-sep-2026).

El certificado multi-obra documenta un vínculo con N obras y su «identificador»
es el portafolio, no un CUI único: por eso nunca iba a «Por confirmar». Pero con
0 de N obras halladas no hay NADA verificado, y la experiencia se entregaba en
silencio como si lo estuviera (casos reales 9:1 y 12:4).

  · 0 de N → marca `identificacion_incompleta` + un ItemRevision para la experiencia.
  · k de N (0 < k < N) → solo la marca: algo SÍ se verificó y el respaldo del
    vínculo es el propio certificado (ADR-011).

Datos ficticios.
"""
from __future__ import annotations

from orquestador import Motor, RepositorioMemoria, etapas_esqueleto
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaResolucionCuiReal
from schemas import pipeline


class _PorCodigo:
    """Consulta InfoObras falsa: responde por código según un mapa CUI → registros."""

    def __init__(self, por_cui: dict):
        self.por_cui = por_cui

    def por_codigo(self, codigo):
        return list(self.por_cui.get(str(codigo), []))

    def buscar(self, nombre):
        return []


def _registro(cui, obra_id, nombre, depto="CUSCO"):
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


OBRA_A = "MEJORAMIENTO DEL SERVICIO DE AGUA POTABLE EN EL CENTRO POBLADO SANTA ROSA ALTA"
OBRA_B = "MEJORAMIENTO DEL SERVICIO DE AGUA POTABLE EN EL CENTRO POBLADO SAN MARTIN BAJO"


def _ctx_multi_obra():
    espejo = {
        "_meta": {"analisis_id": "mo-001", "concurso": "CP-MO", "postor": "Postor Ficticio",
                  "tipo_evaluacion": "obras"},
        "postor": {},
        "profesionales": [{
            "n_prof": 3, "cargo": "RESIDENTE", "nombre": "Ingeniera Ficticia Uno",
            "experiencias": [{
                "n": 4, "folio": "77",
                "proyecto": "Supervisión de obras de saneamiento del paquete rural",
                "entidad_emisora": "MUNICIPALIDAD DISTRITAL FICTICIA",
                "ubicacion": "Cusco", "fecha_inicial": "2021-01-04", "fecha_final": "2022-06-30",
                "obras": [{"cui": "2911001", "proyecto": OBRA_A},
                          {"cui": "2911002", "proyecto": OBRA_B}],
            }],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    motor = Motor(etapas_esqueleto(), RepositorioMemoria())
    return Contexto(job=motor.crear_job(espejo), espejo=espejo, enriquecimiento={})


def _correr(por_cui: dict) -> Contexto:
    ctx = _ctx_multi_obra()
    EtapaResolucionCuiReal(consulta=_PorCodigo(por_cui)).correr(ctx)
    return ctx


def test_multi_obra_sin_ninguna_obra_identificada_va_a_revision():
    ctx = _correr({})                       # ninguno de los dos códigos existe
    enr = ctx.enriquecimiento["3:4"]
    assert enr["via"] == "MULTI_OBRA"
    assert enr["identificacion_incompleta"] is True
    assert all(s["estado"] != "resuelto" for s in enr["sub_obras"])

    items = [it for it in ctx.job.items_revision if not it.resuelto]
    assert len(items) == 1, items
    it = items[0]
    assert (it.n_prof, it.n_exp) == (3, 4)
    assert it.etapa == pipeline.Etapa.RESOLUCION_CUI
    assert "ninguna de las 2 obras" in it.motivo and "confirmar cada una" in it.motivo
    assert it.profesional == "Ingeniera Ficticia Uno" and it.cargo == "RESIDENTE"
    assert len(it.candidatos) <= 3


def test_multi_obra_con_una_de_dos_identificadas_solo_deja_la_marca():
    ctx = _correr({"2911001": [_registro("2911001", 901, OBRA_A)]})
    enr = ctx.enriquecimiento["3:4"]
    assert enr["identificacion_incompleta"] is True
    assert sum(1 for s in enr["sub_obras"] if s["estado"] == "resuelto") == 1
    assert [it for it in ctx.job.items_revision if not it.resuelto] == []


def test_multi_obra_completa_no_marca_ni_revisa():
    ctx = _correr({"2911001": [_registro("2911001", 901, OBRA_A)],
                   "2911002": [_registro("2911002", 902, OBRA_B)]})
    enr = ctx.enriquecimiento["3:4"]
    assert "identificacion_incompleta" not in enr
    assert [it for it in ctx.job.items_revision if not it.resuelto] == []
