"""
Regenera el Excel FINAL del backend para un job ya corrido, leyendo su espejo +
enriquecimiento persistidos (sin re-correr scrapers). Útil para ver cambios de
formato del Excel sobre data real ya obtenida.

Uso: python tools/utils/regenerar_excel_final.py [job_id] [dir_datos] [salida]
"""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from entregables import desempaquetar_enriquecimiento, generar_excel_final  # noqa: E402

job_id = sys.argv[1] if len(sys.argv) > 1 else "4816fbdf3bea"
dir_datos = Path(sys.argv[2]) if len(sys.argv) > 2 else RAIZ / "backend" / "datos_pivote"


def _leer(nombre: str) -> dict:
    """El job vive en `<dir_datos>/<job_id>/<nombre>.json` (layout vigente: una
    carpeta por job); se acepta el layout viejo (`<job_id>.<nombre>.json`) para
    poder regenerar jobs antiguos."""
    for ruta in (dir_datos / job_id / f"{nombre}.json",
                 dir_datos / f"{job_id}.{nombre}.json"):
        if ruta.exists():
            return json.loads(ruta.read_text(encoding="utf-8"))
    if nombre == "job":
        return {}                      # opcional: sin él solo se pierden los avisos
    raise SystemExit(f"No se halló el {nombre} del job {job_id} en {dir_datos}")


espejo = _leer("espejo")
enrich = _leer("enriquecimiento")

# EL MISMO desempaquetado que usa EtapaExcelReal, no una copia: mientras este
# script duplicaba el armado a mano se quedó atrás del real (no copiaba
# `obra_nombre`, así que la herramienta con la que se revisa el Excel sobre datos
# reales afirmaba "InfoObras no devolvió el nombre" — falso: el nombre sí estaba
# en el enriquecimiento).
paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enrich)

# Las experiencias en revisión (motivo + acción del ItemRevision) también las pasa
# EtapaExcelReal: sin ellas el Excel regenerado no muestra los avisos y parece que
# no hubiera ninguno.
revisiones: dict[tuple[int, int], tuple[str, str | None]] = {}
for it in _leer("job").get("items_revision") or []:
    if not it.get("resuelto") and it.get("n_exp") is not None:
        revisiones.setdefault((it["n_prof"], it["n_exp"]),
                              (it.get("motivo") or "", it.get("accion_sugerida")))
for k, enr in enrich.items():
    if isinstance(enr, dict) and str(enr.get("via") or "").upper() == "PRIVADA" \
            and ":" in k and not k.startswith("prof:"):
        np_, ne = (int(x) for x in k.split(":"))
        revisiones.setdefault((np_, ne), ("[PRIVADA]", None))

salida = (Path(sys.argv[3]) if len(sys.argv) > 3
          else dir_datos / job_id / "muestra.xlsx")
salida.parent.mkdir(parents=True, exist_ok=True)
generar_excel_final(espejo, salida, paral, cuis, fichas, revisiones, sunat)
print(f"Excel regenerado: {salida}")
print(f"  cuadros SUNAT: {len(sunat)} · fichas (obra): {len(fichas)} · "
      f"en revisión: {len(revisiones)} · profesionales: "
      f"{len(espejo.get('profesionales', []))}")
