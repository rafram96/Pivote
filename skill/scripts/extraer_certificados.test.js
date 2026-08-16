"use strict";

const assert = require("assert");
const {
  parseFolios,
  parseArgs,
  foliosTdrSospechosos,
  ampliarTdr,
  validarTextoFactor,
  comprobarPaginaFactor,
} = require("./extraer_certificados");

assert.deepStrictEqual(parseFolios("4-6, 8"), [4, 5, 6, 8]);

const profesionales = Array.from({ length: 17 }, (_, i) => ({
  n_prof: i + 1,
  requisitos: { folio: i < 15 ? 34 : 38 + i },
}));
const sospechosos = foliosTdrSospechosos(profesionales);
assert(sospechosos.has("34"), "15/17 cargos con folio 34 deben ser sospechosos");

assert.deepStrictEqual(ampliarTdr([34], "34-38", 100), [34, 35, 36, 37, 38]);
assert.deepStrictEqual(ampliarTdr([34], null, 36), [34, 35, 36]);

const sanos = [
  { requisitos: { folio: 10 } },
  { requisitos: { folio: 11 } },
  { requisitos: { folio: 12 } },
  { requisitos: { folio: 13 } },
];
assert.strictEqual(foliosTdrSospechosos(sanos).size, 0);

assert.deepStrictEqual(
  parseArgs(["e.json", "p.pdf", "s.zip", "comun.pdf"]),
  { espejoPath: "e.json", propuestaPath: "p.pdf", zipPath: "s.zip", basesPath: "comun.pdf", tdrPath: "comun.pdf" },
);
assert.deepStrictEqual(
  parseArgs(["e.json", "p.pdf", "s.zip", "--bases", "bases.pdf", "--tdr", "tdr.pdf"]),
  { espejoPath: "e.json", propuestaPath: "p.pdf", zipPath: "s.zip", basesPath: "bases.pdf", tdrPath: "tdr.pdf" },
);

assert.strictEqual(validarTextoFactor("4. FACTORES DE EVALUACIÓN — PUNTAJE 100"), "verificado");
assert.strictEqual(validarTextoFactor("Norma técnica sanitaria y especificaciones generales"), "incorrecto");
assert.strictEqual(validarTextoFactor(""), "no_verificado");

assert.deepStrictEqual(
  comprobarPaginaFactor("bases.pdf", [28, 29], () => ({ status: 0, stdout: "FACTORES DE EVALUACIÓN PUNTAJE" })),
  { estado: "verificado", detalle: "texto del baremo reconocido" },
);
assert.strictEqual(
  comprobarPaginaFactor("tdr.pdf", [28], () => ({ status: 0, stdout: "Normas técnicas aplicables al hospital" })).estado,
  "incorrecto",
);

console.log("extraer_certificados: 12 pruebas OK");
