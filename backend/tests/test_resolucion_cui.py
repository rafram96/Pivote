"""
Tests offline de la resolución de CUI: detección de ubicación (departamento) y
penalización de scoring. Sin red.
"""
from __future__ import annotations

import itertools

from resolucion.cui import _puntuar, es_aplicable, norm, resolver, ubicacion


def test_ubicacion_no_confunde_ica_dentro_de_huancavelica():
    # "ICA" es substring de "HUANCAVEL-ICA": con `d in cola` se colaba como depto
    # falso. El match por límite de palabra lo evita.
    assert ubicacion("Mejoramiento del Puesto de Salud Lircay, Huancavelica") == {
        "HUANCAVELICA"}


def test_ubicacion_expande_alias_hvca():
    assert ubicacion("Puesto de Salud Lircay, HVCA") == {"HUANCAVELICA"}


def test_ubicacion_detecta_departamento_compuesto():
    assert ubicacion("Centro de Salud Pueblo Nuevo, La Libertad") == {"LA LIBERTAD"}


def test_puntuar_penalizacion_departamental_suave():
    # nombre idéntico pero departamento distinto del hint: penalización SUAVE
    # (-10) para no enterrar a la obra correcta registrada en otra sede.
    cand = {"nombrObra": "PUESTO DE SALUD DE LIRCAY", "nombrDepartamento": "LIMA"}
    sc = _puntuar(cand, norm("Puesto de Salud de Lircay"), {"HUANCAVELICA"}, None)
    assert sc == 95.0  # _sim 100 − 10 (depto distinto) + 5 (es de salud)


def test_puntuar_boost_mismo_departamento():
    cand = {"nombrObra": "PUESTO DE SALUD DE LIRCAY", "nombrDepartamento": "HUANCAVELICA"}
    sc = _puntuar(cand, norm("Puesto de Salud de Lircay"), {"HUANCAVELICA"}, None)
    assert sc == 120.0  # _sim 100 + 15 (mismo depto) + 5 (salud)


# ── Determinismo: el mismo conjunto de obras, en cualquier orden, resuelve igual ─

class _FakeConsulta:
    """Devuelve SIEMPRE las mismas obras (en el orden dado) para forzar el PASO 2
    por nombre y simular el orden inestable que entrega el portal."""

    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return []  # sin código → el resolver va por nombre

    def buscar(self, nombre):
        return list(self.obras)


