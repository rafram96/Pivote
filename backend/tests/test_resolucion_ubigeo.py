"""
Tests offline del VETO DE UBICACIÓN (F8 + ADR-013). Sin red.

La auditoría del job c9c769976750 halló 4 CUIs mal resueltos con patrón común:
candidato del mismo departamento pero OTRA provincia/distrito (San Agustín→El
Tambo, Jaén→Magdalena del Mar, Jauja→Tarma). Reglas:
  - contradicción de PROVINCIA (ambas partes declaradas) → VETO (visible en
    candidatos de revisión), con exención por ruc_match;
  - contradicción de DEPARTAMENTO declarado con intención geográfica en ambos
    lados → VETO (ADR-013, caso Tarapoto del job 36d710f27694);
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


# ── ADR-013 · VETO DE DEPARTAMENTO ──────────────────────────────────────────
# ADR-005 excluía el departamento porque no DESEMPATA homónimos (viven en el
# mismo). Estos tests fijan la precisión de esa regla: el departamento sigue sin
# desempatar, pero cuando está DECLARADO en ambos lados y se CONTRADICE, veta —
# igual que la provincia.

# Caso real que lo motiva: job 36d710f27694, prof 1 exp 1, folio 119. El
# certificado documenta la construcción del Hospital de EsSalud de Tarapoto
# (San Martín, 2012-2014, S/1'445,335.70, 11 525 m²) y el resolver lo dio por
# "establecimiento verificado por nombre" contra el CUI 2405647: instalación de
# servicios de tomografía en Puerto Maldonado (Madre de Dios, 2016, S/415,342).
# "Ciudad de Tarapoto" no calza el patrón `provincia de X` (Tarapoto es distrito
# de la provincia de San Martín), así que el veto de provincia quedaba mudo.
TARAPOTO = {
    "proyecto": "HOSPITAL DE ESSALUD",
    "cui": None,
    "ubicacion": "Ciudad de Tarapoto, Departamento de San Martin",
    "entidad_contratante": ("ESSALUD (supervision encomendada mediante la "
                            "Organizacion Internacional para las Migraciones - "
                            "OIM, en representacion de ESSALUD)"),
    "entidad_emisora": "CONSORCIO SUPERVISOR HOSPITAL TARAPOTO",
    "ruc_emisor": "20544148380",
    "fecha_inicial": "2012-10-26",
    "fecha_final": "2014-02-15",
    "monto_contrato_soles": 1445335.7,
    "area_construida_m2": 11525.02,
}
OBRA_TOMOGRAFIA = {
    "codUniqInv": "2405647", "codigoObra": 33793,
    "nombrObra": ("INSTALACION DE LOS SERVICIOS DE TOMOGRAFIA EN LA UPSS AYUDA AL "
                  "DIAGNOSTICO Y TRATAMIENTO DEL HOSPITAL I VICTOR ALFREDO LAZO "
                  "PERALTA DE ESSALUD - PUERTO MALDONADO, DISTRITO DE TAMBOPATA - "
                  "PROVINCIA DE TAMBOPATA - DEPARTAMENTO DE MADRE DE DIOS"),
    "nombrDepartamento": "MADRE DE DIOS",
}
FICHA_TOMOGRAFIA = {"cui": "2405647", "nombre": OBRA_TOMOGRAFIA["nombrObra"],
                    "dpto": "MADRE DE DIOS", "prov": "TAMBOPATA",
                    "dist": "TAMBOPATA", "entidad": "SEGURO SOCIAL DE SALUD",
                    "estado_dataset": "CERRADA"}


def test_caso_tarapoto_no_resuelve_al_cui_de_madre_de_dios():
    """El caso que motiva ADR-013: con los datos EXACTOS del job, el resolver no
    puede devolver `resuelto` con el CUI 2405647. Debe vetar o ir a revisión, y en
    cualquier caso dejar el candidato VISIBLE para el evaluador."""
    base = _Base({"2405647": FICHA_TOMOGRAFIA})
    r = resolver(dict(TARAPOTO), _Consulta([OBRA_TOMOGRAFIA]), base=base)
    assert r["estado"] != "resuelto", r
    assert r["cui"] != "2405647"
    assert r["cui"] is None
    # nunca un descarte silencioso: el candidato apartado se muestra
    assert "2405647" in {c["cui"] for c in r["candidatos"]}


def test_caso_tarapoto_la_senal_que_faltaba_es_el_departamento():
    """Aísla la señal: sobre los datos EXACTOS del certificado, la provincia no se
    declara ("Ciudad de Tarapoto" no calza `provincia de X` porque Tarapoto es
    distrito) y por eso el veto de provincia quedaba mudo; el departamento sí está
    declarado en ambos lados y se contradice."""
    sig = ubigeo_cert(dict(TARAPOTO))
    assert sig["depto_declarado"] == {"SAN MARTIN"}
    assert sig["prov"] == set()          # ← por esto el veto de provincia no actuó
    prov_c, _dist_c, dep_c = _ubigeo_contra(sig, FICHA_TOMOGRAFIA)
    assert (prov_c, dep_c) == (False, True)
    # misma obra registrada en el departamento que declara el cert → sin contradicción
    ficha_sm = dict(FICHA_TOMOGRAFIA, dpto="SAN MARTIN", prov="SAN MARTIN",
                    dist="TARAPOTO")
    assert _ubigeo_contra(sig, ficha_sm) == (False, False, False)


def test_veto_de_departamento_aislado_del_candado_de_nombre():
    """El veto de departamento actúa por sí solo, sobre un nombre que SÍ tiene
    término propio (MOYOBAMBA) y por lo tanto no dispara el candado de nombre
    genérico: solo cambia el departamento de la ficha MEF entre los dos casos."""
    proyecto = "MEJORAMIENTO DEL HOSPITAL DE ESSALUD DE MOYOBAMBA"
    exp = {"proyecto": proyecto, "cui": None,
           "ubicacion": "Moyobamba, Departamento de San Martin"}
    obra = {"codUniqInv": "2900020", "codigoObra": 20, "nombrObra": proyecto,
            "nombrDepartamento": "SAN MARTIN"}
    ok = {"cui": "2900020", "nombre": proyecto, "dpto": "SAN MARTIN",
          "prov": "MOYOBAMBA", "dist": "MOYOBAMBA"}
    r_ok = resolver(dict(exp), _Consulta([obra]), base=_Base({"2900020": ok}))
    assert r_ok["estado"] == "resuelto" and r_ok["cui"] == "2900020", r_ok
    malo = dict(ok, dpto="MADRE DE DIOS", prov="TAMBOPATA", dist="TAMBOPATA")
    r_malo = resolver(dict(exp), _Consulta([obra]), base=_Base({"2900020": malo}))
    assert r_malo["estado"] == "revision" and r_malo["cui"] is None, r_malo
    assert "2900020" in {c["cui"] for c in r_malo["candidatos"]}
    assert "departamento" in r_malo["decision"]


def test_homonimos_del_mismo_departamento_no_cambian_por_el_veto_nuevo():
    """NO-REGRESIÓN de ADR-005: el departamento sigue sin desempatar homónimos.
    Dos CUIs con nombre idéntico en el MISMO departamento que el certificado se
    comportan igual que antes (guard de empate → revisión), y ninguno se aparta
    por departamento."""
    obra_a = dict(OBRA, codUniqInv="2900001", codigoObra=111)
    obra_b = dict(OBRA, codUniqInv="2900002", codigoObra=222)
    fichas = {c: {"cui": c, "nombre": PROYECTO, "dpto": "JUNIN",
                  "prov": "HUANCAYO", "dist": "SAN AGUSTIN DE CAJAS"}
              for c in ("2900001", "2900002")}
    r = resolver(_exp(), _Consulta([obra_a, obra_b]), base=_Base(fichas))
    assert r["estado"] == "revision"          # ambigüedad de homónimos, como antes
    assert {c["cui"] for c in r["candidatos"]} == {"2900001", "2900002"}
    # y el motivo sigue siendo el de homónimos, no uno de ubicación
    assert "hom" in r["decision"].lower()


def test_departamento_contradictorio_veta():
    base = _Base({"2900001": {"cui": "2900001", "nombre": PROYECTO,
                              "dpto": "AYACUCHO", "prov": "HUAMANGA",
                              "dist": "AYACUCHO"}})
    exp = dict(_exp(), ubicacion="San Agustin de Cajas, Huancayo, Junin")
    r = resolver(exp, _Consulta([OBRA]), base=base)
    assert r["estado"] == "revision"
    assert r["cui"] is None
    assert "2900001" in {c["cui"] for c in r["candidatos"]}


def test_ruc_match_exento_del_veto_de_departamento():
    """NO-REGRESIÓN de ADR-005: `ruc_match` exime de TODO veto de ubicación, y el
    de departamento no es la excepción. Mismos datos del caso Tarapoto, pero con el
    RUC del emisor figurando como ejecutor de la obra."""
    obra = dict(OBRA_TOMOGRAFIA, rucEjecutor="20544148380")
    r = resolver(dict(TARAPOTO), _Consulta([obra]),
                 base=_Base({"2405647": FICHA_TOMOGRAFIA}))
    assert r["estado"] == "resuelto" and r["via"] == "RUC", r
    assert r["cui"] == "2405647"


def test_departamento_ausente_en_un_lado_no_veta():
    """NO-REGRESIÓN de ADR-005: nunca se veta por ausencia de datos. Ni cuando el
    certificado no declara departamento, ni cuando la ficha MEF no lo trae."""
    # a. el certificado no declara departamento (ni ubicación ni rótulo)
    sin_ubic = {k: v for k, v in TARAPOTO.items() if k != "ubicacion"}
    sin_ubic["entidad_contratante"] = "ESSALUD"
    assert ubigeo_cert(sin_ubic)["depto_declarado"] == set()
    assert _ubigeo_contra(ubigeo_cert(sin_ubic),
                          FICHA_TOMOGRAFIA) == (False, False, False)
    # b. la ficha MEF no trae departamento
    ficha_muda = dict(FICHA_TOMOGRAFIA, dpto="", prov="", dist="")
    assert _ubigeo_contra(ubigeo_cert(dict(TARAPOTO)),
                          ficha_muda) == (False, False, False)


def test_departamento_solo_como_nombre_propio_no_veta():
    """El veto exige INTENCIÓN geográfica. Un colegio que se LLAMA como un
    departamento ("I.E. San Martín de Porres", en Lima) no declara San Martín como
    ubicación; vetar ahí sería el falso negativo que ADR-005 temía. Por eso el veto
    mira `depto_declarado` y no `depto`."""
    proyecto = ("MEJORAMIENTO DE LOS SERVICIOS EDUCATIVOS DE LA I.E. 30001 "
                "SAN MARTIN DE PORRES")
    exp = {"proyecto": proyecto, "cui": None}
    sig = ubigeo_cert(exp)
    assert "SAN MARTIN" in sig["depto"]          # el topónimo SÍ aparece…
    assert sig["depto_declarado"] == set()       # …pero no como ubicación declarada
    ficha = {"cui": "2900009", "nombre": proyecto, "dpto": "LIMA",
             "prov": "LIMA", "dist": "SAN MARTIN DE PORRES"}
    # con la señal AMPLIA habría contradicción (LIMA ∉ {SAN MARTIN}); con la
    # declarada, la señal es inerte y el candidato compite
    assert _ubigeo_contra(sig, ficha) == (False, False, False)
    obra = {"codUniqInv": "2900009", "codigoObra": 9, "nombrObra": proyecto,
            "nombrDepartamento": "LIMA"}
    r = resolver(exp, _Consulta([obra]), base=_Base({"2900009": ficha}))
    assert r["estado"] == "resuelto" and r["cui"] == "2900009", r


def test_departamento_declarado_en_el_nombre_del_proyecto_si_veta():
    """La otra cara: el rótulo explícito «departamento de X» dentro del nombre SÍ
    es una declaración geográfica (es como el MEF escribe sus nombres)."""
    proyecto = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL HOSPITAL EL BUEN "
                "PASTOR, DEPARTAMENTO DE SAN MARTIN")
    exp = {"proyecto": proyecto, "cui": None}
    assert ubigeo_cert(exp)["depto_declarado"] == {"SAN MARTIN"}
    ficha = {"cui": "2900010", "nombre": proyecto, "dpto": "LORETO",
             "prov": "MAYNAS", "dist": "IQUITOS"}
    obra = {"codUniqInv": "2900010", "codigoObra": 10, "nombrObra": proyecto,
            "nombrDepartamento": "LORETO"}
    r = resolver(exp, _Consulta([obra]), base=_Base({"2900010": ficha}))
    assert r["estado"] == "revision" and r["cui"] is None, r
    assert "2900010" in {c["cui"] for c in r["candidatos"]}


def test_sin_base_mef_el_veto_de_departamento_es_inerte():
    """Sin base MEF no hay ficha y la señal no existe: el comportamiento histórico
    queda intacto (el veto nunca inventa una contradicción)."""
    r = resolver(dict(TARAPOTO, proyecto="HOSPITAL DE ESSALUD DE TARAPOTO"),
                 _Consulta([OBRA_TOMOGRAFIA]), base=None)
    assert r["estado"] in ("resuelto", "revision")
    assert _ubigeo_contra(ubigeo_cert(dict(TARAPOTO)), None) == (False, False, False)
