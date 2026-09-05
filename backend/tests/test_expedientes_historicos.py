from copy import deepcopy
import importlib
import io
import json

import pytest

from entregables.expedientes import (
    motivo_periodo_no_computable,
    reconciliar_expedientes,
)


def _espejo(experiencias, requisito="Experiencia mínima: 1 año", regla="no_definida"):
    return {
        "reglas_evaluacion": {"periodos_sin_dia": regla},
        "profesionales": [{
            "n_prof": 1,
            "requisitos": {"experiencia": requisito} if requisito else None,
            "experiencias": experiencias,
        }],
    }


def _exp(n, inicio="2020-01-01", fin="2020-12-31"):
    return {"n": n, "proyecto": f"Expediente {n}",
            "fecha_inicial": inicio, "fecha_final": fin}


@pytest.mark.parametrize(
    ("sub_obras", "esperado"),
    [
        ([{"estado": "pendiente"}, {"estado": "pendiente"}], True),
        ([{"estado": "resuelto"}, {"estado": "pendiente"}], True),
        ([{"estado": "resuelto"}, {"estado": "resuelto"}], False),
    ],
    ids=["historico-0-de-N", "historico-parcial", "historico-completo"],
)
def test_multiobra_historica_deriva_pendiente_sin_flags(sub_obras, esperado):
    resultado = reconciliar_expedientes(_espejo([_exp(1)]), {
        "1:1": {"via": "MULTI_OBRA", "sub_obras": sub_obras},
    })[1]
    assert bool(resultado.get("veredicto_provisional")) is esperado
    if esperado:
        assert ("sub-obras pendientes" in resultado["cumple_backend"]
                or "identificación del expediente pendiente" in resultado["cumple_backend"])


@pytest.mark.parametrize("via", ["PRIVADA", "NA"])
def test_privada_y_na_solo_quedan_pendientes_si_sunat_no_identifica_emisor(via):
    espejo = _espejo([_exp(1)])
    identificada = reconciliar_expedientes(espejo, {
        "1:1": {"via": via, "sunat": {"ruc": "20123456789"}},
    })[1]
    pendiente = reconciliar_expedientes(espejo, {"1:1": {"via": via}})[1]
    assert "veredicto_provisional" not in identificada
    assert pendiente["veredicto_provisional"] == [1]
    assert "SUNAT" in pendiente["cumple_backend"]


@pytest.mark.parametrize(
    ("inicio", "fin", "motivo"),
    [
        (None, None, "faltan las fechas inicial y final"),
        (None, "2020-01-31", "falta la fecha inicial"),
        ("2020-01-01", None, "falta la fecha final"),
        ("2020-02-01", "2020-01-01", "anterior"),
        ("2020-02-30", "2020-03-01", "no es legible"),
    ],
)
def test_periodos_ausentes_invertidos_o_imposibles_se_excluyen(inicio, fin, motivo):
    exp = _exp(7, inicio, fin)
    assert motivo in motivo_periodo_no_computable(exp, "no_definida")
    resultado = reconciliar_expedientes(_espejo([exp]), {
        "1:7": {"via": "NOMBRE", "cui": "123"},
        "prof:1": {"dias_efectivos": 999, "cumple_backend": "CUMPLE viejo"},
    })[1]
    assert resultado["dias_efectivos"] == 0
    assert resultado["experiencias_excluidas"][0]["n"] == 7
    assert motivo in resultado["experiencias_excluidas"][0]["motivo"]
    assert resultado["cumple_backend"].startswith("POR VERIFICAR")


def test_mes_solo_se_computa_con_regla_mes_completo():
    exp = _exp(1, "2020-02 (sin día)", "2020-02 (sin día)")
    sin_regla = reconciliar_expedientes(_espejo([exp]), {"1:1": {"via": "NOMBRE", "cui": "1"}})[1]
    con_regla = reconciliar_expedientes(
        _espejo([exp], regla="mes_completo"), {"1:1": {"via": "NOMBRE", "cui": "1"}},
    )[1]
    assert sin_regla["dias_efectivos"] == 0
    assert sin_regla["experiencias_excluidas"]
    assert con_regla["dias_efectivos"] == 29
    assert con_regla["experiencias_excluidas"] == []


def test_minimo_se_compara_y_sin_minimo_se_abstiene():
    enr = {"1:1": {"via": "NOMBRE", "cui": "1"}}
    bajo = reconciliar_expedientes(_espejo([_exp(1)], "Experiencia mínima: 2 años"), enr)[1]
    alcanza = reconciliar_expedientes(_espejo([_exp(1)]), enr)[1]
    sin_minimo = reconciliar_expedientes(_espejo([_exp(1)], None), enr)[1]
    assert bajo["cumple_backend"].startswith("NO CUMPLE")
    assert alcanza["cumple_backend"].startswith("CUMPLE")
    assert sin_minimo["cumple_backend"].startswith("POR VERIFICAR")
    assert "minimo_dias" not in sin_minimo


def test_inferido_no_es_provisional_por_su_solo_color_y_no_resta_paralizaciones():
    resultado = reconciliar_expedientes(_espejo([_exp(1)]), {
        "1:1": {"via": "NOMBRE", "cui": "123",
                "paralizaciones": [{"inicio": "2020-01-01", "fin": "2020-12-31"}]},
    })[1]
    assert resultado["dias_efectivos"] == 366
    assert resultado["dias_paralizados"] == 0
    assert "veredicto_provisional" not in resultado


