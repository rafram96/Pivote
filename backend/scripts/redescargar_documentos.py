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

from datetime import date  # noqa: E402

from entregables.zip_infoobras import (  # noqa: E402
    construir_zip_infoobras,
    descargar_documentos_obra_por_hito,
    descargar_informes_control,
)
from scraping.infoobras import _crear_session  # noqa: E402


def _n_archivos(d: Path) -> int:
    return sum(1 for p in d.rglob("*") if p.is_file()) if d.is_dir() else 0


def _fecha(s) -> date | None:
    """'YYYY-MM-DD…' → date. Parciales/sentinels (POR VERIFICAR) → None."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s or ""))
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _periodos_exp(espejo: dict) -> dict[tuple[int, int], tuple]:
    """{(n_prof, n_exp): (fecha_ini, fecha_fin)} desde el espejo, para filtrar
    los informes de control por el periodo de cada experiencia."""
    out: dict[tuple[int, int], tuple] = {}
    for p in espejo.get("profesionales", []):
        np_ = p.get("n_prof")
        for e in p.get("experiencias", []):
            out[(np_, e.get("n"))] = (_fecha(e.get("fecha_inicial")), _fecha(e.get("fecha_final")))
    return out


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

    periodos = _periodos_exp(espejo)
    sess = _crear_session()
    descargas: dict[tuple[int, int], Path] = {}
    total = len(obras)
    for i, ((n, e), oid) in enumerate(sorted(obras.items()), 1):
        destino = base_desc / f"P{n}_E{e}"
        fi, ff = periodos.get((n, e), (None, None))
        if _n_archivos(destino) > 0:
            print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: ya tiene archivos, salto docs", flush=True)
            descargas[(n, e)] = destino
        else:
            try:
                descargar_documentos_obra_por_hito(oid, destino, session=sess)
                print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: {_n_archivos(destino)} archivos", flush=True)
                descargas[(n, e)] = destino
            except Exception as ex:  # noqa: BLE001 — el portal cae; seguimos
                print(f"  [{i}/{total}] P{n}_E{e} obra {oid}: ERROR docs {ex!r}", flush=True)
        # informes de control (auditorías de Contraloría), filtrados al periodo de
        # la experiencia. Subcarpeta propia → resumible: si ya existe, se salta.
        if not (destino / "Informes de control").is_dir():
            try:
                r = descargar_informes_control(oid, destino, fecha_ini=fi, fecha_fin=ff, session=sess)
                if r.get("descargados"):
                    print(f"       + {r['descargados']} informe(s) de control "
                          f"(de {r['relevantes']} relevantes / {r['encontrados']} en la obra)", flush=True)
                descargas.setdefault((n, e), destino)
            except Exception as ex:  # noqa: BLE001
                print(f"       informes de control ERROR {ex!r}", flush=True)

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
