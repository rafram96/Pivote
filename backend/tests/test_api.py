"""
Tests de la API HTTP (FastAPI + TestClient) — el flujo completo que la demo
recorre: crear concurso → subir análisis → pipeline corre → ver job/extracción/
resumen → resolver revisión → descargar Excel final y ZIP. Sin red externa
(etapas del esqueleto: ingesta real + stubs).
"""
from __future__ import annotations

import importlib
import io
import json
import zipfile

import pytest


ESPEJO = {
    "_meta": {"analisis_id": "api-demo-001", "concurso": "CP-API/2026",
              "postor": "POSTOR API DEMO"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "Profesional Uno",
         "colegiatura": "CIP 12345", "cumple": "SÍ — 4.51 años",
         "total": {"dias": 1645, "anios": 4.51},
         "experiencias": [
             {"n": 1, "proyecto": "Obra API A", "entidad_emisora": "Entidad A",
              "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
              "dias": 724, "cui": "2418877", "folio": "100"},
         ]},
    ],
    "resumen_evaluacion": {"factores": [{"factor": "A", "puntaje": 55}],
                           "puntaje_total": 55},
}


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """App fresca con datos en tmp_path (aisla cada test)."""
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")  # sin red en tests
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app)


def _subir(cliente, concurso_id: str):
    return cliente.post("/api/pivote/analizar", data={"concurso_id": concurso_id},
                        files={
                            "espejo": ("espejo.json", io.BytesIO(
                                json.dumps(ESPEJO).encode("utf-8")), "application/json"),
                            "excel": ("claude.xlsx", io.BytesIO(b"PK demo"), "application/octet-stream"),
                        })


def test_flujo_completo_de_la_demo(cliente):
    # 1 · crear concurso
    r = cliente.post("/api/pivote/concursos",
                     json={"nomenclatura": "CP-API/2026", "entidad": "Entidad Demo"})
    assert r.status_code == 201
    cid = r.json()["concurso_id"]

    # 2 · subir análisis (el pipeline corre como tarea de fondo del TestClient)
    r = _subir(cliente, cid)
    assert r.status_code == 201
    job_id = r.json()["job_id"]

    # 3 · job procesado: 8 pasos OK (esqueleto), estado completado
    r = cliente.get(f"/api/pivote/jobs/{job_id}")
    assert r.status_code == 200
    job = r.json()
    assert job["estado"] == "completado"
    assert len(job["etapas"]) == 8
    assert job["origen"] == "dropzone"

    # 4 · el concurso lista el job
    r = cliente.get(f"/api/pivote/concursos/{cid}")
    assert r.json()["jobs"][0]["job_id"] == job_id
    r = cliente.get("/api/pivote/concursos")
    assert r.json()[0]["n_jobs"] == 1

    # 5 · extracción (profesionales/experiencias para el panel)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/espejo")
    profs = r.json()["profesionales"]
    assert profs[0]["cargo"] == "JEFE DE SUPERVISIÓN"
    assert profs[0]["experiencias"][0]["cui"] == "2418877"

    # 6 · resumen (veredictos + factores)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/resumen")
    res = r.json()
    assert res["puntaje_total"] == 55
    assert res["veredictos"][0]["cumple_claude"].startswith("SÍ")

    # 7 · Excel final REAL descargable (CLAUDE + Base de Datos + hoja del prof)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/excel")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[:2] == ["CLAUDE", "Base de Datos"]
    assert any(n.startswith("P1 ") for n in wb.sheetnames)

    # 8 · ZIP InfoObras descargable (árbol de 4 niveles, sin docs aún)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/zip")
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert any(n.endswith("SIN_DOCUMENTOS.txt") for n in zf.namelist())


def test_espejo_invalido_rechazado_con_errores_claros(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "X"}).json()["concurso_id"]
    roto = {"_meta": {"analisis_id": "x"}, "postor": {}, "profesionales": []}
    r = cliente.post("/api/pivote/analizar", data={"concurso_id": cid},
                     files={
                         "espejo": ("e.json", io.BytesIO(json.dumps(roto).encode()), "application/json"),
                         "excel": ("c.xlsx", io.BytesIO(b"PK"), "application/octet-stream"),
                     })
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert detalle["error"].startswith("el archivo de datos")
    assert detalle["errores"]  # lista campo a campo


def test_decision_de_alerta_persiste(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "Y"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    # sin alertas en el esqueleto: decidir una inexistente igual persiste el registro
    r = cliente.post(f"/api/pivote/jobs/{job_id}/alertas",
                     json={"alerta_id": "al-0", "relevante": False, "razon": "verificado a mano"})
    assert r.status_code == 200


def test_revision_inexistente_404(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "Z"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    r = cliente.post(f"/api/pivote/jobs/{job_id}/revision",
                     json={"n_prof": 9, "n_exp": 9, "cui": "123"})
    assert r.status_code == 404
