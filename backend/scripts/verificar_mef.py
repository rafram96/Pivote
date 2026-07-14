"""
Regresión del módulo de verificación de expedientes contra el MEF (scraping/mef.py).

Corre el pipeline REAL (fetch 08-A + contratos DWH + contraste) sobre una lista de
CUIs y reporta la cobertura: cuántos exponen contrato de expediente y resolución.
Read-only (GET/POST públicos, sin captcha). Reutilizable en el server para re-medir
cuando cambie el portal.

Uso:
    python scripts/verificar_mef.py                 # los 13 CUIs de la validación 13-jul
    python scripts/verificar_mef.py 2324482 2427358 # CUIs a medida
    python scripts/verificar_mef.py --descargar 2324482   # además baja los PDFs a /tmp
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraping import mef  # noqa: E402

# Los 13 CUIs reales de la validación en vivo (salud, educación, saldos, reformulados)
CUIS_DEFAULT = ["2303684", "2564441", "2107892", "2427358", "2088781", "2337618",
                "2148076", "2324196", "2564829", "2255793", "2140959", "2448758",
                "2324482"]


def _snip_de(cui, consulta) -> str:
    """El codSnip de la obra en InfoObras (mejora la cobertura del DWH de contratos).
    Best-effort: '' si InfoObras no responde o no lo trae."""
    try:
        for o in consulta.por_codigo(cui) or []:
            s = str(o.get("codSnip") or "").strip()
            if s and s != cui:
                return s
    except Exception:  # noqa: BLE001
        pass
    return ""


def main(argv: list[str]) -> int:
    from resolucion.cui import ConsultaInfoObras
    descargar = "--descargar" in argv
    cuis = [a for a in argv if a.isdigit()] or CUIS_DEFAULT
    consulta = ConsultaInfoObras()

    print(f"Regresión MEF · {len(cuis)} CUIs (SNIP vía InfoObras)\n" + "=" * 78)
    ok = con_contrato = con_resol = 0
    for cui in cuis:
        snip = _snip_de(cui, consulta)
        exp = {"cui": cui}   # sin certificado: mide cobertura, no el match contra el cert
        b = mef.verificar_cui(exp, cui, snip)
        verificado = b.get("verificado_en_mef")
        cn = b.get("contrato") or {}
        rs = b.get("resolucion") or {}
        tiene_ct = bool(cn.get("numero"))
        tiene_rs = rs.get("veredicto") == "ok"
        ok += bool(verificado)
        con_contrato += tiene_ct
        con_resol += tiene_rs
        estado = "OK " if verificado else "—  "
        ct = f"{cn.get('numero','—'):18} {(cn.get('objeto') or '')[:22]:22}" if tiene_ct else f"{'(sin contrato)':41}"
        rsn = rs.get("numero") or ("(sin resolución)" if not tiene_rs else "?")
        print(f"  {estado} CUI {cui} | {ct} | res: {rsn}")
        if descargar and verificado:
            d = Path(tempfile.mkdtemp()) / f"MEF_{cui}"
            r = mef.descargar_documentos_expediente(cui, d)
            print(f"        ↳ descargados: {r}  → {d}")

    n = len(cuis)
    print("=" * 78)
    print(f"RESUMEN · {n} CUIs · verificados en MEF: {ok}/{n} ({ok*100//n}%) · "
          f"con contrato: {con_contrato}/{n} · con resolución: {con_resol}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
