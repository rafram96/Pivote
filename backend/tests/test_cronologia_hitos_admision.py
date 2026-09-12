"""Admisión de hitos documentales en la cronología.

Los datos son sintéticos: prueban la autoridad estructurada persistida por el
backend, no nombres ni expedientes reales.
"""
from datetime import date

from entregables import cronologia


def _senal(nombre, sentido):
    return {"nombre": nombre, "fuerza": "fuerte", "sentido": sentido,
            "detalle": "caso sintético"}


def _seace(*senales):
    return {"estado": "seleccionado",
            "proceso": {"fecha_firma": "2022-06-18"},
            "candado": {"resultado": "por_confirmar", "senales": list(senales)}}


def _identidad_admitida():
    return _seace(_senal("entidad", "a_favor"),
                  _senal("adjudicatario", "a_favor"),
                  _senal("objeto", "a_favor"))


def _mef_verificado(fecha_resolucion="2022-06-18"):
    return {"verificado_en_mef": True,
            "contratista": {"veredicto": "ok"},
            "resolucion": {"fecha": fecha_resolucion}}


def test_seace_seleccionado_rechazado_no_pinta_c():
    fx = {"seace": _seace(_senal("entidad", "en_contra"),
                          _senal("objeto", "a_favor"))}
    assert cronologia.hito_firma(fx) is None


def test_seace_seleccionado_admitido_pinta_c():
    assert cronologia.hito_firma({"seace": _identidad_admitida()}) == date(2022, 6, 18)


def test_seace_seleccionado_sin_candado_no_pinta_c():
    fx = {"seace": {"estado": "seleccionado",
                     "proceso": {"fecha_firma": "2022-06-18"}}}
    assert cronologia.hito_firma(fx) is None


def test_seace_seleccionado_con_candado_vacio_no_pinta_c():
    fx = {"seace": {"estado": "seleccionado",
                     "proceso": {"fecha_firma": "2022-06-18"},
                     "candado": {}}}
    assert cronologia.hito_firma(fx) is None


def test_contradiccion_solo_temporal_no_descarta_identidad():
    fx = {"seace": _seace(_senal("entidad", "a_favor"),
                          _senal("adjudicatario", "a_favor"),
                          _senal("objeto", "a_favor"),
                          _senal("temporal", "en_contra"))}
    assert cronologia.hito_firma(fx) == date(2022, 6, 18)


def test_seace_rechazado_no_se_rescata_con_mef():
    fx = {"contrato_emisor": {"fecha": "2021-04-09"},
          "seace": _seace(_senal("entidad", "en_contra"),
                          _senal("objeto", "a_favor"))}
    assert cronologia.hito_firma(fx) is None


def test_seace_no_seleccionado_sin_mef_no_pinta_c():
    assert cronologia.hito_firma({"seace": {"estado": "sin_proceso"}}) is None


def test_mef_contrato_emisor_autoriza_firma():
    fx = {"contrato_emisor": {"fecha": "2021-04-09"}}
    assert cronologia.hito_firma(fx) == date(2021, 4, 9)


def test_mef_contrato_coincide_autoriza_fecha_de_suscripcion():
    fx = {"verificacion_expediente": {"contrato": {
        "fecha_suscripcion": "2021-04-09", "veredicto": "coincide"
    }}}
    assert cronologia.hito_firma(fx) == date(2021, 4, 9)


def test_mef_contrato_emisor_elegido_por_emisor_autoriza():
    fx = {"verificacion_expediente": {"contrato": {
        "fecha_suscripcion": "2021-04-09", "elegido_por": "emisor"
    }}}
    assert cronologia.hito_firma(fx) == date(2021, 4, 9)


def test_contrato_heuristico_no_autoriza_hito():
    fx = {"verificacion_expediente": {"contrato": {
        "fecha": "2021-04-09", "elegido_por": "mas_barato"
    }}}
    assert cronologia.hito_firma(fx) is None


def test_resolucion_valida_solo_con_identidad_y_fecha_oficial():
    fx = {"resolucion_aprobacion": {"coincide_emisor": "confirma"},
          "verificacion_expediente": _mef_verificado()}
    assert cronologia.hito_resolucion(fx) == date(2022, 6, 18)


def test_resolucion_descartada_no_reintroduce_fecha_bruta():
    fx = {"resolucion_aprobacion": {
              "fecha_descartada": "2011-03-22",
              "fecha_motivo": "anterior al contrato"},
          "verificacion_expediente": _mef_verificado("2022-06-18")}
    assert cronologia.hito_resolucion(fx) is None


def test_resolucion_de_otro_emisor_no_es_hito():
    fx = {"resolucion_aprobacion": {
              "fecha": "2022-06-18", "coincide_emisor": "nombra_otro"},
          "verificacion_expediente": _mef_verificado()}
    assert cronologia.hito_resolucion(fx) is None


def test_resolucion_sin_identidad_no_es_hito():
    fx = {"resolucion_aprobacion": {"fecha": "2022-06-18"},
          "verificacion_expediente": {
              "resolucion": {"fecha": "2022-06-18"}}}
    assert cronologia.hito_resolucion(fx) is None


def test_resolucion_infoobras_inferida_no_es_hito():
    fx = {"verificacion_expediente": {
              "verificado_en_mef": True, "contratista": {"veredicto": "ok"}},
          "aprobacion_expediente": {"fecha": "2022-06-18"}}
    assert cronologia.hito_resolucion(fx) is None
