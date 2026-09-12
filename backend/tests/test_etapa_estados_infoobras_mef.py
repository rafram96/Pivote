"""El estado de la fuente acompaña a P/E sin convertirse en identidad."""
from copy import deepcopy

import pytest

from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal
from schemas.pipeline import Job


def _contexto(tipo="expedientes"):
    return Contexto(
        Job(job_id="estados-locales", analisis_id="prueba-local"),
        {"_meta": {"tipo_evaluacion": tipo}, "profesionales": [{
            "n_prof": 1, "experiencias": [{"n": 1, "proyecto": "Proyecto de prueba",
                "cargo_ocupado": "Especialista", "entidad_emisora": "Consultora de prueba"}]}]},
        enriquecimiento={"1:1": {"cui": "2000001", "via": "MEF" if tipo == "expedientes" else "CUI_TEXTO"}},
    )


@pytest.mark.parametrize("estado", ["fuente_no_disponible", "sin_resultados", "respuesta_no_reconocida"])
def test_mef_sin_ficha_infoobras_conserva_causa_y_no_afirma_inexistencia(estado):
    consultas = {k: {"estado": estado, "motivo": "Respuesta simulada"}
                 for k in ("mef_ficha", "mef_contratos")}
    ctx = _contexto()
    entrada = deepcopy(ctx.espejo)
    EtapaInfoObrasReal(fetcher=lambda *a: None,
        verificador_mef=lambda *a: {"verificado_en_mef": False, "consultas_fuentes": consultas},
        consulta_ocds=lambda cui: []).correr(ctx)
    enr = ctx.enriquecimiento["1:1"]
    assert enr["consultas_fuentes"]["mef_ficha"]["estado"] == estado
    assert enr["verificacion_expediente"]["consultas_fuentes"] == consultas
    assert enr["via"] == "MEF" and enr["cui"] == "2000001"
    assert ctx.espejo == entrada
    assert not any("no publica" in o.mensaje for o in ctx.job.observaciones)
    enr["consultas_fuentes"]["mef_ficha"]["estado"] = "prueba"
    assert consultas["mef_ficha"]["estado"] == estado


def test_mef_excepcion_no_se_pierde_como_sin_contratos():
    def falla(*a):
        raise ConnectionError("fallo simulado")
    ctx = _contexto()
    EtapaInfoObrasReal(fetcher=lambda *a: None, verificador_mef=falla,
                      consulta_ocds=lambda cui: []).correr(ctx)
    assert ctx.enriquecimiento["1:1"]["consultas_fuentes"]["mef_contratos"]["estado"] == "fuente_no_disponible"


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_infoobras_legacy_none_no_se_convierte_en_consulta_vacia(tipo):
    ctx = _contexto(tipo)
    EtapaInfoObrasReal(fetcher=lambda cui: None,
                      consulta_ocds=lambda cui: []).correr(ctx)
    assert ctx.enriquecimiento["1:1"]["consultas_fuentes"]["infoobras_busqueda"]["estado"] == "no_registrado"


def test_typeerror_del_fetcher_no_dispara_otra_firma_dentro_del_intento():
    ctx = _contexto("obras")
    llamadas = []
    def falla(*args):
        llamadas.append(args)
        raise TypeError("fallo interno, no firma")
    EtapaInfoObrasReal(fetcher=falla, consulta_ocds=lambda cui: []).correr(ctx)
    assert len(llamadas) == 2  # dos pasadas normales, no cuatro llamadas
    assert all(len(a) == 4 for a in llamadas)


def test_diagnostico_se_actualiza_en_reintento_sin_fase_vieja():
    ctx = _contexto("obras")
    llamadas = []
    def fetch(cui, *args, diagnostico):
        llamadas.append(cui)
        diagnostico["infoobras_busqueda"] = {"estado": "sin_resultados"}
        if len(llamadas) == 1:
            diagnostico["infoobras_preparacion"] = {"estado": "fuente_no_disponible"}
        return None
    EtapaInfoObrasReal(fetcher=fetch, consulta_ocds=lambda cui: []).correr(ctx)
    fuentes = ctx.enriquecimiento["1:1"]["consultas_fuentes"]
    assert fuentes["infoobras_busqueda"]["estado"] == "sin_resultados"
    assert "infoobras_preparacion" not in fuentes
