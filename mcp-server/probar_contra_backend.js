/**
 * Prueba de integración del cliente MCP contra un backend REAL (local o LAN).
 * NO forma parte del MCP; ejerce `cliente.js` sin el transporte stdio.
 *
 * Requiere el backend corriendo, p.ej.:
 *   cd backend && PIVOTE_ETAPAS=esqueleto PIVOTE_DATA_DIR=/tmp/mcp_e2e \
 *     ../venv/Scripts/uvicorn api.app:app --port 8001
 *
 * Uso:
 *   node probar_contra_backend.js [serverUrl] [rutaEspejo]
 *   node probar_contra_backend.js http://localhost:8001 ../fixtures/new_format/libertador_espejo.json
 */
import { readFileSync } from "node:fs";
import { crearCliente } from "./cliente.js";

const serverUrl = process.argv[2] || "http://localhost:8001";
const rutaEspejo = process.argv[3] || "../fixtures/new_format/libertador_espejo.json";

const cli = crearCliente({ serverUrl, log: (...a) => console.error(...a) });
const espejo = JSON.parse(readFileSync(new URL(rutaEspejo, import.meta.url), "utf-8"));

function paso(n, obj) {
  console.log(`\n${n}`);
  console.log(JSON.stringify(obj, null, 2));
}

let fallo = false;

const salud = await cli.probarConexion();
paso("1) probar_conexion", salud);
if (!salud.conexion_exitosa) fallo = true;

const sub = await cli.subirAnalisis({ json_espejo: espejo });
paso("2) subir_analisis", sub);
if (!sub.ok) fallo = true;

if (sub.ok) {
  // el pipeline corre en background; dale un momento
  await new Promise((r) => setTimeout(r, 2000));
  const est = await cli.consultarEstado(sub.job_id);
  paso("3) consultar_estado", est);
  if (!est.ok) fallo = true;
}

console.log(`\n${fallo ? "❌ FALLÓ algún paso" : "✅ OK — MCP↔backend de punta a punta"}`);
process.exit(fallo ? 1 : 0);
