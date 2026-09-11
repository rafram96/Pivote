"""Consultas de identidad: fuente legible no equivale a experiencia verificada."""
from __future__ import annotations

import importlib

import pytest
import requests

from scraping import consulta_infoobras as consulta


def _respuesta(html="", status=200):
    respuesta = requests.Response()
    respuesta.status_code = status
    respuesta._content = html.encode("utf-8")
    respuesta.encoding = "utf-8"
    return respuesta


def _html(oid=71, texto=""):
    return f"<html><title>FICHA DE OBRA PÚBLICA - {oid}</title><body>{texto}</body></html>"


class SesionSimulada:
    def __init__(self, respuestas=()):
        self.respuestas = iter(respuestas)
        self.consultas = []
        self.cerrada = False

    def get(self, url, **kwargs):
        self.consultas.append((url, kwargs))
        respuesta = next(self.respuestas)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    def close(self):
        self.cerrada = True


@pytest.fixture
def fuente(monkeypatch):
    def configurar(obras, respuestas=()):
        sesion = SesionSimulada(respuestas)
        monkeypatch.setattr(consulta.infoobras, "_crear_session", lambda: sesion)

        def buscar(session, codigo):
            assert session is sesion
            assert codigo == "2130855"
            if isinstance(obras, Exception):
                raise obras
            return obras

        monkeypatch.setattr(consulta.infoobras, "_buscar_por_cui", buscar)
        return sesion
    return configurar


OBRAS = [
    {"codigoObra": "71", "codUniqInv": "2130855", "nombrObra": "Obra principal",
     "fechaInicio": "2014-06-24", "otroCampoFuente": "sin reinterpretar"},
    {"codigoObra": 53, "codUniqInv": "2130855", "nombrObra": "Componente posterior"},
]


def test_candidatos_conservan_registros_sin_elegir(fuente):
    sesion = fuente(OBRAS)
    salida = consulta.listar_fichas("2130855")
    assert salida["estado"] == "disponible"
    assert [c["obra_id"] for c in salida["candidatos"]] == [71, 53]
    assert salida["candidatos"][0]["datos_fuente"] == OBRAS[0]
    assert salida["candidatos"][0]["nombre"] == "Obra principal"
    assert salida["listado_completo_verificado"] is False
    assert salida["limite_consulta_fuente"] == 20
    assert salida["consultado_en"]
    assert "evalúa" in salida["alcance"]
    assert not sesion.consultas
    assert sesion.cerrada


def test_lista_vacia_no_afirma_que_no_existe(fuente):
    fuente([])
    salida = consulta.listar_fichas("2130855")
    assert salida["estado"] == "sin_resultados"
    assert salida["candidatos"] == []
    assert salida["listado_completo_verificado"] is False


def test_id_alternativo_valido_se_conserva(fuente):
    fuente([{"codigoObra": "invalido", "obraId": 71, "codUniqInv": "2130855"}])
    assert consulta.listar_fichas("2130855")["candidatos"][0]["obra_id"] == 71


def test_json_invalido_http200_es_formato_no_ausencia(monkeypatch):
    class SesionJSON(SesionSimulada):
        def post(self, url, **kwargs):
            self.consultas.append((url, kwargs))
            return _respuesta("<html>Login</html>")

    sesion = SesionJSON()
    monkeypatch.setattr(consulta.infoobras, "_crear_session", lambda: sesion)
    salida = consulta.listar_fichas("2130855")
    assert salida["estado"] == "formato_no_reconocido"
    assert salida["candidatos"] is None
    assert len(sesion.consultas) == 1
    assert sesion.cerrada


@pytest.mark.parametrize("error,estado", [
    (requests.Timeout("secreto/no mostrar"), "fuente_no_respondio"),
    (ValueError("secreto/no mostrar"), "formato_no_reconocido"),
    (requests.HTTPError(response=_respuesta(status=403)), "error_http"),
])
def test_error_no_se_convierte_en_ausencia(fuente, error, estado):
    sesion = fuente(error)
    salida = consulta.listar_fichas("2130855")
    assert salida["estado"] == estado
    assert salida["candidatos"] is None
    assert "secreto" not in str(salida)
    assert sesion.cerrada
    if estado == "error_http":
        assert salida["http_status"] == 403


@pytest.mark.parametrize("cui", [None, True, [], "12&otra=1", "１２３", "12345678901"])
def test_cui_invalido_no_consulta(monkeypatch, cui):
    monkeypatch.setattr(consulta.infoobras, "_crear_session", lambda: pytest.fail("no debe consultar"))
    with pytest.raises(consulta.ConsultaIdentidadInvalida):
        consulta.listar_fichas(cui)


@pytest.mark.parametrize("oid", [True, [], 0, -1, "1&otra=2", 2147483648, 1.5])
def test_id_invalido_no_consulta(monkeypatch, oid):
    monkeypatch.setattr(consulta.infoobras, "_crear_session", lambda: pytest.fail("no debe consultar"))
    with pytest.raises(consulta.ConsultaIdentidadInvalida):
        consulta.consultar_ficha("2130855", oid)


