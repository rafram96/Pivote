"""Test offline: _buscar_por_cui reintenta cuando el portal responde 200 con lista
VACÍA (hipo no-determinístico del portal), no solo ante excepción de red. Esto evita
que un CUI citado caiga en "sin candidato fiable" por un hipo. Sin red (fake session)."""
import scraping.infoobras as io


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Sess:
    """Devuelve los payloads en orden; repite el último si se agotan. Cuenta posts."""
    def __init__(self, payloads):
        self._p = list(payloads)
        self.calls = 0

    def post(self, *a, **k):
        p = self._p[min(self.calls, len(self._p) - 1)]
        self.calls += 1
        return _Resp(p)


_VACIO = {"Result": {"data": []}}


def _lleno(cui):
    return {"Result": {"data": [{"codSnip": cui, "nombrObra": "OBRA X"}]}}


def test_reintenta_en_200_vacio_y_encuentra(monkeypatch):
    monkeypatch.setattr(io.time, "sleep", lambda *a, **k: None)
    sess = _Sess([_VACIO, _lleno("2535573")])   # 1er intento vacío, 2do con la obra
    out = io._buscar_por_cui(sess, "2535573")
    assert len(out) == 1
    assert sess.calls == 2                        # reintentó tras el 200 vacío


def test_vacio_persistente_devuelve_lista_vacia(monkeypatch):
    monkeypatch.setattr(io.time, "sleep", lambda *a, **k: None)
    sess = _Sess([_VACIO])                        # siempre vacío
    out = io._buscar_por_cui(sess, "9999999")
    assert out == []
    assert sess.calls == 3                         # agotó los 3 intentos antes de rendirse


def test_no_reintenta_si_encuentra_al_primero(monkeypatch):
    monkeypatch.setattr(io.time, "sleep", lambda *a, **k: None)
    sess = _Sess([_lleno("385674")])
    out = io._buscar_por_cui(sess, "385674")
    assert len(out) == 1
    assert sess.calls == 1                         # halló al 1er intento → no reintenta
