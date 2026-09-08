"""Guardas puras del baremo recibido; no deducen reglas desde texto."""
from math import isfinite


def baremo_factor_a_valido(regla: dict) -> bool:
    """Un puntaje necesita umbral conocido y un único tramo para cada 0..100.

    En espejos anteriores se admiten los defaults documentados de inclusividad
    (inicio inclusivo, fin exclusivo). Ambos límites nulos nunca representan
    un tramo universal: son la huella de una extracción sin estructurar.
    """
    dias = regla.get("dias_adicionales_requeridos")
    if type(dias) is not int or dias < 0:
        return False
    tramos = regla.get("tramos")
    if not isinstance(tramos, list) or not tramos:
        return False

    def numero(v):
        return type(v) in (int, float) and isfinite(v)

    limites = {0, 100}
    for t in tramos:
        if not isinstance(t, dict):
            return False
        desde, hasta = t.get("desde_porcentaje"), t.get("hasta_porcentaje")
        if desde is None and hasta is None:
            return False
        if any(v is not None and (not numero(v) or not 0 <= v <= 100)
               for v in (desde, hasta)):
            return False
        if desde is not None and hasta is not None and desde > hasta:
            return False
        if not numero(t.get("puntaje")) or t["puntaje"] < 0:
            return False
        if any(k in t and type(t[k]) is not bool
               for k in ("desde_inclusivo", "hasta_inclusivo")):
            return False
        limites.update(v for v in (desde, hasta) if v is not None)

    def contiene(t, x):
        desde, hasta = t.get("desde_porcentaje"), t.get("hasta_porcentaje")
        return ((desde is None or x > desde or x == desde and t.get("desde_inclusivo", True))
                and (hasta is None or x < hasta or x == hasta and t.get("hasta_inclusivo", False)))

    bordes = sorted(limites)
    sondas = bordes + [(a + b) / 2 for a, b in zip(bordes, bordes[1:])]
    return all(sum(contiene(t, x) for t in tramos) == 1 for x in sondas)
