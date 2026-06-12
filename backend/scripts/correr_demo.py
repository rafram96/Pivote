"""
correr_demo.py — Corre el pipeline REAL (portales en vivo) sobre un espejo.

Es el "pre-corredor" de la demo: deja el job, el enriquecimiento, el Excel
final y las descargas persistidos en PIVOTE_DATA_DIR, de modo que la demo del
panel no dependa de que SUNAT/InfoObras respondan en ese momento.

Uso:
    cd backend
    ../venv/Scripts/python.exe scripts/correr_demo.py <espejo.json> ["Nombre concurso"]
Env:
    PIVOTE_DATA_DIR       destino (def: datos_pivote)
    PIVOTE_MAX_DESCARGAS  nº de obras cuyos documentos se descargan (def: 2)
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from orquestador import Motor, RepositorioArchivos, etapas_reales  # noqa: E402
from schemas import pipeline  # noqa: E402

os.environ.setdefault("PIVOTE_MAX_DESCARGAS", "2")


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python scripts/correr_demo.py <espejo.json> [nombre_concurso]")
        return 2
    espejo_path = Path(sys.argv[1])
    espejo = json.loads(espejo_path.read_text(encoding="utf-8"))
    nombre_concurso = sys.argv[2] if len(sys.argv) > 2 else (
        espejo.get("_meta", {}).get("concurso") or "Concurso demo")

    data_dir = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    repo = RepositorioArchivos(data_dir)

    # concurso (reusa si ya existe uno con la misma nomenclatura)
    concurso = next((c for c in repo.listar_concursos()
                     if c.nomenclatura == nombre_concurso), None)
    if concurso is None:
        concurso = pipeline.Concurso(
            concurso_id=uuid.uuid4().hex[:10], nomenclatura=nombre_concurso,
            creado_en=datetime.now(timezone.utc))
        repo.guardar_concurso(concurso)

    motor = Motor(etapas_reales(data_dir), repo)
    job = motor.crear_job(espejo, concurso_id=concurso.concurso_id)
    job.origen = "mcp"
    repo.guardar(job)

    n_exp = sum(len(p.get("experiencias", [])) for p in espejo.get("profesionales", []))
    print(f"→ job {job.job_id} · {len(espejo.get('profesionales', []))} profesionales · "
          f"{n_exp} experiencias · datos en {data_dir}")
    print("→ corriendo pipeline con portales EN VIVO (esto toma minutos)…")
    t0 = time.time()
    job = motor.correr(job.job_id)
    dur = time.time() - t0

    print(f"\n{'=' * 64}")
    print(f"ESTADO: {job.estado.value.upper()}  ·  {dur/60:.1f} min")
    for e in job.etapas:
        m = e.metrica
        print(f"  {e.etapa.value:<16} {e.estado.value:<16} "
              f"ok={m.items_ok}/{m.items_total} rev={m.items_revision} err={m.items_error}")

    enr = repo.cargar_enriquecimiento(job.job_id)
    vias = Counter(v.get("via") for k, v in enr.items() if ":" in k and not k.startswith("prof:"))
    print(f"\nIdentificación de obras: {dict(vias)}")
    con_paral = [(k, len(v["paralizaciones"])) for k, v in enr.items()
                 if v.get("paralizaciones")]
    print(f"Experiencias con paralizaciones: {len(con_paral)} → {con_paral[:8]}")
    pendientes = [it for it in job.items_revision if not it.resuelto]
    print(f"Pendientes de revisión humana: {len(pendientes)}")
    for it in pendientes[:6]:
        print(f"  · prof {it.n_prof} exp {it.n_exp}: {it.motivo} "
              f"({len(it.candidatos)} candidatos)")
    nocumple = {k: v["cumple_backend"] for k, v in enr.items()
                if k.startswith("prof:") and v.get("cumple_backend")}
    if nocumple:
        print(f"Veredictos invertidos por el recálculo: {nocumple}")
    print(f"\nExcel final: {data_dir / (job.job_id + '.final.xlsx')}")
    print(f"Panel: concurso '{nombre_concurso}' → job {job.job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
