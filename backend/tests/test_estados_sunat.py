from __future__ import annotations

import pytest

from scraping import sunat


class _Respuesta:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self.content = text.encode()
        self.encoding = "utf-8"


class _Sesion:
    def close(self):
        pass


def test_busqueda_legacy_y_diagnostico_explicito(monkeypatch):
    monkeypatch.setattr(sunat, "_request_with_retry", lambda *a, **k: _Respuesta(text="No se encontraron resultados"))
    diagnostico = {}
    assert sunat.buscar_por_razon_social("ACME", session=_Sesion(), diagnostico=diagnostico) == []
    assert diagnostico["estado"] == "sin_resultados"
    assert sunat.buscar_por_razon_social("ACME", session=_Sesion()) == []


def test_busqueda_http_y_html_extraño_no_son_sin_resultados(monkeypatch):
    respuestas = iter([_Respuesta(503), _Respuesta(200, "<html>login captcha desconocido</html>"),
                        _Respuesta(200, "<html>login captcha desconocido</html>")])
    monkeypatch.setattr(sunat, "_request_with_retry", lambda *a, **k: next(respuestas))
    d1, d2 = {}, {}
    assert sunat.buscar_por_razon_social("ACME", session=_Sesion(), diagnostico=d1) == []
    assert d1["estado"] == "fuente_no_disponible"
    assert sunat.buscar_por_razon_social("ACME", session=_Sesion(), diagnostico=d2) == []
    assert d2["estado"] == "respuesta_no_reconocida"


def test_busqueda_exitoso_conserva_lista_y_marca_resultado(monkeypatch):
    monkeypatch.setattr(sunat, "_request_with_retry", lambda *a, **k: _Respuesta())
    monkeypatch.setattr(sunat, "_parse_lista", lambda html: [{"ruc": "20123456789", "razon_social": "ACME"}])
    d = {}
    assert sunat.buscar_por_razon_social("ACME", session=_Sesion(), diagnostico=d)[0]["ruc"] == "20123456789"
    assert d["estado"] == "con_resultados"


def test_ruc_legacy_none_y_diagnostico_de_fuente(monkeypatch):
    monkeypatch.setattr(sunat, "_request_with_retry", lambda *a, **k: _Respuesta(504))
    d = {}
    assert sunat.consultar_ruc("20123456789", session=_Sesion(), diagnostico=d) is None
    assert d["estado"] == "fuente_no_disponible"


def test_ruc_exitoso_marca_resultado(monkeypatch):
    monkeypatch.setattr(sunat, "_request_with_retry", lambda *a, **k: _Respuesta())
    monkeypatch.setattr(sunat, "_parse_detalle", lambda html: {"Número de RUC": "20123456789 - ACME"})
    d = {}
    empresa = sunat.consultar_ruc("20123456789", session=_Sesion(), diagnostico=d)
    assert empresa.ruc == "20123456789" and d["estado"] == "con_resultados"


def test_ruc_invalido_sigue_lanzando_value_error():
    with pytest.raises(ValueError):
        sunat.consultar_ruc("123", diagnostico={})
