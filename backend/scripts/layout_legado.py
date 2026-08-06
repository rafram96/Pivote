"""Candado para los scripts que todavía leen el layout PLANO de `datos_pivote/`.

Hasta que el repositorio pasó a **una carpeta por job** (`datos_pivote/<job>/
espejo.json`, `descargas/`, `infoobras.zip`…), los artefactos vivían sueltos en
la raíz con el id como prefijo (`<job>.espejo.json`, `<job>.descargas/`). Dos
utilidades operativas quedaron escritas contra ese layout viejo:

  · `avance_descargas.py`        — mide el avance de las descargas de un job;
  · `redescargar_documentos.py`  — vuelve a bajar los documentos y rearma el ZIP.

Sobre un job del layout vigente NO fallan de forma limpia: leen rutas que no
existen (o, peor, escriben una carpeta `<job>.descargas` paralela a la de verdad),
así que el trabajo se hace en un sitio que ni el Excel ni el Panel miran. Un
resultado que parece hecho y no está es peor que un error.

Mientras no se actualicen —eso es mantenimiento, no esta tarea— el candado los
detiene con un mensaje que se entiende sin conocer el código, y deja `--forzar`
para quien sepa exactamente lo que hace (por ejemplo, un job histórico que sí
quedó en el layout plano y hay que rescatar).
"""
from __future__ import annotations

from pathlib import Path

BANNER = (
    "⚠ Este script usa el formato de datos ANTERIOR (un archivo suelto por job). "
    "Sobre un job del formato vigente (una carpeta por job) se detiene solo; "
    "`--forzar` lo salta bajo responsabilidad de quien lo corre."
)

# Marcas de que el job vive en el layout vigente. Basta cualquiera: un job a
# medio correr puede no tener todavía `espejo.json`.
_MARCAS = ("job.json", "espejo.json", "enriquecimiento.json")


def layout_por_carpeta(base, job_id: str) -> bool:
    """¿Este job está guardado en el layout vigente (`<base>/<job_id>/…`)?"""
    d = Path(base) / str(job_id)
    return d.is_dir() and any((d / m).exists() for m in _MARCAS)


def mensaje(job_id: str) -> str:
    return (
        f"El job {job_id} está guardado en el formato vigente (una carpeta por "
        f"job) y este script usa un formato de datos anterior.\n"
        f"Correrlo aquí puede dejar el Excel y el Panel sin ver lo redescargado: "
        f"escribiría los archivos en un sitio que el sistema ya no lee.\n"
        f"Si sabes lo que haces, repite el comando con --forzar."
    )


def exigir_layout_plano(base, job_id: str, forzar: bool = False) -> None:
    """Aborta si el job vive en el layout por carpeta y no se pidió `--forzar`."""
    if forzar or not layout_por_carpeta(base, job_id):
        return
    raise SystemExit(mensaje(job_id))


def extraer_forzar(argv: list[str]) -> tuple[list[str], bool]:
    """Saca `--forzar` de la línea de comandos y dice si estaba."""
    limpio = [a for a in argv if a != "--forzar"]
    return limpio, len(limpio) != len(argv)
