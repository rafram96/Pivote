"""Caché compartida y materialización atómica de documentos públicos SEACE."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlsplit

from infraestructura.archivos_atomicos import reemplazar_atomico

_MAGIAS = {
    ".pdf": (b"%PDF",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".rar": (b"Rar!\x1a\x07",),
}
_GUARDIA_LOCKS = threading.Lock()
_LOCKS: dict[str, threading.Lock] = {}


@dataclass(frozen=True)
class ResultadoCacheSeace:
    ok: bool
    clave: str
    cache_hit: bool


def clave_archivo_seace(url: str) -> str:
    """Usa el ``fileCode`` estable; cae a SHA-256 si la URL no lo publica."""
    pares = {
        nombre.lower(): valor
        for nombre, valor in parse_qsl(urlsplit(url).query)
    }
    codigo = pares.get("filecode") or pares.get("file_code")
    if codigo:
        seguro = re.sub(r"[^A-Za-z0-9._-]", "-", codigo).strip(".-")
        if seguro:
            return seguro[:160]
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def archivo_seace_valido(ruta: Path) -> bool:
    """Reconoce únicamente PDF, ZIP o RAR cuya magia coincide con la extensión."""
    ruta = Path(ruta)
    magias = _MAGIAS.get(ruta.suffix.lower())
    if not magias or not ruta.is_file():
        return False
    try:
        with ruta.open("rb") as archivo:
            cabecera = archivo.read(8)
        return any(cabecera.startswith(magia) for magia in magias)
    except OSError:
        return False


def _lock_para(ruta: Path) -> threading.Lock:
    clave = str(ruta.resolve())
    with _GUARDIA_LOCKS:
        return _LOCKS.setdefault(clave, threading.Lock())


class CacheDescargasSeace:
    """Descarga una vez por ``fileCode`` y copia a cada experiencia/job."""

    def __init__(self, directorio: Path):
        self.directorio = Path(directorio)

    def materializar(
        self,
        url: str,
        destino: Path,
        *,
        descargar: Callable[[str, Path], bool],
    ) -> ResultadoCacheSeace:
        destino = Path(destino)
        extension = destino.suffix.lower()
        clave = clave_archivo_seace(url)
        cache = self.directorio / f"{clave}{extension}"

        with _lock_para(cache):
            cache_hit = archivo_seace_valido(cache)
            if not cache_hit:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.unlink(missing_ok=True)
                temporal_cache = cache.with_name(
                    f".{cache.stem}.{uuid.uuid4().hex}{extension}"
                )
                try:
                    if (
                        not descargar(url, temporal_cache)
                        or not archivo_seace_valido(temporal_cache)
                    ):
                        return ResultadoCacheSeace(False, clave, False)
                    reemplazar_atomico(temporal_cache, cache)
                finally:
                    temporal_cache.unlink(missing_ok=True)
                    temporal_cache.with_name(
                        temporal_cache.name + ".part"
                    ).unlink(missing_ok=True)

            destino.parent.mkdir(parents=True, exist_ok=True)
            temporal_destino = destino.with_name(
                f".{destino.name}.{uuid.uuid4().hex}.part"
            )
            try:
                try:
                    os.link(cache, temporal_destino)
                except OSError:
                    shutil.copyfile(cache, temporal_destino)
                reemplazar_atomico(temporal_destino, destino)
            finally:
                temporal_destino.unlink(missing_ok=True)

        return ResultadoCacheSeace(True, clave, cache_hit)
