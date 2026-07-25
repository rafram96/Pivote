"""
DEMO — Scraping SUNAT + InfoObras para reunión con el cliente.

Corre los dos scrapers que el backend on-prem usará para enriquecer el JSON
de Claude (cruces que Claude NO puede hacer): SUNAT (fecha inscripción → ALT04,
representantes legales → ALT12) e InfoObras (supervisores, avances,
paralizaciones → Paso 5).

Reusa el código de producción de `Alpamayo-InfoObras/src/scraping/` — NO clona.

Genera 3 cosas:
  1. Reporte legible en consola (para correr EN VIVO frente a Manuel).
  2. `docs/demo_scraping_resultado.json` — el JSON crudo consolidado.
  3. `docs/demo_scraping.html` — página con los datos embebidos (para mostrar /
     dejarle a Manuel; funciona standalone, sin servidor).

Uso:
    venv/Scripts/python.exe src/tools/demo_scraping.py
    venv/Scripts/python.exe src/tools/demo_scraping.py --ruc 20304582147 --cui 2283129

Targets por defecto (datos públicos, reales):
  - SUNAT: RUC 20304582147 (INMOBILIARIA ALPAMAYO S.A. — empresa del cliente)
  - InfoObras: CUI 2283129 (hospital ESSALUD en ejecución, S/ 156M, con paralización)
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ALPAMAYO = Path(r"C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras\Alpamayo-InfoObras")
if not ALPAMAYO.exists():
    print(f"ERROR: no se encuentra repo Alpamayo en {ALPAMAYO}", file=sys.stderr)
    sys.exit(1)
sys.path.insert(0, str(ALPAMAYO))

from src.scraping.sunat import (  # noqa: E402
    consultar_ruc,
    HOST,
    FORM_PATH,
    SEARCH_PATH,
    _crear_session_sunat,
    _request_with_retry,
    _fake_captcha_token,
    _detectar_encoding,
)
from src.scraping.infoobras import fetch_by_cui  # noqa: E402

DOCS = Path(__file__).resolve().parents[3] / "docs"

# Targets por defecto
RUC_DEFAULT = "20304582147"
CUI_DEFAULT = "2283129"


# ──────────────────────────────────────────────────────────────────────────
# SUNAT
# ──────────────────────────────────────────────────────────────────────────
def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def fetch_representantes(ruc: str, timeout: float = 20.0) -> list[dict[str, str]]:
    """Obtiene los representantes legales (acción getRepLeg del portal SUNAT).

    Reusa la infraestructura interna del scraper (session TLS + retry + token).
    Devuelve [{documento, nro_documento, nombre, cargo, fecha_desde}, ...].
    """
    session = _crear_session_sunat()
    try:
        r_form = _request_with_retry(
            session, "GET", HOST + FORM_PATH, timeout=timeout,
            description=f"bootstrap repleg {ruc}",
        )
        if r_form is None:
            return []
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": HOST + FORM_PATH, "Origin": HOST,
        }
        body_ruc = {
            "accion": "consPorRuc", "razSoc": "", "nroRuc": ruc, "nrodoc": "",
            "search1": ruc, "search2": "", "search3": "", "tipdoc": "1",
            "rbtnTipo": "1", "codigo": "", "contexto": "ti-it", "modo": "1",
            "token": _fake_captcha_token(),
        }
        r_det = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, data=body_ruc, headers=headers,
            timeout=timeout, description=f"detalle repleg {ruc}",
        )
        if r_det is None:
            return []
        r_det.encoding = _detectar_encoding(r_det.headers.get("Content-Type", ""))
        html_det = r_det.text
        numrnd = re.search(r'name="numRnd"\s+value="([^"]*)"', html_det)
        numrnd_val = numrnd.group(1) if numrnd else ""
        m_raz = re.search(r"\d{11}\s*-\s*([^<]+)<", html_det)
        des_ruc = _strip(m_raz.group(1)) if m_raz else ""

        body_rep = {
            "accion": "getRepLeg", "nroRuc": ruc, "desRuc": des_ruc,
            "contexto": "ti-it", "modo": "1", "numRnd": numrnd_val,
            "token": _fake_captcha_token(),
        }
        r_rep = _request_with_retry(
            session, "POST", HOST + SEARCH_PATH, data=body_rep, headers=headers,
            timeout=timeout, description=f"getRepLeg {ruc}",
        )
        if r_rep is None:
            return []
        r_rep.encoding = _detectar_encoding(r_rep.headers.get("Content-Type", ""))
        html_rep = html_module.unescape(r_rep.text)

        reps: list[dict[str, str]] = []
        for tr in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", html_rep, re.I):
            celdas = [
                _strip(td) for td in
                re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", tr.group(1), re.I)
            ]
            celdas = [c for c in celdas if c]
            # Fila de datos: 5 columnas, la 1ra es tipo de documento
            if len(celdas) == 5 and celdas[0].upper() in ("DNI", "CE", "PASAPORTE", "RUC"):
                reps.append({
                    "documento": celdas[0],
                    "nro_documento": celdas[1],
                    "nombre": celdas[2],
                    "cargo": celdas[3],
                    "fecha_desde": celdas[4],
                })
        return reps
    finally:
        session.close()


def demo_sunat(ruc: str) -> dict[str, Any]:
    print(f"\n  → Consultando RUC {ruc} en SUNAT…")
    empresa = consultar_ruc(ruc)
    if not empresa:
        return {"ok": False, "ruc": ruc, "error": "RUC no encontrado"}
    data = empresa.to_dict()
    print(f"  → Consultando representantes legales…")
    reps = fetch_representantes(ruc)
    data["representantes_legales"] = reps
    data["ok"] = True
    return data


# ──────────────────────────────────────────────────────────────────────────
# InfoObras
# ──────────────────────────────────────────────────────────────────────────
def _d(v) -> Optional[str]:
    return str(v) if v else None


def demo_infoobras(cui: str) -> dict[str, Any]:
    print(f"\n  → Consultando CUI {cui} en InfoObras…")
    obra = fetch_by_cui(cui)
    if obra is None:
        return {"ok": False, "cui": cui, "error": "Obra no encontrada"}

    supervisores = [
        {
            "nombre": f"{s.nombre} {s.apellido_paterno} {s.apellido_materno or ''}".strip(),
            "tipo": s.tipo,
            "tipo_persona": s.tipo_persona,
            "empresa": s.empresa,
            "ruc": s.ruc,
            "fecha_inicio": _d(s.fecha_inicio),
            "fecha_fin": _d(s.fecha_fin),
        }
        for s in obra.supervisores
    ]
    residentes = [
        {
            "nombre": f"{r.nombre} {r.apellido_paterno} {r.apellido_materno or ''}".strip(),
            "fecha_inicio": _d(r.fecha_inicio),
            "fecha_fin": _d(r.fecha_fin),
        }
        for r in obra.residentes
    ]
    avances = [
        {
            "periodo": f"{a.anio}-{a.mes:02d}",
            "estado": a.estado,
            "avance_real": a.avance_fisico_real,
            "avance_programado": a.avance_fisico_programado,
            "dias_paralizado": a.dias_paralizado,
            "tipo_paralizacion": a.tipo_paralizacion,
            "causal": a.causal,
        }
        for a in obra.avances
    ]
    paralizaciones = [
        {"desde": str(ini), "hasta": str(fin)}
        for ini, fin in obra.suspension_periods
    ]
    return {
        "ok": True,
        "cui": obra.cui,
        "obra_id": obra.obra_id,
        "codigo_infobras": obra.codigo_infobras,
        "nombre": obra.nombre,
        "estado": obra.estado,
        "entidad": obra.entidad,
        "ejecutor": obra.ejecutor,
        "ruc_ejecutor": obra.ruc_ejecutor,
        "monto_contrato": obra.monto_contrato,
        "fecha_inicio": _d(obra.fecha_inicio),
        "fecha_fin": _d(obra.fecha_fin),
        "supervisores": supervisores,
        "residentes": residentes,
        "avances": avances,
        "paralizaciones": paralizaciones,
    }


# ──────────────────────────────────────────────────────────────────────────
# Reporte de consola
# ──────────────────────────────────────────────────────────────────────────
def _linea(c: str = "─", n: int = 72) -> str:
    return c * n


def reporte_consola(sunat: dict, obra: dict) -> None:
    print("\n" + _linea("═"))
    print("  SUNAT  ·  e-consultaruc.sunat.gob.pe")
    print(_linea("═"))
    if not sunat.get("ok"):
        print(f"  ✗ {sunat.get('error')}")
    else:
        print(f"  RUC            {sunat['ruc']}")
        print(f"  Razón social   {sunat['razon_social']}")
        print(f"  Estado         {sunat['estado']} · {sunat['condicion']}")
        print(f"  Inscripción    {sunat['fecha_inscripcion']}   ← alimenta ALT04 (antigüedad)")
        print(f"  Domicilio      {(sunat.get('domicilio_fiscal') or '')[:60]}")
        reps = sunat.get("representantes_legales") or []
        print(f"\n  Representantes legales ({len(reps)})   ← alimenta ALT12 (firmante ≠ rep. legal)")
        for r in reps:
            print(f"    • {r['nombre']} — {r['cargo']} ({r['documento']} {r['nro_documento']}, desde {r['fecha_desde']})")

    print("\n" + _linea("═"))
    print("  INFOOBRAS  ·  infobras.contraloria.gob.pe")
    print(_linea("═"))
    if not obra.get("ok"):
        print(f"  ✗ {obra.get('error')}")
    else:
        monto = obra.get("monto_contrato")
        monto_s = f"S/ {monto:,.2f}" if isinstance(monto, (int, float)) else "—"
        print(f"  CUI            {obra['cui']}   (ObraId {obra['obra_id']})")
        print(f"  Obra           {(obra.get('nombre') or '')[:62]}")
        print(f"  Estado         {obra['estado']}")
        print(f"  Entidad        {obra.get('entidad')}")
        print(f"  Ejecutor       {obra.get('ejecutor')}")
        print(f"  Monto contrato {monto_s}")
        print(f"\n  Supervisores ({len(obra['supervisores'])}):")
        for s in obra["supervisores"]:
            print(f"    • {s['nombre']} — {s['tipo']} ({s.get('empresa') or 's/empresa'})")
        print(f"\n  Avances mensuales: {len(obra['avances'])} períodos registrados")
        parz = obra["paralizaciones"]
        print(f"  Paralizaciones: {len(parz)}   ← alimenta Paso 5 (días efectivos)")
        for p in parz:
            print(f"    • {p['desde']} → {p['hasta']}")
    print("\n" + _linea("═"))
    print("  Estos cruces los hace el BACKEND ON-PREM (sin cloud).")
    print("  Claude extrae el PDF; el backend los agrega automáticamente.")
    print(_linea("═") + "\n")


# ──────────────────────────────────────────────────────────────────────────
# HTML
# ──────────────────────────────────────────────────────────────────────────
def generar_html(payload: dict, destino: Path) -> None:
    plantilla = (Path(__file__).parent / "demo_scraping_template.html").read_text(encoding="utf-8")
    blob = json.dumps(payload, ensure_ascii=False)
    html = plantilla.replace("/*__DATA__*/null", blob)
    destino.write_text(html, encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ruc", default=RUC_DEFAULT)
    ap.add_argument("--cui", default=CUI_DEFAULT)
    ap.add_argument("--no-html", action="store_true", help="No regenerar el HTML")
    args = ap.parse_args()

    print(_linea("━"))
    print("  DEMO — Scraping backend on-prem  ·  SUNAT + InfoObras")
    print("  (reusa src/scraping de Alpamayo-InfoObras, sin clonar código)")
    print(_linea("━"))

    sunat = demo_sunat(args.ruc)
    obra = demo_infoobras(args.cui)

    reporte_consola(sunat, obra)

    payload = {"sunat": sunat, "infoobras": obra}

    DOCS.mkdir(exist_ok=True)
    json_path = DOCS / "demo_scraping_resultado.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  JSON  → {json_path}")

    if not args.no_html:
        html_path = DOCS / "demo_scraping.html"
        try:
            generar_html(payload, html_path)
            print(f"  HTML  → {html_path}")
        except FileNotFoundError:
            print("  (plantilla HTML no encontrada — se omitió el HTML)")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
