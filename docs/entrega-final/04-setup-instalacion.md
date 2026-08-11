# Setup e instalación — InfoObras

> Documento para el responsable técnico. La instalación final se ejecuta solo
> cuando la entrega esté autorizada. No copie contraseñas, datos de concursos ni
> direcciones privadas de red al repositorio.

## 1. Arquitectura de entrega

- **Servidor Windows:** Panel, backend, PostgreSQL y datos persistentes mediante
  Docker Compose; Nginx se ejecuta como contenedor independiente y se conecta a
  la red del sistema para publicar el Panel con un dominio local.
- **Computadora del evaluador:** Claude Code, skill y conector MCP por la red
  local.

El backend no consume servicios de IA en la nube. La extracción ocurre en
Claude Code; el servidor verifica fuentes, recalcula y genera entregables.

## 2. Requisitos

### Servidor

- Windows 11, Docker Desktop con WSL 2 y arranque al iniciar sesión;
- acceso saliente a fuentes públicas;
- IP local fija o reserva DHCP;
- nombre asignado en el DNS local, o acceso para registrarlo temporalmente en
  el archivo `hosts` de las computadoras usuarias;
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

## 6. Pendiente de despliegue: dominio local con Nginx

El Panel debe entregarse con un nombre fácil de recordar, por ejemplo
`http://<DOMINIO-LOCAL>`, en lugar de exigir al usuario la IP y el puerto 3002.
Este punto todavía debe configurarse en el servidor final.

Nginx **no forma parte de `docker-compose.yml`**. Se crea y administra como un
contenedor independiente para no acoplar su ciclo de vida al stack. Su única
integración es conectarse a la red Docker que Compose crea para InfoObras:

```text
infoobras-pivote_default
```

Después de levantar `db`, `backend` y `panel`, cree en una carpeta operacional
privada, por ejemplo `D:\servicios\infoobras-nginx\nginx.conf`, una configuración
como esta:

```nginx
server {
    listen 80;
    server_name <DOMINIO-LOCAL>;

    location / {
        proxy_pass http://panel:3002;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Inicie Nginx desde esa carpeta, fuera de Compose:

```powershell
Set-Location D:\servicios\infoobras-nginx
docker run -d --name infoobras-nginx --restart unless-stopped `
  --network infoobras-pivote_default `
  -p 80:80 `
  -v "${PWD}\nginx.conf:/etc/nginx/conf.d/default.conf:ro" `
  nginx:alpine
```

Registre `<DOMINIO-LOCAL>` en el DNS de la red apuntando a la IP fija del
servidor. Para una prueba temporal puede añadirse `IP DOMINIO` al archivo
`C:\Windows\System32\drivers\etc\hosts` de cada equipo, pero esto no sustituye
el DNS de la entrega. Abra el puerto 80 únicamente para el perfil privado:

```powershell
New-NetFirewallRule -DisplayName "InfoObras Nginx (LAN)" -Direction Inbound `
  -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
```

Compruebe desde otra computadora:

```powershell
curl.exe -I http://<DOMINIO-LOCAL>
docker inspect infoobras-nginx --format '{{json .NetworkSettings.Networks}}'
```

La respuesta debe ser satisfactoria y la inspección debe mostrar
`infoobras-pivote_default`. El puerto 3002 puede conservarse durante el
diagnóstico; para la operación cotidiana se comunica únicamente el dominio.

Como Nginx es externo a Compose, `docker compose stop`, `restart` y `up` no lo
administran. Antes de ejecutar `docker compose down`, desconéctelo o elimínelo
para que Docker pueda retirar la red sin dejar endpoints activos:

```powershell
docker rm -f infoobras-nginx
docker compose -f .\Pivote\deploy\docker-compose.yml down
```

Al levantar nuevamente el stack, vuelva a ejecutar el `docker run` anterior.

## 7. Instalar la base MEF

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

## 8. Instalar la skill

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

## 9. Configurar el MCP

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

## 10. Prueba de aceptación

1. Abra el dominio local del Panel desde una segunda computadora.
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

## 11. Operación y respaldo

```powershell
docker compose -f .\Pivote\deploy\docker-compose.yml ps
docker compose -f .\Pivote\deploy\docker-compose.yml logs -f backend
docker compose -f .\Pivote\deploy\docker-compose.yml restart backend
docker compose -f .\Pivote\deploy\docker-compose.yml up -d --build
docker logs --tail 100 infoobras-nginx
docker restart infoobras-nginx
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

## 12. Diagnóstico rápido

| Síntoma | Revisión |
|---|---|
| Panel no abre en LAN | IP fija, perfil privado y firewall |
| Dominio local no resuelve | registro DNS/`hosts` y dirección IP del servidor |
| Dominio responde 502 | estado de `panel` y conexión de Nginx a `infoobras-pivote_default` |
| Panel abre pero no procesa | salud del backend y servicios del compose |
| ZIP baja como texto | `NEXT_PUBLIC_PIVOTE_API`; corregir y reconstruir Panel |
| Todo cae tras reiniciar | Docker Desktop no inició con la sesión |
| Base MEF vencida | refresco, bitácora y tarea programada |
| Disco lleno | respaldar/retirar análisis autorizados o mover disco de Docker |
| MCP devuelve 401 | renovar sesión o token del conector |
