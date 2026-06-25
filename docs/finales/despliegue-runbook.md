# Runbook de despliegue on-prem (servidor de prueba)

> Checklist accionable para la **primera instalación** en el servidor de Manuel.
> Complementa [`../despliegue/instalacion.md`](../despliegue/instalacion.md).
> Última revisión: 2026-06-25 (incluye el fix de `NEXT_PUBLIC_PIVOTE_API` build-time).

El despliegue son **2 contenedores** (backend FastAPI + panel Next.js) vía Docker
Compose. La skill y el MCP **no** van aquí — corren en la máquina de Manuel.

---

## 1 · Requisitos del servidor
- **Docker** + **Docker Compose v2** (`docker compose version`).
- **Salida a internet** desde el contenedor `backend` (consulta SUNAT + InfoObras en vivo).
- **Disco**: cada análisis baja ~1 GB de documentos InfoObras al ZIP → deja **varios GB libres** (`df -h`).
- **Red LAN**: el server debe ser alcanzable desde la PC de Manuel por una **IP LAN fija** (ideal: IP reservada en el router). Anótala — la vas a usar abajo.
- Reloj/zona horaria: el compose fija `TZ=America/Lima`.

Averigua la IP LAN del server (la necesitas en el paso 3):
```bash
hostname -I        # o:  ip -4 addr show | grep inet
# ej. 192.168.1.50
```

---

## 2 · Llevar el código al servidor
**No hay remoto git configurado** (los repos son locales en la laptop). Elige UNA vía:

### Vía A — copiar carpetas (más simple para una prueba)
Desde la laptop, empaqueta **ambos repos** excluyendo lo pesado/regenerable:
```bash
cd /c/Users/Holbi/Documents/Freelance/proyectos/InfoObras
tar czf pivote-deploy.tgz \
  --exclude='**/venv' --exclude='**/node_modules' \
  --exclude='**/datos_pivote' --exclude='**/.git' \
  --exclude='**/.next' --exclude='**/__pycache__' \
  Pivote Panel-InfoObras
# súbelo al server (scp/rsync) y descomprímelo:
scp pivote-deploy.tgz usuario@192.168.1.50:/opt/
ssh usuario@192.168.1.50 'cd /opt && tar xzf pivote-deploy.tgz'
```
Quedan **hermanos**: `/opt/Pivote` y `/opt/Panel-InfoObras`.

### Vía B — remoto git (mejor para actualizar luego con `git pull`)
Crea un repo privado (GitHub/Gitea), `git remote add` + `git push` de **ambos**
repos, y en el server `git clone` los dos como hermanos.

---

## 3 · Configurar `deploy/.env`  ⚠ el paso que más se equivoca
```bash
cd /opt/Pivote/deploy
cp .env.example .env
nano .env
```
Ajusta:
| Variable | Valor | Por qué |
|---|---|---|
| `PANEL_PORT` | `3002` | URL que abre Manuel: `http://192.168.1.50:3002` |
| `BACKEND_PORT` | `8001` | **debe** quedar publicado: el browser baja el ZIP directo + el MCP |
| `PIVOTE_ETAPAS` | `real` | cruces SUNAT/InfoObras en vivo |
| **`NEXT_PUBLIC_PIVOTE_API`** | **`http://192.168.1.50:8001`** | **CRÍTICO** — IP LAN del server + `BACKEND_PORT`. **NO** `localhost`/`127.0.0.1` |
| `PIVOTE_MAX_DESCARGAS` | *(vacío)* | vacío = baja TODOS los documentos (producción) |

> **Por qué `NEXT_PUBLIC_PIVOTE_API` importa tanto:** el panel baja el ZIP (GBs)
> **directo del backend**, no por su propio proxy (Next no streamea archivos de GBs
> → daría un `.txt` corrupto). Esa URL la **hornea Next en build-time**, así que
> tiene que ser una IP que el **navegador de Manuel** pueda alcanzar (la LAN del
> server), no `localhost`. **Si la cambias después, hay que reconstruir el panel**
> (`docker compose up -d --build panel`).

---

## 4 · Abrir el firewall (LAN)
Ambos puertos deben ser alcanzables desde la PC de Manuel:
```bash
sudo ufw allow 3002/tcp    # panel
sudo ufw allow 8001/tcp    # backend (ZIP directo + MCP)
```
(o el firewall que use el server). **No abrir a internet** — solo LAN (no hay auth).

---

