from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaSunatReal, _nombre_emisor_limpio


@dataclass
class Empresa:
    ruc: str
    razon_social: str = "EMPRESA"
    fecha_inscripcion: object = None
    estado: str = "ACTIVO"
    condicion: str = "HABIDO"
    fecha_inicio_actividades: object = None
    tipo_contribuyente: str = "SOCIEDAD"
    nombre_comercial: str = ""
    domicilio_fiscal: str = ""
    actividades_economicas: list = None


def _ctx(exps):
    return Contexto(job=None, espejo={"postor": {}, "profesionales": [{"n_prof": 1,
        "experiencias": exps}]}, enriquecimiento={})


def _etapa(buscador, consultor=lambda r: Empresa(r), extras=lambda r: ([], None)):
    return EtapaSunatReal(consultor=consultor, buscador=buscador, extras=extras)


def test_mismo_nombre_busca_una_vez_y_copia_matches():
    llamadas = []
    def buscar(nombre):
        llamadas.append(nombre)
        return [{"ruc": "20123456789", "razon_social": nombre}]
    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA CONSTRUCTORA S.A.C."},
                {"n": 2, "entidad_emisora": "ALFA CONSTRUCTORA S.A.C."}])
    _etapa(buscar).correr(ctx)
    assert llamadas == [_nombre_emisor_limpio("ALFA CONSTRUCTORA S.A.C.")]
    assert ctx.enriquecimiento["1:1"]["sunat"]["ruc"] == "20123456789"
    assert ctx.enriquecimiento["1:2"]["sunat"]["ruc"] == "20123456789"


def test_vacios_y_excepcion_no_se_cachean_y_reintentan():
    llamadas = []
    respuestas = [[], RuntimeError("caída"), [{"ruc": "20123456789", "razon_social": "ALFA"}]]
    def buscar(nombre):
        llamadas.append(nombre)
        valor = respuestas.pop(0)
        if isinstance(valor, Exception): raise valor
        return valor
    ctx = _ctx([{"n": i, "entidad_emisora": "ALFA"} for i in (1, 2, 3)])
    _etapa(buscar).correr(ctx)
    assert len(llamadas) == 3
    assert ctx.enriquecimiento["1:3"]["sunat"]["ruc"] == "20123456789"


def test_cache_es_local_a_cada_correr_y_nombres_distintos_no_se_mezclan():
    llamadas = []
    def buscar(nombre):
        llamadas.append(nombre)
        return [{"ruc": "20123456789", "razon_social": nombre}]
    etapa = _etapa(buscar)
    for _ in range(2):
        etapa.correr(_ctx([{"n": 1, "entidad_emisora": "ALFA S.A.C."}]))
    assert len(llamadas) == 2
    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA S.A.C."},
                {"n": 2, "entidad_emisora": "BETA S.A."}])
    etapa.correr(ctx)
    assert len(llamadas) == 4
    assert _nombre_emisor_limpio("ALFA S.A.C.") != _nombre_emisor_limpio("BETA S.A.")


def test_ambiguos_reutilizan_candidatos_sin_promover_ruc():
    llamadas = []
    candidatos = [{"ruc": "20111111111", "razon_social": "ALFA NORTE"},
                  {"ruc": "20222222222", "razon_social": "ALFA SUR"}]
    def buscar(nombre):
        llamadas.append(nombre)
        return candidatos
    def no_consultar(_):
        pytest.fail("Una búsqueda ambigua no debe consultar un RUC")
    ctx = _ctx([{"n": n, "entidad_emisora": "ALFA"} for n in (1, 2)])
    res = _etapa(buscar, consultor=no_consultar).correr(ctx)
    assert llamadas == ["ALFA"]
    assert res.metrica.items_revision == 2
    for n in (1, 2):
        datos = ctx.enriquecimiento[f"1:{n}"]["sunat"]
        assert datos["ambiguo"] == 2 and datos["candidatos"] == candidatos
        assert "ruc" not in datos


