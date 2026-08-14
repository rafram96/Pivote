"""Regresiones de la auditoría de los entregables San Isidro/Tacna."""
from datetime import date

from entregables.excel_final import presentacion_cruces
from orquestador.descargas_infoobras import CacheDescargasInfoObras
from orquestador.etapas_reales import _recalcular_factor_a
from validacion import (aplicar_reglas_formacion, aplicar_reglas_iso,
                        construir_inventario_documental,
                        recalcular_experiencia_postor, recalcular_espejo,
                        reconciliar_puntajes)


def test_mes_parcial_usa_mes_completo_y_preserva_literal():
    espejo = {
        "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [{"n_prof": 1, "fecha_colegiatura": None,
                            "experiencias": [{"n": 1,
                                "fecha_inicial": "2024-02 (literal)",
                                "fecha_final": "2024-02 (literal)"}]}],
    }
    recalcular_espejo(espejo, sobrescribir=True)
    exp = espejo["profesionales"][0]["experiencias"][0]
    assert exp["fecha_inicial"] == "2024-02 (literal)"
    assert exp["_backend"]["fecha_inicial_calculo"] == "2024-02-01"
    assert exp["_backend"]["fecha_final_calculo"] == "2024-02-29"
    assert exp["dias"] == 29


def test_anexo_15_no_exige_diploma_que_las_bases_no_piden():
    espejo = {"profesionales": [{
        "n_prof": 1, "profesion_valida": "NO CUMPLE — falta diploma",
        "requisitos": {"acreditacion_formacion": {
            "modalidad": "anexo_15_registro_publico",
            "diploma_adjunto_requerido": False,
        }},
        "acreditacion_formacion": {
            "titulo_declarado": "Ingeniero Civil", "universidad_declarada": "UNI",
            "documento_identidad": "12345678", "diploma_adjunto": False,
            "extraccion_completa": True,
        },
    }]}
    hallazgos = aplicar_reglas_formacion(espejo)
    assert hallazgos[0].estado == "REVISION_MANUAL"
    assert espejo["profesionales"][0]["profesion_valida"].startswith("POR VERIFICAR")
    assert "falta diploma" not in espejo["profesionales"][0]["profesion_valida"]


def test_postor_multiitem_dedup_mixto_y_decimal():
    espejo = {
        "reglas_evaluacion": {"fecha_presentacion_oferta": "2026-01-31",
                              "antiguedad_maxima_anios": 20,
                              "periodos_sin_dia": "mes_completo"},
        "postor": {"experiencia_postor": [
            {"n": 1, "contrato_id": "C-1", "item_id": "1",
             "monto_item": "100.10", "fecha_inicio": "2006-01-31"},
            {"n": 2, "contrato_id": "C-1", "item_id": "2",
             "monto_item": "200.20", "participacion_porcentaje": "50",
             "fecha_inicio": "2006-02"},
            {"n": 3, "contrato_id": "C-1", "item_id": "1",
             "monto_item": "100.10"},
            {"n": 4, "contrato_id": "C-2", "componentes": ["obra", "equipamiento"],
             "monto_contrato": "300.30", "tipo_solicitado": "SÍ — obra"},
        ]},
    }
    total = recalcular_experiencia_postor(espejo)
    assert total == {"monto_confirmado": "200.20",
                     "monto_maximo_posible": "500.50", "estado": "condicionado"}
    filas = espejo["postor"]["experiencia_postor"]
    assert filas[2]["estado_monto"] == "excluido"
    assert filas[3]["estado_monto"] == "por_verificar"
    assert filas[0]["dentro_periodo_admitido"].startswith("SÍ")


def test_iso_solo_es_definitivo_con_todos_los_consorciados_vigentes():
    espejo = {
        "reglas_evaluacion": {"fecha_presentacion_oferta": "2026-01-01"},
        "postor": {
            "consorciados": [{"nombre": "ALFA S.A.C."}, {"nombre": "BETA SRL"}],
            "isos_certificaciones": [
                {"norma": "ISO 9001:2015", "presente": True,
                 "titular": "ALFA SAC", "fecha_vencimiento": "2027-01-01"},
                {"norma": "ISO 9001:2015", "presente": True,
                 "titular": "BETA S.R.L.", "fecha_vencimiento": "2027-01-01"},
            ],
        },
        "resumen_evaluacion": {"factores": [
            {"factor": "GESTIÓN DE CALIDAD — ISO 9001", "puntaje": 10},
        ]},
    }
    aplicar_reglas_iso(espejo)
    factor = espejo["resumen_evaluacion"]["factores"][0]
    assert factor["estado_puntaje"] == "definitivo"
    espejo["postor"]["isos_certificaciones"].pop()
    aplicar_reglas_iso(espejo)
    assert factor["puntaje"] is None
    assert factor["estado_puntaje"] == "condicionado"
    assert "BETA SRL" in factor["detalle"]


