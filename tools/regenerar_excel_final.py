"""
Regenera el Excel FINAL del backend para un job ya corrido, leyendo su espejo +
enriquecimiento persistidos (sin re-correr scrapers). Útil para ver cambios de
formato del Excel sobre data real ya obtenida.

Uso: python tools/regenerar_excel_final.py [job_id] [dir_datos]
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from entregables import generar_excel_final  # noqa: E402

job_id = sys.argv[1] if len(sys.argv) > 1 else "4816fbdf3bea"
dir_datos = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "datos_pivote"

espejo = json.loads((dir_datos / f"{job_id}.espejo.json").read_text(encoding="utf-8"))
enrich = json.loads((dir_datos / f"{job_id}.enriquecimiento.json").read_text(encoding="utf-8"))

# Mismo armado que EtapaExcelReal
paral, cuis, fichas, sunat = {}, {}, {}, {}
for k, enr in enrich.items():
    if ":" not in k or k.startswith("prof:") or not isinstance(enr, dict):
        continue
    np_, ne = (int(x) for x in k.split(":"))
    if enr.get("paralizaciones"):
        paral[(np_, ne)] = enr["paralizaciones"]
    if enr.get("cui"):
        cuis[(np_, ne)] = enr["cui"]
    if enr.get("sunat"):
        sunat[(np_, ne)] = enr["sunat"]
    if enr.get("obra_ficha") or enr.get("valorizaciones"):
        fichas[(np_, ne)] = {**(enr.get("obra_ficha") or {}),
                             "valorizaciones": enr.get("valorizaciones") or [],
                             "modificaciones_plazo": enr.get("modificaciones_plazo") or []}

salida = dir_datos / f"{job_id}.muestra.xlsx"
generar_excel_final(espejo, salida, paral, cuis, fichas, {}, sunat)
print(f"Excel regenerado: {salida}")
print(f"  cuadros SUNAT: {len(sunat)} · fichas (obra): {len(fichas)} · profesionales: "
      f"{len(espejo.get('profesionales', []))}")
