"""
ADR-010 · el tipo de evaluación del concurso es un PARÁMETRO declarado por la
skill (`_meta.tipo_evaluacion`), no una inferencia del texto de cada certificado.

Lo que protegen estas pruebas (caso real San Isidro P1:E2, 51/68 mal enrutadas):
la skill guardó en `proyecto` solo el nombre entre comillas y perdió la frase
«Elaboración del Expediente Técnico», así que el backend pidió valorizaciones de
una obra que nunca se construyó. Con el parámetro, el enrutado deja de depender
de una palabra que el LLM puede podar.

Precedencia: parámetro del espejo > override env (`PIVOTE_FORZAR_EXPEDIENTES`)
> texto. Un valor fuera del vocabulario cerrado NO se interpreta como «obras».
"""
from __future__ import annotations

import io
import json

import pytest

from resolucion.cui import (
    CLAVE_TIPO_EVALUACION, TIPO_EXPEDIENTES, TIPO_OBRAS, _exp_derivada,
    es_expediente_exp, estampar_tipo_evaluacion, normalizar_tipo_evaluacion,
    tipo_evaluacion_del_espejo,
)

# Certificado que PERDIÓ la palabra «expediente» (el caso que rompe el texto).
EXP_SIN_PALABRA = {"n": 2, "proyecto": "MEJORAMIENTO DEL C.S. FORTALEZA",
                   "cargo_ocupado": "Especialista en Estructuras"}
# Certificado que sí la conserva.
EXP_CON_PALABRA = {"n": 3, "proyecto": "Elaboración del Expediente Técnico: "
                                       "«MEJORAMIENTO DEL HOSPITAL X»",
                   "cargo_ocupado": "Jefe de proyecto"}


# ── normalización ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,esperado", [
    ("expedientes", TIPO_EXPEDIENTES), ("EXPEDIENTE", TIPO_EXPEDIENTES),
    ("Expediente Técnico", TIPO_EXPEDIENTES), ("A", TIPO_EXPEDIENTES),
    ("obras", TIPO_OBRAS), ("Obra", TIPO_OBRAS), ("supervisión de obra", TIPO_OBRAS),
    ("B", TIPO_OBRAS), ("ejecución", TIPO_OBRAS),
])
def test_normaliza_alias_tolerando_mayusculas_y_acentos(valor, esperado):
    assert normalizar_tipo_evaluacion(valor) == esperado


@pytest.mark.parametrize("valor", [None, "", "   ", "mixto", "consultoria", 42, "expedientes y obras"])
def test_valor_desconocido_es_none_no_obras(valor):
    # desconocido ≠ obras: la ausencia de parámetro cae al texto, jamás decide.
    assert normalizar_tipo_evaluacion(valor) is None


def test_tipo_del_espejo_lee_meta_y_tolera_espejos_viejos():
    assert tipo_evaluacion_del_espejo({"_meta": {"tipo_evaluacion": "Expedientes"}}) == TIPO_EXPEDIENTES
    assert tipo_evaluacion_del_espejo({"_meta": {"analisis_id": "x"}}) is None
    assert tipo_evaluacion_del_espejo({}) is None
    assert tipo_evaluacion_del_espejo(None) is None
    assert tipo_evaluacion_del_espejo({"_meta": "roto"}) is None


# ── precedencia ──────────────────────────────────────────────────────────────

def test_sin_parametro_se_conserva_la_deteccion_por_texto():
    assert es_expediente_exp(EXP_CON_PALABRA) is True
    assert es_expediente_exp(EXP_SIN_PALABRA) is False   # el fallo histórico


def test_parametro_expedientes_enruta_aunque_el_texto_perdio_la_palabra():
    assert es_expediente_exp(EXP_SIN_PALABRA, TIPO_EXPEDIENTES) is True


def test_parametro_obras_manda_sobre_el_texto_y_sobre_el_env():
    # concurso declarado de obras: ni la palabra del cert ni el env global lo cambian
    assert es_expediente_exp(EXP_CON_PALABRA, TIPO_OBRAS) is False
    assert es_expediente_exp(EXP_CON_PALABRA, TIPO_OBRAS, forzar=True) is False


def test_env_sigue_funcionando_como_override_cuando_no_hay_parametro():
    assert es_expediente_exp(EXP_SIN_PALABRA, None, forzar=True) is True
    assert es_expediente_exp(EXP_SIN_PALABRA, "", forzar=True) is True


