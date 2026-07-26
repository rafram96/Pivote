"""
Tests offline del parseo SUNAT — corren contra los dumps HTML reales
(backend/exploracion/_sunat_dump/, RUC 20304582147 = Inmobiliaria Alpamayo,
dato público del portal).

Objetivo: que "SUNAT cambió el HTML" sea un test rojo aquí, no un bug
silencioso en producción. Ningún test toca la red.
"""
from __future__ import annotations

from datetime import date

from scraping import sunat


# ── Parseo de detalle (consPorRuc) contra dump real ─────────────────────────

def test_parse_detalle_dump_real(dump_sunat):
    # 01_consPorRuc.html = página de detalle del RUC (la búsqueda por RUC
    # devuelve el detalle directo; 03_*.html quedó vacío en la exploración)
    raw = sunat._parse_detalle(dump_sunat("01_consPorRuc.html"))

    assert raw.get("Número de RUC", "").startswith("20304582147")
    assert "INMOBILIARIA ALPAMAYO" in raw.get("Número de RUC", "")
    assert sunat._parse_fecha_sunat(raw.get("Fecha de Inscripción")) is not None
    assert raw.get("Estado del Contribuyente")
    assert raw.get("Domicilio Fiscal")
    assert len(raw.get("Actividades Económicas", [])) >= 1


def test_parse_lista_dump_real(dump_sunat):
    items = sunat._parse_lista(dump_sunat("02_consPorRazonSoc.html"))

    assert len(items) >= 5, "la búsqueda 'Inmobiliaria Alpamayo' trae ≥5 candidatos"
    rucs = {i["ruc"] for i in items}
    assert "20304582147" in rucs
    assert all(len(i["ruc"]) == 11 and i["ruc"].isdigit() for i in items)
    assert all(i.get("razon_social") for i in items)


# ── Representantes legales (getRepLeg, insumo ALT12) ─────────────────────────

def test_parse_representantes_dump_real(dump_sunat):
    reps = sunat._parse_representantes(dump_sunat("25_getRepLeg.html"))

    assert len(reps) == 1
    rep = reps[0]
    assert rep.tipo_documento == "DNI"
    assert rep.nro_documento == "09683058"
    assert "ACHANCARAY GONZALES MARIO" in rep.nombre
    assert rep.cargo == "GERENTE GENERAL"
    assert rep.fecha_desde == date(2017, 5, 24)


def test_parse_representantes_html_sin_tabla():
    assert sunat._parse_representantes("<html><body>nada</body></html>") == []


# ── Información histórica (getinfHis) ───────────────────────────────────────
# Dumps del sondeo del issue #30: _rico = con cambios de razón social y muchos
# tramos de condición · _vacio = "No hay Información" en las tres tablas ·
# _error = RUC inexistente (el portal devuelve su página de error genérica).

def test_parse_historico_dump_rico(dump_sunat):
    h = sunat._parse_historico(dump_sunat("30_getinfHis_rico.html"), "20573023481")

    assert [r["nombre"] for r in h.razones_sociales] == [
        "JOGAMA CONSULTORIAS Y CONSTRUCCIONES GENERALES E.I.R.L"] * 2
    assert h.razones_sociales[0]["fecha_baja"] == "2018-03-13"

    assert len(h.condiciones) >= 20, "el histórico de condición trae muchos tramos"
    primero = h.condiciones[0]
    assert primero.condicion == "PENDIENTE"
    assert primero.desde is None, "'-' en Fecha Desde = extremo abierto"
    assert primero.hasta == date(2013, 1, 23)
    # el portal usa más estados que HABIDO/NO HABIDO
    assert {"NO HALLADO", "POR VERIFICAR"} <= {t.condicion for t in h.condiciones}

    assert len(h.domicilios) == 2
    # el portal antepone guiones a algunas direcciones; el parser los limpia
    assert all(not d["direccion"].startswith("-") for d in h.domicilios)
    assert h.domicilios[0]["fecha_baja"] == "2015-09-16"


def test_parse_historico_dump_vacio(dump_sunat):
    # las tres tablas existen pero dicen "No hay Información" → histórico vacío,
    # NO un fallo de parseo
    h = sunat._parse_historico(dump_sunat("30_getinfHis_vacio.html"), "20600789911")
    assert h.vacio()
    assert h.to_dict()["condiciones"] == []


def test_parse_historico_pagina_error(dump_sunat):
    # RUC inexistente: la página de error no tiene tablas → nada que parsear
    h = sunat._parse_historico(dump_sunat("30_getinfHis_error.html"), "20607105615")
    assert h.vacio()


# ── ¿Estaba HABIDO al emitir el certificado y durante la obra? ───────────────

def _tramos(*filas):
    return [sunat.TramoCondicion(c, d, h) for c, d, h in filas]