## 5 · Levantar
```bash
cd /opt/Pivote/deploy
docker compose up -d --build       # primera vez tarda: baja imágenes + npm ci + next build + pip
docker compose ps                  # backend y panel en estado "running/healthy"
```

---

## 6 · Verificar (smoke test de verdad)
```bash
# a) backend vivo + portales arriba
curl http://localhost:8001/api/pivote/salud      # {sunat: ok, infoobras: ok}

# b) panel sirve la UI
curl -I http://localhost:3002/                   # HTTP 200
```
Luego, **end-to-end desde la PC de Manuel** (no desde el server):
1. Abrir `http://192.168.1.50:3002` → pestaña **Concursos**.
2. Crear un concurso y subir un análisis (por el **dropzone** o por el **MCP**).
3. Ver avanzar los **Pasos** y la **barra del ZIP** (X/Y obras).
4. Cuando el ZIP quede listo, **descargarlo y confirmar que es un `.zip` real** (no
   un `.txt`). ← esto valida que `NEXT_PUBLIC_PIVOTE_API` quedó bien.

---

## 7 · Lado cliente (PC de Manuel) — después del servidor
- **MCP `infoobras-onprem-bridge`**: `SERVER_URL=http://192.168.1.50:8001` (IP LAN
  explícita, **no** `localhost`). Empaquetar el plugin Cowork: `./plugin/build.ps1`.
- **Alternativa sin MCP**: subir el espejo + Excel por el **dropzone** del panel.

---

## 8 · Operación
```bash
# logs en vivo
docker compose logs -f backend          # o: panel
# reiniciar un servicio (p. ej. tras tocar .env de runtime)
docker compose restart backend
# backup del histórico (jobs/espejos/entregables viven en el volumen)
docker run --rm -v infoobras-pivote_datos_pivote:/d -v "$PWD":/b alpine \
  tar czf /b/backup-datos-$(date +%F).tgz -C /d .
# actualizar a una versión nueva del código (vía A: recopiar; vía B: git pull) y:
docker compose up -d --build            # el volumen datos_pivote se conserva
```

---

## 9 · Troubleshooting
| Síntoma | Causa probable | Arreglo |
|---|---|---|
| El ZIP se baja como **`.txt`** / se corta | `NEXT_PUBLIC_PIVOTE_API` mal (era `localhost`, IP equivocada, o se cambió sin rebuild) | corregir en `.env` → `docker compose up -d --build panel` |
| El panel carga pero **no llega al backend** | `PIVOTE_API` no resuelve (debe ser `http://backend:8001`, red interna del compose) | está fijo en el compose; revisar que ambos servicios estén `up` |
| Manuel no abre el panel desde su PC | puerto cerrado en el firewall, o IP LAN cambió | `ufw allow 3002/8001`; reservar IP del server en el router |
| Logs con **reintentos de InfoObras** | el portal es intermitente (esperado) | el backend reintenta (5×); no es un error |
| **Disco lleno** | los ZIP pesan ~1 GB/análisis | borrar análisis viejos (papelera del panel) o respaldar+limpiar el volumen |
| Puerto **3002/8001 ocupado** | otro servicio en el host | cambiar `PANEL_PORT`/`BACKEND_PORT` en `.env` (y `NEXT_PUBLIC_PIVOTE_API` acorde → rebuild panel) |

---

## 10 · Persistencia: archivos vs Postgres (decisión abierta)
Hoy el backend persiste en **archivos** (volumen `datos_pivote`) — el compose ya
funciona así y **para la prueba alcanza**. El contrato contempla Postgres; cuando se
cablee `RepositorioPostgres` se descomenta el servicio `db` del compose y se apunta
el backend con `DATABASE_URL`. El esquema es un **espejo JSONB** (4 tablas), no un
modelado relacional — ver `pendientes.md` (A5).

---

## Pre-flight (auditado — sin bloqueadores)
- `backend/Dockerfile` — python:3.12-slim, `requirements.txt`, `uvicorn api.app:app` :8001. ✔
- `Panel-InfoObras/frontend/Dockerfile` — node:20, `next build` con `ARG NEXT_PUBLIC_PIVOTE_API`, `next start` :3002. ✔
- `deploy/docker-compose.yml` — backend + panel (con build-arg `NEXT_PUBLIC_PIVOTE_API`); volumen `datos_pivote`; Postgres comentado. ✔
- `deploy/.env.example` — todas las vars, incluida `NEXT_PUBLIC_PIVOTE_API`. ✔
