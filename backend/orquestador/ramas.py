"""Entradas estables y fusión de resultados de las fuentes paralelas.

Solo el coordinador publica cambios. Nunca copia un diccionario mientras un
scraper lo modifica ni permite que el orden de llegada decida una discrepancia.
"""
from copy import deepcopy
from dataclasses import replace

from schemas.pipeline import Job
from .etapas import Contexto, ErrorEstructural


_AUSENTE = object()
MARCA_CONFLICTO = "conflicto entre fuentes paralelas"


def aislar_contexto(ctx: Contexto) -> Contexto:
    return replace(ctx, job=ctx.job.model_copy(deep=True),
                   espejo=deepcopy(ctx.espejo),
                   enriquecimiento=deepcopy(ctx.enriquecimiento),
                   solo_items=deepcopy(ctx.solo_items),
                   datos_humano=deepcopy(ctx.datos_humano))


def _copiar(valor):
    return _AUSENTE if valor is _AUSENTE else deepcopy(valor)


def _fusionar(base, nuevo, actual, ruta: str):
    if nuevo == base:
        return _copiar(actual)
    if actual == base or actual == nuevo:
        return _copiar(nuevo)
    # Dos fuentes pueden añadir campos distintos a la MISMA experiencia.
    if (isinstance(nuevo, dict) and isinstance(actual, dict)
            and (base is _AUSENTE or base is None or isinstance(base, dict))):
        anterior = base if isinstance(base, dict) else {}
        salida = deepcopy(actual)
        for clave in anterior.keys() | nuevo.keys():
            valor = _fusionar(anterior.get(clave, _AUSENTE),
                              nuevo.get(clave, _AUSENTE),
                              actual.get(clave, _AUSENTE), f"{ruta}.{clave}")
            if valor is _AUSENTE:
                salida.pop(clave, None)
            else:
                salida[clave] = valor
        return salida
    raise ErrorEstructural(f"{MARCA_CONFLICTO} en {ruta}")


def _fusionar_revisiones(base: list, nuevas: list, actuales: list) -> list:
    # El contrato permite modificar revisiones existentes y añadir otras,
    # nunca borrar/reordenar las anteriores. No se inventa un ID persistente.
    if len(nuevas) < len(base) or len(actuales) < len(base):
        raise ErrorEstructural("una fuente paralela eliminó revisiones previas")
    salida = deepcopy(actuales)
    for indice, anterior in enumerate(base):
        identidad = tuple(anterior[k] for k in ("n_prof", "n_exp", "etapa"))
        if any(tuple(item[k] for k in ("n_prof", "n_exp", "etapa")) != identidad
               for item in (nuevas[indice], actuales[indice])):
            raise ErrorEstructural("una fuente paralela reordenó revisiones previas")
        salida[indice] = _fusionar(anterior, nuevas[indice], actuales[indice],
                                  f"job.items_revision[{indice}]")
    for nueva in nuevas[len(base):]:
        if nueva not in salida[len(base):]:
            salida.append(deepcopy(nueva))
    return salida


def incorporar_rama(ctx: Contexto, base: Contexto, rama: Contexto) -> None:
    """Aplica solo el delta terminado; un conflicto no aplica un delta parcial."""
    enriquecimiento = _fusionar(base.enriquecimiento, rama.enriquecimiento,
                               ctx.enriquecimiento, "enriquecimiento")
    espejo = _fusionar(base.espejo, rama.espejo, ctx.espejo, "espejo")
    previo, nuevo, actual = (x.job.model_dump() for x in (base, rama, ctx))
    revisiones = _fusionar_revisiones(previo.pop("items_revision"),
                                     nuevo.pop("items_revision"),
                                     actual.pop("items_revision"))
    datos_job = _fusionar(previo, nuevo, actual, "job")
    datos_job["items_revision"] = revisiones
    job = Job.model_validate(datos_job)
    ctx.enriquecimiento = enriquecimiento
    ctx.espejo = espejo
    # Conserva el objeto Job que usa el motor; ningún worker tiene esa referencia.
    for campo, valor in job.__dict__.items():
        setattr(ctx.job, campo, valor)
    for campo, valor in (job.model_extra or {}).items():
        setattr(ctx.job, campo, valor)
