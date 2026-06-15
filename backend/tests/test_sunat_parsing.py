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
