"""
reparar_evaluacion.py — Rellena, en un job YA corrido, lo que el evaluador de la
skill no entregó y el backend sí puede calcular solo (#45 · capa L2).

Para qué existe: las corridas del 26-jul salieron con la evaluación por experiencia
vacía (0 de 63 y 0 de 35 experiencias con `dias`), así que su Excel tiene columnas
en blanco. Desde que `recalcular_espejo` está cableado en la etapa VALIDACIÓN, las
corridas NUEVAS ya no pueden salir así — pero los jobs viejos siguen en disco con
el hueco.

Esto NO re-corre la skill (no gasta tokens del cliente) ni toca la red: los datos
crudos —fechas, cargos, folios— ya están en el espejo; lo único que faltaba era la
aritmética. Lo que el backend NO puede reponer es el juicio (veredictos,
`funciones_similares`): eso se queda vacío y se informa.

Uso:
    python -m scripts.reparar_evaluacion <job_id> [<job_id> ...]
    python -m scripts.reparar_evaluacion --todos      # todos los jobs con el hueco
    python -m scripts.reparar_evaluacion <job_id> --simular   # no escribe nada
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402,F401  (el import ejecuta load_dotenv)
from validacion import recalcular_espejo  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "datos_pivote"
# Campos que produce agent-evaluador por experiencia. Si TODOS vienen vacíos en
# TODAS las experiencias, la evaluación no llegó (ver `validacion/integridad.py`).
_CAMPOS_EVAL = ("dias", "meses", "anios", "anterior_colegiatura")


def _experiencias(espejo: dict):
    for prof in espejo.get("profesionales", []) or []:
        for exp in prof.get("experiencias", []) or []:
            yield prof, exp


def diagnosticar(espejo: dict) -> dict:
    """Cuántas experiencias traen cálculo del evaluador y cuántas no."""
    total = con_dias = 0
    for _, exp in _experiencias(espejo):
        total += 1
        if exp.get("dias") is not None:
            con_dias += 1
    profs = espejo.get("profesionales", []) or []
    return {"experiencias": total, "con_dias": con_dias,
            "profesionales": len(profs),
            "con_veredicto": sum(1 for p in profs if p.get("cumple"))}


def reparar(job_id: str, simular: bool = False) -> dict:
    ruta = DATA / job_id / "espejo.json"
    if not ruta.exists():
        return {"job": job_id, "error": f"no existe {ruta}"}
    espejo = json.loads(ruta.read_text(encoding="utf-8"))
    antes = diagnosticar(espejo)

    recalcular_espejo(espejo)          # sobrescribir=False: solo rellena huecos
    despues = diagnosticar(espejo)

    if not simular and despues["con_dias"] > antes["con_dias"]:
        # respaldo antes de tocar datos del cliente: el espejo es la fuente de
        # verdad del job y una reparación mal hecha no debe ser irreversible
        shutil.copy2(ruta, ruta.with_suffix(".json.antes_reparar"))
        tmp = ruta.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(espejo, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(ruta)

    return {"job": job_id, "antes": antes, "despues": despues,
            "escrito": bool(not simular and despues["con_dias"] > antes["con_dias"])}


def _jobs_con_hueco() -> list[str]:
    out = []
    for d in sorted(DATA.glob("*/espejo.json")):
        try:
            esp = json.loads(d.read_text(encoding="utf-8"))
        except Exception:
            continue
        dg = diagnosticar(esp)
        if dg["experiencias"] and not dg["con_dias"]:
            out.append(d.parent.name)
    return out


def main(argv: list[str]) -> int:
    simular = "--simular" in argv
    ids = [a for a in argv if not a.startswith("--")]
    if "--todos" in argv:
        ids = _jobs_con_hueco()
        print(f"jobs con la evaluación por experiencia vacía: {len(ids)}")
    if not ids:
        print(__doc__)
        return 1
    for job in ids:
        r = reparar(job, simular)
        if r.get("error"):
            print(f"  {job}: {r['error']}")
            continue
        a, d = r["antes"], r["despues"]
        print(f"  {job}: días {a['con_dias']}/{a['experiencias']} → "
              f"{d['con_dias']}/{d['experiencias']} · "
              f"veredictos {d['con_veredicto']}/{d['profesionales']} "
              f"(el backend NO los repone) · "
              f"{'escrito' if r['escrito'] else 'sin cambios'}")
    if simular:
        print("\n(simulación: no se escribió nada)")
    else:
        print("\nRegenera el Excel de los jobs tocados para que el cambio se vea:")
        print("  python tools/utils/regenerar_excel_final.py <job_id>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
