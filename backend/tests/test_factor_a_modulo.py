"""Regresiones de los módulos extraídos de requisitos y Factor A."""
from reglas.factor_a import letra_factor, participantes_factor_a, recalcular_factor_a
from reglas.requisitos import minimo_exigido
from orquestador.etapas_reales import (
    _letra_factor, _minimo_exigido, _participantes_factor_a,
    _recalcular_factor_a,
)


def test_aliases_legacy_son_las_mismas_funciones():
    assert _minimo_exigido is minimo_exigido
    assert _letra_factor is letra_factor
    assert _participantes_factor_a is participantes_factor_a
    assert _recalcular_factor_a is recalcular_factor_a


def test_minimo_publico_conserva_unidad_y_conversion():
    assert minimo_exigido({"texto": "Experiencia mínima: 24 meses"}) == (720, "24 meses")
    assert minimo_exigido({"minimo_experiencia": {
        "cantidad": 3, "unidad": "anios", "texto": "3 años"}}) == (1095, "3 años")


def test_letra_y_participantes_factor_a():
    assert letra_factor({"factor": "A — Experiencia específica"}) == "A"
    espejo = {"profesionales": [
        {"n_prof": 1, "requisitos": {"factor_a_aplica": True}},
        {"n_prof": 2, "requisitos": {"factor_a_aplica": False}},
    ]}
    assert participantes_factor_a(espejo) == {1}
