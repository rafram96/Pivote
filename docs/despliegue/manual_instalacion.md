# Manual de instalación — InfoObras Analyzer

Guía completa para dejar el sistema funcionando. Hay **dos máquinas** y se instalan
distinto:

```
┌─ PC del ingeniero (Manuel) ───────────────┐      ┌─ Servidor on-prem (Docker) ─────────────┐
│  Claude Desktop + Cowork (sub Max)         │      │  backend  (FastAPI, :8001)              │
│   ├─ skill  analizar-licitacion-osce       │ LAN  │   └─ cruces SUNAT/InfoObras, Excel, ZIP │
│   └─ MCP    infoobras-onprem-bridge ───────┼─────▶│  panel    (Next.js, :3002)              │
└────────────────────────────────────────────┘      └──────────────────────────────────────────┘
        Claude (la nube de Anthropic)                        100% on-prem, sin IA cloud
```

> **Nota importante (pivote):** la extracción la hace **Claude** en la PC del
> ingeniero (con su sub Max). Por eso el **servidor YA NO necesita GPU** — el motor
> local Qwen del plan original se reemplazó. El servidor solo corre código
> (FastAPI + scrapers + panel + base de datos). El hardware del contrato
> (i9-14900K / 64 GB / RTX 5000) sobra; la GPU queda sin usar.

---

## PARTE A — Servidor on-prem

### A.1 · Requisitos
- **SO:** Linux (recomendado) o Windows con Docker Desktop.
- **Docker + Docker Compose v2.**
- **CPU/RAM:** cualquier servidor moderno. **Sin GPU.**
- **Disco:** varios GB libres — cada análisis baja documentos de InfoObras (~1 GB por ZIP).
- **Red:** (1) salida a internet (consulta SUNAT e InfoObras); (2) alcanzable por la
  **LAN** desde la PC del ingeniero.

### A.2 · Traer el código (los DOS repos, como hermanos)
El sistema son dos repos que deben quedar **lado a lado**:
```
.../InfoObras/Pivote            (backend + skill + mcp)
.../InfoObras/Panel-InfoObras   (el panel web)
```
Llevarlos al servidor por **copia** (rsync/scp/zip) o **git clone**. Excluir lo
pesado y regenerable: `venv/`, `node_modules/`, `datos_pivote/`.

### A.3 · Configurar
```bash
cd Pivote/deploy
cp .env.example .env
# editar si hace falta: PANEL_PORT (3002), BACKEND_PORT (8001),
# PIVOTE_MAX_DESCARGAS (dejar vacío = baja todos los documentos)
```

### A.4 · Levantar
```bash
docker compose up -d --build      # construye y levanta backend + panel
```

### A.5 · Verificar
```bash
curl http://localhost:8001/api/pivote/salud    # portales: sunat/infoobras ok
curl -I http://localhost:3002/                 # el panel sirve la UI
```
Luego abrir `http://<IP-del-servidor>:3002` → pestaña **Concursos**.

### A.6 · Red / firewall
Abrir en el firewall del servidor los puertos **3002** (panel) y **8001** (API)
para la **LAN interna**. No exponer a internet (no hay login todavía).

### A.7 · Operación día a día
- **Logs:** `docker compose logs -f backend` (o `panel`).
- **Respaldo:** los datos viven en el volumen `datos_pivote` (jobs, Excel, ZIP).
  Respaldarlo es respaldar el histórico (comando en `instalacion.md §Operación`).
- **Actualizar:** `git pull` en ambos repos → `docker compose up -d --build`.
- **Apagar:** `docker compose down` (los datos persisten en el volumen).

---

## PARTE B — PC del ingeniero (skill + MCP)

Aquí corre **Claude** (no se instala IA local). Solo se conecta la skill y el puente MCP.

### B.1 · Requisitos
- **Claude Desktop** con **Cowork** activo y **sub Claude Max** (ya lo tiene).
- **Node.js LTS** (para el MCP y el script que recorta las constancias).
- (opcional) **Claude Code** CLI, si se prefiere a Cowork.

### B.2 · Instalar la skill
**Opción 1 — Cowork (plugin):**
```powershell
cd Pivote
./plugin/build.ps1                 # empaqueta skill + mcp en plugin/
claude plugin validate plugin      # debe decir: Validation passed
# luego cargar el plugin en Cowork
```
**Opción 2 — Claude Code:** copiar la carpeta `Pivote/skill/` a
`~/.claude/skills/analizar-licitacion-osce/` y dentro correr `npm install pdf-lib`.

> Si la PC **no tiene Tesseract**, no pasa nada: la skill usa el **OCR nativo de
> Claude** para los PDFs escaneados (no hay que instalar nada extra).

### B.3 · Apuntar el MCP al servidor
La variable **`SERVER_URL`** debe apuntar al backend del servidor por su **IP de LAN**:
```
SERVER_URL = http://192.168.x.x:8001     ← IP explícita, NO "localhost"
```
(en Windows usar IP/host explícito para evitar el resolver IPv6). El plugin ya trae
el `.mcp.json`; `SERVER_URL` se fija en el entorno o en el config de Cowork
(referencia: `mcp-server/cowork-config-ejemplo.json`).

### B.4 · Probar la conexión
En Claude: pedir **`probar_conexion`** (tool del MCP) o correr un análisis de prueba.
Si responde el backend, está listo.

> **Camino alternativo sin MCP:** el ingeniero puede subir el análisis por el
> **dropzone del panel** (`Nuevo análisis`). El MCP solo automatiza ese paso.

---

## PARTE C — Checklist final
- [ ] Servidor arriba; `http://<server>:3002` abre y lista Concursos.
- [ ] Puertos 3002/8001 abiertos en la LAN.
- [ ] PC del ingeniero: la skill carga en Cowork/Claude Code.
- [ ] MCP conecta (`SERVER_URL` = IP del servidor; `probar_conexion` OK).
- [ ] Una corrida de punta a punta (analizar → subir → ver en el panel → descargar Excel/ZIP) funciona.

---

## Pendiente de infraestructura (ver `docs/backend/modelo_datos.md`)
Hoy la persistencia es en **archivos** dentro del volumen `datos_pivote`. El plan a
PostgreSQL (servicio `db` del compose, hoy comentado) está en el doc de modelo de datos.
