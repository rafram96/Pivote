"""
Persistencia del orquestador detrás de una interfaz.

En el servidor, la implementación es PostgreSQL (constraint del proyecto).
Para desarrollo y tests offline en esta máquina se usan las implementaciones
en memoria y en archivos JSON — mismas semánticas, cero infraestructura.

El espejo se guarda APARTE del Job (el registro del job es liviano; el espejo
de un análisis real pesa ~100 KB).
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from schemas import pipeline


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Escribe `texto` de forma ATÓMICA: a un tmp en el mismo directorio y luego
    `os.replace`. Evita que un lector concurrente (otro request, la etapa de
    descargas) lea un archivo a medio escribir (JSON truncado) y que dos escritores
    dejen contenido mezclado. El tmp lleva un sufijo único (uuid) para no colisionar
    entre hilos/procesos que guarden el mismo archivo a la vez."""
    tmp = ruta.with_name(f"{ruta.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, ruta)          # atómico en el mismo filesystem
    finally:
        try:
            tmp.unlink(missing_ok=True)   # limpia el tmp si os.replace falló
        except OSError:
            pass


@runtime_checkable
class Repositorio(Protocol):
    def guardar(self, job: pipeline.Job) -> None: ...
    def cargar(self, job_id: str) -> Optional[pipeline.Job]: ...
    def listar(self) -> list[pipeline.Job]: ...
    def guardar_espejo(self, job_id: str, espejo: dict) -> None: ...
    def cargar_espejo(self, job_id: str) -> Optional[dict]: ...
    def guardar_concurso(self, concurso: pipeline.Concurso) -> None: ...
    def cargar_concurso(self, concurso_id: str) -> Optional[pipeline.Concurso]: ...
    def listar_concursos(self) -> list[pipeline.Concurso]: ...
    def guardar_enriquecimiento(self, job_id: str, datos: dict) -> None: ...
    def cargar_enriquecimiento(self, job_id: str) -> dict: ...
    def guardar_decisiones(self, job_id: str, datos: dict) -> None: ...
    def cargar_decisiones(self, job_id: str) -> dict: ...
    def eliminar(self, job_id: str) -> None: ...
    def eliminar_concurso(self, concurso_id: str) -> None: ...


class RepositorioMemoria:
    """Para tests. Sin estado compartido entre instancias."""

    def __init__(self):
        self._jobs: dict[str, str] = {}      # job_id → JSON (simula serialización)
        self._espejos: dict[str, str] = {}
        self._concursos: dict[str, str] = {}

    def guardar(self, job: pipeline.Job) -> None:
        self._jobs[job.job_id] = job.model_dump_json()

    def cargar(self, job_id: str) -> Optional[pipeline.Job]:
        crudo = self._jobs.get(job_id)
        return pipeline.Job.model_validate_json(crudo) if crudo else None

    def listar(self) -> list[pipeline.Job]:
        return [pipeline.Job.model_validate_json(j) for j in self._jobs.values()]

    def guardar_espejo(self, job_id: str, espejo: dict) -> None:
        self._espejos[job_id] = json.dumps(espejo, ensure_ascii=False)

    def cargar_espejo(self, job_id: str) -> Optional[dict]:
        crudo = self._espejos.get(job_id)
        return json.loads(crudo) if crudo else None

    def guardar_concurso(self, concurso: pipeline.Concurso) -> None:
        self._concursos[concurso.concurso_id] = concurso.model_dump_json()

    def cargar_concurso(self, concurso_id: str) -> Optional[pipeline.Concurso]:
        crudo = self._concursos.get(concurso_id)
        return pipeline.Concurso.model_validate_json(crudo) if crudo else None

    def listar_concursos(self) -> list[pipeline.Concurso]:
        return [pipeline.Concurso.model_validate_json(c) for c in self._concursos.values()]

    def guardar_enriquecimiento(self, job_id: str, datos: dict) -> None:
        self._espejos[f"enr-{job_id}"] = json.dumps(datos, ensure_ascii=False)

    def cargar_enriquecimiento(self, job_id: str) -> dict:
        crudo = self._espejos.get(f"enr-{job_id}")
        return json.loads(crudo) if crudo else {}

    def guardar_decisiones(self, job_id: str, datos: dict) -> None:
        self._espejos[f"dec-{job_id}"] = json.dumps(datos, ensure_ascii=False)

    def cargar_decisiones(self, job_id: str) -> dict:
        crudo = self._espejos.get(f"dec-{job_id}")
        return json.loads(crudo) if crudo else {}

    def eliminar(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._espejos.pop(job_id, None)
        self._espejos.pop(f"enr-{job_id}", None)
        self._espejos.pop(f"dec-{job_id}", None)

    def eliminar_concurso(self, concurso_id: str) -> None:
        self._concursos.pop(concurso_id, None)


def carpeta_job(base: Path, job_id: str) -> Path:
    """Carpeta ÚNICA del job: `<base>/<job_id>/` — TODOS sus artefactos (JSONs,
    Excels, ZIP, certs/, descargas/) viven ahí, en vez de sueltos en la raíz."""
    d = Path(base) / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


class RepositorioArchivos:
    """La FUENTE DE VERDAD de la persistencia (Postgres es solo respaldo lógico —
    ver RepositorioConRespaldo). Estructura: una carpeta por job (`<dir>/<job_id>/
    job.json|espejo.json|…`); los concursos, livianos y pocos, quedan en la raíz
    (`<dir>/<id>.concurso.json`). Migra solo el layout viejo (todo suelto)."""

    def __init__(self, directorio: Path):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._migrar_layout_suelto()

    def _migrar_layout_suelto(self) -> None:
        """Layout viejo → carpetas: `{id}.job.json` y hermanos (`{id}.espejo.json`,
        `{id}.claude.xlsx`, `{id}.certs/`, …) se mueven a `{id}/<nombre-sin-prefijo>`.
        Idempotente (sin `*.job.json` sueltos = no-op) y tolerante: un artefacto que
        no se pueda mover se queda donde está sin tumbar el arranque."""
        for f in list(self.dir.glob("*.job.json")):
            jid = f.name[: -len(".job.json")]
            destino = self.dir / jid
            destino.mkdir(exist_ok=True)
            for p in list(self.dir.glob(f"{jid}.*")):
                try:
                    p.rename(destino / p.name[len(jid) + 1:])
                except OSError:
                    pass  # en uso / ya existe → se queda; reintenta al próximo arranque

    def _ruta(self, job_id: str, tipo: str) -> Path:
        if tipo == "concurso":
            return self.dir / f"{job_id}.concurso.json"
        return carpeta_job(self.dir, job_id) / f"{tipo}.json"

    def guardar(self, job: pipeline.Job) -> None:
        _escribir_atomico(self._ruta(job.job_id, "job"), job.model_dump_json(indent=2))

    def cargar(self, job_id: str) -> Optional[pipeline.Job]:
        ruta = self._ruta(job_id, "job")
        if not ruta.exists():
            return None
        return pipeline.Job.model_validate_json(ruta.read_text(encoding="utf-8"))

    def listar(self) -> list[pipeline.Job]:
        return [
            pipeline.Job.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.dir.glob("*/job.json"))
        ]

    def guardar_espejo(self, job_id: str, espejo: dict) -> None:
        _escribir_atomico(self._ruta(job_id, "espejo"),
                          json.dumps(espejo, ensure_ascii=False, indent=1))

    def cargar_espejo(self, job_id: str) -> Optional[dict]:
        ruta = self._ruta(job_id, "espejo")
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None

    def guardar_concurso(self, concurso: pipeline.Concurso) -> None:
        _escribir_atomico(self._ruta(concurso.concurso_id, "concurso"),
                          concurso.model_dump_json(indent=2))

    def cargar_concurso(self, concurso_id: str) -> Optional[pipeline.Concurso]:
        ruta = self._ruta(concurso_id, "concurso")
        if not ruta.exists():
            return None
        return pipeline.Concurso.model_validate_json(ruta.read_text(encoding="utf-8"))

    def listar_concursos(self) -> list[pipeline.Concurso]:
        return [
            pipeline.Concurso.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.dir.glob("*.concurso.json"))
        ]

    def guardar_enriquecimiento(self, job_id: str, datos: dict) -> None:
        _escribir_atomico(self._ruta(job_id, "enriquecimiento"),
                          json.dumps(datos, ensure_ascii=False, indent=1))

    def cargar_enriquecimiento(self, job_id: str) -> dict:
        ruta = self._ruta(job_id, "enriquecimiento")
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    # Los {id}.decisiones.json viejos (los escribía app.py directo) llegan aquí
    # renombrados a {id}/decisiones.json por la migración de layout del arranque.
    def guardar_decisiones(self, job_id: str, datos: dict) -> None:
        _escribir_atomico(self._ruta(job_id, "decisiones"),
                          json.dumps(datos, ensure_ascii=False, indent=1))

    def cargar_decisiones(self, job_id: str) -> dict:
        ruta = self._ruta(job_id, "decisiones")
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    def eliminar(self, job_id: str) -> None:
        """Borra la carpeta ENTERA del job (JSONs, Excels, ZIP, certs, descargas)
        + cualquier resto del layout viejo que la migración no haya podido mover."""
        shutil.rmtree(self.dir / job_id, ignore_errors=True)
        for p in self.dir.glob(f"{job_id}.*"):
            if p.name.endswith(".concurso.json"):
                continue  # un concurso con el mismo id NO es artefacto del job
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except OSError:
                    pass

    def eliminar_concurso(self, concurso_id: str) -> None:
        try:
            self._ruta(concurso_id, "concurso").unlink()
        except OSError:
            pass


