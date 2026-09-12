"""Un fallo del selector conserva candidatos, nunca inventa una selección."""
from copy import deepcopy
import json

import pytest

from observabilidad.traza import Traza, restaurar, usar
from resolucion.cui import _elegir_obra, resolver, resolver_con_dedup, resolver_obras


REGISTROS = [
    {"codigoObra": 101, "codUniqInv": "2000001",
     "nombrObra": "MEJORAMIENTO DEL HOSPITAL DE PRUEBA", "nombrDepartamento": "LIMA"},
    {"codigoObra": 102, "codUniqInv": "2000001",
     "nombrObra": "MEJORAMIENTO DEL HOSPITAL DE PRUEBA", "nombrDepartamento": "LIMA"},
]
EXPERIENCIA = {"n": 1, "cui": "2000001", "proyecto": "Mejoramiento del Hospital de Prueba",
               "folio": "100", "entidad_emisora": "Consorcio de Prueba"}


class ConsultaLocal:
    def __init__(self, registros=None):
        self.registros = deepcopy(REGISTROS if registros is None else registros)
        self.llamadas = 0

    def por_codigo(self, codigo):
        self.llamadas += 1
        return deepcopy(self.registros)

    def buscar(self, nombre):
        raise AssertionError("El fallo de selección no habilita otra vía silenciosa")


def _fallar(*args):
    raise ValueError("estructura inesperada del registro")


@pytest.mark.parametrize("salida", [None, {}, "registro inválido", {"codigoObra": 999}])
def test_selector_sin_resultado_valido_no_elige_primero(monkeypatch, salida):
    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", lambda *args: salida)
    r = resolver(deepcopy(EXPERIENCIA), ConsultaLocal())
    assert r["estado"] == "revision"
    assert r["cui"] is None and r["obra"] is None
    assert r["seleccion_obra_pendiente"] is True
    assert {c["obra_id"] for c in r["candidatos"]} == {101, 102}
    assert all(c["score"] == 0 and c["sin_puntuar"] for c in r["candidatos"])
    assert "seleccionar" in r["decision"]
    assert "no respondió" not in r["decision"]


def test_excepcion_se_registra_y_no_modifica_entrada(monkeypatch, caplog, tmp_path):
    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", _fallar)
    exp = deepcopy(EXPERIENCIA)
    consulta = ConsultaLocal()
    ruta = tmp_path / "traza.jsonl"
    token = usar(Traza(ruta))
    try:
        r = resolver(exp, consulta)
    finally:
        restaurar(token)
    assert r["estado"] == "revision" and r["cui"] is None
    assert exp == EXPERIENCIA and consulta.registros == REGISTROS
    assert "ValueError" in caplog.text
    eventos = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    assert any(e["ev"] == "seleccion_obra_fallida" for e in eventos)


def test_lista_vacia_no_lanza_ni_invoca_selector(monkeypatch):
    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", _fallar)
    assert _elegir_obra([]) is None


def test_seleccion_valida_conserva_la_ficha_elegida(monkeypatch):
    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", lambda obras, *args: obras[1])
    r = resolver(deepcopy(EXPERIENCIA), ConsultaLocal())
    assert r["estado"] == "resuelto" and r["cui"] == "2000001"
    assert r["obra"]["obra_id"] == 102


def test_fallo_en_subobra_deja_revision_y_reutiliza_la_consulta(monkeypatch):
    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", _fallar)
    consulta = ConsultaLocal()
    resultados = resolver_obras([deepcopy(EXPERIENCIA), deepcopy(EXPERIENCIA)], consulta)
    assert consulta.llamadas == 1
    for r in resultados:
        assert r["estado"] == "revision" and r["cui"] is None and r["obra"] is None
        assert {c["obra_id"] for c in r["candidatos"]} == {101, 102}
        assert r["seleccion_obra_pendiente"] is True


def test_dedup_no_oculta_el_fallo_de_seleccion(monkeypatch):
    llamadas = []

    def seleccionar(obras, *args):
        llamadas.append(1)
        if len(llamadas) == 2:
            return _fallar()
        return obras[0]

    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", seleccionar)
    resultados = dict(resolver_con_dedup(
        [(deepcopy(EXPERIENCIA), "primera"), (deepcopy(EXPERIENCIA), "segunda")], ConsultaLocal()))
    assert resultados["primera"]["estado"] == "resuelto"
    assert resultados["segunda"]["estado"] == "revision"
    assert resultados["segunda"]["seleccion_obra_pendiente"] is True
    assert len(resultados["segunda"]["candidatos"]) == 2


def test_sin_registros_no_se_confunde_con_fallo_de_seleccion():
    [r] = resolver_obras([deepcopy(EXPERIENCIA)], ConsultaLocal([]))
    assert r["estado"] == "no_encontrado"
    assert not r.get("seleccion_obra_pendiente")


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_etapa_persiste_el_fallo_y_el_motivo_para_los_entregables(monkeypatch, tipo):
    from orquestador.etapas import Contexto
    from orquestador.etapas_reales import EtapaResolucionCuiReal
    from schemas.pipeline import EstadoEtapa, Job

    monkeypatch.setattr("scraping.infoobras.seleccionar_obra", _fallar)
    monkeypatch.setattr("resolucion.base_mef.instancia", lambda: None)
    espejo = {"_meta": {"tipo_evaluacion": tipo}, "profesionales": [
        {"n_prof": 1, "experiencias": [deepcopy(EXPERIENCIA)]}]}
    ctx = Contexto(job=Job(job_id="prueba-selector", analisis_id="prueba-selector"),
                   espejo=espejo, enriquecimiento={})
    resultado = EtapaResolucionCuiReal(consulta=ConsultaLocal()).correr(ctx)
    assert resultado.estado == EstadoEtapa.OK_CON_REVISION
    enr = ctx.enriquecimiento["1:1"]
    assert enr["cui"] is None and enr["sin_verificar"] is True
    assert enr["seleccion_obra_pendiente"] is True
    assert {c["obra_id"] for c in enr["candidatos"]} == {101, 102}
    [revision] = ctx.job.items_revision
    assert revision.motivo == enr["decision"]
    assert revision.candidatos == enr["candidatos"]
