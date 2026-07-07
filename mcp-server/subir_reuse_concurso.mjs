// Reenvía una carpeta de análisis reutilizando un concurso_id existente.
// Uso: node subir_reuse_concurso.mjs "<carpeta>" <concurso_id> [serverUrl]
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { crearCliente } from "./cliente.js";

const carpeta = process.argv[2];
const concurso_id = process.argv[3];
const serverUrl = process.argv[4] || "http://127.0.0.1:8001";
if (!carpeta || !concurso_id) { console.error("uso: node subir_reuse_concurso.mjs <carpeta> <concurso_id> [serverUrl]"); process.exit(1); }

const espejo = JSON.parse(readFileSync(join(carpeta, "espejo.json"), "utf-8"));
const xlsx = readdirSync(carpeta).find((f) => /^Formato_Evaluacion.*\.xlsx$/i.test(f)) || readdirSync(carpeta).find((f) => f.toLowerCase().endsWith(".xlsx"));
const excel_base64 = xlsx ? readFileSync(join(carpeta, xlsx)).toString("base64") : null;
const zipPath = join(carpeta, "certificados.zip");
const certificados_base64 = existsSync(zipPath) ? readFileSync(zipPath).toString("base64") : null;

const cli = crearCliente({ serverUrl, timeoutMs: 300000, log: (...a) => console.error(...a) });
console.error(`→ reenviando ${carpeta}\n  concurso_id:${concurso_id} · excel:${xlsx || "-"} · zip:${certificados_base64 ? (readFileSync(zipPath).length/1048576).toFixed(0)+"MB" : "no"}`);

const r = await cli.subirAnalisis({ json_espejo: espejo, excel_base64, certificados_base64, concurso_id });
console.log("\n== subir_analisis ==");
console.log(JSON.stringify(r, null, 2));
if (r.ok) {
  await new Promise((res) => setTimeout(res, 3000));
  console.log("\n== consultar_estado ==");
  console.log(JSON.stringify(await cli.consultarEstado(r.job_id), null, 2));
}
process.exit(r.ok ? 0 : 1);