def test_cache_entrega_copias_y_no_la_lista_compartida(monkeypatch):
    from importlib import import_module
    etapas = import_module("orquestador.etapas_reales")
    candidatos = [{"ruc": "20111111111", "razon_social": "ALFA NORTE"},
                  {"ruc": "20222222222", "razon_social": "ALFA SUR"}]
    recibidos = []
    def elegir(nombre, matches):
        recibidos.append([m["razon_social"] for m in matches])
        matches[0]["razon_social"] = "MODIFICADO POR CONSUMIDOR"
        return None
    monkeypatch.setattr(etapas, "_elegir_match_exacto", elegir)
    ctx = _ctx([{"n": n, "entidad_emisora": "ALFA"} for n in (1, 2, 3)])
    _etapa(lambda _: candidatos).correr(ctx)
    assert recibidos == [["ALFA NORTE", "ALFA SUR"]] * 3


def test_consultas_exactas_no_fusionan_sufijos_legales():
    nombres = ["ALFA S.A.C.", "ALFA S.A."]
    assert len({_nombre_emisor_limpio(n) for n in nombres}) == 2
    consultas = []
    def buscar(nombre):
        consultas.append(nombre)
        return [{"ruc": "20111111111" if nombre == nombres[0] else "20222222222",
                 "razon_social": nombre}]
    ctx = _ctx([{"n": i, "entidad_emisora": nombre} for i, nombre in enumerate(nombres, 1)])
    _etapa(buscar).correr(ctx)
    assert consultas == nombres
    assert ctx.enriquecimiento["1:1"]["sunat"]["ruc"] != ctx.enriquecimiento["1:2"]["sunat"]["ruc"]


def test_ruc_declarado_y_solo_items_respetados():
    consultas = []
    def no_buscar(_):
        pytest.fail("No debe buscar por nombre si el RUC está declarado")
    def consultar(ruc):
        consultas.append(ruc)
        return Empresa(ruc)
    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA"},
                {"n": 2, "ruc_emisor": "20111111111"},
                {"n": 3, "ruc_emisor": "20222222222"}])
    ctx.solo_items = {(1, 2)}
    _etapa(no_buscar, consultor=consultar).correr(ctx)
    assert consultas == ["20111111111"]
    assert set(ctx.enriquecimiento) == {"1:2"}
    assert ctx.enriquecimiento["1:2"]["sunat"]["via"] == "cert"


def test_alt04_se_calcula_por_experiencia_aunque_emisor_se_reutilice():
    conteo = {"nombre": 0, "ruc": 0, "extras": 0}
    def buscar(nombre):
        conteo["nombre"] += 1
        return [{"ruc": "20111111111", "razon_social": nombre}]
    def consultar(ruc):
        conteo["ruc"] += 1
        return Empresa(ruc, fecha_inscripcion=date(2020, 1, 1))
    def extras(ruc):
        conteo["extras"] += 1
        return [], None
    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA", "fecha_inicial": "2019-01-01"},
                {"n": 2, "entidad_emisora": "ALFA", "fecha_inicial": "2021-01-01"}])
    res = _etapa(buscar, consultar, extras).correr(ctx)
    assert conteo == {"nombre": 1, "ruc": 1, "extras": 1}
    assert ctx.enriquecimiento["1:1"]["sunat"]["alt04"]["estado"] == "ALERTA"
    assert ctx.enriquecimiento["1:2"]["sunat"]["alt04"] is None
    assert [o.referencia for o in res.observaciones if o.codigo == "ALT04"] == ["prof=1 exp=1"]


def test_log_cuenta_tambien_las_llamadas_fallidas(caplog):
    respuestas = [RuntimeError("portal"), [{"ruc": "20111111111", "razon_social": "ALFA"}]]
    def buscar(_):
        valor = respuestas.pop(0)
        if isinstance(valor, Exception):
            raise valor
        return valor
    ctx = _ctx([{"n": n, "entidad_emisora": "ALFA"} for n in (1, 2, 3)])
    with caplog.at_level("INFO"):
        _etapa(buscar).correr(ctx)
    assert "2 llamadas, 1 reutilizaciones" in caplog.text
