# Infraestructura y despliegue

## Server del cliente (producción on-prem)

- Host `192.168.100.5` (red local del cliente; deploy realizado 2026-07-12).
- `deploy/docker-compose.yml`: 3 servicios — `backend` (FastAPI, crea tablas al
  arrancar), `panel` (Next.js, del repo hermano), `db` (postgres:16-alpine,
  sin puerto expuesto). Volúmenes: `datos_pivote:/datos`, `pgdata`.
  `TZ: America/Lima`. Backend expuesto en `${BACKEND_PORT:-8001}`.
- El backend SÍ tiene salida a internet (scraping InfoObras/SUNAT/MEF).
- **No hay scheduler en el stack**: el refresco semanal de la base MEF va por
  crontab del host (sugerido `0 3 * * 0` → `actualizar_base_mef.py`) o manual.
  La base compactada (~26 MB) puede copiarse desde la laptop en vez de
  re-descargar los 523 MB.

## Laptop de desarrollo (Windows 11, Holbi)

- Python del proyecto: `venv\Scripts\python.exe` (Py 3.12, raíz del repo).
- Tesseract 5.5 instalado en `C:\Program Files\Tesseract-OCR\` + idioma `spa`
  (tessdata_fast) en `C:\Users\Holbi\tessdata` → el OCR Camino A de la skill
  funciona local (`TESSDATA_PREFIX`).
- pdfunite/pdfimages disponibles vía MiKTeX. Consola cp1252: cuidar prints
  Unicode en scripts.
- Backends de prueba se levantan con uvicorn en puertos 8011-8013 para no
  chocar con el 8001.

## Entorno de la skill (cliente)

La skill corre en **Cowork (Linux)** empaquetada como plugin (`plugin/`,
`build.ps1` la reconstruye). Cambios en `skill/` NO llegan al cliente sin
rebuild + re-entrega del plugin.

## Pendiente de documentar

Mecanismo exacto de acceso al server del cliente (SSH/escritorio) y el proceso
de rebuild de la imagen del backend en el deploy.
