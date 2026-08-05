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

# ── Documentos SEACE dentro de la carpeta de una experiencia ─────────────────
# (clave del payload, nombre del archivo en el entregable, rótulo legible).
# El nombre YA NO lleva prefijo numérico: `SEACE_01_…` solo servía para que los
# dos archivos encabezaran el listado de la carpeta y, al recortar cada
# componente del ZIP a 38 caracteres, mutilaba las notas
# (`SEACE_01_BASES_INTEGRADAS_N~2c5e00.txt`) borrando justo la diferencia entre
# «no publicado» y «error de la fuente». Sin el prefijo, los nombres completos
# caben (`BASES_INTEGRADAS_NO_DISPONIBLE.txt` = 34).
DOCUMENTOS_SEACE: tuple[tuple[str, str, str], ...] = (
    ("bases", "BASES_INTEGRADAS", "Bases Integradas (SEACE)"),
    ("contrato", "CONTRATO_FIRMADO", "Contrato firmado (SEACE)"),
)

# Nombres históricos: los jobs ya descargados en disco tienen los archivos así.
# Se siguen reconociendo para no borrarlos al rematerializar InfoObras (la caché
# de obra no gestiona SEACE) ni perder su rótulo en el índice.
_ETIQUETAS_SEACE: dict[str, str] = {
    nombre: etiqueta for _, nombre, etiqueta in DOCUMENTOS_SEACE
} | {
    "SEACE_01_BASES_INTEGRADAS": "Bases Integradas (SEACE)",
    "SEACE_02_CONTRATO_FIRMADO": "Contrato firmado (SEACE)",
}


# ── Textos de las notas SEACE (fuente única, issue #81 R3) ───────────────────
# Las lee un evaluador dentro de la carpeta de la experiencia: frases completas,
# sin jerga, y con la distinción intacta entre «falló ahora, se puede reintentar»
# y «no existe publicado, no lo busques más».
NOTA_SEACE_DESCARGA_FALLIDA = (
    "No se pudo descargar este documento en esta corrida: la fuente oficial "
    "falló temporalmente. El proceso sí lo publica; se puede reintentar."
)

_NOTAS_SEACE_AUSENCIA: dict[str, str] = {
    # reintentable: la consulta misma no respondió
    "fuente_no_disponible": (
        "La consulta a los datos abiertos del SEACE no respondió en esta corrida, "
        "así que no fue posible obtener este documento. Se puede reintentar."
    ),
    # definitivos: la fuente respondió y el documento no está
    "sin_tipo": (
        "El SEACE solo publica procesos de otro tipo para esta obra (por ejemplo "
        "ejecución o equipamiento); el proceso que certifica esta experiencia no "
        "figura en los datos abiertos."
    ),
    "sin_procesos": (
        "Los datos abiertos del SEACE cubren contrataciones desde 2018; esta "
        "contratación es anterior, por eso sus documentos no están publicados ahí."
    ),
    "seleccionado": (
        "El proceso de contratación sí fue identificado en el SEACE, pero no "
        "publica este documento entre sus archivos."
    ),
}

_NOTA_SEACE_AUSENCIA_GENERICA = (
    "Este documento no figura publicado en los datos abiertos del SEACE para "
    "esta experiencia."
)


def nota_seace_ausencia(estado: str | None) -> str:
    """Texto de la nota cuando NO hay documento que descargar, según el estado
    de la búsqueda del proceso. Un estado desconocido cae a la frase genérica:
    una nota siempre dice algo comprensible, nunca un código interno."""
    return _NOTAS_SEACE_AUSENCIA.get(str(estado or ""), _NOTA_SEACE_AUSENCIA_GENERICA)


def es_archivo_seace(nombre: str) -> bool:
    """¿Este archivo de una carpeta P/E lo puso SEACE (documento o nota)?

    Cubre los nombres actuales y los históricos con prefijo `SEACE_0…`.
    """
    n = str(nombre).upper()
    return n.startswith("SEACE_") or any(
        n.startswith(nombre_base) for _, nombre_base, _ in DOCUMENTOS_SEACE)


def etiqueta_documento_seace(base: str) -> str:
    """Rótulo legible para el índice a partir del nombre del archivo, ya sin el
    sufijo `_ERROR`/`_NO_DISPONIBLE`. Un nombre desconocido se devuelve tal cual
    (el aviso sigue siendo útil aunque no sepamos de qué documento habla)."""
    return _ETIQUETAS_SEACE.get(str(base).upper(), str(base))


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


def lock_para_descarga(ruta: Path) -> threading.Lock:
    """Devuelve el lock de proceso compartido por una entrada de caché."""
    clave = str(ruta.resolve())
    with _GUARDIA_LOCKS:
        return _LOCKS.setdefault(clave, threading.Lock())


def materializar_archivo(origen: Path, destino: Path) -> None:
    """Publica ``origen`` en ``destino`` por hardlink y cae a copia.

    El temporal vive junto al destino para que el reemplazo sea atómico también
    en Windows. Este patrón es compartido por las cachés SEACE e InfoObras.
    """
    origen, destino = Path(origen), Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.part")
    try:
        try:
            os.link(origen, temporal)
        except OSError:
            shutil.copyfile(origen, temporal)
        reemplazar_atomico(temporal, destino)
    finally:
        temporal.unlink(missing_ok=True)


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

        with lock_para_descarga(cache):
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

            materializar_archivo(cache, destino)

        return ResultadoCacheSeace(True, clave, cache_hit)
