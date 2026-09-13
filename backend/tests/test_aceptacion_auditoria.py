"""
ACEPTACIÓN del resolver contra una auditoría visual de certificados — el
instrumento que sustituye a la golden perdida para los casos que un humano ya
revisó folio por folio.

No hay golden y no la habrá a corto plazo (ver `.ai/handoffs/current.md`, nota
2026-07-28). Lo que sí existe es una AUDITORÍA: un humano abrió los certificados
de una propuesta real y dictaminó, por experiencia, qué debía salir —el CUI
correcto, «privada» o «pendiente legítimo»—. Esta prueba congela ese veredicto y
lo confronta con el resolver actual, re-resolviendo cada experiencia contra el
SNAPSHOT de sus candidatos persistidos (`scripts/replay_enriquecimiento.py`:
mismo código de reconstrucción, sin red).

DATOS PRIVADOS, FUERA DEL REPO. El archivo de veredictos lleva nombres, RUC y
CUI reales de un cliente: vive en la máquina del desarrollador y se inyecta por
entorno. Sin él la prueba se SALTA (nunca falla por ausencia):

    PIVOTE_ACEPTACION_JSON=<ruta>/esperado_identificacion_<caso>.json \
    PIVOTE_DATA_DIR=<ruta>/backend/datos_pivote \
    python -m pytest tests/test_aceptacion_auditoria.py -q

Forma del archivo (vocabulario CERRADO de `esperado`):

    {"job": "<job_id>",
     "experiencias": {"<prof>:<exp>": {"esperado": "RESUELTO"|"PRIVADA"|"PENDIENTE",
                                       "cui": "<cui>" | null, "nota": "..."}}}

Corre CON la base local del MEF (también privada): la corrida original la tenía,
y sin ella los vetos de ubigeo/entidad y la fusión de candidatos quedan inertes
—la prueba mediría otro resolver—. Si la base no está disponible, se salta.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from config import data_dir

# Traducción del vocabulario del resolver al de la auditoría.
_ESTADO_A_VEREDICTO = {"resuelto": "RESUELTO", "na": "PRIVADA"}


def _veredicto(r: dict) -> tuple[str, str | None]:
    """(veredicto, cui) de un resultado del resolver, en el vocabulario de la
    auditoría. Todo lo que no es `resuelto` ni `na` —revision, sin_cui,
    no_encontrado, portal— es PENDIENTE para el evaluador humano."""
    estado = str(r.get("estado") or "")
    veredicto = _ESTADO_A_VEREDICTO.get(estado, "PENDIENTE")
    cui = str(r.get("cui")) if (veredicto == "RESUELTO" and r.get("cui")) else None
    return veredicto, cui


def _esperado() -> dict:
    ruta = os.getenv("PIVOTE_ACEPTACION_JSON", "").strip()
    if not ruta:
        pytest.skip("sin PIVOTE_ACEPTACION_JSON: la auditoría es privada, fuera del repo")
    p = Path(ruta)
    if not p.is_file():
        pytest.skip(f"PIVOTE_ACEPTACION_JSON no existe: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


_CACHE: dict[str, dict] = {}


def _obtenido(job: str) -> dict:
    """Resultados del resolver por clave, re-resueltos contra el snapshot. Se
    cachea: reconstruir el snapshot y resolver 60+ experiencias no es gratis."""
    if job in _CACHE:
        return _CACHE[job]
    from resolucion import base_mef
    from scripts.replay_enriquecimiento import resolver_snapshot

    dj = data_dir() / job
    if not (dj / "espejo.json").is_file() or not (dj / "enriquecimiento.json").is_file():
        pytest.skip(f"sin datos del job {job} en {data_dir()} (PIVOTE_DATA_DIR)")
    base = base_mef.instancia()
    if not base.disponible():
        pytest.skip("base local del MEF no disponible: la aceptación mediría otro resolver")
    resultados, _meta = resolver_snapshot(job, data_dir(), base=base)
    _CACHE[job] = resultados
    return resultados


@pytest.fixture(scope="module")
def caso() -> tuple[dict, dict]:
    esp = _esperado()
    return esp, _obtenido(str(esp["job"]))


def test_identificacion_coincide_con_la_auditoria(caso):
    """Por experiencia: el resolver dice lo que la auditoría dictaminó.

    El mensaje lista TODAS las discrepancias (no corta en la primera) con la
    nota del auditor, que es la que explica qué evidencia del certificado
    resolvía el empate."""
    esperado, obtenido = caso
    fallos = []
    for clave, e in sorted(esperado["experiencias"].items(),
                           key=lambda kv: tuple(int(x) for x in kv[0].split(":"))):
        r = obtenido.get(clave)
        if r is None:
            fallos.append(f"{clave}: sin resultado en el replay (¿multi-obra?)")
            continue
        ver, cui = _veredicto(r)
        quiere, cui_quiere = e["esperado"], (e.get("cui") or None)
        if ver != quiere or (quiere == "RESUELTO" and cui != cui_quiere):
            fallos.append(
                f"{clave}: esperado {quiere}"
                f"{'/' + str(cui_quiere) if cui_quiere else ''} · "
                f"obtenido {ver}{'/' + str(cui) if cui else ''} · "
                f"{str(r.get('decision') or '')[:120]}"
            )
    assert not fallos, ("la identificación no coincide con la auditoría en "
                        f"{len(fallos)} experiencias:\n" + "\n".join(fallos))


def test_ninguna_resuelta_cambia_de_cui(caso):
    """Candado de la Regla de oro sobre este caso: ninguna experiencia que la
    auditoría dio por RESUELTA puede salir resuelta con OTRO CUI. Abstenerse es
    barato (lo mide la prueba de arriba); resolver mal, no."""
    esperado, obtenido = caso
    cambios = []
    for clave, e in esperado["experiencias"].items():
        if e["esperado"] != "RESUELTO" or not e.get("cui"):
            continue
        ver, cui = _veredicto(obtenido.get(clave) or {})
        if ver == "RESUELTO" and cui and cui != str(e["cui"]):
            cambios.append(f"{clave}: auditoría {e['cui']} · resolver {cui}")
    assert not cambios, "resuelto con un CUI distinto al auditado:\n" + "\n".join(cambios)
