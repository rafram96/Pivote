"""Estados diagnósticos de InfoObras; todo el transporte es simulado."""
from __future__ import annotations

import requests

from scraping import infoobras


class Respuesta:
    def __init__(self, texto="", status=200):
        self.text, self.status_code = texto, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


class Sesion:
    def __init__(self, respuestas):
        self.respuestas, self.headers = list(respuestas), {}

    def get(self, *args, **kwargs):
        return self.respuestas.pop(0)


def test_busqueda_vacia_reconocida_no_es_fallo(monkeypatch):
    llamadas = []
    monkeypatch.setattr(infoobras, "_crear_session", lambda: Sesion([]))
    monkeypatch.setattr(infoobras, "_buscar_por_cui",
                        lambda session, cui: llamadas.append(cui) or [])
    diagnostico = {}

    assert infoobras.fetch_by_cui("123", diagnostico=diagnostico) is None
    assert llamadas == ["123"]
    assert diagnostico["infoobras_busqueda"]["estado"] == "sin_resultados"


def test_error_de_transporte_no_se_convierte_en_busqueda_vacia(monkeypatch):
    monkeypatch.setattr(infoobras, "_crear_session", lambda: Sesion([]))

    def cae(*_args):
        raise requests.ConnectionError("portal caído")

    monkeypatch.setattr(infoobras, "_buscar_por_cui", cae)
    diagnostico = {}

    assert infoobras.fetch_by_cui("123", diagnostico=diagnostico) is None
    assert diagnostico["infoobras_busqueda"]["estado"] == "fuente_no_disponible"


def test_html_extraño_conserva_valor_legacy_y_marca_respuesta_no_reconocida():
    diagnostico = {}
    session = Sesion([Respuesta("<html><title>login</title><body>aviso</body></html>")])

    resultado = infoobras._extraer_datos_preparacion(
        session, 17, diagnostico=diagnostico)

    assert resultado == {}
    assert diagnostico["infoobras_preparacion"]["estado"] == "respuesta_no_reconocida"


def test_html_error_en_ejecucion_no_se_marca_como_con_resultados():
    diagnostico = {}
    session = Sesion([Respuesta("<html><title>login</title><body>aviso</body></html>")])

    resultado = infoobras._extraer_datos_ejecucion(
        session, 17, diagnostico=diagnostico)

    assert resultado["_modificaciones_plazo"] == []
    assert diagnostico["infoobras_ejecucion"]["estado"] == "respuesta_no_reconocida"


def test_variable_no_parseada_con_otra_valida_es_lectura_parcial():
    diagnostico = {}
    html = "<script>var lAvances = [{}]; var lSupervisor = [incompleto;</script>"
    session = Sesion([Respuesta(html)])

    infoobras._extraer_datos_ejecucion(session, 17, diagnostico=diagnostico)

    assert diagnostico["infoobras_ejecucion"]["estado"] == "respuesta_no_reconocida"
    assert "Lectura parcial" in diagnostico["infoobras_ejecucion"]["motivo"]


def test_ficha_parcial_distingue_ejecucion_disponible_de_preparacion_caida(monkeypatch):
    html_ejecucion = (
        "<html><script>var lAvances = [];</script>"
        "<title>Ficha - 17</title></html>")
    session = Sesion([
        Respuesta(html_ejecucion),
        Respuesta("<html><title>ficha</title></html>", status=503),
    ])
    diagnostico = {}

    resultado = infoobras._extraer_todos_los_datos(
        session, 17, diagnostico=diagnostico)

    assert resultado["lAvances"] == []
    assert diagnostico["infoobras_ejecucion"]["estado"] == "sin_resultados"
    assert diagnostico["infoobras_preparacion"]["estado"] == "fuente_no_disponible"


def test_id_explicito_ausente_no_sustituye_otra_ficha(monkeypatch):
    procesos = [
        {"codigoObra": 10, "codUniqInv": "123", "nombrObra": "A"},
        {"codigoObra": 11, "codUniqInv": "123", "nombrObra": "B"},
    ]
    monkeypatch.setattr(infoobras, "_crear_session", lambda: Sesion([]))
    monkeypatch.setattr(infoobras, "_buscar_por_cui", lambda *_: procesos)
    monkeypatch.setattr(infoobras.time, "sleep", lambda *_: None)
    diagnostico = {}

    assert infoobras.fetch_by_cui("123", obra_id=99, diagnostico=diagnostico) is None
    assert diagnostico["infoobras_busqueda"]["estado"] == "con_resultados"
    assert diagnostico["infoobras_seleccion"]["estado"] in {
        "identidad_pendiente", "no_seleccionado"}


def test_sumario_desconocido_no_es_ausencia_y_sumario_reconocido_vacio_si_es_ausencia():
    diag1, diag2 = {}, {}
    desconocido = Sesion([Respuesta("<html><title>login</title></html>")])
    reconocido_vacio = Sesion([Respuesta("<div>Aprobación del proyecto</div>")])

    assert infoobras._fetch_aprobacion_expediente(desconocido, 17, diag1) is None
    assert diag1["infoobras_sumario"]["estado"] == "respuesta_no_reconocida"
    assert infoobras._fetch_aprobacion_expediente(reconocido_vacio, 17, diag2) is None
    assert diag2["infoobras_sumario"]["estado"] == "sin_resultados"


def test_warmup_fallido_queda_en_busqueda(monkeypatch):
    monkeypatch.setattr(infoobras, "_crear_session",
                        lambda: (_ for _ in ()).throw(requests.ConnectionError("warmup")))
    diagnostico = {}

    assert infoobras.fetch_by_cui("123", diagnostico=diagnostico) is None
    assert diagnostico["infoobras_busqueda"]["estado"] == "fuente_no_disponible"


def test_fetcher_legacy_sigue_siendo_compatible_con_helper_diagnostico():
    llamadas = []

    def legacy(_session, _obra):
        llamadas.append(True)
        return {"lAvances": []}

    diag = {}
    resultado = infoobras._llamar_con_diagnostico(
        legacy, object(), 17, diagnostico=diag)

    assert resultado == {"lAvances": []}
    assert llamadas == [True]
    assert diag == {}
