"""Reglas de entrada incompletas no se convierten en cumplimiento o puntaje."""
from copy import deepcopy

import openpyxl
import pytest

from orquestador.etapas_reales import _recalcular_factor_a
from scripts.generar_excel import generar_excel
from validacion.postor import recalcular_experiencia_postor


def _postor(total):
    return {"postor": {"experiencia_postor_total": total,
                       "postor_cumple": "CUMPLE — juicio previo",
                       "experiencia_postor": [{"monto_item": "2000000.00"}]}}


@pytest.mark.parametrize("total", [{}, {"monto_requerido": None},
    {"monto_requerido": "1250000", "requisito_estado": "por_verificar"},
    {"monto_requerido": "1250000", "requisito_moneda": "USD"}])
def test_minimo_ausente_o_no_utilizable_no_conserva_cumple(total):
    espejo = _postor(total)
    recalcular_experiencia_postor(espejo)
    assert espejo["postor"]["postor_cumple"].startswith("POR VERIFICAR")


@pytest.mark.parametrize("requerido, prefijo", [("1250000", "CUMPLE"), ("2500000", "NO CUMPLE")])
def test_minimo_estructurado_lo_compara_el_backend(requerido, prefijo):
    espejo = _postor({"monto_requerido": requerido, "requisito_estado": "encontrado", "requisito_moneda": "PEN"})
    recalcular_experiencia_postor(espejo)
    assert espejo["postor"]["postor_cumple"].startswith(prefijo)
    assert requerido in espejo["postor"]["postor_cumple"]


def test_no_aplica_no_equivale_a_cumple():
    espejo = _postor({"monto_requerido": None, "requisito_estado": "no_aplica",
                      "requisito_fuente": {"pagina_pdf": 27, "texto": "No se exige experiencia del postor."}})
    recalcular_experiencia_postor(espejo)
    assert espejo["postor"]["postor_cumple"].startswith("NO APLICA")


@pytest.mark.parametrize("regla", [
    {"dias_adicionales_requeridos": None, "tramos": [{"desde_porcentaje": None, "hasta_porcentaje": None, "puntaje": 60}]},
    {"dias_adicionales_requeridos": 180, "tramos": [{"desde_porcentaje": None, "hasta_porcentaje": None, "puntaje": 60}]},
    {"dias_adicionales_requeridos": None, "tramos": [{"desde_porcentaje": 0, "hasta_porcentaje": 100, "hasta_inclusivo": True, "puntaje": 60}]},
])
def test_baremo_incompleto_no_otorga_puntaje_universal(regla):
    espejo = {"reglas_evaluacion": {"factor_a": regla},
              "profesionales": [{"n_prof": 1, "requisitos": {"factor_a_aplica": True}}],
              "resumen_evaluacion": {"factores": [{"factor": "A", "puntaje": 60}]}}
    original = deepcopy(regla)
    _recalcular_factor_a(espejo, {"prof:1": {"minimo_dias": 365, "dias_efectivos": 366}})
    factor = espejo["resumen_evaluacion"]["factores"][0]
    assert factor["puntaje"] is None
    assert factor["puntaje_confirmado"] is None
    assert factor["estado_puntaje"] == "condicionado"
    assert espejo["reglas_evaluacion"]["factor_a"] == original


def test_excel_muestra_minimo_y_pagina_de_bases(tmp_path):
    espejo = _postor({"monto_requerido": "1250000.00", "requisito_estado": "encontrado",
                      "requisito_moneda": "PEN", "requisito_fuente": {"pagina_pdf": 27, "texto": "Mínimo acumulado."}})
    espejo.update({"_meta": {}, "profesionales": [], "resumen_evaluacion": {"factores": []}})
    salida = tmp_path / "minimo.xlsx"
    generar_excel(espejo, salida)
    wb = openpyxl.load_workbook(salida)
    textos = "\n".join(str(c.value) for ws in wb for row in ws for c in row if c.value is not None)
    assert "MÍNIMO DE EXPERIENCIA DEL POSTOR" in textos
    assert "1250000.00" in textos
    assert "página 27" in textos
    wb.close()
