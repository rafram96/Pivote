"""
Certeza de identificación EN EL PANEL (`/espejo` y `/resumen`).

Qué se protege aquí
───────────────────
1. **El Panel ve lo mismo que el Excel.** La PARTE 5 de la hoja por profesional
   ya decía si el CUI lo citó el certificado, lo confirmó un documento del MEF,
   lo dedujo el backend o no se sabe. El Panel mostraba solo `via`, así que un
   «CUI inferido por el nombre» y un «CUI citado en el papel» se veían iguales.
2. **Un solo cálculo de días por certeza.** `resumen_certeza_profesional` es la
   función pura que reparte los días entre las cubetas; el test
   `test_las_cubetas_son_las_mismas_que_las_del_excel` exige que dé EXACTAMENTE
   las mismas filas de totales que imprime la PARTE 5 (el Excel NO se refactoriza:
   se compara contra él).
3. **El contrato JSON con el que programa el Panel**: `identificacion`
   (nivel/etiqueta/color/detalle), `alertas`, `fuente_mef` (estado + contrato +
   resolución + texto), `certeza` por profesional y `tipo_evaluacion`.

Todos los nombres de personas y empresas son ficticios; no hay datos del cliente.
"""
from __future__ import annotations

import importlib
import io
import json

import openpyxl
import pytest

from entregables import generar_excel_final
from entregables.certeza import resumen_certeza_profesional
from entregables.excel_final import (
    desempaquetar_enriquecimiento, inyectar_veredicto_backend,
)
from schemas.cargo import etiqueta_hoja

CARGO = "ESPECIALISTA EN INSTALACIONES ELECTRICAS"


def _espejo() -> dict:
    """7 experiencias de un concurso de EXPEDIENTES, una por caso de certeza.

    La 7 se traslapa con la 3 (junio-2021) para que ALT11 tenga algo que
    descontar y el total no sea una simple suma."""
    return {
        "_meta": {"analisis_id": "t-panel-certeza", "concurso": "CP-FICTICIO/2026",
                  "postor": "CONSORCIO FICTICIO",
                  "tipo_evaluacion": "expedientes"},
        "postor": {},
        "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [{
            "n_prof": 1, "cargo": CARGO, "nombre": "Profesional Ficticio",
            "colegiatura": "CIP 99999", "cumple": "SÍ",
            "requisitos": {"tipo_experiencia_valida":
                           "Experiencia mínima: 24 meses en el cargo desempeñado."},
            "experiencias": [
                {"n": 1, "proyecto": "Expediente técnico del Colegio Ficticio",
                 "entidad_emisora": "CONSULTORA FICTICIA UNO S.A.C.", "cui": "1111111",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2019-01-01", "fecha_final": "2019-06-30"},
                {"n": 2, "proyecto": "Expediente técnico del Puesto de Salud Ficticio",
                 "entidad_emisora": "CONSULTORA FICTICIA DOS S.A.C.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2020-01-01", "fecha_final": "2020-06-30"},
                {"n": 3, "proyecto": "Expediente técnico del Mercado Ficticio",
                 "entidad_emisora": "INGENIERÍA FICTICIA E.I.R.L.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2021-01-01", "fecha_final": "2021-06-30"},
                {"n": 4, "proyecto": "Expediente técnico del Estadio Ficticio",
                 "entidad_emisora": "ESTUDIO FICTICIO S.R.L.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2022-01-01", "fecha_final": "2022-06-30"},
                {"n": 5, "proyecto": "Expedientes técnicos varios (multi-obra)",
                 "entidad_emisora": "CONSORCIO FICTICIO DOS",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2023-01-01", "fecha_final": "2023-06-30"},
                {"n": 6, "proyecto": "Expediente técnico de la Planta Ficticia",
                 "entidad_emisora": "MINERA FICTICIA S.A.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2024-01-01", "fecha_final": "2024-06-30"},
                {"n": 7, "proyecto": "Expediente técnico del Coliseo Ficticio",
                 "entidad_emisora": "CONSULTORA FICTICIA UNO S.A.C.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2021-06-01", "fecha_final": "2021-12-31"},
            ]}],
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    }


