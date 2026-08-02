"""Primitivas de archivos atómicos compatibles con concurrencia en Windows."""
from __future__ import annotations

import os
import time
from pathlib import Path


def reemplazar_atomico(
    origen: Path,
    destino: Path,
    *,
    intentos: int = 20,
    espera_segundos: float = 0.01,
) -> None:
    """Reemplaza el destino y tolera bloqueos breves de lectores en NTFS."""
    for intento in range(max(1, intentos)):
        try:
            os.replace(origen, destino)
            return
        except PermissionError:
            if intento + 1 >= intentos:
                raise
            time.sleep(espera_segundos)
