"""Fuentes simuladas y entregables temporales: nunca jobs del cliente."""
from copy import deepcopy
from datetime import date
import zipfile

import pytest

from orquestador.recontraste_identidad import recontrastar_asociaciones
from scraping.infoobras import WorkInfo
from test_aplicar_identidad import insumos, proyectar, procesos


@pytest.fixture(autouse=True)
def fuentes_sin_red(monkeypatch):
    from orquestador.recontraste_fuentes import FuentesRecontraste
    monkeypatch.setattr("orquestador.recontraste_identidad.FuentesRecontraste", lambda:
        FuentesRecontraste(ficha=lambda c: None, contratos=lambda c: None,
                          empresa=lambda r: None, buscar=lambda n: [], extras=lambda r: ([], None)))


def obra_correcta(*args, **kwargs):
    assert args == ("2000002",)
    assert kwargs == {"obra_id": 20}  # jamás pasar fechas al selector
    return WorkInfo(cui="2000002", obra_id=20, nombre="Hospital corregido",
                    codigo_infoobras="COD-NUEVO", monto_contrato=123456,
                    fecha_inicio=date(2021, 1, 1))


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_ficha_correcta_recalcula_sin_heredar_otro_proyecto(tipo):
    e, enr, r = insumos(tipo)
    e["profesionales"][0]["experiencias"][0].update(fecha_inicial="2020-01-01", fecha_final="2020-12-31")
    # Obtener huella nueva sin editarla manualmente.
    from entregables.investigacion_identidad import preparar_contexto
    r["huella_contexto"] = preparar_contexto(r["job_id"], e, enr, tipo)["huella_contexto"]
    nuevo, _ = proyectar(e, enr, r)
    nuevo["prof:1"] = {"dias_efectivos": 9999, "cumple_backend": "VIEJO"}
    nuevo["2:1"] = {"testigo": "intacto"}
    antes = deepcopy((e, nuevo))
    final = recontrastar_asociaciones(e, nuevo, ["1:1"], leer_obra=obra_correcta)
    assert (e, nuevo) == antes
    assert final["2:1"] == nuevo["2:1"]
    unidad = final["1:1"]
    assert unidad["obra_ficha"]["obra_id"] == 20
    assert unidad["obra_ficha"]["monto"] == 123456
    assert unidad["obra_nombre"] == "Hospital corregido"
    assert final["prof:1"].get("dias_efectivos") != 9999
    assert unidad["asociacion_investigada"]["fuentes"]["infoobras"]["estado"] == "disponible"
    assert unidad["seace"]["ocid"] == "proceso-ejecucion"
    if tipo == "expedientes":
        assert not unidad.get("paralizaciones")
        assert not unidad["verificacion_expediente"]["verificado_en_mef"]
        assert len(unidad["cruces_fechas"]) == 2
    else:
        assert unidad["paralizaciones"]


@pytest.mark.parametrize("respuesta", ["sin_datos", "caida", "otra_ficha", "otro_cui"])
def test_fuente_faltante_no_se_convierte_en_cero_o_ausencia_demostrada(respuesta):
    e, enr, r = insumos()
    nuevo, _ = proyectar(e, enr, r)
    def leer(*a, **kw):
        if respuesta == "caida": raise TimeoutError("fuente")
        if respuesta == "sin_datos": return None
        return WorkInfo(cui="9999999" if respuesta == "otro_cui" else "2000002",
                        obra_id=99 if respuesta == "otra_ficha" else 20)
    final = recontrastar_asociaciones(e, nuevo, ["1:1"], leer_obra=leer)["1:1"]
    assert final["sin_verificar"]
    assert final["obra"]["obra_id"] == 20
    assert "obra_ficha" not in final and "paralizaciones" not in final
    assert final["asociacion_investigada"]["fuentes"]["infoobras"]["estado"] != "disponible"
    assert final["asociacion_investigada"]["anterior"] == enr["1:1"]


