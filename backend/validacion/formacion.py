"""Compuerta documental de formación profesional (#89).

No consulta registros externos. Interpreta únicamente la regla estructurada de
las bases y los hechos extraídos de la propuesta; cualquier comprobación
registral queda rotulada como revisión manual del Comité.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HallazgoFormacion:
    n_prof: int
    estado: str
    mensaje: str


def _si(v) -> bool:
    return v is True or (isinstance(v, str) and v.strip().lower() in {
        "si", "sí", "true", "1", "requerido", "obligatorio",
    })


def _modalidad(regla: dict) -> str:
    return str(regla.get("modalidad") or regla.get("via") or "").strip().lower()


def aplicar_reglas_formacion(espejo: dict) -> list[HallazgoFormacion]:
    """Muta solo el veredicto visible y `_backend.formacion`; es idempotente."""
    hallazgos: list[HallazgoFormacion] = []
    for prof in espejo.get("profesionales", []) or []:
        regla = ((prof.get("requisitos") or {}).get("acreditacion_formacion") or {})
        if not isinstance(regla, dict) or not regla:
            continue
        n_prof = int(prof.get("n_prof") or 0)
        hechos = prof.get("acreditacion_formacion") or {}
        if not isinstance(hechos, dict):
            hechos = {}
        titulo = hechos.get("titulo_declarado") or prof.get("titulo")
        universidad = hechos.get("universidad_declarada")
        identidad = hechos.get("documento_identidad") or prof.get("dni")
        diploma = hechos.get("diploma_adjunto")
        constancia = hechos.get("constancia_colegiatura_adjunta")
        completa = hechos.get("extraccion_completa") is True
        requiere_diploma = _si(regla.get("diploma_adjunto_requerido"))
        requiere_constancia = _si(regla.get("constancia_colegiatura_adjunta_requerida"))
        modalidad = _modalidad(regla)
        declaracion_registro = modalidad in {
            "anexo_15_registro_publico", "declaracion_y_registro",
            "declaracion_y_revision_manual", "anexo_15",
        }

        backend = prof.setdefault("_backend", {})
        previo = backend.get("formacion") if isinstance(backend.get("formacion"), dict) else {}
        resolucion = previo.get("verificacion_registral")

        faltantes_obligatorios = []
        if requiere_diploma and diploma is not True:
            faltantes_obligatorios.append("diploma")
        if requiere_constancia and constancia is not True:
            faltantes_obligatorios.append("constancia de colegiatura")

        if resolucion == "resuelta_cumple":
            estado = "CUMPLE"
            mensaje = "CUMPLE — verificación registral resuelta manualmente por el Comité."
        elif resolucion == "resuelta_no_cumple":
            estado = "NO_CUMPLE"
            mensaje = "NO CUMPLE — verificación registral resuelta manualmente por el Comité."
        elif faltantes_obligatorios and completa:
            estado = "NO_CUMPLE"
            mensaje = ("NO CUMPLE — falta " + " y ".join(faltantes_obligatorios)
                       + ", documento exigido expresamente por las bases.")
        elif faltantes_obligatorios:
            estado = "REVISION_MANUAL"
            mensaje = ("POR VERIFICAR — la extracción no permite confirmar "
                       + " y ".join(faltantes_obligatorios) + ".")
        elif declaracion_registro and titulo and universidad and identidad:
            estado = "REVISION_MANUAL"
            mensaje = ("POR VERIFICAR — Anexo 15 documentalmente completo; la "
                       "comprobación registral corresponde al Comité y no se automatiza.")
        elif declaracion_registro:
            estado = "REVISION_MANUAL"
            mensaje = ("POR VERIFICAR — no se confirmó la totalidad de los datos del "
                       "Anexo 15; revisar el documento, sin exigir un diploma no pedido.")
        else:
            # Para modalidades documentales distintas, no fabricamos una regla.
            estado = "REVISION_MANUAL"
            mensaje = "POR VERIFICAR — revisar la acreditación según el texto literal de las bases."

        backend["formacion"] = {
            **previo,
            "estado_documental": "cumple" if not faltantes_obligatorios else "por_verificar",
            "verificacion_registral": resolucion or (
                "revision_manual" if declaracion_registro else "no_aplica"),
            "estado": estado.lower(),
            "mensaje": mensaje,
        }
        # Esta columna era donde el LLM producía el falso NO CUMPLE. Desde ahora
        # la compuerta documental manda cuando existe una regla estructurada.
        prof["profesion_valida"] = mensaje
        hallazgos.append(HallazgoFormacion(n_prof, estado, mensaje))
    return hallazgos
