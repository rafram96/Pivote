"""Mínimo de experiencia de las bases, independiente de la orquestación."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re
from typing import Optional

# El mínimo exigido se escribe en AÑOS, MESES o DÍAS según las bases; el regex
# anterior solo entendía "años" y por eso `cumple_backend` casi nunca se calculaba:
# en el concurso de Lircay (CP-02-2025) los 17 cargos dicen "Experiencia mínima:
# 24/36 meses" → 0 de 17 mínimos captados, y los 5 falsos CUMPLE del análisis
# quedaron sin contraveredicto (#51).
#
# `m[ií]nim[ao]` cubre "mínimo de 3 años" y "Experiencia mínima: 24 meses"; el
# hueco intermedio es corto y no-codicioso para no saltar a otra cifra de la frase.
_UNIDAD_TIEMPO_RE = r"a[ñn]os?|meses|mes|d[ií]as?"
_RE_MINIMO = re.compile(
    rf"m[ií]nim[ao][^0-9]{{0,20}}?(\d+(?:[.,]\d+)?)\s*\)?\s*({_UNIDAD_TIEMPO_RE})",
    re.I,
)
_RE_EQUIVALENCIA_TIEMPO = re.compile(
    rf"\(\s*(\d+(?:[.,]\d+)?)\s*({_UNIDAD_TIEMPO_RE})\s*\)",
    re.I,
)

# Conversión a días: la MISMA convención que `reglas.anios` (365) y `reglas.meses`
# (30). Usar otra haría que el umbral contradiga la cifra que se muestra al lado.
_DIAS_POR_UNIDAD = {"a": 365, "m": 30, "d": 1}


def minimo_exigido(requisitos) -> Optional[tuple[int, str]]:
    """Mínimo de las bases normalizado a `(días, texto_literal)`.

    Se compara en DÍAS y no en años porque es la unidad que el Paso 5 calcula sin
    pérdida: convertir los efectivos a años y redondear puede volcar un caso de
    borde (2.996 años redondea a 3.0 y un mínimo de "3 años" pasaría a cumplir)."""
    requisitos = requisitos or {}
    estructurado = requisitos.get("minimo_experiencia")
    cantidad = unidad = None
    if isinstance(estructurado, dict):
        valor = estructurado.get("cantidad")
        unidad_declarada = estructurado.get("unidad")
        unidad = {"anios": "años", "meses": "meses", "dias": "días"}.get(
            unidad_declarada) if isinstance(unidad_declarada, str) else None
        if not isinstance(valor, bool) and isinstance(valor, (str, int, float)):
            try:
                cantidad = Decimal(str(valor).replace(",", "."))
            except InvalidOperation:
                pass
        if cantidad is not None and (not cantidad.is_finite() or cantidad <= 0):
            cantidad = None
    if cantidad is not None and unidad:
        # Conserva equivalencias literales como 0.5 años (6 meses), solo cuando
        # la cifra principal coincide con el mínimo estructurado de las bases.
        texto = "Experiencia mínima: " + str(estructurado.get("texto") or "")
        m = _RE_MINIMO.search(texto)
        if m and Decimal(m.group(1).replace(",", ".")) == cantidad \
                and m.group(2).lower()[0] == unidad[0]:
            equivalencia = _RE_EQUIVALENCIA_TIEMPO.search(texto[m.end():m.end() + 80])
            if equivalencia:
                cantidad = Decimal(equivalencia.group(1).replace(",", "."))
                unidad = equivalencia.group(2)
        if cantidad <= 0:
            return None
        dias = int((cantidad * _DIAS_POR_UNIDAD[unidad.lower()[0]]).to_integral_value(
            rounding=ROUND_CEILING))
        return dias, f"{cantidad:g} {unidad}"

    for v in requisitos.values():
        if not isinstance(v, str):
            continue  # no interpretar cifras de objetos/fuentes serializados
        texto = str(v)
        m = _RE_MINIMO.search(texto)
        if not m:
            continue

        # Si las bases escriben la equivalencia de manera literal —p. ej.
        # «0.5 años (6 meses)»— esa unidad explícita gana. Evita convertir seis
        # meses en 182.5 días y respeta la convención mensual del mismo documento.
        equivalencia = _RE_EQUIVALENCIA_TIEMPO.search(texto[m.end():m.end() + 80])
        elegido = equivalencia or m
        numero_literal, unidad_literal = elegido.group(1), elegido.group(2)
        try:
            numero = Decimal(numero_literal.replace(",", "."))
        except InvalidOperation:
            continue
        if numero <= 0:
            continue

        unidad = unidad_literal.lower()[0]
        dias = int((numero * _DIAS_POR_UNIDAD[unidad]).to_integral_value(
            rounding=ROUND_CEILING))
        return dias, f"{numero_literal} {unidad_literal}"
    return None
