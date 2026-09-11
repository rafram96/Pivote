"""Mínimos estructurados y lectura retrocompatible; sin red ni jobs reales."""
import pytest

from orquestador.etapas_reales import _minimo_exigido


@pytest.mark.parametrize("texto,esperado", [
    ("Acreditar mínimo (6) años a partir de su colegiatura", (2190, "6 años")),
    ("Acreditar mínimo (5) años a partir de su colegiatura", (1825, "5 años")),
    ("Experiencia mínima: veinticuatro (24) meses", (720, "24 meses")),
    ("Experiencia mínima: (180) días", (180, "180 días")),
    ("Experiencia mínima: (0,5) años (6 meses)", (180, "6 meses")),
    ("No se indica mínimo", None),
])
def test_minimo_literal_con_parentesis(texto, esperado):
    assert _minimo_exigido({"tipo_experiencia_valida": texto}) == esperado


@pytest.mark.parametrize("cantidad,unidad,esperado", [
    (6, "anios", (2190, "6 años")), (5, "anios", (1825, "5 años")),
    (24, "meses", (720, "24 meses")), (180, "dias", (180, "180 días")),
    ("0,5", "anios", (183, "0.5 años")),
])
def test_minimo_estructurado_no_depende_de_prosa(cantidad, unidad, esperado):
    assert _minimo_exigido({"minimo_experiencia": {
        "cantidad": cantidad, "unidad": unidad, "texto": "Según cuadro de requisitos",
        "folio": 23, "fuente": "terminos_de_referencia",
    }}) == esperado


def test_minimo_estructurado_conserva_equivalencia_literal_de_meses():
    assert _minimo_exigido({"minimo_experiencia": {
        "cantidad": 0.5, "unidad": "anios", "texto": "0.5 años (6 meses)",
    }}) == (180, "6 meses")


@pytest.mark.parametrize("valor", [None, True, 0, -1, "NaN", "Infinity", "no leído", {}])
def test_minimo_estructurado_invalido_no_inventa_umbral(valor):
    assert _minimo_exigido({"minimo_experiencia": {
        "cantidad": valor, "unidad": "anios",
    }}) is None
    assert _minimo_exigido({"minimo_experiencia": {
        "cantidad": valor, "unidad": "anios",
    }, "tipo_experiencia_valida": "mínimo (5) años"}) == (1825, "5 años")


def test_fuente_anidada_no_se_confunde_con_requisito():
    assert _minimo_exigido({"fuente": {"otro_requisito": "mínimo 8 años"}}) is None


@pytest.mark.parametrize("unidad", [None, "semanas", {}, []])
def test_unidad_desconocida_no_interrumpe_el_calculo(unidad):
    assert _minimo_exigido({"minimo_experiencia": {
        "cantidad": 5, "unidad": unidad,
    }}) is None