def _factor_espejo(efectivos_1, efectivos_2):
    return {
        "reglas_evaluacion": {"factor_a": {"dias_adicionales_requeridos": 365,
            "tramos": [
                {"desde_porcentaje": 0, "hasta_porcentaje": 50, "puntaje": 0},
                {"desde_porcentaje": 50, "hasta_porcentaje": 80, "puntaje": 5},
                {"desde_porcentaje": 80, "hasta_porcentaje": 100,
                 "hasta_inclusivo": True, "puntaje": 10},
            ]}},
        "profesionales": [
            {"n_prof": 1, "requisitos": {"factor_a_aplica": True}},
            {"n_prof": 2, "requisitos": {"factor_a_aplica": True}},
        ],
        "resumen_evaluacion": {"factores": [{"factor": "A", "puntaje": 99}]},
    }, {"prof:1": {"minimo_dias": 365, "dias_efectivos": efectivos_1},
        "prof:2": {"minimo_dias": 365, "dias_efectivos": efectivos_2}}


def test_factor_a_aplica_baremo_y_reconcilia_total():
    espejo, enr = _factor_espejo(730, 730)
    _recalcular_factor_a(espejo, enr)
    reconciliar_puntajes(espejo)
    assert espejo["resumen_evaluacion"]["puntaje_total"] == 10
    assert espejo["resumen_evaluacion"]["estado_puntaje"] == "definitivo"


def test_factor_a_condicionado_publica_rango_no_total():
    espejo, enr = _factor_espejo(730, None)
    _recalcular_factor_a(espejo, enr)
    reconciliar_puntajes(espejo)
    resumen = espejo["resumen_evaluacion"]
    assert resumen["puntaje_total"] is None
    assert resumen["puntaje_confirmado"] == 5
    assert resumen["puntaje_maximo_posible"] == 10


def test_cronologia_distingue_expediente_ejecucion_e_indeterminado():
    exp = presentacion_cruces({"n": 1, "proyecto": "Elaboración del expediente técnico"}, {})
    ejec = presentacion_cruces({"n": 2, "proyecto": "Ejecución de obra hospitalaria"}, {})
    otro = presentacion_cruces({"n": 3, "proyecto": "Servicio hospitalario"}, {})
    assert exp["resp_b"].startswith("POR VERIFICAR") and exp["aplica_b"]
    assert ejec["resp_b"].startswith("NO APLICA") and not ejec["aplica_b"]
    assert otro["resp_b"].startswith("POR VERIFICAR") and otro["aplica_b"]


def test_inventario_cuenta_lo_encontrado_sin_mirar_descargas():
    espejo = {"profesionales": [{"n_prof": 1, "experiencias": [{"n": 1}]}]}
    enr = {"1:1": {"obra": {"obra_id": 7},
        "valorizaciones": [{"anio": 2024, "mes": 1, "docs": 2}],
        "seace": {"docs": {"bases": {"url": "https://x/?fileCode=abc"}}},
        "descargas_reales": {"archivos": 0}}}
    assert construir_inventario_documental(espejo, enr) == 3
    assert enr["1:1"]["documentos_encontrados"] == 3


def test_cache_parcial_tambien_es_terminal(tmp_path):
    cache = CacheDescargasInfoObras(tmp_path / "cache")
    llamadas = []

    def descargar(destino, _pendientes):
        llamadas.append(1)
        (destino / "dato.pdf").write_bytes(b"%PDF")
        return {"secciones": {"InfoObras": {"error": True}}}

    primero = cache.obtener(7, descargar=descargar)
    segundo = cache.obtener(7, descargar=descargar)
    assert not primero.completa and not segundo.completa
    assert segundo.cache_hit
    assert len(llamadas) == 1
