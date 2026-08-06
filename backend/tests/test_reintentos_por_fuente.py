"""Cada fuente migrada al helper único (ADR-014) conserva el contrato externo que
ya tenían sus llamadores: `None`, `False`, relanzar. Lo que se unificó es el
interior (bucle, backoff, clasificación, logging), no lo que se devuelve.

Cubre las fuentes que NO tenían prueba de reintento propia (mef, sunat, seace y
el contador por hilo del ZIP); las de `infoobras.py`, `zip._get_inventario` y
RENIPRESS ya están cubiertas por `test_infoobras_parsing`, `test_buscar_cui_retry`,
`test_entregables` y `test_renipress`, y no se tocaron. Todo offline.
"""
from __future__ import annotations

import pytest
import requests


class _Resp:
    def __init__(self, code, texto="", cuerpo=b"", headers=None):
        self.status_code = code
        self.text = texto
        self._cuerpo = cuerpo
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_content(self, _tam=None, chunk_size=None):
        yield self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Sesion:
    """Devuelve las respuestas en orden; una excepción se lanza. Cuenta llamadas."""

    def __init__(self, *respuestas):
        self._r = list(respuestas)
        self.llamadas = 0
        self.headers = {}

    def _siguiente(self):
        self.llamadas += 1
        r = self._r[min(self.llamadas - 1, len(self._r) - 1)]
        if isinstance(r, Exception):
            raise r
        return r

    def request(self, *a, **k):
        return self._siguiente()

    def get(self, *a, **k):
        return self._siguiente()


@pytest.fixture(autouse=True)
def sin_dormir(monkeypatch):
    """El backoff duerme en `errores_red`; se anula ahí para toda la suite."""
    import scraping.errores_red as er
    monkeypatch.setattr(er.time, "sleep", lambda *_a: None)


# ── MEF: `None` sigue significando lo mismo para sus llamadores ──────────────

def test_mef_get_reintenta_el_5xx_y_devuelve_la_respuesta_buena():
    from scraping import mef
    ses = _Sesion(_Resp(503), _Resp(200, "<html>ficha</html>"))
    r = mef._get(ses, "https://ofi5.mef.gob.pe/x")
    assert r is not None and r.text == "<html>ficha</html>"
    assert ses.llamadas == 2


def test_mef_get_no_reintenta_el_4xx_y_devuelve_none():
    from scraping import mef
    ses = _Sesion(_Resp(404))
    assert mef._get(ses, "https://ofi5.mef.gob.pe/x") is None
    assert ses.llamadas == 1          # 4xx es respuesta: no existe


def test_mef_get_agota_los_intentos_y_devuelve_none():
    from scraping import mef
    ses = _Sesion(requests.ConnectionError("cerrado"))
    assert mef._get(ses, "https://ofi5.mef.gob.pe/x") is None
    assert ses.llamadas == mef._RETRIES


def test_mef_descargar_pdf_reintenta_y_deja_el_archivo(tmp_path):
    from scraping import mef
    ses = _Sesion(_Resp(500), _Resp(200, cuerpo=b"%PDF-1.7 contenido"))
    destino = tmp_path / "doc.pdf"
    assert mef.descargar_pdf(ses, "https://ofi5.mef.gob.pe/d", destino) is True
    assert destino.read_bytes() == b"%PDF-1.7 contenido"
    assert not destino.with_name("doc.pdf.part").exists()


def test_mef_descargar_pdf_devuelve_false_y_limpia_el_parcial(tmp_path):
    from scraping import mef
    ses = _Sesion(requests.ConnectionError("cortado"))
    destino = tmp_path / "doc.pdf"
    assert mef.descargar_pdf(ses, "https://ofi5.mef.gob.pe/d", destino) is False
    assert not destino.exists() and not destino.with_name("doc.pdf.part").exists()


# ── SUNAT: `Response | None`, con su jitter ──────────────────────────────────

