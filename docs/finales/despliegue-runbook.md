# Runbook de despliegue on-prem — **Windows 11 + Docker Desktop + LAN**

> Checklist accionable para la **primera instalación** en el servidor de Manuel:
> una **PC con Windows 11** y **Docker Desktop**, a la que Manuel entra **por la red
> de la oficina (LAN)** desde su propia computadora.
> Última revisión: 2026-07-02 (reescrito para Windows/LAN + corrección Cowork→MCP).

El despliegue son **2 contenedores** (backend FastAPI + panel Next.js) vía Docker
Compose. La skill y el MCP **NO** van aquí — corren donde Manuel analiza (ver §9).

> **Todos los comandos van en PowerShell.** Los que tocan firewall/servicios requieren
> una PowerShell **como Administrador** (clic derecho → *Ejecutar como administrador*).

---

## 1 · Requisitos del servidor (la PC Windows)
- **Docker Desktop** instalado y corriendo, con backend **WSL 2** (el default). Verifica:
  ```powershell
  docker version              # Client y Server responden
  docker compose version      # v2
  ```
- **Salida a internet** desde los contenedores (SUNAT + InfoObras en vivo). ✅ ya confirmado.
- **Disco**: cada análisis baja ~1 GB de documentos al ZIP. Los volúmenes de Docker
  Desktop viven en el disco de WSL (normalmente **C:**) → deja **varios GB libres en C:**
  (o mueve el *disk image location* a otra unidad en Docker Desktop → Settings → Resources).
- **Los 2 repos** deben quedar como **hermanos** en el server (ver §2):
  `...\InfoObras\Pivote` y `...\InfoObras\Panel-InfoObras`.

---

## 2 · Llevar el código al servidor
No hay remoto git configurado (los repos son locales). Elige UNA vía:

### Vía A — copiar las carpetas por red/USB (simple para la prueba)
Desde tu laptop, copia **ambos repos** al server **excluyendo lo pesado/regenerable**.
Con el server accesible por recurso compartido (o a un USB):
```powershell
# ajusta el destino (\\SERVER\... o E:\)
$dst = "\\SERVER\C$\InfoObras"       # o "E:\InfoObras"
$excl = @("venv","node_modules","datos_pivote",".git",".next","__pycache__")
robocopy "C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras\Pivote" "$dst\Pivote" /E /XD $excl
robocopy "C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras\Panel-InfoObras" "$dst\Panel-InfoObras" /E /XD $excl
```
Quedan hermanos: `C:\InfoObras\Pivote` y `C:\InfoObras\Panel-InfoObras`.

### Vía B — remoto git (mejor para actualizar luego con `git pull`)
Crea un repo privado (GitHub/Gitea), `git push` de **ambos**, y en el server
`git clone` los dos como hermanos.

---

## 3 · IP LAN fija del servidor  ⚠ paso obligatorio
El panel se **hornea** con la IP del server (§4). Si la IP **cambia**, el panel deja de
funcionar y hay que **reconstruirlo**. Por eso el server necesita **IP fija**.

```powershell
ipconfig        # anota la IPv4 de la red de la oficina, p.ej. 192.168.1.50
```
Luego **fíjala**: reserva DHCP en el router (por la MAC del server) **o** IP estática en
*Configuración de red → Adaptador → IPv4*. Anota la IP — la usas en §4, §5, §9.

---

## 4 · Configurar `deploy\.env`  ⚠ el paso que más se equivoca
```powershell
cd C:\InfoObras\Pivote\deploy
Copy-Item .env.example .env
notepad .env
```
Ajusta:
| Variable | Valor | Por qué |
|---|---|---|
| `PANEL_PORT` | `3002` | URL que abre Manuel: `http://192.168.1.50:3002` |
| `BACKEND_PORT` | `8001` | **debe** quedar publicado: el navegador baja el ZIP directo |
| `PIVOTE_ETAPAS` | `real` | cruces SUNAT/InfoObras en vivo |
| **`NEXT_PUBLIC_PIVOTE_API`** | **`http://192.168.1.50:8001`** | **CRÍTICO** — IP LAN del server + `BACKEND_PORT`. **NO** `localhost`/`127.0.0.1` |
| `PIVOTE_MAX_DESCARGAS` | *(vacío)* | vacío = baja TODOS los documentos (producción) |

