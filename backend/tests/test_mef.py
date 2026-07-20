"""
Tests offline de la verificación de expedientes contra el MEF (scraping/mef.py).
Funciones puras contra los fixtures congelados en tests/fixtures/mef/ (data pública
del Banco de Inversiones). Sin red: los fetch/descarga NO se ejercitan aquí.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scraping import mef

FIX = Path(__file__).parent / "fixtures" / "mef"


def _html(cui):
    return (FIX / f"{cui}_ficha08a.html").read_text(encoding="utf-8")


def _contratos(cui):
    return json.loads((FIX / f"{cui}_contratos.json").read_text(encoding="utf-8"))


# ── helpers puros ────────────────────────────────────────────────────────────

def test_num_formato_peruano_y_json():
    assert mef._num("S/. 21,676,278.41") == 21676278.41
    assert mef._num(612750) == 612750.0
    assert mef._num("19757801.59") == 19757801.59
    assert mef._num(None) is None and mef._num("") is None


def test_fecha_ddmmyyyy():
    assert mef._fecha("19/10/2017") == date(2017, 10, 19)
    assert mef._fecha("26/07/2017 00:00:00") == date(2017, 7, 26)
    assert mef._fecha("") is None and mef._fecha("2017-10-19") is None


def test_nombres_coinciden_ignora_sufijos_societarios():
    assert mef._nombres_coinciden("VELASQUEZ VASQUEZ EMILIO FELIX",
                                  "Velásquez Vásquez Emilio Félix")
    assert mef._nombres_coinciden("CONSTRUCTORA & CONSULTORA SAHMAT S.R.L.",
                                  "SAHMAT SOCIEDAD COMERCIAL")
    assert not mef._nombres_coinciden("CONSORCIO PUERTO INCA", "CONSORCIO D&D")
    assert not mef._nombres_coinciden("", "ALGO")


# ── parseo del 08-A ──────────────────────────────────────────────────────────

def test_parsear_08a_completo():
    f = mef.parsear_ficha_08a(_html("2324482"))
    assert f["tiene_ficha"] is True
    assert f["seccion_b"] is True
    assert f["costo_total"] == 21676278.41
    # el 08-A trae documentos, y al menos uno es la resolución de aprobación
    assert f["documentos"], "debería listar documentos descargables"
    assert f["resolucion"] is not None
    # el candidato elegido debe verse como resolución (número con dígitos)
    assert f["resolucion"]["numero"] and any(ch.isdigit() for ch in f["resolucion"]["numero"])
    # y la R.G.R 121-2019 (aprobación original) debe estar entre los documentos vistos
    assert any("121-2019" in d["label"] for d in f["documentos"])


def test_parsear_08a_flaco_no_revienta():
    # entidad que no llenó el 08-A → parser no lanza, marca ficha pobre
    f = mef.parsear_ficha_08a(_html("2148076"))
    assert f["seccion_b"] is False
    assert f["resolucion"] is None


def test_documentos_08a_descarta_ruido():
    # los enlaces con idArchivo/etiqueta vacíos NO deben colarse
    f = mef.parsear_ficha_08a(_html("2324482"))
    for d in f["documentos"]:
        assert d["label"].strip() and "idArchivo=&" not in d["url"]


# ── contratos SEACE (DWH) ────────────────────────────────────────────────────

def test_normalizar_contratos_dedup_y_campos():
    cs = mef.normalizar_contratos(_contratos("2324482"))
    # el DWH repite filas (071-2019 y 012-2019 x2) → tras dedup, menos
    numeros = [c["numero"] for c in cs]
    assert len(numeros) == len(set((c["numero"], c["monto"]) for c in cs))
    # el contrato de elaboración del expediente (Velásquez, S/612,750)
    vel = next(c for c in cs if "116-2017" in c["numero"])
    assert "VELASQUEZ" in vel["contratista"].upper()
    assert vel["monto"] == 612750.0
    assert vel["fecha_suscripcion"] == date(2017, 10, 19)
    assert vel["url_pdf"] and vel["url_pdf"].startswith("http")


def test_contrato_de_expediente_elige_elaboracion_no_supervision():
    cs = mef.normalizar_contratos(_contratos("2324482"))
    c = mef.contrato_de_expediente(cs)
    assert c is not None
    # debe ser la ELABORACIÓN (Velásquez 116-2017), no la supervisión (SAHMAT 074)
    assert "116-2017" in c["numero"]
    assert "VELASQUEZ" in c["contratista"].upper()


# ── contraste completo (el bloque que consume el backend) ────────────────────

def test_verificar_expediente_match_positivo():
    # el certificado de Yuyapichis lo emite el propio Ing. Velásquez → contratista OK
    exp = {"cui": "2324482", "nombre_emisor": "Emilio Félix Velásquez Vásquez",
           "proyecto": "Elaboración del Expediente Técnico del C.S. Yuyapichis",
           "fecha_inicial": "2017-10-19", "fecha_final": "2019-04-04"}
    b = mef.verificar_expediente(exp, mef.parsear_ficha_08a(_html("2324482")),
                                 mef.normalizar_contratos(_contratos("2324482")))
    assert b["cui_confirmado"] == "2324482"
    assert b["verificado_en_mef"] is True
    assert b["contratista"]["veredicto"] == "ok"          # Velásquez == Velásquez
    assert "116-2017" in b["contrato"]["numero"]
    assert b["contrato"]["monto"] == 612750.0
    assert b["resolucion"]["veredicto"] == "ok"
    assert set(b["fuentes"]) == {"MEF-SEACE", "MEF-08A"}


def test_verificar_expediente_contratista_no_cotejable():
    # emisor que no coincide con ningún contratista → no_verificable (NO discrepancia)
    exp = {"cui": "2324482", "nombre_emisor": "OTRA EMPRESA DISTINTA SAC"}
    b = mef.verificar_expediente(exp, mef.parsear_ficha_08a(_html("2324482")),
                                 mef.normalizar_contratos(_contratos("2324482")))
    assert b["contratista"]["veredicto"] == "no_verificable"
    assert b["contrato"]["veredicto"] == "ok"   # el contrato igual existe en el MEF


def test_verificar_expediente_sin_datos_degrada():
    # CUI cuya entidad no cargó nada → todo no_verificable, sin lanzar
    exp = {"cui": "2148076", "nombre_emisor": "X"}
    b = mef.verificar_expediente(exp, mef.parsear_ficha_08a(_html("2148076")),
                                 mef.normalizar_contratos(_contratos("2148076")))
    assert b["verificado_en_mef"] is False
    assert b["resolucion"]["veredicto"] == "no_verificable"
    assert "detalle" in b
