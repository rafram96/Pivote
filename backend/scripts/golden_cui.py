"""
Línea base GOLDEN del resolver de CUI (backend/resolucion/cui.py).

Congela el comportamiento ACTUAL del resolver sobre el corpus auditado
(`datos_pivote/auditoria_cui_v3.xlsx`, ~277 certificados con CUI verdad)
ANTES del refactor que viene en fases posteriores. Es la vara de contraste
de todo el proyecto: cualquier cambio al resolver se compara contra estos
buckets para saber si mejora, empata o rompe.

Cada respuesta del portal InfoObras (por_codigo/buscar/rango) se cachea EN
DISCO (`datos_pivote/_golden_cui_cache.json`), así las re-corridas de fases
futuras son 100% offline y deterministas (`--solo-cache`). El portal es
FLAKY: si no responde para un caso NO se cachea el fallo — se reintenta el
caso completo y, si persiste, se marca `portal_caido` (no contamina el golden).

Buckets (comparando el CUI resuelto contra la verdad auditada):
  resuelto_correcto    · resuelto y CUI == verdad
  resuelto_incorrecto  · resuelto pero CUI != verdad   ← el bucket CRÍTICO
  revision             · el resolver mandó a revisión (no arriesgó un CUI)
  na_privada           · descartado por gate de privadas (obra no pública)
  portal_caido         · el portal no respondió tras los reintentos

CASOS ENSANCHADOS (ver `_enriquecer`): cada caso se arma con la experiencia
REAL, reconstruida por join contra `datos_pivote/<job>/espejo.json` usando las
columnas `job` y `prof:exp` de la auditoría. Antes el caso era solo
`{proyecto, cui}` con fechas en None, y eso volvía INERTES la mitad de las
reglas del resolver (veto de ubigeo, veto de departamento de ADR-013, candado
de nombre genérico, `ruc_match`/`ent_match`, clasificación de privadas): la red
de seguridad no podía ver lo que no se le daba. Si el espejo falta o el par
(n_prof, n_exp) no calza, el caso se arma como antes y se CUENTA aparte — el
reporte declara siempre su propia cobertura.

Uso:
    python scripts/golden_cui.py              # corrida completa (live, ~30-90 min)
    python scripts/golden_cui.py --limite 20  # prueba rápida (primeros 20 casos)
    python scripts/golden_cui.py --solo-cache # re-corrida offline (falla si falta red)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = Path(__file__).resolve().parents[1] / "datos_pivote"
XLSX = BASE / "auditoria_cui_v3.xlsx"
CACHE = BASE / "_golden_cui_cache.json"
BASELINE = BASE / "golden_cui_baseline.json"

PAUSA_CASO = 0.6          # pausa entre casos (portal flaky → nunca en paralelo)
REINTENTOS_CASO = 2       # reintentos del caso completo si el portal cae


# ── normalización (misma que el resolver, para deduplicar por proyecto) ──────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def _solo_digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


# ── enriquecimiento del caso con la experiencia REAL del espejo ──────────────

# Campos que `resolucion.cui.resolver` LEE de la experiencia y que la golden no
# le daba. Sin ellos, esas reglas nunca se ejercitan:
#   ubicacion / entidad_contratante → veto de ubigeo, veto de departamento
#                                     (ADR-013), `_muni_contradice`, privadas
#   entidad_emisora / ruc_emisor    → `ruc_match` contra la ficha MEF
#   fecha_inicial / fecha_final     → `_elegir_obra` (desempate entre obras del
#                                     mismo CUI); iban SIEMPRE en None
#   objeto                          → `_es_experiencia_privada`
# `objeto` NO existe hoy en el espejo v1.2.0 (0/277 casos): se lee igual para
# que el día que el contrato lo agregue entre solo, y mientras tanto degrada a
# ausente — nunca a error.
CAMPOS_ESPEJO = ("ubicacion", "entidad_contratante", "entidad_emisora",
                 "ruc_emisor", "objeto", "fecha_inicial", "fecha_final")

_ESPEJOS: dict[str, dict | None] = {}


def _indice_espejo(job: str) -> dict | None:
    """Índice `{(n_prof, n_exp): experiencia}` del espejo de un job.
    Devuelve None si el espejo no está en disco o no se puede leer (el caso
    degrada, no revienta). Cacheado por job: 29 jobs para 277 casos."""
    if job in _ESPEJOS:
        return _ESPEJOS[job]
    ruta = BASE / job / "espejo.json"
    idx: dict | None = None
    if ruta.exists():
        try:
            espejo = json.loads(ruta.read_text(encoding="utf-8"))
            idx = {}
            for prof in espejo.get("profesionales") or []:
                n_prof = prof.get("n_prof")
                for e in prof.get("experiencias") or []:
                    idx[(n_prof, e.get("n"))] = e
        except Exception:   # noqa: BLE001 — espejo ilegible → caso degradado
            idx = None
    _ESPEJOS[job] = idx
    return idx


def _enriquecer(caso: dict) -> None:
    """Rellena `caso['campos']` con los datos REALES de la experiencia y marca
    `caso['enriquecido']`.

    DEGRADACIÓN HONESTA: si falta el job, si `prof:exp` no viene con el formato
    `<n_prof>:<n_exp>`, si el espejo no está en disco o si el par no calza, el
    caso queda como siempre (solo proyecto + CUI citado, fechas en None) y se
    cuenta con su motivo en `caso['motivo_degradado']`. Un golden que miente
    sobre su propia cobertura es peor que uno pobre.

    `ruc_emisor` tiene respaldo: la propia auditoría lo trae en su col 9. Se
    usa solo cuando el espejo no lo dio (o el caso degradó)."""
    campos: dict[str, object] = {}
    motivo = None
    job = caso.get("job") or ""
    mpe = re.match(r"^\s*(\d+)\s*:\s*(\d+)\s*$", caso.get("prof_exp") or "")
    if not job:
        motivo = "la auditoría no trae job"
    elif not mpe:
        motivo = f"prof:exp ilegible ({caso.get('prof_exp')!r})"
    else:
        idx = _indice_espejo(job)
        if idx is None:
            motivo = f"sin espejo legible en disco para el job {job}"
        else:
            exp_real = idx.get((int(mpe.group(1)), int(mpe.group(2))))
            if exp_real is None:
                motivo = (f"el espejo del job {job} no tiene la experiencia "
                          f"{caso.get('prof_exp')}")
            else:
                campos = {k: exp_real.get(k) for k in CAMPOS_ESPEJO
                          if exp_real.get(k) not in (None, "", [])}
    if not campos.get("ruc_emisor") and caso.get("ruc_auditoria"):
        campos["ruc_emisor"] = caso["ruc_auditoria"]
    caso["campos"] = campos
    caso["enriquecido"] = motivo is None
    caso["motivo_degradado"] = motivo


# ── carga de casos desde el xlsx auditado ────────────────────────────────────

def cargar_casos(limite: int | None = None) -> list[dict]:
    """Lee la hoja `auditoria_cui` y deduplica por nombre de proyecto normalizado.
    Toma filas con proyecto Y cui (verdad) no vacíos. El CUI verdad se extrae con
    regex \\d{6,7} sobre la col 6; el CUI citado en el cert es la col 8.

    Cada caso se ENSANCHA con la experiencia real de su espejo (`_enriquecer`);
    el join usa el job (col 1) y `prof:exp` (col 2) de la fila que ganó el dedup,
    así el caso sigue siendo el mismo de siempre, solo que completo."""
    import openpyxl
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["auditoria_cui"]
    filas = list(ws.iter_rows(values_only=True))[1:]   # saltar header
    casos: dict[str, dict] = {}
    for r in filas:
        proyecto = str(r[5] or "").strip()
        m = re.search(r"\d{6,7}", str(r[6] or ""))
        if not proyecto or not m:
            continue
        clave = _norm(proyecto)
        if clave in casos:
            continue
        cui_cert = str(r[8] or "").strip()
        if cui_cert.lower() == "none":
            cui_cert = ""
        casos[clave] = {
            "proyecto": proyecto,
            "cui_verdad": m.group(0),
            "cui_en_cert": cui_cert,
            "riesgo": str(r[0] or "").strip() or "SIN_RIESGO",
            "job": str(r[1] or "").strip(),
            "prof_exp": str(r[2] or "").strip(),
            "ruc_auditoria": _solo_digitos(r[9]) or "",
        }
    ordenados = list(casos.values())
    if limite:
        ordenados = ordenados[:limite]   # recortar ANTES: --limite no paga espejos de más
    for caso in ordenados:
        _enriquecer(caso)
    return ordenados


def resumen_cobertura(casos: list[dict]) -> dict:
    """Cuántos casos van con la experiencia real y qué campos traen de verdad.
    Se imprime y se guarda en el JSON: la golden declara su propia cobertura."""
    from collections import Counter
    enr = [c for c in casos if c["enriquecido"]]
    degradados = [c for c in casos if not c["enriquecido"]]
    return {
        "total": len(casos),
        "enriquecidos": len(enr),
        "degradados": len(degradados),
        "campos_no_vacios": {k: sum(1 for c in casos if c["campos"].get(k))
                             for k in CAMPOS_ESPEJO},
        "motivos_degradado": dict(Counter(c["motivo_degradado"] for c in degradados)),
    }


def imprimir_cobertura(cob: dict) -> None:
    total = cob["total"] or 1
    print("\n  Cobertura del ensanche (casos armados con la experiencia real):")
    print(f"    enriquecidos {cob['enriquecidos']}/{cob['total']} "
          f"({cob['enriquecidos'] * 100 / total:.1f}%) · "
          f"degradados {cob['degradados']}")
    for k in CAMPOS_ESPEJO:
        n = cob["campos_no_vacios"][k]
        print(f"      {k:22} {n:>4}/{cob['total']} ({n * 100 / total:>5.1f}%)")
    for motivo, n in cob["motivos_degradado"].items():
        print(f"      ⚠ degradado ×{n}: {motivo}")


# ── consulta cacheada en disco (envuelve la real) ────────────────────────────

class ConsultaCacheada:
    """Envuelve `resolucion.cui.ConsultaInfoObras` cacheando en disco cada
    respuesta del portal (por_codigo / buscar / rango), para que las re-corridas
    sean offline y deterministas.

    Reglas de cacheo:
      - por_codigo / buscar: se cachea la lista de registros. Si el real lanza
        PortalNoResponde NO se cachea (se re-lanza para que el caso reintente).
      - rango: se cachea (min,max) como ISO; si el real lanza, se cachea (None,None)
        (el rango es solo un hint de re-ranking; su ausencia degrada seguro).
    """

    def __init__(self, solo_cache: bool = False):
        self._solo_cache = solo_cache
        self._cache: dict[str, object] = {}
        self.hubo_fallo_red = False   # se activa si un por_codigo/buscar cayó
        if CACHE.exists():
            self._cache = json.loads(CACHE.read_text(encoding="utf-8"))
        self._real = None if solo_cache else self._crear_real()

    @staticmethod
    def _crear_real():
        from resolucion.cui import ConsultaInfoObras
        return ConsultaInfoObras()

    def guardar(self) -> None:
        tmp = CACHE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE)

    # -- listas de registros (por_codigo / buscar) --

    def _lista(self, clave: str, fn):
        if clave in self._cache:
            return self._cache[clave]
        if self._solo_cache:
            raise RuntimeError(f"--solo-cache: falta en cache la clave {clave!r} "
                               "(la corrida necesitaría red)")
        # PortalNoResponde se propaga SIN cachear (el caso reintenta completo)
        res = fn()
        self._cache[clave] = res
        return res

    def por_codigo(self, codigo: str) -> list[dict]:
        return self._lista(f"cod:{codigo}", lambda: self._real.por_codigo(codigo))

    def buscar(self, nombre: str) -> list[dict]:
        return self._lista(f"nom:{nombre}", lambda: self._real.buscar(nombre))

    # -- rango de valorizaciones (hint de re-ranking) --

    def rango(self, obra_id) -> tuple:
        clave = f"rango:{obra_id}"
        if clave in self._cache:
            oi, of = self._cache[clave]
            return (date.fromisoformat(oi) if oi else None,
                    date.fromisoformat(of) if of else None)
        if self._solo_cache:
            raise RuntimeError(f"--solo-cache: falta en cache la clave {clave!r}")
        try:
            oi, of = self._real.rango(obra_id)
        except Exception:   # noqa: BLE001 — si el real cae, el rango es desconocido
            oi, of = None, None
        self._cache[clave] = [oi.isoformat() if oi else None,
                              of.isoformat() if of else None]
        return (oi, of)


# ── clasificación en buckets ─────────────────────────────────────────────────

def _bucket(resultado: dict, cui_verdad: str) -> str:
    estado = resultado.get("estado")
    if estado == "na":
        return "na_privada"
    if estado == "revision":
        return "revision"
    if estado == "resuelto":
        obtenido = _solo_digitos(resultado.get("cui"))
        return "resuelto_correcto" if obtenido == _solo_digitos(cui_verdad) \
            else "resuelto_incorrecto"
    return "revision"   # defensivo: cualquier estado inesperado cuenta como revisión


# ── resolución de un caso con reintentos por caída del portal ────────────────

def resolver_caso(caso: dict, consulta: ConsultaCacheada, base=None) -> dict:
    """Resuelve un caso; si el portal cae (via=='PORTAL'), reintenta el caso
    completo hasta REINTENTOS_CASO veces con pausa. Devuelve el dict del resolver
    o {'estado':'portal_caido'} si el portal persiste caído.

    `base` (opcional) es la base local del MEF (`base_mef.instancia()`): con ella
    el resolver hace fusión de candidatos por nombre y fetches `por_codigo` de CUIs
    del MEF que la corrida vieja nunca consultó — esos van al portal EN VIVO y se
    añaden a la caché (correcto y esperado)."""
    from resolucion.cui import resolver
    # base del caso + los campos REALES del espejo (ubicación, entidad, RUC,
    # fechas). `proyecto` y `cui` mandan desde la auditoría —son la identidad del
    # caso y lo que ancla el emparejamiento con la baseline— y por eso van
    # DESPUÉS del spread. Se rearma en cada intento: `resolver` escribe en la exp
    # que recibe (`_ficha_mef_citado`, `_fichas_mef`) y un reintento debe partir
    # limpio.
    for intento in range(REINTENTOS_CASO + 1):
        exp = {**caso.get("campos", {}),
               "proyecto": caso["proyecto"],
               "cui": caso["cui_en_cert"] or ""}
        exp.setdefault("fecha_inicial", None)
        exp.setdefault("fecha_final", None)
        consulta.hubo_fallo_red = False
        r = resolver(exp, consulta, base=base)
        # el resolver convierte PortalNoResponde en revisión via='PORTAL' (honesto):
        # esa es la señal de que el portal no respondió, no de "sin candidato".
        if r.get("via") != "PORTAL":
            return r
        if intento < REINTENTOS_CASO:
            time.sleep(1.5 * (intento + 1))
    return {"estado": "portal_caido", "cui": None, "via": "PORTAL",
            "decision": "el portal de InfoObras no respondió tras los reintentos"}


# ── reporte ──────────────────────────────────────────────────────────────────

ORDEN_BUCKETS = ["resuelto_correcto", "resuelto_incorrecto", "revision",
                 "na_privada", "portal_caido"]
ORDEN_RIESGO = ["BAJO", "MEDIO", "ALTO", "SIN_RIESGO"]


def imprimir_reporte(detalle: list[dict], total: int, cobertura: dict | None = None) -> None:
    from collections import Counter
    buckets = Counter(d["bucket"] for d in detalle)
    print("\n" + "=" * 78)
    print(f"LÍNEA BASE GOLDEN · resolver de CUI ACTUAL · {total} casos")
    print("=" * 78)
    print(f"  {'bucket':22} {'n':>5} {'%':>7}")
    print("  " + "-" * 36)
    for b in ORDEN_BUCKETS:
        n = buckets.get(b, 0)
        print(f"  {b:22} {n:>5} {n * 100 / total:>6.1f}%")
    print("  " + "-" * 36)
    print(f"  {'TOTAL':22} {total:>5} {'100.0%':>7}")

    # desglose por riesgo × bucket
    print("\n  Desglose por riesgo:")
    for riesgo in ORDEN_RIESGO:
        sub = [d for d in detalle if d["riesgo"] == riesgo]
        if not sub:
            continue
        c = Counter(d["bucket"] for d in sub)
        piezas = " · ".join(f"{b}={c[b]}" for b in ORDEN_BUCKETS if c.get(b))
        print(f"    {riesgo:11} ({len(sub):>3}): {piezas}")

    # el bucket crítico, en detalle
    malos = [d for d in detalle if d["bucket"] == "resuelto_incorrecto"]
    print(f"\n  RESUELTO_INCORRECTO ({len(malos)}) — el bucket crítico:")
    if not malos:
        print("    (ninguno)")
    for d in malos:
        print(f"    [{d['riesgo']:5} via={d['via'] or '?':8}] verdad={d['cui_verdad']:>8} "
              f"obtenido={d['cui_obtenido'] or '—':>8}")
        print(f"        {d['proyecto'][:100]}")

    caidos = buckets.get("portal_caido", 0)
    if caidos:
        pct = caidos * 100 / total
        marca = "  ⚠ ADVERTENCIA" if pct > 10 else ""
        print(f"\n  portal_caido: {caidos}/{total} ({pct:.1f}%){marca}")
    if cobertura:
        imprimir_cobertura(cobertura)
    print("=" * 78)


# ── main ─────────────────────────────────────────────────────────────────────

# ── comparador de dos corridas golden (viejo vs nuevo) ───────────────────────

def comparar(ruta_a: Path, ruta_b: Path) -> int:
    """Compara dos salidas golden (A=viejo, B=nuevo) caso por caso: matriz de
    transiciones de buckets + lista de los que EMPEORAN y los que MEJORAN.

    Emparejamiento POR POSICIÓN: ambas salidas nacen del mismo `cargar_casos`
    determinístico → la fila i de A es el mismo caso que la fila i de B. Se
    verifica la alineación (proyecto+CUI verdad) y se aborta si difiere."""
    from collections import Counter, defaultdict
    A = json.loads(Path(ruta_a).read_text(encoding="utf-8"))
    B = json.loads(Path(ruta_b).read_text(encoding="utf-8"))
    da, db_ = A["detalle"], B["detalle"]
    if len(da) != len(db_):
        print(f"ERROR: longitudes distintas A={len(da)} B={len(db_)} — no comparables")
        return 1
    desalineados = [i for i, (x, y) in enumerate(zip(da, db_))
                    if x["proyecto"] != y["proyecto"]
                    or _solo_digitos(x["cui_verdad"]) != _solo_digitos(y["cui_verdad"])]
    if desalineados:
        print(f"ERROR: {len(desalineados)} filas desalineadas (p.ej. i={desalineados[0]}) "
              "— las salidas no vienen del mismo orden de casos")
        return 1
    ia = {i: d for i, d in enumerate(da)}
    ib = {i: d for i, d in enumerate(db_)}
    comunes = list(ia)

    print("=" * 84)
    print(f"COMPARACIÓN GOLDEN · A(viejo)={ruta_a.name}  vs  B(nuevo)={ruta_b.name}")
    print("=" * 84)
    print(f"  casos A={len(ia)}  B={len(ib)}  comunes={len(comunes)} (por posición, alineados)")

    # totales por bucket
    ca = Counter(ia[k]["bucket"] for k in comunes)
    cb = Counter(ib[k]["bucket"] for k in comunes)
    print(f"\n  {'bucket':22} {'A(viejo)':>10} {'B(nuevo)':>10} {'dif':>7}")
    print("  " + "-" * 51)
    for bk in ORDEN_BUCKETS:
        d = cb.get(bk, 0) - ca.get(bk, 0)
        print(f"  {bk:22} {ca.get(bk, 0):>10} {cb.get(bk, 0):>10} {d:>+7}")

    # matriz de transiciones viejo→nuevo
    trans = defaultdict(int)
    for k in comunes:
        trans[(ia[k]["bucket"], ib[k]["bucket"])] += 1
    print("\n  Matriz de transiciones (fila = A viejo, col = B nuevo):")
    hdr = "  " + " " * 20 + "".join(f"{b[:9]:>11}" for b in ORDEN_BUCKETS)
    print(hdr)
    for ba in ORDEN_BUCKETS:
        fila = "".join(f"{trans.get((ba, bb), 0):>11}" for bb in ORDEN_BUCKETS)
        print(f"  {ba:20}{fila}")

    # severidad de buckets para decidir mejora/empeora
    rank = {"resuelto_correcto": 0, "revision": 1, "na_privada": 1,
            "portal_caido": 1, "resuelto_incorrecto": 2}

    def _fmt(k: str, da: dict, db: dict) -> str:
        return (f"    [{da['riesgo']:5}] {da['bucket']:20} → {db['bucket']:20}\n"
                f"        verdad={da['cui_verdad']:>8}  "
                f"viejo={da['cui_obtenido'] or '—':>8} (via={da['via'] or '?'})  "
                f"nuevo={db['cui_obtenido'] or '—':>8} (via={db['via'] or '?'})\n"
                f"        {da['proyecto'][:96]}")

    empeoran, mejoran = [], []
    for k in comunes:
        da, db = ia[k], ib[k]
        if da["bucket"] == db["bucket"]:
            continue
        (empeoran if rank[db["bucket"]] > rank[da["bucket"]] else mejoran).append((k, da, db))

    # cualquier resuelto_incorrecto NUEVO (aunque venga de otro incorrecto) es alerta
    print(f"\n  EMPEORAN ({len(empeoran)}):")
    if not empeoran:
        print("    (ninguno)")
    for _, da, db in sorted(empeoran, key=lambda x: -rank[x[2]["bucket"]]):
        print(_fmt(da["proyecto"], da, db))

    print(f"\n  MEJORAN ({len(mejoran)}):")
    if not mejoran:
        print("    (ninguno)")
    for _, da, db in mejoran:
        print(_fmt(da["proyecto"], da, db))

    # foco: incorrectos NUEVOS totales (bucket destino incorrecto)
    inc_b = [ib[k] for k in comunes if ib[k]["bucket"] == "resuelto_incorrecto"]
    print(f"\n  resuelto_incorrecto en B(nuevo): {len(inc_b)}  (criterio: ≤ 16)")
    print("=" * 84)
    return 0


# ── main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Línea base golden del resolver de CUI.")
    ap.add_argument("--limite", type=int, default=None,
                    help="procesar solo los primeros N casos (prueba rápida)")
    ap.add_argument("--solo-cache", action="store_true",
                    help="offline: falla si un caso necesitara tocar la red")
    ap.add_argument("--con-base", action="store_true",
                    help="cablea la base local del MEF (base_mef.instancia()) al "
                         "resolver — habilita fusión de candidatos y fichas MEF")
    ap.add_argument("--salida", type=str, default=None,
                    help="ruta de salida del JSON (por defecto la baseline; usar "
                         "otra para no pisarla)")
    ap.add_argument("--comparar", nargs=2, metavar=("A", "B"),
                    help="modo comparación: no resuelve nada, contrasta dos "
                         "salidas golden (A=viejo B=nuevo) y termina")
    args = ap.parse_args(argv)

    if args.comparar:
        return comparar(Path(args.comparar[0]), Path(args.comparar[1]))

    base = None
    if args.con_base:
        from resolucion import base_mef
        print("Cargando base local del MEF (base_mef.instancia())… "
              "(carga perezosa, ~60 s en el primer uso)", flush=True)
        base = base_mef.instancia()
        # forzar la carga perezosa ahora para que el reloj de casos sea limpio
        _ = base.disponible()
        print(f"  base MEF disponible={base.disponible()}", flush=True)

    salida_path = Path(args.salida) if args.salida else BASELINE

    casos = cargar_casos(args.limite)
    total = len(casos)
    cobertura = resumen_cobertura(casos)
    print(f"Golden CUI · {total} casos únicos del corpus auditado "
          f"({'SOLO-CACHE' if args.solo_cache else 'LIVE'}"
          f"{' · CON-BASE-MEF' if args.con_base else ''})", flush=True)
    print(f"  casos con la experiencia real del espejo: "
          f"{cobertura['enriquecidos']}/{total} "
          f"(degradados: {cobertura['degradados']})", flush=True)

    consulta = ConsultaCacheada(solo_cache=args.solo_cache)
    detalle: list[dict] = []
    t0 = time.perf_counter()

    for i, caso in enumerate(casos, 1):
        r = resolver_caso(caso, consulta, base=base)
        bucket = "portal_caido" if r.get("estado") == "portal_caido" \
            else _bucket(r, caso["cui_verdad"])
        detalle.append({
            "proyecto": caso["proyecto"][:120],
            "cui_verdad": caso["cui_verdad"],
            "cui_obtenido": _solo_digitos(r.get("cui")) or None,
            "estado": r.get("estado"),
            "via": r.get("via"),
            "posible_privada": bool(r.get("posible_privada")),
            "bucket": bucket,
            "riesgo": caso["riesgo"],
            # ADITIVO: `comparar` no lo lee (empareja por posición + proyecto +
            # CUI verdad), pero permite aislar el efecto del ensanche.
            "enriquecido": caso["enriquecido"],
        })
        if not args.solo_cache and i % 5 == 0:
            consulta.guardar()   # crash-safe: persistir cache en corridas largas
        if i % 10 == 0 or i == total:
            dt = time.perf_counter() - t0
            print(f"  … {i}/{total} casos ({dt:.0f}s, {dt / i:.1f}s/caso)", flush=True)
        # pausa gentil entre casos vivos (el portal es flaky → nunca ráfaga)
        if not args.solo_cache and i < total:
            time.sleep(PAUSA_CASO)

    if not args.solo_cache:
        consulta.guardar()

    from collections import Counter
    buckets = Counter(d["bucket"] for d in detalle)
    salida = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modo": "solo_cache" if args.solo_cache else "live",
        "con_base_mef": bool(args.con_base),
        "total": total,
        "buckets": {b: buckets.get(b, 0) for b in ORDEN_BUCKETS},
        "cobertura": cobertura,
        "detalle": detalle,
    }
    salida_path.write_text(json.dumps(salida, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    imprimir_reporte(detalle, total, cobertura)
    print(f"\nGuardado: {salida_path}")
    print(f"Cache:    {CACHE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
