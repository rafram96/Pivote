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
_MARCA_PARCIAL = ".parcial"
_ESTADO = ".estado.json"
_INFORMES = "Informes de control"
_TEMPORAL = re.compile(r"^\..+\.[0-9a-f]{8,}\.part$")

@dataclass(frozen=True)
class ResultadoCacheInfoObras:
    cache_hit: bool
    directorio: Path
    estado: dict[str, Any]
    completa: bool = True
    reintentadas: tuple[str, ...] = ()


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


def secciones_en_error(estado: dict[str, Any] | None) -> tuple[str, ...]:
    """Secciones que la descarga declaró caídas (`{"error": true}`) en un estado."""
    secciones = (estado or {}).get("secciones") or {}
    return tuple(
        nombre for nombre, datos in secciones.items()
        if isinstance(datos, dict) and datos.get("error")
    )


def _leer_estado(ruta: Path) -> dict[str, Any] | None:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def purgar_secciones_en_error(directorio: Path, obra_id: int | str) -> tuple[str, ...]:
    """Compatibilidad: una descarga publicada es terminal y nunca se purga."""
    return ()


class CacheDescargasInfoObras:
    """Descarga una obra una sola vez y reutiliza incluso un resultado parcial."""

    def __init__(self, directorio: Path):
        self.directorio = Path(directorio)

    def recolectar_temporales(self) -> int:
        """Borra los `.{obra}.{uuid}.part` que dejó un corte duro (issue #81, R4).

        Solo mira los hijos DIRECTOS de la caché y solo los que tienen forma de
        temporal nuestro: una entrada publicada nunca coincide con ese patrón.
        """
        if not self.directorio.is_dir():
            return 0
        recolectados = 0
        for hijo in sorted(self.directorio.iterdir()):
            if not hijo.is_dir() or not _TEMPORAL.match(hijo.name):
                continue
            shutil.rmtree(hijo, ignore_errors=True)
            recolectados += int(not hijo.exists())
        return recolectados

    def obtener(
        self,
        obra_id: int | str,
        *,
        descargar: Callable[[Path, frozenset[str] | None], dict[str, Any] | None],
    ) -> ResultadoCacheInfoObras:
        """`descargar` solo se invoca si nunca se publicó esa obra."""
        destino = self.directorio / _clave_obra(obra_id)
        with lock_para_descarga(destino):
            return self._obtener_bajo_lock(destino, descargar)

    def existente(self, obra_id: int | str) -> ResultadoCacheInfoObras | None:
        """Lee una entrada publicada sin reintentar secciones parciales."""
        destino = self.directorio / _clave_obra(obra_id)
        with lock_para_descarga(destino):
            marca, parcial = destino / _MARCA, destino / _MARCA_PARCIAL
            if not (marca.is_file() or parcial.is_file()):
                return None
            estado = _leer_estado(destino / _ESTADO)
            if estado is None:
                return None
            return ResultadoCacheInfoObras(
                True, destino, estado, marca.is_file(), ())

    def _obtener_bajo_lock(
        self,
        destino: Path,
        descargar: Callable[[Path, frozenset[str] | None], dict[str, Any] | None],
    ) -> ResultadoCacheInfoObras:
        marca, parcial = destino / _MARCA, destino / _MARCA_PARCIAL
        estado_previo = (_leer_estado(destino / _ESTADO)
                         if (marca.is_file() or parcial.is_file()) else None)
        if estado_previo is not None:
            return ResultadoCacheInfoObras(
                True, destino, estado_previo, marca.is_file(), ())
        pendientes: frozenset[str] = frozenset()

        self.directorio.mkdir(parents=True, exist_ok=True)
        temporal = self.directorio / f".{destino.name}.{uuid.uuid4().hex}.part"
        temporal.mkdir(parents=True)
        try:
            estado = descargar(temporal, None) or {}
            (temporal / _ESTADO).write_text(
                json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            completa = not secciones_en_error(estado)
            (temporal / (_MARCA if completa else _MARCA_PARCIAL)).write_text(
                "ok\n", encoding="utf-8")
            # Publicación atómica: un corte no deja una entrada ambigua.
            if destino.exists():
                shutil.rmtree(destino)
            os.replace(temporal, destino)
        finally:
            if temporal.exists():
                shutil.rmtree(temporal)
        return ResultadoCacheInfoObras(
            False, destino, estado, completa, tuple(sorted(pendientes)))

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
            if not archivo.is_file() or archivo.name in {_MARCA, _MARCA_PARCIAL, _ESTADO}:
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
