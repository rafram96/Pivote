"""
Dos defectos vistos en la corrida real del 5-sep (Panel con puntaje «—» y
3/12 CUMPLEN), ambos silenciosos:

1. El consolidador emite el factor como "A — Experiencia específica…" (#88) y el
   backend lo buscaba con `== "A"` literal: el Factor A nunca se recalculaba,
   quedaba `puntaje=None` y el total salía condicionado para siempre.
2. Las fechas de solo mes y año ("2021-09 (Setiembre del 2021)") se contaban en
   el recálculo (mes completo autorizado por las bases) pero `reconciliar_…`,
   que alimenta `/resumen`, el Panel y el Excel, solo leía ISO completo: la
   experiencia desaparecía del cómputo y un profesional con 758 días acreditables
   mostraba 439 (bajo el mínimo de 720).
"""
from __future__ import annotations

from datetime import date

import pytest

from orquestador.etapas_reales import (
    _letra_factor, _participantes_factor_a, _recalcular_factor_a,
)
from validacion.puntajes import reconciliar_puntajes
from validacion.recalculo import fechas_calculo, regla_periodos_de


# ── letra del factor ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("etiqueta,esperado", [
    ("A", "A"), ("a", "A"), ("Factor A", "A"), ("A — Experiencia específica", "A"),
    ("B - Sostenibilidad ambiental", "B"), ("C: Integridad", "C"), ("E) BEP", "E"),
    ("Certificaciones del personal clave (PMP / PMI-CP)", ""), ("", ""), (None, ""),
])
def test_letra_factor(etiqueta, esperado):
    assert _letra_factor({"factor": etiqueta}) == esperado


def _espejo_factor_a(etiqueta: str):
    return {
        "reglas_evaluacion": {"factor_a": {"dias_adicionales_requeridos": 365, "tramos": [
            {"desde_porcentaje": 50, "desde_inclusivo": True, "hasta_porcentaje": 100,
             "hasta_inclusivo": True, "puntaje": 60},
            {"desde_porcentaje": 0, "desde_inclusivo": False, "hasta_porcentaje": 50,
             "hasta_inclusivo": False, "puntaje": 30},
            {"desde_porcentaje": 0, "desde_inclusivo": True, "hasta_porcentaje": 0,
             "hasta_inclusivo": True, "puntaje": 0}]}},
        "profesionales": [{"n_prof": 1, "requisitos": {"factor_a_aplica": True}},
                          {"n_prof": 2, "requisitos": {"factor_a_aplica": True}}],
        "resumen_evaluacion": {"factores": [
            {"factor": etiqueta, "puntaje": None, "estado_puntaje": "condicionado",
             "puntaje_maximo_posible": 60}]},
    }, {"prof:1": {"minimo_dias": 1440, "dias_efectivos": 2387},
        "prof:2": {"minimo_dias": 1080, "dias_efectivos": 1682}}


def test_factor_a_con_nombre_completo_se_recalcula_como_el_de_letra_sola():
    esperado = None
    for etiqueta in ("A", "A — Experiencia específica adicional del personal clave"):
        espejo, enr = _espejo_factor_a(etiqueta)
        _recalcular_factor_a(espejo, enr)
        reconciliar_puntajes(espejo)
        f = espejo["resumen_evaluacion"]["factores"][0]
        assert f["puntaje"] == 60, (etiqueta, f)
        assert f["estado_puntaje"] == "definitivo"
        assert espejo["resumen_evaluacion"]["puntaje_total"] == 60
        esperado = esperado or f["puntaje"]


def test_participantes_legado_tambien_reconoce_el_nombre_completo():
    espejo = {"profesionales": [{"n_prof": 2}, {"n_prof": 3}],
              "resumen_evaluacion": {"factores": [
                  {"factor": "A — Experiencia adicional",
                   "detalle": "Factor A (nº 2 Gestor BIM, 3 Coordinador BIM) 100%"}]}}
    assert _participantes_factor_a(espejo) == {2, 3}


# ── fechas de solo mes y año ─────────────────────────────────────────────────

EXP_MES = {"n": 2, "proyecto": "Elaboración del Expediente Técnico de obra: CLINICA X",
           "fecha_inicial": "2021-09 (Setiembre del 2021)",
           "fecha_final": "2022-11 (noviembre del 2022)"}


def test_fechas_calculo_usa_mes_completo_si_lo_dicen_las_bases():
    ini, fin, deducida = fechas_calculo(dict(EXP_MES), "mes_completo")
    assert (ini, fin, deducida) == (date(2021, 9, 1), date(2022, 11, 30), True)


def test_fechas_calculo_no_adivina_sin_regla():
    ini, fin, deducida = fechas_calculo(dict(EXP_MES), "no_definida")
    assert (ini, fin, deducida) == (None, None, False)


def test_fechas_calculo_prefiere_lo_que_dejo_el_recalculo():
    exp = {**EXP_MES, "_backend": {"fecha_inicial_calculo": "2021-09-01",
                                   "fecha_final_calculo": "2022-11-30",
                                   "fechas_deducidas": True}}
    assert fechas_calculo(exp, "no_definida") == (date(2021, 9, 1), date(2022, 11, 30), True)


