"""Limpia el campo `cargo` de los profesionales en espejos YA generados.

Saca la correspondencia con el cargo oficial de las bases que la skill incrustaba
dentro del nombre — "… (cargo bases N°5 ESPECIALISTA EN ESTRUCTURAS)" — a campos
atómicos (`cargo_bases_num`, `cargo_bases_nombre`), dejando `cargo` con la etiqueta
limpia. Además **regenera el Excel final** del job (mismo generador del pipeline,
sin tocar red) para que el entregable salga limpio.

Idempotente: un cargo ya limpio no se toca. Las extracciones nuevas ya salen
separadas (ver agent-evaluador + schema con `cargo_bases_num`) y el ingest del
motor normaliza por si acaso — esto es solo para los jobs de prueba ya en disco.

Uso:  python -m scripts.limpiar_cargos_espejo            # toda la carpeta de datos
      python -m scripts.limpiar_cargos_espejo <job_id>   # solo ese job
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from entregables import regenerar_excel_final  # noqa: E402
from schemas.cargo import normalizar_cargos_espejo  # noqa: E402


def _revisiones(job: dict) -> dict:
    """{(n_prof, n_exp): motivo} de los items aún sin resolver — para que la hoja
    del profesional muestre 'EN REVISIÓN' igual que en el pipeline."""
    rev: dict = {}
    for it in job.get("items_revision", []):
        if not it.get("resuelto") and it.get("n_exp") is not None:
            rev.setdefault((it["n_prof"], it["n_exp"]), it.get("motivo", ""))
    return rev


def procesar(esp_path: Path) -> tuple[int, bool]:
    """Limpia un espejo y regenera su Excel si hay datos. → (cargos_limpiados, regen)."""
    espejo = json.loads(esp_path.read_text(encoding="utf-8"))
    n = normalizar_cargos_espejo(espejo)
    if not n:
        return 0, False
    esp_path.write_text(json.dumps(espejo, ensure_ascii=False, indent=2), encoding="utf-8")

    dd = esp_path.parent
    job_id = esp_path.name.split(".")[0]
    enr_path = dd / f"{job_id}.enriquecimiento.json"
    xlsx = dd / f"{job_id}.final.xlsx"
    if not (enr_path.exists() and xlsx.exists() and xlsx.stat().st_size > 0):
        return n, False
    try:
        enr = json.loads(enr_path.read_text(encoding="utf-8")) or {}
        job_path = dd / f"{job_id}.job.json"
        rev = _revisiones(json.loads(job_path.read_text(encoding="utf-8"))) if job_path.exists() else {}
        regenerar_excel_final(espejo, enr, xlsx, rev)
        return n, True
    except Exception as e:  # noqa: BLE001 — un job roto no debe abortar el lote
        print(f"  ! {job_id}: cargos limpios pero no se pudo regenerar Excel ({e})", flush=True)
        return n, False


def main(job_id: str | None) -> None:
    dd = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    patron = f"{job_id}.espejo.json" if job_id else "*.espejo.json"
    archivos = sorted(dd.glob(patron))
    tot_files = tot_profs = tot_xlsx = 0
    for f in archivos:
        n, regen = procesar(f)
        if n:
            tot_files += 1
            tot_profs += n
            tot_xlsx += int(regen)
            print(f"  {f.name}: {n} cargos limpiados{' + Excel regenerado' if regen else ''}", flush=True)
    print(f"[limpiar-cargos] {tot_files} espejos · {tot_profs} cargos · {tot_xlsx} Excel "
          f"regenerados (de {len(archivos)} archivos)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
