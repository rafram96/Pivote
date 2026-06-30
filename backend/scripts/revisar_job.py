"""Auditoría rápida de un job sin abrir el Excel: por experiencia, el estado de
resolución de CUI (resuelto / revisión / NA), la vía, el CUI del certificado y la
obra hallada. Marca el patrón del bug (revisión PESE a tener un CUI citado) para
cazar más casos como el de Fortaleza.

Uso:  python scripts/revisar_job.py <job_id>
"""
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if len(sys.argv) < 2:
    sys.exit("uso: python scripts/revisar_job.py <job_id>")
job_id = sys.argv[1]
base = os.path.join(os.path.dirname(__file__), "..", "datos_pivote")


def _load(suf):
    return json.load(open(os.path.join(base, f"{job_id}.{suf}.json"), encoding="utf-8"))


esp, enr, job = _load("espejo"), _load("enriquecimiento"), _load("job")
rev = {(it["n_prof"], it["n_exp"]): it
       for it in job.get("items_revision", []) if not it.get("resuelto")}

print(f"JOB {job_id} · estado={job.get('estado')} · {len(rev)} experiencia(s) en revisión\n")
con_cui_en_revision = []

for p in esp.get("profesionales", []):
    np_ = p.get("n_prof")
    print(f"PROF {np_} · {p.get('cargo')} · {p.get('nombre')}")
    for e in p.get("experiencias", []):
        ne = e.get("n")
        cui = e.get("cui")
        d = enr.get(f"{np_}:{ne}", {})
        if (np_, ne) in rev:
            mot = rev[(np_, ne)].get("motivo", "")
            print(f"  exp {ne}: ⚠ REVISIÓN · cui_cert={cui!r} · {mot}")
            if cui:                      # tenía CUI y aun así fue a revisión
                con_cui_en_revision.append((np_, ne, cui, mot))
        else:
            obra = d.get("obra") or {}
            ob = obra.get("nombre_obra") or obra.get("cui") or d.get("via") or "—"
            print(f"  exp {ne}: ok · cui_cert={cui!r} · via={d.get('via')} · obra={str(ob)[:55]}")
    print()

if con_cui_en_revision:
    print("⚠ EN REVISIÓN PESE A TENER CUI CITADO "
          "(el fix de CUI-exacto las resolvería al re-correr el backend):")
    for np_, ne, cui, mot in con_cui_en_revision:
        print(f"   P{np_}E{ne} cui={cui}: {mot}")
else:
    print("✓ Ninguna experiencia con CUI citado quedó en revisión.")
