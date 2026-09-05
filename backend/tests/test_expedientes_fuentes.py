"""Regresiones de fuentes aplicables en concursos de expedientes."""
from __future__ import annotations

import pytest

from entregables.certeza import (
    fuente_mef, fuente_mef_panel, normalizar_motivo_fuente,
)


def _texto_excel(enr: dict) -> str:
    fuente = fuente_mef(enr)
    return " · ".join(texto for texto in (
        fuente["contrato"], fuente["resolucion"], fuente["consultor"]
    ) if texto and texto != "—")


@pytest.mark.parametrize("via", ["PRIVADA", "NA", "privada", "na"])
def test_la_via_privada_no_exige_cui_ni_fuente_publica(via):
    enr = {"via": via, "sin_documentos_mef": True}
    fuente = fuente_mef(enr)
    panel = fuente_mef_panel(enr)
    assert fuente["contrato"] == (
        "No aplica consulta MEF/InfoObras a esta experiencia privada")
    assert "CUI" not in fuente["contrato"]
    assert panel["estado"] == "sin_documentos"
    assert panel["contrato"] is None


def test_vacio_y_expediente_identificado_sin_documentos_no_dicen_lo_mismo():
    vacio = fuente_mef({})
    identificado = fuente_mef({"via": "NOMBRE", "cui": "1234567"})
    assert vacio["contrato"] == (
        "Identificación del expediente pendiente; no hay respaldo MEF "
        "vinculado de forma verificable")
    assert identificado["contrato"] == (
        "Este análisis no dispone de contrato/resolución utilizable para el "
        "contraste")
    assert "no publica" not in vacio["contrato"].lower()
    assert "no publica" not in identificado["contrato"].lower()


def test_la_marca_antigua_no_oculta_un_contrato_posterior():
    enr = {"via": "NOMBRE", "cui": "1234567", "sin_documentos_mef": True,
           "verificacion_expediente": {
               "contratista": {"valor": "CONSULTORA EJEMPLO", "veredicto": "ok"},
               "contrato": {"numero": "008-2024", "fecha": "2024-01-15",
                            "veredicto": "ok", "elegido_por": "emisor"}}}
    fuente = fuente_mef(enr)
    panel = fuente_mef_panel(enr)
    assert fuente["sin_documentos"] is False
    assert "Contrato N° 008-2024" in fuente["contrato"]
    assert panel["estado"] == "contrato"
    assert panel["contrato"]["del_emisor"] is True


def test_documentos_discrepantes_y_fecha_descartada_se_conservan_separados():
    enr = {
        "via": "NOMBRE", "cui": "1234567",
        "verificacion_expediente": {
            "contratista": {"valor": "OTRA CONSULTORA",
                            "declarado": "CONSULTORA DECLARADA",
                            "veredicto": "discrepancia"},
            "contrato": {"numero": "019-2023", "fecha": "2023-04-10",
                         "veredicto": "discrepancia", "elegido_por": "mas_barato",
                         "otros_contratos_expediente": ["020-2023 — TERCERA"]}},
        "resolucion_aprobacion": {
            "numero": "044-2023", "fecha": None,
            "fecha_descartada": "2001-02-03",
            "fecha_motivo": "anterior al contrato",
            "coincide_emisor": "nombra_otro"}}
    fuente = fuente_mef(enr)
    panel = fuente_mef_panel(enr)
    assert "NO coincide con lo declarado" in fuente["contrato"]
    assert "elegido por ser el de menor monto" in fuente["contrato"]
    assert "otros contratos del expediente: 020-2023 — TERCERA" in fuente["contrato"]
    assert "se descartó 03/02/2001: anterior al contrato" in fuente["resolucion"]
    assert panel["estado"] == "ambos"
    assert panel["contrato"]["del_emisor"] is False
    assert panel["resolucion"]["fecha"] is None
    assert panel["resolucion"]["fecha_descartada"] == "2001-02-03"


def test_una_resolucion_con_solo_documento_no_desaparece():
    enr = {"via": "NOMBRE", "cui": "1234567",
           "verificacion_expediente": {
               "resolucion": {"documento": "resolucion_aprobacion.pdf"}}}
    fuente = fuente_mef(enr)
    panel = fuente_mef_panel(enr)
    assert fuente["resolucion"] == (
        "Resolución de aprobación: documento disponible")
    assert panel["estado"] == "resolucion"
    assert panel["resolucion"] == {
        "numero": None, "fecha": None, "coincide_emisor": None,
        "fecha_descartada": None, "fecha_motivo": None}


@pytest.mark.parametrize("enr", [
    {},
    {"via": "NOMBRE", "cui": "1234567", "sin_documentos_mef": True},
    {"via": "NA"},
    {"via": "NOMBRE", "cui": "1234567", "verificacion_expediente": {
        "contrato": {"numero": "001"}, "contratista": {"valor": "CONSULTORA"}}},
])
def test_el_texto_del_panel_es_identico_al_del_entregable(enr):
    assert fuente_mef_panel(enr)["texto"] == _texto_excel(enr)


@pytest.mark.parametrize(("original", "esperado"), [
    ("El MEF no publica la resolución de aprobación de este expediente; resto.",
     "Este análisis no dispone de una resolución de aprobación utilizable; resto."),
    ("Además, el MEF no publica contratos ni Formato 08-A para este proyecto.",
     "Además, este análisis no dispone de contratos ni Formato 08-A para este proyecto."),
    ("el proceso identificado no publica la fecha en que se firmó; revisar.",
     "este análisis no dispone de la fecha en que se firmó; revisar."),
])
def test_normaliza_solo_la_plantilla_historica_y_preserva_el_resto(original, esperado):
    assert normalizar_motivo_fuente(original) == esperado


def test_un_motivo_desconocido_no_se_reescribe():
    motivo = "El portal respondió con una observación distinta; conservar literal."
    assert normalizar_motivo_fuente(motivo) == motivo
