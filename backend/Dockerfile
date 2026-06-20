# Backend on-prem del pivote InfoObras (FastAPI + scrapers SUNAT/InfoObras).
# Contexto de build = raíz del repo Pivote (ver deploy/docker-compose.yml).
#
# Regla preservada: el backend NUNCA llama a APIs cloud de IA; solo cruza
# SUNAT/InfoObras (necesita salida a internet) y recibe el JSON ya generado.
FROM python:3.12-slim

# Zona horaria Lima para fechas/logs coherentes (opcional pero útil on-prem).
ENV TZ=America/Lima \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Solo requirements primero → cachea la capa de dependencias.
# psycopg2-binary, rapidfuzz y openpyxl traen wheels: no hacen falta libs del SO.
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

# Código del backend (paquetes api/ orquestador/ schemas/ entregables/ reglas/ scraping/ scripts/)
COPY backend/ ./backend/

WORKDIR /app/backend

# Datos (jobs/espejos/entregables) en un volumen; modo real por defecto.
ENV PIVOTE_DATA_DIR=/datos \
    PIVOTE_ETAPAS=real
# PIVOTE_MAX_DESCARGAS sin definir → baja TODOS los documentos al ZIP.

EXPOSE 8001

# `python -m uvicorn` para que el CWD (/app/backend) entre al sys.path y resuelva
# los imports de los paquetes del backend.
CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8001"]
