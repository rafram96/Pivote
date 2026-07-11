"""Extrae el "Representante de obra" de InfoObras (contratista ejecutor,
supervisores/inspectores y residentes) para cada obra YA resuelta de un job y lo
guarda en el enriquecimiento, para mostrarlo en el panel junto a la info de SUNAT
(el emisor del certificado). Reusa los `obra_id` resueltos — NO re-resuelve CUIs.

El pipeline ya descarga estos datos (de ahí salen valorizaciones/paralizaciones),
solo no los guardaba; esto los rescata sin volver a correr el análisis.

Uso:  python -m scripts.backfill_representante <job_id>
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402 — carga el .env de la raíz
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraping.infoobras import (  # noqa: E402
    _crear_session,
    _extraer_todos_los_datos,
    _procesar_contratistas,
    _procesar_residentes,
    _procesar_supervisores,
)


def _jsonable(o):
    """dataclass/date/list/dict → estructura JSON-serializable."""
    if isinstance(o, date):
        return o.isoformat()
    if dataclasses.is_dataclass(o):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(o).items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(x) for x in o]
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    return o


def _merge_supervisores(supervisores, sup_html) -> list[dict]:
    """Fusiona los supervisores de `lSupervisor` (persona, DNI, RUC, fechas) con la
    tabla "Representante de obra" de DatosEjecucion (monto, doc. designación, razón
    social). Empareja por documento/RUC; si no, por índice. Los que solo están en
    la tabla HTML se agregan aparte. Devuelve list[dict] (no dataclass)."""
    out: list[dict] = []
    usados: set[int] = set()
    for i, s in enumerate(supervisores):
        d = dataclasses.asdict(s)
        j = next((j for j, h in enumerate(sup_html)
                  if j not in usados and h.get("documento") and h["documento"] == d.get("ruc")), None)
        if j is None and i < len(sup_html) and i not in usados:
            j = i
        if j is not None:
            usados.add(j)
            h = sup_html[j]
            d["razon_social"] = d.get("empresa") or h.get("razon_social")
            d["monto_soles"] = h.get("monto_soles")
            d["doc_designacion"] = h.get("doc_designacion")
        out.append(d)
    for j, h in enumerate(sup_html):                  # supervisores solo en la tabla HTML
        if j not in usados:
            out.append({
                "tipo": h.get("tipo"), "tipo_persona": h.get("tipo_persona"),
                "empresa": h.get("razon_social"), "ruc": h.get("documento"),
                "monto_soles": h.get("monto_soles"), "doc_designacion": h.get("doc_designacion"),
                "fecha_inicio": h.get("fecha_inicio"), "fecha_fin": h.get("fecha_fin"),
            })
    return out


def representante_de_obra(sess, obra_id) -> dict:
    """{contratistas, supervisores, residentes} de una obra de InfoObras.
    El contratista cae de la var JS lContratista (plantilla vieja) o de la tabla
    HTML `_contratistas_html` (plantilla nueva); el supervisor combina lSupervisor
    + la tabla HTML (monto/doc designación); residentes de lResidente."""
    datos = _extraer_todos_los_datos(sess, obra_id)
    contratistas = (_procesar_contratistas(datos.get("lContratista") or [])
                    or datos.get("_contratistas_html") or [])
    supervisores = _merge_supervisores(_procesar_supervisores(datos.get("lSupervisor", [])),
                                       datos.get("_supervisores_html") or [])
    return {
        "contratistas": _jsonable(contratistas),
        "supervisores": _jsonable(supervisores),
        "residentes": _jsonable(_procesar_residentes(datos.get("lResidente", []))),
    }


def main(job_id: str) -> None:
    dd = config.data_dir()
    ruta = dd / f"{job_id}.enriquecimiento.json"
    enr = json.loads(ruta.read_text(encoding="utf-8"))
    sess = _crear_session()
    n = 0
    for k, v in enr.items():
        if not re.match(r"^\d+:\d+$", k) or not isinstance(v, dict):
            continue
        oid = (v.get("obra") or {}).get("obra_id")
        if not oid:
            continue
        try:
            rep = representante_de_obra(sess, oid)
            v["representante_obra"] = rep
            print(f"  {k} obra {oid}: {len(rep['contratistas'])} contratista(s), "
                  f"{len(rep['supervisores'])} supervisor(es), "
                  f"{len(rep['residentes'])} residente(s)", flush=True)
            n += 1
        except Exception as ex:  # noqa: BLE001 — el portal cae; seguimos
            print(f"  {k} obra {oid}: ERROR {ex!r}", flush=True)
    ruta.write_text(json.dumps(enr, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[representante] {n} obras actualizadas en {ruta.name}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python -m scripts.backfill_representante <job_id>")
        sys.exit(2)
    main(sys.argv[1])
