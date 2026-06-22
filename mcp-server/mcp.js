/**
 * MCP local — puente Cowork ⇄ backend on-prem (LAN) del pivote InfoObras.
 *
 *   Claude (Cowork) ──tool call──▶ este MCP (stdio) ──HTTP──▶ backend real
 *                    ◀──response──                  ◀──HTTP──
 *
 * Es un proceso normal en la máquina del usuario, así que puede hacer fetch() al
 * backend on-prem aunque NO esté expuesto a internet. Cablea el "Camino A" del
 * refactor contra los endpoints REALES (backend/api/app.py) — ya no el server de
 * juguete: crea/usa el concurso, sube el espejo+Excel como multipart a
 * /api/pivote/analizar, y consulta el estado del job.
 *
 * Transporte: stdio (Cowork lo lanza como subproceso). Por eso:
 *   ⚠ NUNCA usar console.log — stdout es el canal del protocolo MCP.
 *     Todo log va a stderr (console.error) y, opcional, a un archivo.
 *
 * Config por variables de entorno (en el `env` del MCP en Cowork):
 *   SERVER_URL      base del backend (default http://localhost:8001)
 *   ONPREM_TOKEN    token Bearer opcional (no hardcodear credenciales)
 *   REQUEST_TIMEOUT timeout HTTP en ms (default 60000)
 *   LOG_FILE        ruta opcional de archivo de log
 *   NODE_EXTRA_CA_CERTS  (nativo de Node) CA bundle si el backend usa HTTPS interno
 *
 * Requiere: Node 18+ (fetch/FormData/Blob globales) + `npm install`.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { appendFileSync } from "node:fs";
import { crearCliente } from "./cliente.js";

// ── Config ───────────────────────────────────────────────────────────────────
const SERVER_URL = (process.env.SERVER_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const ONPREM_TOKEN = process.env.ONPREM_TOKEN || null;
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT || "60000", 10);
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

const cli = crearCliente({
  serverUrl: SERVER_URL,
  token: ONPREM_TOKEN,
  timeoutMs: REQUEST_TIMEOUT,
  log,
});

function comoTexto(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

// ── Servidor MCP ─────────────────────────────────────────────────────────────
const server = new McpServer({ name: "infoobras-onprem-bridge", version: "0.2.0" });

server.tool(
  "probar_conexion",
  "Verifica que el backend on-prem de InfoObras responde (GET /api/pivote/salud) y devuelve el estado de los portales SUNAT/InfoObras. Úsalo para confirmar que el puente Cowork→LAN funciona.",
  {},
  async () => comoTexto(await cli.probarConexion())
);

server.tool(
  "listar_concursos",
  "Lista los concursos registrados en el backend, para elegir uno existente antes de subir un análisis o para ver el histórico.",
  {},
  async () => comoTexto(await cli.listarConcursos())
);

server.tool(
  "subir_analisis",
  "Sube el análisis de Claude (JSON espejo v1.2.0 + Excel) al backend on-prem, que hace los cruces SUNAT/InfoObras y calcula los días efectivos. Si no pasas concurso_id, crea el concurso (nomenclatura = _meta.concurso). Devuelve el job_id para seguir el estado y los enlaces de descarga.",
  {
    json_espejo: z.record(z.any()).describe("Objeto JSON espejo (contrato v1.2.0) producido por la skill."),
    excel_base64: z
      .string()
      .optional()
      .describe("Excel 'Formato de Evaluación' en base64 (el backend lo guarda como referencia y regenera el enriquecido)."),
    certificados_base64: z
      .string()
      .optional()
      .describe("ZIP en base64 de las constancias recortadas por la skill (extraer_certificados.js → P{n}_E{m}.pdf, página principal primero). El backend las embebe en cada bloque CERT N°X."),
    concurso_id: z
      .string()
      .optional()
      .describe("ID de un concurso existente (de listar_concursos). Si se omite, se crea uno."),
    concurso: z
      .object({
        nomenclatura: z.string().optional(),
        entidad: z.string().optional(),
        fecha_presentacion: z.string().optional(),
      })
      .partial()
      .optional()
      .describe("Datos para crear el concurso si no hay concurso_id; nomenclatura por defecto = _meta.concurso."),
  },
  async (args) => comoTexto(await cli.subirAnalisis(args))
);

server.tool(
  "consultar_estado",
  "Consulta el estado de un análisis subido (GET /api/pivote/jobs/{job_id}): estado, etapa actual, cuántos items requieren revisión humana, y enlaces de descarga del Excel/ZIP.",
  { job_id: z.string().describe("job_id que devolvió subir_analisis.") },
  async ({ job_id }) => comoTexto(await cli.consultarEstado(job_id))
);

// ── Arranque ─────────────────────────────────────────────────────────────────
async function main() {
  log("─".repeat(50));
  log("MCP infoobras-onprem-bridge v0.2.0 (stdio) → backend real");
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
