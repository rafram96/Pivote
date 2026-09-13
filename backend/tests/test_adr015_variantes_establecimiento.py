"""
ADR-015 · CANDADO DE VARIANTES DEL MISMO ESTABLECIMIENTO.

El Estado inscribe el MISMO establecimiento bajo códigos distintos cuando la
intervención se parte: el plan de contingencia mientras se construye, el saldo
de obra tras una resolución de contrato, la reformulación o actualización del
estudio, un componente o una etapa, o la CONTRATACIÓN del expediente técnico de
otra inversión (registro que se llama como el contrato y cita el código de la
inversión madre). Si el certificado no cita el código ni el número del contrato,
el papel NO dice cuál de los dos acredita: el resolver se abstiene y nombra a
los dos.

Independiente del puntaje A PROPÓSITO: en la corrida real los dos registros del
caso 3:1 de la auditoría quedaron a 2,4 puntos (y el guard de empate los frenó);
la reconstrucción offline los separa por 5,6 y resolvía el principal. Mismo
certificado, dos veredictos según cuánto ruido tuviera el score — la ambigüedad
es del documento, no del puntaje.

CUI y nombres INVENTADOS: el repo es público.
"""
from __future__ import annotations

from resolucion.cui import CLAVE_TIPO_EVALUACION, resolver

CUI_PRINCIPAL = "2044444"
CUI_VARIANTE = "2055555"
CUI_GEMELO_LEJOS = "2066666"

NOMBRE_PRINCIPAL = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD "
                    "VILLA SOLAR, DISTRITO Y PROVINCIA DE PAMPACRUZ, DEPARTAMENTO DE LORETO")
NOMBRE_VARIANTE = ("CONTRATACION DE LA ELABORACION DEL EXPEDIENTE TECNICO DEL PLAN DE "
                   "CONTINGENCIA DEL PROYECTO DE INVERSION PUBLICA: MEJORAMIENTO DE LOS "
                   "SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD VILLA SOLAR, CON "
                   "CODIGO UNICO DE INVERSIONES N 2055555")
PROYECTO = ("Elaboración del Expediente Técnico del Proyecto: MEJORAMIENTO DE LOS "
            "SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD VILLA SOLAR, DISTRITO Y "
            "PROVINCIA DE PAMPACRUZ, DEPARTAMENTO DE LORETO")
UBICACION = "Distrito y Provincia de Pampacruz, Departamento de Loreto"


def _ficha(cui, nombre, score, dpto="LORETO", prov="PAMPACRUZ", dist="PAMPACRUZ"):
    return {"cui": cui, "snip": "", "nombre": nombre, "ubigeo": "", "dpto": dpto,
            "prov": prov, "dist": dist, "entidad": "GOBIERNO REGIONAL LORETO",
            "estado_dataset": "ACTIVO", "situacion": "", "score": score}


def _registro(cui, nombre, obra_id, dpto="LORETO"):
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id,
            "nombrObra": nombre, "nombrDepartamento": dpto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


class _Base:
    def __init__(self, fichas):
        self.fichas = list(fichas)

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return list(self.fichas[:topn])

    def existe_cui(self, codigo):
        return next((f for f in self.fichas if f["cui"] == str(codigo)), None)


class _Consulta:
    def __init__(self, registros):
        self._registros = list(registros)

    def buscar(self, nombre):
        return [dict(o) for o in self._registros]

    def por_codigo(self, codigo):
        return [dict(o) for o in self._registros
                if str(o["codUniqInv"]) == str(codigo)]


def _exp(proyecto=PROYECTO, ubicacion=UBICACION):
    return {"proyecto": proyecto, "ubicacion": ubicacion,
            "entidad_emisora": "CONSULTORA DEL NORTE EIRL",
            "fecha_inicial": "2021-03-01", "fecha_final": "2021-11-30",
            CLAVE_TIPO_EVALUACION: "expedientes"}