def test_flags_explicitos_publicos_no_se_pierden_aunque_haya_cui():
    espejo = _espejo([_exp(1)])
    sin_verificar = reconciliar_expedientes(espejo, {
        "1:1": {"via": "CUI_TEXTO", "cui": "123", "sin_verificar": True},
    })[1]
    multi_incompleta = reconciliar_expedientes(espejo, {
        "1:1": {"via": "MULTI_OBRA", "identificacion_incompleta": True,
                "sub_obras": [{"estado": "resuelto"}]},
    })[1]
    assert sin_verificar["cumple_backend"].startswith("POR VERIFICAR")
    assert "identificación del expediente pendiente" in sin_verificar["cumple_backend"]
    assert multi_incompleta["cumple_backend"].startswith("POR VERIFICAR")
    assert "sub-obras pendientes" in multi_incompleta["cumple_backend"]


def test_preserva_campos_ajenos_limpia_derivados_y_no_muta_entradas():
    espejo = _espejo([_exp(1, None, None)])
    enriquecimiento = {
        "1:1": {"via": "NOMBRE", "cui": "123"},
        "prof:1": {"observacion": "conservar", "dias_efectivos": 999,
                   "minimo_dias": 1, "cumple_backend": "CUMPLE viejo"},
    }
    antes_espejo, antes_enr = deepcopy(espejo), deepcopy(enriquecimiento)
    resultado = reconciliar_expedientes(espejo, enriquecimiento)[1]
    assert resultado["observacion"] == "conservar"
    assert resultado["dias_efectivos"] == 0
    assert resultado["minimo_dias"] == 365
    assert resultado["cumple_backend"].startswith("POR VERIFICAR")
    assert espejo == antes_espejo
    assert enriquecimiento == antes_enr


def test_sin_experiencias_no_recupera_cumple_historico():
    espejo = _espejo([])
    resultado = reconciliar_expedientes(espejo, {
        "prof:1": {"cumple_backend": "CUMPLE viejo", "dias_efectivos": 800},
    })[1]
    assert resultado["dias_efectivos"] == 0
    assert resultado["cumple_backend"].startswith("POR VERIFICAR")


@pytest.fixture()
def cliente_api(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app), modulo


def _crear_job(cliente_api, experiencias, enriquecimiento):
    api, modulo = cliente_api
    espejo = _espejo(experiencias)
    espejo.update({
        "_meta": {"analisis_id": "historico-sintetico",
                  "concurso": "CP-SINTETICO/2026", "postor": "POSTOR SINTETICO",
                  "tipo_evaluacion": "expedientes"},
        "postor": {},
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    })
    profesional = espejo["profesionales"][0]
    profesional.update({"cargo": "ESPECIALISTA", "nombre": "Persona Sintética",
                        "cumple": "CUMPLE histórico"})
    concurso = api.post("/api/pivote/concursos", json={
        "nomenclatura": "CP-SINTETICO/2026", "entidad": "Entidad Sintética",
    })
    assert concurso.status_code == 201, concurso.text
    creado = api.post(
        "/api/pivote/analizar",
        data={"concurso_id": concurso.json()["concurso_id"]},
        files={
            "espejo": ("espejo.json", io.BytesIO(json.dumps(espejo).encode()),
                        "application/json"),
            "excel": ("claude.xlsx", io.BytesIO(b"PK sintetico"),
                      "application/octet-stream"),
        },
    )
    assert creado.status_code == 201, creado.text
    job_id = creado.json()["job_id"]
    modulo.repo.guardar_enriquecimiento(job_id, {
        **enriquecimiento,
        "prof:1": {"dias_efectivos": 9999, "cumple_backend": "CUMPLE antiguo"},
    })
    return api, job_id


def _estados_api(api, job_id):
    espejo = api.get(f"/api/pivote/jobs/{job_id}/espejo")
    resumen = api.get(f"/api/pivote/jobs/{job_id}/resumen")
    assert espejo.status_code == resumen.status_code == 200
    profesional = espejo.json()["profesionales"][0]
    veredicto = resumen.json()["veredictos"][0]
    return profesional, veredicto


def test_api_historico_sin_fechas_coincide_en_espejo_y_resumen(cliente_api):
    api, job_id = _crear_job(
        cliente_api, [_exp(1, None, None)], {"1:1": {"via": "NOMBRE", "cui": "1"}},
    )
    profesional, veredicto = _estados_api(api, job_id)
    assert profesional["total_efectivo"]["dias"] == 0
    assert veredicto["anios_efectivos"] == 0
    assert profesional["estado_efectivo"] == veredicto["estado_efectivo"] == "por_confirmar"
    assert profesional["veredicto_efectivo"].startswith("POR VERIFICAR")
    assert veredicto["veredicto_efectivo"].startswith("POR VERIFICAR")


def test_api_historico_multiobra_cero_de_n_coincide_en_espejo_y_resumen(cliente_api):
    api, job_id = _crear_job(cliente_api, [_exp(1)], {
        "1:1": {"via": "MULTI_OBRA", "sub_obras": [
            {"estado": "sin_resolver"}, {"estado": "sin_resolver"},
        ]},
    })
    profesional, veredicto = _estados_api(api, job_id)
    assert profesional["total_efectivo"]["dias"] == 366
    assert veredicto["anios_efectivos"] == 1.0
    assert profesional["estado_efectivo"] == veredicto["estado_efectivo"] == "por_confirmar"
    assert profesional["veredicto_efectivo"].startswith("POR VERIFICAR")
    assert veredicto["veredicto_efectivo"].startswith("POR VERIFICAR")
