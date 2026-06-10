"""
Tests del validador (notas puras) — unitarios sintéticos por nota +
calibración fijada contra los espejos reales (fixtures locales, gitignored;
se saltan si no están).

Hallazgos de la calibración 2026-06-10 (fijados aquí):
- Trujillo full: 0 observaciones (espejo limpio — round-trip validado).
- Libertador: 14×VEREDICTO (el extractor de fixtures nunca mapeó `cumple` —
  gap del extractor, la skill real SÍ debe emitirlo) + 2×NOTA9 reales:
  prof 9, exps 3 y 4 se solapan 2 días (3 termina 2025-02-02, 4 empieza
  2025-02-01) y nadie lo marcó en el Excel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemas.pipeline import Severidad
from validacion import verificar_espejo
from validacion.notas import (
    nota1_conteo, nota7_orden, nota9_traslapes, nota10_covid,
    puntaje_total_cuadra, totales_cuadran, veredictos_no_vacios,
)

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _exp(n, ini, fin, **extra):
    return {"n": n, "fecha_inicial": ini, "fecha_final": fin, **extra}


# ── N1 · conteo ──────────────────────────────────────────────────────────────

def test_nota1_descuadre_estructurado():
    prof = {"n_prof": 1, "experiencias": [_exp(1, "2020-01-01", "2020-06-30")],
            "cross_checks": [{"label": "NOTA 1", "valor": {"extraidas": 1, "declaradas": 3, "cuadra": False}}]}
    obs = nota1_conteo(prof)
    assert len(obs) == 2  # descuadre de conteo + cuadra=False reportado
    assert all(o.codigo == "NOTA1" for o in obs)


def test_nota1_prosa_no_verificable_no_dispara():
    prof = {"n_prof": 1, "experiencias": [],
            "cross_checks": [{"label": "NOTA 1", "valor": "OK al 2do intento: 1645 días"}]}
    assert nota1_conteo(prof) == []


# ── N7 · orden ───────────────────────────────────────────────────────────────

def test_nota7_desorden_dispara_info():
    prof = {"n_prof": 2, "experiencias": [
        _exp(1, "2020-01-01", "2021-06-30"),
        _exp(2, "2019-01-01", "2019-12-31"),   # más antigua después
    ]}
    obs = nota7_orden(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.INFO


def test_nota7_sentinels_no_rompen():
    prof = {"n_prof": 2, "experiencias": [
        _exp(1, "2020-01-01", "POR VERIFICAR (ilegible)"),
        _exp(2, "2021-01-01", "2021-12-31"),
    ]}
    assert nota7_orden(prof) == []  # solo compara fechas ISO completas


# ── N9 · traslapes ───────────────────────────────────────────────────────────

def test_nota9_traslape_real_no_marcado_es_alerta():
    prof = {"n_prof": 3, "experiencias": [
        _exp(1, "2021-01-01", "2021-06-30"),
        _exp(2, "2021-06-01", "2021-12-31"),   # solapa junio
    ]}
    obs = nota9_traslapes(prof)
    assert {o.referencia for o in obs} == {"prof=3 exp=1", "prof=3 exp=2"}
    assert all(o.severidad == Severidad.ALERTA for o in obs)


def test_nota9_marcado_correctamente_no_dispara():
    prof = {"n_prof": 3, "experiencias": [
        _exp(1, "2021-01-01", "2021-06-30", traslape="SÍ"),
        _exp(2, "2021-06-01", "2021-12-31", traslape="SÍ (con exp 1)"),
    ]}
    assert nota9_traslapes(prof) == []


def test_nota9_marcado_sin_solape_es_advertencia():
    prof = {"n_prof": 3, "experiencias": [
        _exp(1, "2020-01-01", "2020-06-30", traslape="SÍ"),
        _exp(2, "2021-01-01", "2021-12-31"),
    ]}
    obs = nota9_traslapes(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.ADVERTENCIA


# ── N10 · COVID ──────────────────────────────────────────────────────────────

def test_nota10_discrepancias():
    prof = {"n_prof": 4, "experiencias": [
        # intersecta la ventana pero dice NO → alerta
        _exp(1, "2020-01-01", "2020-04-30", incluye_covid="NO"),
        # no intersecta y dice NO → ok
        _exp(2, "2021-01-01", "2021-06-30", incluye_covid="NO"),
        # intersecta y dice SÍ → ok
        _exp(3, "2020-06-01", "2020-12-31", incluye_covid="SÍ"),
        # borde exacto: termina el día que empieza la ventana → SÍ intersecta
        _exp(4, "2020-01-01", "2020-03-16", incluye_covid="NO"),
    ]}
    obs = nota10_covid(prof)
    assert {o.referencia for o in obs} == {"prof=4 exp=1", "prof=4 exp=4"}


# ── Veredictos y totales ─────────────────────────────────────────────────────

def test_veredicto_vacio_o_no_concluyente():
    assert veredictos_no_vacios({"n_prof": 5, "cumple": None})
    assert veredictos_no_vacios({"n_prof": 5, "cumple": "— años válidos: "})
    assert veredictos_no_vacios({"n_prof": 5, "cumple": "SÍ — 5.09 años"}) == []
    assert veredictos_no_vacios({"n_prof": 5, "cumple": "NO CUMPLE (1.55)"}) == []


def test_totales_descuadrados():
    prof = {"n_prof": 6, "total": {"dias": 999},
            "experiencias": [_exp(1, "2020-01-01", "2020-12-31", dias=366)]}
    assert totales_cuadran(prof)
    prof["total"]["dias"] = 366
    assert totales_cuadran(prof) == []


def test_puntaje_total():
    espejo = {"resumen_evaluacion": {
        "factores": [{"factor": "A", "puntaje": 55}, {"factor": "C", "puntaje": 15},
                     {"factor": "B", "puntaje": "NO APLICA"}],
        "puntaje_total": 100}}
    assert puntaje_total_cuadra(espejo)  # 70 ≠ 100
    espejo["resumen_evaluacion"]["puntaje_total"] = 70
    assert puntaje_total_cuadra(espejo) == []


# ── Calibración fijada contra los espejos reales ─────────────────────────────

def _cargar_fixture(rel: str) -> dict:
    ruta = FIXTURES / rel
    if not ruta.exists():
        pytest.skip(f"fixture local no disponible: {rel}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_calibracion_trujillo_limpio():
    espejo = _cargar_fixture("trujillo/trujillo_espejo_full.json")
    assert verificar_espejo(espejo) == []


def test_calibracion_libertador_hallazgos_conocidos():
    espejo = _cargar_fixture("new_format/libertador_espejo.json")
    obs = verificar_espejo(espejo)

    por_codigo: dict[str, int] = {}
    for o in obs:
        por_codigo[o.codigo] = por_codigo.get(o.codigo, 0) + 1

    # El extractor de fixtures no mapea `cumple` → los 14 disparan (gap del
    # extractor; la skill real lo emite). Si esto baja, el fixture mejoró.
    assert por_codigo.get("VEREDICTO") == 14
    # Traslape REAL de 2 días (prof 9: exp 3 termina 2025-02-02, exp 4
    # empieza 2025-02-01) que nadie marcó en el Excel — hallazgo genuino.
    assert por_codigo.get("NOTA9") == 2
    refs_n9 = {o.referencia for o in obs if o.codigo == "NOTA9"}
    assert refs_n9 == {"prof=9 exp=3", "prof=9 exp=4"}
    # Nada más dispara: COVID, orden, totales y puntaje están consistentes.
    assert set(por_codigo) == {"VEREDICTO", "NOTA9"}
