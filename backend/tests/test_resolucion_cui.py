"""
Tests offline de la resolución de CUI: detección de ubicación (departamento) y
penalización de scoring. Sin red.
"""
from __future__ import annotations

import itertools

from resolucion.cui import (
    _es_experiencia_expediente, _es_experiencia_privada, _puntuar, _sin_prefijo,
    norm, resolver, resolver_obras, ubicacion)


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


# ── Sin gate de alcance: se resuelve TODO rubro y TODO tipo (obras y consultorías) ──

def test_sin_prefijo_limpia_envoltorio_de_expediente():
    # Recall de experiencias de expediente: el proyecto real está DENTRO del envoltorio
    # de consultoría/expediente/estudio y sí existe en InfoObras. Quitar el envoltorio.
    N = lambda s: norm(_sin_prefijo(s))
    assert N("Expedientes técnicos de Remodelaciones de Oficinas").startswith("REMODELACIONES")
    assert N("Elaboración del Expediente Técnico Definitivo Agroindustrial: "
             "CONSTRUCCIÓN DE UNA PLANTA").startswith("CONSTRUCCION DE UNA PLANTA")
    assert N("ELABORACIÓN DEL EXPEDIENTE TÉCNICO: MEJORAMIENTO de Iluminación").startswith("MEJORAMIENTO")
    assert "ARQUITECT" not in N("Coliseo Cerrado de Arequipa "
                                 "(desarrollo del proyecto - Diseño Arquitectónico)")
    assert N("Elaboración del Expediente Técnico para la Adecuación del hospital").startswith("ADECUACION")


def test_sin_prefijo_no_toca_nombres_de_obra_limpios():
    # No debe recortar nombres reales sin envoltorio (salud/educación/otros).
    N = _sin_prefijo
    for nombre in ["Mejoramiento del Puesto de Salud Lircay, Huancavelica",
                   "Rehabilitación del C.E.P. N° 5027 - ARTURO TIMORAN, LA PERLA - CALLAO",
                   "Ampliación de la Sede Médico Legal de Juliaca"]:
        assert norm(N(nombre)) == norm(nombre), nombre


def test_es_experiencia_expediente_detecta_por_nombre():
    # Solo estas experiencias (sin valorizaciones) aceptan la "Aprobación del proyecto"
    # como respaldo; una obra ejecutada NO.
    ee = _es_experiencia_expediente
    assert ee("Elaboración del Expediente Técnico: Mejoramiento del Hospital X")
    assert ee("Consultoría para la elaboración de expedientes técnicos de saneamiento")
    assert ee("Estudio de preinversión a nivel de perfil del C.S. Y")
    assert ee("Anteproyecto y proyecto arquitectónico del Coliseo Z")
    assert ee("Proyecto definitivo integral del terminal terrestre")
    # obras ejecutadas normales → NO son expediente
    assert not ee("Mejoramiento del Puesto de Salud Lircay, Huancavelica")
    assert not ee("Construcción del nuevo Centro de Salud Fortaleza")
    assert not ee("")
    assert not ee(None)


# ── Casos REALES de la queja del cliente (14-jul): privadas + matches basura ──

def test_privada_no_se_busca_en_infoobras():
    """Queja real: colegios PRIVADOS (Catholic High School, Trinity College)
    matcheaban obras públicas ajenas ('el código es de una carrera'). Si el
    cliente/promotor es privado, NO se busca: via PRIVADA, sin obra, sin revisión."""
    llamadas = []

    class ConsultaEspia:
        def por_codigo(self, c): return []
        def buscar(self, n): llamadas.append(n); return [
            {"nombrObra": "MEJORAMIENTO DE LA CARRETERA X", "codUniqInv": "2999999",
             "codigoObra": 1, "nombrDepartamento": "LIMA"}]

    casos = [
        {"proyecto": "Ampliación de la Infraestructura Educativa de la Institución "
                     "Educativa Particular 'Catholic High School' - Chimbote"},
        {"proyecto": "Mejoramiento de la Infraestructura Educativa en la Institución "
                     "Educativa Privada Trinity College, distrito de Cutervo"},
        {"proyecto": "Ampliación del local institucional",
         "entidad_contratante": "Institución Educativa Particular San José"},
    ]
    for exp in casos:
        r = resolver(exp, ConsultaEspia())
        assert r["estado"] == "na" and r["via"] == "PRIVADA", exp["proyecto"][:40]
        assert r["obra"] is None
    assert llamadas == []          # JAMÁS tocó la búsqueda por nombre