def _enriquecimiento() -> dict:
    """Enriquecimiento sintético con las formas REALES del pipeline (veredicto
    `ok`, `elegido_por: emisor`, contratista en `contratista.valor`…)."""
    return {
        # 1 · CUI citado en el certificado; el MEF no publica nada del expediente
        "1:1": {"via": "CUI_TEXTO", "cui": "1111111",
                "obra_nombre": "COLEGIO FICTICIO", "codigo_infoobras": "1",
                "sin_documentos_mef": True,
                "cruces_fechas": [{"regla": "FECHA_APROBACION_ET",
                                    "resultado": "por_confirmar",
                                    "motivo": ("El MEF no publica la resolución de "
                                               "aprobación de este expediente; "
                                               "no se puede comparar el término.")}]},
        # 2 · confirmado por el CONTRATO del MEF elegido POR EL EMISOR
        "1:2": {"via": "NOMBRE", "cui": "2222222",
                "obra_nombre": "PUESTO DE SALUD FICTICIO", "codigo_infoobras": "2",
                "verificacion_expediente": {
                    "cui_confirmado": "2222222", "verificado_en_mef": True,
                    "contratista": {"valor": "CONSULTORA FICTICIA DOS S.A.C.",
                                    "declarado": "CONSULTORA FICTICIA DOS S.A.C.",
                                    "veredicto": "ok"},
                    "contrato": {"numero": "015-2020", "fecha": "2019-12-20",
                                 "veredicto": "ok", "elegido_por": "emisor",
                                 "otros_contratos_expediente": []},
                    "resolucion": {"veredicto": "no_verificable"}}},
        # 3 · inferido por el nombre; solo hay resolución y no nombra al consultor
        "1:3": {"via": "NOMBRE", "cui": "3333333",
                "obra_nombre": "MERCADO FICTICIO", "codigo_infoobras": "3",
                "verificacion_expediente": {
                    "cui_confirmado": "3333333", "verificado_en_mef": True,
                    "resolucion": {"numero": "123-2021-MF", "fecha": "2021-08-10",
                                   "veredicto": "no_verificable"}},
                "resolucion_aprobacion": {"legible": True, "fecha": "2021-08-10",
                                          "numero": "123-2021-MF",
                                          "coincide_emisor": "no_nombra"}},
        # 4 · sin identificar: el resolver no pudo cerrar la obra
        "1:4": {"via": "REVISION", "sin_verificar": True},
        # 5 · multi-obra con 0 de 2 identificadas
        "1:5": {"via": "MULTI_OBRA", "identificacion_incompleta": True,
                "sub_obras": [{"cui": None, "estado": "sin_resolver"},
                              {"cui": None, "estado": "sin_resolver"}]},
        # 6 · obra privada: no hay registro público que consultar
        "1:6": {"via": "PRIVADA", "sunat": {"ruc": "20999999999",
                                            "razon_social": "MINERA FICTICIA S.A."}},
        # 7 · inferido con contrato Y resolución que apuntan a OTRO consultor
        "1:7": {"via": "NOMBRE", "cui": "7777777",
                "obra_nombre": "COLISEO FICTICIO", "codigo_infoobras": "7",
                "verificacion_expediente": {
                    "cui_confirmado": "7777777", "verificado_en_mef": True,
                    "contratista": {"valor": "OTRA CONSULTORA FICTICIA S.A.C.",
                                    "declarado": "CONSULTORA FICTICIA UNO S.A.C.",
                                    "veredicto": "no_verificable"},
                    "contrato": {"numero": "030-2021", "fecha": "2021-05-02",
                                 "veredicto": "no_verificable",
                                 "elegido_por": "mas_barato",
                                 "otros_contratos_expediente": [
                                     "031-2021 — TERCERA CONSULTORA FICTICIA"]}},
                "resolucion_aprobacion": {
                    "legible": True, "numero": "456-2021-MF", "fecha": "2021-12-20",
                    "coincide_emisor": "nombra_otro",
                    "consultores": ["OTRA CONSULTORA FICTICIA S.A.C."]}},
    }


