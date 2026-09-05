"""
Vía MEF (ADR-010): para un EXPEDIENTE, el Banco de Inversiones del MEF es la
fuente. Si InfoObras no registra ejecución del proyecto (nunca se construyó o no
está indexado), la ficha del MEF compite como candidato y, con nombre casi
idéntico, ubicación no contradictoria y sin rival, RESUELVE. Para experiencias
de OBRA no cambia nada: la obra tiene que existir en InfoObras.

Origen: corrida real de expedientes del 5-sep-2026 — 7 de 8 experiencias «no
detectables» estaban en la base MEF con score 100 y el resolver las descartaba
porque `por_codigo` de InfoObras no devolvía nada.
"""
from __future__ import annotations

from resolucion.cui import CLAVE_TIPO_EVALUACION, resolver


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
    """InfoObras sin nada: ni por nombre ni por código (el proyecto no se ejecutó)."""

    def por_codigo(self, codigo):
        return []

    def buscar(self, nombre):
        return []


def _ficha(cui, nombre, score, dpto="AYACUCHO", prov="HUAMANGA", dist="SAN JUAN BAUTISTA"):
    return {"cui": cui, "snip": "", "nombre": nombre, "ubigeo": "", "dpto": dpto,
            "prov": prov, "dist": dist, "entidad": "SUNARP", "estado_dataset": "ACTIVO",
            "situacion": "", "score": score}


def _exp(proyecto, ubicacion, tipo="expedientes"):
    return {"proyecto": proyecto, "ubicacion": ubicacion, "entidad_emisora": "AYEP EIRL",
            "fecha_inicial": "2023-10-13", "fecha_final": "2026-06-27",
            CLAVE_TIPO_EVALUACION: tipo}


NOMBRE_MEF = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS REGISTRALES DE LA OFICINA "
              "REGISTRAL AYACUCHO, SEDE DE LA ZONA REGISTRAL N XIV - SEDE AYACUCHO, "
              "DISTRITO DE SAN JUAN BAUTISTA, PROVINCIA DE HUAMANGA, DEPARTAMENTO DE AYACUCHO")
PROYECTO = ("Elaboración del Expediente Técnico del proyecto: MEJORAMIENTO Y AMPLIACIÓN DE "
            "LOS SERVICIOS REGISTRALES DE LA OFICINA REGISTRAL DE AYACUCHO, SEDE DE LA ZONA "
            "REGISTRAL N° XIV — SEDE AYACUCHO, EN LA LOCALIDAD DE SAN JUAN BAUTISTA, DISTRITO "
            "DE SAN JUAN BAUTISTA, PROVINCIA DE HUAMANGA, DEPARTAMENTO DE AYACUCHO")
UBICACION = ("Localidad y Distrito de San Juan Bautista, Provincia de Huamanga, "
             "Departamento de Ayacucho")
ESPINAR = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS REGISTRALES DE LA OFICINA REGISTRAL "
           "ESPINAR DE LA ZONA REGISTRAL N X - SEDE CUSCO, DISTRITO DE ESPINAR")


def test_expediente_sin_ejecucion_en_infoobras_resuelve_por_mef():
    base = _Base([_ficha("2412686", NOMBRE_MEF, 100.0),
                  _ficha("2412695", ESPINAR, 81.0, dpto="CUSCO", prov="ESPINAR", dist="ESPINAR")])
    r = resolver(_exp(PROYECTO, UBICACION), _Consulta(), base=base)
    assert r["estado"] == "resuelto", r
    assert r["via"] == "MEF" and r["cui"] == "2412686"
    assert r["obra"]["obra_id"] is None          # no hay obra de InfoObras detrás
    assert "Banco de Inversiones" in r["decision"]


def test_experiencia_de_obra_no_usa_la_ficha_mef_como_obra():
    base = _Base([_ficha("2412686", NOMBRE_MEF, 100.0)])
    exp = _exp("Supervisión de la obra: " + NOMBRE_MEF, UBICACION, tipo="obras")
    r = resolver(exp, _Consulta(), base=base)
    assert r["estado"] != "resuelto"
    assert r.get("via") != "MEF"


def test_nombre_oficial_flojo_va_a_revision_con_la_ficha_visible():
    base = _Base([_ficha("2412686", NOMBRE_MEF, 88.0)])
    r = resolver(_exp(PROYECTO, UBICACION), _Consulta(), base=base)
    assert r["estado"] == "revision", r
    assert any(c["cui"] == "2412686" for c in r["candidatos"])
    assert "Banco de Inversiones" in r["decision"]


def test_dos_fichas_igual_de_parecidas_no_resuelve():
    base = _Base([_ficha("2412686", NOMBRE_MEF, 97.0),
                  _ficha("2999999", NOMBRE_MEF + " - ETAPA II", 96.0)])
    r = resolver(_exp(PROYECTO, UBICACION), _Consulta(), base=base)
    assert r["estado"] == "revision", r


def test_otra_intervencion_en_el_mismo_lugar_no_resuelve():
    # el certificado es la CONSTRUCCIÓN del colegio; la ficha, una red de alcantarillado
    # en ese colegio: token_set_ratio la puntúa alto, la cobertura/rubro la frena
    exp = _exp("Expediente Técnico Definitivo: CONSTRUCCION Y EQUIPAMIENTO DE LA "
               "INSTITUCION EDUCATIVA N° 14325 NIVEL PRIMARIA, DISTRITO DE FRIAS, "
               "PROVINCIA DE AYABACA, DPTO. PIURA",
               "Distrito de Frías, Provincia de Ayabaca, Dpto. Piura")
    base = _Base([_ficha("2556981", "RENOVACION DE RED DE ALCANTARILLADO; EN EL(LA) IE 14325 "
                         "- FRIAS EN LA LOCALIDAD FRIAS, DISTRITO DE FRIAS, PROVINCIA AYABACA, "
                         "DEPARTAMENTO PIURA", 96.0, dpto="PIURA", prov="AYABACA", dist="FRIAS")])
    r = resolver(exp, _Consulta(), base=base)
    assert not (r["estado"] == "resuelto" and r["via"] == "MEF"), r
