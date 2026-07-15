"use strict";
/**
 * match_cargo.js — candado DETERMINÍSTICO para la correspondencia cargo↔bases.
 *
 * `agent-evaluador` (LLM) asigna `cargo_bases_num` a ojo y a veces lo corre (se
 * vio +1 sistemático: el Jefe de Supervisión quedó evaluado como Estructuras,
 * Estructuras como Arquitectura, etc.). No se le puede exigir determinismo al
 * modelo, así que lo atrapamos aquí: matcheamos el `cargo` LITERAL del profesional
 * contra el nombre de cada cargo del Cuadro de Personal de las bases
 * (`personal_clave[].cargo`) y ese match manda. El número del LLM queda de respaldo.
 *
 * El match es por TOKENS DISTINTIVOS del nombre del cargo (ESTRUCTURAS, ARQUITECTURA,
 * SANITARIAS, ELECTRICAS, SUPERVISION, CAMPO…), ignorando genéricos ("ESPECIALISTA",
 * "DE", "EN"). Puntúa por tokens compartidos + cobertura del cargo de bases, de modo
 * que "Especialista en Supervisión de Estructuras" gana con ESTRUCTURAS (cobertura
 * total) y no con SUPERVISION (parcial). Ante EMPATE real devuelve null (no adivina).
 */

// Genéricos que NO identifican al cargo (aparecen en casi todos). Los de ≤2 letras
// (DE, EN, LA, EL, Y…) y los puramente numéricos se filtran por longitud aparte.
const _STOP = new Set([
  "DEL", "LOS", "LAS", "ESPECIALISTA", "OBRA", "PARA", "CON", "POR",
  "PROFESIONAL", "CLAVE", "PERSONAL",
]);

function _norm(s) {
  return String(s == null ? "" : s)
    .normalize("NFKD").replace(/[̀-ͯ]/g, "")   // sin tildes
    .toUpperCase().replace(/[^A-Z0-9\s]/g, " ")
    .replace(/\s+/g, " ").trim();
}

function _toks(s) {
  return new Set(
    _norm(s).split(" ").filter(
      (t) => t.length >= 3 && !_STOP.has(t) && !/^\d+$/.test(t)));
}

/**
 * @returns {{numero:number, nombre:string, score:number, shared:number}|null}
 *   la mejor coincidencia por nombre, o null si no hay señal o hay empate real.
 */
function matchCargoBases(cargoProf, personalClave) {
  const pt = _toks(cargoProf);
  if (!pt.size || !Array.isArray(personalClave)) return null;
  let best = null, second = null;
  for (const c of personalClave) {
    if (!c || c.numero == null) continue;
    const bt = _toks(c.cargo);
    if (!bt.size) continue;
    let shared = 0;
    for (const t of pt) if (bt.has(t)) shared++;
    if (!shared) continue;
    // tokens compartidos + cobertura del cargo de bases (premia el match específico)
    const score = shared + shared / bt.size;
    const cand = { numero: c.numero, nombre: c.cargo, score, shared };
    if (!best || score > best.score) { second = best; best = cand; }
    else if (!second || score > second.score) { second = cand; }
  }
  if (!best) return null;
  if (second && Math.abs(best.score - second.score) < 1e-9) return null; // empate → no adivinar
  return best;
}

module.exports = { matchCargoBases, _norm, _toks };
