"""
ACEPTACIÓN del resolver contra una auditoría visual de certificados — el
instrumento que sustituye a la golden perdida para los casos que un humano ya
revisó folio por folio (ADR-015 §3).

No hay golden y no la habrá (ADR-015 retiró la golden como criterio de
calibración). Lo que sí existe es una AUDITORÍA: un humano abrió los
certificados de una propuesta real y dictaminó, por experiencia, qué debía salir
—el CUI correcto, «privada» o «pendiente legítimo»—. Esta prueba congela ese
veredicto y lo confronta con el resolver actual, re-resolviendo cada experiencia
contra el SNAPSHOT de sus candidatos persistidos
(`scripts/replay_enriquecimiento.py`: mismo código de reconstrucción, sin red).

DATOS PRIVADOS, FUERA DEL REPO. El archivo de veredictos lleva nombres, RUC y
CUI reales de un cliente: vive en la máquina del desarrollador y se inyecta por
entorno. Sin él la prueba se SALTA (nunca falla por ausencia):

    PIVOTE_ACEPTACION_JSON=<ruta>/esperado_identificacion_<caso>.json \\
    PIVOTE_DATA_DIR=<ruta>/backend/datos_pivote \\
    python -m pytest tests/test_aceptacion_auditoria.py -q

Forma del archivo (vocabulario CERRADO de `esperado`):

    {"job": "<job_id>",
     "experiencias": {"<prof>:<exp>": {"esperado": "RESUELTO"|"PRIVADA"|"PENDIENTE",
                                       "cui": "<cui>" | null, "nota": "...",
                                       "resuelto_por_etapa": "CONTRATO" | ...}}}

Corre CON la base local del MEF (también privada): la corrida original la tenía,
y sin ella los vetos de ubigeo/entidad y la fusión de candidatos quedan inertes
—la prueba mediría otro resolver—. Si la base no está disponible, se salta.

## Lo que el replay NO puede reproducir, y cómo se mide igual (ADR-015 §4)

El replay ejercita el RESOLVER sin red. Hay dos clases de resultado que nacen
fuera de él y que exigirle sería medir lo que no hace:

1. **Resuelto por la ETAPA de verificación** (`resuelto_por_etapa` en el
   esperado). Las vías CONTRATO y RESOLUCION identifican el proyecto con una
   fuente oficial del MEF que se consulta EN VIVO (el contrato de expediente o
   la resolución de aprobación, a nombre del consorcio emisor). No hay forma
   offline de reproducirlas. Para esas experiencias la prueba comprueba el
   resultado PERSISTIDO del job —vía CONTRATO/RESOLUCION/MEF con el CUI que la
   auditoría confirma— en vez de exigirle al replay que las resuelva.

2. **Certificados MULTI-OBRA** (ADR-011): el replay los salta por diseño (un
   vínculo, N obras; se resuelven con `resolver_obras`, no con `resolver`).
   Cuando el replay no devuelve resultado para una clave, la prueba lee también
   el resultado persistido: así un multi-obra que el auditor dio por PENDIENTE
   se compara contra lo que el job realmente produjo, y no cuenta como fallo del
   resolver ni se cuela como aprobado sin mirar.

En ambos casos la comparación es contra el archivo del job, que es un HECHO de
la corrida real — no contra una expectativa relajada.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from config import data_dir

# Traducción del vocabulario del resolver al de la auditoría.
_ESTADO_A_VEREDICTO = {"resuelto": "RESUELTO", "na": "PRIVADA"}

# Vías que identifican el proyecto con una fuente oficial del MEF consultada en
# vivo por la etapa de verificación (ADR-010). No son reproducibles offline.
_VIAS_DE_ETAPA = ("CONTRATO", "RESOLUCION", "MEF")


def _veredicto(r: dict) -> tuple[str, str | None]:
    """(veredicto, cui) de un resultado del resolver, en el vocabulario de la
    auditoría. Todo lo que no es `resuelto` ni `na` —revision, sin_cui,
    no_encontrado, portal— es PENDIENTE para el evaluador humano."""
    estado = str(r.get("estado") or "")
    veredicto = _ESTADO_A_VEREDICTO.get(estado, "PENDIENTE")
    cui = str(r.get("cui")) if (veredicto == "RESUELTO" and r.get("cui")) else None
    return veredicto, cui


def _veredicto_persistido(v) -> tuple[str, str | None, str]:
    """(veredicto, cui, vía) de lo que el job REALMENTE dejó escrito para una
    experiencia. El enriquecimiento no guarda `estado`: la vía PRIVADA marca la
    obra privada y la presencia de `cui` marca la identificación."""
    if not isinstance(v, dict) or not v:
        return "PENDIENTE", None, ""
    via = str(v.get("via") or "")
    if via == "PRIVADA":
        return "PRIVADA", None, via
    cui = v.get("cui")
    return ("RESUELTO", str(cui), via) if cui else ("PENDIENTE", None, via)


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


def _persistido(job: str) -> dict:
    """Lo que el job escribió en su corrida real (`enriquecimiento.json`)."""
    return json.loads((data_dir() / job / "enriquecimiento.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def caso() -> tuple[dict, dict, dict]:
    esp = _esperado()
    job = str(esp["job"])
    return esp, _obtenido(job), _persistido(job)


def test_identificacion_coincide_con_la_auditoria(caso):
    """Por experiencia: el resolver dice lo que la auditoría dictaminó.

    Las experiencias que la auditoría marca `resuelto_por_etapa` y las que el
    replay no cubre (multi-obra) se comprueban contra el resultado PERSISTIDO
    del job — ver el encabezado del módulo, ADR-015 §4.

    El mensaje lista TODAS las discrepancias (no corta en la primera) con la
    nota del auditor, que es la que explica qué evidencia del certificado
    resolvía el empate."""
    esperado, obtenido, persistido = caso
    fallos = []
    for clave, e in sorted(esperado["experiencias"].items(),
                           key=lambda kv: tuple(int(x) for x in kv[0].split(":"))):
        quiere, cui_quiere = e["esperado"], (e.get("cui") or None)
        etapa = str(e.get("resuelto_por_etapa") or "")
        r = obtenido.get(clave)
        if etapa or r is None:
            ver, cui, via = _veredicto_persistido(persistido.get(clave))
            fuente = f"etapa {etapa}" if etapa else "sin replay (multi-obra)"
            if ver != quiere or (quiere == "RESUELTO" and cui != cui_quiere):
                fallos.append(f"{clave} [{fuente}]: esperado {quiere}"
                              f"{'/' + str(cui_quiere) if cui_quiere else ''} · "
                              f"persistido {ver}{'/' + str(cui) if cui else ''} (vía {via or '—'})")
            elif etapa and via not in _VIAS_DE_ETAPA:
                fallos.append(f"{clave} [{fuente}]: la auditoría dice que se resolvió por "
                              f"la etapa, pero el job lo registra por vía {via or '—'}")
            continue
        ver, cui = _veredicto(r)
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
    barato (lo mide la prueba de arriba); resolver mal, no.

    Solo cuentan las experiencias cuyo veredicto esperado es RESUELTO **con un
    CUI**: una que el auditor dejó en PENDIENTE (o en PRIVADA) no tiene CUI de
    referencia, así que resolverla es un desacuerdo de abstención —lo mide la
    prueba de arriba— y NUNCA un «cambio de CUI» (ADR-015 §4)."""
    esperado, obtenido, _persistido_ = caso
    cambios = []
    for clave, e in esperado["experiencias"].items():
        if e["esperado"] != "RESUELTO" or not e.get("cui"):
            continue
        ver, cui = _veredicto(obtenido.get(clave) or {})
        if ver == "RESUELTO" and cui and cui != str(e["cui"]):
            cambios.append(f"{clave}: auditoría {e['cui']} · resolver {cui}")
    assert not cambios, "resuelto con un CUI distinto al auditado:\n" + "\n".join(cambios)
