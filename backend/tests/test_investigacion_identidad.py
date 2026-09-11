from copy import deepcopy
from types import SimpleNamespace

import pytest

from entregables.investigacion_identidad import preparar_contexto


def espejo(obras=None):
    return {"postor": {"secreto": "no exportar"}, "profesionales": [
        {"n_prof": 1, "nombre": "no exportar", "experiencias": [
            {"n": 1, "cui": None, "proyecto": "Proyecto", "fecha_inicial": "2020-01-01",
             "obras": obras or []}]}]}


def test_contexto_inmutable_compacto_y_huella_estable():
    e = espejo()
    enr = {"1:1": {"cui": "1234567", "via": "NOMBRE", "obra": {"obra_id": 42},
                    "obra_ficha": {"obra_id": 42, "valorizaciones": ["muchos datos"]}}}
    antes = deepcopy((e, enr))
    p = preparar_contexto("abcdef123456", e, enr, "obras")
    assert (e, enr) == antes
    assert p["casos"][0]["accion"] == "comprobar_fichas"
    assert "valorizaciones" not in str(p)
    assert "no exportar" not in str(p)
    enr["1:1"]["tiempos_s"] = {"total": 40}
    assert preparar_contexto("abcdef123456", e, enr, "obras")["huella_contexto"] == p["huella_contexto"]
    enr["1:1"]["obra"]["obra_id"] = 43
    nuevo = preparar_contexto("abcdef123456", e, enr, "obras")
    assert nuevo["huella_contexto"] != p["huella_contexto"]
    assert "ficha_y_seleccion_difieren" in nuevo["casos"][0]["disparadores"]


def test_multiobra_conserva_declaradas_sin_enriquecer_sin_heredar_fechas():
    p = preparar_contexto("abcdef123456", espejo([{"proyecto": "A"}, {"proyecto": "B"}]),
                         {"1:1": {"sub_obras": [{"cui": "1234567"}]}}, "obras")
    assert [c["caso_id"] for c in p["casos"]] == ["1:1:s1", "1:1:s2"]
    assert "fecha_inicial" not in p["casos"][1]["declarado_subobra"]
    assert "identificacion_pendiente" in p["casos"][1]["disparadores"]


def test_privada_omitida_no_equivale_a_verificada():
    p = preparar_contexto("abcdef123456", espejo(), {"1:1": {"via": "PRIVADA"}}, "obras")
    assert not p["casos"]
    assert p["omitidos"][0]["motivo"] == "ruta_privada_vigente_no_auditada"


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
@pytest.mark.parametrize("extra,motivo", [
    ({"via": "RUC"}, "contratista_no_demuestra_intervencion"),
    ({"seace": {"estado": "seleccionado"}}, "contrato_requiere_contraste_de_rol_y_emisor"),
])
def test_positivo_con_ficha_no_exime_identidad_contractual(tipo, extra, motivo):
    ev = {"cui": "1234567", "via": "NOMBRE", "obra": {"obra_id": 42}, **extra}
    caso = preparar_contexto("abcdef123456", espejo(), {"1:1": ev}, tipo)["casos"][0]
    assert caso["accion"] == "investigar"
    assert motivo in caso["disparadores"]


def test_duplicados_rechazados():
    e = espejo(); e["profesionales"] *= 2
    with pytest.raises(ValueError):
        preparar_contexto("abcdef123456", e, {}, "obras")


@pytest.mark.parametrize("estado,codigo", [("en_proceso",409),("completado",200),("requiere_revision",200)])
def test_api_solo_lectura(monkeypatch, estado, codigo):
    import api.app as modulo
    from fastapi.testclient import TestClient
    monkeypatch.setattr(modulo, "_job_o_404", lambda jid: SimpleNamespace(estado=estado))
    monkeypatch.setattr(modulo, "_espejo_o_404", lambda jid: espejo())
    monkeypatch.setattr(modulo.repo, "cargar_enriquecimiento", lambda jid: {})
    monkeypatch.setattr(modulo, "tipo_evaluacion_del_espejo", lambda e: "obras")
    r = TestClient(modulo.app).get('/api/pivote/jobs/abcdef123456/investigacion-identidad')
    assert r.status_code == codigo
    if codigo == 200:
        assert r.json()["casos"][0]["accion"] == "investigar"