def test_parametro_invalido_no_decide_y_cae_al_siguiente_nivel():
    assert es_expediente_exp(EXP_SIN_PALABRA, "mixto") is False          # → texto
    assert es_expediente_exp(EXP_SIN_PALABRA, "mixto", forzar=True) is True  # → env


# ── estampado en memoria (lo que ve el resolver) ─────────────────────────────

def test_estampar_marca_cada_experiencia_y_devuelve_el_tipo():
    espejo = {"_meta": {"tipo_evaluacion": "expedientes"},
              "profesionales": [{"n_prof": 1, "experiencias": [dict(EXP_SIN_PALABRA)]},
                                {"n_prof": 2, "experiencias": [dict(EXP_CON_PALABRA)]}]}
    assert estampar_tipo_evaluacion(espejo) == TIPO_EXPEDIENTES
    for prof in espejo["profesionales"]:
        for exp in prof["experiencias"]:
            assert exp[CLAVE_TIPO_EVALUACION] == TIPO_EXPEDIENTES
            # el resolver, que solo recibe la experiencia, ya enruta bien
            assert es_expediente_exp(exp) is True


def test_estampar_sin_parametro_no_toca_nada():
    exp = dict(EXP_SIN_PALABRA)
    espejo = {"_meta": {"analisis_id": "x"}, "profesionales": [{"experiencias": [exp]}]}
    assert estampar_tipo_evaluacion(espejo) is None
    assert CLAVE_TIPO_EVALUACION not in exp


def test_la_subobra_derivada_hereda_el_tipo_de_la_madre():
    madre = {**EXP_SIN_PALABRA, "entidad_contratante": "GORE X",
             CLAVE_TIPO_EVALUACION: TIPO_EXPEDIENTES}
    hija = _exp_derivada(madre, {"proyecto": "PUESTO DE SALUD Y", "cui": None})
    assert hija[CLAVE_TIPO_EVALUACION] == TIPO_EXPEDIENTES
    sin_tipo = _exp_derivada(EXP_SIN_PALABRA, {"proyecto": "P", "cui": None})
    assert CLAVE_TIPO_EVALUACION not in sin_tipo


# ── Excel: la cronología y la reconciliación siguen al mismo parámetro ───────

def test_presentacion_cruces_respeta_el_tipo_declarado():
    from entregables.excel_final import presentacion_cruces
    # sin parámetro: el nombre no dice «expediente» → tipo indeterminado → Regla B aplica
    p = presentacion_cruces(EXP_SIN_PALABRA, {})
    assert p["aplica_b"] is True
    assert p["resp_b"].startswith("POR VERIFICAR")
    # concurso de EXPEDIENTES: la fila deja de dudar y reclama su fuente
    p = presentacion_cruces(EXP_SIN_PALABRA, {}, TIPO_EXPEDIENTES)
    assert p["aplica_b"] is True
    assert "sin fuente" in p["resp_b"].lower()
    # concurso de OBRAS: la Regla B no aplica aunque el cert diga «expediente»
    p = presentacion_cruces(EXP_CON_PALABRA, {}, TIPO_OBRAS)
    assert p["aplica_b"] is False
    assert p["resp_b"].startswith("NO APLICA")


def test_reconciliar_no_descuenta_paralizaciones_a_un_expediente_declarado():
    from entregables.excel_final import reconciliar_resultados_profesionales
    espejo = {"_meta": {"tipo_evaluacion": "expedientes"},
              "profesionales": [{"n_prof": 1, "experiencias": [
                  {**EXP_SIN_PALABRA, "fecha_inicial": "2021-01-01",
                   "fecha_final": "2021-12-31"}]}]}
    enr = {"1:2": {"cui": "2000001", "via": "NOMBRE",
                   "paralizaciones": [{"inicio": "2021-03-01", "fin": "2021-05-31"}]}}
    con_param = reconciliar_resultados_profesionales(espejo, enr)[1]
    espejo["_meta"].pop("tipo_evaluacion")
    sin_param = reconciliar_resultados_profesionales(espejo, enr)[1]
    # como expediente, la paralización de la construcción posterior no le resta días
    assert con_param["dias_efectivos"] > sin_param["dias_efectivos"]


