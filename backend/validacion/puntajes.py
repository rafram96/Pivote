"""Reconciliación final de factores y puntaje técnico (#90/#91)."""
from __future__ import annotations


def reconciliar_puntajes(espejo: dict) -> dict:
    resumen = espejo.setdefault("resumen_evaluacion", {})
    minimo = maximo = 0.0
    condicionado = False
    sin_cota = False
    for factor in resumen.get("factores", []) or []:
        if factor.get("aplica") is False or isinstance(factor.get("puntaje"), str):
            factor["estado_puntaje"] = "no_aplica"
            continue
        puntaje = factor.get("puntaje")
        pmin = factor.get("puntaje_confirmado")
        if pmin is None:
            pmin = puntaje
        pmax = factor.get("puntaje_maximo_posible")
        if pmax is None:
            pmax = puntaje
        # Un factor condicionado con máximo conocido (p. ej. el que valora el
        # Comité, 0–25) tiene piso 0 aunque el evaluador no haya escrito el
        # confirmado: NO es «sin cota». Sin cota es solo no conocer el máximo.
        if pmin is None and isinstance(pmax, (int, float)):
            pmin = 0
        if isinstance(pmin, (int, float)):
            minimo += float(pmin)
        else:
            condicionado = sin_cota = True
        if isinstance(pmax, (int, float)):
            maximo += float(pmax)
        else:
            condicionado = sin_cota = True
        if puntaje is None or factor.get("estado_puntaje") == "condicionado":
            condicionado = True
        elif factor.get("estado_puntaje") is None:
            factor["estado_puntaje"] = "definitivo"
            factor["puntaje_confirmado"] = puntaje
            factor["puntaje_maximo_posible"] = puntaje

    resumen["puntaje_confirmado"] = round(minimo, 6)
    resumen["puntaje_maximo_posible"] = None if sin_cota else round(maximo, 6)
    resumen["estado_puntaje"] = "condicionado" if condicionado else "definitivo"
    resumen["puntaje_total"] = None if condicionado else round(minimo, 6)
    if condicionado:
        rango = (f"entre {minimo:g} y {maximo:g} puntos"
                 if not sin_cota else f"al menos {minimo:g} puntos, con factores sin cota")
        resumen["nota"] = f"Puntaje técnico condicionado: {rango}."
    else:
        resumen["nota"] = f"Puntaje técnico total definitivo: {minimo:g} puntos."
    return resumen
