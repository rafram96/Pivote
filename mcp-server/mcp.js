/**
 * MCP local de prueba — puente Cowork ⇄ servidor on-prem (LAN).
 *
 * Propósito: validar de punta a punta el "Camino A" del refactor InfoObras:
 *   Claude (Cowork) ──tool call──▶ este MCP (stdio) ──HTTP──▶ servidor LAN
 *                    ◀──response──                  ◀──HTTP──
 *
 * Es un proceso normal en la máquina del usuario, así que dentro de cada tool
 * puede hacer fetch() a cualquier IP/host que su red resuelva — incluido el
 * servidor on-prem NO expuesto a internet.
 *
 * Transporte: stdio (Cowork lo lanza como subproceso). Por eso:
 *   ⚠ NUNCA usar console.log — stdout es el canal del protocolo MCP.
 *     Todo log va a stderr (console.error) y, opcional, a un archivo.
 *
 * Config por variables de entorno (se setean en el `env` del MCP en Cowork):
 *   SERVER_URL      base del servidor (default http://localhost:8090)
 *   ONPREM_TOKEN    token Bearer opcional (no hardcodear credenciales)
 *   REQUEST_TIMEOUT timeout HTTP en ms (default 30000)
 *   LOG_FILE        ruta opcional de archivo de log
 *   NODE_EXTRA_CA_CERTS  (nativo de Node) ruta a CA bundle si el server usa
 *                        HTTPS con certificado interno
 *
 * Requiere: Node 18+ (usa fetch global) + `npm install`.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { appendFileSync } from "node:fs";

// ── Config ───────────────────────────────────────────────────────────────────
const SERVER_URL = (process.env.SERVER_URL || "http://localhost:8090").replace(/\/$/, "");
const ONPREM_TOKEN = process.env.ONPREM_TOKEN || null;
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT || "30000", 10);
const LOG_FILE = process.env.LOG_FILE || null;

// ── Logging (stderr + archivo opcional, NUNCA stdout) ────────────────────────
function log(...args) {
  const linea = `[${new Date().toISOString()}] ${args.map(String).join(" ")}`;
  console.error(linea); // stderr — seguro bajo stdio
  if (LOG_FILE) {
    try {
      appendFileSync(LOG_FILE, linea + "\n");
    } catch {
      /* no romper el MCP por un fallo de log */
    }
  }
}

// ── Helper HTTP con timeout finito ───────────────────────────────────────────
async function pedir(metodo, ruta, body) {
  const url = `${SERVER_URL}/${ruta.replace(/^\//, "")}`;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT);
  const headers = { "Content-Type": "application/json" };
  if (ONPREM_TOKEN) headers["Authorization"] = `Bearer ${ONPREM_TOKEN}`;

  log(`→ ${metodo} ${url}`);
  try {
    const resp = await fetch(url, {
      method: metodo,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
    const texto = await resp.text();
    let data;
    try {
      data = JSON.parse(texto);
    } catch {
      data = { _raw: texto };
    }
    log(`← ${resp.status} (${texto.length} bytes)`);
    return { status: resp.status, ok: resp.ok, data };
  } catch (err) {
    const msg = err?.name === "AbortError"
      ? `timeout tras ${REQUEST_TIMEOUT}ms`
      : String(err?.message || err);
    log(`✗ error: ${msg}`);
    return { status: 0, ok: false, data: { error: msg } };
  } finally {
    clearTimeout(t);
  }
}

function comoTexto(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

// ── Servidor MCP ─────────────────────────────────────────────────────────────
const server = new McpServer({ name: "infoobras-onprem-bridge", version: "0.1.0" });

// Tool 1 — test de conectividad puro
server.tool(
  "probar_conexion",
  "Verifica que el servidor on-prem de InfoObras está accesible desde esta máquina (GET /health). Úsalo para confirmar que el puente Cowork→LAN funciona.",
  {},
  async () => {
    const r = await pedir("GET", "/health");
    return comoTexto({
      conexion_exitosa: r.ok,
      server_url: SERVER_URL,
      status_http: r.status,
      respuesta_servidor: r.data,
    });
  }
);

// Tool 2 — eco (ida y vuelta de datos)
server.tool(
  "eco",
  "Envía un mensaje al servidor on-prem y devuelve lo que el servidor responde (POST /echo). Sirve para probar que los datos viajan ida y vuelta.",
  { mensaje: z.string().describe("Texto o dato a enviar como prueba") },
  async ({ mensaje }) => {
    const r = await pedir("POST", "/echo", { mensaje });
    return comoTexto({ ok: r.ok, status_http: r.status, respuesta_servidor: r.data });
  }
);

// Tool 3 — flujo realista simulado
server.tool(
  "subir_y_validar",
  "Sube el Excel (base64) y el JSON espejo al servidor on-prem para validación y cruces SUNAT/InfoObras (POST /subir_y_validar). En el prototipo el servidor devuelve un reporte simulado.",
  {
    excel_base64: z.string().optional().describe("Excel codificado en base64 (opcional en prueba)"),
    json_espejo: z.record(z.any()).describe("Objeto JSON espejo con los datos extraídos por Claude"),
  },
  async ({ excel_base64, json_espejo }) => {
    const r = await pedir("POST", "/subir_y_validar", {
      excel: excel_base64 || null,
      json: json_espejo,
    });
    return comoTexto({ ok: r.ok, status_http: r.status, reporte: r.data });
  }
);

// ── Arranque ─────────────────────────────────────────────────────────────────
async function main() {
  log("─".repeat(50));
  log("MCP infoobras-onprem-bridge arrancando (stdio)");
  log(`SERVER_URL = ${SERVER_URL}`);
  log(`auth = ${ONPREM_TOKEN ? "Bearer (configurado)" : "ninguna"}`);
  log(`timeout = ${REQUEST_TIMEOUT}ms`);
  log("─".repeat(50));
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("MCP conectado y escuchando tool calls por stdio.");
}

main().catch((e) => {
  log(`FATAL: ${e?.stack || e}`);
  process.exit(1);
});
