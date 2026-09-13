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


def _obra_portal(d: dict, ruc: str = "", orden: int = 0) -> dict:
    """Mapea una obra del enriquecimiento (obra elegida o candidato) a la forma
    que el resolver espera del portal.

    `codigoObra` SIEMPRE sale con valor. El enriquecimiento solo persiste el
    `obra_id` de la obra ELEGIDA, no de los candidatos, y el resolver usa ese campo
    como CLAVE de `vistos` (`_recolectar_candidatos`): con todos los candidatos en
    `None` se quedaba UNO SOLO por experiencia —el primero— y el replay medía un
    universo de un candidato donde la corrida real tuvo tres o cuatro. Se sintetiza
    `SNAP:<orden>` (único y creciente por experiencia, nunca se consulta al portal)
    para conservar el orden de desempate por `obra_id`."""
    return {"codUniqInv": str(d.get("cui") or ""),
            "codigoObra": (d.get("obra_id") or d.get("codigo_infoobras")
                           or f"SNAP:{orden}"),
            "nombrObra": d.get("nombre_obra") or "",
            "nombrDepartamento": d.get("departamento") or "",
            "fechaIniObra": None,
            "rucEjecutor": ruc, "rucSupervisor": ""}


def _dedup(pool: list[dict]) -> list[dict]:
    """Dedup por (cui, nombre) conservando la primera aparición."""
    vistos, out = set(), []
    for o in pool:
        k = (o["codUniqInv"], o["nombrObra"])
        if k not in vistos and (o["codUniqInv"] or o["nombrObra"]):
            vistos.add(k)
            out.append(o)
    return out


class ConsultaSnapshot:
    """Sirve el universo registrado por la corrida original, por experiencia.

    Dos canales, porque el resolver los usa para cosas distintas y confundirlos
    falsea el replay:

      · `buscar(nombre)` = lo que InfoObras devolvió POR NOMBRE. Es el universo de
        `_recolectar_candidatos`.
      · `por_codigo(cui)` = los registros de ese CUI en InfoObras. Lo consultan la
        vía del CUI citado, el checkpoint de fase y la FUSIÓN con la base del MEF.

    Con `pool_codigo` aparte (modo `fidelidad_mef`, ver `resolver_snapshot`) los
    candidatos que en la corrida original vinieron de la base del MEF salen del
    canal por CÓDIGO y no del de nombre: así la fusión los vuelve a traer con su
    `_origen` real y el candado de ADR-005 §1 se ejercita igual que en producción.
    Sin él, un candidato del MEF se disfraza de obra que InfoObras devolvió por
    nombre y el replay resulta MÁS FÁCIL que la corrida real."""

    def __init__(self, pool: list[dict], pool_codigo: list[dict] | None = None):
        self.pool = _dedup(pool)
        self.pool_codigo = _dedup([*pool, *(pool_codigo or [])])

    def por_codigo(self, codigo):
        c = _digitos(codigo)
        return [o for o in self.pool_codigo if _digitos(o["codUniqInv"]) == c]

    def buscar(self, nombre):
        return list(self.pool)


def _estado_antes(v: dict) -> tuple[str, str | None, str]:
    via = str(v.get("via") or "")
    cui = v.get("cui")
    if via == "PRIVADA":
        return "na", None, via
    return ("resuelto", str(cui), via) if cui else ("revision", None, via)


