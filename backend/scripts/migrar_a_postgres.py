"""
Backfill: migra los datos existentes en archivos (DATA_DIR) a PostgreSQL.

Idempotente (upserts): se puede correr N veces; la última corrida gana. Los
binarios (xlsx/zip/certs/descargas) NO se mueven — se quedan en DATA_DIR, que
sigue montado igual. Correr UNA vez al activar PIVOTE_DB_URL en el server:

    cd backend
    PIVOTE_DATA_DIR=/datos PIVOTE_DB_URL=postgresql://... python scripts/migrar_a_postgres.py

(en compose: docker compose exec backend python scripts/migrar_a_postgres.py)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orquestador.repositorio import RepositorioArchivos          # noqa: E402
from orquestador.repositorio_pg import RepositorioPostgres        # noqa: E402


def main() -> int:
    dsn = os.getenv("PIVOTE_DB_URL")
    if not dsn:
        print("falta PIVOTE_DB_URL en el entorno")
        return 1
    data_dir = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    archivos = RepositorioArchivos(data_dir)
    pg = RepositorioPostgres(dsn, dir_datos=data_dir)

    concursos = archivos.listar_concursos()
    for c in concursos:
        pg.guardar_concurso(c)
    print(f"concursos: {len(concursos)}")

    jobs = archivos.listar()
    n_esp = n_enr = n_dec = 0
    for job in jobs:
        pg.guardar(job)
        espejo = archivos.cargar_espejo(job.job_id)
        if espejo is not None:
            pg.guardar_espejo(job.job_id, espejo)   # indexa profesionales de paso
            n_esp += 1
        enr = archivos.cargar_enriquecimiento(job.job_id)
        if enr:
            pg.guardar_enriquecimiento(job.job_id, enr)
            n_enr += 1
        dec = archivos.cargar_decisiones(job.job_id)
        if dec:
            pg.guardar_decisiones(job.job_id, dec)
            n_dec += 1
    print(f"jobs: {len(jobs)} · espejos: {n_esp} · enriquecimientos: {n_enr} · decisiones: {n_dec}")
    print("listo — verifica con el panel y recién entonces archiva los .json (no los borres)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
