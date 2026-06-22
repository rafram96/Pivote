"""Avance de las descargas InfoObras de un job + ETA aproximado.

La barra del panel cuenta etapas (8), así que se queda clavada en ~38% durante
toda la fase de descargas (que es la más larga). Este script mide el avance real
por experiencias: cuántas obras ya se bajaron y cuántas faltan.

Uso:  python scripts/avance_descargas.py <job_id>
"""
import json
import os
import sys
import time

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows sin -X utf8
except Exception:
    pass

API = os.environ.get("PIVOTE_API", "http://127.0.0.1:8001")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python scripts/avance_descargas.py <job_id>")
    job = sys.argv[1]
    base = os.path.join(os.path.dirname(__file__), "..", "datos_pivote")
    desc = os.path.join(base, f"{job}.descargas")

    esp = json.load(open(os.path.join(base, f"{job}.espejo.json"), encoding="utf-8"))
    todas = [(p["n_prof"], e["n"]) for p in esp["profesionales"] for e in p.get("experiencias", [])]

    carpetas: dict[tuple[int, int], float] = {}
    if os.path.isdir(desc):
        for d in os.listdir(desc):
            if d.startswith("P") and "_E" in d:
                try:
                    a, b = d[1:].split("_E")
                    carpetas[(int(a), int(b))] = os.path.getmtime(os.path.join(desc, d))
                except ValueError:
                    pass

    try:
        j = requests.get(f"{API}/api/pivote/jobs/{job}", timeout=8).json()
        estado = j.get("estado", "?")
        rev = {(it["n_prof"], it["n_exp"]) for it in j.get("items_revision", []) if not it.get("resuelto")}
    except Exception:
        estado, rev = "?", set()

    bajan = [x for x in todas if x not in rev]
    faltan = [x for x in bajan if x not in carpetas]

    print(f"job {job} · estado: {estado}")
    print(f"experiencias: {len(bajan)} bajan · {len(rev)} en revisión (no bajan)")
    print(f"descargadas: {len(carpetas)}/{len(bajan)} · faltan por empezar: {len(faltan)} {sorted(faltan)}")

    if estado == "en_proceso" and carpetas and faltan:
        ini = min(carpetas.values())
        transcurrido = time.time() - ini
        prom = transcurrido / max(1, len(carpetas) - 1)  # la última carpeta está en curso
        eta = prom * (len(faltan) + 1)
        print(f"~{transcurrido/60:.0f} min descargando · ETA resto: "
              f"~{eta/60:.0f} min (aprox; las obras de hospital pesan 10-100x más que las chicas)")
    elif estado != "en_proceso":
        print("→ descargas terminadas (el job ya pasó de la etapa InfoObras)")


if __name__ == "__main__":
    main()
