/**
 * Sube una carpeta de análisis (espejo.json + Excel + certificados.zip) al backend
 * on-prem por el cliente MCP, incluyendo las constancias recortadas.
 *
 * Uso: node subir_carpeta_certs.mjs "<carpeta>" [serverUrl]
 */
import { dirname, resolve } from "node:path";
import { crearCliente } from "./cliente.js";

const carpeta = process.argv[2];
const serverUrl = process.argv[3] || "http://127.0.0.1:8001";
if (!carpeta) { console.error("uso: node subir_carpeta_certs.mjs <carpeta> [serverUrl]"); process.exit(1); }

const carpetaCanonica = resolve(carpeta);
const cli = crearCliente({
  serverUrl,
  timeoutMs: 60000,
  uploadTimeoutMs: 600000,
  analisisDir: dirname(carpetaCanonica),
  log: (...a) => console.error(...a),
});
console.error(`→ subiendo por ruta local ${carpetaCanonica}`);

const r = await cli.subirAnalisisDesdeCarpeta({ carpeta_analisis: carpetaCanonica });
console.log("\n== subir_analisis ==");
console.log(JSON.stringify(r, null, 2));

if (r.ok) {
  await new Promise((res) => setTimeout(res, 2000));
  console.log("\n== consultar_estado ==");
  console.log(JSON.stringify(await cli.consultarEstado(r.job_id), null, 2));
}
process.exit(r.ok ? 0 : 1);
