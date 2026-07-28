"""
Tests offline de la resolución de CUI: detección de ubicación (departamento) y
penalización de scoring. Sin red.
"""
from __future__ import annotations

import itertools

from resolucion.cui import (
    _es_experiencia_expediente, _es_experiencia_privada, _es_registro_expediente,
    _exp_derivada, _muni_contradice, _puntuar, _sin_prefijo, norm, resolver,
    resolver_con_dedup, resolver_obras, rubros_mixtos, tokens_distintivos,
    ubicacion, ubigeo_cert)


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


def test_empate_entre_cuis_identicos_abstiene_deterministamente():
    # 3 CUIs distintos con nombre/departamento idénticos → mismo score y ninguna
    # señal dura los distingue: es el caso HOMÓNIMO puro. El guard de empate (F7)
    # NO arriesga un CUI — abstiene (revisión). La DETERMINÍSTICA se conserva: el
    # resultado es el mismo en las 6 permutaciones y el candidato de cabecera es
    # siempre el CUI menor (orden reproducible para la cola humana).
    obras = [_obra("2000003", 80, _NOMBRE), _obra("2000001", 50, _NOMBRE),
             _obra("2000002", 65, _NOMBRE)]
    estados, cabeceras = set(), set()
    for p in itertools.permutations(obras):
        r = resolver(_EXP, _FakeConsulta(list(p)))
        assert r["estado"] == "revision" and r["cui"] is None, r
        estados.add(r["estado"])
        cabeceras.add(r["candidatos"][0]["cui"])
    assert estados == {"revision"}       # abstención estable en las 6 permutaciones
    assert cabeceras == {"2000001"}      # cabecera = CUI menor, orden determinístico


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
    """buscar() devuelve dos obras HOMÓNIMAS; expone rango() para verificar que la
    selección YA NO lo consulta (contador `rango_llamado`). El solape se eliminó de
    la selección: usaba el periodo DECLARADO por el cert —el dato bajo auditoría—
    para reordenar, así un periodo mentiroso podía lavar un homónimo que le cuadre."""
    def __init__(self, obras):
        self.obras = obras
        self.rango_llamado = 0

    def por_codigo(self, codigo):
        return []

    def buscar(self, nombre):
        return list(self.obras)

    def rango(self, obra_id):
        self.rango_llamado += 1
        return (None, None)


def test_solape_no_reordena_la_seleccion():
    # El solape de valorizaciones NO debe reordenar la selección. Dos homónimas:
    # la de MAYOR score de identidad (RUC del emisor calza) NO solapa el periodo
    # declarado; la de MENOR score SÍ solaparía. La elección debe ser la de mayor
    # identidad — nunca cambiar por el solape. Y `rango()` no debe ni consultarse.
    exp = {"proyecto": "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS",
           "fecha_inicial": "2022-06-01", "fecha_final": "2023-01-31",
           "ruc_emisor": "20100010001"}
    # ganadora: mayor identidad (RUC del emisor = ejecutor de la obra → +30)
    ganadora = _obra("1111111", 100, "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS")
    ganadora["rucEjecutor"] = "20100010001"
    # homónima sin RUC: menor score de identidad (sería la que "solaparía" el cert)
    homonima = _obra("2222222", 200, "MEJORAMIENTO DEL PUESTO DE SALUD DE POMACOCHAS")
    fake = _FakeConRango([homonima, ganadora])
    r = resolver(exp, fake)
    assert r["estado"] == "resuelto"
    assert r["cui"] == "1111111", r     # gana la de mayor identidad, no el solape
    assert fake.rango_llamado == 0      # la selección NO consultó valorizaciones


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

