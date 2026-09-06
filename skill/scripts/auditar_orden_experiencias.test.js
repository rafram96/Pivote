"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { auditarOrdenEscaneo } = require("./auditar_orden_experiencias");
const fila = (n, pagina, extras = {}) => ({ n, paginas_pdf: [pagina], ...extras });

test("escaneado manda sobre fechas, folios impresos y páginas de anexos", () => {
  const filas = [fila(1, 20, { paginas_pdf: [20, 2], folio: 300, fecha_final: "2025-01-01" }),
    fila(2, 21, { folio: 10, fecha_final: "2020-01-01" })];
  const copia = structuredClone(filas);
  assert.deepEqual(auditarOrdenEscaneo(filas, 1), []);
  assert.deepEqual(filas, copia);
});

test("inversión por fecha final dispara crítico sin renumerar", () => {
  const filas = [fila(1, 25), fila(2, 20)];
  const avisos = auditarOrdenEscaneo(filas, 3);
  assert.equal(avisos[0].tipo, "orden_escaneo_invertido");
  assert.equal(avisos[0].severidad, "critical");
  assert.equal(avisos[0].referencia, "P3 E2");
  assert.deepEqual(filas.map(e => e.n), [1, 2]);
});

test("periodos en una misma página conservan el orden de aparición", () => {
  assert.deepEqual(auditarOrdenEscaneo([fila(1, 20), fila(2, 20), fila(3, 22)], 1), []);
});

test("página ausente no se sustituye por folio ni por un anexo", () => {
  for (const paginas_pdf of [null, [], [null, 30], [0], [-1], [2.5], ["20"]]) {
    const avisos = auditarOrdenEscaneo([fila(1, null, { paginas_pdf, folio: 50 })], 1);
    assert.equal(avisos.length, 1);
    assert.equal(avisos[0].tipo, "orden_escaneo_no_verificable");
    assert.equal(avisos[0].severidad, "warning");
  }
});

test("un hueco de páginas no oculta inversiones entre las conocidas", () => {
  const avisos = auditarOrdenEscaneo([fila(1, 30), fila(2, null), fila(3, 20)], 1);
  assert.ok(avisos.some(a => a.tipo === "orden_escaneo_invertido"));
  assert.ok(avisos.some(a => a.tipo === "orden_escaneo_no_verificable"));
});

test("numeración duplicada, desplazada o ausente bloquea antes del evaluador", () => {
  for (const ns of [[1, 1], [2, 3], [2, 1], [1, null]]) {
    assert.ok(auditarOrdenEscaneo(ns.map((n, i) => fila(n, 20 + i)), 1)
      .some(a => a.tipo === "numeracion_experiencias_invalida" && a.severidad === "critical"));
  }
});

test("CLI previo al evaluador es solo lectura y bloquea un profesional invertido", (t) => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "orden-escaneo-test-"));
  t.after(() => fs.rmSync(ws, { recursive: true, force: true }));
  fs.mkdirSync(path.join(ws, "_prof"));
  const archivo = path.join(ws, "_prof/profesional_01.json");
  const raw = JSON.stringify({ experiencias: [fila(1, 30), fila(2, 20)] });
  fs.writeFileSync(archivo, raw);
  const run = () => spawnSync(process.execPath,
    [path.join(__dirname, "auditar_orden_experiencias.js"), ws], { encoding: "utf8" });
  assert.equal(run().status, 1);
  assert.equal(fs.readFileSync(archivo, "utf8"), raw);
  fs.writeFileSync(archivo, JSON.stringify({ experiencias: [fila(1, 20), fila(2, 30)] }));
  assert.equal(run().status, 0);
});

test("recortes PDF conservan E# y página principal aunque las fechas estén invertidas", async (t) => {
  const { PDFDocument } = require("pdf-lib");
  const JSZip = require("jszip");
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "orden-certificado-test-"));
  t.after(() => fs.rmSync(ws, { recursive: true, force: true }));
  const pdf = await PDFDocument.create();
  for (let i = 1; i <= 3; i++) pdf.addPage([200 + i, 300]);
  fs.writeFileSync(path.join(ws, "propuesta.pdf"), await pdf.save());
  fs.writeFileSync(path.join(ws, "espejo.json"), JSON.stringify({ profesionales: [{
    n_prof: 1, experiencias: [
      fila(1, 2, { paginas_pdf: [2, 1], fecha_final: "2025-01-01" }),
      fila(2, 3, { fecha_final: "2020-01-01" }),
    ],
  }] }));
  const r = spawnSync(process.execPath, [path.join(__dirname, "extraer_certificados.js"),
    path.join(ws, "espejo.json"), path.join(ws, "propuesta.pdf"), path.join(ws, "certs.zip")],
  { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  const zip = await JSZip.loadAsync(fs.readFileSync(path.join(ws, "certs.zip")));
  const e1 = await PDFDocument.load(await zip.file("P1_E1.pdf").async("nodebuffer"));
  const e2 = await PDFDocument.load(await zip.file("P1_E2.pdf").async("nodebuffer"));
  assert.deepEqual(e1.getPages().map(p => p.getWidth()), [202, 201]);
  assert.deepEqual(e2.getPages().map(p => p.getWidth()), [203]);
});
