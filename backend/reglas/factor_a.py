"""Factor A sobre los totales profesionales, sin I/O ni generación Excel."""
import re

from validacion.baremo import baremo_factor_a_valido
from validacion.puntajes import reconciliar_puntajes

_RE_LETRA_FACTOR = re.compile(r"^\s*(?:factor\s+)?([A-Za-z])(?=\s*[—–\-:.)]|\s|$)", re.I)


def letra_factor(f: dict) -> str:
    """Letra del factor ('A') venga sola ("A"), con rótulo ("Factor A") o con su
    nombre ("A — Experiencia específica…", formato que emite el consolidador
    desde #88). Un nombre sin letra inicial aislada ("Certificaciones del
    personal clave") devuelve "". Antes se comparaba `== "A"` literal y el
    Factor A de un espejo real nunca se recalculaba: puntaje mudo en Excel y Panel."""
    m = _RE_LETRA_FACTOR.match(str((f or {}).get("factor") or ""))
    return m.group(1).upper() if m else ""


def participantes_factor_a(espejo: dict) -> set[int]:
    """Cargos que participan según las bases; legado: recupera la lista que
    quedó escrita en el detalle del factor, sin confiar en sus resultados."""
    estructurados = {
        p.get("n_prof") for p in espejo.get("profesionales", [])
        if (p.get("requisitos") or {}).get("factor_a_aplica") is True
    }
    if estructurados:
        return estructurados
    factor = next((f for f in (espejo.get("resumen_evaluacion") or {}).get("factores", [])
                   if letra_factor(f) == "A"), None)
    texto = str((factor or {}).get("detalle") or "")
    # Formato histórico real: "Factor A (nº 2 ..., 3 ..., 4 ..., 6 ...)".
    # El paréntesis termina antes de las cifras de años/porcentaje del resultado.
    parentesis = re.search(r"factor\s*a\s*\(([^)]+)\)", texto, flags=re.I)
    if parentesis:
        numeros = {int(x) for x in re.findall(r"\b\d+\b", parentesis.group(1))}
        existentes = {p.get("n_prof") for p in espejo.get("profesionales", [])}
        if numeros & existentes:
            return numeros & existentes
    m = re.search(r"participan[^:]*:\s*([^.;]+)", texto, flags=re.I)
    return {int(x) for x in re.findall(r"\d+", m.group(1))} if m else set()


