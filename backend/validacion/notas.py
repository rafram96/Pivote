"""
Validador determinístico — las verificaciones PURAS de las 15 NOTAS
(spec: docs/backend/validador.md). Funciones sobre el espejo (dict crudo ya
validado de schema); devuelven `pipeline.Observacion` — el sistema señala,
no juzga ni corrige.

Implementadas aquí (no requieren bases ni fuentes externas):
  N1  — cross-check de conteo vs Anexo 16 (si viene estructurado)
  N7  — orden de experiencias por fecha_final ascendente
  N9  — traslapes recalculados vs lo que Claude marcó
  N10 — ventana COVID recalculada vs `incluye_covid`
  +   — veredictos obligatorios no vacíos (hallazgo del Excel real)
  +   — totales del profesional vs suma de experiencias
  +   — puntaje_total vs suma de factores

Quedan para la etapa con más insumos: N15 (necesita el nº de cargos de las
bases), N2/N4 (consistencia con juicios), N14 (consorciados ↔ ISOs).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from schemas import pipeline

COVID_INICIO = date(2020, 3, 16)
COVID_FIN = date(2020, 6, 30)

_E = pipeline.Etapa.VALIDACION
_SEV = pipeline.Severidad


def _obs(codigo: str, severidad, mensaje: str, referencia: Optional[str] = None) -> pipeline.Observacion:
    return pipeline.Observacion(
        codigo=codigo, severidad=severidad, mensaje=mensaje,
        origen=_E, referencia=referencia)


def _fecha_iso(v) -> Optional[date]:
    """date solo si el valor es una fecha ISO completa (sentinels/parciales → None)."""
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) == 10:
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _es_si(v) -> Optional[bool]:
    """Normaliza los flags texto del espejo ('SÍ…'/'NO…') a bool; None si no se sabe."""
    if not isinstance(v, str) or not v.strip():
        return None
    t = v.strip().upper()
    if t.startswith(("SÍ", "SI")):
        return True
    if t.startswith("NO"):
        return False
    return None


# ── N1 · cross-check de conteo vs cuadro resumen del Anexo 16 ────────────────

def nota1_conteo(prof: dict) -> list[pipeline.Observacion]:
    out = []
    n_prof = prof.get("n_prof")
    extraidas = len(prof.get("experiencias", []))
    for cc in prof.get("cross_checks", []) or []:
        valor = cc.get("valor")
        if not isinstance(valor, dict):
            continue  # cross-check en prosa: no verificable determinísticamente
        declaradas = valor.get("declaradas")
        if isinstance(declaradas, int) and declaradas != extraidas:
            out.append(_obs(
                "NOTA1", _SEV.ADVERTENCIA,
                f"conteo no cuadra: {extraidas} experiencias extraídas vs "
                f"{declaradas} declaradas en el Anexo 16",
                f"prof={n_prof}"))
        if valor.get("cuadra") is False:
            out.append(_obs(
                "NOTA1", _SEV.ADVERTENCIA,
                "el subagente reportó que el cross-check NO cuadró tras sus reintentos",
                f"prof={n_prof}"))
    return out


# ── N7 · orden por fecha_final ascendente ────────────────────────────────────

def nota7_orden(prof: dict) -> list[pipeline.Observacion]:
    fechas = [
        (e.get("n"), _fecha_iso(e.get("fecha_final")))
        for e in prof.get("experiencias", [])
    ]
    fechas = [(n, f) for n, f in fechas if f is not None]
    desorden = [
        f"exp {n2} ({f2}) antes que exp {n1} ({f1})"
        for (n1, f1), (n2, f2) in zip(fechas, fechas[1:])
        if f2 < f1
    ]
    if desorden:
        return [_obs(
            "NOTA7", _SEV.INFO,
            "experiencias fuera de orden por fecha_final ascendente: " + "; ".join(desorden),
            f"prof={prof.get('n_prof')}")]
    return []


# ── N9 · traslapes recalculados vs marcados ──────────────────────────────────

def nota9_traslapes(prof: dict) -> list[pipeline.Observacion]:
    out = []
    n_prof = prof.get("n_prof")
    exps = prof.get("experiencias", [])
    periodos = []
    for e in exps:
        ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
        if ini and fin and fin >= ini:
            periodos.append((e.get("n"), ini, fin))

    # pares que realmente se solapan (≥1 día en común)
    en_traslape: set = set()
    for i, (n_a, ia, fa) in enumerate(periodos):
        for n_b, ib, fb in periodos[i + 1:]:
            if ib <= fa and ia <= fb:
                en_traslape.update((n_a, n_b))

    for e in exps:
        n = e.get("n")
        marcado = _es_si(e.get("traslape"))
        menciona_texto = "TRASLAP" in str(e.get("observaciones") or "").upper()
        if n in en_traslape and marcado is not True:
            if menciona_texto:
                # Claude SÍ lo detectó (vive en observaciones, texto libre) pero
                # no llenó el campo estructurado — gap de estructura, no de juicio.
                out.append(_obs(
                    "NOTA9", _SEV.ADVERTENCIA,
                    "traslape real detectado por Claude en observaciones (texto libre) "
                    "pero sin marcar el campo estructurado `traslape`",
                    f"prof={n_prof} exp={n}"))
            else:
                out.append(_obs(
                    "NOTA9", _SEV.ALERTA,
                    "traslape real entre periodos NO marcado por Claude",
                    f"prof={n_prof} exp={n}"))
        elif n not in en_traslape and marcado is True:
            out.append(_obs(
                "NOTA9", _SEV.ADVERTENCIA,
                "marcado como traslape pero las fechas no se solapan",
                f"prof={n_prof} exp={n}"))
    return out


# ── N10 · ventana COVID recalculada ──────────────────────────────────────────

def nota10_covid(prof: dict) -> list[pipeline.Observacion]:
    out = []
    for e in prof.get("experiencias", []):
        ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
        if not (ini and fin):
            continue
        real = ini <= COVID_FIN and fin >= COVID_INICIO
        marcado = _es_si(e.get("incluye_covid"))
        if marcado is not None and marcado != real:
            out.append(_obs(
                "NOTA10", _SEV.ALERTA,
                f"incluye_covid={'SÍ' if marcado else 'NO'} pero el periodo "
                f"{ini}→{fin} {'SÍ' if real else 'NO'} intersecta la ventana "
                f"{COVID_INICIO}–{COVID_FIN}",
                f"prof={prof.get('n_prof')} exp={e.get('n')}"))
    return out


# ── Veredictos obligatorios (hallazgo del Excel real: 3 venían vacíos) ───────

def veredictos_no_vacios(prof: dict) -> list[pipeline.Observacion]:
    cumple = prof.get("cumple")
    # El veredicto del profesional usa el vocabulario CUMPLE / NO CUMPLE (no SÍ/NO,
    # que es para flags como incluye_covid). Es concluyente si empieza con CUMPLE,
    # NO (cubre "NO CUMPLE") o SÍ/SI (legacy); vacío/None/"—" → alerta.
    t = cumple.strip().upper() if isinstance(cumple, str) else ""
    if t.startswith(("CUMPLE", "NO", "SÍ", "SI")):
        return []
    return [_obs(
        "VEREDICTO", _SEV.ALERTA,
        f"veredicto 'cumple' del profesional vacío o no concluyente: {cumple!r}",
        f"prof={prof.get('n_prof')}")]


# ── Totales del profesional vs suma de experiencias ─────────────────────────

def totales_cuadran(prof: dict) -> list[pipeline.Observacion]:
    exps = prof.get("experiencias", [])
    dias = [e.get("dias") for e in exps]
    if not dias or any(not isinstance(d, (int, float)) for d in dias):
        return []
    suma = sum(dias)
    total = (prof.get("total") or {}).get("dias")
    if isinstance(total, (int, float)) and abs(total - suma) > len(exps):  # ±1 día/exp
        return [_obs(
            "TOTAL", _SEV.ADVERTENCIA,
            f"total.dias={total} no cuadra con la suma de experiencias ({suma})",
            f"prof={prof.get('n_prof')}")]
    return []


# ── Puntaje total vs factores ────────────────────────────────────────────────

def puntaje_total_cuadra(espejo: dict) -> list[pipeline.Observacion]:
    resumen = espejo.get("resumen_evaluacion") or {}
    factores = resumen.get("factores") or []
    numericos = [f.get("puntaje") for f in factores if isinstance(f.get("puntaje"), (int, float))]
    total = resumen.get("puntaje_total")
    if not numericos or not isinstance(total, (int, float)):
        return []
    if abs(sum(numericos) - total) > 0.01:
        return [_obs(
            "PUNTAJE", _SEV.ALERTA,
            f"puntaje_total={total} ≠ suma de factores ({sum(numericos)})")]
    return []


# ── Corrida completa ─────────────────────────────────────────────────────────

def verificar_espejo(espejo: dict) -> list[pipeline.Observacion]:
    """Corre todas las notas puras sobre un espejo (dict ya válido de schema)."""
    out: list[pipeline.Observacion] = []
    for prof in espejo.get("profesionales", []):
        out.extend(nota1_conteo(prof))
        out.extend(nota7_orden(prof))
        out.extend(nota9_traslapes(prof))
        out.extend(nota10_covid(prof))
        out.extend(veredictos_no_vacios(prof))
        out.extend(totales_cuadran(prof))
    out.extend(puntaje_total_cuadra(espejo))
    return out