def resolver_snapshot(job_id: str, base_datos: Path, base=None,
                      fidelidad_mef: bool | None = None) -> tuple[dict, dict]:
    """Re-resuelve TODAS las experiencias del job contra su snapshot y devuelve
    `({clave: resultado}, {"sin_enr": n, "subobras": n})`.

    Es el corazón del replay, extraído para que la prueba de aceptación de la
    auditoría (`tests/test_aceptacion_auditoria.py`) reconstruya el snapshot
    EXACTAMENTE igual sin duplicar el código. `base` se arrastra a `resolver`:
    el replay del CLI la deja en None (aísla el efecto del cambio del resolver de
    las señales del MEF), la aceptación le pasa la base local del MEF para
    ejercitar los vetos/fusión que sí corrieron en la corrida original.

    `fidelidad_mef` (por defecto: True cuando hay `base`) reparte los candidatos
    persistidos por su `origen`: los que en la corrida original trajo la FUSIÓN con
    el MEF (`origen == "mef"`) se sirven solo por CÓDIGO, para que la fusión los
    recolecte de nuevo desde la base real y el candado de ADR-005 §1 los vea con su
    origen verdadero. Sin `base` no hay fusión, así que el modo se apaga: apartar
    esos candidatos los borraría del universo."""
    dj = base_datos / job_id
    espejo = json.loads((dj / "espejo.json").read_text(encoding="utf-8"))
    enr = json.loads((dj / "enriquecimiento.json").read_text(encoding="utf-8"))
    fiel = bool(base) if fidelidad_mef is None else bool(fidelidad_mef and base)

    meta = {"sin_enr": 0, "subobras": 0}
    salida: dict[str, dict] = {}
    pools: dict[str, ConsultaSnapshot] = {}

    # parche quirúrgico: cada experiencia resuelve contra SU snapshot; el bucle
    # de herencia (resolver_con_dedup) es el de producción, sin re-implementar.
    _resolver_real = _cui.resolver

    def _resolver_snapshot(exp, consulta, base_=None):
        return _resolver_real(exp, pools[exp["_clave_replay"]], base_)

    exps = []
    for prof in espejo.get("profesionales") or []:
        np_ = prof.get("n_prof")
        for e in prof.get("experiencias") or []:
            ne = e.get("n")
            clave = f"{np_}:{ne}"
            if e.get("obras"):                       # multi-obra: fuera del replay
                meta["subobras"] += 1
                continue
            v = enr.get(clave)
            if not isinstance(v, dict) or not v:
                meta["sin_enr"] += 1
                continue
            ruc = ""
            if str(v.get("via") or "") == "RUC":     # el portal traía el RUC del emisor
                ruc = _digitos((v.get("sunat") or {}).get("ruc")) \
                    or _digitos(e.get("ruc_emisor"))
            pool, pool_codigo, orden = [], [], 0
            if isinstance(v.get("obra"), dict) and v["obra"]:
                pool.append(_obra_portal(v["obra"], ruc, orden))
            for c in v.get("candidatos") or []:
                if not isinstance(c, dict):
                    continue
                orden += 1
                if fiel and c.get("origen") == "mef":
                    pool_codigo.append(_obra_portal(c, "", orden))
                else:
                    pool.append(_obra_portal(c, "", orden))
            pools[clave] = ConsultaSnapshot(pool, pool_codigo)
            e2 = dict(e)
            e2["_clave_replay"] = clave
            exps.append((e2, clave))
    # UNA sola pasada con TODAS las experiencias del job, como en producción
    # (`etapas_reales` arma una lista plana): la herencia por folio y la de mismo
    # proyecto cruzan profesionales, y agrupar por profesional la apagaba.
    if exps:
        _cui.resolver = _resolver_snapshot
        try:
            for clave, r in _cui.resolver_con_dedup(exps, None, base=base):
                salida[clave] = r
        finally:
            _cui.resolver = _resolver_real
    return salida, meta


def replay_job(job_id: str, base_datos: Path) -> dict:
    dj = base_datos / job_id
    enr = json.loads((dj / "enriquecimiento.json").read_text(encoding="utf-8"))
    resultados, meta = resolver_snapshot(job_id, base_datos)

    res = {"job": job_id, "total": 0, "sin_enr": meta["sin_enr"],
           "subobras": meta["subobras"], "igual": 0, "cambios": []}
    for clave, r in resultados.items():
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
