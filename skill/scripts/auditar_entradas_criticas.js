#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const { normalizarBasesCriticas, auditarFechas } = require("./entradas_criticas");

function auditarCarpeta(carpeta) {
  const leer = p => JSON.parse(fs.readFileSync(p, "utf8"));
  const avisos = normalizarBasesCriticas(leer(path.join(carpeta, "bases.json"))).avisos;
  const dir = path.join(carpeta, "_prof");
  const archivos = fs.readdirSync(dir).filter(n => /^profesional_\d+\.json$/.test(n)).sort();
  if (!archivos.length) throw new Error("No hay profesionales en _prof.");
  for (const nombre of archivos) {
    avisos.push(...auditarFechas(leer(path.join(dir, nombre)).experiencias, Number(nombre.match(/\d+/)[0])));
  }
  return avisos;
}
module.exports = { auditarCarpeta };
if (require.main === module) {
  try {
    if (!process.argv[2]) throw new Error("Uso: node auditar_entradas_criticas.js <carpeta_analisis>");
    const avisos = auditarCarpeta(process.argv[2]);
    for (const a of avisos) console.log(`${a.severidad}: ${a.tipo}: ${a.referencia}: ${a.mensaje}`);
    if (avisos.some(a => a.severidad === "critical")) {
      console.error("INCOMPLETO: corregir las entradas en el agente indicado antes de evaluar. No repetir otros profesionales.");
      process.exitCode = 1;
    } else console.log("OK: entradas críticas estructuradas y cotejos registrados; esto no sustituye la lectura de las fuentes.");
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
