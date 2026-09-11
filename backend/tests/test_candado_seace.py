"""
T-004 F5 — candado de identidad CERTIFICADO ↔ PROCESO SEACE.

Todo offline: el candado es puro y los fixtures son sintéticos salvo el caso
POSITIVO, calcado de datos reales de la corrida Vitarte (job `7e9306a321ac`,
prof 8 exp 2 — E.S. Pedro Sánchez Meza, CUI 2337618, proceso
AS-SM-28-2021-GRJ-CS-1) y el caso NEGATIVO del Hospital del Altiplano
(CUI 2300016), verificado en vivo contra CONOSCE/OCDS el 2026-08-05.
"""
from __future__ import annotations

import zipfile

import openpyxl
import pytest

from entregables import (construir_zip_infoobras, desempaquetar_enriquecimiento,
                         generar_excel_final)
from validacion.candado_seace import (
    CONFIRMADO, CONTRADICE, POR_CONFIRMAR, TOLERANCIA_DIAS_FIRMA,
    confirmado_sin_adjudicatario, evaluar_candado, observaciones_temporales,
    resumen_proceso, rotulo,
)


# ── Fixtures: el caso real Pedro Sánchez Meza ────────────────────────────────

def proceso_sanchez_meza() -> dict:
    """Resumen del proceso real AS-SM-28-2021-GRJ-CS-1 (GORE Junín)."""
    return {
        "entidad_convocante": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
        "rucs_adjudicatarios": ["20263373058"],
        "fecha_firma": "2021-09-24",
        "fecha_convocatoria": "2021-07-14",
        "vigencia_inicio": "2021-09-25",
        "vigencia_fin": "2024-03-12",
        "monto": 3798760.90,
        "nomenclatura": "AS-SM-28-2021-GRJ-CS-1",
        "tipo": "supervision",
    }


def cert_sanchez_meza() -> dict:
    """Certificado real: constancia de INDECONSULT por la supervisión."""
    return {
        "entidad_contratante": "GOBIERNO REGIONAL DE JUNÍN",
        "entidad_emisora": "INSTITUTO DE CONSULTORIA S.A.",
        "ruc_emisor": "20263373058",
        "tipo_experiencia": "supervision",
        "fecha_inicial": "2021-10-01",
        "fecha_final": "2023-10-11",
        "monto_contrato_soles": None,
    }


# ── 1 · Promoción ────────────────────────────────────────────────────────────

def test_promocion_caso_real_sanchez_meza():
    """Entidad, emisor adjudicatario, objeto y fechas cuadran → confirmado."""
    c = evaluar_candado(proceso_sanchez_meza(), cert_sanchez_meza())
    assert c.resultado == CONFIRMADO
    assert len(c.a_favor) >= 2
    assert not c.en_contra
    nombres = {s.nombre for s in c.a_favor}
    assert {"entidad", "adjudicatario", "objeto", "temporal"} >= nombres
    # El detalle es auditable a ojo, no un booleano.
    detalle = " ".join(s.detalle for s in c.senales)
    assert "20263373058" in detalle and "GOBIERNO REGIONAL DE JUNIN" in detalle


def test_promocion_exige_dos_senales_no_una():
    """Una sola señal fuerte a favor NO alcanza para promover."""
    proceso = {**proceso_sanchez_meza(), "entidad_convocante": None,
               "rucs_adjudicatarios": [], "fecha_firma": None,
               "fecha_convocatoria": None,
               "vigencia_inicio": None, "vigencia_fin": None}
    c = evaluar_candado(proceso, cert_sanchez_meza())
    assert [s.nombre for s in c.a_favor] == ["objeto"]
    assert c.resultado == POR_CONFIRMAR


