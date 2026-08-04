"""Caché por job del corpus documental de cada obra de InfoObras."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from orquestador.descargas_seace import (
    es_archivo_seace, lock_para_descarga, materializar_archivo,
)

_MARCA = ".completa"
_ESTADO = ".estado.json"
_INFORMES = "Informes de control"


@dataclass(frozen=True)
class ResultadoCacheInfoObras:
    cache_hit: bool
    directorio: Path
    estado: dict[str, Any]


@dataclass(frozen=True)
class ResultadoMaterializacion:
    archivos: int
    informes: int


def _clave_obra(obra_id: int | str) -> str:
    clave = re.sub(r"[^0-9A-Za-z._-]", "-", str(obra_id)).strip(".-")
    if not clave:
        raise ValueError("obra_id vacío o inválido")
    return clave[:120]


def _anio_nombre_informe(nombre: str) -> int | None:
    coincidencia = re.match(r"\s*(\d{4})\s+-", nombre)
    return int(coincidencia.group(1)) if coincidencia else None


def informe_en_periodo(nombre: str, fecha_ini: date | None,
                       fecha_fin: date | None) -> bool:
    """Replica la semántica histórica: filtro inclusivo por AÑO, no por día."""
    if fecha_ini is None or fecha_fin is None:
        return True
    anio = _anio_nombre_informe(nombre)
    if anio is None:
        return True
    inferior, superior = sorted((fecha_ini.year, fecha_fin.year))
    return inferior <= anio <= superior


class CacheDescargasInfoObras:
    """Descarga una obra una vez y materializa árboles por experiencia."""

    def __init__(self, directorio: Path):
        self.directorio = Path(directorio)

    def obtener(
        self,
        obra_id: int | str,
        *,
        descargar: Callable[[Path], dict[str, Any] | None],
    ) -> ResultadoCacheInfoObras:
        destino = self.directorio / _clave_obra(obra_id)
        with lock_para_descarga(destino):
            return self._obtener_bajo_lock(destino, descargar)

    def _obtener_bajo_lock(
        self,
        destino: Path,
        descargar: Callable[[Path], dict[str, Any] | None],
    ) -> ResultadoCacheInfoObras:
        marca, estado_ruta = destino / _MARCA, destino / _ESTADO
        if marca.is_file() and estado_ruta.is_file():
            try:
                estado = json.loads(estado_ruta.read_text(encoding="utf-8"))
                return ResultadoCacheInfoObras(True, destino, estado)
            except (OSError, json.JSONDecodeError):
                pass

        self.directorio.mkdir(parents=True, exist_ok=True)
        if destino.exists():
            shutil.rmtree(destino)
        temporal = self.directorio / f".{destino.name}.{uuid.uuid4().hex}.part"
        temporal.mkdir(parents=True)
        try:
            estado = descargar(temporal) or {}
            (temporal / _ESTADO).write_text(
                json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (temporal / _MARCA).write_text("ok\n", encoding="utf-8")
            os.replace(temporal, destino)
        finally:
            if temporal.exists():
                shutil.rmtree(temporal)
        return ResultadoCacheInfoObras(False, destino, estado)

    def materializar(
        self,
        resultado: ResultadoCacheInfoObras,
        destino: Path,
        *,
        fecha_ini: date | None,
        fecha_fin: date | None,
    ) -> ResultadoMaterializacion:
        """Copia el árbol completo salvo informes fuera del periodo certificado."""
        origen, destino = resultado.directorio, Path(destino)
        # La carpeta P/E solo mezcla dos fuentes. Al rematerializar InfoObras se
        # preservan los archivos SEACE (nombres actuales e históricos: hay jobs
        # en disco con el prefijo `SEACE_0…` y regenerar su ZIP no puede
        # borrarlos) y se elimina cualquier resto de un corpus anterior, incluso
        # una sección que ahora quedó vacía.
        if destino.is_dir():
            for anterior in destino.iterdir():
                if es_archivo_seace(anterior.name):
                    continue
                if anterior.is_dir():
                    shutil.rmtree(anterior)
                else:
                    anterior.unlink()

        archivos = informes = 0
        for archivo in sorted(origen.rglob("*")):
            if not archivo.is_file() or archivo.name in {_MARCA, _ESTADO}:
                continue
            relativa = archivo.relative_to(origen)
            es_informe = relativa.parts[0] == _INFORMES
            if es_informe and not informe_en_periodo(
                    archivo.name, fecha_ini, fecha_fin):
                continue
            materializar_archivo(archivo, destino / relativa)
            archivos += 1
            informes += int(es_informe)
        return ResultadoMaterializacion(archivos, informes)
