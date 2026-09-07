"""Log del backend a archivo, además de la consola.

Hasta el 7-sep-2026 nada configuraba el logger raíz: uvicorn solo instala los
suyos, así que todo `logger.info` de las etapas (tiempos, reintentos, MEF que no
respondió) se perdía y la corrida Muraria del 6-sep dejó «logs vacíos». Este
módulo instala UNA vez un archivo rotativo en `<datos>/logs/backend.log` y un
handler de consola si no había ninguno. Nivel con `PIVOTE_LOG_NIVEL` (INFO).
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MARCA = "_pivote_registro"
_FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar_registro(dir_datos: Path | str, nivel: str | None = None) -> Path | None:
    """Instala los handlers (idempotente). Devuelve la ruta del archivo o None si
    la carpeta no se pudo crear (entonces queda solo la consola)."""
    raiz = logging.getLogger()
    if any(getattr(h, _MARCA, False) for h in raiz.handlers):
        return next((Path(h.baseFilename) for h in raiz.handlers
                     if getattr(h, _MARCA, False) and isinstance(h, RotatingFileHandler)), None)
    nombre_nivel = (nivel or os.getenv("PIVOTE_LOG_NIVEL") or "INFO").strip().upper()
    raiz.setLevel(getattr(logging, nombre_nivel, logging.INFO))
    formato = logging.Formatter(_FORMATO)
    if not any(isinstance(h, logging.StreamHandler) for h in raiz.handlers):
        consola = logging.StreamHandler()
        consola.setFormatter(formato)
        setattr(consola, _MARCA, True)
        raiz.addHandler(consola)
    try:
        carpeta = Path(dir_datos) / "logs"
        carpeta.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(carpeta / "backend.log", maxBytes=10_000_000,
                                      backupCount=5, encoding="utf-8")
    except OSError as ex:
        logging.getLogger(__name__).warning("sin log a archivo (%s)", ex)
        return None
    archivo.setFormatter(formato)
    setattr(archivo, _MARCA, True)
    raiz.addHandler(archivo)
    return Path(archivo.baseFilename)
