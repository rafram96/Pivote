"""
mef-test.py — DEMO: búsqueda de inversiones en el MEF por NOMBRE, SIN captcha.

Usa los endpoints JSON que alimentan el buscador "Búsqueda por nombre" del SSI
(descubiertos en script_ssi01.js — es el mismo WS que usa la página, pero directo,
así que no pasa por el captcha de la Consulta Pública):

  POST /invierteWS/Ssi/busInvNombreDWH          data: {des_inv, tipo: "NOM"}
  POST /invierteWS/Dashboard/busInvNombreSSI    (fallback, mismo contrato)

Uso:
  python tools/mef-test.py "FELIPE SANTIAGO SALAVERRY"
  python tools/mef-test.py "DIVINO NIÑO VILLA LOS REYES"
  python tools/mef-test.py 2118617          # si es numérico: abre la ficha por CUI

Devuelve: CUI · SNIP · Estado · Situación · Nombre (+ enlace a la ficha).
Solo lectura. Demo para T-003 / módulo B (no es código de producción).
"""
from __future__ import annotations

import sys
import time

import requests

BASE = "https://ofi5.mef.gob.pe"
BUSCAR_DWH = BASE + "/invierteWS/Ssi/busInvNombreDWH"
BUSCAR_SSI = BASE + "/invierteWS/Dashboard/busInvNombreSSI"
FICHA = BASE + "/invierte/consultapublica/consultainversiones?cui={cui}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def _post(ses: requests.Session, url: str, nombre: str, reintentos: int = 3) -> list[dict]:
    for intento in range(reintentos):
        try:
            r = ses.post(url, data={"des_inv": nombre, "tipo": "NOM"}, timeout=30)
            if r.status_code == 404:
                return []   # endpoint muerto (p. ej. el DWH) → sin ruido, al fallback
            r.raise_for_status()
            res = r.json()
            return res if isinstance(res, list) else []
        except Exception as e:  # noqa: BLE001 — portal público intermitente
            print(f"   (intento {intento + 1}/{reintentos} falló: {e})", file=sys.stderr)
            time.sleep(1.5 * (intento + 1))
    return []


def buscar(nombre: str) -> list[dict]:
    """SSI primero (el WS vivo, verificado 15-jul); el DWH — que la página oficial
    intenta primero pero hoy responde 404 — queda como fallback por si lo reviven."""
    ses = requests.Session()
    ses.headers["User-Agent"] = UA
    res = _post(ses, BUSCAR_SSI, nombre)
    fuente = "SSI"
    if not res:
        res = _post(ses, BUSCAR_DWH, nombre, reintentos=1)
        fuente = "DWH"
    for o in res:
        o["_fuente"] = fuente
    return res


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(__doc__)
        return 2
    consulta = " ".join(sys.argv[1:]).strip()

    if consulta.isdigit():   # modo CUI directo: solo imprime el enlace a la ficha
        print(f"CUI {consulta} → ficha: {FICHA.format(cui=consulta)}")
        return 0

    print(f'Buscando "{consulta}" en el Banco de Inversiones del MEF (sin captcha)…\n')
    t0 = time.time()
    res = buscar(consulta)
    if not res:
        print("Sin resultados. Prueba con una palabra clave más distintiva "
              "(p. ej. el nombre propio de la I.E., no el nombre completo).")
        print("Ojo: 0 resultados NO prueba que no exista — validar el buscador "
              "con un término conocido (anti-falso-negativo).")
        return 1

    print(f"{len(res)} resultado(s) [{res[0]['_fuente']}] en {time.time()-t0:.1f}s:")
    print(f"{'CUI':>9}  {'SNIP':>8}  {'ESTADO':12} {'SITUACIÓN':22} NOMBRE")
    print("─" * 110)
    for o in res[:25]:
        cui = str(o.get("CODIGO_UNICO") or "").strip()
        snip = str(o.get("COD_SNIP") or "").strip()
        est = str(o.get("ESTADO") or "—")[:12]
        sit = str(o.get("SITUACION") or "—")[:22]
        nom = str(o.get("NOMBRE_INVERSION") or "")[:70]
        print(f"{cui:>9}  {snip:>8}  {est:12} {sit:22} {nom}")
    if len(res) > 25:
        print(f"… y {len(res) - 25} más (afina la palabra clave)")
    print(f"\nFicha de un CUI: {FICHA.format(cui='<CUI>')}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # consola Windows
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
