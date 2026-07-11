"""
Config compartida del backend — carga del .env + resolución de la carpeta de datos.

Único lugar que decide DÓNDE viven los datos (jobs/espejos/entregables), para que
la API y TODOS los scripts respondan igual al mismo `.env`:

  PIVOTE_DATA_DIR ausente   → `backend/datos_pivote` (el default de siempre)
  PIVOTE_DATA_DIR relativa  → anclada a `backend/` (NO al CWD: correr un script
                              desde otra carpeta ya no cambia dónde caen los datos)
  PIVOTE_DATA_DIR absoluta  → tal cual (así la fija Docker: /datos)

El `.env` de la raíz del repo se carga aquí con override=False: el entorno real
(Docker, tests con monkeypatch) siempre le gana al archivo.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND = Path(__file__).resolve().parent          # .../Pivote/backend
_RAIZ = _BACKEND.parent                              # .../Pivote

load_dotenv(_RAIZ / ".env", override=False)


def data_dir() -> Path:
    """Carpeta de datos del pivote (una carpeta por job + concursos en la raíz)."""
    d = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))
    return d if d.is_absolute() else _BACKEND / d