def test_privada_se_clasifica_al_final():
    """PÚBLICO-PRIMERO: colegios PRIVADOS (Catholic High School, Trinity College)
    AHORA SÍ se buscan en InfoObras (se agota primero toda la resolución pública),
    pero al no haber candidato público fiable se clasifican al FINAL como privadas:
    via PRIVADA, sin obra, sin revisión — y ninguna obra basura sale resuelta."""
    llamadas = []

    class ConsultaEspia:
        def por_codigo(self, c): return []
        # devuelve una obra educativa AJENA (mismo rubro → no la veta el rubro, pero
        # sin nombre propio compartido → no pasa el gate): jamás debe resolverse.
        def buscar(self, n): llamadas.append(n); return [
            {"nombrObra": "MEJORAMIENTO DEL SERVICIO EDUCATIVO INICIAL DE LA I.E. 1234, "
                          "DISTRITO DE SANTA", "codUniqInv": "2999999",
             "codigoObra": 1, "nombrDepartamento": "ANCASH"}]

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
        assert r["cui"] is None
    assert llamadas != []          # AHORA sí busca (público-primero), pero clasifica al final


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
        {"proyecto": "I.E. 616 Salaverry", "cui": "2118617",      # obra real + rango POR obra
         "fecha_inicial": "2019-06-01", "fecha_final": "2020-08-31"},
        {"proyecto": "Víctor Maldonado", "cui": None},            # sin CUI
        {"proyecto": "I.E. 15510 Gálvez", "cui": "2036812"},      # obra real (sin rango por obra)
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
    # se ARRASTRA el rango POR obra cuando el cert lo da (para el cruce de cobertura)
    assert res[2]["fecha_inicial"] == "2019-06-01" and res[2]["fecha_final"] == "2020-08-31"
    assert res[4].get("fecha_inicial") is None   # sin rango por obra → None


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


# ── ADR-011 · resolución por SUB-OBRA (cert multi-obra) ──────────────────────

_MADRE_HV = {
    "proyecto": ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL HOSPITAL DE APOYO "
                 "SULLANA II-2 Y EL CENTRO DE SALUD POSOPE ALTO I-3 (PAQUETE 6)"),
    "cui": None,
    "entidad_contratante": "MUNICIPALIDAD PROVINCIAL DE SULLANA",
    "entidad_emisora": "HV CONTRATISTAS S.A.", "ruc_emisor": "20100000001",
    "ubicacion": "Provincia de Sullana, Piura",
    "fecha_inicial": "2022-03-01", "fecha_final": "2023-07-31",
}


def test_exp_derivada_hereda_el_contrato_pero_no_la_ubicacion():
    """La herencia de la madre a la sub-obra, campo por campo. Heredar TODO vetaría
    sub-obras legítimas de un paquete que cruza provincias; heredar NADA dejaría la
    búsqueda por nombre sin candados."""
    sub = {"proyecto": "MEJORAMIENTO ... CENTRO DE SALUD POSOPE ALTO I-3", "cui": None}
    d = _exp_derivada(_MADRE_HV, sub)

    # el proyecto es el de la SUB-OBRA (el punto del desglose), no el compuesto
    assert d["proyecto"] == sub["proyecto"] and "PAQUETE" not in d["proyecto"]
    # el contrato es uno solo → entidad/emisor/RUC viajan (mantienen los candados)
    assert d["entidad_contratante"] == "MUNICIPALIDAD PROVINCIAL DE SULLANA"
    assert d["ruc_emisor"] == "20100000001"
    # la ubicación de la madre NO viaja
    assert "ubicacion" not in d
    # las fechas del vínculo sí, como respaldo (desempate en _elegir_obra)
    assert d["fecha_inicial"] == "2022-03-01" and d["fecha_final"] == "2023-07-31"
    # dict NUEVO: resolver() escribe en la exp que recibe y no debe tocar a la madre
    d["_fichas_mef"] = {"x": 1}
    assert "_fichas_mef" not in _MADRE_HV


def test_exp_derivada_prefiere_las_fechas_propias_de_la_sub_obra():
    """Escenario B (sub-fechas declaradas): mandan las de la sub-obra."""
    sub = {"proyecto": "OBRA X", "cui": None,
           "fecha_inicial": "2022-06-01", "fecha_final": "2022-12-31"}
    d = _exp_derivada(_MADRE_HV, sub)
    assert d["fecha_inicial"] == "2022-06-01" and d["fecha_final"] == "2022-12-31"


