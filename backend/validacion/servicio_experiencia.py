"""Evidencia y contraste del servicio declarado en una experiencia.

Este módulo es deliberadamente puro: no completa un certificado desde el camino
del concurso, el proyecto, el emisor ni una orientación de búsqueda.
"""
from __future__ import annotations

import re
from typing import Any

_TIPOS = {"supervision_obra", "ejecucion_obra", "elaboracion_expediente",
          "supervision_expediente", "preinversion", "otro", "no_determinado"}
_A_SEACE = {
    "supervision_obra": "supervision",
    "ejecucion_obra": "ejecucion",
    "elaboracion_expediente": "expediente",
    "supervision_expediente": None,
    "preinversion": "preinversion",
    "otro": "otro",
    "no_determinado": None,
}


def _texto(valor: Any) -> str:
    return str(valor).strip() if isinstance(valor, str) else ""


def _evidencia(exp: dict) -> dict:
    """Obtiene el objeto de evidencia sin fabricar campos faltantes."""
    valor = exp.get("servicio_declarado")
    if isinstance(valor, dict):
        return valor
    return {}


def _tipo_literal(texto: str) -> tuple[str | None, str]:
    t = texto.casefold()
    hay_sup = bool(re.search(r"supervisi[oó]n|\bsupervisor\b|\bsupervisora\b", t))
    # «Construcción de X» puede ser solo el nombre del proyecto. Exigimos un
    # acto/rol de servicio; este control de coherencia no vuelve a leer el PDF.
    hay_ejec = bool(re.search(r"ejecuci[oó]n\b|\bresidente\b", t))
    hay_et = bool(re.search(r"elaboraci[oó]n\s+(?:de(?:l| la)?\s+)?(?:expediente|estudio definitivo)", t))
    sup_et = bool(re.search(
        r"(?:supervisi[oó]n|supervisor(?:a)?)\s+(?:de(?:l| la)?\s+)?"
        r"(?:elaboraci[oó]n\s+(?:de(?:l| la)?\s+)?)?"
        r"(?:expediente t[eé]cnico|estudio definitivo)", t))
    hay_pre = bool(re.search(r"preinversi[oó]n|perfil de proyecto|ficha t[eé]cnica", t))
    if bool(re.search(r"\bresidente\b", t)) and hay_sup:
        return None, "El literal mezcla residente y supervisor; no se puede determinar un único servicio."
    if sup_et:
        return "supervision_expediente", "El literal combina supervisión y elaboración de expediente."
    if (hay_sup and hay_et) or (hay_et and hay_ejec):
        return None, "El literal menciona servicios de distintas fases; falta precisar cuál prestó el profesional."
    if hay_sup:
        return "supervision_obra", "El literal identifica supervisión; ‘supervisión de ejecución’ sigue siendo supervisión."
    if hay_et:
        return "elaboracion_expediente", "El literal identifica elaboración de expediente/estudio definitivo."
    if hay_pre:
        return "preinversion", "El literal identifica preinversión/perfil/ficha técnica."
    if hay_ejec:
        return "ejecucion_obra", "El literal identifica ejecución o residencia sin supervisión."
    return None, "El literal no identifica de forma suficiente un servicio de la taxonomía."


def evidencia_validada(ev: dict, fuentes: set[str] | tuple[str, ...] = ("certificado",)) -> tuple[str | None, str]:
    """Valida tipo contractual estructurado, literal, página y fuente."""
    if not isinstance(ev, dict):
        return None, "La evidencia no tiene estructura de servicio."
    tipo = ev.get("tipo")
    texto = _texto(ev.get("texto"))
    pagina = ev.get("pagina_pdf")
    if (not isinstance(tipo, str) or tipo not in _TIPOS - {"otro", "no_determinado"}
            or not texto or not isinstance(pagina, int) or isinstance(pagina, bool)
            or pagina <= 0 or ev.get("fuente") not in tuple(fuentes)):
        return None, "Falta tipo contractual conocido, literal no vacío, página positiva o fuente adecuada."
    detectado, motivo = _tipo_literal(texto)
    if detectado != tipo:
        return None, f"El literal no es coherente con el tipo estructurado ({tipo}); {motivo}"
    return tipo, "Evidencia estructurada y literal coherentes."


def evidencia_tipo_servicio(experiencia: dict) -> dict:
    """Devuelve tipo SEACE solo con literal certificado completo y trazable."""
    exp = experiencia or {}
    ev = _evidencia(exp)
    tipo, motivo = evidencia_validada(ev)
    tipo_seace = _A_SEACE.get(tipo) if tipo else None
    return {"tipo": tipo_seace,
            "fuente": "certificado_literal" if tipo_seace else "sin_evidencia",
            "motivo": motivo}


def contrastar_servicio(espejo: dict, experiencia: dict) -> dict:
    """Contrasta servicio esperado de bases/TDR con literal del certificado."""
    meta = (espejo or {}).get("_meta") or {}
    meta = meta if isinstance(meta, dict) else {}
    esperado = meta.get("servicio_esperado")
    declarado = (experiencia or {}).get("servicio_declarado")
    if not isinstance(declarado, dict):
        declarado = None
    etipo_contrato, motivo_esperado = evidencia_validada(esperado, {"bases", "tdr"})
    dtipo_contrato, motivo_declarado = evidencia_validada(declarado)
    if etipo_contrato and dtipo_contrato and etipo_contrato == dtipo_contrato:
        estado = "coincide"
    elif etipo_contrato and dtipo_contrato:
        estado = "difiere"
    else:
        estado = "no_determinado"
    motivo = {"coincide": "El servicio esperado y el literal del certificado tienen el mismo tipo.",
              "difiere": "El literal del certificado declara un servicio distinto del esperado.",
              "no_determinado": "No hay evidencia completa en ambos lados para contrastar el servicio."}[estado]
    if estado == "no_determinado" and motivo_esperado != "Evidencia estructurada y literal coherentes.":
        motivo += f" Esperado: {motivo_esperado}."
    if estado == "no_determinado" and not dtipo_contrato:
        motivo += f" Declarado: {motivo_declarado}."
    motivo += " Este contraste no decide admisibilidad profesional, contrato, CUI ni cumplimiento."
    return {"esperado": esperado if isinstance(esperado, dict) else None,
            "declarado": declarado,
            "estado": estado, "motivo": motivo}


def fase_servicio_incompatible(espejo: dict, experiencia: dict, es_expediente: bool) -> bool:
    """Marca solo un servicio certificado conocido de la fase opuesta."""
    tipo, _ = evidencia_validada(_evidencia(experiencia or {}))
    if tipo is None:
        return False
    if es_expediente:
        return tipo in {"supervision_obra", "ejecucion_obra"}
    return tipo in {"elaboracion_expediente", "preinversion", "supervision_expediente"}
