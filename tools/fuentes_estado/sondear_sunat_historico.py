"""
Sonda de la consulta "Información Histórica" de SUNAT (issue #30, punto 4).

Objetivo: descubrir la ACCIÓN del portal que devuelve el histórico del
contribuyente (razón social / condición / domicilio fiscal con sus vigencias),
igual que `getRepLeg` devuelve los representantes legales, y guardar dumps HTML
reales para escribir el parser con test offline.

Fase 1 (descubrir): baja la página de detalle del RUC y lista todas las acciones
que los botones del portal disparan (cada consulta secundaria es un <form> con
`<input type="hidden" name="accion" value="...">`).
Fase 2 (probar): postea cada acción candidata reusando `desRuc` de la página de
detalle, guarda el HTML y resume las tablas que devuelve.

HALLAZGOS DEL SONDEO (25-jul-2026) — ver docs del issue #30:
  · acción = `getinfHis` (así, con "inf" en minúscula); `numRnd` vacío funciona.
  · la respuesta declara `charset=ISO-8859-1` en el header PERO los bytes son
    UTF-8 → hay que forzar utf-8, `_detectar_encoding` la rompe (NICOLÃS).
  · devuelve 3 tablas fijas y en orden: razón social / condición / domicilio.
    Sin datos, la 1.ª fila dice "No hay Información".
  · RUC inexistente → página de error genérica del portal (~1.9 KB), sin tablas.

Datos públicos (consulta RUC SUNAT), solo lectura.

Uso:
    python tools/fuentes_estado/sondear_sunat_historico.py 20606391812 20573023481
    python tools/fuentes_estado/sondear_sunat_historico.py            # RUC del issue
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraping.sunat import (  # noqa: E402
    HOST, FORM_PATH, SEARCH_PATH,
    _crear_session_sunat, _detectar_encoding, _fake_captcha_token,
    _request_with_retry, _strip_tags,
)

DUMP = RAIZ / "tools" / "_sonda_sunat_hist"

# RUC de la captura del cliente (Consorcio San Nicolás) — el issue lo cita.
RUC_DEFAULT = "20606391812"


def _guardar(nombre: str, html: str) -> Path:
    DUMP.mkdir(parents=True, exist_ok=True)
    ruta = DUMP / nombre
    ruta.write_text(html, encoding="utf-8", errors="replace")
    return ruta


def bajar_detalle(session, ruc: str) -> str:
    """POST consPorRuc → HTML de la ficha (de ahí salen numRnd y los botones)."""
    r_form = _request_with_retry(session, "GET", HOST + FORM_PATH,
                                 timeout=20, description="bootstrap")
    if r_form is None or r_form.status_code >= 400:
        raise SystemExit("no se pudo bootstrapear la sesión SUNAT")

    body = {
        "accion": "consPorRuc", "razSoc": "", "nroRuc": ruc, "nrodoc": "",
        "search1": ruc, "search2": "", "search3": "", "tipdoc": "1",
        "rbtnTipo": "1", "codigo": "", "contexto": "ti-it", "modo": "1",
        "token": _fake_captcha_token(),
    }
    r = _request_with_retry(
        session, "POST", HOST + SEARCH_PATH, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Referer": HOST + FORM_PATH, "Origin": HOST},
        timeout=20, description=f"detalle {ruc}")
    if r is None or r.status_code >= 400:
        raise SystemExit("no se pudo bajar el detalle del RUC")
    r.encoding = _detectar_encoding(r.headers.get("Content-Type", ""))
    return r.text


def acciones_disponibles(html: str) -> list[tuple[str, str]]:
    """Extrae (accion, etiqueta-del-botón) de la ficha de detalle.

    Cada consulta secundaria del portal (Información Histórica, Deuda Coactiva,
    Representantes…) es un <form> propio con `<input type="hidden" name="accion"
    value="...">` y el <button> que lo submitea dentro del mismo form.
    """
    import html as html_module
    vistos: dict[str, str] = {}
    for m in re.finditer(r"<form[\s\S]*?</form>", html, re.I):
        bloque = m.group(0)
        m_acc = re.search(r'name="accion"\s+value="([^"]*)"', bloque)
        if not m_acc:
            continue
        m_btn = re.search(r"<button[^>]*>([\s\S]*?)</button>", bloque, re.I)
        etiqueta = html_module.unescape(_strip_tags(m_btn.group(1))) if m_btn else ""
        vistos.setdefault(m_acc.group(1), etiqueta or "(sin etiqueta)")
    # fallback: acciones seteadas desde JS (por si el portal cambia de patrón)
    for acc in re.findall(r"accion(?:\.value)?\s*=\s*[\"']([\w]+)[\"']", html):
        vistos.setdefault(acc, "(solo en JS)")
    return sorted(vistos.items())


def probar_accion(session, ruc: str, accion: str, numRnd: str, desRuc: str) -> str:
    """Postea una acción del portal reusando el contexto de la ficha.

    OJO: la respuesta de `getinfHis` declara ISO-8859-1 pero manda UTF-8 —
    se decodifica a mano, NO con `_detectar_encoding`.
    """
    body = {
        "accion": accion, "nroRuc": ruc, "desRuc": desRuc,
        "contexto": "ti-it", "modo": "1", "numRnd": numRnd,
        "token": _fake_captcha_token(),
    }
    r = _request_with_retry(
        session, "POST", HOST + SEARCH_PATH, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Referer": HOST + FORM_PATH, "Origin": HOST},
        timeout=20, description=f"{accion} {ruc}")
    if r is None or r.status_code >= 400:
        return ""
    return r.content.decode("utf-8", errors="replace")


def resumir_tablas(html: str) -> list[list[list[str]]]:
    """Devuelve las tablas del histórico como listas de filas de celdas."""
    import html as html_module
    decoded = html_module.unescape(html)
    tablas = []
    for t in re.finditer(r"<table[\s\S]*?</table>", decoded, re.I):
        filas = []
        for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", t.group(0), re.I):
            filas.append([
                _strip_tags(c)
                for c in re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr.group(1), re.I)
            ])
        tablas.append(filas)
    return tablas


def main() -> None:
    rucs = sys.argv[1:] or [RUC_DEFAULT]
    session = _crear_session_sunat()
    try:
        for ruc in rucs:
            print(f"\n═══════════ RUC {ruc} ═══════════")
            html = bajar_detalle(session, ruc)
            _guardar(f"{ruc}_00_detalle.html", html)

            m_rnd = re.search(r'name="numRnd"\s+value="([^"]*)"', html)
            m_raz = re.search(r"\d{11}\s*-\s*([^<]+)<", html)
            numRnd = m_rnd.group(1) if m_rnd else ""
            desRuc = _strip_tags(m_raz.group(1)) if m_raz else ""
            print(f"detalle: {len(html)} chars · numRnd={numRnd!r} · desRuc={desRuc!r}")

            acciones = acciones_disponibles(html)
            print("── acciones que ofrece la ficha ──")
            for acc, etiqueta in acciones:
                print(f"  {acc:<24} {etiqueta}")

            candidatas = [a for a, _ in acciones if re.search(r"his", a, re.I)]
            print(f"── candidatas a histórico: {candidatas or '(ninguna)'} ──")
            for acc in candidatas:
                resp = probar_accion(session, ruc, acc, numRnd, desRuc)
                ruta = _guardar(f"{ruc}_{acc}.html", resp)
                print(f"  {acc}: {len(resp)} chars → {ruta.name}")
                for i, filas in enumerate(resumir_tablas(resp), 1):
                    cab = filas[0] if filas else []
                    print(f"    tabla {i} {cab} · {max(0, len(filas) - 1)} fila(s)")
                    for f in filas[1:]:
                        print(f"       {f}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
