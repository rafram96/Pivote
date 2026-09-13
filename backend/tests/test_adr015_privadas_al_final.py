"""
ADR-015 · PRECISIÓN DE ADR-004: la rama de privadas va al final DE VERDAD.

ADR-004 decidió que la clasificación «posible obra privada» corre solo cuando la
resolución pública se agotó SIN candidato fiable. En la práctica la rama pisaba
a candidatos identificados:

  · un certificado cuyo nombre oficial es puro genérico + geografía («HOSPITAL
    REGIONAL EN LA PROVINCIA DE …») no tiene NINGÚN token propio, así que ni la
    compuerta de tokens ni el mínimo `n_hit ≥ 1` de la vía PROBABLE pueden
    cumplirse nunca, y la experiencia caía hasta la rama de privadas aunque un
    solo CUI llevara su nombre palabra por palabra y la ubicación coincidiera;
  · y el fuzzy contra el catálogo de entidades no reconocía a la contratante
    escrita con guion («GOBIERNO REGIONAL LIMA-PROVINCIAS» = 89,5) aunque la
    ficha MEF del propio candidato dijera «GOBIERNO REGIONAL LIMA».

Aquí se prueban las dos precisiones. **El umbral 90 del catálogo no baja**: lo
que se suma es la entidad de la ficha MEF del candidato ganador, que es
evidencia de identidad y no de vocabulario.

CUI, entidades y nombres INVENTADOS: el repo es público.
"""
from __future__ import annotations

from rapidfuzz import fuzz

from resolucion.cui import (CLAVE_TIPO_EVALUACION, _entidad_publica_contratante,
                            norm, resolver)

CUI_HOSPITAL = "2077777"
ENTIDAD_FICHA = "GOBIERNO REGIONAL SELVA"
ENTIDAD_CERT = "GOBIERNO REGIONAL SELVA-PROVINCIAS"

NOMBRE_OFICIAL = "CONSTRUCCION Y EQUIPAMIENTO DEL HOSPITAL REGIONAL EN LA PROVINCIA DE MARANOCHA"
PROYECTO = ("Elaboración del Expediente Técnico a nivel de ejecución de obra del ESTUDIO "
            "DEFINITIVO: CONSTRUCCIÓN Y EQUIPAMIENTO DEL HOSPITAL REGIONAL EN LA "
            "PROVINCIA DE MARANOCHA")
UBICACION = "Provincia de Maranocha, Departamento de Loreto"


class _Base:
    """Base MEF de juguete con el catálogo de entidades públicas de ADR-004
    (mismo umbral 90, mismo fuzzy)."""

    CATALOGO = ("GOBIERNO REGIONAL SELVA", "MUNICIPALIDAD PROVINCIAL DE MARANOCHA")

    def __init__(self, fichas=()):
        self.fichas = list(fichas)

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return list(self.fichas[:topn])

    def existe_cui(self, codigo):
        return next((f for f in self.fichas if f["cui"] == str(codigo)), None)

    def es_entidad_publica(self, nombre):
        q = norm(nombre)
        mejor = max((fuzz.token_set_ratio(q, norm(e)) for e in self.CATALOGO),
                    default=0.0)
        return mejor >= 90, round(float(mejor), 1)


class _Consulta:
    def __init__(self, registros=()):
        self._registros = list(registros)

    def buscar(self, nombre):
        return [dict(o) for o in self._registros]

    def por_codigo(self, codigo):
        return [dict(o) for o in self._registros
                if str(o["codUniqInv"]) == str(codigo)]


def _ficha():
    return {"cui": CUI_HOSPITAL, "snip": "", "nombre": NOMBRE_OFICIAL, "ubigeo": "",
            "dpto": "LORETO", "prov": "MARANOCHA", "dist": "MARANOCHA",
            "entidad": ENTIDAD_FICHA, "estado_dataset": "ACTIVO", "situacion": "",
            "score": 100.0}


def _registro():
    return {"codUniqInv": CUI_HOSPITAL, "codSnip": "", "codigoObra": "OB-80001",
            "nombrObra": NOMBRE_OFICIAL, "nombrDepartamento": "LORETO",
            "fechaIniObra": None, "rucEjecutor": "", "rucSupervisor": ""}


def _exp(entidad=ENTIDAD_CERT, proyecto=PROYECTO):
    return {"proyecto": proyecto, "ubicacion": UBICACION,
            "entidad_contratante": entidad, "entidad_emisora": "CONSULTORA DEL SUR SAC",
            "fecha_inicial": "2013-05-02", "fecha_final": "2014-01-20",
            CLAVE_TIPO_EVALUACION: "expedientes"}


def test_el_catalogo_no_reconoce_a_la_contratante_con_guion():
    """Punto de partida: el umbral 90 del catálogo NO baja y sigue sin reconocerla."""
    base = _Base()
    reconocida, score = base.es_entidad_publica(ENTIDAD_CERT)
    assert not reconocida and score < 90, score


def test_la_entidad_de_la_ficha_mef_reconoce_a_la_contratante():
    base = _Base([_ficha()])
    exp = _exp()
    best = {"cui": CUI_HOSPITAL}
    assert _entidad_publica_contratante(exp, best, base)[0], exp
    # sin candidato ganador la señal no existe: la ficha es del CANDIDATO
    assert not _entidad_publica_contratante(_exp(), None, base)[0]


def test_el_ganador_por_nombre_literal_no_lo_pisa_la_rama_de_privadas():
    """12:4 de la auditoría: nombre oficial sin un solo token propio (todo
    genérico y geografía), un único CUI que lo lleva palabra por palabra y la
    ubicación a favor → se resuelve, no se rotula «posible obra privada»."""
    base = _Base([_ficha()])
    r = resolver(_exp(), _Consulta([_registro()]), base=base)
    assert r["estado"] == "resuelto" and r["cui"] == CUI_HOSPITAL, r
    assert not r.get("posible_privada"), r


def test_contratante_societaria_sin_candidato_sigue_siendo_posible_privada():
    """La rama b de ADR-004 sigue viva donde debe: sin candidato público fiable y
    con una contratante que el catálogo no reconoce, la experiencia va a revisión
    marcada `posible_privada`."""
    base = _Base()
    exp = _exp(entidad="CONSTRUCTORA ANDINA S.A.C.",
               proyecto="Construcción del Edificio Corporativo Torre Andina")
    r = resolver(exp, _Consulta(), base=base)
    assert r["estado"] == "revision" and r.get("posible_privada"), r


def test_contratante_societaria_no_se_salva_por_la_ficha_de_un_candidato_ajeno():
    """La precisión no es un pase libre: si la contratante no se parece a la
    entidad de la ficha, la rama de privadas actúa igual."""
    base = _Base([_ficha()])
    exp = _exp(entidad="CONSTRUCTORA ANDINA S.A.C.")
    assert not _entidad_publica_contratante(exp, {"cui": CUI_HOSPITAL}, base)[0]
