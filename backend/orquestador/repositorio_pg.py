"""
RepositorioPostgres — RESPALDO LÓGICO del orquestador en PostgreSQL (3 tablas).

Rol (decisión 2026-07-11): NO reemplaza a los archivos — los espeja. Los archivos
(RepositorioArchivos) siguen siendo la fuente de verdad; este repo recibe cada
escritura vía RepositorioConRespaldo (write-through best-effort) y sirve como
respaldo restaurable + copia consultable (pg_dump, SQL ad-hoc).

Diseño "básico" acordado con el cliente (2026-06-25, sin modelado relacional):

  jobs           el registro del análisis; `concurso_id` y `estado` como columnas
                 planas porque son los DOS únicos filtros reales del sistema
                 (listar por concurso, reanudar en_proceso al arrancar).
  documentos     JSONB genérico (clave, tipo) para todo lo que se lee/escribe
                 completo por id: espejo · enriquecimiento · concurso · decisiones.
  profesionales  índice DERIVADO del espejo para la búsqueda global del panel;
                 se regenera al guardar el espejo. Columnas *_norm pre-normalizadas
                 en Python (sin tildes/minúsculas) → LIKE simple, sin extensiones.

Los binarios (Excels, ZIPs, PDFs de certs/ y descargas/) NO viven en la BD ni
los toca este repo: viven en la carpeta del job y los administra el primario.

Activación: PIVOTE_DB_URL en el entorno (api/app.py envuelve el repo de archivos
con RepositorioConRespaldo). psycopg se importa perezoso para que este módulo sea
importable en máquinas sin la lib (esta laptop corre solo con archivos).
"""
from __future__ import annotations

import json
import unicodedata
from typing import Optional

from schemas import pipeline

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          text PRIMARY KEY,
    concurso_id     text,
    estado          text,
    datos           jsonb NOT NULL,
    creado_en       timestamptz,
    actualizado_en  timestamptz
);
CREATE INDEX IF NOT EXISTS jobs_concurso_idx ON jobs (concurso_id);
CREATE INDEX IF NOT EXISTS jobs_estado_idx   ON jobs (estado);

CREATE TABLE IF NOT EXISTS documentos (
    clave           text NOT NULL,
    tipo            text NOT NULL,
    datos           jsonb NOT NULL,
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (clave, tipo)
);