def test_la_geografia_de_la_madre_no_veta_a_la_sub_obra():
    """El veto de ubicación entra por DOS puertas (`ubigeo_cert` lee la entidad
    contratante; `_muni_contradice` la lee sola). Para una sub-obra ambas se apagan:
    la única autoridad geográfica sobre la sub-obra es SU nombre. Sin esto, un
    paquete de la Municipalidad Provincial de Sullana vetaría su propia obra de
    Posope Alto (Lambayeque) — falso negativo."""
    sub = {"proyecto": "MEJORAMIENTO ... CENTRO DE SALUD POSOPE ALTO I-3", "cui": None}
    d = _exp_derivada(_MADRE_HV, sub)

    # la madre SÍ declara Sullana…
    assert "SULLANA" in ubigeo_cert(_MADRE_HV)["prov"]
    # …y la sub-obra derivada NO hereda esa provincia
    assert ubigeo_cert(d)["prov"] == set()
    # el candado municipalidad-vs-municipalidad también queda inerte
    ficha_otra_muni = {"entidad": "MUNICIPALIDAD PROVINCIAL DE CHICLAYO"}
    assert _muni_contradice(_MADRE_HV, ficha_otra_muni) is True
    assert _muni_contradice(d, ficha_otra_muni) is False


def test_la_sub_obra_conserva_la_geografia_de_su_propio_nombre():
    """Apagar la geografía heredada NO es apagar el veto: si el NOMBRE de la
    sub-obra declara su provincia, esa sí cuenta (y sí puede vetar)."""
    sub = {"proyecto": "MEJORAMIENTO DEL C.S. X, PROVINCIA DE CHICLAYO", "cui": None}
    assert "CHICLAYO" in ubigeo_cert(_exp_derivada(_MADRE_HV, sub))["prov"]


def test_sub_obra_sin_cui_resuelve_por_nombre():
    """El delta del ADR-011: antes una sub-obra sin CUI moría en `sin_cui`."""
    class ConsultaHV:
        def por_codigo(self, c):
            return []

        def buscar(self, nombre):
            if "SULLANA" in nombre.upper():
                return [{"nombrObra": "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL "
                                      "HOSPITAL DE APOYO SULLANA II-2",
                         "codUniqInv": "2595123", "codigoObra": 444,
                         "nombrDepartamento": "PIURA"}]
            return []

    obras = [{"proyecto": "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL HOSPITAL "
                          "DE APOYO SULLANA II-2", "cui": None},
             {"proyecto": "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL CENTRO DE "
                          "SALUD POSOPE ALTO I-3", "cui": None}]
    res = resolver_obras(obras, ConsultaHV(), exp_madre=_MADRE_HV)

    assert [r["estado"] for r in res] == ["resuelto", "revision"]
    assert res[0]["cui"] == "2595123" and res[0]["via"] == "NOMBRE"
    # 1 de N: la que no resuelve queda VISIBLE con su motivo, no desaparece
    assert res[1]["cui"] is None and res[1]["decision"]
    assert res[1]["proyecto"].endswith("POSOPE ALTO I-3")


def test_sub_obra_sin_exp_madre_sigue_saliendo_sin_cui():
    """Sin madre no hay de dónde derivar: se conserva el estado histórico en vez de
    buscar por un nombre pelado y sin candados."""
    class ConsultaVacia:
        def por_codigo(self, c):
            return []

        def buscar(self, nombre):
            raise AssertionError("no debe buscar por nombre sin exp_madre")

    res = resolver_obras([{"proyecto": "OBRA X", "cui": None}], ConsultaVacia())
    assert res[0]["estado"] == "sin_cui"


