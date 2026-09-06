"""Procedencia para presentación; no resuelve CUI ni decide su certeza."""
from __future__ import annotations


def _dic(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _texto(valor) -> str | None:
    if valor is None:
        return None
    return str(valor).strip() or None


def procedencia_cui(experiencia: dict | None, enriquecimiento: dict | None) -> dict:
    """No convierte el identificador declarado en uno usado por el backend.

    La obra seleccionada tiene la precedencia histórica del endpoint /espejo.
    Se retienen las sub-obras, incluso pendientes y sin CUI, sin escoger una
    para representar todo el certificado.
    """
    exp, enr = _dic(experiencia), _dic(enriquecimiento)
    utilizado = (_dic(enr.get("obra")).get("cui") or enr.get("cui")
                 or _dic(enr.get("verificacion_expediente")).get("cui_confirmado")
                 or _dic(enr.get("obra_ficha")).get("cui"))
    sub_obras = enr.get("sub_obras")
    return {
        "cui_declarado": _texto(exp.get("cui")),
        "cui_utilizado": _texto(utilizado),
        "via": _texto(enr.get("via")),
        "sub_obras": [
            {"nombre": sub.get("nombre") or sub.get("nombre_obra") or sub.get("proyecto"),
             "cui": _texto(sub.get("cui") or _dic(sub.get("obra")).get("cui")),
             "estado": sub.get("estado")}
            for sub in (sub_obras if isinstance(sub_obras, list) else [])
            if isinstance(sub, dict)
        ],
    }


def rotulo_cui(procedencia: dict) -> str:
    """Línea compacta de identidad, no una afirmación de confirmación."""
    declarado = procedencia.get("cui_declarado")
    utilizado = procedencia.get("cui_utilizado")
    if declarado and declarado == utilizado:
        texto = f"CUI {declarado} (declarado y utilizado)"
    else:
        texto = (f"CUI declarado: {declarado or 'no consignado'} · "
                 f"CUI utilizado: {utilizado or 'no registrado'}")
    if procedencia.get("sub_obras"):
        texto += " · Multi-obra: ver identificación por sub-obra"
    return texto
