"""Conclusiones desde los totales calculados, sin generar archivos ni celdas."""
from entregables.textos import conciliar_conclusion, sin_jerga
from reglas.calculo import anios
from reglas.requisitos import minimo_exigido


def conclusion_expedientes(prof: dict, dias_ef: int, traslape: int,
                            dias_inferidos: int, dias_sin_identificar: int,
                            hay_provisional: bool) -> str:
    """Conclusión del profesional en un concurso de EXPEDIENTES.

    UNA sola fuente de verdad: los días efectivos que acaba de imprimir la
    PARTE 5 — que son los de `reconciliar_resultados_profesionales`. Reglas:

    · Si el backend ya dictó `cumple_backend` (NO CUMPLE o POR VERIFICAR), esa
      línea manda tal cual: ya cita el mismo número.
    · Si no lo dictó, se redacta aquí desde los días efectivos y el mínimo. Un
      «CUMPLE» heredado del evaluador NUNCA sobrevive a unos días efectivos por
      debajo del mínimo (caso real P9: la hoja decía «CUMPLE — 574 días» con un
      mínimo de 24 meses, porque tabla y conclusión contaban cosas distintas).
    · Siempre se dice cuántos de esos días dependen de un CUI inferido o de una
      experiencia sin identificar: es la información que la tabla acaba de
      desglosar y la que decide si el veredicto se puede firmar.
    """
    exigido = minimo_exigido(prof.get("requisitos"))
    minimo_dias, minimo_texto = exigido if exigido else (
        None, prof.get("minimo_exigido_backend"))
    anios_ef = round(anios(dias_ef), 2)
    base = sin_jerga(prof.get("cumple_backend") or "") or None
    bajo_minimo = bool(minimo_dias) and dias_ef < minimo_dias

    if base and (bajo_minimo or not base.strip().upper().startswith("CUMPLE")):
        texto = base
    elif minimo_dias is None:
        texto = (f"POR VERIFICAR — {dias_ef} días efectivos ({anios_ef} años) "
                 f"tras descontar {traslape} días de traslape; las bases no "
                 f"consignan un mínimo con el que compararlos")
    elif bajo_minimo:
        texto = (f"NO CUMPLE — {dias_ef} días efectivos ({anios_ef} años) tras "
                 f"descontar {traslape} días de traslape, contra un mínimo de "
                 f"{minimo_texto} ({minimo_dias} días)")
    else:
        texto = (f"CUMPLE — {dias_ef} días efectivos ({anios_ef} años) tras "
                 f"descontar {traslape} días de traslape, contra un mínimo de "
                 f"{minimo_texto} ({minimo_dias} días)")

    dependientes = []
    if dias_inferidos:
        dependientes.append(f"{dias_inferidos} días corresponden a identificación "
                            f"inferida por nombre")
    if dias_sin_identificar:
        dependientes.append(f"{dias_sin_identificar} días corresponden a expedientes "
                            f"sin identificar")
    texto = texto.rstrip().rstrip(".")     # `cumple_backend` ya trae su punto final
    if dependientes:
        texto += (". Antes de descontar traslapes, " + " y ".join(dependientes)
                  + "; la identificación no acredita por sí sola el tiempo ni el cargo")
    else:
        texto += (". La identificación del expediente no acredita por sí sola el "
                  "tiempo ni el cargo")
    return texto + "."

def conclusion_tiempo_efectivo(prof: dict, dias_declarados: int,
                             periodos: int, conclusion_expediente: str | None = None) -> dict:
    """Conserva texto visible y veredicto original para su presentación."""
    veredicto = prof.get("cumple_backend") or prof.get("cumple") or "POR VERIFICAR — sin conclusión"
    if conclusion_expediente is not None:
        return {"veredicto": conclusion_expediente, "texto": conclusion_expediente}
    visible = sin_jerga(veredicto)
    if not prof.get("cumple_backend"):
        visible = conciliar_conclusion(visible, dias_declarados, periodos)
    return {"veredicto": veredicto, "texto": visible}

