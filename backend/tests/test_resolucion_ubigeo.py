"""
Tests offline del VETO DE UBICACIÓN (F8). Sin red.

La auditoría del job c9c769976750 halló 4 CUIs mal resueltos con patrón común:
candidato del mismo departamento pero OTRA provincia/distrito (San Agustín→El
Tambo, Jaén→Magdalena del Mar, Jauja→Tarma). Reglas:
  - contradicción de PROVINCIA (ambas partes declaradas) → VETO (visible en
    candidatos de revisión), con exención por ruc_match;
  - contradicción SOLO de distrito (provincia no contradicha) → penaliza −25;
  - ausencia de datos en cualquiera de los lados → señal inerte.
"""
from __future__ import annotations

import pytest

from resolucion.cui import (_provincia_desde_cola, _terminos_geo, _ubigeo_contra,
                            resolver, ubigeo_cert)


class _Base:
    """Base MEF de juguete: solo fichas por CUI (sin candidatos propios)."""

    def __init__(self, fichas):
        self.fichas = fichas

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return []

    def existe_cui(self, codigo):
        return self.fichas.get(str(codigo))


class _Consulta:
    """InfoObras falso: buscar() devuelve siempre las mismas obras."""

    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return [o for o in self.obras if str(o.get("codUniqInv")) == str(codigo)]

    def buscar(self, nombre):
        return list(self.obras)


PROYECTO = ("MEJORAMIENTO DE LOS SERVICIOS DE LA I.E. 30001 SAN MARTIN, DISTRITO DE "
            "SAN AGUSTIN DE CAJAS, PROVINCIA DE HUANCAYO, DEPARTAMENTO DE JUNIN")
OBRA = {"codUniqInv": "2900001", "codigoObra": 111,
        "nombrObra": PROYECTO, "nombrDepartamento": "JUNIN"}


def _exp():
    return {"proyecto": PROYECTO, "cui": None}


def test_ubigeo_cert_extrae_prov_y_dist():
    sig = ubigeo_cert(_exp())
    assert "HUANCAYO" in sig["prov"]
    assert "SAN AGUSTIN DE CAJAS" in sig["dist"]
    assert "JUNIN" in sig["depto"]


def test_cola_geografica_exige_tres_niveles():
    # "…, CAMANA, AREQUIPA" con solo dos niveles NO infiere provincia (el término
    # previo al depto podría ser distrito o localidad — un falso positivo VETA)
    assert _provincia_desde_cola(_terminos_geo("OBRA EN CAMANA, AREQUIPA")) == set()
    tres = _terminos_geo("OBRA EN OCONA, CAMANA, AREQUIPA")
    assert "CAMANA" in _provincia_desde_cola(tres)


def test_contradiccion_de_provincia_veta():
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "TARMA", "dist": "ACOBAMBA"}})
    r = resolver(_exp(), _Consulta([OBRA]), base=base)
    assert r["estado"] == "revision"
    assert r["cui"] is None
    cuis_visibles = {c["cui"] for c in r["candidatos"]}
    assert "2900001" in cuis_visibles          # vetado pero visible para el humano


def test_provincia_coincidente_no_veta():
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "HUANCAYO",
                              "dist": "SAN AGUSTIN DE CAJAS"}})
    r = resolver(_exp(), _Consulta([OBRA]), base=base)
    assert r["estado"] == "resuelto"
    assert r["cui"] == "2900001"


def test_contradiccion_solo_distrito_penaliza_sin_vetar():
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "HUANCAYO", "dist": "EL TAMBO"}})
    r = resolver(_exp(), _Consulta([OBRA]), base=base)
    assert r["estado"] == "resuelto"           # misma provincia: no veta
    assert r["cui"] == "2900001"
    base_ok = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                                 "dpto": "JUNIN", "prov": "HUANCAYO",
                                 "dist": "SAN AGUSTIN DE CAJAS"}})
    r_ok = resolver(_exp(), _Consulta([OBRA]), base=base_ok)
    assert r["candidatos"][0]["score"] < r_ok["candidatos"][0]["score"]


def test_ruc_match_exento_del_veto():
    obra = dict(OBRA, rucEjecutor="20123456789")
    exp = dict(_exp(), ruc_emisor="20123456789")
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "TARMA", "dist": "ACOBAMBA"}})
    r = resolver(exp, _Consulta([obra]), base=base)
    assert r["estado"] == "resuelto"
    assert r["via"] == "RUC"


def test_municipalidad_contratante_distinta_veta():
    # contratante = Municipalidad Distrital de San Agustín; el CUI candidato es de
    # la Municipalidad Distrital de El Tambo → veto (caso auditado 1:3 del BNP)
    exp = dict(_exp(), entidad_contratante="MUNICIPALIDAD DISTRITAL DE SAN AGUSTIN")
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "HUANCAYO", "dist": "EL TAMBO",
                              "entidad": "MUNICIPALIDAD DISTRITAL DE EL TAMBO"}})
    r = resolver(exp, _Consulta([OBRA]), base=base)
    assert r["estado"] == "revision"
    assert r["cui"] is None


def test_misma_municipalidad_no_veta():
    exp = dict(_exp(), entidad_contratante="MUNICIPALIDAD DISTRITAL DE SAN AGUSTIN DE CAJAS")
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "JUNIN", "prov": "HUANCAYO",
                              "dist": "SAN AGUSTIN DE CAJAS",
                              "entidad": "MUNICIPALIDAD DISTRITAL DE SAN AGUSTIN DE CAJAS"}})
    r = resolver(exp, _Consulta([OBRA]), base=base)
    assert r["estado"] == "resuelto"
    assert r["cui"] == "2900001"


def test_sin_datos_es_inerte():
    # cert sin provincia declarada y ficha sin prov: nada cambia. (El colegio NO
    # debe llamarse como un departamento — "San Martín" dispararía la señal de
    # depto legítimamente.)
    exp = {"proyecto": "MEJORAMIENTO DE LOS SERVICIOS DE LA I.E. 30001 LOS LIBERTADORES",
           "cui": None}
    obra = dict(OBRA, nombrObra=exp["proyecto"])
    base = _Base({"2900001": {"cui": "2900001", "nombre": exp["proyecto"],
                              "dpto": "JUNIN", "prov": "", "dist": ""}})
    assert _ubigeo_contra(ubigeo_cert(exp),
                          base.existe_cui("2900001")) == (False, False, False)
    r = resolver(exp, _Consulta([obra]), base=base)
    assert r["cui"] == "2900001"