def recalcular_factor_a(espejo: dict, enriquecimiento: dict) -> None:
    """El Factor A solo existe sobre tiempo efectivo que excede el mínimo.

    Con contrato v1.4 el baremo viaja estructurado. Los casos pendientes generan
    un límite inferior/superior; solo se publica un puntaje único si ambos caen
    en el mismo tramo. En espejos antiguos sin baremo se conserva la abstención.
    """
    resumen = espejo.get("resumen_evaluacion") or {}
    factor = next((f for f in resumen.get("factores", [])
                   if letra_factor(f) == "A"), None)
    if not factor:
        return
    participantes = participantes_factor_a(espejo)
    if not participantes:
        return
    regla = (espejo.get("reglas_evaluacion") or {}).get("factor_a") or {}
    if not baremo_factor_a_valido(regla):
        factor.update(puntaje=None, puntaje_confirmado=None, puntaje_maximo_posible=None,
                      estado_puntaje="condicionado", detalle=(
                          "POR VERIFICAR — umbral o baremo del Factor A ausente, incompleto o incompatible. "
                          "No se puede determinar cuántos cargos califican ni asignar puntaje; revisar las bases."))
        for p in espejo.get("profesionales", []):
            if p.get("n_prof") in participantes:
                p["anios_adicionales"] = "POR VERIFICAR — falta umbral o baremo válido del Factor A"
        reconciliar_puntajes(espejo)
        return
    tramos = regla["tramos"]
    adicional_requerido = regla.get("dias_adicionales_requeridos")
    califican: list[int] = []
    pendientes: list[int] = []
    for p in espejo.get("profesionales", []):
        np_ = p.get("n_prof")
        if np_ not in participantes:
            continue
        d = enriquecimiento.get(f"prof:{np_}") or {}
        minimo, efectivos = d.get("minimo_dias"), d.get("dias_efectivos")
        # La falta de InfoObras es una verificación complementaria y no invalida
        # el contrato/constancia salvo que la regla documental lo marque así.
        documental_pendiente = d.get("factor_a_documental") == "por_verificar"
        if minimo is None or efectivos is None or documental_pendiente:
            pendientes.append(np_)
            p["anios_adicionales"] = "POR VERIFICAR — el tiempo efectivo no es definitivo"
            continue
        exceso = max(0, efectivos - minimo)
        p["anios_adicionales"] = f"{round(exceso / 365, 2)} años efectivos adicionales"
        if exceso >= adicional_requerido:
            califican.append(np_)
    porcentaje_confirmado = (len(califican) * 100 / len(participantes))
    porcentaje_maximo = ((len(califican) + len(pendientes)) * 100 / len(participantes))

    def _en_tramo(pct: float, tramo: dict) -> bool:
        desde, hasta = tramo.get("desde_porcentaje"), tramo.get("hasta_porcentaje")
        if desde is not None:
            if pct < desde or (pct == desde and tramo.get("desde_inclusivo") is False):
                return False
        if hasta is not None:
            if pct > hasta or (pct == hasta and tramo.get("hasta_inclusivo") is not True):
                return False
        return True

    def _puntaje(pct: float):
        for tramo in tramos:
            if isinstance(tramo, dict) and _en_tramo(pct, tramo):
                return tramo.get("puntaje")
        return None

    puntaje_min, puntaje_max = _puntaje(porcentaje_confirmado), _puntaje(porcentaje_maximo)
    factor["puntaje_confirmado"] = puntaje_min
    factor["puntaje_maximo_posible"] = puntaje_max
    if puntaje_min is not None and puntaje_min == puntaje_max:
        factor["puntaje"] = puntaje_min
        factor["estado_puntaje"] = "definitivo"
    else:
        factor["puntaje"] = None
        factor["estado_puntaje"] = "condicionado"
    factor["detalle"] = (
        f"{len(califican)} de {len(participantes)} cargos acreditan al menos "
        f"{adicional_requerido} días "
        f"efectivo adicional (profesionales {', '.join(map(str, califican)) or 'ninguno'}). "
        + (f"Revisión documental pendiente: {', '.join(map(str, pendientes))}. " if pendientes else "")
        + (f"Tramo definitivo: {puntaje_min} puntos."
           if factor["estado_puntaje"] == "definitivo" else
           f"Resultado condicionado entre {puntaje_min if puntaje_min is not None else 'sin dato'} "
           f"y {puntaje_max if puntaje_max is not None else 'sin dato'} puntos.")
    )
    minimos, maximos, condicionado = [], [], False
    for f in resumen.get("factores", []):
        if f.get("aplica") is False or isinstance(f.get("puntaje"), str):
            continue
        p = f.get("puntaje")
        pmin = f.get("puntaje_confirmado", p)
        pmax = f.get("puntaje_maximo_posible", p)
        if isinstance(pmin, (int, float)):
            minimos.append(pmin)
        if isinstance(pmax, (int, float)):
            maximos.append(pmax)
        condicionado = condicionado or f.get("estado_puntaje") == "condicionado" or p is None
    if tramos:
        resumen["puntaje_confirmado"] = sum(minimos)
        resumen["puntaje_maximo_posible"] = sum(maximos)
        resumen["estado_puntaje"] = "condicionado" if condicionado else "definitivo"
        resumen["puntaje_total"] = None if condicionado else sum(minimos)
    resumen["nota"] = (
        "Puntajes y total generados desde los valores finales reconciliados. "
        + ("El total es condicionado mientras existan factores por verificar."
           if resumen.get("estado_puntaje") == "condicionado" else
           "El total es definitivo."))
