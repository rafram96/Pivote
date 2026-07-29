"use strict";
/**
 * Tests de montos_postor.js (#62). Los casos son LITERALES del OCR de
 * divino_nino (job ae368cb5dafa) — cada uno nació de un error real cometido
 * mientras se construía el script, no de un escenario inventado.
 */
const test = require("node:test");
const assert = require("node:assert");
const {
  rescatarMontos, elegirMonto, candidatosDePagina, paginasDeFolio, emisorCalza, _num,
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
  assert.strictEqual(c.monto, 211029);
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
