# Instalación y despliegue — Pivote InfoObras

Guía para poner el sistema en marcha. Hay **dos lados**, y solo uno va en Docker:

```
┌─ Máquina del ingeniero (Manuel) ──────────┐      ┌─ Servidor on-prem (Docker) ─────────────┐
│  Claude Code / Cowork (sub Max 5x)         │      │  backend  (FastAPI, :8001)              │
│   ├─ skill  analizar-licitacion-osce       │ LAN  │   └─ cruces SUNAT/InfoObras, Excel, ZIP │
│   └─ MCP    infoobras-onprem-bridge ───────┼─────▶│  panel    (Next.js, :3002)              │
│      (sube el análisis al backend)         │      │   └─ proxyea /api/pivote/* → backend    │
└────────────────────────────────────────────┘      └──────────────────────────────────────────┘
```

- **Servidor (Docker)**: backend + panel. Es lo que se despliega con `docker compose`.
- **Cliente (sin Docker)**: el skill y el MCP corren en la máquina del ingeniero,
  dentro de Claude Code/Cowork con su sub Max 5x. **No** se dockerizan: la
  extracción la hace Claude ahí (regla on-prem: el backend nunca llama a IA cloud).

---

## 1. Servidor on-prem (Docker)

### Requisitos
- Docker + Docker Compose v2.
- Los dos repos como **hermanos** en disco:
  ```
  .../InfoObras/Pivote            (este repo)
  .../InfoObras/Panel-InfoObras   (el panel)
  ```
- Salida a internet desde el contenedor `backend` (consulta SUNAT e InfoObras).

### Pasos
```bash
cd Pivote/deploy
cp .env.example .env          # ajustar puertos / PIVOTE_MAX_DESCARGAS si hace falta
docker compose up -d --build  # construye y levanta backend + panel
```

Eso deja:
- **Panel** en `http://<servidor>:3002`  ← la URL que abre el ingeniero.
- **Backend** en `http://<servidor>:8001` (API; el panel lo alcanza por la red
  interna de compose, no hace falta exponerlo salvo para el MCP — ver §2).

### Verificación
```bash
# salud de los portales (debe responder sunat/infoobras ok)
curl http://localhost:8001/api/pivote/salud
# el panel sirve la UI
curl -I http://localhost:3002/
```
Luego abre `http://<servidor>:3002` y entra a **Concursos**: debe listar los
análisis reales del backend.

### Operación
- **Logs**: `docker compose logs -f backend` (o `panel`).
- **Datos**: viven en el volumen `datos_pivote` (jobs/espejos/Excel/ZIP, con
  datos reales del cliente). Respaldar ese volumen es respaldar el histórico.
  ```bash
  docker run --rm -v infoobras-pivote_datos_pivote:/d -v "$PWD":/b busybox \
    tar czf /b/backup_datos_pivote.tgz -C /d .
  ```
- **Actualizar**: `git pull` en ambos repos → `docker compose up -d --build`.
- **Apagar**: `docker compose down` (los datos persisten en el volumen).

---

## 2. Cliente — máquina del ingeniero (skill + MCP, sin Docker)

Aquí corre Claude Code/Cowork con el sub Max 5x. Dos piezas:

### a) Skill `analizar-licitacion-osce`
Empaquetada como **plugin de Cowork** (`Pivote/plugin/`). Para construir/instalar:
```powershell
# desde Pivote/
./plugin/build.ps1          # ensambla skill + mcp-server en plugin/
claude plugin validate plugin   # debe decir: Validation passed
```
Luego se carga el plugin en Cowork. (En Claude Code "a secas" también se puede
sincronizar la carpeta `skill/` a `~/.claude/skills/analizar-licitacion-osce/`.)

> Si la máquina **no tiene Tesseract**, el skill usa el **OCR nativo de Claude**
> para los PDFs escaneados — no hay que instalar nada extra (ver SKILL.md, Paso 0).

### b) MCP `infoobras-onprem-bridge`
Sube el análisis al backend. Necesita Node y apuntar al servidor:
- Variable **`SERVER_URL`** = `http://<servidor>:8001` (el backend dockerizado).
  Por defecto es `http://127.0.0.1:8001` (sirve solo si el backend corre en la
  misma máquina). En Windows usar **IP/host explícito, no `localhost`** (evita el
  resolver IPv6).
- El plugin ya trae el `.mcp.json`; se configura `SERVER_URL` en el entorno o en
  el config de Cowork (`mcp-server/cowork-config-ejemplo.json` es la referencia).

> **Camino alternativo sin MCP**: el ingeniero puede subir el análisis por el
> **dropzone del panel** (`Nuevo análisis`). El MCP solo automatiza ese paso.

### Flujo de uso (end-to-end)
1. En Claude Code/Cowork: `/analizar-licitacion-osce bases.pdf propuesta.pdf`.
2. El skill extrae+evalúa y consolida el JSON espejo + Excel.
3. Sube por el MCP (o por el dropzone del panel).
4. El backend cruza SUNAT/InfoObras, calcula el Paso 5 y genera Excel/ZIP.
5. El ingeniero ve el resultado y resuelve los "casos por confirmar" en el panel.

---

## 3. Variables de entorno

### Backend (servicio `backend`)
| Variable | Default | Qué hace |
|---|---|---|
| `PIVOTE_ETAPAS` | `real` | `real` = cruces SUNAT/InfoObras en vivo · `esqueleto` = stubs sin red |
| `PIVOTE_MAX_DESCARGAS` | _(sin definir)_ | sin definir = baja **todos** los documentos · `0` = ninguno · `N` = tope (solo pruebas) |
| `PIVOTE_DATA_DIR` | `/datos` | carpeta de datos (montada como volumen) |
| `INFOOBRAS_*`, `SUNAT_*` | (ver `Pivote/.env.example`) | reintentos/throttle de scraping |

### Panel (servicio `panel`)
| Variable | Valor | Qué hace |
|---|---|---|
| `PIVOTE_API` | `http://backend:8001` | destino del proxy `/api/pivote/*` (red interna de compose) |

### MCP (máquina del ingeniero)
| Variable | Valor | Qué hace |
|---|---|---|
| `SERVER_URL` | `http://<servidor>:8001` | backend al que el MCP sube el análisis |

---

## 4. Persistencia

Hoy el backend persiste en **archivos** dentro del volumen `datos_pivote`
(`RepositorioArchivos`: jobs, espejos, enriquecimiento, Excel, ZIP).

**PostgreSQL está pendiente de cablear** (el plan lo exige para producción). El
`docker-compose.yml` trae un servicio `db` **comentado** y listo para activar
cuando se implemente el repositorio Postgres + el caché SUNAT
(`backend/scraping/sunat_cache.py`). Mientras tanto, respaldar el volumen.

---

## 5. Limitaciones y notas (estado actual)

- **Sin autenticación**: el panel y el API no tienen login. Pensado para **LAN**
  interna. Antes de exponerlo fuera de la red, agregar token o allowlist de IP.
- **PostgreSQL pendiente** (ver §4) — persistencia en archivos por ahora.
- El `backend` necesita **salida a internet** (SUNAT/InfoObras); el portal
  InfoObras es intermitente, por eso el backend reintenta.
- Contextos de build **cross-repo**: el compose asume Pivote y Panel-InfoObras
  como carpetas hermanas. Si cambian de ubicación, ajustar `context:` en el compose.
- El skill/MCP del cliente requieren **Claude Code/Cowork con sub Max 5x** (la
  extracción es de Claude; el backend nunca llama a IA cloud).