def test_ficha_explicita_preserva_fechas_y_enlaces_sin_bajar_documentos(fuente):
    texto = '<table><tr><td>Contrato principal</td><td>24/06/2014</td></tr></table>'
    texto += '<button data-download-url="/InfobrasWeb/doc/71.pdf" data-nombre="Contrato">Ver</button>'
    texto += '<script>NO ES TEXTO VISIBLE</script>'
    sesion = fuente(OBRAS, [_respuesta(_html(texto=texto)), _respuesta(_html())])
    salida = consulta.consultar_ficha("2130855", "71")
    assert salida["estado"] == "disponible"
    assert salida["ficha"]["obra_id"] == 71
    assert salida["ficha"]["datos_fuente"]["fechaInicio"] == "2014-06-24"
    assert len(sesion.consultas) == 2
    assert all(url.endswith("?ObraId=71") for url, _ in sesion.consultas)
    assert not any(url.endswith(".pdf") for url, _ in sesion.consultas)
    lectura = salida["fuentes"][0]
    assert "24/06/2014" in lectura["texto_visible"]
    assert "NO ES TEXTO VISIBLE" not in lectura["texto_visible"]
    assert lectura["documentos_enlazados"][0]["clasificacion"] == "sin_identificar"
    assert lectura["documentos_enlazados"][0]["nombre_fuente"] == "Contrato"
    assert sesion.cerrada


def test_id_ausente_no_consulta_ni_sustituye(fuente):
    sesion = fuente(OBRAS)
    salida = consulta.consultar_ficha("2130855", 999)
    assert salida["estado"] == "ficha_no_encontrada_en_consulta"
    assert salida["ficha"] is None
    assert not sesion.consultas
    assert "ni se afirma que no exista" in salida["motivo"]


def test_fuente_parcial_retiene_identidad_y_error(fuente):
    fuente(OBRAS, [_respuesta(_html()), requests.Timeout()])
    salida = consulta.consultar_ficha("2130855", 71)
    assert salida["estado"] == "parcial"
    assert salida["ficha"]["obra_id"] == 71
    assert salida["fuentes"][1]["estado"] == "fuente_no_respondio"


@pytest.mark.parametrize("html", ["<title>Login</title>", _html(oid=53), "<div>Error</div>"])
def test_http_200_no_prueba_ficha_correcta(fuente, html):
    fuente(OBRAS, [_respuesta(html), _respuesta(html)])
    salida = consulta.consultar_ficha("2130855", 71)
    assert salida["estado"] == "sin_lectura_de_ficha"
    assert all(f["estado"] == "formato_no_reconocido" for f in salida["fuentes"])


def test_layout_con_dos_titulos_lee_id_de_ficha(fuente):
    html = "<title>Infobras | Datos de ejecución</title>" + _html()
    fuente(OBRAS, [_respuesta(html), _respuesta(html)])
    salida = consulta.consultar_ficha("2130855", 71)
    assert salida["estado"] == "disponible"
    assert salida["fuentes"][0]["obra_ids_en_titulos"] == [71]


def test_titulos_con_ids_contradictorios_no_acreditan_ficha(fuente):
    html = _html(71) + _html(53)
    fuente(OBRAS, [_respuesta(html), _respuesta(html)])
    salida = consulta.consultar_ficha("2130855", 71)
    assert salida["estado"] == "sin_lectura_de_ficha"
    assert salida["fuentes"][0]["obra_ids_en_titulos"] == [53, 71]


def test_truncamiento_explicito(fuente):
    fuente(OBRAS, [_respuesta(_html(texto="x" * 65000)), _respuesta(_html())])
    salida = consulta.consultar_ficha("2130855", 71)["fuentes"][0]
    assert salida["texto_truncado"] is True
    assert len(salida["texto_visible"]) == consulta._LIMITE_TEXTO
    assert salida["caracteres_totales"] > consulta._LIMITE_TEXTO


@pytest.fixture
def cliente_lectura(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    monkeypatch.delenv("PIVOTE_DB_URL", raising=False)
    monkeypatch.delenv("PIVOTE_ONPREM_TOKEN", raising=False)
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    with TestClient(modulo.app) as cliente:
        yield cliente


def test_api_conserva_estados_sin_crear_jobs(cliente_lectura, fuente, tmp_path):
    fuente(requests.Timeout())
    respuesta = cliente_lectura.get("/api/pivote/infoobras/candidatos?cui=2130855")
    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "fuente_no_respondio"
    assert not list(tmp_path.rglob("espejo.json"))


def test_api_id_explicito_y_entrada_invalida(cliente_lectura, fuente):
    fuente(OBRAS, [_respuesta(_html()), _respuesta(_html())])
    respuesta = cliente_lectura.get("/api/pivote/infoobras/ficha?cui=2130855&obra_id=71")
    assert respuesta.status_code == 200
    assert respuesta.json()["ficha"]["obra_id"] == 71
    assert cliente_lectura.get("/api/pivote/infoobras/ficha?cui=2130855&obra_id=0").status_code == 400
    assert cliente_lectura.get("/api/pivote/infoobras/candidatos?cui=no").status_code == 400
