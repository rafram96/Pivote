"use strict";
/* Test offline del candado de cargos. Correr: node scripts/match_cargo.test.js
 *
 * Caso REAL divino-niño (Consorcio Ingeniería Group, concurso 002-2026-GRC).
 * El MISMO postor, dos corridas de la skill:
 *   - corrida 9-jul  → cargo_bases_num = 1,2,3,4,5  (correcto)
 *   - corrida 14-jul → cargo_bases_num = 2,3,4,5,5  (CORRIDO +1, la queja del cliente)
 * El LLM (agent-evaluador) es no-determinístico. El candado por nombre debe dar
 * SIEMPRE 1,2,3,4,5 — arregla la corrida mala y coincide con la buena.
 */
const assert = require("assert");
const { matchCargoBases, _toks } = require("./match_cargo");

let ok = 0;
const eq = (a, b, msg) => { assert.strictEqual(a, b, msg); ok++; };

// Cuadro de Personal REAL de divino (reconstruido de la corrida buena, 9-jul).
const DIVINO_PC = [
  { numero: 1, cargo: "JEFE DE SUPERVISIÓN" },
  { numero: 2, cargo: "ESPECIALISTA EN ESTRUCTURAS" },
  { numero: 3, cargo: "ESPECIALISTA EN ARQUITECTURA" },
  { numero: 4, cargo: "ESPECIALISTA EN INSTALACIONES SANITARIAS" },
  { numero: 5, cargo: "ESPECIALISTA EN INSTALACIONES ELÉCTRICAS" },
];

// Los `cargo` declarados de los 5 profesionales, con el nº que el LLM les puso en
// CADA corrida (de los espejos reales), y el nº CORRECTO esperado.
const PROFES = [
  { cargo: "JEFE DE SUPERVISION",                       llm14: 2, llm09: 1, correcto: 1 },
  { cargo: "ESPECIALISTA EN ESTRUCTURAS",               llm14: 3, llm09: 2, correcto: 2 },
  { cargo: "ESPECIALISTA EN ARQUITECTURA",              llm14: 4, llm09: 3, correcto: 3 },
  { cargo: "ESPECIALISTA EN INSTALACIONES SANITARIAS",  llm14: 5, llm09: 4, correcto: 4 },
  { cargo: "ESPECIALISTA EN INSTALACIONES ELECTRICAS",  llm14: 5, llm09: 5, correcto: 5 },
];

console.log("  cargo declarado                       | LLM 14-jul | matcher | correcto");
console.log("  " + "-".repeat(74));
for (const p of PROFES) {
  const m = matchCargoBases(p.cargo, DIVINO_PC);
  assert.ok(m, `sin match para "${p.cargo}"`);
  const marca = m.numero === p.correcto ? "✓" : "✗";
  const arreglo = p.llm14 !== p.correcto ? `  (arregla +1: ${p.llm14}→${m.numero})` : "";
  console.log(`  ${p.cargo.padEnd(37)} |     ${p.llm14}      |    ${m.numero}    |    ${p.correcto}  ${marca}${arreglo}`);
  eq(m.numero, p.correcto, `divino: "${p.cargo}" → esperaba N°${p.correcto}, dio N°${m.numero}`);
}

// el matcher coincide con la corrida BUENA (9-jul) y ARREGLA la mala (14-jul)
for (const p of PROFES) {
  eq(matchCargoBases(p.cargo, DIVINO_PC).numero, p.llm09,
    `debe coincidir con la corrida buena para "${p.cargo}"`);
}

// ── casos borde ─────────────────────────────────────────────────────────────
eq(matchCargoBases("", DIVINO_PC), null, "cargo vacío → null");
eq(matchCargoBases("Coordinador de Vuelos Espaciales", DIVINO_PC), null, "sin token compartido → null");
// variante ruidosa: el token distintivo (ESTRUCTURAS) gana sobre SUPERVISIÓN
eq(matchCargoBases("Ing. Especialista en Supervisión de Estructuras N° 1", DIVINO_PC).numero, 2,
  "variante ruidosa → ESTRUCTURAS (N°2), no SUPERVISIÓN");
// empate real (dos cargos idénticos) → no adivinar
eq(matchCargoBases("ESPECIALISTA EN ESTRUCTURAS",
  [{ numero: 1, cargo: "ESPECIALISTA EN ESTRUCTURAS" },
   { numero: 2, cargo: "ESPECIALISTA EN ESTRUCTURAS" }]), null, "empate real → null");
assert.ok(_toks("Especialista en Estructuras").has("ESTRUCTURAS"), "token distintivo"); ok++;
assert.ok(!_toks("Especialista en Estructuras").has("ESPECIALISTA"), "genérico filtrado"); ok++;

console.log(`\n✓ ${ok} asserts OK — el candado da 1,2,3,4,5 en AMBAS corridas (arregla el +1)`);
