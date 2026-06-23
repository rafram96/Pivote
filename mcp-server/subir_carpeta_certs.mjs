/**
 * Sube una carpeta de análisis (espejo.json + Excel + certificados.zip) al backend
 * on-prem por el cliente MCP, incluyendo las constancias recortadas.
 *
 * Uso: node subir_carpeta_certs.mjs "<carpeta>" [serverUrl]
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { crearCliente } from "./cliente.js";

const carpeta = process.argv[2];
const serverUrl = process.argv[3] || "http://127.0.0.1:8001";
if (!carpeta) { console.error("uso: node subir_carpeta_certs.mjs <carpeta> [serverUrl]"); process.exit(1); }

const espejo = JSON.parse(readFileSync(join(carpeta, "espejo.json"), "utf-8"));
const xlsx = readdirSync(carpeta).find((f) => f.toLowerCase().endsWith(".xlsx"));
const excel_base64 = xlsx ? readFileSync(join(carpeta, xlsx)).toString("base64") : null;
const zipPath = join(carpeta, "certificados.zip");
const certificados_base64 = existsSync(zipPath) ? readFileSync(zipPath).toString("base64") : null;

const cli = crearCliente({ serverUrl, timeoutMs: 180000, log: (...a) => console.error(...a) });
console.error(`→ subiendo ${carpeta}\n  espejo + excel:${xlsx || "-"} + zip:${certificados_base64 ? "sí" : "no"}`);

const r = await cli.subirAnalisis({ json_espejo: espejo, excel_base64, certificados_base64 });
console.log("\n== subir_analisis ==");
console.log(JSON.stringify(r, null, 2));

if (r.ok) {
  await new Promise((res) => setTimeout(res, 2000));
  console.log("\n== consultar_estado ==");
  console.log(JSON.stringify(await cli.consultarEstado(r.job_id), null, 2));
}
process.exit(r.ok ? 0 : 1);
