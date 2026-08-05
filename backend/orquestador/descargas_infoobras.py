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

# La sección PRINCIPAL (valorizaciones por hito + documentos obra-level) no vive
# en una carpeta propia: se reparte por todo el árbol. Las demás sí tienen su
# carpeta, y su nombre es EXACTAMENTE el nombre de la sección — por eso un
# reintento selectivo puede tirar solo lo suyo.
SECCION_PRINCIPAL = "InfoObras"
SECCIONES_CON_CARPETA = (
    _INFORMES, "Datos de cierre", "Aprobación del expediente", "Verificación MEF",
)


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


def _conservar_en_clon(nombre: str, pendientes: frozenset[str]) -> bool:
    """¿Esta carpeta de primer nivel sobrevive al reintento selectivo?

    Se tira lo de las secciones que se van a reintentar (para no dejar restos de
    una descarga a medias) y se conserva TODO lo demás por enlace duro: reintentar
    una sección jamás vuelve a bajar las sanas.
    """
    if nombre in pendientes:
        return False
    # La principal no tiene carpeta propia: si se reintenta, se rehace todo lo
    # que no pertenezca a una sección con carpeta.
    return not (SECCION_PRINCIPAL in pendientes
                and nombre not in SECCIONES_CON_CARPETA)


def _clonar_secciones_sanas(origen: Path, destino: Path,
                            pendientes: frozenset[str]) -> None:
    for hijo in sorted(origen.iterdir()):
        if hijo.name in {_MARCA, _MARCA_PARCIAL, _ESTADO}:
            continue
        if not _conservar_en_clon(hijo.name, pendientes):
            continue
        if hijo.is_dir():
            for archivo in sorted(hijo.rglob("*")):
                if archivo.is_file():
                    materializar_archivo(
                        archivo, destino / archivo.relative_to(origen))
        elif hijo.is_file():
            materializar_archivo(hijo, destino / hijo.name)


def _fusionar_estado(viejo: dict[str, Any], nuevo: dict[str, Any],
                     pendientes: frozenset[str]) -> dict[str, Any]:
    """Estado del reintento: lo sano del anterior + lo que devolvió el reintento."""
    secciones = dict(viejo.get("secciones") or {})
    secciones.update(nuevo.get("secciones") or {})
    # Los avisos de una sección reintentada caducan con ella (arrancan con
    # "«Sección»: …"); los de las sanas se conservan tal cual.
    avisos = [a for a in (viejo.get("avisos") or [])
              if not any(str(a).startswith(f"{s}:") for s in pendientes)]
    for aviso in nuevo.get("avisos") or []:
        if aviso not in avisos:
            avisos.append(aviso)
    informes = (nuevo.get("informes_anios") if _INFORMES in pendientes
                else viejo.get("informes_anios")) or []
    return {"secciones": secciones, "avisos": avisos, "informes_anios": informes}


def purgar_secciones_en_error(directorio: Path, obra_id: int | str) -> tuple[str, ...]:
    """Deja la entrada de caché de una obra lista para reintentar lo que falló.

    La usa la resolución de una revisión: invalidar `P{n}_E{m}/` no basta si el
    corpus de la obra quedó guardado con una sección caída. Borra lo de las
    secciones en error y degrada la marca a `.parcial` — incluso si la entrada
    venía marcada `.completa` por una versión anterior del backend, que es
    justamente el caso que un evaluador no podía desatascar.

    Devuelve las secciones que quedaron pendientes ( `()` si no había nada que
    purgar: una caché sana se reutiliza tal cual y la revisión no re-descarga).
    """
    destino = Path(directorio) / _clave_obra(obra_id)
    with lock_para_descarga(destino):
        estado = _leer_estado(destino / _ESTADO)
        pendientes = tuple(secciones_en_error(estado))
        if not pendientes:
            return ()
        for hijo in sorted(destino.iterdir()):
            if hijo.name in {_MARCA, _MARCA_PARCIAL, _ESTADO}:
                continue
            if _conservar_en_clon(hijo.name, frozenset(pendientes)):
                continue
            if hijo.is_dir():
                shutil.rmtree(hijo, ignore_errors=True)
            else:
                hijo.unlink(missing_ok=True)
        (destino / _MARCA_PARCIAL).write_text("ok\n", encoding="utf-8")
        (destino / _MARCA).unlink(missing_ok=True)
        return pendientes


class CacheDescargasInfoObras:
    """Descarga una obra una vez y materializa árboles por experiencia.

    Estados de una entrada (issue #81, R1):

    - `.completa` — todas las secciones se bajaron sin error. Se reutiliza tal
      cual, sin tocar la fuente (también las publicadas por versiones anteriores).
    - `.parcial` — al menos una sección quedó en error. El corpus sano SÍ se
      usa, y la próxima vez que alguien pida esta obra se reintentan SOLO las
      secciones fallidas: las sanas se conservan por enlace duro.

    Un error transitorio del portal ya no queda congelado como corpus definitivo.
    """

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
        """`descargar(ruta, pendientes)`: `pendientes` es `None` en la primera
        descarga (bajar todo) o el conjunto de secciones a reintentar."""
        destino = self.directorio / _clave_obra(obra_id)
        with lock_para_descarga(destino):
            return self._obtener_bajo_lock(destino, descargar)

    def _obtener_bajo_lock(
        self,
        destino: Path,
        descargar: Callable[[Path, frozenset[str] | None], dict[str, Any] | None],
    ) -> ResultadoCacheInfoObras:
        marca, parcial = destino / _MARCA, destino / _MARCA_PARCIAL
        estado_previo = (_leer_estado(destino / _ESTADO)
                         if (marca.is_file() or parcial.is_file()) else None)
        if estado_previo is not None and marca.is_file():
            return ResultadoCacheInfoObras(True, destino, estado_previo)
        pendientes: frozenset[str] = frozenset()
        if estado_previo is not None:
            pendientes = frozenset(secciones_en_error(estado_previo))
            if not pendientes:
                # Entrada parcial sin errores declarados (p. ej. una purga que ya
                # se resolvió): se promueve sin volver a la fuente.
                marca.write_text("ok\n", encoding="utf-8")
                parcial.unlink(missing_ok=True)
                return ResultadoCacheInfoObras(True, destino, estado_previo)

        self.directorio.mkdir(parents=True, exist_ok=True)
        temporal = self.directorio / f".{destino.name}.{uuid.uuid4().hex}.part"
        temporal.mkdir(parents=True)
        try:
            if pendientes:
                _clonar_secciones_sanas(destino, temporal, pendientes)
                estado = _fusionar_estado(
                    estado_previo or {}, descargar(temporal, pendientes) or {},
                    pendientes)
            else:
                estado = descargar(temporal, None) or {}
            (temporal / _ESTADO).write_text(
                json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            completa = not secciones_en_error(estado)
            (temporal / (_MARCA if completa else _MARCA_PARCIAL)).write_text(
                "ok\n", encoding="utf-8")
            # El corpus anterior se borra RECIÉN aquí: si la descarga revienta a
            # media corrida, la entrada publicada sigue intacta y reintentable.
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
