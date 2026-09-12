from __future__ import annotations

from dataclasses import dataclass

from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaSunatReal


@dataclass
class Empresa:
    ruc: str
    razon_social: str = "EMPRESA"
    estado: str = "ACTIVO"
    condicion: str = "HABIDO"


def _ctx(experiencias):
    return Contexto(
        job=None,
        espejo={"postor": {}, "profesionales": [{"n_prof": 1,
            "experiencias": experiencias}]},
        enriquecimiento={},
    )


def test_buscador_legacy_vacio_queda_no_registrado_sin_afirmar_portal_vacio():
    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA"}])
    EtapaSunatReal(buscador=lambda nombre: []).correr(ctx)

    fuente = ctx.enriquecimiento["1:1"]["consultas_fuentes"]["sunat_nombre"]
    assert fuente["estado"] == "no_registrado"
    assert fuente["nombre"] == "ALFA"
    assert ctx.enriquecimiento["1:1"]["sunat"].get("no_encontrado") is not True


def test_buscador_inyectado_puede_publicar_fallo_sin_reintento_de_firma():
    llamadas = []

    def buscar(nombre, *, diagnostico):
        llamadas.append(nombre)
        diagnostico.update(estado="fuente_no_disponible", motivo="timeout")
        return []

    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA"}])
    EtapaSunatReal(buscador=buscar).correr(ctx)

    assert llamadas == ["ALFA"]
    assert ctx.enriquecimiento["1:1"]["sunat"].get("no_encontrado") is not True
    assert ctx.enriquecimiento["1:1"]["consultas_fuentes"]["sunat_nombre"] == {
        "nombre": "ALFA", "estado": "fuente_no_disponible", "motivo": "timeout"
    }


def test_cache_nombre_conserva_diagnostico_y_no_comparte_su_diccionario():
    llamadas = []

    def buscar(nombre, *, diagnostico):
        llamadas.append(nombre)
        diagnostico.update(estado="con_resultados", motivo="portal")
        return [{"ruc": "20111111111", "razon_social": nombre}]

    def consultar(ruc, *, diagnostico):
        diagnostico.update(estado="con_resultados", motivo="detalle")
        return Empresa(ruc)

    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA"},
                {"n": 2, "entidad_emisora": "ALFA"}])
    EtapaSunatReal(consultor=consultar, buscador=buscar,
                   extras=lambda ruc: ([], None)).correr(ctx)

    assert llamadas == ["ALFA"]
    for clave in ("1:1", "1:2"):
        assert ctx.enriquecimiento[clave]["consultas_fuentes"]["sunat_nombre"]["motivo"] == "portal"


def test_detalle_ruc_fallido_conserva_ruc_consultado_pero_no_ficha_sunat():
    def buscar(nombre, *, diagnostico):
        diagnostico.update(estado="con_resultados", motivo="portal")
        return [{"ruc": "20111111111", "razon_social": nombre}]

    def consultar(ruc, *, diagnostico):
        diagnostico.update(estado="fuente_no_disponible", motivo="timeout")
        return None

    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA"}])
    EtapaSunatReal(consultor=consultar, buscador=buscar).correr(ctx)
    datos = ctx.enriquecimiento["1:1"]

    assert datos["consultas_fuentes"]["sunat_ruc"] == {
        "ruc": "20111111111", "estado": "fuente_no_disponible", "motivo": "timeout"
    }
    assert "sunat" not in datos


def test_ruc_declarado_no_busca_nombre_y_publica_diagnostico_ruc():
    def no_buscar(nombre):
        raise AssertionError("no debe buscar por nombre")

    def consultar(ruc, *, diagnostico):
        diagnostico.update(estado="con_resultados", motivo="detalle")
        return Empresa(ruc)

    ctx = _ctx([{"n": 1, "entidad_emisora": "ALFA 20111111111"}])
    EtapaSunatReal(consultor=consultar, buscador=no_buscar,
                   extras=lambda ruc: ([], None)).correr(ctx)
    datos = ctx.enriquecimiento["1:1"]
    assert datos["consultas_fuentes"]["sunat_ruc"]["estado"] == "con_resultados"
    assert datos["sunat"]["ruc"] == "20111111111"
