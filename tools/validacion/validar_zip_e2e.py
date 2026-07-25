"""
Validación END-TO-END del ZIP de sustentos InfoObras (punto 1 de "qué falta").

Ejercita la RUTA ACTUAL de producción —no el tool plano viejo— de punta a punta
con descargas REALES del portal:

    descargar_documentos_obra_por_hito()   → árbol por hito en disco
    construir_zip_infoobras()              → ZIP de 5 niveles
    inspección del ZIP                     → estructura + tamaños + vacíos

Es la pieza que nunca se había corrido completa (las re-corridas usaban
PIVOTE_MAX_DESCARGAS=0). Acotada: 1 obra. Datos públicos (.gob.pe), solo lectura.

Uso:
    python tools/validar_zip_e2e.py                 # obra 72056 (prototipo, 7 docs)
    python tools/validar_zip_e2e.py --obra-id 33900 # otra obra
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from entregables.zip_infoobras import (  # noqa: E402
    construir_zip_infoobras,
    descargar_documentos_obra_por_hito,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--obra-id", default="72056")
    ap.add_argument("--cargo", default="JEFE DE SUPERVISIÓN")
    ap.add_argument("--proyecto", default="MEJORAMIENTO DE LOS SERVICIOS DE SALUD / OBRA DE PRUEBA")
    args = ap.parse_args()

    trabajo = RAIZ / "tools" / f"_validacion_zip_{args.obra_id}"
    descargas = trabajo / "descarga"
    if trabajo.exists():
        shutil.rmtree(trabajo)
    descargas.mkdir(parents=True)

    print(f"→ 1/3 Descargando obra {args.obra_id} POR HITO (portal en vivo)…")
    res = descargar_documentos_obra_por_hito(args.obra_id, descargas)
    inv = res["inventario"]
    print(f"   descargados={res['descargados']}  fallidos={res['fallidos']}")
    print(f"   hitos con archivos: {len(inv['avances'])}  ·  "
          f"obra-level docs: {len(inv['obra']['documentos'])}")
    for av in inv["avances"]:
        print(f"     · {av['anio']}-{av['mes']:<12} {len(av['documentos'])} doc(s)")

    print("\n→ 2/3 Construyendo el ZIP (árbol Proyecto→Profesional→Exp→hito)…")
    espejo = {
        "_meta": {"concurso": "VALIDACIÓN E2E (obra real)", "postor": "—"},
        "profesionales": [{
            "n_prof": 1, "cargo": args.cargo,
            "experiencias": [{"n": 1, "proyecto": args.proyecto, "cui": args.obra_id}],
        }],
    }
    salida = trabajo / "sustentos.zip"
    construir_zip_infoobras(espejo, {(1, 1): descargas}, salida)
    print(f"   ZIP → {salida.relative_to(RAIZ)}  ({salida.stat().st_size:,} bytes)")

    print("\n→ 3/3 Inspeccionando el ZIP…")
    vacios = 0
    with zipfile.ZipFile(salida) as zf:
        infos = sorted(zf.infolist(), key=lambda i: i.filename)
        for i in infos:
            marca = "  ⚠ VACÍO" if i.file_size == 0 and not i.filename.endswith("/") else ""
            if marca:
                vacios += 1
            print(f"   {i.file_size:>10,}  {i.filename}{marca}")
        total = sum(i.file_size for i in infos)
    print(f"\n   {len(infos)} entradas · {total:,} bytes sin comprimir · vacíos={vacios}")

    ok = res["descargados"] > 0 and vacios == 0
    print("\n" + ("✅ OK — descargas reales, ZIP bien formado, sin archivos vacíos."
                  if ok else "❌ REVISAR — hubo fallos o archivos vacíos."))
    print(f"(carpeta de trabajo: {trabajo.relative_to(RAIZ)} — borrar tras revisar)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
