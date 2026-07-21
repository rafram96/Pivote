"""
Tests offline de la base local del MEF (resolucion/base_mef.py).

Sin red: se cargan los fixtures mini congelados en tests/fixtures/mef/
(mef_mini.csv.gz + entidades_mini.csv, 24 filas inventadas pero realistas) hacia
una carpeta temporal con los nombres canónicos que espera BaseMef.
"""
from __future__ import annotations

import gzip
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from resolucion.base_mef import BaseMef, instancia

FIX = Path(__file__).parent / "fixtures" / "mef"


@pytest.fixture
def base(tmp_path) -> BaseMef:
    """BaseMef apuntada a una copia temporal de los fixtures mini con los nombres
    de archivo canónicos (inversiones.csv.gz / entidades_publicas.csv / metadata.json)."""
    shutil.copy(FIX / "mef_mini.csv.gz", tmp_path / "inversiones.csv.gz")
    shutil.copy(FIX / "entidades_mini.csv", tmp_path / "entidades_publicas.csv")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"fecha": date.today().isoformat(), "cuis_distintos": 23}),
        encoding="utf-8")
    return instancia(dir_base=tmp_path)


# ── disponibilidad ───────────────────────────────────────────────────────────

def test_disponible_con_fixtures(base):
    assert base.disponible() is True
    assert base.edad_dias() == 0


def test_sin_archivos_es_inerte(tmp_path):
    b = BaseMef(tmp_path)          # carpeta vacía
    assert b.disponible() is False
    assert b.edad_dias() is None
    assert b.buscar_candidatos("cualquier cosa") == []
    assert b.existe_cui("2376130") is None
    assert b.es_entidad_publica("INEN") == (False, 0.0)


# ── búsqueda por nombre ──────────────────────────────────────────────────────

def test_buscar_por_nombre_truncado(base):
    # nombre como vendría de un certificado: truncado y con cola geográfica
    q = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DEL PUESTO DE SALUD DEL "
         "CENTRO POBLADO DE CHINCHINGA DEL DISTRITO DE SAN PABLO DE PILLAO - "
         "PROVINCIA DE HUANUCO -")
    res = base.buscar_candidatos(q)
    assert res, "debería hallar candidatos"
    assert res[0]["cui"] == "2376130"
    assert res[0]["score"] >= 90
    # el ficha trae los campos del contrato
    assert res[0]["dpto"] == "HUANUCO"
    assert res[0]["estado_dataset"] == "ACTIVO"


def test_buscar_no_confunde_rubro_pero_ambos_aparecen(base):
    # la losa deportiva de Chinchinga es OTRA obra; puede aparecer pero NO como top1
    q = "PUESTO DE SALUD DE CHINCHINGA SAN PABLO DE PILLAO HUANUCO"
    res = base.buscar_candidatos(q)
    assert res[0]["cui"] == "2376130"


def test_buscar_sin_match_devuelve_vacio(base):
    assert base.buscar_candidatos("XKZQ WWPLPL NADAQUEVERAQUI") == []


# ── existe_cui ───────────────────────────────────────────────────────────────

def test_existe_cui_por_codigo(base):
    f = base.existe_cui("2376130")
    assert f is not None
    assert "CHINCHINGA" in f["nombre"]
    assert f["snip"] == ""


def test_existe_cui_por_snip_cuando_no_hay_cui(base):
    # fila SNIP-only (sin CODIGO_UNICO): accesible por su SNIP
    f = base.existe_cui("361313")
    assert f is not None
    assert f["cui"] == ""
    assert "YUYAPICHIS" in f["nombre"]


def test_existe_cui_inexistente(base):
    assert base.existe_cui("9999999") is None
    assert base.existe_cui("") is None


# ── entidades públicas ───────────────────────────────────────────────────────

def test_entidad_publica_por_sigla(base):
    ok, score = base.es_entidad_publica("INEN")
    assert ok is True
    assert score == 100.0


def test_entidad_publica_orden_san_agustin_es_falso(base):
    # caso trampa: matchea ~82 con "MUNICIPALIDAD DISTRITAL DE SAN AGUSTIN"
    # pero el umbral 90 es DURO → no es entidad pública
    ok, score = base.es_entidad_publica("ORDEN DE SAN AGUSTIN")
    assert ok is False
    assert score < 90


def test_entidad_publica_fuzzy_alto(base):
    ok, _ = base.es_entidad_publica("MUNICIPALIDAD PROVINCIAL DE TRUJILLO")
    assert ok is True


# ── determinismo ─────────────────────────────────────────────────────────────

def test_homonimo_orden_determinista(base):
    # dos CUIs con nombre IDÉNTICO → mismo score; desempate estable por CUI asc
    res = base.buscar_candidatos("CONSTRUCCION DEL COLISEO DEPORTIVO DE MONTERREY")
    cuis = [r["cui"] for r in res if r["nombre"].endswith("MONTERREY")]
    assert cuis[:2] == ["2500001", "2500002"]
    # repetir la consulta da el MISMO orden
    res2 = base.buscar_candidatos("CONSTRUCCION DEL COLISEO DEPORTIVO DE MONTERREY")
    assert [r["cui"] for r in res] == [r["cui"] for r in res2]