CREATE TABLE IF NOT EXISTS profesionales (
    job_id           text NOT NULL,
    n_prof           int  NOT NULL,
    nombre           text,
    colegiatura      text,
    cargo            text,
    nombre_norm      text,
    colegiatura_norm text,
    cargo_norm       text,
    datos            jsonb NOT NULL,
    PRIMARY KEY (job_id, n_prof)
);
CREATE INDEX IF NOT EXISTS profesionales_nombre_idx ON profesionales (nombre_norm);
"""


def sin_tildes(s: str) -> str:
    """Minúsculas y sin tildes — misma normalización que la búsqueda del panel."""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c)).lower()


class RepositorioPostgres:
    """Implementa el protocolo `Repositorio` sobre PostgreSQL (upserts idempotentes,
    mismas semánticas que RepositorioArchivos)."""

    def __init__(self, dsn: str):
        # import perezoso: psycopg solo se exige donde este repo realmente corre
        from psycopg_pool import ConnectionPool
        self._pool = ConnectionPool(dsn, min_size=1, max_size=4, open=True)
        with self._pool.connection() as con:
            con.execute(_DDL)

    def _jsonb(self, datos):
        from psycopg.types.json import Jsonb
        return Jsonb(datos)

    # ── jobs ──────────────────────────────────────────────────────────────────

    def guardar(self, job: pipeline.Job) -> None:
        datos = json.loads(job.model_dump_json())
        with self._pool.connection() as con:
            con.execute(
                """INSERT INTO jobs (job_id, concurso_id, estado, datos, creado_en, actualizado_en)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (job_id) DO UPDATE SET
                     concurso_id = EXCLUDED.concurso_id, estado = EXCLUDED.estado,
                     datos = EXCLUDED.datos, actualizado_en = EXCLUDED.actualizado_en""",
                (job.job_id, job.concurso_id, getattr(job.estado, "value", job.estado),
                 self._jsonb(datos), job.creado_en, job.actualizado_en))

    def cargar(self, job_id: str) -> Optional[pipeline.Job]:
        with self._pool.connection() as con:
            fila = con.execute("SELECT datos FROM jobs WHERE job_id = %s",
                               (job_id,)).fetchone()
        return pipeline.Job.model_validate(fila[0]) if fila else None

    def listar(self) -> list[pipeline.Job]:
        with self._pool.connection() as con:
            filas = con.execute(
                "SELECT datos FROM jobs ORDER BY creado_en NULLS FIRST, job_id").fetchall()
        return [pipeline.Job.model_validate(f[0]) for f in filas]

    # ── documentos JSONB (espejo · enriquecimiento · concurso · decisiones) ──

    def _guardar_doc(self, clave: str, tipo: str, datos: dict) -> None:
        with self._pool.connection() as con:
            con.execute(
                """INSERT INTO documentos (clave, tipo, datos) VALUES (%s, %s, %s)
                   ON CONFLICT (clave, tipo) DO UPDATE SET
                     datos = EXCLUDED.datos, actualizado_en = now()""",
                (clave, tipo, self._jsonb(datos)))

    def _cargar_doc(self, clave: str, tipo: str) -> Optional[dict]:
        with self._pool.connection() as con:
            fila = con.execute(
                "SELECT datos FROM documentos WHERE clave = %s AND tipo = %s",
                (clave, tipo)).fetchone()
        return fila[0] if fila else None

    def guardar_espejo(self, job_id: str, espejo: dict) -> None:
        self._guardar_doc(job_id, "espejo", espejo)
        self._indexar_profesionales(job_id, espejo)

    def cargar_espejo(self, job_id: str) -> Optional[dict]:
        return self._cargar_doc(job_id, "espejo")

    def guardar_enriquecimiento(self, job_id: str, datos: dict) -> None:
        self._guardar_doc(job_id, "enriquecimiento", datos)

    def cargar_enriquecimiento(self, job_id: str) -> dict:
        return self._cargar_doc(job_id, "enriquecimiento") or {}

    def guardar_decisiones(self, job_id: str, datos: dict) -> None:
        self._guardar_doc(job_id, "decisiones", datos)

    def cargar_decisiones(self, job_id: str) -> dict:
        return self._cargar_doc(job_id, "decisiones") or {}

    def guardar_concurso(self, concurso: pipeline.Concurso) -> None:
        self._guardar_doc(concurso.concurso_id, "concurso",
                          json.loads(concurso.model_dump_json()))

    def cargar_concurso(self, concurso_id: str) -> Optional[pipeline.Concurso]:
        datos = self._cargar_doc(concurso_id, "concurso")
        return pipeline.Concurso.model_validate(datos) if datos else None

    def listar_concursos(self) -> list[pipeline.Concurso]:
        with self._pool.connection() as con:
            filas = con.execute(
                "SELECT datos FROM documentos WHERE tipo = 'concurso' ORDER BY clave").fetchall()
        return [pipeline.Concurso.model_validate(f[0]) for f in filas]

    # ── índice de profesionales (búsqueda global del panel) ──────────────────

    def _indexar_profesionales(self, job_id: str, espejo: dict) -> None:
        """Regenera las filas del job desde el espejo (DELETE+INSERT en una tx:
        idempotente, y un re-guardado del espejo refresca el índice solo)."""
        filas = []
        for p in espejo.get("profesionales", []) or []:
            nombre = p.get("nombre")
            coleg = p.get("colegiatura")
            cargo = p.get("cargo")
            filas.append((
                job_id, p.get("n_prof") or 0, nombre, coleg, cargo,
                sin_tildes(str(nombre)) if nombre else None,
                sin_tildes(str(coleg)) if coleg else None,
                sin_tildes(str(cargo)) if cargo else None,
                self._jsonb({
                    "cumple": p.get("cumple"),
                    "n_experiencias": len(p.get("experiencias", []) or []),
                }),
            ))
        with self._pool.connection() as con:
            con.execute("DELETE FROM profesionales WHERE job_id = %s", (job_id,))
            if filas:
                con.cursor().executemany(
                    """INSERT INTO profesionales
                       (job_id, n_prof, nombre, colegiatura, cargo,
                        nombre_norm, colegiatura_norm, cargo_norm, datos)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""", filas)

    def buscar_profesionales(self, q: str) -> list[dict]:
        """Mismo shape que el escaneo de espejos del endpoint (una fila por
        aparición) pero resuelto con un LIKE indexable en vez de leer N espejos."""
        patron = f"%{sin_tildes(q)}%"
        with self._pool.connection() as con:
            filas = con.execute(
                """SELECT p.nombre, p.cargo, p.colegiatura, p.n_prof, p.datos,
                          j.job_id, j.estado, j.concurso_id,
                          COALESCE(c.datos->>'nomenclatura', j.datos->>'concurso'),
                          j.datos->>'postor'
                   FROM profesionales p
                   JOIN jobs j USING (job_id)
                   LEFT JOIN documentos c ON c.clave = j.concurso_id AND c.tipo = 'concurso'
                   WHERE p.nombre_norm LIKE %s OR p.colegiatura_norm LIKE %s
                      OR p.cargo_norm LIKE %s
                   ORDER BY p.nombre_norm NULLS LAST, j.job_id
                   LIMIT 50""",
                (patron, patron, patron)).fetchall()
        return [{
            "nombre": f[0], "cargo": f[1], "colegiatura": f[2], "n_prof": f[3],
            "cumple": (f[4] or {}).get("cumple"),
            "n_experiencias": (f[4] or {}).get("n_experiencias", 0),
            "job_id": f[5], "estado_job": f[6], "concurso_id": f[7],
            "concurso": f[8], "postor": f[9],
        } for f in filas]

    # ── borrado ───────────────────────────────────────────────────────────────

    def eliminar(self, job_id: str) -> None:
        """Borra las filas del job en las 3 tablas. Los binarios/archivos los borra
        el primario (RepositorioArchivos) — este repo es solo el respaldo lógico."""
        with self._pool.connection() as con:
            con.execute("DELETE FROM profesionales WHERE job_id = %s", (job_id,))
            con.execute("DELETE FROM documentos WHERE clave = %s", (job_id,))
            con.execute("DELETE FROM jobs WHERE job_id = %s", (job_id,))

    def eliminar_concurso(self, concurso_id: str) -> None:
        with self._pool.connection() as con:
            con.execute("DELETE FROM documentos WHERE clave = %s AND tipo = 'concurso'",
                        (concurso_id,))
