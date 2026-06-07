# Prueba de conexión Cowork → servidor on-prem (Camino A)

> **Objetivo**: validar empíricamente el único supuesto del refactor que aún
> no probamos — que un **MCP local** lanzado por Cowork puede alcanzar un
> **servidor HTTP en la red** (que en producción será el backend on-prem NO
> expuesto a internet) y devolverle la respuesta a Claude.
>
> Si esto funciona, el "todo automático desde Cowork" que se le prometería a
> Manuel está confirmado.

```
Claude (Cowork) ──tool call──▶ MCP local (stdio) ──HTTP POST──▶ servidor LAN
                 ◀──response──                    ◀──HTTP resp──
```

## Estructura

```
src/connection/
├── server/                     # simula el backend on-prem
│   ├── server.js               # HTTP nativo (sin deps): /health /echo /subir_y_validar
│   └── package.json
└── mcp/                        # el puente que corre en la PC del usuario
    ├── mcp.js                  # MCP stdio (SDK @modelcontextprotocol)
    ├── package.json
    └── cowork-config-ejemplo.json
```

## Paso 1 — Arrancar el servidor de prueba

El servidor **no tiene dependencias** (solo Node nativo).

```bash
cd src/connection/server
node server.js
```

Debe imprimir las IPs de la máquina en la LAN y quedar escuchando en
`http://localhost:8090`. Verifica en el navegador o con curl:

```bash
curl http://localhost:8090/health
```

## Paso 2 — Instalar dependencias del MCP

```bash
cd src/connection/mcp
npm install
```

(Descarga `@modelcontextprotocol/sdk` y `zod`.)

## Paso 3 — Registrar el MCP en Cowork

1. Abre la config de MCP de Cowork (`claude_desktop_config.json` o equivalente).
2. Copia el bloque de `cowork-config-ejemplo.json` dentro de `mcpServers`.
3. **Ajusta la ruta absoluta** de `mcp.js`.
4. Reinicia Cowork para que cargue el MCP.

## Paso 4 — Probar desde Cowork

Con el servidor del Paso 1 corriendo, pídele a Claude en Cowork:

1. **"Usa la tool `probar_conexion`"**
   → Debe devolver `conexion_exitosa: true` + el `/health` del servidor.
   ✅ Esto solo ya prueba que Cowork → MCP → servidor funciona.

2. **"Usa `eco` con el mensaje 'hola on-prem'"**
   → Debe devolver el mensaje reflejado por el servidor (ida y vuelta).

3. **"Usa `subir_y_validar` con este json_espejo: {...}"**
   → Debe devolver el reporte simulado (faltantes, alertas SUNAT/InfoObras).

En la terminal del servidor verás los logs de cada request entrante con la IP
de origen — confirmación de que el tráfico llegó.

## Paso 5 — Subir el listón: IP de LAN real

Una vez que funcione con `localhost`, el salto al caso on-prem es trivial:

1. Deja el servidor corriendo (ya escucha en `0.0.0.0`, todas las interfaces).
2. En la config del MCP, cambia `SERVER_URL` a la IP LAN de la máquina del
   servidor (ej. `http://192.168.1.50:8090`).
3. Reinicia Cowork y repite el Paso 4.

Si funciona con la IP LAN → **Camino A validado**: el MCP en la PC de Manuel
podrá hablar con el backend on-prem en su red sin exponerlo a internet.

## Qué cuidar en el despliegue real (no en la prueba)

- **Auth**: setear `ONPREM_TOKEN` en el `env` del MCP (no hardcodear).
- **HTTPS con CA interna**: setear `NODE_EXTRA_CA_CERTS` con el bundle.
- **Firewall**: el puerto del servidor abierto para la PC de Manuel en la LAN.
- **Timeouts**: ya configurados finitos (`REQUEST_TIMEOUT`, default 30s).

## Criterio de éxito

| Prueba | Éxito |
|---|---|
| `probar_conexion` con localhost | `conexion_exitosa: true` |
| `eco` ida y vuelta | mensaje reflejado |
| `subir_y_validar` | reporte simulado recibido |
| Repetir con IP LAN real | los 3 anteriores funcionan |

Si los 4 pasan → el transporte automático del refactor está probado y se le
puede prometer a Manuel sin riesgo.