def test_cui_citado_que_no_existe_no_cae_a_busqueda_por_nombre():
    """ESCALERA (la decisión de diseño de PR-2). El cert de Talara cita el código de
    un Plan Integral que NO es obra. Si esa sub-obra cayera a búsqueda por nombre,
    el resolver podría casarla con cualquier obra parecida: sería adivinar sobre
    evidencia que YA contradice — el falso positivo que el ADR-011 quiere evitar.
    Un código citado que no existe se queda en `no_encontrado`."""
    buscados = []

    class ConsultaTalara:
        def por_codigo(self, c):
            return []                      # el Plan Integral no figura como obra

        def buscar(self, nombre):
            buscados.append(nombre)
            return [{"nombrObra": "MEJORAMIENTO DEL AEROPUERTO JORGE CHAVEZ",
                     "codUniqInv": "2999999", "codigoObra": 9,
                     "nombrDepartamento": "LIMA"}]

    res = resolver_obras([{"proyecto": "Jorge Chávez", "cui": "2089754"}],
                         ConsultaTalara(), exp_madre=_MADRE_HV)
    assert res[0]["estado"] == "no_encontrado" and res[0]["cui"] == "2089754"
    assert buscados == []                  # ni siquiera se intentó por nombre


# ── ADR-011 · P1 · candado MULTI-RUBRO ───────────────────────────────────────

def _obras(*nombres):
    return [{"proyecto": n, "cui": None} for n in nombres]


def test_rubros_mixtos_detecta_salud_mas_vial():
    """El caso del ADR: un paquete que mezcla especialidades y no dice cuánto
    tiempo va a cada una es indecidible sin anexo."""
    mix = rubros_mixtos(_obras("MEJORAMIENTO DEL CENTRO DE SALUD POSOPE ALTO I-3",
                               "MEJORAMIENTO DE LA CARRETERA VECINAL SULLANA-TAMBOGRANDE"))
    assert mix == {"salud", "vial"}


def test_rubros_mixtos_no_dispara_con_un_solo_rubro():
    assert rubros_mixtos(_obras("HOSPITAL DE APOYO SULLANA II-2",
                                "CENTRO DE SALUD POSOPE ALTO I-3")) == set()


def test_rubros_mixtos_no_dispara_por_una_obra_con_dos_componentes():
    """UNA obra que menciona dos rubros ("el centro de salud y su acceso vial") es
    una obra con dos componentes, no un paquete multi-rubro. La contradicción se
    exige ENTRE dos sub-obras — si no, el candado se dispararía por redacción."""
    assert rubros_mixtos(_obras(
        "MEJORAMIENTO DEL CENTRO DE SALUD X Y SU ACCESO VIAL",
        "MEJORAMIENTO DEL CENTRO DE SALUD Y")) == set()


def test_rubros_mixtos_ignora_las_sub_obras_de_rubro_indeterminado():
    """Rubro vacío = indeterminado: nunca participa (misma regla que el veto)."""
    assert rubros_mixtos(_obras("HOSPITAL DE APOYO SULLANA II-2",
                                "OBRA SIN PALABRAS DE RUBRO ALGUNO")) == set()
    # …y con una tercera que sí contradice, la mixtura es solo entre las declaradas
    assert rubros_mixtos(_obras("HOSPITAL DE APOYO SULLANA II-2",
                                "OBRA SIN PALABRAS DE RUBRO ALGUNO",
                                "CARRETERA VECINAL X")) == {"salud", "vial"}


# ── ADR-013 · CANDADO DE NOMBRE GENÉRICO ────────────────────────────────────
# Un `proyecto` cuyo nombre no aporta NINGÚN término propio —solo genéricos de
# obra, palabras de rubro y el nombre de una entidad del Estado— no puede
# sostener `via = NOMBRE`: describe a decenas de obras. Se exige corroboración
# dura o se va a revisión con los candidatos VISIBLES.

class _ConsultaFija:
    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return [o for o in self.obras if str(o.get("codUniqInv")) == str(codigo)]

    def buscar(self, nombre):
        return list(self.obras)


class _BaseFichas:
    """Base MEF de juguete: solo fichas por CUI (sin candidatos propios)."""

    def __init__(self, fichas):
        self.fichas = fichas

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return []

    def existe_cui(self, codigo):
        return self.fichas.get(str(codigo))

    def es_entidad_publica(self, nombre):
        return (True, 100)


