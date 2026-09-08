"""Cálculo monetario determinístico de experiencia del postor (#97)."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from reglas import fecha_cutoff
from .recalculo import fecha_para_calculo

DOS = Decimal("0.01")


def _decimal(v) -> Decimal | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        return Decimal(str(v).replace(",", "")).quantize(DOS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _texto(v: Decimal | None) -> str | None:
    return format(v, ".2f") if v is not None else None


def _clave(v) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(v or "").upper())


def _es_si(v) -> bool:
    return isinstance(v, str) and v.strip().upper().startswith(("SI", "SÍ", "CUMPLE"))


def recalcular_experiencia_postor(espejo: dict) -> dict:
    """Recalcula mínimo confirmado y máximo posible, mutando el espejo.

    Un monto prorrateado por el LLM no se confirma sin evidencia documental de
    desglose. Contrato+ítem es la unidad de deduplicación; dos ítems distintos
    del mismo contrato se conservan.
    """
    postor = espejo.get("postor") or {}
    filas = postor.get("experiencia_postor") or []
    confirmados = Decimal("0")
    maximo = Decimal("0")
    vistos: set[tuple[str, str]] = set()
    reglas = espejo.get("reglas_evaluacion") or {}
    fecha_presentacion, _ = fecha_para_calculo(
        reglas.get("fecha_presentacion_oferta"), extremo="inicio", regla="no_definida")
    antiguedad = reglas.get("antiguedad_maxima_anios")
    cutoff = (fecha_cutoff(fecha_presentacion, int(antiguedad))
              if fecha_presentacion and isinstance(antiguedad, int) else None)
    regla_mes = reglas.get("periodos_sin_dia") or "no_definida"

    for fila in filas:
        fecha_inicio, deducida = fecha_para_calculo(
            fila.get("fecha_inicio"), extremo="inicio", regla=regla_mes)
        if cutoff is None:
            fila["dentro_periodo_admitido"] = (
                "POR VERIFICAR — falta fecha oficial o antigüedad máxima en las bases")
        elif fecha_inicio is None:
            fila["dentro_periodo_admitido"] = "POR VERIFICAR — fecha de inicio no determinada"
        else:
            fila["dentro_periodo_admitido"] = (
                "SÍ" if fecha_inicio >= cutoff else "NO")
            if deducida:
                fila["dentro_periodo_admitido"] += " — fecha deducida por regla de mes completo"
        contrato = fila.get("contrato_id") or fila.get("contrato")
        item = fila.get("item_id")
        clave = (_clave(contrato), _clave(item))
        if clave[0] and clave in vistos:
            fila["estado_monto"] = "excluido"
            fila["monto_aplicable"] = "0.00"
            fila["observaciones"] = "Duplicado real del mismo contrato e ítem; se cuenta una sola vez."
            continue
        if clave[0]:
            vistos.add(clave)

        contrato_monto = (_decimal(fila.get("monto_contrato"))
                          or _decimal(fila.get("monto")))
        item_monto = _decimal(fila.get("monto_item"))
        aplicable_declarado = _decimal(fila.get("monto_aplicable"))
        evidencia = bool(str(fila.get("evidencia_desglose") or "").strip())
        componentes = [str(x).strip() for x in (fila.get("componentes") or []) if str(x).strip()]
        mixto = len(componentes) > 1

        base_confirmada: Decimal | None = None
        base_maxima = item_monto or contrato_monto or aplicable_declarado or Decimal("0")
        if fila.get("estado_monto") == "excluido":
            base_maxima = Decimal("0")
        elif item_monto is not None:
            base_confirmada = item_monto
        elif aplicable_declarado is not None and evidencia:
            base_confirmada = aplicable_declarado
        elif not mixto and _es_si(fila.get("tipo_solicitado")) and contrato_monto is not None:
            base_confirmada = contrato_monto

        participacion = _decimal(fila.get("participacion_porcentaje"))
        if participacion is not None:
            proporcion = participacion / Decimal("100")
            base_maxima *= proporcion
            if base_confirmada is not None:
                base_confirmada *= proporcion

        base_maxima = base_maxima.quantize(DOS, rounding=ROUND_HALF_UP)
        if base_confirmada is not None:
            base_confirmada = base_confirmada.quantize(DOS, rounding=ROUND_HALF_UP)
            confirmados += base_confirmada
            fila["estado_monto"] = "confirmado"
            fila["monto_aplicable"] = _texto(base_confirmada)
        else:
            fila["estado_monto"] = "por_verificar"
            fila["monto_aplicable"] = None
        maximo += max(base_maxima, base_confirmada or Decimal("0"))

    total = postor.setdefault("experiencia_postor_total", {})
    total["monto_confirmado"] = _texto(confirmados)
    total["monto_maximo_posible"] = _texto(maximo)
    total["estado"] = "definitivo" if confirmados == maximo else "condicionado"

    requerido = None
    for campo in ("monto_requerido", "requerido", "minimo", "monto_minimo"):
        requerido = _decimal(total.get(campo))
        if requerido is not None:
            break
    estado_requisito = total.get("requisito_estado")
    fuente = total.get("requisito_fuente") or {}
    if (estado_requisito == "no_aplica" and requerido is None
            and fuente.get("pagina_pdf") and fuente.get("texto")):
        postor["postor_cumple"] = "NO APLICA — mínimo de experiencia no exigido según la fuente registrada en las bases."
    elif (requerido is None or not requerido.is_finite() or requerido < 0
          or estado_requisito not in (None, "encontrado")
          or total.get("requisito_moneda") not in (None, "PEN")):
        postor["postor_cumple"] = (
            "POR VERIFICAR — falta un mínimo de experiencia del postor utilizable de las bases "
            "(monto, moneda o condición aplicable); la suma acreditada no lo sustituye.")
    else:
        if confirmados >= requerido:
            postor["postor_cumple"] = (
                f"CUMPLE — monto confirmado S/ {_texto(confirmados)} alcanza el mínimo S/ {_texto(requerido)}.")
        elif maximo < requerido:
            postor["postor_cumple"] = (
                f"NO CUMPLE — incluso el máximo posible S/ {_texto(maximo)} no alcanza S/ {_texto(requerido)}.")
        else:
            postor["postor_cumple"] = (
                f"POR VERIFICAR — confirmado S/ {_texto(confirmados)}; máximo posible S/ {_texto(maximo)} "
                f"frente al mínimo S/ {_texto(requerido)}.")
    return total
