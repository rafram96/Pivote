"""
medir_resolucion.py — Métrica consolidada del método de resolución de CUI.

Corre el matcher refinado (CUI-en-texto → dedup → nombre+RUC) sobre TODAS las
experiencias del Libertador (fixtures/new_format/libertador_espejo.json) y reporta
cuántas se resuelven solas (determinístico/dedup/auto) vs revisión, más los
traslapes por profesional.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import buscar_cui_por_nombre as B  # noqa: E402

ESPEJO = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path(__file__).resolve().parents[1] / "fixtures" / "new_format" / "libertador_espejo.json"


def clasificar(decision: str) -> str:
    if "N/A" in decision:
        return "na"
    if "DETERMINÍSTICO" in decision:
        return "determ"
    if "DEDUP" in decision:
        return "dedup"
    if "AUTO" in decision:
        return "auto"
    if "PROBABLE" in decision:
        return "probable"
    return "revision"


def main() -> int:
    d = json.loads(ESPEJO.read_text(encoding="utf-8"))
    s = B._crear_session()
    tally: Counter = Counter()
    total_exp = total_tras = profs_tras = 0
    print(f"{'Profesional':40} {'exp':>3} {'det':>3} {'ddp':>3} {'aut':>3} {'prb':>3} {'rev':>3} {'n/a':>3}  traslape")
    print("-" * 82)
    for p in d["profesionales"]:
        exps = p.get("experiencias", [])
        if not exps:
            continue
        res = B.resolver_lote(exps, s)
        cl = [clasificar(r["decision"]) for r in res]
        c = Counter(cl)
        de = B.dias_efectivos(exps) or {"traslape": 0}
        tras = de["traslape"]
        profs_tras += 1 if tras else 0
        total_tras += tras
        total_exp += len(exps)
        for k in cl:
            tally[k] += 1
        print(f"{(p.get('cargo') or '')[:40]:40} {len(exps):>3} {c['determ']:>3} {c['dedup']:>3} "
              f"{c['auto']:>3} {c['probable']:>3} {c['revision']:>3} {c['na']:>3}  {tras} d")

    na = tally["na"]
    aplic = total_exp - na  # denominador: solo obras de salud pública (cruzables)
    print(f"\n=== TOTAL · {total_exp} experiencias ({na} N/A excluidas · {aplic} aplicables) ===")
    for k, etq in [("determ", "Determinístico (CUI en texto verificado)"),
                   ("dedup", "Dedup (mismo certificado)"),
                   ("auto", "Auto (nombre verificado)"),
                   ("probable", "Probable (confirmar)"),
                   ("revision", "Revisión humana")]:
        n = tally[k]
        pct = f"({100 * n / aplic:.0f}%)" if aplic else ""
        print(f"  {etq:42}: {n:>3}  {pct}")
    print(f"  {'N/A (privado/ajeno a salud · excluido)':42}: {na:>3}")
    auto = tally["determ"] + tally["dedup"] + tally["auto"]
    if aplic:
        print(f"\n  → RESUELTAS SIN HUMANO (det+dedup+auto): {auto}/{aplic}  ({100 * auto / aplic:.0f}% de las aplicables)")
    print(f"  → con confirmación (probable): {tally['probable']}  ·  a revisión: {tally['revision']}")
    print(f"  Profesionales con traslape: {profs_tras}/{len(d['profesionales'])} · días de traslape (Paso 5): {total_tras}")
    print(f"  Queries cacheadas en _CACHE: {len(B._CACHE)} (obras únicas consultadas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