# ── 1 · la función pura contra la PARTE 5 del Excel ──────────────────────────

def _valor_total(ws, etiqueta: str):
    for fila in ws.iter_rows():
        for c in fila:
            if str(c.value or "").startswith(etiqueta):
                return ws.cell(c.row, 19).value
    raise AssertionError(f"no se encontró la fila de totales {etiqueta!r}")


def test_la_aritmetica_api_es_la_misma_que_el_resumen_compacto(tmp_path):
    espejo, enr = _espejo(), _enriquecimiento()
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "final.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, CARGO)]

    certeza = resumen_certeza_profesional(
        espejo["profesionales"][0], enr, "mes_completo", "expedientes")

    suma = sum(certeza[c]["dias"] for c in
               ("citado_confirmado", "inferido", "sin_identificar", "privada"))
    assert suma == _valor_total(ws, "SUMA COMPUTADA ANTES DE TRASLAPES")
    assert certeza["dias_traslape"] == _valor_total(
        ws, "(−) TRASLAPES ENTRE EXPERIENCIAS")
    assert certeza["dias_efectivos"] == _valor_total(
        ws, "TOTAL EFECTIVO NETO")


def test_las_cubetas_cuadran_con_los_dias_efectivos():
    """confirmado + inferido + sin identificar + privada − traslape = efectivos."""
    certeza = resumen_certeza_profesional(
        _espejo()["profesionales"][0], _enriquecimiento(), "mes_completo",
        "expedientes")
    suma = sum(certeza[c]["dias"] for c in
               ("citado_confirmado", "inferido", "sin_identificar", "privada"))
    assert suma - certeza["dias_traslape"] == certeza["dias_efectivos"]
    # exp 1 (181) + exp 2 (182); exp 3 (181) + exp 7 (214); exp 4 + exp 5 (362);
    # exp 6 privada (182). Traslape exp3∩exp7 = junio-2021 = 30 días.
    assert certeza["citado_confirmado"] == {"experiencias": 2, "dias": 363}
    assert certeza["inferido"] == {"experiencias": 2, "dias": 395}
    assert certeza["sin_identificar"] == {"experiencias": 2, "dias": 362}
    assert certeza["privada"] == {"experiencias": 1, "dias": 182}
    assert certeza["dias_traslape"] == 30


def test_una_experiencia_sin_fechas_legibles_cuenta_como_experiencia_sin_dias():
    """El Panel debe poder decir «1 experiencia, 0 días» sin que la fila se caiga."""
    espejo = _espejo()
    exp = espejo["profesionales"][0]["experiencias"][3]     # la sin identificar
    exp["fecha_inicial"] = "POR VERIFICAR"
    exp["fecha_final"] = "POR VERIFICAR"
    certeza = resumen_certeza_profesional(espejo["profesionales"][0],
                                          _enriquecimiento(), "mes_completo",
                                          "expedientes")
    assert certeza["sin_identificar"] == {"experiencias": 2, "dias": 181}


# ── 2 · los dos endpoints ────────────────────────────────────────────────────

@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """App fresca con datos en tmp_path y etapas de esqueleto (sin red)."""
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app), modulo


@pytest.fixture()
def job(cliente):
    """Job con el espejo de expedientes y el enriquecimiento sintético ya escrito."""
    api, modulo = cliente
    r = api.post("/api/pivote/concursos",
                 json={"nomenclatura": "CP-FICTICIO/2026", "entidad": "Entidad Ficticia"})
    assert r.status_code == 201
    r = api.post("/api/pivote/analizar",
                 data={"concurso_id": r.json()["concurso_id"]},
                 files={"espejo": ("espejo.json", io.BytesIO(
                            json.dumps(_espejo()).encode("utf-8")), "application/json"),
                        "excel": ("claude.xlsx", io.BytesIO(b"PK demo"),
                                  "application/octet-stream")})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    # El enriquecimiento del esqueleto se sustituye por el sintético: aquí se
    # prueba la proyección al Panel, no el pipeline.
    modulo.repo.guardar_enriquecimiento(job_id, _enriquecimiento())
    return api, job_id