def test_tokens_distintivos_descuenta_genericos_y_entidades():
    # el caso que motiva el candado: 3 palabras, ninguna identifica una obra
    assert tokens_distintivos("HOSPITAL DE ESSALUD") == set()
    assert tokens_distintivos("MEJORAMIENTO DE LOS SERVICIOS DE SALUD") == set()
    # un nombre propio SÍ cuenta, aunque venga con genéricos y con la entidad
    assert tokens_distintivos("HOSPITAL DE ESSALUD DE MOYOBAMBA") == {"MOYOBAMBA"}
    assert "KREAR" in tokens_distintivos(
        "Mejoramiento de la Infraestructura Educativa KREAR")


_OBRA_GENERICA = {
    "codUniqInv": "2405647", "codigoObra": 33793,
    "nombrObra": ("INSTALACION DE LOS SERVICIOS DE TOMOGRAFIA DEL HOSPITAL I "
                  "VICTOR ALFREDO LAZO PERALTA DE ESSALUD - PUERTO MALDONADO"),
    "nombrDepartamento": "MADRE DE DIOS",
}
_FICHA_GENERICA = {"cui": "2405647", "nombre": _OBRA_GENERICA["nombrObra"],
                   "dpto": "MADRE DE DIOS", "prov": "TAMBOPATA",
                   "dist": "TAMBOPATA", "entidad": "SEGURO SOCIAL DE SALUD"}


def test_nombre_generico_sin_corroboracion_va_a_revision():
    """«HOSPITAL DE ESSALUD» no puede sostener un `resuelto` por nombre: sin RUC,
    sin N° de institución, sin entidad que calce y sin ubigeo coincidente, el
    candidato queda VISIBLE en revisión — nunca descartado en silencio."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD", "fecha_inicial": "2012-10-26"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]),
                 base=_BaseFichas({"2405647": _FICHA_GENERICA}))
    assert r["estado"] == "revision" and r["cui"] is None, r
    assert "2405647" in {c["cui"] for c in r["candidatos"]}
    assert "término propio" in r["decision"]


def test_nombre_generico_con_ruc_del_emisor_si_resuelve():
    """El candado exige CORROBORACIÓN, no un nombre perfecto: el RUC del emisor
    figurando como ejecutor de la obra es evidencia dura y basta."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD", "ruc_emisor": "20544148380",
           "fecha_inicial": "2012-10-26"}
    obra = dict(_OBRA_GENERICA, rucEjecutor="20544148380")
    r = resolver(exp, _ConsultaFija([obra]),
                 base=_BaseFichas({"2405647": _FICHA_GENERICA}))
    assert r["estado"] == "resuelto" and r["via"] == "RUC", r


def test_nombre_generico_con_ubigeo_coincidente_si_resuelve():
    """Ubigeo POSITIVO (la provincia/distrito del MEF coincide con la declarada)
    también corrobora. El departamento NO cuenta como corroboración: ADR-005 midió
    que no desempata homónimos."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD",
           "ubicacion": "Distrito de Tambopata, Provincia de Tambopata",
           "fecha_inicial": "2016-06-18"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]),
                 base=_BaseFichas({"2405647": _FICHA_GENERICA}))
    assert r["estado"] == "resuelto" and r["cui"] == "2405647", r


def test_nombre_generico_con_entidad_TAMBIEN_generica_no_se_salva():
    """`ent_match` NO corrobora si la entidad del certificado es ella misma
    genérica. «SEGURO SOCIAL DE SALUD» es el nombre formal de EsSalud: casa con
    CUALQUIER inversión de EsSalud del país, así que "confirma" el candidato con
    la misma palabra que ya hacía genérico al nombre. Corroborarse a sí mismo no
    es corroborar — es el caso exacto del ADR-013 (Hospital EsSalud de Tarapoto
    contra una tomografía en Madre de Dios)."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD",
           "entidad_contratante": "SEGURO SOCIAL DE SALUD",
           "fecha_inicial": "2012-10-26"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]),
                 base=_BaseFichas({"2405647": _FICHA_GENERICA}))
    assert r["estado"] == "revision" and r["cui"] is None, r
    assert any(c.get("cui") == "2405647" for c in r["candidatos"]), r