def test_gate_issue83_no_cuenta_adjudicatario():
    """El proceso puede estar confirmado por F5 y aun así NO habilitar #83 si
    una de sus dos patas fue precisamente el RUC que #83 quiere obtener."""
    cert = {**cert_sanchez_meza(), "entidad_contratante": None,
            "fecha_inicial": None, "fecha_final": None}
    c = evaluar_candado(proceso_sanchez_meza(), cert)
    assert c.resultado == CONFIRMADO
    assert {s.nombre for s in c.a_favor} == {"adjudicatario", "objeto"}
    assert confirmado_sin_adjudicatario(c) is False
    assert confirmado_sin_adjudicatario(c.como_dict()) is False


def test_gate_issue83_acepta_dos_senales_independientes():
    c = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "ruc_emisor": None,
        "entidad_contratante": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
    })
    assert c.resultado == CONFIRMADO
    assert confirmado_sin_adjudicatario(c) is True


def test_gate_issue83_ignora_temporal_fuerte_persistida():
    """Jobs antiguos pueden haber guardado la fecha como FUERTE; nunca debe
    convertir ese metadato en una señal de identidad."""
    base = {"resultado": CONFIRMADO, "senales": [
        {"nombre": "entidad", "fuerza": "fuerte", "sentido": "a_favor"},
        {"nombre": "objeto", "fuerza": "fuerte", "sentido": "a_favor"},
        {"nombre": "temporal", "fuerza": "fuerte", "sentido": "a_favor"},
    ]}
    assert confirmado_sin_adjudicatario(base) is True
    solo_fecha = {**base, "senales": [base["senales"][2]]}
    assert confirmado_sin_adjudicatario(solo_fecha) is False


# ── 2 · Degradación por metadata incompleta ──────────────────────────────────

def test_degradacion_metadata_incompleta():
    """Sin entidad, sin RUC y sin fechas del proceso → nunca se promueve."""
    proceso = {"tipo": "supervision"}
    c = evaluar_candado(proceso, cert_sanchez_meza())
    assert c.resultado == POR_CONFIRMAR
    assert not c.en_contra


def test_degradacion_certificado_sin_entidad_contratante():
    """El caso más común del corpus: el certificado no cita entidad contratante.
    Eso NO puede contradecir — solo deja de sumar."""
    cert = {**cert_sanchez_meza(), "entidad_contratante": None}
    c = evaluar_candado(proceso_sanchez_meza(), cert)
    assert not c.en_contra
    # Emisor adjudicatario + objeto + fechas siguen alcanzando.
    assert c.resultado == CONFIRMADO
    entidad = next(s for s in c.senales if s.nombre == "entidad")
    assert entidad.sentido == "sin_dato"


def test_emisor_que_no_es_adjudicatario_no_contradice():
    """Una constancia de un consorciado con RUC propio no es una contradicción."""
    cert = {**cert_sanchez_meza(), "ruc_emisor": "20512345678",
            "entidad_contratante": None}
    c = evaluar_candado(proceso_sanchez_meza(), cert)
    adj = next(s for s in c.senales if s.nombre == "adjudicatario")
    assert adj.sentido == "sin_dato"
    assert not c.en_contra


# ── 3 · Contradicción ────────────────────────────────────────────────────────

def test_contradice_entidad_de_otra_region():
    proceso = {**proceso_sanchez_meza(),
               "entidad_convocante": "MUNICIPALIDAD PROVINCIAL DE MAYNAS"}
    c = evaluar_candado(proceso, cert_sanchez_meza())
    assert c.resultado == CONTRADICE
    assert [s.nombre for s in c.en_contra] == ["entidad"]
    assert "MAYNAS" in c.motivo


def test_contradice_objeto_distinto():
    proceso = {**proceso_sanchez_meza(), "tipo": "ejecucion"}
    c = evaluar_candado(proceso, cert_sanchez_meza())
    assert c.resultado == CONTRADICE
    assert "objeto" in [s.nombre for s in c.en_contra]


def test_contradice_sin_un_dia_en_comun():
    cert = {**cert_sanchez_meza(), "fecha_inicial": "2015-01-01",
            "fecha_final": "2016-01-01"}
    c = evaluar_candado(proceso_sanchez_meza(), cert)
    # Las fechas siguen reportándose con precisión, pero son débiles: no
    # pueden vetar una identidad respaldada por entidad y objeto.
    assert c.resultado == CONFIRMADO
    temporal = next(s for s in c.senales if s.nombre == "temporal")
    assert temporal.fuerza == "debil" and temporal.sentido == "en_contra"


