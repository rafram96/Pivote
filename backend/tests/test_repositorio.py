"""
Tests del protocolo Repositorio — mismas semánticas en las 3 implementaciones.

Memoria y Archivos corren offline siempre. PostgreSQL se prueba SOLO si hay una
BD alcanzable en PIVOTE_TEST_DB_URL (en el server del cliente, o local con
`docker run -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:16-alpine` →
PIVOTE_TEST_DB_URL=postgresql://postgres:test@localhost:5433/postgres).
"""
from __future__ import annotations

import os

import pytest

from orquestador import RepositorioArchivos, RepositorioMemoria
from schemas import pipeline

ESPEJO = {
    "_meta": {"analisis_id": "repo-001", "concurso": "CP-REPO", "postor": "POSTOR R"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "María Pérez",
         "colegiatura": "CIP 11111", "cumple": "SÍ — 5 años",
         "experiencias": [{"n": 1}, {"n": 2}]},
        {"n_prof": 2, "cargo": "ESP. ESTRUCTURAS", "nombre": "Juan Núñez",
         "experiencias": [{"n": 1}]},
    ],
}


def _repos(tmp_path):
    return [RepositorioMemoria(), RepositorioArchivos(tmp_path)]


def _job(jid="j-repo-1", **kw) -> pipeline.Job:
    return pipeline.Job(job_id=jid, analisis_id="a-1", **kw)


# ── decisiones (nuevo en el protocolo: antes app.py escribía el archivo directo) ──

def test_decisiones_roundtrip_y_default_vacio(tmp_path):
    for repo in _repos(tmp_path):
        assert repo.cargar_decisiones("nope") == {}
        repo.guardar_decisiones("j1", {"al-0": {"relevante": False, "razon": "ok"}})
        assert repo.cargar_decisiones("j1")["al-0"]["razon"] == "ok"


def test_decisiones_archivo_compatible_con_los_viejos(tmp_path):
    """Los {id}.decisiones.json que app.py escribió antes se siguen leyendo."""
    import json
    (tmp_path / "jx.decisiones.json").write_text(
        json.dumps({"al-9": {"relevante": True}}), encoding="utf-8")
    repo = RepositorioArchivos(tmp_path)
    assert repo.cargar_decisiones("jx")["al-9"]["relevante"] is True


def test_eliminar_borra_tambien_las_decisiones(tmp_path):
    for repo in _repos(tmp_path):
        repo.guardar(_job("j2"))
        repo.guardar_decisiones("j2", {"al-1": {"relevante": True}})
        repo.eliminar("j2")
        assert repo.cargar("j2") is None
        assert repo.cargar_decisiones("j2") == {}


# ── PostgreSQL (gateado: requiere BD alcanzable) ─────────────────────────────

_DB = os.getenv("PIVOTE_TEST_DB_URL")
pg = pytest.mark.skipif(not _DB, reason="sin PIVOTE_TEST_DB_URL (se prueba en el server)")


@pytest.fixture()
def repo_pg(tmp_path):
    from orquestador.repositorio_pg import RepositorioPostgres
    repo = RepositorioPostgres(_DB, dir_datos=tmp_path)
    # limpiar restos de corridas previas (BD de prueba compartida)
    with repo._pool.connection() as con:
        con.execute("DELETE FROM profesionales; DELETE FROM documentos; DELETE FROM jobs;")
    yield repo
    repo._pool.close()


@pg
def test_pg_job_roundtrip_y_listar(repo_pg):
    from schemas.pipeline import JobEstado
    repo_pg.guardar(_job("pg-1", estado=JobEstado.EN_PROCESO, concurso_id="c1"))
    j = repo_pg.cargar("pg-1")
    assert j is not None and j.estado == JobEstado.EN_PROCESO
    repo_pg.guardar(_job("pg-1", estado=JobEstado.COMPLETADO))   # upsert pisa
    assert repo_pg.cargar("pg-1").estado == JobEstado.COMPLETADO
    assert [x.job_id for x in repo_pg.listar()] == ["pg-1"]


@pg
def test_pg_documentos_roundtrip(repo_pg):
    repo_pg.guardar_espejo("pg-2", ESPEJO)
    assert repo_pg.cargar_espejo("pg-2")["_meta"]["analisis_id"] == "repo-001"
    repo_pg.guardar_enriquecimiento("pg-2", {"1:1": {"cui": "123"}})
    assert repo_pg.cargar_enriquecimiento("pg-2")["1:1"]["cui"] == "123"
    repo_pg.guardar_decisiones("pg-2", {"al-0": {"relevante": False}})
    assert repo_pg.cargar_decisiones("pg-2")["al-0"]["relevante"] is False
    c = pipeline.Concurso(concurso_id="c9", nomenclatura="CP-PG/2026")
    repo_pg.guardar_concurso(c)
    assert repo_pg.cargar_concurso("c9").nomenclatura == "CP-PG/2026"
    assert any(x.concurso_id == "c9" for x in repo_pg.listar_concursos())


@pg
def test_pg_busqueda_profesionales_sin_tildes(repo_pg):
    from schemas.pipeline import JobEstado
    repo_pg.guardar_concurso(pipeline.Concurso(concurso_id="cB", nomenclatura="CP-B/2026"))
    repo_pg.guardar(_job("pg-3", estado=JobEstado.COMPLETADO, concurso_id="cB",
                         postor="POSTOR R"))
    repo_pg.guardar_espejo("pg-3", ESPEJO)          # indexa 2 profesionales
    hits = repo_pg.buscar_profesionales("perez")     # sin tilde matchea "Pérez"
    assert len(hits) == 1
    h = hits[0]
    assert h["nombre"] == "María Pérez" and h["n_prof"] == 1
    assert h["n_experiencias"] == 2 and h["cumple"] == "SÍ — 5 años"
    assert h["concurso"] == "CP-B/2026" and h["estado_job"] == "completado"
    assert repo_pg.buscar_profesionales("nuñez") or repo_pg.buscar_profesionales("nunez")
    # re-guardar el espejo NO duplica el índice
    repo_pg.guardar_espejo("pg-3", ESPEJO)
    assert len(repo_pg.buscar_profesionales("perez")) == 1


@pg
def test_pg_eliminar_limpia_tablas_y_disco(repo_pg, tmp_path):
    repo_pg.guardar(_job("pg-4"))
    repo_pg.guardar_espejo("pg-4", ESPEJO)
    (tmp_path / "pg-4.final.xlsx").write_bytes(b"PK")   # binario en disco
    repo_pg.eliminar("pg-4")
    assert repo_pg.cargar("pg-4") is None
    assert repo_pg.cargar_espejo("pg-4") is None
    assert repo_pg.buscar_profesionales("perez") == []
    assert not (tmp_path / "pg-4.final.xlsx").exists()