def test_regla_periodos_de_lee_las_bases():
    assert regla_periodos_de({"reglas_evaluacion": {"periodos_sin_dia": "mes_completo"}}) == "mes_completo"
    assert regla_periodos_de({}) == "no_definida"
    assert regla_periodos_de(None) == "no_definida"


def _espejo_prof5(regla: str):
    # Caso real (anonimizado): 439 días ISO + 15 meses solo con mes/año.
    return {
        "reglas_evaluacion": {"periodos_sin_dia": regla},
        "profesionales": [{"n_prof": 5, "nombre": "P", "cargo": "ESP",
                           "requisitos": {"tiempo_minimo_experiencia": "24 meses"},
                           "experiencias": [
                               {"n": 1, "proyecto": "Expediente A",
                                "fecha_inicial": "2020-11-02", "fecha_final": "2022-01-14"},
                               dict(EXP_MES)]}],
    }


def test_reconciliar_cuenta_el_mes_completo_cuando_las_bases_lo_autorizan():
    from entregables.excel_final import reconciliar_resultados_profesionales
    con = reconciliar_resultados_profesionales(_espejo_prof5("mes_completo"), {})[5]
    sin = reconciliar_resultados_profesionales(_espejo_prof5("no_definida"), {})[5]
    # con la regla: 2020-11-02 → 2022-11-30 continuo (solape contado una vez)
    assert con["dias_efectivos"] > 700, con
    assert 2 not in (con.get("veredicto_provisional") or [])
    assert "NO CUMPLE" not in str(con.get("cumple_backend") or "")
    # sin la regla: solo la experiencia ISO cuenta y la parcial queda marcada
    assert sin["dias_efectivos"] == 439, sin
    assert 2 in sin["veredicto_provisional"]
    assert "sin leer" in sin["cumple_backend"]


def test_total_condicionado_publica_rango_aunque_un_factor_no_traiga_confirmado():
    # Caso real: el Factor E (valoración del Comité, 0–25) llega con
    # puntaje_confirmado=None y sin puntaje. Su piso es 0, no «sin cota»:
    # el evaluador debe ver «entre 60 y 100», no «al menos 60, con factores sin cota».
    espejo = {"resumen_evaluacion": {"factores": [
        {"factor": "A — Experiencia", "puntaje": 60, "estado_puntaje": "definitivo",
         "puntaje_confirmado": 60, "puntaje_maximo_posible": 60},
        {"factor": "B — ISO", "puntaje": None, "estado_puntaje": "condicionado",
         "puntaje_confirmado": 0, "puntaje_maximo_posible": 5},
        {"factor": "E — BEP", "puntaje": None, "estado_puntaje": "condicionado",
         "puntaje_confirmado": None, "puntaje_maximo_posible": 35},
        {"factor": "PMP", "aplica": False, "puntaje": "NO APLICA"},
    ]}}
    r = reconciliar_puntajes(espejo)
    assert r["puntaje_total"] is None
    assert r["puntaje_confirmado"] == 60
    assert r["puntaje_maximo_posible"] == 100
    assert "entre 60 y 100" in r["nota"]


# ── /resumen expone el estado condicionado ───────────────────────────────────

@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app)


def test_resumen_expone_rango_y_estado_de_cada_factor(cliente):
    import io
    import json
    from tests.test_tipo_evaluacion import ESPEJO_MIN
    espejo = json.loads(json.dumps(ESPEJO_MIN))
    espejo["resumen_evaluacion"] = {
        "puntaje_total": None, "puntaje_confirmado": 15, "puntaje_maximo_posible": 100,
        "estado_puntaje": "condicionado", "nota": "Puntaje técnico condicionado: entre 15 y 100 puntos.",
        "factores": [
            {"factor": "A — Experiencia adicional", "aplica": True, "puntaje": None,
             "estado_puntaje": "condicionado", "puntaje_confirmado": 0,
             "puntaje_maximo_posible": 60, "detalle": "x"},
            {"factor": "Certificaciones (PMP)", "aplica": False,
             "puntaje": "NO APLICA — no figura", "detalle": "y"},
        ]}
    cid = cliente.post("/api/pivote/concursos",
                       json={"nomenclatura": "CP-R/2026", "entidad": "E"}).json()["concurso_id"]
    r = cliente.post("/api/pivote/analizar", data={"concurso_id": cid}, files={
        "espejo": ("espejo.json", io.BytesIO(json.dumps(espejo).encode("utf-8")), "application/json"),
        "excel": ("claude.xlsx", io.BytesIO(b"PK demo"), "application/octet-stream"),
    })
    assert r.status_code == 201, r.text
    res = cliente.get(f"/api/pivote/jobs/{r.json()['job_id']}/resumen").json()
    assert res["estado_puntaje"] == "condicionado"
    assert res["puntaje_confirmado"] == 15 and res["puntaje_maximo_posible"] == 100
    assert "entre 15 y 100" in res["nota_puntaje"]
    fa = res["factores"][0]
    assert fa["aplica"] is True and fa["estado_puntaje"] == "condicionado"
    assert fa["puntaje_confirmado"] == 0 and fa["puntaje_maximo_posible"] == 60
    assert res["factores"][1]["aplica"] is False