def test_confirmado_con_discrepancia_temporal_la_conserva_en_motivo():
    c = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "fecha_inicial": "2015-01-01", "fecha_final": "2016-01-01"
    })
    assert c.resultado == CONFIRMADO
    assert observaciones_temporales(c) == [next(
        s.detalle for s in c.senales if s.nombre == "temporal")]
    assert "señal fuerte de identidad" in c.motivo
    assert "Observación de fechas:" in c.motivo


# ── 4 · Zona gris de similitud ───────────────────────────────────────────────

def test_zona_gris_de_similitud_no_decide():
    """Un parecido intermedio de razón social nunca confirma ni contradice.

    Caso REAL: el certificado dice «GOBIERNO REGIONAL DE JUNÍN» y el proceso
    «GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL» → 80/100. Es casi seguro la misma
    entidad, pero 80 no alcanza el umbral de match fuerte: la señal se abstiene
    y son el RUC del adjudicatario y las fechas las que confirman el caso.
    """
    proceso = {**proceso_sanchez_meza(),
               "rucs_adjudicatarios": [], "fecha_firma": None,
               "fecha_convocatoria": None,
               "vigencia_inicio": None, "vigencia_fin": None}
    c = evaluar_candado(proceso, cert_sanchez_meza())
    entidad = next(s for s in c.senales if s.nombre == "entidad")
    assert entidad.sentido == "sin_dato", entidad.detalle
    assert "zona gris" in entidad.detalle and "80/100" in entidad.detalle
    assert c.resultado == POR_CONFIRMAR