def test_nombre_generico_con_entidad_PROPIA_si_resuelve():
    """La otra cara: una entidad con término propio (una municipalidad concreta)
    SÍ es señal dura — identifica a un contratante entre miles, no a un sector."""
    ficha = {**_FICHA_GENERICA, "entidad": "MUNICIPALIDAD DISTRITAL DE PERENE"}
    exp = {"proyecto": "HOSPITAL DE ESSALUD",
           "entidad_contratante": "MUNICIPALIDAD DISTRITAL DE PERENE",
           "fecha_inicial": "2012-10-26"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]),
                 base=_BaseFichas({"2405647": ficha}))
    assert r["estado"] == "resuelto" and r["cui"] == "2405647", r


def test_un_solo_token_distintivo_basta_umbral_n1():
    """Calibración N=1 (medida sobre las 1519 experiencias del corpus): exigir DOS
    términos propios mandaría a revisión el 11.5% del corpus resuelto. Con uno
    solo, el candado no se activa."""
    proyecto = "MEJORAMIENTO DEL HOSPITAL DE ESSALUD DE MOYOBAMBA"
    assert len(tokens_distintivos(proyecto)) == 1
    obra = {"codUniqInv": "2900030", "codigoObra": 30, "nombrObra": proyecto,
            "nombrDepartamento": "SAN MARTIN"}
    ficha = {"cui": "2900030", "nombre": proyecto, "dpto": "SAN MARTIN",
             "prov": "MOYOBAMBA", "dist": "MOYOBAMBA"}
    r = resolver({"proyecto": proyecto, "fecha_inicial": "2015-01-01"},
                 _ConsultaFija([obra]), base=_BaseFichas({"2900030": ficha}))
    assert r["estado"] == "resuelto" and r["cui"] == "2900030", r


