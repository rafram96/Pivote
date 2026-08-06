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


# Días desde los que la base local del MEF se considera vencida.
#
# Por qué 10: la actualización corre los domingos a las 03:00, así que en
# operación normal la base nunca pasa de 7 días. Con 10 se tolera el rebote
# normal (una corrida que arranca tarde, un domingo con mantenimiento) pero UNA
# semana saltada se ve al miércoles siguiente — antes de que se pierda la
# segunda. Un umbral de 14 solo avisaría cuando ya van dos fallos.
DIAS_FRESCURA_MEF = 10


def dias_frescura_mef() -> int:
    """Umbral de antigüedad de la base del MEF, en días (`PIVOTE_MEF_DIAS_FRESCURA`).

    Un valor ausente, no numérico o menor que 1 cae al default: preferimos avisar
    de más a que un typo en el `.env` apague el aviso en silencio — que es
    exactamente el fallo silencioso que este umbral existe para evitar."""
    crudo = (os.getenv("PIVOTE_MEF_DIAS_FRESCURA") or "").strip()
    if not crudo:
        return DIAS_FRESCURA_MEF
    try:
        n = int(crudo)
    except ValueError:
        return DIAS_FRESCURA_MEF
    return n if n >= 1 else DIAS_FRESCURA_MEF