def test_es_experiencia_privada_no_confunde_al_emisor():
    # el EMISOR privado (contratista SAC) es lo normal en obra pública → NO privada
    assert not _es_experiencia_privada({
        "proyecto": "Mejoramiento del C.S. Lircay, Huancavelica",
        "entidad_emisora": "VICTEN CONTRATISTAS S.A.C."})
    assert _es_experiencia_privada({"proyecto": "IEP Santa María de Chota"})
    assert not _es_experiencia_privada({"proyecto": "I.E. N° 105 San Antonio, Huarochirí"})


def test_privada_señal_precisa_sin_falsos_positivos():
    """La palabra 'privada/particular' SUELTA disparaba falsos positivos en obra
    pública (auditoría 14-jul). Debe atarse a un sustantivo de colegio; y I.E.P.
    solo cuenta seguida de NOMBRE, no de número (esas son primarias públicas)."""
    # obra PÚBLICA que solo MENCIONA lo privado → NO debe gatearse
    publicas = [
        "Mejoramiento de la carretera, liberación de predios de PROPIEDAD PRIVADA",
        "Ampliación de redes bajo ASOCIACIÓN PÚBLICO PRIVADA (APP)",
        "Obra por impuestos con INVERSIÓN PRIVADA - colegio nacional",
        "Mejoramiento del servicio educativo I.E.P. N° 70480",   # primaria pública
        "Mejoramiento de la I.E. N° 80672 del C.P. Pilancón",
    ]
    for p in publicas:
        assert not _es_experiencia_privada({"proyecto": p}), p
    # colegio PRIVADO de verdad (spelled-out o sigla + nombre) → SÍ
    privadas = [
        "Institución Educativa Particular Catholic High School",
        "Institución Educativa Privada Trinity College",
        "Construcción de la I.E.P. 'Crezco Jugando' - Trujillo",
        "Institución Educativa de gestión privada San Marcos",
        "C.E.P. San Agustín",
    ]
    for p in privadas:
        assert _es_experiencia_privada({"proyecto": p}), p


def test_publica_con_numero_colegio_distinto_va_a_revision():
    """El gate ignora el número de I.E. (usa solo letras), pero el SCORING lo pesa
    fuerte: una obra con OTRO número de colegio no debe reportarse como match."""
    class ConsultaOtroColegio:
        def por_codigo(self, c): return []
        def buscar(self, n): return [
            {"nombrObra": "AMPLIACION Y MEJORAMIENTO DEL SERVICIO EDUCATIVO EN LA "
                          "I.E. N° 18115 DE LA CAMPIÑA", "codUniqInv": "2068524",
             "codigoObra": 3, "nombrDepartamento": "CAJAMARCA"}]

    exp = {"proyecto": "Ampliación y Mejoramiento del Servicio Educativo en la I.E. "
                       "N° 80672 del C.P. Pilancón",
           "fecha_inicial": "2019-01-01"}
    r = resolver(exp, ConsultaOtroColegio())
    assert r["estado"] == "revision", r    # 80672 ≠ 18115 → no es la obra


def test_match_generico_sin_nombre_propio_va_a_revision():
    """Queja real (KREAR / IE 105 El Ancko): el gate pasaba con palabras genéricas
    (MEJORAMIENTO+INFRAESTRUCTURA+EDUCATIVA) y devolvía obras 'que nada tienen que
    ver'. Ahora esas palabras son stopwords: sin el NOMBRE PROPIO compartido, el
    candidato se rechaza → revisión (no un match basura)."""
    class ConsultaBasura:
        def por_codigo(self, c): return []
        def buscar(self, n): return [
            # obra educativa genérica de OTRO colegio (sin 'KREAR')
            {"nombrObra": "MEJORAMIENTO Y AMPLIACION DE LA INFRAESTRUCTURA EDUCATIVA "
                          "DE LA I.E. JOSE CARLOS MARIATEGUI, DISTRITO DE TRUJILLO",
             "codUniqInv": "2888888", "codigoObra": 9, "nombrDepartamento": "LA LIBERTAD"}]

    exp = {"proyecto": "Mejoramiento y Ampliación de la Infraestructura Educativa "
                       "'KREAR', Distrito de Trujillo - Trujillo - La Libertad",
           "fecha_inicial": "2018-06-01", "fecha_final": "2019-02-28"}
    r = resolver(exp, ConsultaBasura())
    assert r["estado"] == "revision", r     # sin 'KREAR' compartido → NO se acepta
    assert r["cui"] is None


