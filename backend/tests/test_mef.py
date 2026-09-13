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
    # Desde el 13-sep-2026 la aprobación se toma de la SECCIÓN B del 08-A
    # («Expediente técnico o documento equivalente»), no del acto que «más se
    # ve» como resolución en la lista plana: en esta ficha la fila de la
    # sección B enlaza «APROBACIÓN DEL EXP. TEC,» (sin número) y la R.G.R
    # 121-2019 vive en la sección C (liquidación).
    assert f["resolucion"]["origen"] == "seccion_b"
    assert f["resolucion"]["documento"].startswith("APROBACIÓN DEL EXP")
    # y la R.G.R 121-2019 debe seguir entre los documentos vistos, en la sección C
    assert any("121-2019" in d["label"] and d["seccion"] == "C" for d in f["documentos"])


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


def test_verificar_expediente_coteja_empresa_y_separa_firmante():
    """Un gerente firma, pero la razón social es quien contrató con el Estado."""
    exp = {
        "cui": "2324482",
        "entidad_emisora": "VELÁSQUEZ VÁSQUEZ EMILIO FÉLIX",
        "ruc_emisor": "10123456789",
        "nombre_emisor": "MARÍA REPRESENTANTE DISTINTA",
        "cargo_emisor": "Gerente General",
    }
    b = mef.verificar_expediente(
        exp, mef.parsear_ficha_08a(_html("2324482")),
        mef.normalizar_contratos(_contratos("2324482")),
    )

    assert b["contratista"]["veredicto"] == "ok"
    assert b["contratista"]["declarado"] == "VELÁSQUEZ VÁSQUEZ EMILIO FÉLIX"
    assert b["emisor_certificado"] == {
        "empresa": "VELÁSQUEZ VÁSQUEZ EMILIO FÉLIX",
        "ruc": "10123456789",
        "firmante": "MARÍA REPRESENTANTE DISTINTA",
        "cargo_firmante": "Gerente General",
    }


def test_verificar_expediente_contratista_no_cotejable():
    # emisor que no coincide con ningún contratista → no_verificable (NO discrepancia)
    exp = {"cui": "2324482", "nombre_emisor": "OTRA EMPRESA DISTINTA SAC"}
    b = mef.verificar_expediente(exp, mef.parsear_ficha_08a(_html("2324482")),
                                 mef.normalizar_contratos(_contratos("2324482")))
    assert b["contratista"]["veredicto"] == "no_verificable"
    # el contrato existe en el MEF, pero eso no lo vincula con ESTE certificado:
    # el veredicto del contrato sigue al del contratista (antes decía «ok» por
    # mera existencia y el Excel lo pintaba como ✔ Coincide).
    assert b["contrato"]["veredicto"] == "no_verificable"
    assert b["contrato"]["numero"]


def test_verificar_expediente_sin_datos_degrada():
    # CUI cuya entidad no cargó nada → todo no_verificable, sin lanzar
    exp = {"cui": "2148076", "nombre_emisor": "X"}
    b = mef.verificar_expediente(exp, mef.parsear_ficha_08a(_html("2148076")),
                                 mef.normalizar_contratos(_contratos("2148076")))
    assert b["verificado_en_mef"] is False
    assert b["resolucion"]["veredicto"] == "no_verificable"
    assert "detalle" in b


# ── elección del contrato cuando el CUI tiene VARIOS de expediente ───────────
# (5-sep-2026) Un CUI puede tener varios contratos de elaboración, cada uno con
# distinto contratista. La ficha mostraba siempre el más barato aunque fuera de
# otra empresa, y el Excel lo rotulaba «Por confirmar» pese a que la experiencia
# ya estaba resuelta por el contrato del emisor. Nombres FICTICIOS.

def _c(numero, contratista, monto, objeto="ELABORACION DEL EXPEDIENTE TECNICO DEL PROYECTO"):
    return {"numero": numero, "contratista": contratista, "monto": monto, "objeto": objeto,
            "nomenclatura": "", "fecha_suscripcion": date(2022, 3, 15),
            "valor_referencial": None, "url_pdf": None}


DOS_CONTRATOS = [
    _c("13-2022", "CONSULTORA ANDINA DEL SUR S.A.C.", 100_000.0),      # el más barato
    _c("01-2022", "GRUPO PROYECTA INGENIEROS E.I.R.L.", 250_000.0),    # el del emisor
]


def test_verificar_expediente_prefiere_el_contrato_del_emisor_aunque_no_sea_el_barato():
    exp = {"cui": "2999001", "entidad_emisora": "GRUPO PROYECTA INGENIEROS EIRL"}
    b = mef.verificar_expediente(exp, {}, DOS_CONTRATOS)
    assert b["contrato"]["numero"] == "01-2022"
    assert b["contrato"]["elegido_por"] == "emisor"
    # «coincide» para el evaluador: el Excel mapea "ok" → ✔ Coincide
    assert b["contrato"]["veredicto"] == "ok"
    assert b["contratista"]["veredicto"] == "ok"
    assert b["contrato"]["otros_contratos_expediente"] == [
        "13-2022 — CONSULTORA ANDINA DEL SUR S.A.C."]
    assert b["contrato"]["monto"] == 250_000.0
    assert b["contrato"]["fecha"] == "2022-03-15"


def test_verificar_expediente_sin_emisor_coincidente_conserva_el_mas_barato():
    exp = {"cui": "2999001", "entidad_emisora": "OTRA FIRMA TOTALMENTE DISTINTA"}
    b = mef.verificar_expediente(exp, {}, DOS_CONTRATOS)
    assert b["contrato"]["numero"] == "13-2022"          # exactamente lo de antes
    assert b["contrato"]["elegido_por"] == "mas_barato"
    assert b["contrato"]["veredicto"] == "no_verificable"
    assert b["contrato"]["otros_contratos_expediente"] == [
        "01-2022 — GRUPO PROYECTA INGENIEROS E.I.R.L."]


