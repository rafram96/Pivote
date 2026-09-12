from scraping import mef
import pytest


class _Sesion:
    headers = {}


class _Respuesta:
    def __init__(self, cuerpo):
        self.text = cuerpo if isinstance(cuerpo, str) else ""
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


def _get_fake(monkeypatch, respuestas):
    def fake(_session, url, **kw):
        if kw.get("metodo") == "POST":
            return _Respuesta(respuestas.get("contratos"))
        return _Respuesta(respuestas.get("ficha")) if "ficha" in respuestas else None
    monkeypatch.setattr(mef, "_get", fake)


def test_ficha_vacia_no_se_confunde_con_fallo(monkeypatch):
    _get_fake(monkeypatch, {"ficha": "", "contratos": []})
    f, c = {}, {}
    assert mef.fetch_ficha_08a("1", _Sesion(), diagnostico=f) == ""
    assert f["estado"] == "respuesta_no_reconocida"
    assert mef.fetch_contratos("1", "", _Sesion(), diagnostico=c) == []
    assert c["estado"] == "sin_resultados"


def test_ficha_08a_reconocida_con_datos_es_con_resultados(monkeypatch):
    _get_fake(monkeypatch, {
        "ficha": "<html>ETAPA: EJECUCIÓN ESTADO: ACTIVO</html>",
        "contratos": [],
    })
    d = {}
    mef.fetch_ficha_08a("1", _Sesion(), diagnostico=d)
    assert d["estado"] == "con_resultados"


def test_json_invalido_y_fallo_de_transporte_son_diagnosticables(monkeypatch):
    _get_fake(monkeypatch, {"ficha": "mantenimiento", "contratos": {"error": 1}})
    f, c = {}, {}
    mef.fetch_ficha_08a("1", _Sesion(), diagnostico=f)
    mef.fetch_contratos("1", "", _Sesion(), diagnostico=c)
    assert f["estado"] == "respuesta_no_reconocida"
    assert c["estado"] == "respuesta_no_reconocida"

    monkeypatch.setattr(mef, "_get", lambda *_a, **_k: None)
    d = {}
    assert mef.fetch_ficha_08a("2", _Sesion(), diagnostico=d) is None
    assert d["estado"] == "fuente_no_disponible"


def test_json_value_error_es_respuesta_no_reconocida(monkeypatch):
    class _RespuestaMala(_Respuesta):
        def json(self):
            raise ValueError("HTML")

    monkeypatch.setattr(mef, "_get", lambda *_a, **_k: _RespuestaMala(""))
    d = {}
    assert mef.fetch_contratos("1", "", _Sesion(), diagnostico=d) == []
    assert d["estado"] == "respuesta_no_reconocida"


def test_verificar_cui_agrega_consultas_sin_contaminar_entrada(monkeypatch):
    _get_fake(monkeypatch, {"ficha": "", "contratos": []})
    exp = {"cui": "123", "entidad_emisora": "Empresa"}
    original = dict(exp)
    salida = mef.verificar_cui(exp, "123", session=_Sesion())
    assert exp == original
    assert salida["consultas_fuentes"]["mef_contratos"]["estado"] == "sin_resultados"
    assert salida["consultas_fuentes"]["mef_ficha"]["estado"] == "respuesta_no_reconocida"


def test_cache_conserva_diagnostico_y_fallo_hasta_ttl(monkeypatch):
    reloj = {"t": 0.0}
    llamadas = []

    def fake(_session, url, **kw):
        llamadas.append((url, kw.get("metodo")))
        if kw.get("metodo") == "POST":
            return _Respuesta([])
        return None

    monkeypatch.setattr(mef, "_get", fake)
    cache = mef.CacheMef(session=_Sesion(), ttl_fallo=10, reloj=lambda: reloj["t"])
    d1, d2, d3 = {}, {}, {}
    assert mef.fetch_ficha_08a("1", cache=cache, diagnostico=d1) is None
    assert mef.fetch_ficha_08a("1", cache=cache, diagnostico=d2) is None
    assert d2["estado"] == "fuente_no_disponible"
    assert mef.fetch_contratos("1", cache=cache, diagnostico=d3) == []
    assert d3["estado"] == "sin_resultados"
    assert len(llamadas) == 2
    reloj["t"] = 11
    d4 = {}
    assert mef.fetch_ficha_08a("1", cache=cache, diagnostico=d4) is None
    assert d4["estado"] == "fuente_no_disponible"
    assert len(llamadas) == 3


def test_cache_legacy_calienta_estado_sin_keyword_nuevo(monkeypatch):
    monkeypatch.setattr(mef, "fetch_ficha_08a", lambda cui, session=None: "<html>ficha</html>")
    cache = mef.CacheMef(session=_Sesion(), ttl_fallo=10, reloj=lambda: 0.0)
    primero, segundo = {}, {}
    assert cache.ficha_08a("1", diagnostico=primero) == "<html>ficha</html>"
    assert primero["estado"] == "respuesta_no_reconocida"
    assert cache.ficha_08a("1", diagnostico=segundo) is None
    assert segundo["estado"] == "respuesta_no_reconocida"


def test_cache_legacy_contratos_sin_keyword_nuevo(monkeypatch):
    monkeypatch.setattr(mef, "_fetch_contratos_crudo",
                        lambda cui, codsnip="", session=None: [])
    cache = mef.CacheMef(session=_Sesion())
    d = {}
    assert cache.contratos("1", diagnostico=d) == []
    assert d["estado"] == "sin_resultados"


def test_error_json_real_conserva_causa_en_cache_y_se_recupera(monkeypatch):
    class Invalida:
        def json(self):
            raise ValueError("JSON inválido")
    reloj = [0]
    respuestas = [Invalida(), _Respuesta([])]
    monkeypatch.setattr(mef, "_get", lambda *a, **kw: respuestas.pop(0))
    cache = mef.CacheMef(session=_Sesion(), ttl_fallo=10, reloj=lambda: reloj[0])
    assert cache.contratos("1") == []
    diag = {}
    assert cache.contratos("1", diagnostico=diag) == []
    assert diag["estado"] == "respuesta_no_reconocida"
    assert len(respuestas) == 1
    reloj[0] = 11
    assert cache.contratos("1", diagnostico=diag) == []
    assert diag["estado"] == "sin_resultados"


def test_http_404_no_es_ausencia_documental():
    class Sesion:
        def request(self, *a, **kw):
            return type("Respuesta", (), {"status_code": 404})()
    diag = {}
    assert mef._get(Sesion(), "https://fuente.invalid/consulta", diagnostico=diag) is None
    assert diag["estado"] == "fuente_no_disponible"


def test_lista_contractual_invalida_no_llega_al_contraste(monkeypatch):
    _get_fake(monkeypatch, {"contratos": ["Error del servidor"]})
    diag = {}
    assert mef.fetch_contratos("1", session=_Sesion(), diagnostico=diag) == []
    assert diag["estado"] == "respuesta_no_reconocida"


def test_adaptador_typeerror_no_se_invoca_dos_veces():
    llamadas = []
    def falla(cui, *, diagnostico):
        llamadas.append(cui)
        raise TypeError("fallo interno")
    with pytest.raises(TypeError, match="fallo interno"):
        mef._llamar_con_diagnostico(falla, "1", diagnostico={})
    assert llamadas == ["1"]
