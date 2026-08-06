"""
Medición previa de la paralelización de N profesionales (issue #25) — OFFLINE.

La issue exige medir ANTES de implementar, y la línea base es la versión actual.
Esto no paraleliza nada: mide de dónde sale el tiempo, para que la decisión
GO/NO-GO se tome con números y no con intuición sobre cuál es el cuello.

Cuatro mediciones, ninguna toca la red:

  M1 · LÍNEA BASE REAL — el wall-clock por etapa que dejó persistido cada job
       real de `datos_pivote/*/job.json` (`metrica.duracion_ms`). Es lo que el
       usuario esperó de verdad, en el servidor, contra los portales vivos. No
       hay simulación que lo mejore como evidencia.

  M2 · CPU LOCAL DE LA RESOLUCIÓN — el mismo bucle de producción
       (`resolver_con_dedup`) corriendo contra el snapshot del portal
       reconstruido desde el enriquecimiento persistido (el harness de
       `replay_enriquecimiento.py`, cero red). Lo que queda es el cómputo local
       puro. `wall_real − cpu_local` = espera de los portales.

  M3 · BASE MEF — `buscar_candidatos()` sobre la base local real instalada en
       esta máquina, con los nombres de obra reales del corpus. p50/p95/máx +
       carga perezosa del índice + RAM. Es la parte que la issue #25 propone
       paralelizar.

  M4 · TECHO (Amdahl) — con la fracción paralelizable medida, el máximo que
       podría dar la paralelización con N trabajadores. Un techo, no una
       promesa: ignora el rate-limit de facto del portal, que solo puede
       empeorarlo.

Uso (desde backend/):
    python scripts/medir_paralelismo.py            # las cuatro
    python scripts/medir_paralelismo.py --sin-mef  # salta M3 (~90 s de carga)
    python scripts/medir_paralelismo.py --json     # salida cruda
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import data_dir  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ETAPAS = ["ingesta", "validacion", "resolucion_cui", "infoobras", "sunat",
          "renipress", "reglas", "excel", "persistencia"]


def _jobs(base: Path) -> list[Path]:
    return sorted(p for p in base.iterdir()
                  if (p / "espejo.json").is_file() and (p / "job.json").is_file())


def _n_exp(espejo: dict) -> int:
    return sum(len(p.get("experiencias") or [])
               for p in espejo.get("profesionales") or [])


# ── M1 · línea base real ─────────────────────────────────────────────────────

def medir_baseline(base: Path) -> dict:
    filas = []
    for d in _jobs(base):
        espejo = json.loads((d / "espejo.json").read_text(encoding="utf-8"))
        job = json.loads((d / "job.json").read_text(encoding="utf-8"))
        ms = {}
        extra = {}
        for et in job.get("etapas") or []:
            m = et.get("metrica") or {}
            ms[et.get("etapa")] = m.get("duracion_ms") or 0
            if et.get("etapa") == "infoobras":
                extra = {"descargas": m.get("descargas") or 0,
                         "reintentos": m.get("reintentos") or 0,
                         "gb": round((m.get("bytes_descargados") or 0) / 1e9, 1)}
        filas.append({
            "job": d.name,
            "profesionales": len(espejo.get("profesionales") or []),
            "experiencias": _n_exp(espejo),
            "etapas_s": {k: round(ms.get(k, 0) / 1000, 1) for k in ETAPAS},
            "total_s": round(sum(ms.values()) / 1000, 1),
            "infoobras": extra,
        })
    return {"jobs": filas}


# ── M2 · CPU local de la etapa de resolución ─────────────────────────────────

def medir_resolucion(base: Path, repeticiones: int = 3) -> dict:
    from scripts.replay_enriquecimiento import replay_job

    filas = []
    for d in _jobs(base):
        if not (d / "enriquecimiento.json").is_file():
            continue
        muestras = []
        replayadas = 0
        for _ in range(repeticiones):
            t0 = time.perf_counter()
            r = replay_job(d.name, base)
            muestras.append(time.perf_counter() - t0)
            replayadas = r["total"]
        if not replayadas:
            continue
        cpu_s = min(muestras)          # el mínimo: el resto es ruido de la máquina
        filas.append({
            "job": d.name,
            "experiencias_replayadas": replayadas,
            "cpu_local_s": round(cpu_s, 3),
            "cpu_local_ms_por_exp": round(cpu_s * 1000 / replayadas, 2),
        })
    return {"repeticiones": repeticiones, "jobs": filas}


# ── M3 · base MEF ────────────────────────────────────────────────────────────

def corpus_nombres(base: Path) -> list[str]:
    """Nombres de obra reales de todas las experiencias de todos los jobs."""
    nombres = []
    for d in _jobs(base):
        espejo = json.loads((d / "espejo.json").read_text(encoding="utf-8"))
        for prof in espejo.get("profesionales") or []:
            for e in prof.get("experiencias") or []:
                n = str(e.get("proyecto") or "").strip()
                if len(n) > 5:
                    nombres.append(n)
    return nombres


def medir_mef(base: Path, nombres: list[str]) -> dict:
    from resolucion.base_mef import BaseMef

    dir_mef = base / "referencia" / "mef"
    b = BaseMef(dir_mef)
    if not b.disponible():
        return {"disponible": False, "dir": str(dir_mef)}

    t0 = time.perf_counter()
    b.buscar_candidatos("hospital regional de prueba de carga")   # carga perezosa
    carga_s = time.perf_counter() - t0

    lat = []
    hits = 0
    for n in nombres:
        t = time.perf_counter()
        r = b.buscar_candidatos(n, topn=10)
        lat.append((time.perf_counter() - t) * 1000)
        hits += 1 if r else 0
    lat.sort()

    def pct(p: float) -> float:
        if not lat:
            return 0.0
        return round(lat[min(len(lat) - 1, int(len(lat) * p))], 1)

    return {
        "disponible": True,
        "consultas": len(lat),
        "con_candidatos": hits,
        "carga_indice_s": round(carga_s, 1),
        "ram_mb": b.memoria_mb(),
        "p50_ms": pct(0.50), "p95_ms": pct(0.95),
        "max_ms": round(max(lat), 1) if lat else 0.0,
        "media_ms": round(statistics.fmean(lat), 1) if lat else 0.0,
        "total_s": round(sum(lat) / 1000, 1),
        "edad_dias": b.edad_dias(),
    }


# ── M4 · techo de Amdahl ─────────────────────────────────────────────────────

def techo(fraccion_paralelizable: float, n: int) -> float:
    """Aceleración máxima con `n` trabajadores (ley de Amdahl)."""
    f = max(0.0, min(1.0, fraccion_paralelizable))
    return 1.0 / ((1 - f) + f / max(1, n))


def calcular_techo(baseline: dict, resolucion: dict, mef: dict) -> dict:
    por_job = {j["job"]: j for j in resolucion["jobs"]}
    filas = []
    for j in baseline["jobs"]:
        r = por_job.get(j["job"])
        if not r:
            continue
        wall = j["etapas_s"]["resolucion_cui"]
        cpu = r["cpu_local_s"]
        # el coste MEF de esa etapa: una consulta por experiencia no resuelta por
        # código, acotado por arriba con una consulta por experiencia
        mef_s = (mef.get("media_ms", 0) / 1000) * r["experiencias_replayadas"] \
            if mef.get("disponible") else 0.0
        local = cpu + mef_s
        red = max(0.0, wall - local)
        filas.append({
            "job": j["job"],
            "experiencias": j["experiencias"],
            "resolucion_wall_s": wall,
            "local_s": round(local, 1),
            "de_ella_mef_s": round(mef_s, 1),
            "red_s": round(red, 1),
            "pct_red": round(100 * red / wall, 1) if wall else 0.0,
        })
    pct_red = round(statistics.fmean([f["pct_red"] for f in filas]), 1) if filas else 0.0
    return {
        "por_job": filas,
        "pct_red_promedio": pct_red,
        # Techo de paralelizar SOLO la etapa de resolución, sobre el total del job
        "techo_etapa": {n: round(techo(1.0, n), 2) for n in (2, 4, 8)},
        "techo_job_completo": _techo_job(baseline, resolucion),
    }


def _techo_job(baseline: dict, resolucion: dict) -> list[dict]:
    """Si la etapa de resolución se volviera instantánea, ¿cuánto baja el job?"""
    out = []
    for j in baseline["jobs"]:
        total = j["total_s"]
        res = j["etapas_s"]["resolucion_cui"]
        out.append({
            "job": j["job"],
            "total_s": total,
            "resolucion_s": res,
            "pct_del_job": round(100 * res / total, 1) if total else 0.0,
            "techo_si_fuese_gratis": round(total / max(1e-9, total - res), 2),
        })
    return out


# ── salida ───────────────────────────────────────────────────────────────────

def imprimir(datos: dict) -> None:
    b, r, m, t = (datos["baseline"], datos["resolucion"], datos["mef"],
                  datos["techo"])

    print("\n══ M1 · LÍNEA BASE REAL (job.json de corridas contra portales vivos) ══")
    print(f"{'job':14}{'prof':>5}{'exp':>5}" +
          "".join(f"{e[:9]:>10}" for e in ("validacion", "resoluc_cui", "infoobras",
                                           "sunat", "excel")) +
          f"{'TOTAL_s':>9}")
    for j in b["jobs"]:
        e = j["etapas_s"]
        print(f"{j['job']:14}{j['profesionales']:>5}{j['experiencias']:>5}"
              f"{e['validacion']:>10.1f}{e['resolucion_cui']:>10.1f}"
              f"{e['infoobras']:>10.1f}{e['sunat']:>10.1f}{e['excel']:>10.1f}"
              f"{j['total_s']:>9.1f}")

    print("\n══ M2 · CPU LOCAL DE LA RESOLUCIÓN (replay offline, sin red) ══")
    print(f"{'job':14}{'exps':>6}{'cpu_s':>9}{'ms/exp':>9}")
    for j in r["jobs"]:
        print(f"{j['job']:14}{j['experiencias_replayadas']:>6}"
              f"{j['cpu_local_s']:>9.2f}{j['cpu_local_ms_por_exp']:>9.2f}")

    print("\n══ M3 · BASE MEF · buscar_candidatos() sobre la base real ══")
    if not m.get("disponible"):
        print(f"   base no instalada en {m.get('dir')} — M3 omitida")
    else:
        print(f"   consultas={m['consultas']} (con candidatos: {m['con_candidatos']})"
              f" · base de hace {m['edad_dias']} día(s)")
        print(f"   carga perezosa del índice: {m['carga_indice_s']} s"
              f" · RAM {m['ram_mb']} MB")
        print(f"   p50={m['p50_ms']} ms · p95={m['p95_ms']} ms · máx={m['max_ms']} ms"
              f" · media={m['media_ms']} ms · suma={m['total_s']} s")

    print("\n══ M4 · DE DÓNDE SALE EL TIEMPO DE LA RESOLUCIÓN ══")
    print(f"{'job':14}{'wall_s':>9}{'local_s':>9}{'(mef_s)':>9}{'red_s':>9}{'%red':>7}")
    for f in t["por_job"]:
        print(f"{f['job']:14}{f['resolucion_wall_s']:>9.1f}{f['local_s']:>9.1f}"
              f"{f['de_ella_mef_s']:>9.1f}{f['red_s']:>9.1f}{f['pct_red']:>7.1f}")
    print(f"\n   Espera de portal, promedio: {t['pct_red_promedio']}% del tiempo "
          f"de la etapa.")
    print("\n   Si la etapa de resolución fuese GRATIS (techo absoluto, "
          "inalcanzable):")
    for f in t["techo_job_completo"]:
        print(f"     {f['job']:14} resolución {f['pct_del_job']:>5.1f}% del job "
              f"→ el job entero mejoraría ×{f['techo_si_fuese_gratis']}")


def main(argv: list[str]) -> int:
    base = data_dir()
    datos = {"baseline": medir_baseline(base)}
    datos["resolucion"] = medir_resolucion(base)
    if "--sin-mef" in argv:
        datos["mef"] = {"disponible": False, "dir": "(omitida por --sin-mef)"}
    else:
        datos["mef"] = medir_mef(base, corpus_nombres(base))
    datos["techo"] = calcular_techo(datos["baseline"], datos["resolucion"],
                                    datos["mef"])
    if "--json" in argv:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    else:
        imprimir(datos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
