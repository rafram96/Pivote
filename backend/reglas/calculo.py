"""
Motor de reglas — Paso 5 (días efectivos) y ALT03. Funciones puras.

Convenciones verificadas contra las hojas manuales del ingeniero en el formato
definitivo (`02. Formato de evaluacion COMPLETADO.xlsx`, hojas JEFE/Estructura):

- **Conteo INCLUSIVO**: días(a, b) = (b − a) + 1. Verificado en 6 pares
  (ej. 2016-06-10 → 2017-05-15 = 340; 2019-05-01 → 2019-10-31 = 184).
- **Días efectivos** = brutos − paralizaciones (InfoObras) − traslapes (ALT11).
  Reconciliación golden hoja CLAUDE ↔ hoja JEFE: 1857 brutos − 212 paralizados
  = 1645 efectivos (4.5068 años).
- meses = días/30 · años = días/365 (convención del flujo del ingeniero).
- **ALT03**: experiencia con inicio anterior a (fecha_presentacion − 25 años)
  → alerta. Cutoff 25 confirmado por el cliente el 2026-06-10.

La etapa REGLAS del orquestador envuelve estas funciones; aquí no hay I/O.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Optional

from schemas.enriquecimiento import DiasEfectivos, Intervalo

CUTOFF_ANIOS_ALT03 = 25
_UN_DIA = timedelta(days=1)


# ── Aritmética de intervalos (todas las fechas son date; intervalos inclusivos) ──

def dias_inclusivos(inicio: date, fin: date) -> int:
    """Días calendario contando ambos extremos (convención del ingeniero)."""
    if fin < inicio:
        raise ValueError(f"fin < inicio: {inicio} → {fin}")
    return (fin - inicio).days + 1


def periodo_fechas(p) -> tuple[date, date]:
    """Normaliza un periodo a (inicio, fin) como `date`. Acepta:
      - tupla/lista (date|iso, date|iso)
      - dict {"inicio": date|iso, "fin": date|iso, "tipo"?: str}
    Así el cálculo no depende de si el periodo trae o no su 'tipo' (paralizado
    vs sin valorización) — eso es solo para la presentación."""
    if isinstance(p, dict):
        a, b = p.get("inicio"), p.get("fin")
    else:
        a, b = p[0], p[1]
    a = a if isinstance(a, date) else date.fromisoformat(str(a)[:10])
    b = b if isinstance(b, date) else date.fromisoformat(str(b)[:10])
    return a, b


def _normalizar(intervalos: Iterable[tuple[date, date]]) -> list[tuple[date, date]]:
    """Ordena y fusiona intervalos que se traslapan O son contiguos (unión).
    La fusión de contiguos no afecta el conteo de traslape (suma idéntica)."""
    ordenados = sorted(intervalos, key=lambda iv: iv[0])
    union: list[tuple[date, date]] = []
    for ini, fin in ordenados:
        if fin < ini:
            raise ValueError(f"intervalo inválido: {ini} → {fin}")
        if union and ini <= union[-1][1] + _UN_DIA:
            union[-1] = (union[-1][0], max(union[-1][1], fin))
        else:
            union.append((ini, fin))
    return union


def restar_paralizaciones(
    periodo: tuple[date, date],
    paralizaciones: Iterable[tuple[date, date]],
) -> list[tuple[date, date]]:
    """Tramos EFECTIVOS de un periodo tras quitarle las paralizaciones.

    Réplica de lo que el ingeniero hace a mano ("Experiencia certificado" →
    "Experiencia Efectiva"): el certificado 2021-05-13→2023-05-06 con obra
    paralizada oct-2021, feb–abr-2022 y jul–sep-2022 queda en 4 tramos
    (141 + 92 + 61 + 218 días).
    """
    ini, fin = periodo
    if fin < ini:
        raise ValueError(f"periodo inválido: {ini} → {fin}")
    # Recortar cada paralización al periodo y unirlas. Se descartan las
    # paralizaciones invertidas (p_fin < p_ini): son datos corruptos del portal
    # InfoObras y no deben tumbar el cálculo de TODOS los profesionales — la
    # etapa las marca aparte para revisión humana.
    recortadas = [
        (max(p_ini, ini), min(p_fin, fin))
        for p_ini, p_fin in paralizaciones
        if p_fin >= p_ini and p_fin >= ini and p_ini <= fin
    ]
    tramos: list[tuple[date, date]] = []
    cursor = ini
    for p_ini, p_fin in _normalizar(recortadas):
        if p_ini > cursor:
            tramos.append((cursor, p_ini - _UN_DIA))
        cursor = max(cursor, p_fin + _UN_DIA)
    if cursor <= fin:
        tramos.append((cursor, fin))
    return tramos


def fusionar_traslapes(
    intervalos: Iterable[tuple[date, date]],
) -> tuple[list[tuple[date, date]], int]:
    """ALT11: un profesional no acumula doble por estar 'en dos obras a la vez'.

    Devuelve (intervalos fusionados, días de traslape descontados).
    Los intervalos meramente contiguos (uno termina y el otro empieza al día
    siguiente) se unen pero NO cuentan traslape.
    """
    lista = list(intervalos)
    if not lista:
        return [], 0
    union = _normalizar(lista)
    dias_brutos = sum(dias_inclusivos(i, f) for i, f in lista)
    dias_union = sum(dias_inclusivos(i, f) for i, f in union)
    return union, dias_brutos - dias_union


# ── Días efectivos (Paso 5) ───────────────────────────────────────────────────

def dias_efectivos_profesional(
    experiencias: Iterable[tuple[date, date]],
    paralizaciones_por_exp: Optional[dict[int, list[tuple[date, date]]]] = None,
) -> DiasEfectivos:
    """Paso 5 completo para un profesional.

    `experiencias`: periodos [inicio, fin] en el orden del espejo (índice 0..n-1).
    `paralizaciones_por_exp`: {índice → paralizaciones de la obra de esa exp}.

    brutos = Σ días de cada periodo (lo que reporta Claude en la hoja CLAUDE)
    paralizados = lo descontado por InfoObras
    traslape = lo descontado por ALT11 sobre los tramos ya-efectivos
    efectivos = brutos − paralizados − traslape (lo de la hoja por profesional)
    """
    paralizaciones_por_exp = paralizaciones_por_exp or {}
    periodos = list(experiencias)
    dias_brutos = sum(dias_inclusivos(i, f) for i, f in periodos)

    tramos_efectivos: list[tuple[date, date]] = []
    for idx, periodo in enumerate(periodos):
        tramos_efectivos.extend(
            restar_paralizaciones(periodo, paralizaciones_por_exp.get(idx, []))
        )
    dias_tras_paralizacion = sum(dias_inclusivos(i, f) for i, f in tramos_efectivos)
    dias_paralizados = dias_brutos - dias_tras_paralizacion

    fusionados, dias_traslape = fusionar_traslapes(tramos_efectivos)
    dias_efectivos = dias_tras_paralizacion - dias_traslape

    return DiasEfectivos(
        dias_brutos=dias_brutos,
        dias_paralizados=dias_paralizados,
        dias_traslape=dias_traslape,
        dias_efectivos=dias_efectivos,
        intervalos_fusionados=[Intervalo(inicio=i, fin=f) for i, f in fusionados],
    )


def anios(dias: int) -> float:
    return dias / 365


def meses(dias: int) -> float:
    return dias / 30


# ── ALT03 · experiencia demasiado antigua ─────────────────────────────────────

def fecha_cutoff(fecha_presentacion: date, cutoff_anios: int = CUTOFF_ANIOS_ALT03) -> date:
    """fecha_presentacion − N años (29-feb cae a 28-feb en años no bisiestos)."""
    anio = fecha_presentacion.year - cutoff_anios
    try:
        return fecha_presentacion.replace(year=anio)
    except ValueError:  # 29 de febrero
        return fecha_presentacion.replace(year=anio, day=28)


def alerta_experiencia_antigua(
    fecha_inicial: date,
    fecha_presentacion: date,
    cutoff_anios: int = CUTOFF_ANIOS_ALT03,
) -> bool:
    """True si la experiencia empezó antes del cutoff (ALT03)."""
    return fecha_inicial < fecha_cutoff(fecha_presentacion, cutoff_anios)