NIVELES = {1: "citado", 2: "confirmado_mef", 3: "inferido", 4: "sin_identificar",
           5: "sin_identificar", 6: "privada", 7: "inferido"}
COLORES = {1: "verde", 2: "verde", 3: "violeta", 4: "amarillo", 5: "amarillo",
           6: "gris", 7: "violeta"}
ESTADOS_MEF = {1: "sin_documentos", 2: "contrato", 3: "resolucion",
               4: "sin_documentos", 5: "sin_documentos", 6: "sin_documentos",
               7: "ambos"}


def _experiencias(api, job_id) -> dict:
    r = api.get(f"/api/pivote/jobs/{job_id}/espejo")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tipo_evaluacion"] == "expedientes"
    prof = cuerpo["profesionales"][0]
    return prof, {e["n"]: e for e in prof["experiencias"]}


def test_espejo_da_nivel_etiqueta_y_color_de_cada_experiencia(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    assert set(exps) == set(NIVELES)
    for n, e in exps.items():
        ident = e["identificacion"]
        assert ident["nivel"] == NIVELES[n], n
        assert ident["color"] == COLORES[n], n
        assert ident["etiqueta"] and ident["detalle"]


def test_espejo_explica_en_llano_por_que_un_cui_es_inferido(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    detalle = exps[7]["identificacion"]["detalle"]
    assert detalle.startswith("CUI 7777777 inferido por el nombre del proyecto")
    assert "contrato a nombre de otro contratista" in detalle
    assert "OTRA CONSULTORA FICTICIA S.A.C." in detalle
    # el multi-obra dice CUÁNTAS obras faltan, no solo «sin identificar»
    assert "2 obras y ninguna ubicada" in exps[5]["identificacion"]["detalle"]
    # la privada no se presenta como un fallo del postor
    assert "no aplica consulta MEF/InfoObras" in exps[6]["identificacion"]["detalle"]
    assert "SUNAT no acredita por sí sola" in exps[6]["identificacion"]["detalle"]


def test_espejo_trae_las_alertas_del_entregable(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    assert exps[7]["alertas"] == [
        "La resolución de aprobación del MEF nombra a OTRO consultor "
        "(OTRA CONSULTORA FICTICIA S.A.C.), no al emisor del certificado"]
    assert exps[5]["alertas"] == [
        "Certificado con 2 obras y ninguna ubicada en el registro público"]
    # «no verificable» NO es una alerta: la ausencia de fuente no acusa al postor
    assert exps[3]["alertas"] == []


def test_espejo_estructura_la_fuente_mef(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    assert {n: e["fuente_mef"]["estado"] for n, e in exps.items()} == ESTADOS_MEF

    contrato = exps[2]["fuente_mef"]["contrato"]
    assert contrato["numero"] == "015-2020"
    assert contrato["contratista"] == "CONSULTORA FICTICIA DOS S.A.C."
    assert contrato["fecha"] == "2019-12-20"
    assert contrato["del_emisor"] is True
    assert exps[2]["fuente_mef"]["resolucion"] is None

    # elegido «por el más barato» NO confirma identidad, y se ve entre qué eligió
    ajeno = exps[7]["fuente_mef"]
    assert ajeno["contrato"]["del_emisor"] is False
    assert ajeno["contrato"]["otros"] == ["031-2021 — TERCERA CONSULTORA FICTICIA"]
    assert ajeno["resolucion"] == {"numero": "456-2021-MF", "fecha": "2021-12-20",
                                   "coincide_emisor": "nombra_otro",
                                   "fecha_descartada": None, "fecha_motivo": None}
    assert "Contrato N° 030-2021" in ajeno["texto"]

    assert exps[1]["fuente_mef"]["contrato"] is None
    assert "no dispone de contrato/resolución utilizable" in exps[1]["fuente_mef"]["texto"]
    assert "no publica" not in exps[1]["fuente_mef"]["texto"].lower()


def test_espejo_expone_la_evidencia_cruda_del_mef(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    assert exps[3]["resolucion_aprobacion"]["numero"] == "123-2021-MF"
    assert exps[1]["sin_documentos_mef"] is True
    assert exps[5]["identificacion_incompleta"] is True
    for clave in ("camino", "contrato_emisor", "cruces_fechas"):
        assert clave in exps[7], clave


def test_espejo_normaliza_copia_del_motivo_sin_alterar_resultado(job):
    api, job_id = job
    _, exps = _experiencias(api, job_id)
    cruce = exps[1]["cruces_fechas"][0]
    assert cruce == {
        "regla": "FECHA_APROBACION_ET", "resultado": "por_confirmar",
        "motivo": ("Este análisis no dispone de una resolución de aprobación "
                   "utilizable; no se puede comparar el término.")}
    modulo = importlib.import_module("api.app")
    original = modulo.repo.cargar_enriquecimiento(job_id)["1:1"]["cruces_fechas"][0]
    assert original["motivo"].startswith("El MEF no publica la resolución")
    assert original["resultado"] == cruce["resultado"]


def test_espejo_resume_la_certeza_del_profesional(job):
    api, job_id = job
    prof, _ = _experiencias(api, job_id)
    assert prof["certeza"] == {
        "citado_confirmado": {"experiencias": 2, "dias": 363},
        "inferido": {"experiencias": 2, "dias": 395},
        "sin_identificar": {"experiencias": 2, "dias": 362},
        "privada": {"experiencias": 1, "dias": 182},
        "dias_efectivos": 1272, "dias_traslape": 30,
    }


def test_resumen_trae_la_misma_certeza_y_el_tipo_de_evaluacion(job):
    api, job_id = job
    r = api.get(f"/api/pivote/jobs/{job_id}/resumen")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["tipo_evaluacion"] == "expedientes"
    veredicto = cuerpo["veredictos"][0]
    prof, _ = _experiencias(api, job_id)
    assert veredicto["certeza"] == prof["certeza"]


def test_un_concurso_de_obras_no_cambia(cliente):
    """El caso «obras» conserva su contrato: sin bloques de certeza."""
    api, modulo = cliente
    espejo = _espejo()
    espejo["_meta"]["tipo_evaluacion"] = "obras"
    r = api.post("/api/pivote/concursos",
                 json={"nomenclatura": "CP-OBRAS/2026", "entidad": "Entidad Ficticia"})
    r = api.post("/api/pivote/analizar",
                 data={"concurso_id": r.json()["concurso_id"]},
                 files={"espejo": ("espejo.json", io.BytesIO(
                            json.dumps(espejo).encode("utf-8")), "application/json"),
                        "excel": ("claude.xlsx", io.BytesIO(b"PK demo"),
                                  "application/octet-stream")})
    assert r.status_code == 201, r.text
    job_id = r.json()["job_id"]
    modulo.repo.guardar_enriquecimiento(job_id, _enriquecimiento())

    cuerpo = api.get(f"/api/pivote/jobs/{job_id}/espejo").json()
    assert cuerpo["tipo_evaluacion"] == "obras"
    prof = cuerpo["profesionales"][0]
    assert prof["certeza"] is None
    assert all("identificacion" not in e and "fuente_mef" not in e
               for e in prof["experiencias"])
    resumen = api.get(f"/api/pivote/jobs/{job_id}/resumen").json()
    assert resumen["tipo_evaluacion"] == "obras"
    assert resumen["veredictos"][0]["certeza"] is None
