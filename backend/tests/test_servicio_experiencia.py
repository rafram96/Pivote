from validacion.candado_seace import _senal_objeto, A_FAVOR, SIN_DATO
from validacion.servicio_experiencia import (
    contrastar_servicio, evidencia_tipo_servicio, fase_servicio_incompatible,
)
from scraping.seace_abierto import tipo_por_experiencia


def ev(texto, pagina=4, tipo=None):
    tipo = tipo or ("supervision_obra" if "Supervisión" in texto else "elaboracion_expediente" if "expediente" in texto.lower() else "ejecucion_obra")
    return {"tipo": tipo, "texto": texto, "pagina_pdf": pagina, "fuente": "certificado"}


def test_literal_supervision_de_ejecucion_es_supervision():
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Supervisión de ejecución de obra")})["tipo"] == "supervision"


def test_literal_requiere_trazabilidad_y_no_inventa_desde_proyecto():
    salida = evidencia_tipo_servicio({"proyecto": "Construcción del hospital"})
    assert salida["tipo"] is None and salida["fuente"] == "sin_evidencia"


def test_construccion_en_titulo_no_prueba_ejecucion():
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Especialista en estructuras del proyecto Construcción del hospital", tipo="ejecucion_obra")})["tipo"] is None


def test_residente_de_obra_es_ejecucion_y_roles_mixtos_abstienen():
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Residente de obra", tipo="ejecucion_obra")})["tipo"] == "ejecucion"
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Residente / supervisor de obra", tipo="ejecucion_obra")})["tipo"] is None


def test_tipo_estructurado_contradicho_por_literal_abstiene():
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Supervisor de obra", tipo="ejecucion_obra")})["tipo"] is None


def test_supervisor_de_obra_es_supervision():
    assert evidencia_tipo_servicio({"servicio_declarado": ev("Supervisor de obra", tipo="supervision_obra")})["tipo"] == "supervision"


def test_supervision_expediente_no_se_convierte_en_supervision_obra():
    salida = evidencia_tipo_servicio({"servicio_declarado": ev("Supervisión de la elaboración del expediente técnico", tipo="supervision_expediente")})
    assert salida["tipo"] is None and salida["fuente"] == "sin_evidencia"


def test_contraste_sin_declarado_no_es_contradicho():
    salida = contrastar_servicio({"_meta": {"servicio_esperado": {"tipo": "supervision_obra", "texto": "supervisión de obra", "pagina_pdf": 2, "fuente": "bases"}}}, {})
    assert salida["estado"] == "no_determinado"


def test_contraste_difiere_solo_con_dos_evidencias():
    salida = contrastar_servicio(
        {"_meta": {"servicio_esperado": {"tipo": "supervision_obra", "texto": "supervisión de obra", "pagina_pdf": 2, "fuente": "tdr"}}},
        {"servicio_declarado": ev("Ejecución de obra")},
    )
    assert salida["estado"] == "difiere" and salida["declarado"]["texto"] == "Ejecución de obra"


def test_candado_no_usa_tipo_legacy_como_evidencia():
    señal = _senal_objeto({"tipo": "supervision"}, {"tipo_experiencia": "ejecucion"})
    assert señal.sentido == SIN_DATO


def test_tipo_explicito_orienta_sin_ser_prueba():
    assert tipo_por_experiencia(False, {"servicio_declarado": {"tipo": "ejecucion_obra"}})["tipo"] == "ejecucion"
    assert tipo_por_experiencia(False, {"servicio_declarado": {"tipo": "supervision_expediente"}})["tipo"] is None


def test_fase_incompatible_solo_con_declarado_conocido():
    assert fase_servicio_incompatible({}, {"servicio_declarado": ev("Elaboración del expediente técnico")}, False)
    assert not fase_servicio_incompatible({}, {"proyecto": "Elaboración del expediente"}, False)
