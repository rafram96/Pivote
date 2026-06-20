"""Re-descarga TODOS los documentos InfoObras de un job ya analizado y rearma el
ZIP. Reusa los `obra_id` del enriquecimiento (NO re-resuelve CUIs ni SUNAT).

Resumible: salta las experiencias cuya carpeta ya tiene archivos, y continúa
ante caídas del portal (registra el fallo y sigue). Útil tras quitar el límite
de descargas (PIVOTE_MAX_DESCARGAS) para completar el ZIP de un job viejo.

Uso:   python -m scripts.redescargar_documentos <job_id>
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from entregables.zip_infoobras import (  # noqa: E402
    construir_zip_infoobras,
    descargar_documentos_obra_por_hito,
)
from scraping.infoobras import _crear_session  # noqa: E402


def _n_archivos(d: Path) -> int:
    return sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


def main(job_id: str) -> None:
    dd = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    espejo = json.loads((dd / f"{job_id}.espejo.json").read_text(encoding="utf-8"))
    enr = json.loads((dd / f"{job_id}.enriquecimiento.json").read_text(encoding="utf-8"))
    base_desc = dd / f"{job_id}.descargas"
    base_desc.mkdir(parents=True, exist_ok=True)

    obras: dict[tuple[int, int], object] = {}
    for k, v in enr.items():
        m = re.match(r"^(\d+):(\d+)$", k)
        if not m or not isinstance(v, dict):
            continue
        oid = (v.get("obra") or {}).get("obra_id")
        if oid:
            obras[(int(m.group(1)), int(m.group(2)))] = oid
    print(f"[redescarga] job {job_id}: {len(obras)} obras con obra_id", flush=True)

    sess = _crear_session()
    descargas: dict[tuple[int, int], Path] = {}
    total = len(obras)
    for i, ((n, e), oid) in enumerate(sorted(obras.items()), 1):
        destino = base_desc / f"P{n}_E{e}"
        if _n_archivos(destino) > 0:
            print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: ya tiene archivos, salto", flush=True)
            descargas[(n, e)] = destino
            continue
        try:
            descargar_documentos_obra_por_hito(oid, destino, session=sess)
            print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: {_n_archivos(destino)} archivos", flush=True)
            descargas[(n, e)] = destino
        except Exception as ex:  # noqa: BLE001 — el portal cae; seguimos
            print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: ERROR {ex!r}", flush=True)

    # incluir cualquier carpeta ya existente que no estuviera en `obras`
    for sub in base_desc.iterdir():
        mm = re.match(r"^P(\d+)_E(\d+)$", sub.name)
        if mm and sub.is_dir():
            descargas.setdefault((int(mm.group(1)), int(mm.group(2))), sub)

    salida = dd / f"{job_id}.infoobras.zip"
    if salida.exists():
        salida.unlink()
    construir_zip_infoobras(espejo, descargas, salida, enriquecimiento=enr)
    mb = salida.stat().st_size / 1e6
    print(f"[redescarga] ZIP rearmado: {salida.name} · {mb:.1f} MB · "
          f"{len(descargas)} experiencias con carpeta", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python -m scripts.redescargar_documentos <job_id>")
        sys.exit(2)
    main(sys.argv[1])
