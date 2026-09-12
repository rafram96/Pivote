"""Textos de presentación sin dependencias del generador de hojas."""
import re


def sin_jerga(v):
    """Las celdas las lee el EVALUADOR, no un programador (#55). Todo texto
    visible pasa por aquí: nombres de agentes internos, marcadores del
    consolidador (⟦crudo:…⟧), campos del schema y 'null' se reescriben a
    lenguaje de evaluador. Medido en urgente1 (job e7c0fff6afb1): 34 celdas
    llegaban con jerga. No-op en valores no-texto (números, None)."""
    if not isinstance(v, str):
        return v
    out = re.sub(r"\bbackend\s*/\s*comit[eé]\b", "Comité", v, flags=re.I)
    # "(backend/evaluador)" es UNA sola instrucción («que lo mire quien evalúa»),
    # no dos actores: la regla genérica de abajo lo dejaría en
    # "equipo evaluador/evaluador".
    out = re.sub(r"\bbackend\s*/\s*evaluador(?:es)?\b", "equipo evaluador", out,
                 flags=re.I)
    out = re.sub(r"\bEl\s+backend\b", "El equipo evaluador", out)
    out = re.sub(r"\bel\s+backend\b", "el equipo evaluador", out)
    out = re.sub(r"\bbackend\b", "equipo evaluador", out, flags=re.I)
    # marcador del consolidador: la nota cruda del agente se vuelve una Nota legible
    # El consolidador histórico emitió ambas marcas. Aceptar las dos evita dejar
    # `⟦Claude:` colgando al retirar únicamente el corchete de cierre.
    out = re.sub(r"⟦\s*(?:crudo|Claude)\s*:\s*", "· Nota literal: ", out,
                 flags=re.I).replace("⟧", "")
    # nombres de agentes internos → quién es para el evaluador
    out = re.sub(r"\bagent-propuesta-mapa\b", "la lectura de la propuesta", out)
    out = re.sub(r"\bagent-propuesta-profesional\b", "la lectura del profesional", out)
    out = re.sub(r"\bagent-bases\b", "la lectura de las bases", out)
    out = re.sub(r"\bagent-evaluador\b", "la evaluación automática", out)
    out = re.sub(r"\bagent-[a-z-]+\b", "el sistema", out)
    # campos del schema / valores de programador
    out = re.sub(r"\bfunciones_similares\s*=\s*null\b",
                 "funciones: no constan en el certificado", out, flags=re.I)
    out = re.sub(r"\bfunciones_similares\b", "funciones", out)
    out = re.sub(r"\bn_prof\s*=\s*(\d+)\b", r"profesional \1", out)
    out = re.sub(r"\broster_bundles\.json\b", "el mapa de la propuesta", out)
    # «espejo» es el nombre interno del JSON que viaja al servidor; para quien
    # evalúa, eso es «el análisis».
    out = re.sub(r"\bJSON\s+espejo\b", "el análisis", out, flags=re.I)
    out = re.sub(r"\bespejos?\b", "análisis", out, flags=re.I)
    out = re.sub(r"\bcargos_similares_validos\b", "cargos similares admitidos", out)
    out = re.sub(r"\baplica\s*:\s*false\b", "no aplica", out, flags=re.I)
    out = re.sub(r"\bsubagente(?:s)?\b", "revisión documental", out, flags=re.I)
    out = re.sub(r"\bOCR\b", "lectura del documento", out)
    out = re.sub(r"\bstint\b", "periodo", out, flags=re.I)
    out = re.sub(r"Deber[aá]\s+acercarse\s+a\s+los\s+Centros\s+de\s+Servicios.*$",
                 "", out, flags=re.I)
    out = re.sub(r"^\s*-{2,}\s*", "", out)
    out = re.sub(r"\bCHACARILLLA\b", "CHACARILLA", out, flags=re.I)
    out = re.sub(r"\bnull\b", "sin dato", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def conciliar_conclusion(texto, dias_verificados, periodos: int = 0) -> str:
    """Conclusión visible desde el total inclusivo, nunca desde prosa aritmética."""
    if not isinstance(texto, str) or not isinstance(dias_verificados, int) \
            or isinstance(dias_verificados, bool) or periodos <= 0:
        return texto if isinstance(texto, str) else ("" if texto is None else str(texto))
    normal = texto.strip().upper()
    if normal.startswith("NO CUMPLE"):
        estado = "NO CUMPLE"
    elif normal.startswith(("POR VERIFICAR", "POR CONFIRMAR")):
        estado = "POR VERIFICAR"
    elif normal.startswith(("CUMPLE", "SÍ CUMPLE", "SI CUMPLE")):
        estado = "CUMPLE"
    else:
        estado = "POR VERIFICAR"
    # Es el veredicto de la EVALUACIÓN INICIAL sobre los días declarados; el tiempo
    # efectivo verificado (paralizaciones, traslapes, ventana) va en la línea
    # siguiente. Antes decía «total declarado recalculado», que se leía como si
    # fuera el efectivo (revisión del 5-sep-2026, 12 hojas).
    return (f"{estado} según la evaluación inicial — {dias_verificados} días "
            f"declarados ({round(dias_verificados / 365, 2)} años) en "
            f"{periodos} periodo{'s' if periodos != 1 else ''} computable"
            f"{'s' if periodos != 1 else ''}; el tiempo efectivo verificado va en la "
            "línea siguiente.")