def test_seace_fecha_y_monto_solo_del_contrato_exacto():
    e, enr, r = insumos()
    def leer(cui):
        ps = procesos(cui)
        elegido = ps[1]["contracts"][0]
        elegido.update(dateSigned="2022-03-04", value={"amount": 777},
                       period={"startDate": "2022-04-01", "endDate": "2022-10-01"})
        ps[1]["contracts"].append({"id": "ajeno", "dateSigned": "1999-01-01", "value": {"amount": 999999}})
        return ps
    nuevo, _ = proyectar(e, enr, r, leer_procesos=leer)
    s = nuevo["1:1"]["seace"]
    assert s["fecha_suscripcion"] == "2022-03-04"
    assert s["proceso"]["monto"] == 777
    assert s["vigencia"] == ["2022-04-01", "2022-10-01"]
    assert len(s["proceso_fuente"]["contracts"]) == 1


@pytest.mark.parametrize("monto", [None, 0])
def test_no_confunde_valor_referencial_con_monto_contractual(monto):
    e, enr, r = insumos()
    def leer(cui):
        ps = procesos(cui)
        ps[1]["tender"]["value"] = {"amount": 99999}
        ps[1]["contracts"][0]["value"] = {"amount": monto}
        return ps
    nuevo, _ = proyectar(e, enr, r, leer_procesos=leer)
    assert nuevo["1:1"]["seace"]["proceso"]["monto"] == monto


def test_multiobra_sin_fechas_globales_y_cache_por_ficha():
    e, enr, r = insumos()
    nuevo, _ = proyectar(e, enr, r)
    unidad = nuevo["1:1"]
    e["profesionales"][0]["experiencias"][0].update(
        fecha_inicial="2000-01-01", fecha_final="2025-01-01", obras=[{}, {}, {}])
    nuevo["1:1"] = {"via": "MULTI_OBRA", "sub_obras": [unidad, deepcopy(unidad), {"testigo": "intacto"}],
                     "paralizaciones": [{"inicio": "1900-01-01", "fin": "2020-01-01"}]}
    llamadas = []
    def leer(*args, **kwargs):
        llamadas.append(kwargs)
        return obra_correcta(*args, **kwargs)
    final = recontrastar_asociaciones(e, nuevo, ["1:1:s1", "1:1:s2"], leer_obra=leer)
    assert len(llamadas) == 1
    padre = final["1:1"]
    assert "paralizaciones" not in padre
    assert padre["sin_verificar"]
    assert padre["sub_obras"][2] == {"testigo": "intacto"}
    for s in padre["sub_obras"][:2]:
        assert not s.get("paralizaciones")
        assert s["ficha"]["obra_id"] == 20
        assert "fecha_declarada" not in s["cruces_fechas"][0]


def test_abstencion_no_consulta_ni_restituye_fuentes():
    e, enr, r = insumos()
    r.update(estado="ambiguo", seleccion_propuesta=None, motivo="Sin identidad única",
             consultas=[{"fuente": "InfoObras", "estado": "leido"}])
    nuevo, _ = proyectar(e, enr, r)
    final = recontrastar_asociaciones(e, nuevo, ["1:1"], leer_obra=lambda *a, **kw: pytest.fail("No consultar"))
    assert final["1:1"]["cui"] is None
    assert final["1:1"]["sin_verificar"]
    assert not final["1:1"].get("obra_ficha")


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_generador_existente_muestra_ficha_nueva_sin_datos_anteriores(tmp_path, tipo):
    from entregables.excel_final import regenerar_excel_final
    from entregables.investigacion_identidad import preparar_contexto
    e, enr, r = insumos(tipo)
    e["profesionales"][0]["experiencias"][0].update(fecha_inicial="2020-01-01", fecha_final="2020-12-31")
    r["huella_contexto"] = preparar_contexto(r["job_id"], e, enr, tipo)["huella_contexto"]
    nuevo, _ = proyectar(e, enr, r)
    final = recontrastar_asociaciones(e, nuevo, ["1:1"], leer_obra=obra_correcta)
    ruta = tmp_path / "prueba.xlsx"
    regenerar_excel_final(deepcopy(e), deepcopy(final), ruta,
                         {(1, 1): (final["1:1"]["decision"], "Revisar evidencia")})
    with zipfile.ZipFile(ruta) as z:
        texto = " ".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))
    assert "Hospital corregido" in texto
    assert "COD-NUEVO" in texto
    assert "2000002" in texto
    assert "1000001" not in texto
    assert "anterior.pdf" not in texto
    if tipo == "expedientes":
        assert "lectura MEF fue incompleta" in texto