def test_match_con_nombre_propio_si_resuelve():
    # el mismo caso KREAR pero con la obra CORRECTA disponible → resuelve
    class ConsultaBien:
        def por_codigo(self, c): return []
        def buscar(self, n): return [
            {"nombrObra": "MEJORAMIENTO DE LA INFRAESTRUCTURA EDUCATIVA KREAR, "
                          "DISTRITO DE TRUJILLO", "codUniqInv": "2777777",
             "codigoObra": 7, "nombrDepartamento": "LA LIBERTAD"}]

    exp = {"proyecto": "Mejoramiento y Ampliación de la Infraestructura Educativa "
                       "'KREAR', Distrito de Trujillo - La Libertad",
           "fecha_inicial": "2018-06-01"}
    r = resolver(exp, ConsultaBien())
    assert r["estado"] == "resuelto" and r["cui"] == "2777777", r


def test_resolver_obras_multi_cui():
    """Cert MULTI-OBRA (queja real: el cert de Talara lista 7 sub-proyectos, cada
    uno con su CUI, y el sistema no analizaba ninguno). resolver_obras verifica
    CADA código por separado (por_codigo, determinístico), sin adivinar por nombre:
    el que existe → resuelto; el que no (un estudio/plan) → no_encontrado; sin CUI
    → sin_cui. Cachea el CUI repetido."""
    llamadas = []

    class ConsultaObras:
        def por_codigo(self, c):
            llamadas.append(c)
            return {
                "2118617": [{"nombrObra": "CONSTRUCCION ... I.E. 616 SALAVERRY",
                             "codUniqInv": "2118617", "codigoObra": 1,
                             "nombrDepartamento": "PIURA"}],
                "2036812": [{"nombrObra": "MEJORAMIENTO ... I.E 15510",
                             "codUniqInv": "2036812", "codigoObra": 2,
                             "nombrDepartamento": "PIURA"}],
            }.get(c, [])  # 2089754 (Plan Integral) y otros → []

    obras = [
        {"proyecto": "Jorge Chávez", "cui": "2089754"},           # estudio → no figura
        {"proyecto": "Módulo 1516", "cui": "2089754"},            # mismo código (cacheado)
        {"proyecto": "I.E. 616 Salaverry", "cui": "2118617"},     # obra real
        {"proyecto": "Víctor Maldonado", "cui": None},            # sin CUI
        {"proyecto": "I.E. 15510 Gálvez", "cui": "2036812"},      # obra real
    ]
    res = resolver_obras(obras, ConsultaObras())
    assert [r["estado"] for r in res] == [
        "no_encontrado", "no_encontrado", "resuelto", "sin_cui", "resuelto"]
    assert res[2]["obra"]["cui"] == "2118617" and res[2]["cui"] == "2118617"
    assert res[4]["obra"]["nombre_obra"].startswith("MEJORAMIENTO")
    # el CUI repetido (2089754) se consultó UNA sola vez
    assert llamadas.count("2089754") == 1
    # cada entrada conserva SU proyecto (aunque compartan código)
    assert res[0]["proyecto"] == "Jorge Chávez" and res[1]["proyecto"] == "Módulo 1516"


def test_resolver_no_pre_bloquea_consultorias_ni_otros_rubros():
    # Antes un gate mandaba a 'na' lo que no fuera salud/educación (y luego un intento
    # equivocado, las consultorías). Ahora NADA se pre-bloquea: expedientes/consultorías
    # y cualquier rubro se intentan resolver por nombre (están en InfoObras). Con un
    # match fiable, resuelven — no caen en 'na' de arranque.
    exp = {"proyecto": "Elaboración del expediente técnico: " + _NOMBRE.title() + ", Tacna",
           "fecha_inicial": "2019-01-01"}
    r = resolver(exp, _FakeConsulta([_obra("2000001", 50, _NOMBRE)]))
    assert r["estado"] == "resuelto", r
    assert r["via"] != "NA"
