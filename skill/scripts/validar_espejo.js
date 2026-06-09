#!/usr/bin/env node
"use strict";
/**
 * validar_espejo.js — Valida un JSON espejo contra el schema zod.
 * Versión Node (la PC del ingeniero solo tiene Node).
 *
 * Uso:  node scripts/validar_espejo.js <ruta_json>
 * Salida: "OK · …" (exit 0) o "INVÁLIDO · …" con errores por campo (exit 1).
 */
const fs = require("fs");
const path = require("path");
const { JsonEspejo } = require(path.resolve(__dirname, "../schemas/espejo.js"));

function main() {
  const ruta = process.argv[2];
  if (!ruta) {
    console.error("Uso: node scripts/validar_espejo.js <ruta_json>");
    process.exit(2);
  }
  let data;
  try {
    data = JSON.parse(fs.readFileSync(ruta, "utf-8"));
  } catch (e) {
    console.log(`ERROR: no se pudo leer/parsear JSON: ${e.message}`);
    process.exit(1);
  }

  const res = JsonEspejo.safeParse(data);
  if (!res.success) {
    const issues = res.error.issues;
    console.log(`INVÁLIDO · ${issues.length} error(es):`);
    for (const it of issues) {
      const loc = it.path.join(".") || "(raíz)";
      console.log(`  - [${loc}] ${it.message}`);
    }
    process.exit(1);
  }

  const esp = res.data;
  const nprof = esp.profesionales.length;
  const nexp = esp.profesionales.reduce((s, p) => s + (p.experiencias ? p.experiencias.length : 0), 0);
  console.log(
    `OK · espejo válido · ${nprof} profesionales · ${nexp} experiencias · ` +
    `postor_exp=${esp.postor.experiencia_postor.length} · ` +
    `factores=${esp.resumen_evaluacion.factores.length}`
  );
  process.exit(0);
}

main();