def test_sunat_reintenta_el_5xx_y_devuelve_la_respuesta():
    from scraping import sunat
    ses = _Sesion(_Resp(502), _Resp(200, "ok"))
    r = sunat._request_with_retry(ses, "GET", "https://e-consultaruc.sunat.gob.pe/x",
                                  timeout=5, description="detalle")
    assert r is not None and r.text == "ok" and ses.llamadas == 2


def test_sunat_devuelve_el_4xx_sin_reintentar():
    from scraping import sunat
    ses = _Sesion(_Resp(404))
    r = sunat._request_with_retry(ses, "GET", "https://e-consultaruc.sunat.gob.pe/x",
                                  timeout=5, description="detalle")
    assert r is not None and r.status_code == 404 and ses.llamadas == 1


def test_sunat_devuelve_none_si_el_portal_nunca_responde():
    from scraping import sunat
    ses = _Sesion(requests.Timeout("agotado"))
    r = sunat._request_with_retry(ses, "GET", "https://e-consultaruc.sunat.gob.pe/x",
                                  timeout=5, description="detalle")
    assert r is None and ses.llamadas == sunat.SUNAT_MAX_RETRIES


# ── SEACE abierto: 404 es respuesta, 5xx es caída ────────────────────────────

def test_seace_get_devuelve_el_404_como_respuesta():
    from scraping import seace_abierto as sa
    ses = _Sesion(_Resp(404))
    r = sa._get(ses, "https://contratacionesabiertas.oece.gob.pe/api/v1/x")
    assert r is not None and r.status_code == 404 and ses.llamadas == 1


def test_seace_get_reintenta_el_5xx_y_luego_devuelve_none():
    from scraping import seace_abierto as sa
    ses = _Sesion(_Resp(503))
    assert sa._get(ses, "https://contratacionesabiertas.oece.gob.pe/api/v1/x") is None
    assert ses.llamadas == sa._RETRIES


# ── ZIP InfoObras: el contador por hilo sigue contando reintentos ────────────

def test_zip_cuenta_los_reintentos_en_las_estadisticas_del_hilo(tmp_path):
    from entregables import zip_infoobras as z

    z.reset_descargas_stats()
    ses = _Sesion(_Resp(503), _Resp(200, cuerpo=b"contenido"))
    ok = z._descargar_a_carpeta(
        ses, {"filename": "f/a.pdf", "nombre": "acta", "extension": "pdf"},
        tmp_path, timeout=5)

    assert ok is True
    assert z.descargas_stats()["reintentos"] == 1
    assert z.descargas_stats()["fallidos"] == []


def test_zip_registra_el_fallo_definitivo_tras_agotar_intentos(tmp_path):
    from entregables import zip_infoobras as z

    z.reset_descargas_stats()
    ses = _Sesion(requests.ConnectionError("('Connection aborted.', RemoteDisconnected())"))
    ok = z._descargar_a_carpeta(
        ses, {"filename": "f/a.pdf", "nombre": "acta", "extension": "pdf"},
        tmp_path, timeout=5, intentos=3)

    assert ok is False
    assert z.descargas_stats()["reintentos"] == 2      # 3 intentos → 2 reintentos
    etiqueta, categoria, _msg = z.descargas_stats()["fallidos"][0]
    assert etiqueta == "acta" and categoria == "portal"
    assert not (tmp_path / "acta.pdf").exists()


def test_zip_no_reintenta_un_4xx_de_descarga(tmp_path):
    from entregables import zip_infoobras as z

    z.reset_descargas_stats()
    ses = _Sesion(_Resp(404))
    ok = z._descargar_a_carpeta(
        ses, {"filename": "f/a.pdf", "nombre": "acta", "extension": "pdf"},
        tmp_path, timeout=5)

    assert ok is False and ses.llamadas == 1
    assert z.descargas_stats()["reintentos"] == 0
    assert z.descargas_stats()["fallidos"][0][0] == "acta"
