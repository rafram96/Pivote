"use strict";
/**
 * Tests de montos_postor.js (#62). Los casos son LITERALES del OCR de
 * divino_nino (job ae368cb5dafa) — cada uno nació de un error real cometido
 * mientras se construía el script, no de un escenario inventado.
 */
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  rescatarMontos, elegirMonto, candidatosDePagina, paginasDeFolio, emisorCalza, _num,
  importeExistente,
} = require("./montos_postor.js");

// ── páginas ──────────────────────────────────────────────────────────────────
test("paginasDeFolio: rango, lista y holgura por el 'aprox.' del mapa", () => {
  // el mapa dijo "49-56 aprox." y el MONTO CONTRACTUAL estaba en la 48
  assert.ok(paginasDeFolio("49-56 aprox.").includes(48));
  assert.deepStrictEqual(paginasDeFolio("78; 115", null, 0), [78, 115]);
  assert.ok(!paginasDeFolio("121-133", null, 0).includes(120));
});

// ── montos: forma y limpieza ────────────────────────────────────────────────
test("_num entiende el separador de millón con apóstrofe", () => {
  assert.strictEqual(_num("1'000,237.56"), 1000237.56);
  assert.strictEqual(_num("756,307.16"), 756307.16);
});

test("un número sin forma de monto no es candidato (la lección del '90' de #52)", () => {
  const c = candidatosDePagina("el 90% de la cuantía y un puntaje de 100", 1);
  assert.strictEqual(c.length, 0);
});

// ── la trampa central: el monto más grande NO acredita ──────────────────────
const FOLIO_77 = `
CIP N* 148043, ha laborado como CONTRATISTA y a la vez JEFE DE SUPERVISION
Monto de Contrato de Consultoria : S/23, 467.84 SOLES
Monto de Ejecucion de Obra :S/ 939,152.16 SOLES
Monto de Adicional de Obra N* 01 :S/ 63,249.46 SOLES
Monto Total de Ejecucion de Obra :S/ 1" 000, 237.56 SOLES
`;

test("elige el contrato de consultoría, no la obra supervisada ni el total", () => {
  const r = elegirMonto(candidatosDePagina(FOLIO_77, 77));
  assert.strictEqual(r.monto, 23467.84, "debe acreditar el contrato, no la obra");
});

test("los montos de obra/adicional quedan etiquetados, no elegidos", () => {
  const c = candidatosDePagina(FOLIO_77, 77);
  const obra = c.find((x) => Math.abs(x.valor - 939152.16) < 0.01);
  const adic = c.find((x) => Math.abs(x.valor - 63249.46) < 0.01);
  assert.strictEqual(obra.etiqueta, "obra_supervisada");
  assert.strictEqual(adic.etiqueta, "descartado");
});

test("el adelanto (10% del contractual) se descarta", () => {
  const txt = `
CLÁUSULA TERCERA: MONTO. CONTRACTUAL
El monto total del presente contrato asciende a S/. 211,029.00 (DOSCIENTOS ONCE MIL
Dicha retención equivale a la suma de S/.21,102.90 (Veintiún mil Ciento dos)
`;
  const r = elegirMonto(candidatosDePagina(txt, 48));
  assert.strictEqual(r.monto, 211029);
});

test("tolera la basura del OCR entre palabras: 'MONTO. CONTRACTUAL'", () => {
  const c = candidatosDePagina(
    "CLÁUSULA TERCERA: MONTO. CONTRACTUAL\nEl monto total del presente contrato asciende a S/. 211,029.00", 48);
  assert.ok(c.some((x) => x.etiqueta === "acredita"));
});

