#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

// Audita el crudo, ANTES del fallback folio -> paginas_pdf del consolidador.
// Nunca reordena datos evaluados: n también es la llave de sus juicios y PDFs.
function auditarOrdenEscaneo(experiencias, nProf) {
  const avisos = [];
  const emitir = (severidad, tipo, mensaje, n) => avisos.push({
    severidad, tipo, mensaje, referencia: `P${nProf}${n != null ? ` E${n}` : ""}`,
  });
  const filas = Array.isArray(experiencias) ? experiencias : [];
  if (filas.some((e, i) => e.n !== i + 1)) {
    emitir("critical", "numeracion_experiencias_invalida",
      "Las experiencias deben llegar en orden de escaneado con n contiguo 1..N. " +
      "Corregir la extracción antes de evaluar; no renumerar juicios ya emitidos.");
  }
  let anterior = null;
  const sinPagina = [];
  for (const e of filas) {
    const pagina = Array.isArray(e.paginas_pdf) ? e.paginas_pdf[0] : null;
    if (!Number.isInteger(pagina) || pagina < 1) {
      sinPagina.push(e.n);
      continue;
    }
    if (anterior && pagina < anterior.pagina) {
      emitir("critical", "orden_escaneo_invertido",
        `E${e.n} (página física ${pagina}) aparece antes en el PDF que ` +
        `E${anterior.n} (página ${anterior.pagina}). Corregir el orden en la ` +
        "extracción y repetir la evaluación; no intercambiar solo los números.", e.n);
    }
    anterior = { n: e.n, pagina };
  }
  if (sinPagina.length) {
    emitir("warning", "orden_escaneo_no_verificable",
      `Sin página física principal válida en E${sinPagina.join(", E")}: ` +
      "orden del escaneado no verificable para esas experiencias. Revisar el PDF; " +
      "el folio impreso no sustituye a la página física.");
  }
  return avisos;
}

function auditarCarpeta(carpeta) {
  const dir = path.join(carpeta, "_prof");
  const archivos = fs.readdirSync(dir).filter(n => /^profesional_\d+\.json$/.test(n)).sort();
  if (!archivos.length) throw new Error("No hay profesionales en _prof.");
  return archivos.flatMap(nombre => {
    const raw = JSON.parse(fs.readFileSync(path.join(dir, nombre), "utf8"));
    const nProf = Number(nombre.match(/\d+/)[0]);
    return auditarOrdenEscaneo(raw.experiencias, nProf);
  });
}

module.exports = { auditarOrdenEscaneo, auditarCarpeta };

if (require.main === module) {
  try {
    if (!process.argv[2]) throw new Error("Uso: node auditar_orden_experiencias.js <carpeta_analisis>");
    const avisos = auditarCarpeta(process.argv[2]);
    for (const a of avisos) console.log(`${a.severidad}: ${a.referencia}: ${a.mensaje}`);
    if (avisos.some(a => a.severidad === "critical")) {
      console.error("INCOMPLETO: corregir extracción antes de evaluar.");
      process.exitCode = 1;
    } else {
      console.log(avisos.length ? "Sin inversiones comprobadas; revisar advertencias." :
        "OK: numeración y orden entre páginas comprobados. Verificar orden intrapágina contra el PDF.");
    }
  } catch (e) {
    console.error(e.message);
    process.exitCode = 1;
  }
}
