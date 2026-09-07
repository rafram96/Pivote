"""Instrumentación de la etapa infoobras: tiempos por experiencia/fuente, caché MEF
por corrida y resumen TIEMPOS en el job. Todo offline, con fakes inyectados."""
from __future__ import annotations

from orquestador import Motor, RepositorioMemoria, etapas_esqueleto
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal, _acepta_parametro
from schemas import pipeline

EXP = {"proyecto": "Elaboración del Expediente Técnico: MEJORAMIENTO DEL C.S. X",
       "entidad_emisora": "CONSORCIO CONSULTOR PARACAS", "fecha_inicial": "2021-01-01",
       "fecha_final": "2021-12-31"}


def _ctx(enr: dict, tipo="expedientes"):
    espejo = {"_meta": {"analisis_id": "v-001", "concurso": "c", "postor": "p", "tipo_evaluacion": tipo},
              "postor": {},
              "profesionales": [{"n_prof": 1, "cargo": "ESP", "nombre": "N",
                                 "experiencias": [{"n": 1, "folio": "1", **EXP},
                                                  {"n": 2, "folio": "2", **EXP}]}],
              "resumen_evaluacion": {"factores": []}}
    job = Motor(etapas_esqueleto(), RepositorioMemoria()).crear_job(espejo)
    return Contexto(job=job, espejo=espejo,
                    enriquecimiento={"1:1": dict(enr), "1:2": dict(enr)})


def _enr_nombre(cui="2425571"):
    return {"via": "NOMBRE", "cui": cui,
            "obra": {"cui": cui, "nombre_obra": "MEJORAMIENTO DEL C.S. X", "departamento": "ICA"}}


def test_acepta_parametro_detecta_cache_y_kwargs():
    assert _acepta_parametro(lambda exp, cui, codsnip="", cache=None: None, "cache")
    assert _acepta_parametro(lambda exp, cui, codsnip="", **kw: None, "cache")
    assert not _acepta_parametro(lambda exp, cui, codsnip="": None, "cache")
    assert not _acepta_parametro(None, "cache")


def test_etapa_persiste_tiempos_y_resume_en_observacion():
    recibidos = []

    def verificador(exp, cui, codsnip="", cache=None):
        recibidos.append(cache)
        return {"verificado_en_mef": True, "cui_confirmado": cui,
                "contrato": {"numero": "001-2021", "fecha": "2021-01-05"}}

    etapa = EtapaInfoObrasReal(fetcher=lambda *a: None, verificador_mef=verificador,
                               consulta_ocds=lambda cui: [])
    ctx = _ctx(_enr_nombre())
    res = etapa.correr(ctx)

    # Sin InfoObras (fetcher → None) el expediente se verifica solo contra el MEF
    assert ctx.enriquecimiento["1:1"]["verificacion_expediente"]["verificado_en_mef"]
    # la MISMA caché MEF (una por corrida) llegó a cada verificación
    assert len(recibidos) == 2 and recibidos[0] is recibidos[1] is not None
    assert type(recibidos[0]).__name__ == "CacheMef"
    # tiempos por experiencia, con las fuentes que se tocaron
    t = ctx.enriquecimiento["1:1"]["tiempos_s"]
    assert set(t) >= {"total", "infoobras", "mef", "seace"}
    assert all(isinstance(v, float) and v >= 0 for v in t.values())
    # y el resumen de la etapa como observación INFO del job
    tiempos = [o for o in res.observaciones if o.codigo == "TIEMPOS"]
    assert len(tiempos) == 1 and tiempos[0].severidad == pipeline.Severidad.INFO
    m = tiempos[0].mensaje
    assert "fases:" in m and "bucle" in m and "segunda_pasada" in m and "seace" in m
    assert "fuentes:" in m and "mef" in m and "caché MEF:" in m


def test_verificador_sin_parametro_cache_sigue_funcionando():
    llamadas = []

    def verificador(exp, cui, codsnip=""):
        llamadas.append(cui)
        return {"verificado_en_mef": True, "cui_confirmado": cui}

    etapa = EtapaInfoObrasReal(fetcher=lambda *a: None, verificador_mef=verificador,
                               consulta_ocds=lambda cui: [])
    ctx = _ctx(_enr_nombre())
    etapa.correr(ctx)
    assert llamadas == ["2425571", "2425571"]
    assert etapa._cache_mef is None


def test_sin_verificador_no_hay_cache_ni_error():
    etapa = EtapaInfoObrasReal(fetcher=lambda *a: None, consulta_ocds=lambda cui: [])
    ctx = _ctx(_enr_nombre())
    res = etapa.correr(ctx)
    assert etapa._cache_mef is None
    assert any(o.codigo == "TIEMPOS" for o in res.observaciones)
