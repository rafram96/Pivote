"""
Tests offline de la resolución de CUI: detección de ubicación (departamento) y
penalización de scoring. Sin red.
"""
from __future__ import annotations

from resolucion.cui import _puntuar, norm, ubicacion


def test_ubicacion_no_confunde_ica_dentro_de_huancavelica():
    # "ICA" es substring de "HUANCAVEL-ICA": con `d in cola` se colaba como depto
    # falso. El match por límite de palabra lo evita.
    assert ubicacion("Mejoramiento del Puesto de Salud Lircay, Huancavelica") == {
        "HUANCAVELICA"}


def test_ubicacion_expande_alias_hvca():
    assert ubicacion("Puesto de Salud Lircay, HVCA") == {"HUANCAVELICA"}


def test_ubicacion_detecta_departamento_compuesto():
    assert ubicacion("Centro de Salud Pueblo Nuevo, La Libertad") == {"LA LIBERTAD"}


def test_puntuar_penalizacion_departamental_suave():
    # nombre idéntico pero departamento distinto del hint: penalización SUAVE
    # (-10) para no enterrar a la obra correcta registrada en otra sede.
    cand = {"nombrObra": "PUESTO DE SALUD DE LIRCAY", "nombrDepartamento": "LIMA"}
    sc = _puntuar(cand, norm("Puesto de Salud de Lircay"), {"HUANCAVELICA"}, None)
    assert sc == 95.0  # _sim 100 − 10 (depto distinto) + 5 (es de salud)


def test_puntuar_boost_mismo_departamento():
    cand = {"nombrObra": "PUESTO DE SALUD DE LIRCAY", "nombrDepartamento": "HUANCAVELICA"}
    sc = _puntuar(cand, norm("Puesto de Salud de Lircay"), {"HUANCAVELICA"}, None)
    assert sc == 120.0  # _sim 100 + 15 (mismo depto) + 5 (salud)