def test_condicion_en_fecha_dentro_y_fuera_del_historico():
    tramos = _tramos(
        ("HABIDO", None, date(2013, 1, 23)),
        ("NO HABIDO", date(2013, 1, 24), date(2014, 5, 24)),
        ("HABIDO", date(2014, 5, 25), date(2018, 3, 13)),
    )
    assert sunat.condicion_en_fecha(tramos, date(2012, 6, 1)) == "HABIDO"
    assert sunat.condicion_en_fecha(tramos, date(2013, 6, 1)) == "NO HABIDO"
    # posterior al último tramo → cae en la condición actual de la ficha
    assert sunat.condicion_en_fecha(tramos, date(2020, 1, 1),
                                    condicion_actual="HABIDO") == "HABIDO"
    # ...y sin condición actual no se puede afirmar nada
    assert sunat.condicion_en_fecha(tramos, date(2020, 1, 1)) is None


def test_condicion_en_fecha_tramos_del_mismo_dia_gana_el_ultimo():
    # caso real (BCP): alta y baja el mismo día, dos filas que se pisan
    tramos = _tramos(("NO HALLADO", date(2017, 12, 20), date(2017, 12, 20)),
                     ("HABIDO", date(2017, 12, 20), date(2017, 12, 20)))
    assert sunat.condicion_en_fecha(tramos, date(2017, 12, 20)) == "HABIDO"


def test_evaluar_habido_emision_y_periodo_limpios():
    tramos = _tramos(("HABIDO", None, date(2020, 12, 31)))
    r = sunat.evaluar_habido(tramos, fecha_emision=date(2019, 5, 10),
                             ini=date(2018, 1, 1), fin=date(2019, 4, 30))
    assert r["emision"]["ok"] is True and r["emision"]["condicion"] == "HABIDO"
    assert r["periodo"]["ok"] is True
    assert r["periodo"]["tramos_no_habido"] == []


def test_evaluar_habido_detecta_el_tramo_malo_dentro_de_la_obra():
    tramos = _tramos(
        ("HABIDO", None, date(2018, 6, 30)),
        ("NO HABIDO", date(2018, 7, 1), date(2018, 9, 30)),
        ("HABIDO", date(2018, 10, 1), date(2021, 1, 1)),
    )
    r = sunat.evaluar_habido(tramos, fecha_emision=date(2019, 2, 1),
                             ini=date(2018, 1, 1), fin=date(2018, 12, 31))
    assert r["emision"]["ok"] is True          # al emitir ya estaba habido
    assert r["periodo"]["ok"] is False         # pero durante la obra, no
    malos = r["periodo"]["tramos_no_habido"]
    assert len(malos) == 1
    assert malos[0]["condicion"] == "NO HABIDO"
    # el tramo se reporta recortado al periodo de la experiencia
    assert malos[0]["desde"] == "2018-07-01" and malos[0]["hasta"] == "2018-09-30"


def test_evaluar_habido_sin_datos_no_inventa_veredicto():
    r = sunat.evaluar_habido([], fecha_emision=date(2019, 1, 1),
                             ini=date(2018, 1, 1), fin=date(2018, 12, 31))
    assert r["emision"]["ok"] is None
    assert r["periodo"]["ok"] is None


def test_evaluar_habido_cobertura_parcial_no_da_verde():
    """El hueco del review (H2): un tramo HABIDO que TOCA el periodo no dice nada
    del resto. Histórico que muere en dic-2018, periodo hasta dic-2019 y ficha sin
    condición actual → todo 2019 sin dato: ok=None, jamás True."""
    tramos = _tramos(("HABIDO", None, date(2018, 12, 31)))
    r = sunat.evaluar_habido(tramos, ini=date(2018, 1, 1), fin=date(2019, 12, 31))
    per = r["periodo"]
    assert per["ok"] is None
    assert per["sin_dato"] == [{"desde": "2019-01-01", "hasta": "2019-12-31"}]


def test_evaluar_habido_hueco_intermedio_no_da_verde():
    tramos = _tramos(("HABIDO", None, date(2018, 6, 30)),
                     ("HABIDO", date(2018, 9, 1), date(2019, 12, 31)))
    r = sunat.evaluar_habido(tramos, ini=date(2018, 1, 1), fin=date(2018, 12, 31))
    per = r["periodo"]
    assert per["ok"] is None
    assert per["sin_dato"] == [{"desde": "2018-07-01", "hasta": "2018-08-31"}]


def test_evaluar_habido_no_habido_gana_aunque_haya_huecos():
    """Un NO HABIDO dentro del periodo es veredicto duro (eso SÍ se sabe), con o
    sin días sin dato alrededor."""
    tramos = _tramos(("NO HABIDO", date(2018, 3, 1), date(2018, 5, 31)))
    r = sunat.evaluar_habido(tramos, ini=date(2018, 1, 1), fin=date(2018, 12, 31))
    assert r["periodo"]["ok"] is False
    assert r["periodo"]["sin_dato"]          # los huecos quedan reportados igual