> **Por qué `NEXT_PUBLIC_PIVOTE_API` importa tanto:** el panel baja el ZIP (GBs)
> **directo del backend**, no por su propio proxy (Next no streamea archivos de GBs →
> daría un `.txt` corrupto). Esa URL la **hornea Next en el build**, así que tiene que
> ser una IP que el **navegador de Manuel** (en su PC de la LAN) pueda alcanzar — la IP
> del server, **no** `localhost`. **Si la cambias después, reconstruye el panel:**
> `docker compose up -d --build panel`.

---

## 5 · Firewall de Windows (acceso LAN)
Para que la PC de Manuel alcance el panel y el backend (PowerShell **como Admin**):
```powershell
New-NetFirewallRule -DisplayName "InfoObras pivote (LAN)" -Direction Inbound `
  -Protocol TCP -LocalPort 3002,8001 -Action Allow -Profile Private
```
> `-Profile Private` = red de oficina/hogar. **No** lo expongas a internet (no hay auth;
> es solo para la LAN). Si la red de la oficina está marcada como "Pública" en Windows,
> cámbiala a **Privada** o usa `-Profile Any`.

---

## 6 · Que Docker Desktop sobreviva reinicios  ⚠ específico de Windows
Docker Desktop **no es un servicio**: corre en la sesión del usuario. Tras reiniciar la
PC, si nadie inicia sesión, el daemon no arranca y el sistema queda **caído en silencio**.
- Docker Desktop → **Settings → General → "Start Docker Desktop when you sign in"** ✔.
- Configura la PC para **iniciar sesión automáticamente** (o que quede con sesión abierta).
- Los contenedores ya tienen `restart: unless-stopped` → vuelven solos **si el daemon está vivo**.

---

## 7 · Levantar
```powershell
cd C:\InfoObras\Pivote\deploy
docker compose up -d --build     # 1ª vez tarda: baja imágenes + npm ci + next build + pip
docker compose ps                # backend y panel en "running"
```

---

## 8 · Verificar (smoke test de verdad)
```powershell
# a) backend vivo + portales arriba
curl http://localhost:8001/api/pivote/salud       # {sunat: ok, infoobras: ok}
# b) panel sirve la UI
curl -I http://localhost:3002/                    # HTTP 200
```
Luego, **end-to-end desde la PC de Manuel** (NO desde el server):
1. Abrir `http://192.168.1.50:3002` → pestaña **Concursos**.
2. Crear un concurso y subir un análisis por el **dropzone** (ver §9).
3. Ver avanzar los **Pasos** y la **barra del ZIP** (X/Y obras).
4. Cuando el ZIP quede listo, **descargarlo y confirmar que es un `.zip` real** (no un
   `.txt`). ← esto valida que `NEXT_PUBLIC_PIVOTE_API` quedó bien.

---

## 9 · Cómo sube Manuel los análisis (la parte de red que confunde)
La skill corre **donde Manuel la ejecuta**, y de ahí depende si el MCP automático llega:

- **Si corre la skill en Cowork (nube):** Cowork **NO alcanza la LAN** de la oficina (IP
  privada) → el **MCP `subir_analisis` NO llega**. Camino real: Manuel **descarga** el
  espejo + Excel (+ certs) de Cowork y los **sube por el dropzone del panel** desde su PC
  (su navegador sí está en la LAN). ✅ es lo que valida el §8.
