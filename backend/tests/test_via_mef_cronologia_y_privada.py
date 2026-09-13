"""Vía MEF (ADR-010/ADR-015 §2): dos precisiones medidas en la auditoría del
12-sep, con datos sintéticos.

1. CRONOLOGÍA DEL BANCO. Dos fichas del MEF con el mismo nombre oficial empatan
   en parecido (100 y 100). Si una se registró DESPUÉS de que terminara el
   certificado, no puede ser el proyecto que ese certificado acredita: deja de
   contar como rival y la otra resuelve. Se usa la fecha más temprana entre
   registro y viabilidad (el MEF re-registra inversiones antiguas con fecha de
   registro tardía). Solo descarta rivales: una ficha anterior al certificado no
   gana por eso (ADR-013: la coincidencia no corrobora).

2. PRIVADA ANTES QUE «CONFIRMAR». Si el cliente es privado por léxico (clínica),
   la vía MEF que no resolvió devuelve PRIVADA en vez de una revisión que cita
   una ficha pública parecida.
"""
from resolucion import cui as _cui

_NOMBRE = "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL HOSPITAL DE APOYO SAN JACINTO"


def _ficha(cui, mef_score=100.0, score=120.0, registro="", viab="", nombre=_NOMBRE):
    return {"cui": cui, "mef_score": mef_score, "nombre_obra": nombre, "full": nombre,
            "score": score, "solo_ficha": True, "origen": "mef",
            "mef_fecha_registro": registro, "mef_fecha_viabilidad": viab}


def _exp(fecha_final="2009-08-28", proyecto=None, **extra):
    d = {"proyecto": proyecto or "Elaboración del Expediente Técnico del " + _NOMBRE.title(),
         "ubicacion": "San Jacinto", "fecha_inicial": "2008-08-06", "fecha_final": fecha_final}
    d.update(extra)
    return d


def _via(exp, best, ranked):
    return _cui._via_mef_expediente(exp, best, ranked, [dict(c) for c in ranked], None, False)


def test_rival_registrado_despues_del_certificado_no_compite():
    best = _ficha("2999101", registro="2007-12-17", viab="2007-12-31")
    tardio = _ficha("2999102", score=103.0, registro="2015-12-11", viab="2017-07-05",
                    nombre=_NOMBRE + " DISTRITO DE SAN JACINTO, PROVINCIA DE TUMBES")
    r = _via(_exp(), best, [best, tardio])
    assert r["estado"] == "resuelto" and r["cui"] == "2999101" and r["via"] == "MEF"


def test_rival_anterior_al_certificado_sigue_compitiendo():
    best = _ficha("2999101", registro="2007-12-17")
    rival = _ficha("2999102", score=103.0, registro="2006-03-01",
                   nombre=_NOMBRE + " - ZONA NORTE")
    r = _via(_exp(), best, [best, rival])
    assert r["estado"] == "revision" and r["cui"] is None
    assert "compite" in r["decision"]


def test_sin_fechas_en_la_carga_no_cambia_nada():
    best = _ficha("2999101")
    rival = _ficha("2999102", score=103.0, nombre=_NOMBRE + " - ZONA NORTE")
    r = _via(_exp(), best, [best, rival])
    assert r["estado"] == "revision"


def test_registro_tardio_pero_viabilidad_antigua_cuenta_como_antigua():
    # el MEF re-registró la inversión en 2018 pero fue viable en 2009: existía
    best = _ficha("2999101", registro="2007-12-17")
    rival = _ficha("2999102", score=103.0, registro="2018-08-14", viab="2009-10-15",
                   nombre=_NOMBRE + " - ZONA NORTE")
    r = _via(_exp(fecha_final="2012-05-30"), best, [best, rival])
    assert r["estado"] == "revision"


def test_certificado_sin_fecha_final_no_descarta_rivales():
    best = _ficha("2999101", registro="2007-12-17")
    tardio = _ficha("2999102", score=103.0, registro="2015-12-11",
                    nombre=_NOMBRE + " - ZONA NORTE")
    r = _via(_exp(fecha_final=None), best, [best, tardio])
    assert r["estado"] == "revision"


def test_cliente_privado_por_lexico_devuelve_privada_y_no_confirmar():
    exp = _exp(proyecto="Ampliación y remodelación de los bloques B y C de la Clínica San Bartolo",
               entidad_contratante="Inversiones Salud Total S.A.")
    ficha = _ficha("2999201", mef_score=80.0, score=80.0,
                   nombre="REMODELACION Y AMPLIACION DE PLANTA DE BOMBEO")
    r = _via(exp, ficha, [ficha])
    assert r["estado"] == "na" and r["via"] == "PRIVADA"


def test_cliente_publico_conserva_la_revision_de_la_via_mef():
    exp = _exp(proyecto="Ampliación y remodelación del Centro de Salud San Bartolo",
               entidad_contratante="Municipalidad Distrital de San Bartolo")
    ficha = _ficha("2999201", mef_score=80.0, score=80.0,
                   nombre="REMODELACION Y AMPLIACION DE PLANTA DE BOMBEO")
    r = _via(exp, ficha, [ficha])
    assert r["estado"] == "revision" and r["via"] == "NOMBRE"