def test_evaluar_habido_cobertura_completa_sigue_dando_verde():
    tramos = _tramos(("HABIDO", None, None))
    r = sunat.evaluar_habido(tramos, ini=date(2018, 1, 1), fin=date(2019, 12, 31))
    assert r["periodo"]["ok"] is True and r["periodo"]["sin_dato"] == []


def test_evaluar_habido_periodo_posterior_al_historico_usa_condicion_actual():
    # experiencia posterior al último tramo: manda la condición de la ficha
    tramos = _tramos(("NO HABIDO", None, date(2015, 1, 1)))
    r = sunat.evaluar_habido(tramos, ini=date(2018, 1, 1), fin=date(2018, 12, 31),
                             condicion_actual="HABIDO")
    assert r["periodo"]["ok"] is True
    assert r["periodo"]["condiciones"] == ["HABIDO"]


# ── Diagnóstico de página anómala (captcha real / cambio de estructura) ─────

def test_diagnostico_dump_real_es_estructura_conocida(dump_sunat):
    assert sunat.diagnosticar_html_sunat(dump_sunat("01_consPorRuc.html")) is None
    assert sunat.diagnosticar_html_sunat(dump_sunat("02_consPorRazonSoc.html")) is None


def test_diagnostico_captcha_real():
    html = (
        '<html><body><form><div class="g-recaptcha" '
        'data-sitekey="6LeXXX"></div></form></body></html>'
    )
    assert sunat.diagnosticar_html_sunat(html) == "captcha_real"


def test_diagnostico_estructura_desconocida():
    assert sunat.diagnosticar_html_sunat("<html><body><h1>SUNAT 2.0</h1></body></html>") \
        == "estructura_desconocida"
    assert sunat.diagnosticar_html_sunat("") == "estructura_desconocida"


def test_diagnostico_ruc_inexistente():
    # respuesta NORMAL del portal para un RUC que no existe (caso 20607105615)
    html = ("<html><body><strong> El número de RUC 20607105615 consultado no es "
            "válido. Debe verificar el número y volver a ingresar. </strong></body></html>")
    assert sunat.diagnosticar_html_sunat(html) == "ruc_inexistente"


def test_diagnostico_no_enmascara_problemas_con_substrings_amplias():
    # una frase legítima como "no registra operaciones" NO debe clasificarse como
    # ruc_inexistente (anclamos a "no es válido", no a "no registr").
    assert sunat.diagnosticar_html_sunat(
        "<html><body>El contribuyente no registra operaciones</body></html>") \
        == "estructura_desconocida"
    # captcha gana aunque la página contenga una frase genérica
    captcha = ('<html><body>no registra representantes'
               '<div class="g-recaptcha" data-sitekey="x"></div></body></html>')
    assert sunat.diagnosticar_html_sunat(captcha) == "captcha_real"


# ── Helpers puros ────────────────────────────────────────────────────────────

def test_parse_fecha_sunat_formatos():
    esperado = date(2010, 6, 15)
    assert sunat._parse_fecha_sunat("15.06.2010") == esperado
    assert sunat._parse_fecha_sunat("15/06/2010") == esperado
    assert sunat._parse_fecha_sunat("15-06-2010") == esperado


def test_parse_fecha_sunat_invalidas():
    assert sunat._parse_fecha_sunat(None) is None
    assert sunat._parse_fecha_sunat("") is None
    assert sunat._parse_fecha_sunat("-") is None
    assert sunat._parse_fecha_sunat("basura") is None
    assert sunat._parse_fecha_sunat("99.99.2010") is None


def test_normalizar_nombre_empresa():
    f = sunat.normalizar_nombre_empresa
    assert f("INSTITUTO DE CONSULTORÍA S.A.C.") == "INSTITUTO DE CONSULTORIA"
    assert f("INDECONSULT  E.I.R.L.") == "INDECONSULT"
    assert f("Constructora Ñawi S.R.L.") == "CONSTRUCTORA NAWI"
    assert f("ALPAMAYO SOCIEDAD ANONIMA CERRADA") == "ALPAMAYO"
    assert f("") == ""


def test_score_match_empresa():
    # Misma empresa, distinto sufijo legal → match fuerte
    assert sunat.score_match_empresa(
        "INMOBILIARIA ALPAMAYO", "INMOBILIARIA ALPAMAYO S.A.") >= 85
    # Empresas distintas → mismatch
    assert sunat.score_match_empresa(
        "INMOBILIARIA ALPAMAYO", "CONSTRUCTORA TRUJILLO INGENIEROS") < 70
    # Vacíos → 0
    assert sunat.score_match_empresa("", "ALPAMAYO") == 0


def test_fake_captcha_token_largo():
    assert len(sunat._fake_captcha_token()) == 52
