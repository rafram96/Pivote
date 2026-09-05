"""
Un CUI mal transcrito no debe adquirir autoridad oficial.

El código citado en el certificado es evidencia fuerte, pero lo leyó un OCR o
un modelo: un dígito cambiado cae con facilidad sobre OTRO CUI real (los
espacios CUI y SNIP además se solapan). Antes, un código exacto resolvía aunque
el nombre no compartiera ningún término y solo lo frenaba la contradicción
TRIPLE de #59 (nombre + departamento + rubro a la vez). En sub-obras se
aceptaba cualquier registro sin cotejo.

Regla nueva (abstención pura, jamás promueve): sin ningún término del nombre
en común Y (solo calzó contra un SNIP, o contradice la ubicación o el rubro que
el certificado declara) → revisión con la obra del código a la vista.

Los casos documentados como CORRECTOS siguen resolviendo: Fortaleza (componente
de una red integrada, sin departamento declarado, mismo rubro) y COAR (afinidad
de nombre ≥ 1 aunque la ubicación difiera).
"""
from __future__ import annotations

from resolucion.cui import (
    _codigo_dudoso, _cotejo_codigo, fuente_camino, resolver, resolver_obras,
)


def _obra(cui, obra_id, nombre, depto="TACNA", snip=""):
    return {"codUniqInv": cui, "codSnip": snip, "codigoObra": obra_id,
            "nombrObra": nombre, "nombrDepartamento": depto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


class _PorCodigo:
    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return list(self.obras)

    def buscar(self, nombre):
        return []


# ── cotejo puro ──────────────────────────────────────────────────────────────

def test_cotejo_detecta_sin_afinidad_contradiccion_y_snip():
    o = _obra("2000001", 1, "CONSTRUCCION DE VEREDAS EN FERREÑAFE", depto="LAMBAYEQUE")
    c = _cotejo_codigo(o, "Mejoramiento del Hospital de Yanahuanca, Pasco", "2000001",
                       {"PASCO"})
    assert c["sin_afinidad"] and c["contra_dep"] and c["contra_rubro"]
    assert c["solo_snip"] is False
    # el mismo código calzando contra el SNIP de la obra
    o2 = _obra("2999999", 1, "CONSTRUCCION DE VEREDAS EN FERREÑAFE", snip="2000001")
    assert _cotejo_codigo(o2, "Mejoramiento del Hospital de Yanahuanca", "2000001", set())["solo_snip"]


def test_codigo_dudoso_solo_con_sin_afinidad_mas_una_contradiccion_o_snip():
    assert _codigo_dudoso({"sin_afinidad": False, "contra_dep": True,
                           "contra_rubro": True, "solo_snip": True}) is None
    assert _codigo_dudoso({"sin_afinidad": True, "contra_dep": False,
                           "contra_rubro": False, "solo_snip": False}) is None
    assert "SNIP" in _codigo_dudoso({"sin_afinidad": True, "contra_dep": False,
                                      "contra_rubro": False, "solo_snip": True})
    assert "departamento" in _codigo_dudoso({"sin_afinidad": True, "contra_dep": True,
                                              "contra_rubro": False, "solo_snip": False})
    assert "rubro" in _codigo_dudoso({"sin_afinidad": True, "contra_dep": False,
                                       "contra_rubro": True, "solo_snip": False})


# ── Paso 0 · experiencia con CUI citado ──────────────────────────────────────

def test_cui_citado_sobre_otra_obra_en_otro_departamento_va_a_revision():
    # un dígito mal leído cayó sobre un hospital real de otro departamento, mismo rubro
    exp = {"cui": "2466825", "proyecto": "Mejoramiento del Hospital de Yanahuanca",
           "ubicacion": "Yanahuanca, Daniel Alcides Carrión, Pasco",
           "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"}
    obra = _obra("2466825", 900, "MEJORAMIENTO DEL HOSPITAL DE APOYO DE CHULUCANAS",
                 depto="PIURA")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "revision", r
    assert r["cui"] is None
    assert r["candidatos"][0]["cui"] == "2466825"      # la obra del código queda a la vista
    assert "dígito mal leído" in r["decision"]


def test_cui_citado_que_solo_calza_con_un_snip_va_a_revision():
    exp = {"cui": "2000001", "proyecto": "Mejoramiento del Hospital de Yanahuanca",
           "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"}
    obra = _obra("2999999", 901, "CONSTRUCCION DE VEREDAS EN EL DISTRITO DE FERREÑAFE",
                 depto="LAMBAYEQUE", snip="2000001")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "revision", r
    assert "SNIP" in r["decision"]


def test_fortaleza_sigue_resolviendo_componente_sin_departamento_declarado():
    # Regresión del caso real Pichanaki/Fortaleza (test histórico): sin
    # departamento en el cert y mismo rubro no hay contradicción → resuelve.
    exp = {"cui": "2466824", "fecha_inicial": "2025-05-15", "fecha_final": "2025-09-01",
           "proyecto": "SUPERVISIÓN DE LA CONSTRUCCIÓN DEL NUEVO CENTRO DE SALUD FORTALEZA"}
    obra = _obra("2466824", 517400,
                 "MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL PRIMER NIVEL "
                 "DE ATENCION DE LA RED INTEGRADA DE SALUD ATE VITARTE", depto="LIMA")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "resuelto", r
    assert r["cui"] == "2466824"


def test_coar_sigue_resolviendo_con_afinidad_de_nombre_aunque_cambie_la_region():
    exp = {"cui": "2429909", "proyecto": "Supervisión del COAR Cusco",
           "ubicacion": "Cusco, Cusco, Cusco",
           "fecha_inicial": "2019-01-01", "fecha_final": "2020-01-01"}
    obra = _obra("2429909", 77, "CREACION DEL SERVICIO EDUCATIVO ESPECIALIZADO COAR "
                 "EN LA REGION PASCO", depto="PASCO")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "resuelto", r


# ── sub-obras por código ─────────────────────────────────────────────────────

def test_subobra_por_codigo_con_obra_contradictoria_se_abstiene_con_candidato():
    madre = {"proyecto": "Paquete de puestos de salud", "entidad_contratante": "GORE PASCO",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"}
    subs = [{"proyecto": "Puesto de Salud de Huariaca, Pasco", "cui": "2100001"}]
    obra = _obra("2100001", 5, "MEJORAMIENTO DE LA CARRETERA VECINAL TRAMO A-B", depto="LORETO")
    out = resolver_obras(subs, _PorCodigo([obra]), exp_madre=madre)
    assert out[0]["estado"] == "revision", out
    assert out[0]["cui"] is None
    assert out[0]["candidatos"][0]["cui"] == "2100001"


def test_subobra_por_codigo_coherente_sigue_resolviendo():
    madre = {"proyecto": "Paquete de puestos de salud", "entidad_contratante": "GORE PASCO",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"}
    subs = [{"proyecto": "Puesto de Salud de Huariaca", "cui": "2100002"}]
    obra = _obra("2100002", 6, "MEJORAMIENTO DEL PUESTO DE SALUD HUARIACA", depto="PASCO")
    out = resolver_obras(subs, _PorCodigo([obra]), exp_madre=madre)
    assert out[0]["estado"] == "resuelto", out
    assert out[0]["cui"] == "2100002"


# ── auditabilidad del camino (#50) ───────────────────────────────────────────

def test_fuente_camino_sigue_la_precedencia():
    exp = {"proyecto": "X", "cargo_ocupado": "Y"}
    assert fuente_camino(exp, "expedientes") == "declarado"
    assert fuente_camino({**exp, "_tipo_evaluacion": "obras"}) == "declarado"
    assert fuente_camino(exp, None, forzar=True) == "forzado"
    assert fuente_camino(exp) == "texto"
