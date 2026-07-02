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
        descargas_estado = j.get("descargas_estado", "?")
    except Exception:
        estado, descargas_estado = "?", "?"

    enr = json.load(open(os.path.join(base, f"{job}.enriquecimiento.json"), encoding="utf-8"))
    # La descarga se dispara para TODA experiencia que tuvo un obra_id resuelto EN
    # ALGÚN MOMENTO — no solo las que terminan "no en revisión": una experiencia puede
    # resolver el CUI (dispara la descarga) y RECIÉN DESPUÉS la etapa InfoObras la manda
    # a revisión por falta de cobertura. Filtrar por el resultado final subestimaba el
    # total (denominador falso) y el conteo de carpetas lo superaba.
    bajan = [x for x in todas
             if isinstance(enr.get(f"{x[0]}:{x[1]}"), dict) and enr[f"{x[0]}:{x[1]}"].get("obra")]
    faltan = [x for x in bajan if x not in carpetas]

    print(f"job {job} · estado: {estado} · descargas: {descargas_estado}")
    print(f"experiencias con obra resuelta (bajan): {len(bajan)} · {len(todas) - len(bajan)} no bajan (sin obra)")
    print(f"descargadas: {len(carpetas)}/{len(bajan)} · faltan por empezar: {len(faltan)} {sorted(faltan)}")

    # "terminado" es descargas_estado, NO estado del job (el job pasa a
    # requiere_revision/completado con las descargas AÚN en background).
    if descargas_estado == "en_progreso" and carpetas and faltan:
        ini = min(carpetas.values())
        transcurrido = time.time() - ini
        prom = transcurrido / max(1, len(carpetas) - 1)  # la última carpeta está en curso
        eta = prom * (len(faltan) + 1)
        print(f"~{transcurrido/60:.0f} min descargando · ETA resto: "
              f"~{eta/60:.0f} min (aprox; las obras de hospital pesan 10-100x más que las chicas)")
    elif descargas_estado == "listas":
        print("→ descargas terminadas (ZIP completo)")
    elif descargas_estado == "error":
        print("→ descargas terminaron con error — revisa los logs del backend")
    else:
        print(f"→ descargas: {descargas_estado}")


if __name__ == "__main__":
    main()
