"""Conciliación histórica pura para concursos explícitos de expedientes."""
from __future__ import annotations

from typing import Optional

from entregables.certeza import (
    MULTI_OBRA,
    PRIVADA,
    SIN_IDENTIFICAR,
    clasificar_identificacion,
)
from reglas import anios, dias_efectivos_profesional
from validacion.recalculo import fechas_calculo, regla_periodos_de


_DERIVADOS = frozenset({
    "dias_brutos", "dias_paralizados", "dias_traslape", "dias_efectivos",
    "anios_efectivos", "cumple_backend", "veredicto_provisional",
    "cobertura_baja", "minimo_dias", "minimo_texto", "minimo_anios",
    "experiencias_excluidas",
})


def _vacia(valor: object) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def motivo_periodo_no_computable(exp: dict, regla: str) -> Optional[str]:
    """Explica por qué el período no se puede contar, sin lanzar por datos malos."""
    if not isinstance(exp, dict):
        return "faltan las fechas inicial y final"
    try:
        inicio, fin, _ = fechas_calculo(exp, regla)
    except (TypeError, ValueError, OverflowError):
        inicio = fin = None
    if inicio is not None and fin is not None:
        return "la fecha final es anterior a la fecha inicial" if fin < inicio else None

    literal_inicio = exp.get("fecha_inicial")
    literal_fin = exp.get("fecha_final")
    if inicio is None and fin is None:
        if _vacia(literal_inicio) and _vacia(literal_fin):
            return "faltan las fechas inicial y final"
        if _vacia(literal_inicio):
            return "falta la fecha inicial y la fecha final no es legible"
        if _vacia(literal_fin):
            return "falta la fecha final y la fecha inicial no es legible"
        return "las fechas inicial y final no son legibles con la regla vigente"
    if inicio is None:
        return ("falta la fecha inicial" if _vacia(literal_inicio)
                else "la fecha inicial no es legible con la regla vigente")
    return ("falta la fecha final" if _vacia(literal_fin)
            else "la fecha final no es legible con la regla vigente")


def _sub_obras_pendientes(enriquecimiento: dict) -> bool:
    sub_obras = enriquecimiento.get("sub_obras")
    if not isinstance(sub_obras, list):
        return False
    resueltas = sum(
        1 for sub in sub_obras
        if isinstance(sub, dict) and str(sub.get("estado") or "").strip() == "resuelto"
    )
    return resueltas < len(sub_obras)


def _motivo_identificacion(exp: dict, enriquecimiento: dict) -> Optional[str]:
    certeza = clasificar_identificacion(exp, enriquecimiento)
    nivel = certeza.get("nivel")
    if nivel == PRIVADA:
        sunat = enriquecimiento.get("sunat")
        if not (sunat if isinstance(sunat, dict) else {}).get("ruc"):
            return "identificación del emisor privado pendiente en SUNAT"
        return None
    if enriquecimiento.get("identificacion_incompleta"):
        return "sub-obras pendientes"
    if enriquecimiento.get("sin_verificar"):
        return "identificación del expediente pendiente"
    if nivel == SIN_IDENTIFICAR:
        return "identificación del expediente pendiente"
    if nivel == MULTI_OBRA and _sub_obras_pendientes(enriquecimiento):
        return "sub-obras pendientes"
    return None


def _agregado_limpio(valor: object) -> dict:
    anterior = dict(valor) if isinstance(valor, dict) else {}
    return {clave: valor for clave, valor in anterior.items() if clave not in _DERIVADOS}


def reconciliar_expedientes(espejo: dict, enriquecimiento: Optional[dict]) -> dict[int, dict]:
    """Recalcula días y estado de expedientes persistidos, sin mutar las entradas."""
    from orquestador.etapas_reales import _minimo_exigido

    espejo = espejo if isinstance(espejo, dict) else {}
    enriquecimiento = enriquecimiento if isinstance(enriquecimiento, dict) else {}
    regla = regla_periodos_de(espejo)
    salida: dict[int, dict] = {}

    for profesional in espejo.get("profesionales", []) or []:
        if not isinstance(profesional, dict):
            continue
        n_prof = profesional.get("n_prof")
        periodos = []
        pendientes: dict[object, list[str]] = {}
        excluidas = []

        for experiencia in profesional.get("experiencias", []) or []:
            if not isinstance(experiencia, dict):
                continue
            n_exp = experiencia.get("n")
            motivo_periodo = motivo_periodo_no_computable(experiencia, regla)
            if motivo_periodo:
                excluidas.append({"n": n_exp, "motivo": motivo_periodo})
                pendientes.setdefault(n_exp, []).append(motivo_periodo)
            else:
                inicio, fin, _ = fechas_calculo(experiencia, regla)
                periodos.append((inicio, fin))

            datos_exp = enriquecimiento.get(f"{n_prof}:{n_exp}") or {}
            datos_exp = datos_exp if isinstance(datos_exp, dict) else {}
            motivo_identidad = _motivo_identificacion(experiencia, datos_exp)
            if motivo_identidad:
                pendientes.setdefault(n_exp, []).append(motivo_identidad)

        datos = _agregado_limpio(enriquecimiento.get(f"prof:{n_prof}"))
        calculo = dias_efectivos_profesional(periodos, {})
        dias_efectivos = calculo.dias_efectivos
        anios_efectivos = round(anios(dias_efectivos), 2)
        datos.update(
            dias_brutos=calculo.dias_brutos,
            dias_paralizados=0,
            dias_traslape=calculo.dias_traslape,
            dias_efectivos=dias_efectivos,
            anios_efectivos=anios_efectivos,
            experiencias_excluidas=excluidas,
        )

        exigido = _minimo_exigido(profesional.get("requisitos"))
        if exigido:
            minimo_dias, minimo_texto = exigido
            datos.update(
                minimo_dias=minimo_dias,
                minimo_texto=minimo_texto,
                minimo_anios=(minimo_dias // 365 if minimo_dias % 365 == 0
                               else round(minimo_dias / 365, 2)),
            )

        numeros_pendientes = sorted(pendientes, key=lambda n: (n is None, str(n)))
        if numeros_pendientes:
            datos["veredicto_provisional"] = numeros_pendientes
            detalle = "; ".join(
                f"experiencia {n}: {', '.join(dict.fromkeys(pendientes[n]))}"
                for n in numeros_pendientes
            )
            minimo = datos.get("minimo_texto", "sin mínimo consignado")
            datos["cumple_backend"] = (
                f"POR VERIFICAR — {dias_efectivos} días efectivos PROVISIONALES "
                f"({anios_efectivos} años) contra {minimo}: {detalle}. La ausencia "
                "de evidencia no invalida la experiencia; confirmarla antes de concluir."
            )
        elif not periodos:
            datos["cumple_backend"] = (
                "POR VERIFICAR — 0 días efectivos; no hay períodos computables "
                "con los cuales emitir un veredicto."
            )
        elif exigido is None:
            datos["cumple_backend"] = (
                f"POR VERIFICAR — {dias_efectivos} días efectivos ({anios_efectivos} "
                "años); las bases no consignan un mínimo comparable."
            )
        elif dias_efectivos < datos["minimo_dias"]:
            datos["cumple_backend"] = (
                f"NO CUMPLE — {dias_efectivos} días efectivos ({anios_efectivos} años) "
                f"contra un mínimo de {datos['minimo_texto']}"
            )
        else:
            datos["cumple_backend"] = (
                f"CUMPLE — {dias_efectivos} días efectivos ({anios_efectivos} años) "
                f"contra un mínimo de {datos['minimo_texto']}"
            )

        salida[n_prof] = datos
    return salida
