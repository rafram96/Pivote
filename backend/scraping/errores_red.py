"""Clasifica excepciones de red/portal en (categoría, mensaje corto) para que los
logs de scraping de InfoObras dejen de escupir la excepción cruda (IncompleteRead
con bytes, tracebacks SSL, URLs larguísimas). Puro string-matching, sin red →
testeable offline.

Categorías:
  red    → problema del lado del usuario: DNS, SSL/intercepción, sin salida a internet.
  portal → problema del servidor InfoObras: cortó la descarga, 5xx, timeout.
  otro   → no clasificado (se devuelve un extracto corto).
"""
from __future__ import annotations

import re

RED = "red"
PORTAL = "portal"
OTRO = "otro"


def clasificar(e) -> tuple[str, str]:
    """Devuelve (categoria, mensaje_corto en español) para una excepción o cadena."""
    s = str(e)
    low = s.lower()

    # --- RED: tu conexión (DNS / SSL / sin salida) ---
    if "getaddrinfo failed" in low or "failed to resolve" in low or "nameresolution" in low:
        return RED, "sin DNS — no se pudo resolver el dominio (revisa tu internet)"
    if ("certificate_verify_failed" in low or "hostname mismatch" in low
            or "certificateerror" in low or "sslcertverification" in low):
        return RED, "SSL inválido — posible red/proxy interceptando"
    if "sslerror" in low or "[ssl:" in low:
        return RED, "error SSL en la conexión"

    # --- PORTAL: el servidor de InfoObras ---
    m = re.search(r"incompleteread\((\d+) bytes read, (\d+) more expected\)", low)
    if m:
        leido, falta = int(m.group(1)), int(m.group(2))
        tot = (leido + falta) / 1e6
        return PORTAL, f"el portal cortó la transferencia ({leido / 1e6:.1f}/{tot:.1f} MB)"
    if "descarga incompleta" in low:
        return PORTAL, "el portal cortó la descarga antes de terminar"
    if "remotedisconnected" in low or "connection aborted" in low or "connectionreset" in low:
        return PORTAL, "el portal cerró la conexión"
    if "connection broken" in low or "chunkedencoding" in low:
        return PORTAL, "transferencia interrumpida por el portal"
    if "timed out" in low or "timeout" in low:
        return PORTAL, "timeout — el portal no respondió a tiempo"
    m = re.search(r"http (\d{3})", low)
    if m:
        return PORTAL, f"el portal respondió HTTP {m.group(1)}"
    if "max retries exceeded" in low:
        return RED, "no se pudo conectar al portal (sin salida a internet)"

    # --- fallback: extracto corto de una línea ---
    base = s.splitlines()[0].strip() if s.strip() else type(e).__name__
    return OTRO, (base[:88] + "…") if len(base) > 88 else base


def corto(e) -> str:
    """'[categoria] mensaje corto' — para meter directo en un log."""
    cat, msg = clasificar(e)
    return f"[{cat}] {msg}"
