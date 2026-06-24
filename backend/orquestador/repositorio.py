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
import shutil
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from schemas import pipeline


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

    def eliminar(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._espejos.pop(job_id, None)
        self._espejos.pop(f"enr-{job_id}", None)

    def eliminar_concurso(self, concurso_id: str) -> None:
        self._concursos.pop(concurso_id, None)


class RepositorioArchivos:
    """Para desarrollo local: un JSON por job en un directorio.
    `<dir>/<job_id>.job.json` + `<dir>/<job_id>.espejo.json`."""

    def __init__(self, directorio: Path):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _ruta(self, job_id: str, tipo: str) -> Path:
        return self.dir / f"{job_id}.{tipo}.json"

    def guardar(self, job: pipeline.Job) -> None:
        self._ruta(job.job_id, "job").write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def cargar(self, job_id: str) -> Optional[pipeline.Job]:
        ruta = self._ruta(job_id, "job")
        if not ruta.exists():
            return None
        return pipeline.Job.model_validate_json(ruta.read_text(encoding="utf-8"))

    def listar(self) -> list[pipeline.Job]:
        return [
            pipeline.Job.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(self.dir.glob("*.job.json"))
        ]

    def guardar_espejo(self, job_id: str, espejo: dict) -> None:
        self._ruta(job_id, "espejo").write_text(
            json.dumps(espejo, ensure_ascii=False, indent=1), encoding="utf-8")

    def cargar_espejo(self, job_id: str) -> Optional[dict]:
        ruta = self._ruta(job_id, "espejo")
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None

    def guardar_concurso(self, concurso: pipeline.Concurso) -> None:
        self._ruta(concurso.concurso_id, "concurso").write_text(
            concurso.model_dump_json(indent=2), encoding="utf-8")

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
        self._ruta(job_id, "enriquecimiento").write_text(
            json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    def cargar_enriquecimiento(self, job_id: str) -> dict:
        ruta = self._ruta(job_id, "enriquecimiento")
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    def eliminar(self, job_id: str) -> None:
        """Borra TODOS los artefactos del job: .job/.espejo/.enriquecimiento.json,
        .claude.xlsx, .final.xlsx, .infoobras.zip y las carpetas .certs/.descargas."""
        for p in self.dir.glob(f"{job_id}.*"):
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


# La implementación PostgreSQL vive en el servidor (tabla jobs JSONB + espejos).
# Se implementa al cablear PERSISTENCIA; el motor no cambia: depende del protocolo.
