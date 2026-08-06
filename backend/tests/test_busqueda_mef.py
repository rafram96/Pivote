"""
Tests offline del buscador de la base local del MEF (resolucion/busqueda_mef.py).

Sin red: se usa la base mini congelada en tests/fixtures/mef (fixture
`dir_mef_mini` de conftest). Cubre lo que promete el contrato del endpoint
`GET /api/pivote/mef/buscar`: encuentra por nombre y por código, los filtros
descartan, el límite corta, y la base ausente responde con bandera en vez de
reventar.
"""
from __future__ import annotations

import pytest

from resolucion.base_mef import BaseMef
from resolucion.busqueda_mef import ConsultaInvalida, buscar


@pytest.fixture
def base(dir_mef_mini) -> BaseMef:
    return BaseMef(dir_mef_mini)


# ── encuentra ────────────────────────────────────────────────────────────────

def test_busca_por_nombre_y_devuelve_la_ficha_completa(base):
    r = buscar("hospital regional hermilio valdizan huanuco", base=base)
    assert r["base_mef_no_disponible"] is False
    assert r["coincidencia"] == "nombre"
    assert r["total"] >= 1
    top = r["resultados"][0]
    assert top["cui"] == "2366120"
    assert "HERMILIO VALDIZAN" in top["nombre"]
    assert top["ubicacion"] == "HUANUCO, HUANUCO, HUANUCO"
    assert top["entidad"] == "GOBIERNO REGIONAL DE HUANUCO"
    assert top["estado"] == "ACTIVO"
    assert top["situacion"] == "EN EJECUCION FISICA"
    assert top["score"] >= 60
    assert isinstance(r["ms"], float)      # la latencia se mide, no se promete


def test_busca_por_cui_exacto(base):
    r = buscar("2200145", base=base)
    assert r["coincidencia"] == "codigo"
    assert r["total"] == 1
    assert r["resultados"][0]["cui"] == "2200145"
    assert r["resultados"][0]["score"] == 100.0


def test_busca_por_snip_exacto(base):
    r = buscar("361313", base=base)
    assert r["coincidencia"] == "codigo"
    assert r["resultados"][0]["snip"] == "361313"
    assert r["resultados"][0]["cui"] is None      # esta fila no tiene CUI


def test_numero_que_no_es_codigo_cae_a_la_busqueda_por_nombre(base):
    # "1452" no es un CUI; sí aparece en el nombre de un colegio
    r = buscar("institucion educativa 1452 krear", base=base)
    assert r["coincidencia"] == "nombre"
    assert r["resultados"][0]["cui"] == "2311876"


def test_texto_generico_lo_dice_en_vez_de_devolver_vacio_a_secas(base):
    # todas las palabras son comunes a decenas de miles de nombres → el índice
    # no tiene por dónde acotar, y eso hay que decirlo
    r = buscar("puesto de salud", base=base)
    assert r["total"] == 0
    assert r["base_mef_no_disponible"] is False
    assert "demasiado genérico" in r["aviso"]


def test_sin_coincidencias_no_es_un_error(base):
    r = buscar("planta nuclear de la luna", base=base)
    assert r["total"] == 0
    assert r["resultados"] == []
    assert r["base_mef_no_disponible"] is False
    assert r["aviso"] is None


# ── filtros ──────────────────────────────────────────────────────────────────

def test_filtro_geografico_descarta(base):
    sin_filtro = buscar("hospital regional", limite=50, base=base)
    assert {x["cui"] for x in sin_filtro["resultados"]} == {"2200145", "2366120"}

    con_filtro = buscar("hospital regional", dpto="huancavelica", limite=50, base=base)
    assert con_filtro["filtros"] == {"dpto": "huancavelica"}
    assert {x["cui"] for x in con_filtro["resultados"]} == {"2200145"}


def test_filtro_por_entidad_es_parcial_y_sin_tildes(base):
    r = buscar("hospital", entidad="gobierno regional", limite=50, base=base)
    assert r["total"] >= 1
    assert all("GOBIERNO REGIONAL" in x["entidad"] for x in r["resultados"])


def test_filtro_tambien_se_aplica_al_acierto_por_codigo(base):
    assert buscar("2200145", dpto="huancavelica", base=base)["total"] == 1
    # el mismo CUI con un departamento que no es el suyo: cero, y es lo correcto
    fuera = buscar("2200145", dpto="lima", base=base)
    assert fuera["coincidencia"] == "codigo"
    assert fuera["total"] == 0


def test_filtro_por_distrito(base):
    r = buscar("hospital regional", dist="lircay", limite=50, base=base)
    assert {x["cui"] for x in r["resultados"]} == {"2200145"}


# ── límite ───────────────────────────────────────────────────────────────────

def test_limite_corta_la_lista(base):
    amplio = buscar("distrito de san pablo de pillao", limite=50, base=base)
    assert amplio["total"] > 2
    corto = buscar("distrito de san pablo de pillao", limite=2, base=base)
    assert corto["total"] == 2
    assert corto["limite"] == 2
    # el corte respeta el orden: los 2 primeros son los mismos
    assert [x["cui"] for x in corto["resultados"]] == \
           [x["cui"] for x in amplio["resultados"][:2]]


def test_limite_no_recorta_antes_de_filtrar(base):
    """Con límite 1 y un filtro que descarta a los mejor puntuados, igual debe
    aparecer el que sí pasa el filtro (se sobre-pide al índice y se filtra
    ANTES de cortar). El colegio de Lima es el 3.º de la lista sin filtro."""
    r = buscar("distrito de san pablo de pillao", dpto="lima", limite=1, base=base)
    assert [x["cui"] for x in r["resultados"]] == ["2311876"]


# ── entradas inválidas ───────────────────────────────────────────────────────

@pytest.mark.parametrize("q", ["", "  ", "a", "x" * 201])
def test_texto_invalido(base, q):
    with pytest.raises(ConsultaInvalida):
        buscar(q, base=base)


@pytest.mark.parametrize("limite", [0, -3, 51, "muchos"])
def test_limite_invalido(base, limite):
    with pytest.raises(ConsultaInvalida):
        buscar("hospital", limite=limite, base=base)


# ── base ausente ─────────────────────────────────────────────────────────────

def test_base_ausente_avisa_en_castellano_y_no_revienta(tmp_path):
    r = buscar("hospital regional", base=BaseMef(tmp_path))   # carpeta vacía
    assert r["base_mef_no_disponible"] is True
    assert r["total"] == 0
    assert r["resultados"] == []
    assert "no está instalada" in r["aviso"]
    assert r["edad_dias"] is None


def test_base_ausente_valida_igual_la_entrada(tmp_path):
    """Primero se valida lo que pidió el usuario: un texto imposible es 400
    aunque la base falte (si no, el aviso taparía el error real)."""
    with pytest.raises(ConsultaInvalida):
        buscar("x", base=BaseMef(tmp_path))
