"""
Traducción de vocabularios de la prueba de aceptación (ADR-015 §3 y §4), sin
datos privados: `test_aceptacion_auditoria.py` se salta entero cuando la
auditoría no está, así que estas piezas —las que deciden qué cuenta como
RESUELTO— necesitan su propia regresión en la suite pública.
"""
from __future__ import annotations

from tests.test_aceptacion_auditoria import (_VIAS_DE_ETAPA, _veredicto,
                                             _veredicto_persistido)


def test_el_resolver_solo_resuelve_o_se_abstiene():
    assert _veredicto({"estado": "resuelto", "cui": "2000001"}) == ("RESUELTO", "2000001")
    assert _veredicto({"estado": "na", "cui": None}) == ("PRIVADA", None)
    # todo lo demás —revision, portal caído, sin_cui— es PENDIENTE para el humano
    assert _veredicto({"estado": "revision", "cui": None}) == ("PENDIENTE", None)
    assert _veredicto({}) == ("PENDIENTE", None)


def test_el_resultado_persistido_se_lee_por_via_y_cui():
    """El enriquecimiento no guarda `estado`: la vía PRIVADA marca la privada y
    la presencia de `cui` marca la identificación."""
    assert _veredicto_persistido({"via": "CONTRATO", "cui": "2000002"}) == \
        ("RESUELTO", "2000002", "CONTRATO")
    assert _veredicto_persistido({"via": "PRIVADA", "cui": None}) == ("PRIVADA", None, "PRIVADA")
    assert _veredicto_persistido({"via": "REVISION", "cui": None}) == \
        ("PENDIENTE", None, "REVISION")
    # multi-obra (ADR-011): el job lo registra sin CUI propio → PENDIENTE
    assert _veredicto_persistido({"via": "MULTI_OBRA", "cui": None}) == \
        ("PENDIENTE", None, "MULTI_OBRA")
    assert _veredicto_persistido(None) == ("PENDIENTE", None, "")


def test_las_vias_de_etapa_son_las_que_consultan_el_mef_en_vivo():
    """Son las que el replay NO puede reproducir; por eso la aceptación lee su
    resultado persistido en vez de exigírselo al resolver."""
    assert set(_VIAS_DE_ETAPA) == {"CONTRATO", "RESOLUCION", "MEF"}
