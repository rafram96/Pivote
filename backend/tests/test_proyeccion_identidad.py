"""La presentación conserva identidad y evidencia sin resolverlas otra vez."""
from copy import deepcopy

import pytest

from entregables.certeza import (
    alertas_experiencia, clasificar_identificacion, identificacion_panel,
)
from entregables.excel_final import desempaquetar_enriquecimiento
from entregables.identidad import proyectar_identidad
from entregables.procedencia import procedencia_cui, rotulo_cui


@pytest.mark.parametrize("enr", [
    {},
    {"cui": "2222222", "via": "PROBABLE"},
    {"cui": "2222222", "obra": {"cui": "3333333"}, "via": "NOMBRE"},
    {"obra_ficha": {"cui": "4444444"}, "via": "NOMBRE"},
    {"verificacion_expediente": {"cui_confirmado": "5555555"}},
    {"via": "PRIVADA", "sunat": {"estado": "BAJA DE OFICIO"}},
    {"via": "REVISION", "seleccion_obra_pendiente": True, "cui": None,
     "motivo_revision": "No se pudo seleccionar ficha", "sin_verificar": True},
    {"via": "REVISION", "naturaleza_en_conflicto": True,
     "motivo_revision": "Naturaleza pública o privada pendiente de contraste"},
    {"via": "MULTI_OBRA", "identificacion_incompleta": True, "sub_obras": [
        {"nombre": "Escuela ficticia", "cui": "6666666", "estado": "resuelto"},
        {"nombre": "Mercado ficticio", "estado": "revision"}]},
    {"via": "NOMBRE", "cui": "7777777", "resolucion_aprobacion": {
        "coincide_emisor": "nombra_otro", "consultores": ["Consultora ficticia"]}},
])
@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_crudo_y_ficha_comparten_identidad_sin_mutar_fuentes(enr, tipo):
    exp = {"n": 1, "cui": "1111111"}
    antes = deepcopy((exp, enr))
    _, _, fichas, _ = desempaquetar_enriquecimiento({"1:1": enr})
    directa = proyectar_identidad(exp, enr, tipo)
    ficha = fichas.get((1, 1), {})
    assert proyectar_identidad(exp, ficha, tipo) == directa
    assert directa["procedencia"] == procedencia_cui(exp, enr)
    assert directa["rotulo_cui"] == rotulo_cui(directa["procedencia"])
    if tipo == "expedientes":
        assert directa["certeza"] == clasificar_identificacion(exp, enr)
        assert directa["identificacion"] == identificacion_panel(exp, enr)
        assert directa["alertas"] == alertas_experiencia(exp, enr)
    else:
        assert directa["certeza"] is None
        assert directa["identificacion"] is None
        assert directa["alertas"] == []
    if ficha:
        # Conserva incluso motivos/marcas nuevas; no otra lista parcial de campos.
        assert ficha["_enriquecimiento_identidad"] is enr
    assert (exp, enr) == antes


def test_ficha_legada_no_rellena_utilizado_nulo_con_cui_aplanado():
    ficha = {"cui": "9999999", "_procedencia_cui": {
        "cui_declarado": "8888888", "cui_utilizado": None,
        "via": "REVISION", "sub_obras": []}}
    antes = deepcopy(ficha)
    proyeccion = proyectar_identidad({"cui": "1111111"}, ficha, "expedientes")
    assert proyeccion["procedencia"]["cui_declarado"] == "1111111"
    assert proyeccion["procedencia"]["cui_utilizado"] is None
    assert "CUI utilizado: no registrado" in proyeccion["rotulo_cui"]
    assert ficha == antes


def test_sunat_por_canal_excel_se_conserva_sin_reescribir_original():
    enr = {"via": "PRIVADA"}
    _, _, fichas, _ = desempaquetar_enriquecimiento({"1:1": enr})
    ficha = {**fichas[(1, 1)], "sunat": {"estado": "BAJA DE OFICIO"}}
    proyeccion = proyectar_identidad({}, ficha, "expedientes")
    assert proyeccion["alertas"] == ["El emisor figura de BAJA en SUNAT"]
    assert enr == {"via": "PRIVADA"}


def test_declarante_ausente_no_hereda_cui_utilizado():
    proyeccion = proyectar_identidad(None, {"cui": "2222222"}, "expedientes")
    assert proyeccion["procedencia"]["cui_declarado"] is None
    assert proyeccion["procedencia"]["cui_utilizado"] == "2222222"
    assert proyeccion["identificacion"]["nivel"] == "sin_identificar"


def test_contexto_vacio_explicito_manda_sobre_ficha_aplanada():
    proyeccion = proyectar_identidad({"cui": "1111111"}, {
        "_enriquecimiento_identidad": {}, "cui": "2222222", "via": "NOMBRE",
    }, "expedientes")
    assert proyeccion["procedencia"]["cui_utilizado"] is None
    assert proyeccion["identificacion"]["nivel"] == "sin_identificar"