- **Si corre la skill en Claude Code local** (su PC o el propio server, en la LAN): el
  **MCP sí llega** → subida automática. Config del MCP: `SERVER_URL=http://192.168.1.50:8001`
  (IP LAN, **no** `localhost`) + empaquetar el plugin: `.\plugin\build.ps1`.

> **Decisión pendiente con Manuel:** local (MCP automático, lo que él quería) vs Cowork
> (dropzone manual). Exponer el backend a internet para que Cowork llegue = contra la
> elección LAN-only; no recomendado.

---

## 10 · Operación
```powershell
docker compose logs -f backend          # logs en vivo (o: panel)
docker compose restart backend          # reiniciar tras tocar .env de runtime
docker compose up -d --build            # actualizar código (el volumen datos_pivote se conserva)

# backup del histórico (jobs/espejos/entregables viven en el volumen)
docker run --rm -v infoobras-pivote_datos_pivote:/d -v ${PWD}:/b alpine `
  tar czf "/b/backup-datos-$(Get-Date -Format yyyy-MM-dd).tgz" -C /d .
```

---

## 11 · Troubleshooting (Windows/LAN)
| Síntoma | Causa probable | Arreglo |
|---|---|---|
| El ZIP se baja como **`.txt`** / se corta | `NEXT_PUBLIC_PIVOTE_API` mal (era `localhost`, IP equivocada, o se cambió sin rebuild) | corregir en `.env` → `docker compose up -d --build panel` |
| Manuel **no abre el panel** desde su PC | firewall cerrado, red marcada "Pública", o la IP LAN cambió | regla del §5; poner la red en **Privada**; reservar la IP (§3) |
| Panel carga pero **no llega al backend** | `PIVOTE_API` debe ser `http://backend:8001` (red interna del compose) | está fijo en el compose; revisar que ambos servicios estén `up` |
| Todo caído **tras reiniciar la PC** | Docker Desktop no arrancó (sin sesión iniciada) | §6: autostart + auto-login |
| Logs con **reintentos de InfoObras** | el portal es intermitente (esperado) | el backend reintenta; no es error |
| **Disco C: lleno** | los ZIP pesan ~1 GB/análisis y el volumen vive en WSL (C:) | borrar análisis viejos (papelera del panel), o mover el disk image de Docker a otra unidad |
| Puerto **3002/8001 ocupado** | otro servicio en el host | cambiar `PANEL_PORT`/`BACKEND_PORT` en `.env` (+ `NEXT_PUBLIC_PIVOTE_API` acorde → rebuild panel) |
| `docker` "cannot connect to the Docker daemon" | Docker Desktop no está corriendo | abrir Docker Desktop y esperar a que diga *Engine running* |

---

## 12 · Persistencia: archivos vs Postgres (A5)
Hoy el backend persiste en **archivos** (volumen `datos_pivote`) — el compose ya funciona
así y **para la prueba alcanza**. El contrato contempla Postgres: el **esquema ya está
diseñado y validado** (`backend/db/schema.sql` — 4 tablas JSONB + vistas `base_datos`/
`analisis`). Falta cablear `RepositorioPostgres` (blobs 1:1), descomentar el servicio
`db` del compose + `DATABASE_URL`, y el backfill. Ver `pendientes.md` (A5).

---

## Pre-flight (auditado — sin bloqueadores)
- `backend/Dockerfile` — python:3.12-slim, `requirements.txt`, `uvicorn api.app:app` :8001. ✔
- `Panel-InfoObras/frontend/Dockerfile` — node:20, `next build` con `ARG NEXT_PUBLIC_PIVOTE_API`, `next start` :3002. ✔
- `deploy/docker-compose.yml` — backend + panel (build-arg `NEXT_PUBLIC_PIVOTE_API`); volumen `datos_pivote`; Postgres comentado; `restart: unless-stopped`; `TZ=America/Lima`. ✔
- `deploy/.env.example` — todas las vars, incluida `NEXT_PUBLIC_PIVOTE_API`. ✔