class RepositorioConRespaldo:
    """Archivos como FUENTE DE VERDAD + Postgres como RESPALDO LÓGICO (write-through).

    Decisión 2026-07-11: la BD NO reemplaza a los archivos — los espeja. Toda
    lectura va al primario (archivos); toda escritura va al primario y luego,
    best-effort, al respaldo: si Postgres está caído se loguea y la operación
    SIGUE (el análisis nunca se frena por el respaldo). Recuperación: si el
    respaldo estuvo caído un rato, `scripts/migrar_a_postgres.py` lo re-sincroniza
    completo (upserts idempotentes)."""

    def __init__(self, primario: "RepositorioArchivos", respaldo):
        self._p = primario
        self._r = respaldo

    def _respaldar(self, metodo: str, *args) -> None:
        import logging
        try:
            getattr(self._r, metodo)(*args)
        except Exception:  # noqa: BLE001 — el respaldo nunca tumba la operación
            logging.getLogger(__name__).exception("respaldo pg falló: %s", metodo)

    # escrituras: primario y luego espejo al respaldo
    def guardar(self, job: pipeline.Job) -> None:
        self._p.guardar(job)
        self._respaldar("guardar", job)

    def guardar_espejo(self, job_id: str, espejo: dict) -> None:
        self._p.guardar_espejo(job_id, espejo)
        self._respaldar("guardar_espejo", job_id, espejo)

    def guardar_concurso(self, concurso: pipeline.Concurso) -> None:
        self._p.guardar_concurso(concurso)
        self._respaldar("guardar_concurso", concurso)

    def guardar_enriquecimiento(self, job_id: str, datos: dict) -> None:
        self._p.guardar_enriquecimiento(job_id, datos)
        self._respaldar("guardar_enriquecimiento", job_id, datos)

    def guardar_decisiones(self, job_id: str, datos: dict) -> None:
        self._p.guardar_decisiones(job_id, datos)
        self._respaldar("guardar_decisiones", job_id, datos)

    def eliminar(self, job_id: str) -> None:
        self._p.eliminar(job_id)
        self._respaldar("eliminar", job_id)

    def eliminar_concurso(self, concurso_id: str) -> None:
        self._p.eliminar_concurso(concurso_id)
        self._respaldar("eliminar_concurso", concurso_id)

    # lecturas: SIEMPRE del primario (la verdad está en los archivos)
    def cargar(self, job_id: str):
        return self._p.cargar(job_id)

    def listar(self):
        return self._p.listar()

    def cargar_espejo(self, job_id: str):
        return self._p.cargar_espejo(job_id)

    def cargar_concurso(self, concurso_id: str):
        return self._p.cargar_concurso(concurso_id)

    def listar_concursos(self):
        return self._p.listar_concursos()

    def cargar_enriquecimiento(self, job_id: str) -> dict:
        return self._p.cargar_enriquecimiento(job_id)

    def cargar_decisiones(self, job_id: str) -> dict:
        return self._p.cargar_decisiones(job_id)
