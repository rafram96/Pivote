# Setup e instalación — InfoObras

> Documento para el responsable técnico. La instalación final se ejecuta solo
> cuando la entrega esté autorizada. No copie contraseñas, datos de concursos ni
> direcciones privadas de red al repositorio.

## 1. Arquitectura de entrega

- **Servidor Windows:** Panel, backend, PostgreSQL y datos persistentes mediante
  Docker Compose.
- **Computadora del evaluador:** Claude Code, skill y conector MCP por la red
  local.

El backend no consume servicios de IA en la nube. La extracción ocurre en
Claude Code; el servidor verifica fuentes, recalcula y genera entregables.

## 2. Requisitos

### Servidor

- Windows 11, Docker Desktop con WSL 2 y arranque al iniciar sesión;
- acceso saliente a fuentes públicas;
- IP local fija o reserva DHCP;
- espacio suficiente: un análisis puede ocupar 1 GB o más;
- repositorios `Pivote` y `Panel-InfoObras` como carpetas hermanas.

### Computadora del evaluador

- Claude Code con sesión activa y Node.js;
- acceso a los puertos del Panel y backend;
- espacio para los archivos temporales.

## 3. Preparar el código

```text
D:\proyectos\InfoObras\
├── Pivote\
└── Panel-InfoObras\
```

Registre los commits aprobados de ambos repositorios y confirme que no hay
cambios locales sin revisar. Backend y Panel se entregan como una versión
compatible.

## 4. Configurar el servidor

```powershell
Set-Location D:\proyectos\InfoObras\Pivote\deploy
Copy-Item .env.example .env
notepad .env
```

Complete:

```dotenv
PANEL_PORT=3002
BACKEND_PORT=8001
NEXT_PUBLIC_PIVOTE_API=http://<IP-FIJA-DEL-SERVIDOR>:8001
PIVOTE_ETAPAS=real
DB_PASSWORD=<CLAVE-LARGA-Y-PRIVADA>
```

Deje `PIVOTE_MAX_DESCARGAS` vacío en producción. No use `localhost` en
`NEXT_PUBLIC_PIVOTE_API`: la usa el navegador de otra computadora. Si cambia la
IP, reconstruya el Panel.

Abra los puertos solo en la red privada:

```powershell
New-NetFirewallRule -DisplayName "InfoObras (LAN)" -Direction Inbound `
  -Protocol TCP -LocalPort 3002,8001 -Action Allow -Profile Private
```

No exponga los servicios directamente a internet.

## 5. Levantar los servicios

Desde la carpeta que contiene ambos repositorios:

```powershell
docker compose -f .\Pivote\deploy\docker-compose.yml config --quiet
docker compose -f .\Pivote\deploy\docker-compose.yml up -d --build
docker compose -f .\Pivote\deploy\docker-compose.yml ps
```

Deben aparecer saludables `db`, `backend` y `panel`. Verifique:

```powershell
curl.exe http://127.0.0.1:8001/api/pivote/salud
curl.exe -I http://127.0.0.1:3002
```

Repita con la IP fija desde otra computadora de la red.

## 6. Instalar la base MEF

Si se entrega una carga validada, cópiela al volumen persistente sin incorporar
datos de concursos. Si no existe, genere la primera:

```powershell
Set-Location D:\proyectos\InfoObras\Pivote
.\deploy\actualizar-mef.ps1
```

Compruebe `/api/pivote/salud` y registre la actualización semanal:

```powershell
.\deploy\registrar-tarea-mef.ps1
```

Ejecute una prueba manual desde el Programador de tareas y revise
`%ProgramData%\InfoObras\logs`.

## 7. Instalar la skill

El runtime vigente usa una skill enlazada; no requiere reconstruir el plugin
histórico. En la computadora del evaluador:

```powershell
$destinoSkill = Join-Path $env:USERPROFILE ".claude\skills\analizar-licitacion-osce"
New-Item -ItemType Directory -Force (Split-Path $destinoSkill) | Out-Null
New-Item -ItemType Junction -Path $destinoSkill `
  -Target "D:\proyectos\InfoObras\Pivote\skill"
Set-Location $destinoSkill
npm install
```

Si el enlace ya existe, compruebe su destino. Reinicie Claude Code y confirme
que `/analizar-licitacion-osce` está disponible.

## 8. Configurar el MCP

```powershell
Set-Location D:\proyectos\InfoObras\Pivote\mcp-server
npm install
npm test
```

Registre `mcp-server\mcp.js` en la configuración MCP de Claude Code con:

```text
SERVER_URL=http://<IP-FIJA-DEL-SERVIDOR>:8001
REQUEST_TIMEOUT=60000
```

Use rutas absolutas y doble barra inversa en JSON. Tokens y certificados se
guardan solo en configuración local. Reinicie Claude Code y pruebe la conexión.
Un `HTTP 401 token_expired` se corrige renovando la autenticación del conector;
no regenere el análisis por ese mensaje.

## 9. Prueba de aceptación

1. Abra el Panel desde una segunda computadora.
2. Cree un concurso de prueba claramente rotulado.
3. Ejecute la skill con un paquete controlado.
4. Confirme la carga MCP y pruebe también el flujo manual.
5. Espere las nueve etapas y verifique que el progreso no supere 100 %.
6. Revise CUI, SUNAT, rutas pública/privada y casos Por confirmar.
7. Descargue y abra Excel y ZIP; compruebe el índice.
8. Reinicie el stack y confirme persistencia.
9. Ejecute una propuesta real conocida contra expectativas escritas antes de
   iniciar.

La entrega se acepta cuando Panel, Excel y evidencia coinciden, no solo porque
los contenedores estén saludables.

## 10. Operación y respaldo

```powershell
docker compose -f .\Pivote\deploy\docker-compose.yml ps
docker compose -f .\Pivote\deploy\docker-compose.yml logs -f backend
docker compose -f .\Pivote\deploy\docker-compose.yml restart backend
docker compose -f .\Pivote\deploy\docker-compose.yml up -d --build
```

Respalde los volúmenes de archivos y PostgreSQL. Ejemplo del primero, desde una
carpeta privada:

```powershell
docker run --rm -v infoobras-pivote_datos_pivote:/datos `
  -v ${PWD}:/backup alpine `
  tar czf /backup/infoobras-datos.tgz -C /datos .
```

Para PostgreSQL use `pg_dump`. Pruebe la restauración en un entorno separado y
no suba respaldos al repositorio.

## 11. Diagnóstico rápido

| Síntoma | Revisión |
|---|---|
| Panel no abre en LAN | IP fija, perfil privado y firewall |
| Panel abre pero no procesa | salud del backend y servicios del compose |
| ZIP baja como texto | `NEXT_PUBLIC_PIVOTE_API`; corregir y reconstruir Panel |
| Todo cae tras reiniciar | Docker Desktop no inició con la sesión |
| Base MEF vencida | refresco, bitácora y tarea programada |
| Disco lleno | respaldar/retirar análisis autorizados o mover disco de Docker |
| MCP devuelve 401 | renovar sesión o token del conector |
