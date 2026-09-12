"""Proyección de identidad común a las salidas; no selecciona ni verifica obras.

Acepta enriquecimiento original o la ficha efímera del generador Excel. Las
reglas y los textos siguen perteneciendo a ``certeza`` y ``procedencia``.
"""
from __future__ import annotations

from entregables.certeza import (
    alertas_experiencia, clasificar_identificacion, identificacion_panel,
)
from entregables.procedencia import procedencia_cui, rotulo_cui


def proyectar_identidad(experiencia: dict | None, enriquecimiento: dict | None,
                       tipo_evaluacion: str | None = None) -> dict:
    """Prepara la identidad una vez por consumidor, sin mutar las entradas.

    La ficha Excel conserva una referencia de lectura al enriquecimiento
    original: su CUI aplanado es un dato de presentación, no un sustituto de
    la evidencia que recibe la API. En llamadas legacy se admite la procedencia
    ya preparada, pero el CUI declarado SIEMPRE procede de la experiencia.

    No se añade la clasificación de expedientes a la ruta de obras. Tampoco
    se confunden los identificadores declarado/utilizado con su certeza.
    """
    exp = experiencia if isinstance(experiencia, dict) else {}
    enr = enriquecimiento if isinstance(enriquecimiento, dict) else {}
    original = enr.get("_enriquecimiento_identidad")
    contexto = original if isinstance(original, dict) else enr
    # El generador admite SUNAT por un canal separado; una llamada legacy
    # puede completarlo o retirarlo sin reescribir el enriquecimiento original.
    if isinstance(original, dict) and "sunat" in enr:
        contexto = {**original, "sunat": enr["sunat"]}
    procedencia = procedencia_cui(exp, contexto)
    legado = enr.get("_procedencia_cui")
    if not isinstance(original, dict) and isinstance(legado, dict) and legado:
        procedencia = {**legado, "cui_declarado": procedencia["cui_declarado"]}

    certeza = identificacion = None
    alertas = []
    if tipo_evaluacion == "expedientes":
        certeza = clasificar_identificacion(exp, contexto)
        identificacion = identificacion_panel(exp, contexto)
        alertas = alertas_experiencia(exp, contexto)
    return {
        "procedencia": procedencia,
        "rotulo_cui": rotulo_cui(procedencia),
        "certeza": certeza,
        "identificacion": identificacion,
        "alertas": alertas,
    }
