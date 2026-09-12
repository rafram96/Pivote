"""La fusión no reemplaza una experiencia completa por el resultado de una fuente."""
from copy import deepcopy

import pytest

from orquestador.etapas import Contexto, ErrorEstructural
from orquestador.ramas import aislar_contexto, incorporar_rama
from schemas.pipeline import Etapa, ItemRevision, Job


def contexto(datos=None):
    return Contexto(Job(job_id="prueba-ramas", analisis_id="sintetico"),
                    espejo={"profesionales": []}, enriquecimiento=deepcopy(datos or {}))


@pytest.mark.parametrize("datos", [{}, {"1:1": {}}, {"1:1": None},
                                  {"1:1": {"cui": "1234567"}}])
@pytest.mark.parametrize("inverso", [False, True])
def test_ambas_fuentes_preservadas_en_cualquier_orden(datos, inverso):
    ctx = contexto(datos)
    base = aislar_contexto(ctx)
    ramas = [aislar_contexto(base), aislar_contexto(base)]
    for rama, campo in zip(ramas, ("sunat", "renipress")):
        enr = rama.enriquecimiento.get("1:1") or {}
        enr[campo] = {"candidatos": [{"nombre": campo}]}
        rama.enriquecimiento["1:1"] = enr
    for rama in reversed(ramas) if inverso else ramas:
        incorporar_rama(ctx, base, rama)
    datos_finales = ctx.enriquecimiento["1:1"]
    assert datos_finales["sunat"] == {"candidatos": [{"nombre": "sunat"}]}
    assert datos_finales["renipress"] == {"candidatos": [{"nombre": "renipress"}]}
    if (datos.get("1:1") or {}).get("cui"):
        assert datos_finales["cui"] == "1234567"
    ramas[0].enriquecimiento["1:1"]["sunat"]["candidatos"].clear()
    assert datos_finales["sunat"]["candidatos"]  # no comparte objetos con el worker
    assert base.enriquecimiento == datos


def test_eliminar_campo_de_una_fuente_no_borra_los_de_la_otra():
    ctx = contexto({"1:1": {"obsoleto": True, "cui": "1234567"}})
    base = aislar_contexto(ctx)
    info, sunat = aislar_contexto(base), aislar_contexto(base)
    del info.enriquecimiento["1:1"]["obsoleto"]
    sunat.enriquecimiento["1:1"]["sunat"] = {"ruc": "20111111111"}
    incorporar_rama(ctx, base, sunat)
    incorporar_rama(ctx, base, info)
    assert ctx.enriquecimiento == {"1:1": {"cui": "1234567", "sunat": {"ruc": "20111111111"}}}


def test_conflicto_no_aplica_ni_otros_campos_del_delta():
    ctx = contexto({"1:1": {"valor": 0}})
    base = aislar_contexto(ctx)
    a, b = aislar_contexto(base), aislar_contexto(base)
    a.enriquecimiento["1:1"]["valor"] = 1
    b.enriquecimiento["1:1"].update(valor=2, dato_nuevo=True)
    b.espejo["campo"] = "no aplicar"
    incorporar_rama(ctx, base, a)
    antes = aislar_contexto(ctx)
    with pytest.raises(ErrorEstructural, match="conflicto entre fuentes"):
        incorporar_rama(ctx, base, b)
    assert ctx == antes


def test_mismo_cambio_en_dos_fuentes_es_idempotente():
    ctx = contexto({"1:1": {"valor": 0}})
    base = aislar_contexto(ctx)
    rama = aislar_contexto(base)
    rama.enriquecimiento["1:1"]["valor"] = 1
    incorporar_rama(ctx, base, rama)
    incorporar_rama(ctx, base, rama)
    assert ctx.enriquecimiento == {"1:1": {"valor": 1}}


def test_revisiones_editadas_y_agregadas_no_se_pisan():
    ctx = contexto()
    ctx.job.items_revision = [ItemRevision(n_prof=1, n_exp=1, etapa=Etapa.RESOLUCION_CUI,
                                          motivo="previa")]
    base = aislar_contexto(ctx)
    info, sunat = aislar_contexto(base), aislar_contexto(base)
    info.job.items_revision[0].resuelto = True
    info.job.items_revision[0].motivo = "fuente identificada"
    for rama, etapa in ((info, Etapa.INFOOBRAS), (sunat, Etapa.SUNAT)):
        rama.job.items_revision.append(ItemRevision(n_prof=1, n_exp=2, etapa=etapa,
                                                    motivo=etapa.value))
    incorporar_rama(ctx, base, sunat)
    incorporar_rama(ctx, base, info)
    assert len(ctx.job.items_revision) == 3
    assert ctx.job.items_revision[0].resuelto
    assert ctx.job.items_revision[0].motivo == "fuente identificada"
    assert {it.etapa for it in ctx.job.items_revision[1:]} == {Etapa.INFOOBRAS, Etapa.SUNAT}


def test_rechaza_borrar_revisiones_sin_aplicar_datos_parciales():
    ctx = contexto()
    ctx.job.items_revision = [ItemRevision(n_prof=1, n_exp=1, etapa=Etapa.RESOLUCION_CUI,
                                          motivo="previa")]
    base = aislar_contexto(ctx)
    rama = aislar_contexto(base)
    rama.job.items_revision.clear()
    rama.enriquecimiento["1:1"] = {"nuevo": True}
    with pytest.raises(ErrorEstructural, match="eliminó revisiones"):
        incorporar_rama(ctx, base, rama)
    assert ctx == base
