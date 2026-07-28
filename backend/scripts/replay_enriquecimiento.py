"""
Replay OFFLINE del resolver de CUI sobre jobs ya corridos — el sustituto de la
golden mientras el corpus v4 se reconstruye (el v3 se perdió, ver
`.ai/handoffs/current.md` nota 2026-07-28).

Re-resuelve cada experiencia del espejo contra un SNAPSHOT del portal
reconstruido desde el enriquecimiento persistido (obra elegida + candidatos
registrados), y compara el resultado nuevo contra el histórico. Sirve para
medir el efecto real de un cambio del resolver sobre datos reales sin red:

  · RESUELTO→REVISION esperado en los casos que el cambio ataca (fixes)
  · RESUELTO→REVISION no esperado = SOBRE-DISPARO (el costo a vigilar)
  · cualquier CUI que CAMBIA de valor = mirar con lupa

Límites honestos del snapshot (documentados, no sorpresas):
  · el universo de búsqueda de CADA experiencia son las obras que SU corrida
    original registró (elegida + hasta 3 candidatos) — no el portal completo,
    y nunca el pool de otra experiencia (un pool compartido contamina: dispara
    guards de empate con los candidatos de las hermanas);
  · corre con base=None (sin MEF) para aislar el efecto del cambio del
    resolver de las señales de fusión/fichas MEF;
  · las experiencias multi-obra (sub_obras) se saltan y se cuentan.

La herencia DEDUP (#58) se ejercita con el código REAL: no se re-implementa el
bucle — se parchea `resolver` dentro del módulo para servirle a cada
experiencia su propio snapshot, y `resolver_con_dedup` corre tal cual.

Uso:
  python scripts/replay_enriquecimiento.py <job_id> [<job_id> ...]
  python scripts/replay_enriquecimiento.py --todos      # todos los jobs en DATA_DIR
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import data_dir  # noqa: E402
import resolucion.cui as _cui  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _obra_portal(d: dict, ruc: str = "") -> dict:
    """Mapea una obra del enriquecimiento (obra elegida o candidato) a la forma
    que el resolver espera del portal."""
    return {"codUniqInv": str(d.get("cui") or ""),
            "codigoObra": d.get("obra_id") or d.get("codigo_infoobras"),
            "nombrObra": d.get("nombre_obra") or "",
            "nombrDepartamento": d.get("departamento") or "",
            "fechaIniObra": None,
            "rucEjecutor": ruc, "rucSupervisor": ""}


class ConsultaSnapshot:
    """Sirve el universo registrado por la corrida original (pool por profesional)."""

    def __init__(self, pool: list[dict]):
        # dedup por (cui, nombre) conservando la primera aparición
        vistos, self.pool = set(), []
        for o in pool:
            k = (o["codUniqInv"], o["nombrObra"])
            if k not in vistos and (o["codUniqInv"] or o["nombrObra"]):
                vistos.add(k)
                self.pool.append(o)

    def por_codigo(self, codigo):
        c = _digitos(codigo)
        return [o for o in self.pool if _digitos(o["codUniqInv"]) == c]

    def buscar(self, nombre):
        return list(self.pool)


def _estado_antes(v: dict) -> tuple[str, str | None, str]:
    via = str(v.get("via") or "")
    cui = v.get("cui")
    if via == "PRIVADA":
        return "na", None, via
    return ("resuelto", str(cui), via) if cui else ("revision", None, via)


def replay_job(job_id: str, base_datos: Path) -> dict:
    dj = base_datos / job_id
    espejo = json.loads((dj / "espejo.json").read_text(encoding="utf-8"))
    enr = json.loads((dj / "enriquecimiento.json").read_text(encoding="utf-8"))

    res = {"job": job_id, "total": 0, "sin_enr": 0, "subobras": 0,
           "igual": 0, "cambios": []}
    pools: dict[str, ConsultaSnapshot] = {}

    # parche quirúrgico: cada experiencia resuelve contra SU snapshot; el bucle
    # de herencia (resolver_con_dedup) es el de producción, sin re-implementar.
    _resolver_real = _cui.resolver

    def _resolver_snapshot(exp, consulta, base=None):
        return _resolver_real(exp, pools[exp["_clave_replay"]], base)

    for prof in espejo.get("profesionales") or []:
        np_ = prof.get("n_prof")
        exps = []
        for e in prof.get("experiencias") or []:
            ne = e.get("n")
            clave = f"{np_}:{ne}"
            if e.get("obras"):                       # multi-obra: fuera del replay
                res["subobras"] += 1
                continue
            v = enr.get(clave)
            if not isinstance(v, dict) or not v:
                res["sin_enr"] += 1
                continue
            ruc = ""
            if str(v.get("via") or "") == "RUC":     # el portal traía el RUC del emisor
                ruc = _digitos((v.get("sunat") or {}).get("ruc")) \
                    or _digitos(e.get("ruc_emisor"))
            pool = []
            if isinstance(v.get("obra"), dict) and v["obra"]:
                pool.append(_obra_portal(v["obra"], ruc))
            for c in v.get("candidatos") or []:
                if isinstance(c, dict):
                    pool.append(_obra_portal(c))
            pools[clave] = ConsultaSnapshot(pool)
            e2 = dict(e)
            e2["_clave_replay"] = clave
            exps.append((e2, clave))
        if not exps:
            continue
        _cui.resolver = _resolver_snapshot
        try:
            resultados = list(_cui.resolver_con_dedup(exps, None, base=None))
        finally:
            _cui.resolver = _resolver_real
        for clave, r in resultados:
            res["total"] += 1
            antes_estado, antes_cui, antes_via = _estado_antes(enr[clave])
            ahora_estado, ahora_cui = r["estado"], r.get("cui")
            if antes_estado == ahora_estado and (antes_cui or None) == (ahora_cui or None):
                res["igual"] += 1
            else:
                res["cambios"].append({
                    "clave": clave,
                    "antes": f"{antes_estado}({antes_via or '—'}·{antes_cui or '—'})",
                    "ahora": f"{ahora_estado}({r.get('via') or '—'}·{ahora_cui or '—'})",
                    "decision": str(r.get("decision") or "")[:110],
                })
    return res


def main(argv: list[str]) -> int:
    base_datos = data_dir()
    if "--todos" in argv:
        jobs = sorted(p.name for p in base_datos.iterdir()
                      if (p / "espejo.json").exists()
                      and (p / "enriquecimiento.json").exists())
    else:
        jobs = [a for a in argv if not a.startswith("-")]
    if not jobs:
        print(__doc__)
        return 2

    tot = {"total": 0, "igual": 0, "cambios": 0}
    for j in jobs:
        r = replay_job(j, base_datos)
        tot["total"] += r["total"]
        tot["igual"] += r["igual"]
        tot["cambios"] += len(r["cambios"])
        print(f"\n══ {j} · {r['total']} experiencias replayadas "
              f"(sin_enr={r['sin_enr']} · subobras={r['subobras']}) ══")
        print(f"   sin cambio: {r['igual']}")
        for c in r["cambios"]:
            print(f"   Δ {c['clave']}: {c['antes']} → {c['ahora']}")
            print(f"       {c['decision']}")
    print(f"\n══ TOTAL: {tot['total']} · sin cambio {tot['igual']} · "
          f"cambios {tot['cambios']} ══")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
