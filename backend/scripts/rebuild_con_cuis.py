"""Rehace un job inyectando CUIs conseguidos a mano (p. ej. experiencias de
educación que la skill dejó sin CUI) y re-corre el pipeline COMPLETO **sin
descarga de documentos** (resolución → InfoObras valorizaciones → SUNAT → reglas
→ Excel). Los documentos se completan después con `redescargar_documentos`
(resumible: no re-baja lo que ya está) y el representante con
`backfill_representante`.

Con CUI explícito la resolución es determinística (PASO 0), así no depende de la
precisión del match por nombre.

Uso:  python -m scripts.rebuild_con_cuis <job_id>
(el mapa de CUIs va inline; ajustar por job)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from orquestador.etapas_reales import EtapaInfoObrasReal, etapas_reales  # noqa: E402
from orquestador.motor import Motor  # noqa: E402
from orquestador.repositorio import RepositorioArchivos  # noqa: E402
from schemas import pipeline  # noqa: E402

# CUIs conseguidos a mano para las 12 experiencias educativas del job Pichanaki.
# P1·E1 (I.E. Téc. Agropecuario Llillinta, 2010) NO se incluye: su única
# inversión registrada en InfoObras es una reparación "Sin Ejecución" (0
# valorizaciones) — adjuntarla sería un match falso; se deja sin cruce.
CUIS: dict[tuple[int, int], str] = {
    (1, 2): "2140935", (1, 3): "2478578", (1, 4): "2319251", (1, 5): "2428518",
    (1, 6): "2533504", (5, 1): "2045607", (5, 2): "2030496", (5, 3): "2399634",
    (6, 1): "2246585", (7, 1): "2140680", (7, 2): "2412677", (7, 3): "2303684",
}


def main(job_id: str) -> None:
    dd = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    repo = RepositorioArchivos(dd)

    # 1) inyectar los CUIs al espejo
    espejo = repo.cargar_espejo(job_id)
    if espejo is None:
        print(f"espejo no encontrado para {job_id}"); sys.exit(1)
    n = 0
    for p in espejo.get("profesionales", []):
        for e in p.get("experiencias", []):
            cui = CUIS.get((p.get("n_prof"), e.get("n")))
            if cui:
                e["cui"] = cui
                n += 1
    repo.guardar_espejo(job_id, espejo)
    print(f"[rebuild] {n} CUIs inyectados al espejo", flush=True)

    # 2) reset: enriquecimiento en blanco + checkpoints borrados → re-corrida total
    repo.guardar_enriquecimiento(job_id, {})
    job = repo.cargar(job_id)
    job.etapas = []
    job.items_revision = []
    job.observaciones = []
    job.estado = pipeline.JobEstado.RECIBIDO
    repo.guardar(job)
    print("[rebuild] checkpoints reseteados", flush=True)

    # 3) motor con la descarga de docs APAGADA (dir_descargas=None en InfoObras)
    etapas = [
        EtapaInfoObrasReal(dir_descargas=None) if isinstance(et, EtapaInfoObrasReal) else et
        for et in etapas_reales(dd)
    ]
    motor = Motor(etapas, repo)
    print("[rebuild] re-corriendo pipeline (sin descarga de docs)...", flush=True)
    job = motor.correr(job_id)
    print(f"[rebuild] estado final: {job.estado.value}", flush=True)

    # 4) reporte de veredictos
    enr = repo.cargar_enriquecimiento(job_id) or {}
    resueltas = sum(1 for k, v in enr.items() if isinstance(v, dict)
                    and ":" in k and (v.get("obra") or {}).get("obra_id"))
    print(f"[rebuild] experiencias con obra resuelta: {resueltas}", flush=True)
    for p in espejo.get("profesionales", []):
        cumple = (p.get("cumple") or "")[:60]
        print(f"   P{p.get('n_prof')} {p.get('nombre','')[:24]:24} · {cumple}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python -m scripts.rebuild_con_cuis <job_id>"); sys.exit(2)
    main(sys.argv[1])
