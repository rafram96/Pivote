#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { normalizarBasesCriticas, auditarFechas } = require("./entradas_criticas");
const { prepararProfesional } = require("./preparar_extraccion");

function auditarCarpeta(carpeta, { guardar = false } = {}) {
  const leer = p => JSON.parse(fs.readFileSync(p, "utf8"));
  const avisos = normalizarBasesCriticas(leer(path.join(carpeta, "bases.json"))).avisos;
  const dir = path.join(carpeta, "_prof");
  const archivos = fs.readdirSync(dir).filter(n => /^profesional_\d+\.json$/.test(n)).sort();
  if (!archivos.length) throw new Error("No hay profesionales en _prof.");
  const preparados = [], revisiones = [], fuentes = [];
  for (const nombre of archivos) {
    const archivo = path.join(dir, nombre);
    const nProf = Number(nombre.match(/\d+/)[0]);
    const resultado = prepararProfesional(leer(archivo), nProf);
    preparados.push(resultado.profesional);
    revisiones.push(...resultado.revisiones);
    avisos.push(...resultado.avisos, ...auditarFechas(resultado.profesional.experiencias, nProf));
    fuentes.push({ archivo: `_prof/${nombre}`, sha256: crypto.createHash("sha256").update(fs.readFileSync(archivo)).digest("hex") });
  }
  if (guardar) {
    // Copias derivadas; jamás sobrescribir los crudos del extractor. Se escribe
    // un listado completo para no mezclar profesionales de una preparación vieja.
    fs.writeFileSync(path.join(carpeta, "profesionales_preparados.json"), JSON.stringify({
      version: 1, fuentes, profesionales: preparados,
    }, null, 2) + "\n", "utf8");
    fs.writeFileSync(path.join(carpeta, "revisiones_extraccion.json"), JSON.stringify({
      version: 1, fuentes, revisiones,
    }, null, 2) + "\n", "utf8");
  }
  return avisos;
}
module.exports = { auditarCarpeta };
if (require.main === module) {
  try {
    if (!process.argv[2]) throw new Error("Uso: node auditar_entradas_criticas.js <carpeta_analisis>");
    const avisos = auditarCarpeta(process.argv[2], { guardar: true });
    for (const a of avisos) console.log(`${a.severidad}: ${a.tipo}: ${a.referencia}: ${a.mensaje}`);
    if (avisos.some(a => a.severidad === "critical")) {
      console.error("INCOMPLETO: corregir las entradas en el agente indicado antes de evaluar. No repetir otros profesionales.");
      process.exitCode = 1;
    } else console.log("OK: profesionales_preparados.json listo. Revisar revisiones_extraccion.json antes del evaluador; los campos irresueltos quedan por verificar.");
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