def test_la_variante_del_mismo_establecimiento_manda_a_revision():
    base = _Base([_ficha(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, 99.0),
                  _ficha(CUI_VARIANTE, NOMBRE_PRINCIPAL, 92.0)])
    consulta = _Consulta([_registro(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, "OB-70001"),
                          _registro(CUI_VARIANTE, NOMBRE_VARIANTE, "OB-70002")])
    r = resolver(_exp(), consulta, base=base)
    assert r["estado"] == "revision", r
    # el motivo nombra a LOS DOS candidatos, y dice cuál es la variante
    assert CUI_PRINCIPAL in r["decision"] and CUI_VARIANTE in r["decision"], r
    assert "contingencia" in r["decision"].lower(), r
    assert {c["cui"] for c in r["candidatos"]} >= {CUI_PRINCIPAL, CUI_VARIANTE}, r


def test_el_candado_no_mira_la_distancia_de_puntaje():
    """Con 60 puntos de diferencia (el guard de empate de ADR-005 §2 ni se asoma)
    o con 0,1, el candado dice lo mismo: la ambigüedad es del documento, no del
    puntaje. Es la razón por la que el caso real salía resuelto en el replay
    (5,6 puntos de separación) y a revisión en producción (2,4)."""
    from resolucion.cui import _rival_variante

    best = {"cui": CUI_PRINCIPAL, "score": 140.0, "nombre_literal": True,
            "geo_match": True, "full": NOMBRE_PRINCIPAL}
    lejos = {"cui": CUI_VARIANTE, "score": 80.0, "nombre_literal": True,
             "geo_match": True, "full": NOMBRE_VARIANTE + " " + NOMBRE_PRINCIPAL}
    cerca = dict(lejos, score=139.9)
    for otro in (lejos, cerca):
        hallado = _rival_variante(best, [best, otro], _exp())
        assert hallado is not None, otro
        rival, marca, cui_variante = hallado
        assert rival["cui"] == CUI_VARIANTE and cui_variante == CUI_VARIANTE
        assert "CONTINGENCIA" in marca


def test_dos_establecimientos_parecidos_en_provincias_distintas_siguen_resolviendo():
    """Negativa: el homónimo de otra provincia lo aparta el veto de ubicación de
    siempre; el candado de variantes no se mete y la experiencia resuelve."""
    lejos = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD "
             "VILLA SOLAR, DISTRITO Y PROVINCIA DE MARANOCHA, DEPARTAMENTO DE LORETO "
             "- SALDO DE OBRA")
    base = _Base([_ficha(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, 99.0),
                  _ficha(CUI_GEMELO_LEJOS, lejos, 95.0, prov="MARANOCHA",
                         dist="MARANOCHA")])
    consulta = _Consulta([_registro(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, "OB-70001"),
                          _registro(CUI_GEMELO_LEJOS, lejos, "OB-70003")])
    r = resolver(_exp(), consulta, base=base)
    assert r["estado"] == "resuelto" and r["cui"] == CUI_PRINCIPAL, r


def test_si_el_certificado_declara_la_variante_el_candado_no_opina():
    """El certificado que dice «saldo de obra» ya eligió: de la fase se ocupa
    `_checkpoint_fase`, no este candado."""
    saldo = NOMBRE_PRINCIPAL + " - SALDO DE OBRA"
    base = _Base([_ficha(CUI_VARIANTE, NOMBRE_PRINCIPAL, 99.0),
                  _ficha(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, 95.0)])
    consulta = _Consulta([_registro(CUI_VARIANTE, saldo, "OB-70002"),
                          _registro(CUI_PRINCIPAL, NOMBRE_PRINCIPAL, "OB-70001")])
    proyecto = ("Elaboración del Expediente Técnico del SALDO DE OBRA del Proyecto: "
                + NOMBRE_PRINCIPAL)
    r = resolver(_exp(proyecto=proyecto), consulta, base=base)
    assert "variante del otro" not in str(r.get("decision") or ""), r