def test_entidad_identica_suma_a_favor():
    """Cuando el certificado copia la razón social tal cual, la señal sí decide."""
    proceso = {**proceso_sanchez_meza(), "rucs_adjudicatarios": []}
    cert = {**cert_sanchez_meza(),
            "entidad_contratante": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL - DRTC"}
    c = evaluar_candado(proceso, cert)
    entidad = next(s for s in c.senales if s.nombre == "entidad")
    assert entidad.sentido == "a_favor", entidad.detalle
    assert c.resultado == CONFIRMADO


# ── 5 · Señal temporal DÍA A DÍA (nunca truncada a mes) ──────────────────────

def test_temporal_mismo_mes_dias_incompatibles():
    """Caso borde exigido: firma 30/01, inicio declarado 05/01.

    Comparten enero, así que un cómputo truncado a mes lo daría por bueno —
    exactamente el defecto detectado en el clamp del Paso 5. Con aritmética de
    días completos son 25 días de diferencia, por encima de la tolerancia de
    {TOLERANCIA_DIAS_FIRMA}: la señal NO cuadra.
    """
    proceso = {**proceso_sanchez_meza(), "fecha_firma": "2011-01-30",
               "fecha_convocatoria": None,
               "vigencia_inicio": "2011-01-31", "vigencia_fin": "2013-01-30"}
    cert = {**cert_sanchez_meza(), "fecha_inicial": "2011-01-05",
            "fecha_final": "2012-12-31"}
    c = evaluar_candado(proceso, cert)
    temporal = next(s for s in c.senales if s.nombre == "temporal")
    assert temporal.sentido == "en_contra", temporal.detalle
    assert temporal.fuerza == "debil"
    assert "25 días" in temporal.detalle
    assert c.resultado == CONFIRMADO


def test_temporal_dentro_de_la_tolerancia_en_dias():
    """Un desfase menor a la tolerancia sí cuadra (orden de inicio posterior a
    la firma es normal). El borde se prueba con día exacto, no con mes."""
    proceso = {**proceso_sanchez_meza(), "fecha_firma": "2021-01-16",
               "fecha_convocatoria": None,
               "vigencia_inicio": "2021-01-17", "vigencia_fin": "2023-01-16"}
    cert = {**cert_sanchez_meza(), "fecha_inicial": "2021-01-01",
            "fecha_final": "2022-12-31"}
    assert (16 - 1) == TOLERANCIA_DIAS_FIRMA          # el borde exacto
    c = evaluar_candado(proceso, cert)
    temporal = next(s for s in c.senales if s.nombre == "temporal")
    assert temporal.sentido == "a_favor", temporal.detalle
    assert temporal.fuerza == "debil"


def test_temporal_un_dia_mas_alla_de_la_tolerancia_contradice():
    proceso = {**proceso_sanchez_meza(), "fecha_firma": "2021-01-17",
               "fecha_convocatoria": None,
               "vigencia_inicio": "2021-01-18", "vigencia_fin": "2023-01-17"}
    cert = {**cert_sanchez_meza(), "fecha_inicial": "2021-01-01",
            "fecha_final": "2022-12-31"}
    c = evaluar_candado(proceso, cert)
    temporal = next(s for s in c.senales if s.nombre == "temporal")
    assert temporal.sentido == "en_contra", temporal.detalle
    assert temporal.fuerza == "debil"
    assert c.resultado == CONFIRMADO


# ── 6 · Monto: señal débil que ni veta ni promueve sola ──────────────────────

def test_monto_dispar_no_veta():
    """El certificado declara el monto de la OBRA y el proceso el del servicio:
    difieren por diseño. Con dos señales fuertes a favor sigue confirmando."""
    cert = {**cert_sanchez_meza(), "monto_contrato_soles": 98000000.0}
    c = evaluar_candado(proceso_sanchez_meza(), cert)
    assert c.resultado == CONFIRMADO
    monto = next(s for s in c.senales if s.nombre == "monto")
    assert monto.fuerza == "debil" and monto.sentido != "en_contra"


def test_monto_coincidente_no_promueve_solo():
    """Monto idéntico + UNA sola señal fuerte a favor → sigue por confirmar."""
    proceso = {**proceso_sanchez_meza(), "entidad_convocante": None,
               "rucs_adjudicatarios": [], "fecha_firma": None,
               "fecha_convocatoria": None,
               "vigencia_inicio": None, "vigencia_fin": None}
    cert = {**cert_sanchez_meza(), "monto_contrato_soles": 3798760.90}
    c = evaluar_candado(proceso, cert)
    monto = next(s for s in c.senales if s.nombre == "monto")
    assert monto.sentido == "a_favor" and monto.fuerza == "debil"
    assert len(c.a_favor) == 1
    assert c.resultado == POR_CONFIRMAR


# ── 7 · El caso Altiplano no llega al candado (no hay proceso que cruzar) ────

def test_altiplano_sin_proceso_de_supervision():
    """CUI 2300016: los 14 procesos publicados son adquisición de equipamiento
    biomédico de EsSalud (verificado en vivo el 2026-08-05). El selector NO se
    equivoca: no hay proceso de supervisión que promover, así que la experiencia
    ni siquiera llega al candado y el Excel dice «no se encontró un proceso del
    tipo correspondiente». Este test fija ese hallazgo."""
    from scraping.seace_abierto import clasificar_proceso, seleccionar_proceso
    procesos = [
        {"ocid": f"ocds-dgv273-seacev3-{i}",
         "tender": {"title": f"LP-SM-{i}-2025-ESSALUD/CEABE-1",
                    "description": "Adquisición de Equipamiento Biomédico para la "
                                   "implementación del proyecto de inversión Creación "
                                   "de los Servicios de Salud del Hospital del "
                                   "Altiplano de la Región Puno - ESSALUD",
                    "mainProcurementCategory": "goods"},
         "buyer": {"name": "SEGURO SOCIAL DE  SALUD"}}
        for i in (1200091, 1180718, 1180069)
    ]
    assert {clasificar_proceso(p)[0] for p in procesos} == {"otro"}
    sel = seleccionar_proceso(procesos, "supervision")
    assert sel["elegido"] is None
    assert "no tiene proceso de supervision" in sel["motivo"]


# ── 8 · Extracción del resumen desde la forma OCDS real ──────────────────────

def test_resumen_proceso_desde_ocds():
    comp = {
        "ocid": "ocds-dgv273-seacev3-2021-41-85",
        "buyer": {"id": "PE-CONSUCODE-41",
                  "name": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL"},
        "parties": [
            {"name": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
             "roles": ["buyer", "procuringEntity"], "id": "PE-CONSUCODE-41"},
            # Consorcio: el "RUC" de 6 dígitos NO es un RUC y debe descartarse.
            {"name": "CONSORCIO ALKA", "roles": ["tenderer"],
             "identifier": {"scheme": "PE-RUC", "id": "466064"}},
            {"name": "INSTITUTO DE CONSULTORIA S.A.",
             "roles": ["tenderer", "supplier"],
             "identifier": {"scheme": "PE-RUC", "id": "20263373058"}},
        ],
        "tender": {"title": "AS-SM-28-2021-GRJ-CS-1",
                   "value": {"amount": 3799140.81},
                   "tenderPeriod": {"startDate": "2021-07-14T00:00:00-05:00"}},
        "contracts": [{"dateSigned": "2021-09-24T00:00:00-05:00",
                       "period": {"startDate": "2021-09-25T00:00:00-05:00",
                                  "endDate": "2024-03-12T00:00:00-05:00"},
                       "value": {"amount": 3798760.90}}],
        "awards": [{"suppliers": [{"id": "PE-RUC-20263373058",
                                   "name": "INSTITUTO DE CONSULTORIA S.A."}]}],
    }
    r = resumen_proceso(comp)
    assert r["entidad_convocante"] == "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL"
    assert r["rucs_adjudicatarios"] == ["20263373058"]     # sin el 466064
    assert r["adjudicatarios"] == [{
        "ruc": "20263373058",
        "nombre": "INSTITUTO DE CONSULTORIA S.A.",
        "origen": "parties",
    }]
    assert r["fecha_firma"] == "2021-09-24"
    assert r["fecha_convocatoria"] == "2021-07-14"
    assert r["vigencia_inicio"] == "2021-09-25"
    assert r["vigencia_fin"] == "2024-03-12"
    assert r["monto"] == pytest.approx(3798760.90)


def test_resumen_abarca_todos_los_contratos_no_solo_el_primero():
    """Regresión del caso real CUI 2343407 (CP-SM-9-2017-PRONIS-1).

    La fuente devuelve primero un contrato de DOS DÍAS de 2024 (liquidación) y
    después el contrato de verdad, 2018–2020. Quedarse con `contracts[0]`
    marcaba «NO COINCIDE» dos experiencias legítimas de 2018 y 2020.
    """
    comp = {
        "ocid": "ocds-dgv273-seacev3-425421",
        "buyer": {"name": "UNIDAD EJECUTORA 125 PROGRAMA NACIONAL DE "
                          "INVERSIONES EN SALUD"},
        "tender": {"title": "CP-SM-9-2017-PRONIS-1"},
        "contracts": [
            {"id": "2250234", "dateSigned": "2018-04-17T00:00:00-05:00",
             "period": {"startDate": "2024-04-24T00:00:00-05:00",
                        "endDate": "2024-04-25T00:00:00-05:00"},
             "value": {"amount": 1000.0}},
            {"id": "1153133", "dateSigned": "2018-04-17T00:00:00-05:00",
             "period": {"startDate": "2018-04-18T00:00:00-05:00",
                        "endDate": "2020-05-01T00:00:00-05:00"},
             "value": {"amount": 2000.0}},
        ],
    }
    r = resumen_proceso(comp)
    assert r["vigencia_inicio"] == "2018-04-18"
    assert r["vigencia_fin"] == "2024-04-25"
    assert r["fecha_firma"] == "2018-04-17"      # la más TEMPRANA
    assert r["monto"] == pytest.approx(3000.0)   # suma, no `contracts[0]`
    r["tipo"] = "supervision"
    cert = {**cert_sanchez_meza(), "entidad_contratante": None,
            "fecha_inicial": "2018-05-29", "fecha_final": "2020-03-15"}
    c = evaluar_candado(r, cert)
    # Tipo y fechas no bastan: el proceso queda por confirmar sin dos señales
    # fuertes de identidad independientes.
    assert c.resultado == POR_CONFIRMAR, [s.detalle for s in c.senales]


# ── 9 · Los entregables muestran el rótulo correcto en los 3 estados ─────────

ESPEJO = {
    "_meta": {"analisis_id": "f5", "concurso": "CP-TEST-F5", "postor": "P"},
    "postor": {},
    "profesionales": [{
        "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "N",
        "experiencias": [{
            "n": 1, "proyecto": "Supervisión del Hospital",
            "fecha_inicial": "2021-10-01", "fecha_final": "2023-10-11",
        }],
    }],
    "resumen_evaluacion": {"factores": []},
}


def _seace(candado: dict | None) -> dict:
    datos = {
        "estado": "seleccionado", "cui": "2337618",
        "proceso_objeto": "supervision", "seleccion": "objeto+vigencia",
        "ambiguo": False, "motivo": "único proceso de supervisión del CUI",
        "fecha_suscripcion": "2021-09-24",
        "proceso": proceso_sanchez_meza(),
        "docs": {"bases": {"estado": "disponible", "url": "https://e/b.pdf"},
                 "contrato": {"estado": "disponible", "url": "https://e/c.pdf"}},
    }
    if candado is not None:
        datos["candado"] = candado
    return datos


def _textos_excel(tmp_path, seace) -> str:
    enr = {"1:1": {"cui": "2337618", "seace": seace}}
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(
        ESPEJO, tmp_path / "final.xlsx", paral, cuis, fichas, {}, sunat)
    wb = openpyxl.load_workbook(salida)
    return "\n".join(str(c.value) for ws in wb.worksheets
                     for fila in ws.iter_rows() for c in fila if c.value)


@pytest.mark.parametrize("resultado", [CONFIRMADO, POR_CONFIRMAR, CONTRADICE])
def test_excel_muestra_el_rotulo_de_los_tres_estados(tmp_path, resultado):
    texto = _textos_excel(
        tmp_path, _seace({"resultado": resultado, "motivo": "motivo de prueba",
                          "senales": []}))
    assert rotulo(resultado) in texto
    if resultado == CONFIRMADO:
        assert "motivo de prueba" not in texto      # solo se explica lo dudoso
    else:
        assert "motivo de prueba" in texto


def test_excel_de_job_viejo_sin_candado_no_rompe(tmp_path):
    """Compatibilidad: un job anterior a F5 se regenera igual que siempre."""
    texto = _textos_excel(tmp_path, _seace(None))
    assert "DOCUMENTOS DEL PROCESO (SEACE)" in texto
    assert "Correspondencia con el certificado" not in texto


def test_excel_confirmado_no_oculta_observacion_temporal(tmp_path):
    candado = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "fecha_inicial": "2015-01-01", "fecha_final": "2016-01-01"
    }).como_dict()
    texto = _textos_excel(tmp_path, _seace(candado))
    assert candado["resultado"] == CONFIRMADO
    assert "Observación de fechas" in texto
    assert candado["senales"][3]["detalle"] in texto