def test_verificar_expediente_con_un_solo_contrato_dice_unico():
    exp = {"cui": "2999001", "entidad_emisora": "OTRA FIRMA TOTALMENTE DISTINTA"}
    b = mef.verificar_expediente(exp, {}, [DOS_CONTRATOS[0]])
    assert b["contrato"]["elegido_por"] == "unico"
    assert b["contrato"]["otros_contratos_expediente"] == []
    assert b["contrato"]["veredicto"] == "no_verificable"


# ── CacheMef: ficha y contratos por CUI durante una corrida ──────────────────

class _SesionMuda:
    headers: dict = {}


def _parchear_get(monkeypatch, respuestas):
    """`respuestas[url_final]` → objeto con .text/.json() o None (portal caído)."""
    from scraping import mef as m
    llamadas = []

    class _R:
        def __init__(self, cuerpo):
            self.text = cuerpo if isinstance(cuerpo, str) else ""
            self._cuerpo = cuerpo

        def json(self):
            return self._cuerpo

    def _get(session, url, **kw):
        clave = "contratos:" + kw.get("data", {}).get("id", "") if kw.get("metodo") == "POST" else url[-7:]
        llamadas.append(clave)
        r = respuestas.get(clave)
        return None if r is None else _R(r)

    monkeypatch.setattr(m, "_get", _get)
    return llamadas


def test_cache_mef_no_repite_ficha_ni_contratos(monkeypatch):
    from scraping.mef import CacheMef, fetch_contratos, fetch_ficha_08a
    html = "<html>ETAPA: EJECUCIÓN ESTADO: ACTIVO</html>"
    llamadas = _parchear_get(monkeypatch, {"2331865": html,
                                           "contratos:2331865": [{"n": 1}]})
    c = CacheMef(session=_SesionMuda())
    assert fetch_ficha_08a("2331865", cache=c) == html
    assert fetch_ficha_08a("2331865", cache=c) == html
    assert fetch_contratos("2331865", "", cache=c) == [{"n": 1}]
    assert fetch_contratos("2331865", "0", cache=c) == [{"n": 1}]     # codsnip "" ≡ "0"
    assert llamadas == ["2331865", "contratos:2331865"]
    assert c.peticiones == 2 and c.aciertos == 2
    assert "2 peticiones, 2 reutilizadas" in c.resumen()


def test_cache_mef_recuerda_el_portal_caido_solo_un_rato_y_por_recurso(monkeypatch):
    """Un fallo de ficha no presume caída de contratos (revisión de Codex, 7-sep)."""
    from scraping.mef import CacheMef, fetch_contratos, fetch_ficha_08a
    llamadas = _parchear_get(monkeypatch, {"contratos:2280509": [{"n": 1}]})   # ficha: None
    reloj = {"t": 0.0}
    c = CacheMef(session=_SesionMuda(), ttl_fallo=120.0, reloj=lambda: reloj["t"])
    assert fetch_ficha_08a("2280509", cache=c) is None
    assert fetch_ficha_08a("2280509", cache=c) is None   # dentro del TTL: sin red
    assert fetch_contratos("2280509", cache=c) == [{"n": 1}]   # contratos SÍ se consultan
    assert llamadas == ["2280509", "contratos:2280509"] and c.evitadas_por_fallo == 1
    reloj["t"] = 121.0
    assert fetch_ficha_08a("2280509", cache=c) is None   # pasado el TTL: reintenta
    assert llamadas == ["2280509", "contratos:2280509", "2280509"]


def test_cache_mef_no_convierte_respuesta_invalida_en_sin_contratos(monkeypatch):
    """HTML de error o JSON de otra forma = fallo con TTL, nunca «[]» permanente."""
    from scraping import mef as m
    from scraping.mef import CacheMef, fetch_contratos
    respuestas = {"contratos:2331865": "<html>mantenimiento</html>"}   # r.json() → str
    llamadas = _parchear_get(monkeypatch, respuestas)
    reloj = {"t": 0.0}
    c = CacheMef(session=_SesionMuda(), ttl_fallo=120.0, reloj=lambda: reloj["t"])
    assert fetch_contratos("2331865", cache=c) == []
    assert fetch_contratos("2331865", cache=c) == []        # fallo recordado, sin red
    assert llamadas == ["contratos:2331865"] and c.evitadas_por_fallo == 1
    respuestas["contratos:2331865"] = [{"n": 7}]             # el servicio se recupera
    reloj["t"] = 121.0
    assert fetch_contratos("2331865", cache=c) == [{"n": 7}]
    assert fetch_contratos("2331865", cache=c) == [{"n": 7}]   # ahora sí es dato cacheado
    assert llamadas == ["contratos:2331865", "contratos:2331865"]
    # sin caché, el llamador sigue recibiendo la lista
    assert m.fetch_contratos("2331865", "", _SesionMuda()) == [{"n": 7}]


def test_sin_cache_las_funciones_siguen_igual(monkeypatch):
    from scraping.mef import fetch_contratos, fetch_ficha_08a
    _parchear_get(monkeypatch, {"contratos:2331865": [{"n": 1}]})
    assert fetch_ficha_08a("2331865", _SesionMuda()) is None
    assert fetch_contratos("2331865", "", _SesionMuda()) == [{"n": 1}]
    assert fetch_contratos("9999999", "", _SesionMuda()) == []
