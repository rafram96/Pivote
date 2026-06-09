"""
diag_casos.py — Inspecciona los casos PROBABLE/REVISIÓN de un dataset.

Para cada experiencia que NO resuelve sola, imprime: proyecto, establecimiento,
ubicación detectada (desambiguación), fragmentos, # candidatos y top-3 con
departamento + score. Sirve para entender regresiones y misses.

Uso: python tools/diag_casos.py <espejo.json> [--todos]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import buscar_cui_por_nombre as B  # noqa: E402

ESPEJO = Path(sys.argv[1])
TODOS = "--todos" in sys.argv


def main() -> int:
    d = json.loads(ESPEJO.read_text(encoding="utf-8"))
    s = B._crear_session()
    for p in d["profesionales"]:
        exps = p.get("experiencias", [])
        if not exps:
            continue
        res = B.resolver_lote(exps, s)
        for e, r in zip(exps, res):
            dec = r["decision"]
            interesa = TODOS or ("PROBABLE" in dec or "REVISIÓN" in dec)
            if not interesa:
                continue
            proy = e["proyecto"]
            print(f"\n[{(p.get('cargo') or '')[:28]:28}] {dec}")
            print(f"   proyecto : {proy[:90]}")
            print(f"   establec : {B.establecimiento(proy)[:60]}")
            print(f"   ubicación: {sorted(B.ubicacion(proy))}   toks={sorted(B._tokens_clave(B.establecimiento(proy)))}")
            print(f"   frags    : {B.fragmentos(proy)}")
            ranked = r.get("ranked") or []
            print(f"   #cands={r.get('n_cands')}  top:")
            for c in ranked:
                print(f"      cui={c['cui']:>9}  dep={str(c['dep'])[:14]:14} sc={c['score']:>6}  {c['ruc']}  {c['nombre']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