def test_resumen_mismo_cui_acumula_observaciones_por_experiencia():
    from entregables.excel_final import _cron_proyectos
    c1 = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "fecha_inicial": "2015-01-01", "fecha_final": "2016-01-01"
    }).como_dict()
    c2 = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "fecha_inicial": "2014-01-01", "fecha_final": "2014-12-31"
    }).como_dict()
    espejo = {**ESPEJO, "profesionales": [{
        **ESPEJO["profesionales"][0], "experiencias": [
            {"n": 1, "proyecto": "Mismo proyecto", "cui": "2337618"},
            {"n": 2, "proyecto": "Mismo proyecto", "cui": "2337618"},
        ]}]}
    fichas = {(1, 1): {"cui": "2337618", "seace": _seace(c1)},
              (1, 2): {"cui": "2337618", "seace": _seace(c2)}}
    proyectos = _cron_proyectos(espejo, fichas)
    observacion = proyectos[0]["observacion_fechas"]
    assert len(observacion) == 2
    assert observacion[0].startswith("P1 E1 · AS-SM-28-2021-GRJ-CS-1:")
    assert observacion[1].startswith("P1 E2 · AS-SM-28-2021-GRJ-CS-1:")


@pytest.mark.parametrize("resultado", [CONFIRMADO, POR_CONFIRMAR, CONTRADICE])
def test_indice_del_zip_muestra_el_rotulo(tmp_path, resultado):
    origen = tmp_path / "P1E1"
    origen.mkdir()
    (origen / "BASES_INTEGRADAS.pdf").write_bytes(b"%PDF-1.4\n")
    salida = tmp_path / "z.zip"
    construir_zip_infoobras(
        ESPEJO, {(1, 1): origen}, salida,
        enriquecimiento={"1:1": {"cui": "2337618", "seace": _seace(
            {"resultado": resultado, "motivo": "m", "senales": []})}})
    with zipfile.ZipFile(salida) as zf:
        indice = zf.read("indice.txt").decode("utf-8")
    assert rotulo(resultado) in indice


