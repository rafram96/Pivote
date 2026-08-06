"""El helper único de reintentos (ADR-014): política, clasificación y —lo que
motivó la tarea— la distinción entre «la fuente respondió vacío» (dato) y «la
fuente no respondió» (incógnita). Todo offline: nunca se duerme ni se toca red.
"""
from __future__ import annotations

import logging

import pytest
import requests

from scraping.errores_red import (
    EXPONENCIAL, LINEAL, Permanente, Politica, RespuestaTransitoria, Resultado,
    con_reintentos, permanente, reintentar,
)


# ── política: intentos, backoff llamado, jitter acotado ──────────────────────

def test_politica_lineal_y_exponencial_dan_las_esperas_de_siempre():
    lineal = Politica(intentos=3, base=1.5, modo=LINEAL)
    assert [lineal.espera(i) for i in range(3)] == [1.5, 3.0, 4.5]

    expo = Politica(intentos=3, base=1.0, modo=EXPONENCIAL)
    assert [expo.espera(i) for i in range(3)] == [1.0, 2.0, 4.0]


def test_jitter_esta_acotado_entre_cero_y_su_valor():
    p = Politica(intentos=3, base=0.5, modo=EXPONENCIAL, jitter=0.3)
    assert p.espera(0, azar=lambda: 0.0) == pytest.approx(0.5)
    assert p.espera(0, azar=lambda: 1.0) == pytest.approx(0.8)
    # cualquier azar real cae dentro de la banda [base, base + jitter]
    for _ in range(50):
        assert 0.5 <= p.espera(0) <= 0.8


def test_el_tope_recorta_la_espera_antes_del_jitter():
    p = Politica(intentos=5, base=1.0, modo=EXPONENCIAL, tope=2.0, jitter=0.5)
    assert p.espera(4, azar=lambda: 0.0) == pytest.approx(2.0)


def test_politica_invalida_no_se_construye():
    with pytest.raises(ValueError):
        Politica(intentos=0)
    with pytest.raises(ValueError):
        Politica(jitter=-1)
    with pytest.raises(ValueError):
        Politica(modo="al azar")


def test_agota_los_intentos_y_duerme_entre_ellos_pero_no_al_final():
    p = Politica(intentos=3, base=2.0, modo=LINEAL)
    esperas, llamadas = [], []

    def _siempre_cae():
        llamadas.append(1)
        raise requests.ConnectionError("portal caído")

    res = con_reintentos(_siempre_cae, politica=p, dormir=esperas.append)

    assert len(llamadas) == 3          # n intentos
    assert esperas == [2.0, 4.0]       # backoff llamado entre intentos, no tras el último
    assert res.respondio is False and res.intentos == 3
    assert isinstance(res.error, requests.ConnectionError)


def test_no_reintenta_si_el_primer_intento_responde():
    esperas = []
    res = con_reintentos(lambda: "ok", dormir=esperas.append)
    assert res.respondio is True and res.valor == "ok" and res.intentos == 1
    assert esperas == []


def test_gancho_al_reintentar_cuenta_solo_los_reintentos():
    cuenta = []

    def _cae():
        raise OSError("nope")

    con_reintentos(_cae, politica=Politica(intentos=4, base=0.0),
                   excepciones=(OSError,), dormir=lambda _s: None,
                   al_reintentar=lambda n, err: cuenta.append((n, type(err))))
    assert cuenta == [(1, OSError), (2, OSError), (3, OSError)]


# ── clasificación: vacío ≠ caído ─────────────────────────────────────────────

def test_una_respuesta_vacia_es_dato_no_caida():
    """`[]`, `None` y `False` devueltos por la operación son respuestas
    definitivas: la fuente contestó y el llamador puede concluir."""
    for vacio in ([], None, False, "", 0):
        res = con_reintentos(lambda v=vacio: v, dormir=lambda _s: None)
        assert res.respondio is True
        assert res.valor == vacio
        assert res.intentos == 1          # ni siquiera se reintentó


def test_una_caida_no_es_dato():
    res = con_reintentos(lambda: (_ for _ in ()).throw(requests.Timeout("t")),
                         politica=Politica(intentos=2, base=0.0),
                         dormir=lambda _s: None)
    assert res.respondio is False
    assert res.valor is None
    assert res.valor_o("SIN DATO") == "SIN DATO"


