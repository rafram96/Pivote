# Infraestructura y despliegue

Estado local más reciente: usuario volvió a levantar backend 8001, PID 31748,
sin PostgreSQL; nueva corrida autorizada en proceso el 10-sep.
[Registro operativo](../../../.ai/context/current_state.md#nueva-corrida-pucallpa-autorizada-10-sep-1626-lima).
No modifica el estado del servidor del cliente descrito a continuación.

## Servidor del cliente (producción on-prem)

- Servidor Windows `192.168.100.5` (red local del cliente; deploy realizado 2026-07-12).
- `deploy/docker-compose.yml` / servicios de Windows: `backend` (FastAPI, crea tablas al
  arrancar), `panel` (Next.js, del repo hermano), `db` (postgres:16-alpine,
  sin puerto expuesto). Volúmenes: `datos_pivote:/datos`, `pgdata`.
  `TZ: America/Lima`. Backend expuesto en `${BACKEND_PORT:-8001}`.
- El backend SÍ tiene salida a internet (scraping InfoObras/SUNAT/MEF).
- **No hay scheduler en el stack**: el refresco semanal de la base MEF va por
  programador de tareas del host / crontab (sugerido `0 3 * * 0` → `actualizar_base_mef.py`) o manual.
  La base compactada (~26 MB) puede copiarse desde la laptop en vez de
  re-descargar los 523 MB.

## Laptop de desarrollo (Windows 11, Holbi)

- Preparación autorizada del 10-sep: backend local iniciado sobre código actual
  y MEF actualizado. [Estado operativo canónico](../../../.ai/context/current_state.md#preparación-operativa-local-10-sep-1220-lima).
  Lanzador privado `C:/Users/Holbi/InfoObras/operacion/iniciar_backend_actual.py`
  con Python del venv; obtiene DSN del contenedor existente en memoria.
  No modifica `.env`; otro arranque necesita configurar la conexión también.
  Sin scheduler nuevo, despliegue al cliente ni ejecución de jobs.
- Python del proyecto: `venv\Scripts\python.exe` (Py 3.12, raíz del repo).
- Tesseract 5.5 instalado en `C:\Program Files\Tesseract-OCR\` + idioma `spa`
  (tessdata_fast) en `C:\Users\Holbi\tessdata` → el OCR Camino A de la skill
  funciona local (`TESSDATA_PREFIX`).
- pdfunite/pdfimages disponibles vía MiKTeX. Consola cp1252: cuidar prints
  Unicode en scripts.
- Backends de prueba se levantan con uvicorn en puertos 8011-8013 para no
  chocar con el 8001.

## Entorno de la skill (cliente)

La skill corre en la máquina del cliente ejecutando **Claude Code**, empaquetada como plugin (`plugin/`,
`build.ps1` la reconstruye). Cambios en `skill/` NO llegan al cliente sin
rebuild + re-entrega del plugin.

## Materialización documental por job (código local, 10-sep)

`descargas/` contiene los árboles P/E que se empaquetan y sus marcas terminales.
`fuentes_descarga/` vincula cada materialización a su `obra_id` antes del intento;
no se cuenta como documento. Si una selección cambia, `descargas_previas/`
conserva el corpus InfoObras retirado y sus marcas fuera del ZIP. No se elimina
la caché `cache_obras/` ni se purgan fuentes ya intentadas; SEACE es independiente.
Las carpetas nuevas se crean al usar el código; no hubo migración de jobs existentes.

## Pendiente de documentar

Mecanismo exacto de acceso al server del cliente (SSH/escritorio) y el proceso
de rebuild de la imagen del backend en el deploy.
