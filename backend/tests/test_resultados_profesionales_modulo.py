from __future__ import annotations

from copy import deepcopy
import pytest

from entregables.excel_final import reconciliar_resultados_profesionales as historico
from reglas.resultados_profesionales import (
    inyectar_veredicto_backend, reconciliar_resultados_profesionales,
)


def _datos():
    espejo = {"_meta": {"tipo_evaluacion": "obras"}, "profesionales": [{
        "n_prof": 1, "requisitos": {}, "experiencias": [{
            "n": 1, "proyecto": "OBRA A", "fecha_inicial": "2020-01-01",
            "fecha_final": "2020-12-31",
        }],
    }]}
    enriquecimiento = {"1:1": {"via": "NOMBRE"}, "prof:1": {"marca": "original"}}
    return espejo, enriquecimiento


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_reconciliar_es_equivalente_y_no_muta_entradas(tipo):
    espejo, enr = _datos()
    espejo["_meta"]["tipo_evaluacion"] = tipo
    espejo0, enr0 = deepcopy(espejo), deepcopy(enr)
    assert historico is reconciliar_resultados_profesionales
    resultado = reconciliar_resultados_profesionales(espejo, enr)[1]
    assert resultado["dias_efectivos"] == 366
    assert resultado["marca"] == "original"
    assert espejo == espejo0 and enr == enr0


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_inyectar_es_idempotente_y_mutador_explicito(tipo):
    espejo, enr = _datos()
    espejo["_meta"]["tipo_evaluacion"] = tipo
    inyectar_veredicto_backend(espejo, enr)
    primero = deepcopy((espejo, enr))
    inyectar_veredicto_backend(espejo, enr)
    assert (espejo, enr) == primero


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
@pytest.mark.parametrize("fin,dias,cumple", [
    ("2019-12-30", 364, False), ("2019-12-31", 365, True),
])
def test_umbral_se_compara_en_dias_sin_redondear(tipo, fin, dias, cumple):
    espejo, enr = _datos()
    espejo["_meta"]["tipo_evaluacion"] = tipo
    prof = espejo["profesionales"][0]
    prof["requisitos"] = {"texto": "Experiencia mínima: 1 año"}
    prof["experiencias"][0].update(fecha_inicial="2019-01-01", fecha_final=fin)
    enr["1:1"] = {"via": "CUI_TEXTO", "cui": "1111111"}
    resultado = reconciliar_resultados_profesionales(espejo, enr)[1]
    assert resultado["dias_efectivos"] == dias
    assert resultado["minimo_dias"] == 365
    assert (str(resultado.get("cumple_backend", "")).startswith("NO CUMPLE")) is not cumple


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_privada_sin_sunat_conserva_dias_y_motivo_provisional(tipo):
    espejo, enr = _datos()
    espejo["_meta"]["tipo_evaluacion"] = tipo
    enr["1:1"] = {"via": "PRIVADA", "paralizaciones": [("2020-01-01", "2020-12-31")]}
    datos = reconciliar_resultados_profesionales(espejo, enr)[1]
    assert datos["dias_efectivos"] == 366
    assert datos["dias_paralizados"] == 0
    assert datos["veredicto_provisional"] == [1]
    assert "SUNAT" in datos["cumple_backend"]


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_traslape_se_desconta_una_vez(tipo):
    espejo, enr = _datos()
    espejo["_meta"]["tipo_evaluacion"] = tipo
    prof = espejo["profesionales"][0]
    prof["experiencias"] = [
        {"n": 1, "fecha_inicial": "2020-01-01", "fecha_final": "2020-01-10"},
        {"n": 2, "fecha_inicial": "2020-01-06", "fecha_final": "2020-01-15"},
    ]
    datos = reconciliar_resultados_profesionales(espejo, enr)[1]
    assert (datos["dias_brutos"], datos["dias_traslape"], datos["dias_efectivos"]) == (20, 5, 15)
