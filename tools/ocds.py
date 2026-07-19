"""
ocds.py — SONDA T-004 (BASES): documentos del procedimiento vía la API OCDS del
OECE (ex-OSCE), SIN captcha. Cierra la única pieza que CONOSCE no daba: el PDF de
las Bases Integradas.

Descubierto en la sonda del 2026-07-18. El portal de Contrataciones Abiertas migró
de osce.gob.pe (host muerto) a **oece.gob.pe**:

  API:     https://contratacionesabiertas.oece.gob.pe/api/v1/records?page=N
  Por ocid: https://contratacionesabiertas.oece.gob.pe/api/v1/record/<ocid>

MAPEO CLAVE (verificado en vivo):
  ocid = "ocds-dgv273-seacev3-<codigoconvocatoria>"
  → el `codigoconvocatoria` de los datasets CONOSCE (ver conosce.py) es el mismo
    número. Así se enlaza sin buscar: CONOSCE da el codigoconvocatoria, OCDS da
    los documentos de ese proceso.

El record trae `compiledRelease.tender.documents[]` con, típicamente:
    biddingDocuments   → "Bases Administrativas", **"Bases Integradas"**,
                         "Documentos de Presentación de Propuestas"
    clarifications     → Pliego de absolución de consultas
    evaluationReports  → Documentos de Calificación y Evaluación
    awardNotice        → Documentos de Otorgamiento de Buena Pro
Y `compiledRelease.contracts[].documents[]` con contractSigned (el contrato).

Las URLs de documentos apuntan a Alfresco (SdescargarArchivoAlfresco?fileCode=UUID)
o al servlet del portal; TODAS bajan el PDF directo, sin captcha (verificado:
Bases Integradas 7.4MB, Bases Administrativas 2.9MB, contrato 2.2MB).

Uso:
  python tools/ocds.py 1207427                 # por codigoconvocatoria (arma el ocid)
  python tools/ocds.py ocds-dgv273-seacev3-1207427
  python tools/ocds.py 1207427 --bajar         # descarga las Bases Integradas + contrato

Solo lectura. Sonda para T-004 (aún no es código de producción). Requiere IP Perú
(el host oece.gob.pe puede geobloquear desde fuera).
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

API = "https://contratacionesabiertas.oece.gob.pe/api/v1"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/144",
      "Accept": "application/json"}
OUT = Path(__file__).parent / "_sonda_seace"
OUT.mkdir(parents=True, exist_ok=True)


def ocid_de(clave: str) -> str:
    """Acepta un ocid completo o un codigoconvocatoria y devuelve el ocid."""
    clave = clave.strip()
    if clave.startswith("ocds-"):
        return clave
    return f"ocds-dgv273-seacev3-{clave}"


def obtener_record(clave: str) -> dict | None:
    ocid = ocid_de(clave)
    r = requests.get(f"{API}/record/{ocid}", headers=UA, timeout=30, verify=False)
    if r.status_code != 200:
        return None
    d = r.json()
    rec = (d.get("records") or [d])[0]
    return rec.get("compiledRelease", rec)


def documentos(comp: dict) -> list[dict]:
    docs = list(comp.get("tender", {}).get("documents", []) or [])
    for c in comp.get("contracts", []) or []:
        docs += c.get("documents", []) or []
    return docs


def descargar(url: str, dest: Path) -> bool:
    r = requests.get(url, headers={"User-Agent": UA["User-Agent"]},
                     timeout=120, verify=False, allow_redirects=True)
    if r.status_code != 200 or not r.content:
        return False
    dest.write_bytes(r.content)
    return r.content[:4] == b"%PDF"


def main() -> int:
    import urllib3
    urllib3.disable_warnings()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    bajar = "--bajar" in sys.argv
    if not args:
        print(__doc__)
        return 2

    comp = obtener_record(args[0])
    if not comp:
        print("No se encontró el proceso (ocid inválido, sin datos, o geobloqueo fuera de Perú).")
        return 1

    t = comp.get("tender", {})
    print(f"ocid       : {comp.get('ocid')}")
    print(f"proceso    : {t.get('title')}")
    print(f"entidad    : {comp.get('buyer', {}).get('name')}")
    print(f"método     : {t.get('procurementMethodDetails')}")
    docs = documentos(comp)
    print(f"\n{len(docs)} documento(s):")
    for d in docs:
        print(f"  [{d.get('documentType'):18}] {str(d.get('title'))[:46]:46} {d.get('url')}")

    if bajar:
        print("\nDescargando Bases Integradas + contrato…")
        for d in docs:
            titulo = str(d.get("title") or "")
            es_bi = d.get("documentType") == "biddingDocuments" and "Integradas" in titulo
            es_contrato = d.get("documentType") == "contractSigned"
            if not (es_bi or es_contrato):
                continue
            nombre = ("BASES_INTEGRADAS" if es_bi else "CONTRATO") + f"_{comp.get('ocid').split('-')[-1]}.pdf"
            ok = descargar(d["url"], OUT / nombre)
            print(f"  {'OK ' if ok else 'FALLÓ'} {nombre}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