// ── candado de procedencia (el error que cometí y este test congela) ────────
test("emisorCalza distingue al emisor del contrato vecino", () => {
  assert.strictEqual(emisorCalza("MUNICIPALIDAD DISTRITAL DE HUARMAC\nDISTRITO DE HUARMACA",
    "Municipalidad Distrital de Huarmaca (Región Piura)"), true);
  assert.strictEqual(emisorCalza("MUNICIPALIDAD PROVINCIAL GRAN CHIMU\nDISTRITO DE CASCAS",
    "Municipalidad Distrital de Huarmaca (Región Piura)"), false);
  assert.strictEqual(emisorCalza("cualquier cosa", ""), null); // sin emisor no se juzga
});

test("NO toma el monto de una página cuyo emisor no calza", () => {
  // reproduce el bug: rango "49-56 aprox." de Huarmaca solapa el contrato de
  // Gran Chimú (p56). Sin candado, n=1 se llevaba 109,658.34 — ajeno y plausible.
  const paginas = {
    48: "MUNICIPALIDAD DISTRITAL DE HUARMACA\nCLÁUSULA TERCERA: MONTO. CONTRACTUAL\nEl monto total del presente contrato asciende a S/. 211,029.00",
    56: "MUNICIPALIDAD PROVINCIAL GRAN CHIMU — DISTRITO DE CASCAS\nEl monto total del presente contrato asciende a S/ 109,658.34",
  };
  const [c] = rescatarMontos(
    [{ n: 1, emisor: "Municipalidad Distrital de Huarmaca (Región Piura)", folio: "49-56 aprox.", monto: null }],
    (p) => paginas[p] || null,
  );
  assert.strictEqual(c.monto_contrato, 211029);
  assert.equal(c.monto, null); // alias legado existente no se rellena
  assert.ok(c._rescate.paginas_descartadas_por_emisor.includes(56));
});

// ── abstención: no adivinar ─────────────────────────────────────────────────
test("solo montos de obra → no elige y explica", () => {
  const r = elegirMonto(candidatosDePagina("Monto de Ejecucion de Obra: S/ 939,152.16", 1));
  assert.strictEqual(r.monto, null);
  assert.match(r.motivo, /OBRA supervisada/);
});

test("dos montos contractuales distintos → no adivina", () => {
  const r = elegirMonto(candidatosDePagina(
    "El monto total del presente contrato asciende a S/ 100,000.00\n"
    + "MONTO CONTRACTUAL: S/ 250,000.00", 1));
  assert.strictEqual(r.monto, null);
  assert.match(r.motivo, /varios montos/);
});

test("un monto que ya venía del mapa no se toca", () => {
  const [c] = rescatarMontos([{ n: 1, emisor: "X", folio: "1", monto: 999 }], () => "S/ 111,111.00");
  assert.strictEqual(c.monto, 999);
  assert.strictEqual(c._rescate, null);
});

test("sin montos en los folios citados: null con motivo, nunca inventado", () => {
  const [c] = rescatarMontos(
    [{ n: 1, emisor: "Municipalidad de Prueba", folio: "10-11", monto: null }],
    () => "MUNICIPALIDAD DE PRUEBA — acta sin cifras",
  );
  assert.strictEqual(c.monto, null);
  assert.match(c._rescate.motivo, /no se hallaron montos/);
});

test("precedencia de importe existente: contrato, ítem, legado y cero presente", () => {
  const leer = () => { throw new Error("un importe existente no consulta OCR"); };
  for (const [entrada, campo, valor] of [
    [{ monto_contrato: 10, monto_item: 20, monto: 30 }, "monto_contrato", 10],
    [{ monto_contrato: "", monto_item: 20, monto: 30 }, "monto_item", 20],
    [{ monto_item: 20, monto: 30 }, "monto_item", 20],
    [{ monto_contrato: null, monto_item: "", monto: 30 }, "monto", 30],
    [{ monto_contrato: "  ", monto_item: 0, monto: 30 }, "monto_item", 0],
    [{ monto_contrato: 0, monto_item: 20, monto: 30 }, "monto_contrato", 0],
  ]) {
    assert.deepStrictEqual(importeExistente(entrada), { campo, valor });
    const [salida] = rescatarMontos([{ n: 1, emisor: "X", folio: "1", ...entrada }], leer);
    assert.deepStrictEqual(salida, { n: 1, emisor: "X", folio: "1", ...entrada, _rescate: null });
  }
});