def test_resultado_no_es_booleano_y_lo_dice():
    """El candado del caso 6:1: `if res:` no puede compilar mentalmente como
    «¿hay dato?». Explota con un mensaje que explica la diferencia."""
    res = Resultado(True, [])
    with pytest.raises(TypeError, match="no es un booleano"):
        bool(res)
    with pytest.raises(TypeError):
        if res:            # noqa: SIM103 — es justamente lo que se prohíbe
            pass
    # la pregunta correcta sí responde
    assert res.respondio is True and res.valor == []


def test_reintentar_vacio_agotado_termina_en_respondio_con_su_valor():
    """El 200-con-lista-vacía de InfoObras: se reintenta, pero si la fuente
    insiste en contestar vacío, el vacío ES el dato — no una caída."""
    llamadas = []

    def _hipo():
        llamadas.append(1)
        return reintentar([])

    res = con_reintentos(_hipo, politica=Politica(intentos=3, base=0.0),
                         dormir=lambda _s: None)
    assert len(llamadas) == 3
    assert res.respondio is True and res.valor == []


def test_una_respuesta_util_tras_un_hipo_gana():
    salidas = [reintentar([]), ["obra"]]
    res = con_reintentos(lambda: salidas.pop(0),
                         politica=Politica(intentos=3, base=0.0),
                         dormir=lambda _s: None)
    assert res.respondio is True and res.valor == ["obra"] and res.intentos == 2


def test_si_contesto_alguna_vez_el_final_es_respondio_aunque_luego_caiga():
    """Contestó vacío y después el portal se cayó: la fuente estaba viva, así que
    el resultado sigue siendo dato (es la bandera `hubo_respuesta` que
    `_buscar_por_cui` llevaba a mano)."""
    salidas = [reintentar([]), requests.ConnectionError("caída")]

    def _mixto():
        s = salidas.pop(0)
        if isinstance(s, Exception):
            raise s
        return s

    res = con_reintentos(_mixto, politica=Politica(intentos=2, base=0.0),
                         dormir=lambda _s: None)
    assert res.respondio is True and res.valor == []


def test_respuesta_transitoria_cuenta_como_caida():
    res = con_reintentos(lambda: (_ for _ in ()).throw(RespuestaTransitoria("HTTP 503")),
                         politica=Politica(intentos=2, base=0.0),
                         dormir=lambda _s: None)
    assert res.respondio is False
    assert "503" in str(res.error)


# ── lo permanente sube en el acto ────────────────────────────────────────────

def test_lo_permanente_no_gasta_intentos_y_conserva_su_tipo():
    llamadas = []

    def _cuatro_cero_cuatro():
        llamadas.append(1)
        with permanente():
            raise requests.HTTPError("HTTP 404")

    with pytest.raises(requests.HTTPError):
        con_reintentos(_cuatro_cero_cuatro, politica=Politica(intentos=3, base=0.0),
                       dormir=lambda _s: None)
    assert len(llamadas) == 1


def test_permanente_deja_pasar_lo_que_no_falla():
    with permanente():
        pass          # 2xx → no-op, como el raise_for_status de una respuesta sana


def test_una_excepcion_fuera_de_la_tupla_sube_sin_reintentar():
    llamadas = []

    def _error_de_programa():
        llamadas.append(1)
        raise KeyError("bug, no red")

    with pytest.raises(KeyError):
        con_reintentos(_error_de_programa, politica=Politica(intentos=3, base=0.0),
                       excepciones=(requests.RequestException,),
                       dormir=lambda _s: None)
    assert len(llamadas) == 1


def test_relanzar_es_no_op_si_contesto_y_lanza_si_no():
    Resultado(True, []).relanzar()          # no lanza
    with pytest.raises(requests.Timeout):
        Resultado(False, None, requests.Timeout("t")).relanzar()
    with pytest.raises(requests.HTTPError):
        Resultado(False).relanzar(requests.HTTPError("de repuesto"))


# ── logging: siempre con `corto()` ───────────────────────────────────────────

def test_cada_intento_fallido_se_loguea_con_el_mensaje_corto(caplog):
    with caplog.at_level(logging.DEBUG):
        con_reintentos(lambda: (_ for _ in ()).throw(requests.ConnectionError(
            "HTTPSConnectionPool(host='x', port=443): Read timed out")),
            politica=Politica(intentos=2, base=0.0), etiqueta="PORTAL X",
            dormir=lambda _s: None)
    texto = caplog.text
    assert "PORTAL X intento 1/2" in texto
    assert "[portal] timeout" in texto          # clasificado, no la excepción cruda
    assert "HTTPSConnectionPool" not in texto
