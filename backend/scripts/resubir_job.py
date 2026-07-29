"""Re-sube un job YA existente al backend para re-correr el pipeline con el código
actual (sin re-correr la skill). Crea un concurso nuevo y postea el espejo + Excel
guardados en disco. Útil para aplicar un fix del backend a una propuesta ya analizada.

Uso:  python scripts/resubir_job.py <job_id> [serverUrl]

Tip: para verificar RÁPIDO sin re-bajar los documentos de InfoObras (GBs), arranca
el backend con la variable PIVOTE_MAX_DESCARGAS=0 — la resolución de CUI y los días
efectivos igual se calculan; solo se omite la descarga de documentos al ZIP.
"""
import os
import sys

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if len(sys.argv) < 2:
    sys.exit("uso: python scripts/resubir_job.py <job_id> [serverUrl]")
job_id = sys.argv[1]
url = (sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8001").rstrip("/")
base = os.path.join(os.path.dirname(__file__), "..", "datos_pivote")


def _hallar(nombre: str, ext: str) -> str:
    """Layout vigente (`<job>/<nombre>.<ext>`, carpeta por job) con fallback al
    viejo (`<job>.<nombre>.<ext>` plano) — mismo criterio que
    tools/utils/regenerar_excel_final.py."""
    for p in (os.path.join(base, job_id, f"{nombre}.{ext}"),
              os.path.join(base, f"{job_id}.{nombre}.{ext}")):
        if os.path.exists(p):
            return p
    sys.exit(f"no existe {nombre}.{ext} para el job {job_id} (ni layout carpeta ni plano)")


esp = _hallar("espejo", "json")
xls = _hallar("claude", "xlsx")

cid = requests.post(f"{url}/api/pivote/concursos",
                    json={"nomenclatura": f"REPLAY {job_id}"}, timeout=30).json()["concurso_id"]
with open(esp, "rb") as fe, open(xls, "rb") as fx:
    r = requests.post(f"{url}/api/pivote/analizar",
                      data={"concurso_id": cid, "origen": "replay"},
                      files={"espejo": fe, "excel": fx}, timeout=120)
print("HTTP", r.status_code)
try:
    out = r.json()
    print("nuevo job_id:", out.get("job_id"), "· concurso:", cid)
except Exception:
    print(r.text[:400])
