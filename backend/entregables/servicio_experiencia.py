"""Presentación del contraste de servicio, común a Excel y ZIP."""
from validacion.servicio_experiencia import contrastar_servicio


ETIQUETAS_SERVICIO = {
    "supervision_obra": "Supervisión de obra",
    "ejecucion_obra": "Ejecución de obra",
    "elaboracion_expediente": "Elaboración de expediente técnico",
    "supervision_expediente": "Supervisión de expediente técnico",
    "preinversion": "Preinversión",
    "otro": "Otro servicio",
    "no_determinado": "No determinado",
}


def describir_servicio(evidencia):
    """No sustituye una página ausente por el folio o el rango de la experiencia."""
    evidencia = evidencia if isinstance(evidencia, dict) else {}
    tipo = ETIQUETAS_SERVICIO.get(evidencia.get("tipo"), "No determinado")
    literal = evidencia.get("texto")
    fuente = evidencia.get("fuente")
    pagina = evidencia.get("pagina_pdf")
    referencia = ", ".join(str(x) for x in (
        fuente, f"página PDF {pagina}" if pagina else None) if x)
    partes = [tipo]
    if literal:
        partes.append(f"«{literal}»")
    if referencia:
        partes.append(f"({referencia})")
    return ". ".join(partes)


def filas_contraste_servicio(contraste):
    """Filas breves; la coincidencia no se rotula como cumplimiento."""
    contraste = contraste if isinstance(contraste, dict) else {}
    return [
        ("SERVICIO ESPERADO (concurso)", describir_servicio(contraste.get("esperado"))),
        ("SERVICIO DECLARADO (certificado)", describir_servicio(contraste.get("declarado"))),
        ("CONTRASTE DE SERVICIO", contraste.get("motivo") or "Servicio no determinado."),
    ]


def lineas_contraste_servicio(espejo, experiencia):
    return [f"{etiqueta}: {valor}" for etiqueta, valor in
            filas_contraste_servicio(contrastar_servicio(espejo, experiencia))]
