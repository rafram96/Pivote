# Runbook de despliegue on-prem (servidor de prueba)

> Verificado el 2026-06-23 con audit estático de los assets. **No se hallaron
> bloqueadores.** Complementa [`../despliegue/instalacion.md`](../despliegue/instalacion.md)
> con un checklist accionable para la primera instalación en el servidor.

## ✅ Pre-flight (auditado — todo OK)
- `backend/Dockerfile` — python:3.12-slim, instala `requirements.txt`, arranca
  `uvicorn api.app:app` en :8001. ✔
- `requirements.txt` — incluye las deps de constancias (`pymupdf`, `Pillow`) +
  fastapi/uvicorn. `psycopg2` comentado (Postgres aún no cableado). ✔
- `deploy/docker-compose.yml` — backend (ctx `..`) + panel (ctx
  `../../Panel-InfoObras/frontend`); volumen `datos_pivote`; Postgres comentado. ✔
- **Panel** — `Panel-InfoObras/frontend/Dockerfile` EXPOSE 3002 y
  `next start --port 3002`; proxy `/api/pivote/*` por `PIVOTE_API`. ✔
- `deploy/.env.example` — coherente con las vars del compose. ✔

## Requisitos del servidor
- Docker + Docker Compose v2.
- **Salida a internet** desde el contenedor `backend` (SUNAT + InfoObras).
- **Disco**: los ZIP de InfoObras pesan ~1 GB por análisis → varios GB libres.
- Red **LAN** alcanzable desde la máquina de Manuel (para el MCP).

## ⚠ Antes de empezar — llevar el código al servidor
**No hay remoto git configurado** (el repo es local en la laptop). Para que el
servidor tenga el código, elegir UNA vía:
- **A · Copiar las carpetas** (más simple para una prueba): `rsync`/`scp`/zip de
  `Pivote/` y `Panel-InfoObras/` al servidor, como hermanas. Excluir `venv/`,
  `node_modules/`, `datos_pivote/` (pesados y se regeneran).
- **B · Remoto git** (mejor para `git pull` de actualizaciones): crear un repo
  privado (GitHub/Gitea), `git remote add` + `git push` de **ambos** repos, y en
  el servidor `git clone`.

## Pasos
```bash
# 1 · Ambos repos como HERMANOS en el servidor (vía A o B de arriba)
#   /opt/Pivote   y   /opt/Panel-InfoObras

# 2 · Config
cd Pivote/deploy
cp .env.example .env
#   editar si hace falta: PANEL_PORT, BACKEND_PORT, PIVOTE_MAX_DESCARGAS

# 3 · Levantar (construye backend + panel)
docker compose up -d --build

# 4 · Verificar
curl http://localhost:8001/api/pivote/salud   # portales: sunat/infoobras ok
curl -I http://localhost:3002/                # panel sirve la UI
#   abrir http://<server>:3002 → pestaña Concursos
```

## Lado cliente (máquina de Manuel) — después del servidor
- MCP `infoobras-onprem-bridge`: **`SERVER_URL=http://<IP-LAN-del-server>:8001`**
  (IP explícita, **no** `localhost`). Plugin Cowork: `./plugin/build.ps1`.
- Alternativa sin MCP: subir el análisis por el **dropzone del panel**.

## Caveats a tener presentes
- **Persistencia = archivos** en el volumen `datos_pivote` (Postgres pendiente).
  Respaldar ese volumen = respaldar el histórico (comando en `instalacion.md §Operación`).
- **Sin autenticación** → solo LAN interna. No exponer a internet sin token/allowlist.
- **InfoObras es intermitente** → el backend reintenta; es esperado ver reintentos en logs.
- El código ya incluye los fixes recientes (ZIP atómico + nombres cortos): el
  `docker compose up --build` los toma automáticamente (copia `backend/`).

## Decisión abierta para esta prueba
- **Postgres vs archivos**: para la prueba, **archivos** alcanza (el compose ya
  funciona así). Para producción real hay que cablear `RepositorioPostgres` +
  descomentar el servicio `db`. Ver [`pendientes.md`](pendientes.md) P5 y
  [`../despliegue/instalacion.md §4`](../despliegue/instalacion.md).