test("rescate no muta entrada y es idempotente", () => {
  const entrada = { n: 1, emisor: "Huarmaca", folio: "1", monto: null };
  const texto = () => "HUARMACA\nMONTO CONTRACTUAL: S/ 111,111.00";
  const [primera] = rescatarMontos([entrada], texto);
  assert.equal(entrada.monto_contrato, undefined);
  const [segunda] = rescatarMontos([primera], () => { throw new Error("no debe leer OCR"); });
  assert.equal(segunda.monto_contrato, primera.monto_contrato);
  assert.deepStrictEqual(segunda._rescate, primera._rescate);
});

test("rango exacto 129-172 no incluye el vecino 173", () => {
  assert.ok(!paginasDeFolio("129-172").includes(173));
  assert.deepStrictEqual(paginasDeFolio("129-172", null, 0).slice(-1), [172]);
});

test("rango exacto no toma vecino del mismo emisor y respeta tope", () => {
  const paginas = {
    172: "HUARMACA\nMONTO CONTRACTUAL: S/ 111,111.00",
    173: "HUARMACA\nMONTO CONTRACTUAL: S/ 222,222.00",
  };
  const [c] = rescatarMontos(
    [{ n: 1, emisor: "Huarmaca", folio: "129-172", monto: null }],
    (p) => paginas[p] || null,
  );
  assert.strictEqual(c.monto_contrato, 111111);
  assert.ok(!c._rescate.paginas_barridas.includes(173));
  assert.deepStrictEqual(paginasDeFolio("129-172", 130, 0), [129, 130]);
});

test("CLI --escribir rescata a monto_contrato sin crear alias monto", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "montos-postor-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  fs.mkdirSync(path.join(dir, "_ocr_propuesta"));
  const rosterPath = path.join(dir, "roster_bundles.json");
  fs.writeFileSync(rosterPath, JSON.stringify({ postor: { experiencia_postor: [
    { n: 1, emisor: "Huarmaca", folio: "1", monto_contrato: null },
    { n: 2, emisor: "Huarmaca", folio: "1", monto_contrato: 125000,
      monto_fuente: { pagina: 5, texto: "importe extraído" } },
  ] } }));
  fs.writeFileSync(path.join(dir, "_ocr_propuesta", "p0001.txt"),
    "HUARMACA\nMONTO CONTRACTUAL: S/ 111,111.00");
  const r = spawnSync(process.execPath,
    [path.join(__dirname, "montos_postor.js"), dir, "--escribir"],
    { encoding: "utf8" });
  assert.strictEqual(r.status, 0, r.stderr);
  assert.match(r.stdout, /rescatados 1 · sin resolver 0 · total 2/);
  const guardado = JSON.parse(fs.readFileSync(rosterPath, "utf8"));
  const [c] = guardado.postor.experiencia_postor;
  assert.strictEqual(c.monto_contrato, 111111);
  assert.ok(!Object.hasOwn(c, "monto"));
  assert.ok(c._rescate && c._rescate.elegido.pagina === 1);
  assert.strictEqual(guardado.postor.experiencia_postor[1].monto_contrato, 125000);
  assert.deepStrictEqual(guardado.postor.experiencia_postor[1].monto_fuente,
    { pagina: 5, texto: "importe extraído" });
  assert.ok(!fs.readdirSync(dir).some(nombre => nombre.includes(".tmp-")));
  const segundo = spawnSync(process.execPath,
    [path.join(__dirname, "montos_postor.js"), dir, "--escribir"], { encoding: "utf8" });
  assert.strictEqual(segundo.status, 0, segundo.stderr);
  assert.match(segundo.stdout, /rescatados 0 · sin resolver 0 · total 2/);
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(rosterPath, "utf8")), guardado);
});
