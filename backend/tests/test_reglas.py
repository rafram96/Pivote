"""
Tests del motor de reglas — goldens tomados de las hojas manuales del
ingeniero en el formato definitivo (hojas JEFE y Estructura del Excel
Libertador). Solo fechas y conteos; sin nombres ni datos identificables.
"""
from __future__ import annotations

from datetime import date

import pytest

from reglas import (
    alerta_experiencia_antigua,
    anios,
    dias_efectivos_profesional,
    dias_inclusivos,
    fecha_cutoff,
    fusionar_traslapes,
    restar_paralizaciones,
)


# ── Conteo inclusivo (convención del ingeniero, 6 pares verificados) ─────────

@pytest.mark.parametrize("ini, fin, esperado", [
    (date(2016, 6, 10), date(2017, 5, 15), 340),
    (date(2019, 5, 1), date(2019, 10, 31), 184),
    (date(2023, 11, 22), date(2025, 7, 22), 609),
    (date(2021, 5, 13), date(2023, 5, 6), 724),   # certificado completo (brutos)
    (date(2020, 1, 1), date(2020, 1, 1), 1),       # un solo día cuenta 1
])
def test_dias_inclusivos(ini, fin, esperado):
    assert dias_inclusivos(ini, fin) == esperado


def test_dias_inclusivos_rechaza_invertido():
    with pytest.raises(ValueError):
        dias_inclusivos(date(2020, 2, 1), date(2020, 1, 1))


# ── Experiencia efectiva (golden: hoja JEFE, certificado partido en 4 tramos) ─

CERT = (date(2021, 5, 13), date(2023, 5, 6))
PARALIZACIONES_OBRA = [
    (date(2021, 10, 1), date(2021, 10, 31)),
    (date(2022, 2, 1), date(2022, 4, 30)),
    (date(2022, 7, 1), date(2022, 9, 30)),
]


def test_restar_paralizaciones_golden_jefe():
    tramos = restar_paralizaciones(CERT, PARALIZACIONES_OBRA)
    assert [dias_inclusivos(i, f) for i, f in tramos] == [141, 92, 61, 218]
    assert tramos[0] == (date(2021, 5, 13), date(2021, 9, 30))
    assert tramos[-1] == (date(2022, 10, 1), date(2023, 5, 6))


def test_restar_paralizaciones_golden_estructura():
    # Hoja Estructura: cert 2019-11-04→2023-03-31 (1244 brutos) queda en
    # 762 + 424 = 1186 efectivos (paralizado nov-2019 y ene-2022)
    tramos = restar_paralizaciones(
        (date(2019, 11, 4), date(2023, 3, 31)),
        [(date(2019, 11, 4), date(2019, 11, 30)),
         (date(2022, 1, 1), date(2022, 1, 31))],
    )
    assert [dias_inclusivos(i, f) for i, f in tramos] == [762, 424]


def test_restar_paralizaciones_fuera_del_periodo_no_afecta():
    tramos = restar_paralizaciones(
        (date(2021, 1, 1), date(2021, 12, 31)),
        [(date(2020, 1, 1), date(2020, 6, 30)), (date(2022, 3, 1), date(2022, 4, 1))],
    )
    assert tramos == [(date(2021, 1, 1), date(2021, 12, 31))]


def test_restar_paralizaciones_cubre_todo_deja_cero():
    assert restar_paralizaciones(
        (date(2021, 3, 1), date(2021, 6, 30)),
        [(date(2021, 1, 1), date(2021, 12, 31))],
    ) == []


# ── Traslapes (ALT11) ─────────────────────────────────────────────────────────

def test_fusionar_traslapes_descuenta_solo_el_solape():
    fusionados, traslape = fusionar_traslapes([
        (date(2020, 1, 1), date(2020, 6, 30)),
        (date(2020, 4, 1), date(2020, 9, 30)),
    ])
    assert fusionados == [(date(2020, 1, 1), date(2020, 9, 30))]
    assert traslape == dias_inclusivos(date(2020, 4, 1), date(2020, 6, 30))  # 91


def test_contiguos_se_unen_sin_contar_traslape():
    fusionados, traslape = fusionar_traslapes([
        (date(2020, 1, 1), date(2020, 3, 31)),
        (date(2020, 4, 1), date(2020, 6, 30)),  # empieza al día siguiente
    ])
    assert fusionados == [(date(2020, 1, 1), date(2020, 6, 30))]
    assert traslape == 0


def test_fusionar_vacio():
    assert fusionar_traslapes([]) == ([], 0)


# ── Paso 5 completo (golden: hoja CLAUDE ↔ hoja JEFE reconcilian) ────────────

def test_dias_efectivos_profesional_golden_jefe():
    experiencias = [
        (date(2016, 6, 10), date(2017, 5, 15)),   # 340
        (date(2019, 5, 1), date(2019, 10, 31)),   # 184
        CERT,                                      # 724 brutos → 512 efectivos
        (date(2023, 11, 22), date(2025, 7, 22)),  # 609
    ]
    res = dias_efectivos_profesional(experiencias, {2: PARALIZACIONES_OBRA})

    assert res.dias_brutos == 1857        # total de la hoja CLAUDE
    assert res.dias_paralizados == 212
    assert res.dias_traslape == 0
    assert res.dias_efectivos == 1645     # total de la hoja JEFE
    assert anios(res.dias_efectivos) == pytest.approx(4.506849315068493)


def test_dias_efectivos_con_traslape_entre_experiencias():
    # Dos experiencias que se solapan en junio (30 días, ALT11)
    res = dias_efectivos_profesional([
        (date(2021, 1, 1), date(2021, 6, 30)),
        (date(2021, 6, 1), date(2021, 12, 31)),
    ])
    assert res.dias_traslape == 30
    assert res.dias_efectivos == dias_inclusivos(date(2021, 1, 1), date(2021, 12, 31))


# ── ALT03 (cutoff 25 años — confirmado por el cliente 2026-06-10) ────────────

def test_alerta_experiencia_antigua():
    presentacion = date(2026, 1, 15)
    assert fecha_cutoff(presentacion) == date(2001, 1, 15)
    assert alerta_experiencia_antigua(date(2000, 12, 31), presentacion) is True
    assert alerta_experiencia_antigua(date(2001, 1, 15), presentacion) is False
    assert alerta_experiencia_antigua(date(2010, 1, 1), presentacion) is False


def test_fecha_cutoff_29_febrero():
    # 2024-02-29 − 25 años → 1999 no es bisiesto → cae al 28
    assert fecha_cutoff(date(2024, 2, 29)) == date(1999, 2, 28)
