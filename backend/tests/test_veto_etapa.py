"""
VETO DE ETAPA — «3RA ETAPA» no es «2DA ETAPA», aunque sea el mismo proyecto.

Caso que lo motiva (corrida real, nombres ficticios aquí): la experiencia de un
expediente técnico «… — 3RA ETAPA» se resolvió contra el CUI cuyo nombre oficial
dice «… 2DA ETAPA», porque la resolución de aprobación nombraba al emisor y
ninguna otra señal separaba los dos registros. Una etapa distinta es OTRA
inversión: otro CUI, otro contrato, otras valorizaciones. Vale igual para
TRAMO, COMPONENTE y PAQUETE.

Reglas que fija este archivo:
  · `etapa_de` lee la clase y el número del nombre normalizado (y NO confunde el
    nivel hospitalario "III-1" con una etapa, ni "FASE" —esa es la fase del ciclo
    de inversión, con su propio veto).
  · el veto exige contradicción POSITIVA: si solo un lado declara etapa, no veta.
  · `ruc_match` NO exime: el mismo contratista suele ganar varias etapas.
  · lo vetado no compite (sale de `ranked`), así que ninguna vía —MEF, NÚMERO,
    RUC, NOMBRE— puede resolver contra él; se muestra en revisión con el motivo
    en llano.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from resolucion.cui import (  # noqa: E402
    _cotejo_codigo, _etapa_contradice, _rankear, etapa_de, resolver,
)

RUC_EMISOR = "20100000001"

_PROYECTO = ("Mejoramiento de los servicios académicos de la Facultad de Ciencias "
             "Empresariales de la Universidad Nacional del Valle Verde, distrito de "
             "Villa Nueva, provincia de Andes Altos, región Junín")
_NOMBRE_OBRA = ("MEJORAMIENTO DE LOS SERVICIOS ACADEMICOS DE LA FACULTAD DE CIENCIAS "
                "EMPRESARIALES DE LA UNIVERSIDAD NACIONAL DEL VALLE VERDE, DISTRITO DE "
                "VILLA NUEVA - ANDES ALTOS - JUNIN")


def _exp(sufijo: str = "", **extra) -> dict:
    exp = {"proyecto": _PROYECTO + sufijo,
           "ruc_emisor": RUC_EMISOR,
           "fecha_inicial": "2021-03-01",
           "fecha_final": "2022-06-30"}
    exp.update(extra)
    return exp


def _obra(cui: str, obra_id: int, sufijo: str = "") -> dict:
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id,
            "nombrObra": _NOMBRE_OBRA + sufijo,
            "nombrDepartamento": "JUNIN",
            "rucEjecutor": RUC_EMISOR, "rucSupervisor": ""}


class _Consulta:
    """Fake mínimo: devuelve siempre el mismo juego de obras congelado."""

    def __init__(self, obras):
        self.obras = list(obras)

    def buscar(self, nombre):
        return list(self.obras)

    def por_codigo(self, codigo):
        return [o for o in self.obras if str(o.get("codUniqInv")) == str(codigo)]


# ── (a) helper puro ──────────────────────────────────────────────────────────

def test_etapa_de_reconoce_las_variantes():
    assert etapa_de("Mejoramiento del local — 3RA ETAPA") == ("ETAPA", 3)
    assert etapa_de("SEGUNDA ETAPA del proyecto") == ("ETAPA", 2)
    assert etapa_de("Ampliación, ETAPA II") == ("ETAPA", 2)
    assert etapa_de("Carretera vecinal TRAMO 2") == ("TRAMO", 2)
    assert etapa_de("COMPONENTE 1 del paquete") == ("COMPONENTE", 1)
    assert etapa_de("PAQUETE N° 4 de colegios") == ("PAQUETE", 4)
    assert etapa_de("1era etapa de la obra") == ("ETAPA", 1)
    assert etapa_de("Décima etapa") == ("ETAPA", 10)


def test_etapa_de_no_confunde_nivel_hospitalario_ni_fase():
    # "III-1" es el nivel del establecimiento de salud, no una etapa
    assert etapa_de("HOSPITAL REGIONAL NIVEL III-1 DE VALLE VERDE") is None
    assert etapa_de("ETAPA III-1") is None
    # FASE es la fase del ciclo de inversión (expediente/ejecución), no una etapa
    assert etapa_de("FASE 2 del proyecto") is None
    # nombre sin etapa declarada
    assert etapa_de(_PROYECTO) is None
    assert etapa_de("") is None


def test_etapa_contradice_exige_ambos_lados():
    a = _PROYECTO + " - 3RA ETAPA"
    assert _etapa_contradice(a, _NOMBRE_OBRA + " - 2DA ETAPA")
    assert not _etapa_contradice(a, _NOMBRE_OBRA + " - III ETAPA")   # misma etapa
    assert not _etapa_contradice(a, _NOMBRE_OBRA)                    # obra calla
    assert not _etapa_contradice(_PROYECTO, _NOMBRE_OBRA + " - 2DA ETAPA")  # cert calla
    # clases distintas no se contradicen entre sí
    assert not _etapa_contradice(a, _NOMBRE_OBRA + " TRAMO 2")


# ── (b) el caso del certificado: 3RA ETAPA contra un registro 2DA ETAPA ───────

def test_certificado_3ra_no_resuelve_contra_la_2da_etapa():
    exp = _exp(" - 3RA ETAPA")
    obra_2da = _obra("2500002", 90001, " - 2DA ETAPA")

    ranked, vetados = _rankear({"a": obra_2da}, exp)
    assert ranked == []                       # no compite: no puede ganar por RUC
    assert [c["veto"] for c in vetados] == ["etapa"]
    assert vetados[0]["veto_etapa"] == ("ETAPA", 3, 2)

    r = resolver(exp, _Consulta([obra_2da]))
    assert r["estado"] == "revision"
    assert r["cui"] is None
    assert "etapa" in r["decision"].lower()
    assert "N° 3" in r["decision"] and "N° 2" in r["decision"]
    # el candidato queda VISIBLE para la cola humana (no se borra la evidencia)
    assert [c["cui"] for c in r["candidatos"]] == ["2500002"]


def test_el_veto_de_etapa_no_lo_exime_el_ruc_del_emisor():
    """A diferencia del rubro: el mismo contratista suele ejecutar varias etapas
    del mismo proyecto, así que su RUC no dice CUÁL de ellas acredita."""
    exp = _exp(" - 3RA ETAPA")
    obra = _obra("2500002", 90001, " - 2DA ETAPA")
    _, vetados = _rankear({"a": obra}, exp)
    assert vetados and vetados[0]["ruc_match"] is True
    assert vetados[0]["veto"] == "etapa"


# ── (c) misma etapa: se resuelve como antes ──────────────────────────────────

def test_misma_etapa_resuelve_igual_que_antes():
    exp = _exp(" - 3RA ETAPA")
    obra = _obra("2500003", 90003, " - 3RA ETAPA")
    ranked, vetados = _rankear({"a": obra}, exp)
    assert vetados == [] and [c["cui"] for c in ranked] == ["2500003"]

    r = resolver(exp, _Consulta([obra]))
    assert r["estado"] == "resuelto" and r["cui"] == "2500003"


def test_con_ambas_etapas_gana_la_del_certificado():
    exp = _exp(" - 3RA ETAPA")
    obras = [_obra("2500002", 90001, " - 2DA ETAPA"),
             _obra("2500003", 90003, " - 3RA ETAPA")]
    r = resolver(exp, _Consulta(obras))
    assert r["estado"] == "resuelto" and r["cui"] == "2500003"


# ── (d) sin etapa en el certificado: no se veta por omisión ──────────────────

def test_certificado_sin_etapa_no_veta_al_candidato_con_etapa():
    exp = _exp()                                    # el cert no declara etapa
    obra = _obra("2500002", 90001, " - 2DA ETAPA")
    ranked, vetados = _rankear({"a": obra}, exp)
    assert vetados == [] and [c["cui"] for c in ranked] == ["2500002"]
    r = resolver(exp, _Consulta([obra]))
    assert r["estado"] == "resuelto" and r["cui"] == "2500002"


def test_registro_sin_etapa_no_se_veta():
    exp = _exp(" - 3RA ETAPA")
    obra = _obra("2500002", 90001)                  # el registro no declara etapa
    ranked, vetados = _rankear({"a": obra}, exp)
    assert vetados == [] and [c["cui"] for c in ranked] == ["2500002"]


# ── (e) CUI citado que apunta a otra etapa ───────────────────────────────────

def test_cui_citado_de_otra_etapa_va_a_revision_con_el_candidato_visible():
    exp = _exp(" - 3RA ETAPA", cui="2500002")
    obra_2da = _obra("2500002", 90001, " - 2DA ETAPA")
    r = resolver(exp, _Consulta([obra_2da]))
    assert r["estado"] == "revision" and r["cui"] is None
    assert r["decision"] == ("el CUI citado corresponde a otra etapa del mismo "
                             "proyecto (N° 3 en el certificado, N° 2 en el registro) "
                             "— confirmar")
    assert [c["cui"] for c in r["candidatos"]] == ["2500002"]


def test_cui_citado_de_la_misma_etapa_sigue_resolviendo():
    exp = _exp(" - 3RA ETAPA", cui="2500003")
    obra = _obra("2500003", 90003, " - 3RA ETAPA")
    r = resolver(exp, _Consulta([obra]))
    assert r["estado"] == "resuelto" and r["cui"] == "2500003"


def test_cotejo_codigo_expone_la_contradiccion_de_etapa():
    obra = _obra("2500002", 90001, " - 2DA ETAPA")
    c = _cotejo_codigo(obra, _PROYECTO + " - 3RA ETAPA", "2500002", {"JUNIN"})
    assert c["contra_etapa"] is True
    # sin etapa declarada en el certificado, la señal queda apagada
    assert _cotejo_codigo(obra, _PROYECTO, "2500002", {"JUNIN"})["contra_etapa"] is False
