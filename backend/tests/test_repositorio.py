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


def test_migracion_layout_suelto_a_carpetas(tmp_path):
    """El layout viejo (todo suelto: {id}.job.json, {id}.espejo.json, {id}.claude.xlsx,
    {id}.certs/, {id}.decisiones.json) se migra a la carpeta {id}/ al construir el
    repo — y todo se sigue leyendo igual. Idempotente en el segundo arranque."""
    import json
    j = _job("jm")
    (tmp_path / "jm.job.json").write_text(j.model_dump_json(), encoding="utf-8")
    (tmp_path / "jm.espejo.json").write_text(json.dumps(ESPEJO), encoding="utf-8")
    (tmp_path / "jm.decisiones.json").write_text(
        json.dumps({"al-9": {"relevante": True}}), encoding="utf-8")
    (tmp_path / "jm.claude.xlsx").write_bytes(b"PK")
    (tmp_path / "jm.certs").mkdir()
    (tmp_path / "jm.certs" / "P1_E1.pdf").write_bytes(b"%PDF")
    (tmp_path / "otro.concurso.json").write_text("{}", encoding="utf-8")

    repo = RepositorioArchivos(tmp_path)                      # ← migra al construir
    assert repo.cargar("jm").job_id == "jm"
    assert repo.cargar_espejo("jm")["_meta"]["analisis_id"] == "repo-001"
    assert repo.cargar_decisiones("jm")["al-9"]["relevante"] is True
    assert (tmp_path / "jm" / "claude.xlsx").exists()
    assert (tmp_path / "jm" / "certs" / "P1_E1.pdf").exists()
    assert not (tmp_path / "jm.job.json").exists()            # ya no hay sueltos
    assert (tmp_path / "otro.concurso.json").exists()          # concursos quedan en raíz
    RepositorioArchivos(tmp_path)                              # 2º arranque: no-op
    assert repo.cargar("jm") is not None


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
def repo_pg():
    from orquestador.repositorio_pg import RepositorioPostgres
    repo = RepositorioPostgres(_DB)
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
def test_pg_eliminar_limpia_las_tablas(repo_pg):
    # solo tablas: los archivos/binarios los borra el PRIMARIO (es respaldo lógico)
    repo_pg.guardar(_job("pg-4"))
    repo_pg.guardar_espejo("pg-4", ESPEJO)
    repo_pg.eliminar("pg-4")
    assert repo_pg.cargar("pg-4") is None
    assert repo_pg.cargar_espejo("pg-4") is None
    assert repo_pg.buscar_profesionales("perez") == []


# ── RepositorioConRespaldo (archivos = verdad · pg = espejo write-through) ────

class _RespaldoEspia:
    """Respaldo fake: registra llamadas; opcionalmente falla SIEMPRE."""
    def __init__(self, falla=False):
        self.llamadas: list[tuple] = []
        self._falla = falla

    def __getattr__(self, nombre):
        def _metodo(*args):
            if self._falla:
                raise RuntimeError("pg caído")
            self.llamadas.append((nombre, args))
        return _metodo


def test_respaldo_recibe_cada_escritura_y_lecturas_van_al_primario(tmp_path):
    from orquestador.repositorio import RepositorioConRespaldo
    espia = _RespaldoEspia()
    repo = RepositorioConRespaldo(RepositorioArchivos(tmp_path), espia)

    repo.guardar(_job("jw"))
    repo.guardar_espejo("jw", ESPEJO)
    repo.guardar_decisiones("jw", {"al-0": {"relevante": True}})
    repo.eliminar("jw")

    assert [n for n, _ in espia.llamadas] == [
        "guardar", "guardar_espejo", "guardar_decisiones", "eliminar"]
    # las lecturas NO tocan el respaldo (van al primario)
    repo.guardar(_job("jw2"))
    espia.llamadas.clear()
    assert repo.cargar("jw2") is not None
    assert repo.listar()[0].job_id == "jw2"
    assert repo.cargar_espejo("jw2") is None
    assert espia.llamadas == []


def test_respaldo_caido_no_frena_la_operacion(tmp_path):
    """La regla de oro: si Postgres se cae, el análisis SIGUE sobre archivos."""
    from orquestador.repositorio import RepositorioConRespaldo
    repo = RepositorioConRespaldo(RepositorioArchivos(tmp_path), _RespaldoEspia(falla=True))
    repo.guardar(_job("jf"))                      # no lanza pese al respaldo roto
    repo.guardar_espejo("jf", ESPEJO)
    assert repo.cargar("jf").job_id == "jf"       # el primario tiene todo
    assert repo.cargar_espejo("jf")["_meta"]["analisis_id"] == "repo-001"