def test_candado_de_nombre_no_toca_el_cui_citado():
    """Un CUI escrito en el certificado se resuelve en el PASO 0 y no pasa por las
    compuertas por nombre: sigue siendo autoritativo aunque el nombre sea genérico
    (el certificado suele citar un componente del proyecto integral)."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD", "cui": "2405647",
           "fecha_inicial": "2016-06-18"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]),
                 base=_BaseFichas({"2405647": _FICHA_GENERICA}))
    assert r["estado"] == "resuelto" and r["cui"] == "2405647", r
    assert r["via"] in ("CUI_TEXTO", "PROBABLE")


def test_candado_de_nombre_tambien_actua_sin_base_mef():
    """Sin base MEF no hay fichas y `geo_match`/`ent_match` no existen, pero el
    candado es el mismo: un nombre sin término propio no resuelve por nombre."""
    exp = {"proyecto": "HOSPITAL DE ESSALUD", "fecha_inicial": "2012-10-26"}
    r = resolver(exp, _ConsultaFija([_OBRA_GENERICA]), base=None)
    assert r["estado"] == "revision" and r["cui"] is None, r


def test_dedup_requiere_coincidencia_de_emisor_rechaza_diferente():
    """Fix #58: DEDUP por folio exige que el emisor coincida. Si dos experiencias
    comparten folio pero tienen emisores distintos (ej. Arcadia vs Picota por folio 84),
    la segunda NO hereda el CUI de la primera."""
    from resolucion.cui import resolver_con_dedup
    obra = {"codUniqInv": "222222", "codigoObra": 222, "nombrObra": "OBRA SANTA ANITA"}
    exp1 = {"proyecto": "OBRA SANTA ANITA", "folio": "84",
            "entidad_emisora": "MUNICIPALIDAD DISTRITAL DE SANTA ANITA", "cui": "222222"}
    exp2 = {"proyecto": "OBRA PICOTA INEXISTENTE EN INFOOBRAS", "folio": "84",
            "entidad_emisora": "MUNICIPALIDAD PROVINCIAL DE PICOTA"}

    exps = [(exp1, (1, 1)), (exp2, (1, 2))]
    res = dict(resolver_con_dedup(exps, _ConsultaFija([obra]), base=None))

    assert res[(1, 1)]["estado"] == "resuelto"
    assert res[(1, 1)]["cui"] == "222222"
    # Exp 2 NO hereda de Exp 1 porque el emisor es distinto
    assert res[(1, 2)]["estado"] == "revision"
    assert res[(1, 2)].get("via") != "DEDUP"


def test_dedup_requiere_coincidencia_de_emisor_acepta_mismo():
    """Fix #58: DEDUP por folio sí hereda cuando el emisor es la misma entidad
    (caso legítimo de 2° periodo del mismo certificado)."""
    from resolucion.cui import resolver_con_dedup
    obra = {"codUniqInv": "222222", "codigoObra": 222, "nombrObra": "OBRA SANTA ANITA"}
    exp1 = {"proyecto": "OBRA SANTA ANITA PERIODO 1", "folio": "84",
            "entidad_emisora": "MUNICIPALIDAD DISTRITAL DE SANTA ANITA S.A.C.", "cui": "222222"}
    exp2 = {"proyecto": "PERIODO 2 - CONTINUACION DE SERVICIO", "folio": "84",
            "entidad_emisora": "MUNICIPALIDAD DISTRITAL DE SANTA ANITA"}

    exps = [(exp1, (1, 1)), (exp2, (1, 2))]
    res = dict(resolver_con_dedup(exps, _ConsultaFija([obra]), base=None))

    assert res[(1, 1)]["estado"] == "resuelto"
    assert res[(1, 2)]["estado"] == "resuelto"
    assert res[(1, 2)]["via"] == "DEDUP"
    assert res[(1, 2)]["cui"] == "222222"


def test_cui_citado_que_contradice_nombre_depto_y_rubro_cae_a_revision():
    """Fix #59 (Caso Navarro, P9-E3): Un CUI citado que en InfoObras apunta a una obra que
    contradice NOMBRE (0 tokens en común), DEPARTAMENTO y RUBRO simultáneamente cae a revisión."""
    # Certificado dice Salud en Pasco: "C.S. Yanahuanca"
    exp = {"proyecto": "CENTRO DE SALUD YANAHUANCA - PASCO", "cui": "49922",
           "ubicacion": "Distrito de Yanahuanca, Provincia de Daniel Alcides Carrión, Departamento de Pasco"}
    # El CUI 49922 en InfoObras resulta ser veredas en Ferreñafe (Lambayeque)
    obra_veredas = {
        "codUniqInv": "49922", "codigoObra": 49922,
        "nombrObra": "CONSTRUCCION DE VEREDAS Y SARDINELES EN FERREÑAFE",
        "nombrDepartamento": "LAMBAYEQUE"
    }
    r = resolver(exp, _ConsultaFija([obra_veredas]), base=None)
    assert r["estado"] == "revision"
    assert r["cui"] is None
    assert "contradice el nombre, el departamento y el rubro" in r["decision"]


def test_cui_citado_coar_no_se_demota_por_ubigeo():
    """Regresión #59 (Caso COAR): Si el CUI citado coincide y mantiene afinidad de nombre
    o rubro, se resuelve aunque el departamento difiera (obras multiregionales COAR)."""
    exp = {"proyecto": "MEJORAMIENTO DEL SERVICIO EDUCATIVO COAR CUSCO", "cui": "2429909",
           "ubicacion": "Departamento de Cusco"}
    obra_coar = {
        "codUniqInv": "2429909", "codigoObra": 2429909,
        "nombrObra": "CREACION DEL SERVICIO EDUCATIVO ESPECIALIZADO COAR EN PASCO",
        "nombrDepartamento": "PASCO"
    }
    r = resolver(exp, _ConsultaFija([obra_coar]), base=None)
    assert r["estado"] == "resuelto"
    assert r["cui"] == "2429909"
