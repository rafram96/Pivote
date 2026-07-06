"""
Verificador puntual del fix de expedientes (T-001): confirma que la página
`Mapa/Sumario` de InfoObras entrega el botón de descarga del hito "Aprobación del
proyecto" en el HTML del SERVIDOR (no pintado por JS) y que el parser lo extrae.

Read-only: un solo GET a una página PÚBLICA de InfoObras. No corre el pipeline, no
sube datos, no toca SUNAT ni descarga documentos.

Uso:  python scripts/verificar_aprobacion.py [obraId ...]   (default: 124468)
"""
from __future__ import annotations

import sys

from scraping.infoobras import (
    _SUMARIO, _crear_session, parsear_aprobacion_expediente)


def verificar(obra_id: str) -> None:
    sess = _crear_session()
    r = sess.get(_SUMARIO, params={"obraId": obra_id}, timeout=30)
    html = r.text
    tiene_boton = "data-download-url" in html
    tiene_rotulo = "probaci" in html and "proyecto" in html.lower()  # "Aprobación del proyecto"
    it = parsear_aprobacion_expediente(html)

    print(f"\n── obraId {obra_id} ─ HTTP {r.status_code} ─ {len(html):,} bytes")
    print(f"   'data-download-url' en el HTML server-side : {'SÍ' if tiene_boton else 'NO'}")
    print(f"   rótulo 'Aprobación del proyecto' presente   : {'SÍ' if tiene_rotulo else 'NO'}")
    if it:
        print("   ✅ parser EXTRAJO la aprobación:")
        for k in ("nombre", "filename", "extension", "fecha"):
            print(f"        {k:10}: {it.get(k)}")
        print(f"        url       : {it.get('url')}")
    else:
        print("   ❌ parser devolvió None (revisa si el botón viene por JS o cambió el HTML)")


if __name__ == "__main__":
    ids = sys.argv[1:] or ["124468"]
    for oid in ids:
        try:
            verificar(oid)
        except Exception as e:  # noqa: BLE001
            print(f"── obraId {oid}: fallo — {type(e).__name__}: {e}")
