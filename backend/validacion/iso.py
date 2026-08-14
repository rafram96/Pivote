"""Compuerta determinística de certificados ISO (#92).

Usa únicamente hechos ya extraídos de la propuesta y la fecha oficial de las
bases. No consulta SUNEDU, MINEDU, INACAL ni ningún otro registro o portal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
import unicodedata


_RE_ISO = re.compile(r"(?:ISO|NTP\s*[-–]?\s*ISO)\s*[-:]?\s*(9001|14001|37001)", re.I)
_SUFIJOS = {"SAC", "SRL", "EIRL", "SA", "SAA"}
_SUFIJOS_SEPARADOS = (("E", "I", "R", "L"), ("S", "A", "A"),
                      ("S", "A", "C"), ("S", "R", "L"), ("S", "A"))


@dataclass(frozen=True)
class HallazgoISO:
    norma: str
    estado: str
    mensaje: str


def _fecha(v) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v.strip()) == 10:
        try:
            return date.fromisoformat(v.strip())
        except ValueError:
            return None
    return None


def _nombre(v) -> str:
    texto = "".join(c for c in unicodedata.normalize("NFD", str(v or "").upper())
                    if not unicodedata.combining(c))
    partes = re.findall(r"[A-Z0-9]+", texto)
    for sufijo in _SUFIJOS_SEPARADOS:
        if tuple(partes[-len(sufijo):]) == sufijo:
            del partes[-len(sufijo):]
            break
    while partes and partes[-1] in _SUFIJOS:
        partes.pop()
    return " ".join(partes)


def _coincide_titular(esperado: str, titular: str) -> bool:
    a, b = _nombre(esperado), _nombre(titular)
    return bool(a and b and (a == b or (len(a) >= 8 and a in b) or (len(b) >= 8 and b in a)))


def _norma(texto) -> str | None:
    m = _RE_ISO.search(str(texto or ""))
    return m.group(1) if m else None


def aplicar_reglas_iso(espejo: dict) -> list[HallazgoISO]:
    """Marca vigencia y vuelve condicional cualquier puntaje ISO no probado."""
    postor = espejo.setdefault("postor", {})
    certificados = postor.get("isos_certificaciones") or []
    reglas = espejo.get("reglas_evaluacion") or {}
    fecha_oferta = _fecha(reglas.get("fecha_presentacion_oferta"))

    for cert in certificados:
        emision = _fecha(cert.get("fecha_emision"))
        vencimiento = _fecha(cert.get("fecha_vencimiento"))
        if not fecha_oferta or not vencimiento:
            estado = "por_verificar"
        elif emision and emision > fecha_oferta:
            estado = "por_verificar"
        elif vencimiento < fecha_oferta:
            estado = "vencido"
        else:
            estado = "vigente"
        cert["estado_vigencia"] = estado

    consorciados = postor.get("consorciados") or []
    titulares_requeridos = [
        str(c.get("nombre") or c.get("razon_social") or "").strip()
        for c in consorciados if isinstance(c, dict)
    ]
    titulares_requeridos = [x for x in titulares_requeridos if x]
    if not titulares_requeridos:
        nombre_postor = ((espejo.get("_meta") or {}).get("postor")
                         or postor.get("nombre") or postor.get("postor"))
        if nombre_postor:
            titulares_requeridos = [str(nombre_postor)]

    hallazgos: list[HallazgoISO] = []
    factores = (espejo.setdefault("resumen_evaluacion", {}).get("factores") or [])
    for factor in factores:
        norma = _norma(" ".join(str(factor.get(k) or "")
                                for k in ("factor", "criterio", "detalle")))
        if not norma:
            continue
        candidatos = [c for c in certificados
                      if c.get("presente") is not False and _norma(c.get("norma")) == norma]
        faltantes = []
        no_vigentes = []
        incompletos = []
        if not fecha_oferta:
            incompletos.append("falta la fecha oficial de presentación")
        if not titulares_requeridos:
            incompletos.append("no se identificó al titular requerido")
        for titular in titulares_requeridos:
            propios = [c for c in candidatos if _coincide_titular(titular, c.get("titular"))]
            if not propios:
                faltantes.append(titular)
            elif not any(c.get("estado_vigencia") == "vigente" for c in propios):
                if any(c.get("estado_vigencia") == "vencido" for c in propios):
                    no_vigentes.append(titular)
                else:
                    incompletos.append(f"vigencia de {titular}")

        probado = bool(titulares_requeridos and fecha_oferta
                       and not faltantes and not no_vigentes and not incompletos)
        if probado:
            puntaje = factor.get("puntaje")
            factor["estado_puntaje"] = "definitivo" if isinstance(puntaje, (int, float)) else "condicionado"
            if isinstance(puntaje, (int, float)):
                factor["puntaje_confirmado"] = puntaje
                factor["puntaje_maximo_posible"] = puntaje
            mensaje = (f"ISO {norma}: vigencia y titularidad acreditadas documentalmente "
                       f"para {len(titulares_requeridos)} titular(es) a la fecha oficial.")
            estado = "DEFINITIVO"
        else:
            anterior = factor.get("puntaje")
            maximo = (factor.get("puntaje_maximo_posible")
                      if isinstance(factor.get("puntaje_maximo_posible"), (int, float))
                      else anterior if isinstance(anterior, (int, float)) else None)
            factor["puntaje"] = None
            factor["estado_puntaje"] = "condicionado"
            factor["puntaje_confirmado"] = 0
            factor["puntaje_maximo_posible"] = maximo
            razones = []
            if faltantes:
                razones.append("sin certificado confirmado para " + ", ".join(faltantes))
            if no_vigentes:
                razones.append("certificado vencido para " + ", ".join(no_vigentes))
            razones.extend(incompletos)
            mensaje = (f"ISO {norma}: POR VERIFICAR — "
                       + "; ".join(razones or ["evidencia documental insuficiente"]) + ".")
            estado = "CONDICIONADO"
        factor["detalle"] = mensaje
        hallazgos.append(HallazgoISO(norma, estado, mensaje))
    return hallazgos