def test_indice_zip_confirmado_conserva_observacion_temporal(tmp_path):
    origen = tmp_path / "P1E1"
    origen.mkdir()
    (origen / "BASES_INTEGRADAS.pdf").write_bytes(b"%PDF-1.4\n")
    candado = evaluar_candado(proceso_sanchez_meza(), {
        **cert_sanchez_meza(), "fecha_inicial": "2015-01-01", "fecha_final": "2016-01-01"
    }).como_dict()
    salida = tmp_path / "z.zip"
    construir_zip_infoobras(
        ESPEJO, {(1, 1): origen}, salida,
        enriquecimiento={"1:1": {"cui": "2337618", "seace": _seace(candado)}})
    with zipfile.ZipFile(salida) as zf:
        indice = zf.read("indice.txt").decode("utf-8")
    assert candado["resultado"] == CONFIRMADO
    assert "Observación de fechas" in indice
    assert candado["senales"][3]["detalle"] in indice


def test_indice_de_job_viejo_sin_candado_queda_igual(tmp_path):
    origen = tmp_path / "P1E1"
    origen.mkdir()
    (origen / "BASES_INTEGRADAS.pdf").write_bytes(b"%PDF-1.4\n")
    salida = tmp_path / "z.zip"
    construir_zip_infoobras(
        ESPEJO, {(1, 1): origen}, salida,
        enriquecimiento={"1:1": {"cui": "2337618", "seace": _seace(None)}})
    with zipfile.ZipFile(salida) as zf:
        indice = zf.read("indice.txt").decode("utf-8")
    assert "Documentos del proceso (SEACE)" not in indice


# ── 10 · Extensión del documento persistido (causa de los 3 _ERROR de Vitarte)

@pytest.mark.parametrize("clave", ["format", "formato"])
@pytest.mark.parametrize("valor,esperada", [("zip", ".zip"), ("rar", ".rar"),
                                            ("application/pdf", ".pdf")])
def test_extension_documento_lee_las_dos_formas(clave, valor, esperada):
    """La descarga diferida trabaja sobre el bloque PERSISTIDO, que guarda la
    clave en español. Leer solo `format` forzaba `.pdf` y la validación por
    magia tiraba el archivo: los 3 `*_ERROR.txt` de la corrida Vitarte."""
    from scraping.seace_abierto import extension_documento
    doc = {"url": "https://prod1.seace.gob.pe/x?fileCode=abc", clave: valor}
    assert extension_documento(doc) == esperada
