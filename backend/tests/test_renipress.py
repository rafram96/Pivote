"""Pruebas offline del contrato y la tolerancia a fallos de RENIPRESS."""
from __future__ import annotations

import json

import pytest
import requests

from scraping.renipress import ClienteRENIPRESS


class _Respuesta:
    def __init__(self, texto: str = "{}", estado: int = 200):
        self.text = texto
        self.status_code = estado

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _Sesion:
    def __init__(self, cargas):
        self.cargas = list(cargas)
        self.consultas = []

    def get(self, url, **kwargs):
        self.consultas.append(("GET", url, kwargs))
        if "cargarEstablecimientos" in url:
            carga = self.cargas.pop(0)
            if isinstance(carga, Exception):
                raise carga
            return _Respuesta(carga)
        return _Respuesta()

    def post(self, url, **kwargs):
        self.consultas.append(("POST", url, kwargs))
        return _Respuesta()


def _cliente(*cargas, reintentos=1):
    sesion = _Sesion(cargas)
    cliente = ClienteRENIPRESS(
        crear_sesion=lambda: sesion,
        dormir=lambda _: None,
        reintentos=reintentos,
        timeout=2,
    )
    return cliente, sesion


def test_normaliza_codigo_y_detecta_coincidencia_exacta():
    cuerpo = json.dumps(
        {
            "recordsFiltered": 1,
            "data": [
                {
                    "codigounico": "00008215",
                    "nombrerazonsocial": "CLINICA INTERNACIONAL",
                    "ruc": "20100054184",
                    "estado": "ACTIVO",
                    "distrito": "LIMA",
                }
            ],
        }
    )
    cliente, _ = _cliente(cuerpo)

    resultado = cliente.buscar("00008215")

    assert resultado.estado == "encontrado"
    assert resultado.tipo_consulta == "codigo"
    assert resultado.total == 1
    assert resultado.ambiguo is False
    assert resultado.establecimientos[0].coincidencia_exacta is True
    assert resultado.establecimientos[0].ruc == "20100054184"


def test_distingue_busqueda_sana_sin_resultados():
    cliente, _ = _cliente('{"recordsFiltered":0,"data":[]}')

    resultado = cliente.buscar("NOMBRE INEXISTENTE")

    assert resultado.estado == "sin_resultados"
    assert resultado.detalle_error is None
    assert resultado.establecimientos == []


def test_portal_caido_no_se_convierte_en_sin_resultados():
    cliente, _ = _cliente(
        requests.Timeout("agotado"),
        requests.ConnectionError("cerrado"),
        reintentos=2,
    )

    resultado = cliente.buscar("CLINICA")

    assert resultado.estado == "portal_no_disponible"
    assert resultado.intentos == 2
    assert resultado.detalle_error == "RENIPRESS no respondió tras 2 intento(s)"


def test_parcha_draw_invalido_del_portal():
    cliente, _ = _cliente(
        '{"draw":,"recordsTotal":1,"data":[{"codigounico":"123456"}]}'
    )

    resultado = cliente.buscar("123456")

    assert resultado.estado == "encontrado"
    assert resultado.total == 1


def test_envia_defaults_y_filtro_de_activos():
    cliente, sesion = _cliente('{"recordsTotal":0,"data":[]}')

    cliente.buscar("CLINICA", solo_activos=False, max_filas=25)

    _, _, post = next(c for c in sesion.consultas if c[0] == "POST")
    _, _, carga = next(
        c for c in sesion.consultas if "cargarEstablecimientos" in c[1]
    )
    assert post["data"]["cmb_departamento"] == "0"
    assert post["data"]["cmb_estado"] == "0"
    assert carga["params"]["length"] == "25"


@pytest.mark.parametrize("termino", ["", "   ", None])
def test_rechaza_termino_vacio(termino):
    cliente, _ = _cliente()

    with pytest.raises(ValueError, match="no puede estar vacío"):
        cliente.buscar(termino)


@pytest.mark.parametrize("max_filas", [0, 501])
def test_acota_paginacion(max_filas):
    cliente, _ = _cliente()

    with pytest.raises(ValueError, match="entre 1 y 500"):
        cliente.buscar("CLINICA", max_filas=max_filas)


def test_configuracion_invalida_de_entorno_degrada_a_defaults(monkeypatch):
    monkeypatch.setenv("PIVOTE_RENIPRESS_REINTENTOS", "basura")
    monkeypatch.setenv("PIVOTE_RENIPRESS_TIMEOUT", "-2")
    sesion = _Sesion(['{"recordsTotal":0,"data":[]}'])

    cliente = ClienteRENIPRESS(crear_sesion=lambda: sesion, dormir=lambda _: None)
    resultado = cliente.buscar("CLINICA")

    assert resultado.estado == "sin_resultados"
    primera_consulta = sesion.consultas[0]
    assert primera_consulta[2]["timeout"] == 40.0
