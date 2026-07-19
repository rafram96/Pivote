"""
renipress.py — SONDA T-006: búsqueda de establecimientos de salud en RENIPRESS
(SUSALUD), SIN captcha y por código.

Usa los endpoints JSON que alimentan la grilla del buscador público
(app20.susalud.gob.pe — Spring MVC + DataTables server-side, sin captcha):

  POST listadoEstablecimientosRegistrados.htm?action=buscarEstablecimientos
  GET  listadoEstablecimientosRegistrados.htm?action=cargarEstablecimientos

Hallazgos de la sonda (18-jul-2026):
  - Sin captcha ni sesión especial: basta un GET inicial (cookie JSESSIONID).
  - Los combos deben ir con su valor DEFAULT ("0" = Todos), NO vacíos —
    con cadenas vacías el WS responde ok pero 0 filas (falso negativo).
  - cmb_estado default es "1" (ACTIVO); "0" = todos los estados.
  - txt_filtrar acepta: nombre / denominación / razón social / nombre
    comercial / código único / RUC / director médico (substring).
  - El nombre viene en la clave "nombrerazonsocial" (no "nombre").
  - El JSON de la grilla trae un bug del server ('"draw":,') → se parcha.

Uso:
  python tools/renipress.py "CLINICA INTERNACIONAL"
  python tools/renipress.py "CLINICA SAN PABLO" --todos     # incluye bajas/cierres
  python tools/renipress.py 00008215                        # por código único
  python tools/renipress.py 20100054184                     # por RUC

Devuelve: Código único · Estado · Condición · Distrito/Provincia/Dpto · Nombre.
Solo lectura. Sonda para T-006 (no es código de producción).
"""
from __future__ import annotations

import json
import re
import sys
import time

import requests

BASE = "http://app20.susalud.gob.pe:8080/registro-renipress-webapp/"
PAG_BUSCAR = BASE + "listadoEstablecimientosRegistrados.htm?action=mostrarBuscar"
WS_BUSCAR = BASE + "listadoEstablecimientosRegistrados.htm?action=buscarEstablecimientos"
WS_CARGAR = BASE + "listadoEstablecimientosRegistrados.htm?action=cargarEstablecimientos"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")

# Valores DEFAULT del formulario (¡"0" = Todos, no cadena vacía!).
FORM_BASE = {
    "cmb_departamento": "0", "cmb_provincia": "0", "cmb_distrito": "0",
    "cmb_institucion": "0", "cmb_tipo_establecimiento": "0",
    "cmb_clasificacion": "0", "cmb_categoria": "0", "cmb_unidadEjecutora": "0",
    "cmb_servicio": "0", "cmb_autoridadSanitaria": "0", "cmb_red": "0",
    "cmb_microRed": "0", "cmb_clas": "0", "cmb_colegio": "0",
    "cmb_especialidad": "0", "cmb_quintil": "0", "cmb_telesalud": "0",
}


def buscar(termino: str, solo_activos: bool = True,
           max_filas: int = 50, reintentos: int = 3) -> list[dict]:
    """Busca en RENIPRESS por nombre/razón social/código único/RUC (substring)."""
    form = dict(FORM_BASE)
    form["txt_filtrar"] = termino
    form["cmb_estado"] = "1" if solo_activos else "0"
    for intento in range(reintentos):
        try:
            ses = requests.Session()
            ses.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest"})
            ses.get(PAG_BUSCAR, timeout=30)          # cookie de sesión
            ses.post(WS_BUSCAR, data=form, timeout=40)   # valida y fija la búsqueda
            q = dict(form)
            q.update({"draw": "1", "start": "0", "length": str(max_filas)})
            r = ses.get(WS_CARGAR, params=q, timeout=90)
            r.raise_for_status()
            # bug del server: '"draw":,' no es JSON válido
            j = json.loads(re.sub(r'"draw":\s*,', '"draw":1,', r.text))
            filas = j.get("data") or []
            for f in filas:
                f["_total"] = j.get("recordsTotal")
            return filas
        except Exception as e:  # noqa: BLE001 — portal público intermitente
            print(f"   (intento {intento + 1}/{reintentos} falló: {e})", file=sys.stderr)
            time.sleep(1.5 * (intento + 1))
    return []


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    todos = "--todos" in sys.argv
    if not args or not args[0].strip():
        print(__doc__)
        return 2
    termino = " ".join(args).strip()

    ambito = "todos los estados" if todos else "solo ACTIVOS"
    print(f'Buscando "{termino}" en RENIPRESS ({ambito}, sin captcha)…\n')
    t0 = time.time()
    filas = buscar(termino, solo_activos=not todos)
    if not filas:
        print("Sin resultados. Prueba una palabra más distintiva o --todos "
              "(incluye bajas y cierres).")
        print("Ojo: 0 resultados NO prueba que no exista — validar el buscador "
              "con un término conocido (anti-falso-negativo).")
        return 1

    total = filas[0].get("_total")
    print(f"{total} resultado(s) en {time.time()-t0:.1f}s:")
    print(f"{'CÓDIGO':>8}  {'ESTADO':10} {'CONDICIÓN':10} {'UBICACIÓN':34} NOMBRE / RAZÓN SOCIAL")
    print("─" * 118)
    for f in filas:
        cod = str(f.get("codigounico") or "").strip()
        est = str(f.get("estado") or "—")[:10]
        cond = str(f.get("condicion") or "—")[:10]
        ubi = f"{f.get('distrito') or ''}/{f.get('provincia') or ''}/{f.get('departamento') or ''}"[:34]
        nom = str(f.get("nombrerazonsocial") or "")[:55]
        print(f"{cod:>8}  {est:10} {cond:10} {ubi:34} {nom}")
    if total and total > len(filas):
        print(f"… y {total - len(filas)} más (afina la palabra clave)")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # consola Windows
    except Exception:  # noqa: BLE001
        pass
    raise SystemExit(main())
