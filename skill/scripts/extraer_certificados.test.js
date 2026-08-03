"use strict";

const assert = require("assert");
const {
  parseFolios,
  foliosTdrSospechosos,
  ampliarTdr,
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

console.log("extraer_certificados: 5 pruebas OK");