def _obra(cui, obra_id, nombre, depto="TACNA"):
    return {"codUniqInv": cui, "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


_EXP = {"proyecto": "Mejoramiento del Hospital Regional de Tacna, Tacna",
        "fecha_inicial": "2019-01-01"}
_NOMBRE = "MEJORAMIENTO DEL HOSPITAL REGIONAL DE TACNA"


def test_resolver_determinista_entre_cuis_con_score_igual():
    # 3 CUIs distintos con nombre/departamento idénticos → mismo score. El
    # desempate por menor CUI debe elegir SIEMPRE el mismo, sin importar el orden.
    obras = [_obra("2000003", 80, _NOMBRE), _obra("2000001", 50, _NOMBRE),
             _obra("2000002", 65, _NOMBRE)]
    elegidos = {resolver(_EXP, _FakeConsulta(list(p)))["cui"]
                for p in itertools.permutations(obras)}
    assert elegidos == {"2000001"}  # el CUI menor, en las 6 permutaciones


def test_resolver_determinista_mismo_cui_varias_obras():
    # Mismo CUI con dos registros (distinto codigoObra) e igual score → el
    # representante debe ser SIEMPRE el de menor obra_id.
    obras = [_obra("2000003", 80, _NOMBRE), _obra("2000003", 70, _NOMBRE)]
    obra_ids = set()
    for p in itertools.permutations(obras):
        r = resolver(_EXP, _FakeConsulta(list(p)))
        assert r["cui"] == "2000003"
        obra_ids.add(r["obra"]["obra_id"])
    assert obra_ids == {70}  # menor obra_id como representante, en ambos órdenes


# ── CUI exacto es autoritativo aunque el nombre difiera ──────────────────────

class _FakeConCodigo:
    """Devuelve la obra al buscar POR CÓDIGO (ejercita el PASO 0 / CUI)."""

    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return list(self.obras)

    def buscar(self, nombre):
        return []


class _FakeConRango:
    """buscar() devuelve dos obras HOMÓNIMAS (mismo nombre/depto → mismo score);
    rango() da valorizaciones distintas: la vieja NO solapa el certificado, la
    correcta SÍ. Ejercita el re-rank por solape del PASO 2."""
    def __init__(self, obras, rangos):
        self.obras = obras
        self.rangos = rangos

    def por_codigo(self, codigo):
        return []

    def buscar(self, nombre):
        return list(self.obras)

    def rango(self, obra_id):
        return self.rangos.get(obra_id, (None, None))


def test_resolver_prefiere_la_obra_que_solapa_valorizaciones():
    # Regresión (caso obra 4653): dos obras con nombre idéntico; sin el re-rank gana
    # la de menor CUI (desempate) aunque sus valorizaciones sean VIEJAS y no cubran
    # el certificado. Con el re-rank, gana la que SOLAPA el periodo del cert.
    from datetime import date
    exp = {"proyecto": "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS",
           "fecha_inicial": "2022-06-01", "fecha_final": "2023-01-31"}
    vieja = _obra("1111111", 100, "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS")
    nueva = _obra("2222222", 200, "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS")
    rangos = {100: (date(2015, 1, 1), date(2016, 4, 1)),     # vieja: NO solapa
              200: (date(2022, 1, 1), date(2023, 3, 1))}     # nueva: SÍ solapa
    r = resolver(exp, _FakeConRango([vieja, nueva], rangos))
    assert r["estado"] == "resuelto"
    assert r["cui"] == "2222222", r     # la que solapa, pese a tener CUI mayor


def test_resolver_cui_exacto_resuelve_aunque_nombre_difiera():
    # Regresión (caso Pichanaki/Fortaleza): el certificado cita un COMPONENTE
    # ("C.S. Fortaleza") dentro de la red integrada; la obra en InfoObras tiene
    # otro nombre, pero el CUI coincide EXACTO → debe RESOLVER (CUI autoritativo),
    # no quedar en revisión por el chequeo de tokens del nombre.
    exp = {"cui": "2466824", "fecha_inicial": "2025-05-15", "fecha_final": "2025-09-01",
           "proyecto": "SUPERVISIÓN DE LA CONSTRUCCIÓN DEL NUEVO CENTRO DE SALUD FORTALEZA"}
    obra = _obra("2466824", 517400,
                 "MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL PRIMER NIVEL "
                 "DE ATENCION DE LA RED INTEGRADA DE SALUD ATE VITARTE", depto="LIMA")
    r = resolver(exp, _FakeConCodigo([obra]))
    assert r["estado"] == "resuelto", r          # antes caía en 'revision'
    assert r["cui"] == "2466824"
    assert r["obra"]["obra_id"] == 517400


# ── Alcance: CUALQUIER rubro de obra; consultorías/expedientes → revisión manual ──

def test_es_aplicable_acepta_cualquier_rubro_de_obra():
    # obras fuera de salud/educación ahora SÍ se cruzan (ampliado 2026-07-02)
    assert es_aplicable("Mejoramiento de la carretera Lima - Canta")
    assert es_aplicable("Instalación del sistema de agua potable de X")
    assert es_aplicable("Mejoramiento de los servicios de salud del hospital Y")
    assert es_aplicable("Construcción de la I.E. N° 044")


def test_es_aplicable_excluye_consultorias_y_expedientes():
    assert not es_aplicable("Elaboración del expediente técnico del proyecto X")
    assert not es_aplicable("Consultoría para la elaboración de cuatro expedientes")
    assert not es_aplicable("Supervisión del estudio definitivo del contrato")
    assert not es_aplicable("Reformulación del expediente técnico de la obra Z")


def test_resolver_consultoria_va_a_revision_con_motivo_claro():
    # un ESTUDIO (sin obra física) → 'na' con motivo claro, no 'sin candidato'
    exp = {"proyecto": "Elaboración del expediente técnico de mejoramiento vial",
           "fecha_inicial": "2022-01-01"}
    r = resolver(exp, _FakeConCodigo([]))
    assert r["estado"] == "na"
    assert r["via"] == "CONSULTORIA"
    assert "expediente" in r["decision"].lower() or "consultor" in r["decision"].lower()
