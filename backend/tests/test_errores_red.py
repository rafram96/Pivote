"""Test offline del clasificador de errores de red/portal (sin red)."""
from scraping.errores_red import OTRO, PORTAL, RED, clasificar, corto


def test_dns_getaddrinfo_es_red():
    e = ("HTTPSConnectionPool(host='infobras.contraloria.gob.pe', port=443): Max retries "
         "exceeded with url: /x (Caused by NameResolutionError(\"...Failed to resolve "
         "'infobras.contraloria.gob.pe' ([Errno 11001] getaddrinfo failed)\"))")
    cat, msg = clasificar(e)
    assert cat == RED and "DNS" in msg


def test_ssl_hostname_mismatch_es_red():
    e = ("SSLError(SSLCertVerificationError(1, \"[SSL: CERTIFICATE_VERIFY_FAILED] certificate "
         "verify failed: Hostname mismatch, certificate is not valid for "
         "'infobras.contraloria.gob.pe'. (_ssl.c:1010)\"))")
    cat, msg = clasificar(e)
    assert cat == RED and "SSL" in msg


def test_incompleteread_es_portal_y_extrae_mb():
    e = ("('Connection broken: IncompleteRead(11730943 bytes read, 3601483 more expected)', "
         "IncompleteRead(11730943 bytes read, 3601483 more expected))")
    cat, msg = clasificar(e)
    assert cat == PORTAL
    assert "11.7/15.3 MB" in msg          # 11.73 leído de 15.33 totales


def test_remote_disconnected_es_portal():
    e = "('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))"
    cat, msg = clasificar(e)
    assert cat == PORTAL and "cerró" in msg


def test_corto_lleva_categoria_entre_corchetes():
    assert corto("IncompleteRead(100 bytes read, 50 more expected)").startswith("[portal]")


def test_fallback_otro_es_corto():
    cat, msg = clasificar("algo raro que no matchea ningún patrón conocido")
    assert cat == OTRO and len(msg) <= 90
