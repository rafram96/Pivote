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
 *   UPLOAD_TIMEOUT  timeout de subida multipart en ms (default 600000)
 *   ANALISIS_DIR    única carpeta local desde la que la tool puede leer análisis
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
import { textoBusqueda, textoDescargaEstado, textoDescargaIniciada } from "./textos.js";

// ── Config ───────────────────────────────────────────────────────────────────
const SERVER_URL = (process.env.SERVER_URL || "http://127.0.0.1:8001").replace(/\/$/, "");
const ONPREM_TOKEN = process.env.ONPREM_TOKEN || null;
const REQUEST_TIMEOUT = parseInt(process.env.REQUEST_TIMEOUT || "60000", 10);
const UPLOAD_TIMEOUT = parseInt(process.env.UPLOAD_TIMEOUT || "600000", 10);
const ANALISIS_DIR = process.env.ANALISIS_DIR || null;
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
  uploadTimeoutMs: UPLOAD_TIMEOUT,
  analisisDir: ANALISIS_DIR,
  log,
});

function comoTexto(obj) {
  return { content: [{ type: "text", text: JSON.stringify(obj, null, 2) }] };
}

// Las tools que usa el evaluador a mano contestan en castellano, no en JSON:
// lo que se lee en el chat tiene que entenderlo alguien que evalúa propuestas.
function comoFrase(texto) {
  return { content: [{ type: "text", text: texto }] };
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
  "Sube un análisis desde la computadora del usuario al backend on-prem por LAN. El camino normal es carpeta_analisis: el MCP local lee espejo.json, el único Excel y certificados.zip dentro de ANALISIS_DIR y los envía como multipart. Base64 queda solo para compatibilidad. Devuelve el job_id y enlaces de descarga.",
  {
    carpeta_analisis: z.string().optional().describe("Ruta local, dentro de ANALISIS_DIR, que contiene espejo.json, un Excel .xlsx y certificados.zip opcional."),
    json_espejo: z.record(z.any()).optional().describe("Compatibilidad: objeto JSON espejo cuando no se usa carpeta_analisis."),
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
  async (args) => {
    if (args.carpeta_analisis && args.json_espejo) {
      return comoTexto({ ok: false, error: "usa carpeta_analisis o json_espejo/base64, no ambos" });
    }
    if (args.carpeta_analisis) {
      return comoTexto(await cli.subirAnalisisDesdeCarpeta(args));
    }
    return comoTexto(await cli.subirAnalisis(args));
  }
);

server.tool(
  "consultar_estado",
  "Consulta el estado de un análisis subido (GET /api/pivote/jobs/{job_id}): estado, etapa actual, cuántos items requieren revisión humana, y enlaces de descarga del Excel/ZIP.",
  { job_id: z.string().describe("job_id que devolvió subir_analisis.") },
  async ({ job_id }) => comoTexto(await cli.consultarEstado(job_id))
);

// ── Consulta y descarga de una obra por su CUI ───────────────────────────────

server.tool(
  "buscar_cui",
  "Busca el código único de inversión (CUI) de una obra por su nombre, en la base local del MEF que tiene el servidor de InfoObras. Úsala cuando el usuario pregunte «cuál es el CUI de…», «búscame el hospital de Abancay» o tenga el nombre de una obra y le falte el código. Es una consulta local: no sale a internet ni depende de portales. Devuelve los mejores candidatos con nombre, ubicación y entidad.",
  {
    q: z.string().describe("Nombre de la obra (o un CUI/SNIP, si ya lo tiene y quiere confirmarlo)."),
    dpto: z.string().optional().describe("Departamento, para acotar (p.ej. «Apurímac»)."),
    prov: z.string().optional().describe("Provincia, para acotar."),
    dist: z.string().optional().describe("Distrito, para acotar."),
    entidad: z.string().optional().describe("Entidad a cargo, aunque sea parcial (p.ej. «gobierno regional»)."),
    limite: z.number().int().min(1).max(50).optional().describe("Cuántos candidatos mostrar (por defecto 10)."),
  },
  async (args) => comoFrase(textoBusqueda(await cli.buscarCui(args), { q: args.q }))
);

server.tool(
  "descargar_documentos_cui",
  "Pide al servidor que baje de InfoObras TODOS los documentos de una obra a partir de su CUI: valorizaciones, informes de control, datos de cierre y la aprobación del expediente. Úsala cuando el usuario diga «bájame los papeles/documentos de esta obra» o «descarga el CUI X». Contesta al instante con un número de seguimiento; la descarga sigue en el servidor y puede tardar minutos. Los archivos NO viajan por el chat: al terminar se entrega la dirección del ZIP.",
  {
    cui: z.string().describe("Código único de inversión (solo números)."),
    fecha_inicio: z
      .string()
      .optional()
      .describe("AAAA-MM-DD. Acota los informes de control al periodo de la experiencia."),
    fecha_fin: z.string().optional().describe("AAAA-MM-DD. Fin del periodo."),
  },
  async (args) => comoFrase(textoDescargaIniciada(await cli.descargarPorCui(args)))
);

server.tool(
  "consultar_descarga_cui",
  "Consulta cómo va una descarga de documentos por CUI, con el número de seguimiento que devolvió descargar_documentos_cui. Dice en qué tramo está, cuántos documentos lleva y, cuando termina, de dónde bajar el ZIP.",
  {
    descarga_id: z.string().describe("Número de seguimiento que devolvió descargar_documentos_cui."),
  },
  async ({ descarga_id }) => comoFrase(textoDescargaEstado(await cli.consultarDescargaCui(descarga_id)))
);

// ── Arranque ─────────────────────────────────────────────────────────────────
async function main() {
  log("─".repeat(50));
  log("MCP infoobras-onprem-bridge v0.2.0 (stdio) → backend real");
  log(`SERVER_URL = ${SERVER_URL}`);
  log(`auth = ${ONPREM_TOKEN ? "Bearer (configurado)" : "ninguna"}`);
  log(`timeout = ${REQUEST_TIMEOUT}ms`);
  log(`upload timeout = ${UPLOAD_TIMEOUT}ms`);
  log(`ANALISIS_DIR = ${ANALISIS_DIR || "NO CONFIGURADO (rutas locales deshabilitadas)"}`);
  log("─".repeat(50));
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("MCP conectado y escuchando tool calls por stdio.");
}

main().catch((e) => {
  log(`FATAL: ${e?.stack || e}`);
  process.exit(1);
});