# ── API: el form-field completa al espejo, el espejo manda ───────────────────

ESPEJO_MIN = {
    "_meta": {"analisis_id": "tipo-eval-001", "concurso": "CP-TIPO/2026", "postor": "POSTOR"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE PROYECTO", "nombre": "Profesional Uno",
         "colegiatura": "CIP 12345", "cumple": "SÍ — 2.0 años",
         "total": {"dias": 730, "anios": 2.0},
         "experiencias": [
             {"n": 1, "proyecto": "MEJORAMIENTO DEL C.S. FORTALEZA",
              "entidad_emisora": "Entidad A", "ruc_emisor": "20123456789",
              "nombre_emisor": "Firma Uno", "cargo_emisor": "Gerente General",
              "fecha_emision": "2023-06-01", "tipo_documento": "Constancia",
              "entidad_contratante": "Entidad Pública",
              "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
              "dias": 724, "folio": "100"},
         ]},
    ],
    "resumen_evaluacion": {"factores": [{"factor": "A", "puntaje": 55}], "puntaje_total": 55},
}


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """Mismo arnés que `test_api.py`: datos en tmp y etapas esqueleto (sin red)."""
    import importlib
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app)


def _subir(cliente, cid, meta_extra=None, data_extra=None):
    espejo = json.loads(json.dumps(ESPEJO_MIN))
    espejo["_meta"].update(meta_extra or {})
    data = {"concurso_id": cid, **(data_extra or {})}
    return cliente.post("/api/pivote/analizar", data=data, files={
        "espejo": ("espejo.json", io.BytesIO(json.dumps(espejo).encode("utf-8")), "application/json"),
        "excel": ("claude.xlsx", io.BytesIO(b"PK demo"), "application/octet-stream"),
    })


def _concurso(cliente):
    r = cliente.post("/api/pivote/concursos", json={"nomenclatura": "CP-TIPO/2026", "entidad": "E"})
    return r.json()["concurso_id"]


def _espejo_persistido(job_id: str) -> dict:
    """El espejo tal como quedó guardado (el endpoint `/espejo` es una proyección
    para el panel y no expone `_meta`)."""
    import api.app as modulo
    return modulo.repo.cargar_espejo(job_id) or {}


def test_api_espejo_con_parametro_lo_persiste_canonico(cliente):
    cid = _concurso(cliente)
    r = _subir(cliente, cid, meta_extra={"tipo_evaluacion": "Expediente Técnico"})
    assert r.status_code == 201, r.text
    esp = _espejo_persistido(r.json()["job_id"])
    assert esp["_meta"]["tipo_evaluacion"] == TIPO_EXPEDIENTES


def test_api_form_field_completa_cuando_el_espejo_no_lo_trae(cliente):
    cid = _concurso(cliente)
    r = _subir(cliente, cid, data_extra={"tipo_evaluacion": "obras"})
    assert r.status_code == 201, r.text
    esp = _espejo_persistido(r.json()["job_id"])
    assert esp["_meta"]["tipo_evaluacion"] == TIPO_OBRAS


def test_api_el_espejo_manda_sobre_el_form_field(cliente):
    cid = _concurso(cliente)
    r = _subir(cliente, cid, meta_extra={"tipo_evaluacion": "expedientes"},
               data_extra={"tipo_evaluacion": "obras"})
    assert r.status_code == 201, r.text
    esp = _espejo_persistido(r.json()["job_id"])
    assert esp["_meta"]["tipo_evaluacion"] == TIPO_EXPEDIENTES


def test_api_sin_parametro_sigue_aceptando_espejos_viejos(cliente):
    cid = _concurso(cliente)
    r = _subir(cliente, cid)
    assert r.status_code == 201, r.text
    esp = _espejo_persistido(r.json()["job_id"])
    assert esp["_meta"].get("tipo_evaluacion") is None


@pytest.mark.parametrize("donde", ["espejo", "form"])
def test_api_valor_fuera_del_vocabulario_es_422(cliente, donde):
    cid = _concurso(cliente)
    kw = ({"meta_extra": {"tipo_evaluacion": "mixto"}} if donde == "espejo"
          else {"data_extra": {"tipo_evaluacion": "mixto"}})
    r = _subir(cliente, cid, **kw)
    assert r.status_code == 422
    assert "permitidos" in json.dumps(r.json())
