#!/usr/bin/env node
"use strict";
/**
 * consolidar_espejo.js — Paso 4 de la skill, DETERMINÍSTICO.
 *
 * Une las salidas de los subagentes en el JSON espejo v1.2.0, normalizando los
 * alias/typos que producen (cada subagente LLM diverge) y dejando `_backend` en
 * null. Reemplaza el "el orquestador consolida a mano" — que es inviable y
 * propenso a errores en propuestas grandes (miles de líneas).
 *
 * Uso:
 *   node scripts/consolidar_espejo.js <carpeta_analisis>
 *   # luego: node scripts/validar_espejo.js <carpeta>/espejo.json
 *
 * Archivos que espera en <carpeta_analisis> (los escriben los pasos previos):
 *   bases.json            agent-bases       → { metadata_concurso, personal_clave[] }
 *   roster_bundles.json   agent-propuesta-mapa → { roster[], postor{...}, postor_nivel? }
 *                          donde postor = { detalle, formularios[], oferta_economica,
 *                          experiencia_postor[], consorciados[], isos_certificaciones[] }
 *   evaluacion.json       agent-evaluador   → { profesionales_eval{}, experiencias_eval{},
 *                          postor_eval{}, resumen_evaluacion{}, observaciones_claude[] }
 *   _prof/profesional_NN.json  agent-propuesta-profesional ×N (hechos crudos)
 *
 * El nº de profesionales se auto-detecta de _prof/ (no está hardcodeado).
 * El bloque postor se LEE del mapa (no se hardcodea); si falta algo, queda vacío
 * + una observación para que el orquestador lo complete.
 *
 * ── Candado 1:1 evaluador ↔ profesionales (#45-L3) ──────────────────────────
 * La salida del evaluador se leía con `|| {}` / `|| []`: si no cubría a los N
 * profesionales, el espejo salía con las columnas de juicio en null y VALIDABA
 * perfecto contra el schema — un falso "todo bien". Pasó dos veces el 26-jul (una
 * corrida con los veredictos corridos +1 y otra sin nada). `auditarEvaluacion`
 * NO toca los datos: solo obliga a que el hueco se vea (avisos `critical` en
 * `observaciones_claude`, mismo patrón que `cargo_corregido`).
 *
 * El candado mira exactamente lo que el pegado usa, no un proxy:
 *   · la LLAVE DE JOIN (`eeByN[x.n]`) → coteja el CONJUNTO de `n`, no el conteo;
 *     un evaluador que entrega la cantidad exacta con los `n` cambiados deja
 *     TODO en null y el conteo cuadra igual;
 *   · el VEREDICTO, no la clave → `{n_prof:1, cumple:null}` produce el mismo
 *     espejo que no mandar nada, así que cuenta como ausente.
 * Y el consolidador NO puede terminar diciendo «OK» si hay un crítico: el gate
 * está en `consolidar()`/`reportar()` (última línea + exit code 1), porque un
 * candado que nadie consume no es un candado.
 */
const fs = require("fs");
const path = require("path");
const { matchCargoBases, _norm, _toks } = require("./match_cargo");

const rd = (p) => JSON.parse(fs.readFileSync(p, "utf-8"));
const rdOpt = (p, def) => (fs.existsSync(p) ? rd(p) : def);

// ── helpers de normalización (el oro: tolerantes a la deriva de los subagentes) ──
const pick = (...vs) => { for (const v of vs) if (v !== undefined && v !== null && v !== "") return v; return null; };
const numify = (v) => {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const m = String(v).replace(/[^\d.,-]/g, "").replace(/,/g, "");
  const n = parseFloat(m);
  return Number.isFinite(n) ? n : null;
};
const intsFrom = (v) => {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map((x) => parseInt(x, 10)).filter(Number.isFinite);
  return (String(v).match(/\d+/g) || []).map((x) => parseInt(x, 10)).filter(Number.isFinite);
};
const declStr = (v) => {
  if (v == null) return null;
  if (typeof v === "number" || typeof v === "string") return v;
  if (typeof v === "object") {
    const t = pick(v.texto_literal, v.texto), e = pick(v.equivalencia_literal, v.equivalencia);
    if (t || e) return [t, e].filter(Boolean).join(" — ");
    return JSON.stringify(v);
  }
  return String(v);
};
const fechaOk = (v) => {
  if (v == null) return null;
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s) || /^\d{4}-\d{2}(\D.*)?$/.test(s) || s.startsWith("POR VERIFICAR")) return s;
  return null; // formato desconocido → null (no rompe el schema .strict())
};
// SÍ/NO desde booleano o texto (incluye_covid, traslape, cert_antes_culminar…)
const siNo = (jv, ev_) => pick(jv, (typeof ev_ === "boolean" ? (ev_ ? "SÍ" : "NO") : ev_));
const BACKEND = () => ({
  fecha_creacion_emisor: null, alerta_antiguedad_emisor: null,
  firmante_facultado_sunat: null, vinculacion_postor_emisor: null,
  codigo_ciu: null, codigo_infoobras: null,
  paralizaciones: null, alerta_experiencia_antigua: null,
});

// ════════════════════════════════════════════════════════════════════════════
// Candado 1:1 evaluador ↔ profesionales (#45-L3)
// ════════════════════════════════════════════════════════════════════════════
const obs = (severidad, tipo, mensaje, referencia) => ({ severidad, tipo, mensaje, referencia });

// Palabras de ROL que aparecen en casi cualquier veredicto y NO identifican una
// especialidad; se excluyen del cotejo veredicto↔cargo para no gritar por ruido.
const _ROL_GENERICO = new Set([
  "JEFE", "SUPERVISION", "SUPERVISOR", "RESIDENTE", "INSPECTOR", "COORDINADOR",
  "ASISTENTE", "ADJUNTO", "INGENIERO", "INGENIERA", "TECNICO", "GENERAL",
  "OBRAS", "PROYECTO", "PROYECTOS", "EQUIPO", "CONTRATO", "CONTRATOS",
]);

/**
 * ¿Este valor es un juicio de verdad, o solo la cáscara?
 * `{}`, `[]`, `""` y `null` producen EXACTAMENTE el mismo espejo que no mandar
 * nada (columna en null), así que para el candado valen lo mismo: ausencia.
 */
function _conValor(v) {
  if (v == null) return false;
  if (typeof v === "string") return v.trim() !== "";
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return true; // números, booleanos
}

// Campos de juicio de una experiencia: si NINGUNO trae valor, la fila sale con
// todas las columnas de la Parte 4 en null — el mismo hueco que no evaluarla.
const _JUICIO_EXP = [
  "dias", "meses", "anios", "cargo_bases_valido", "tipo_obra_valido",
  "cargo_valido_emitir", "anterior_colegiatura", "cert_antes_culminar",
  "incluye_covid", "traslape", "funciones_similares", "observaciones",
];

// Un veredicto sano cita números que NO son sus constancias: lo DECLARADO en el
// Anexo 16 y lo EXIGIDO por las bases ("las bases exigen 3 constancias y solo
// presenta 2"). Gritar por esas redacciones entrena al evaluador a ignorar los
// críticos — que es justo lo que inutiliza el candado.
const _CITA_AJENA = /(?:DECLARA\w*|EXIG\w+|REQUIER\w+|SOLICIT\w+|PID\w+|MINIM\w+|MENOS|ANEXO|BASES|TDR|CUADRO|RESUMEN)\s+(?:\w+\s+){0,3}$/;

/** Claves numéricas contiguas 0..K-1 → el evaluador indexó desde 0 (n_prof empieza en 1). */
function _esBaseCero(mapa) {
  const ks = Object.keys(mapa);
  if (!ks.length || !ks.every((k) => /^\d+$/.test(k))) return false;
  const ns = ks.map(Number).sort((a, b) => a - b);
  return ns[0] === 0 && ns.every((n, i) => n === i);
}
const _correrUno = (mapa) => {
  const out = {};
  for (const k of Object.keys(mapa)) out[String(Number(k) + 1)] = mapa[k];
  return out;
};

/**
 * `profesionales_eval` / `experiencias_eval` deberían ser OBJETOS indexados por
 * `n_prof` ("1", "2", …). Cuando el evaluador los devuelve como ARRAY, indexar por
 * n_prof sobre un array es un +1 silencioso (`arr["1"]` es el SEGUNDO elemento):
 * cada profesional recibe el veredicto del siguiente y el último se queda sin nada
 * — exactamente el cuadro del 26-jul. Aquí se normaliza a mapa SIN descartar nada
 * y se deja constancia de la forma en que llegó.
 *
 * @param {object} ev salida cruda de agent-evaluador
 * @returns {{PE:object, EE:object, avisos:Array}}
 */
function normalizarEval(ev) {
  const avisos = [];
  const E = ev || {};

  // ── profesionales_eval: un objeto por profesional ──
  let PE = {};
  const rawPE = E.profesionales_eval;
  if (Array.isArray(rawPE)) {
    if (rawPE.length && rawPE.every((x) => x && !Array.isArray(x) && x.n_prof != null)) {
      for (const x of rawPE) PE[String(x.n_prof)] = x;
      avisos.push(obs("warning", "evaluacion_forma_array",
        "agent-evaluador devolvió profesionales_eval como ARRAY; se reindexó por el n_prof de cada elemento (nada se perdió). "
        + "El contrato pide un objeto {\"1\": {...}, \"2\": {...}}.",
        "evaluacion.json → profesionales_eval"));
    } else {
      rawPE.forEach((x, k) => { PE[String(k + 1)] = x; });
      avisos.push(obs("critical", "evaluacion_forma_array",
        `agent-evaluador devolvió profesionales_eval como ARRAY de ${rawPE.length} elemento(s) SIN n_prof: se pareó por POSICIÓN (1..N). `
        + "Si el evaluador se saltó a alguien, todos los que siguen quedan con el veredicto de otro (corrimiento). "
        + "Verifica veredicto por veredicto antes de subir.",
        "evaluacion.json → profesionales_eval"));
    }
  } else if (rawPE && typeof rawPE === "object") {
    PE = rawPE;
  } else if (rawPE != null) {
    avisos.push(obs("critical", "evaluacion_forma_desconocida",
      `profesionales_eval llegó como ${typeof rawPE}, no como objeto indexado por n_prof: se ignoró y NINGÚN profesional queda evaluado.`,
      "evaluacion.json → profesionales_eval"));
  }
  if (_esBaseCero(PE)) {
    PE = _correrUno(PE);
    avisos.push(obs("critical", "evaluacion_indice_base_cero",
      "profesionales_eval venía indexado desde 0 (\"0\",\"1\",…) y n_prof empieza en 1: se corrió +1 para parearlo. "
      + "Es una corrección determinística sobre una salida ambigua — verifica que cada veredicto sea del profesional que dice.",
      "evaluacion.json → profesionales_eval"));
  }

  // ── experiencias_eval: una LISTA por profesional ──
  let EE = {};
  let rawEE = E.experiencias_eval;

  // Fallback: si no viene en top-level, buscar si venía anidado dentro de profesionales_eval
  if ((!rawEE || (typeof rawEE === "object" && !Array.isArray(rawEE) && Object.keys(rawEE).length === 0)) && E.profesionales_eval) {
    const fallbackEE = {};
    let count = 0;
    const peSource = E.profesionales_eval;
    const items = Array.isArray(peSource)
      ? peSource
      : Object.entries(peSource).map(([k, v]) => ({ ...(v || {}), _key: k }));

    for (const item of items) {
      if (!item || typeof item !== "object") continue;
      const nProf = item.n_prof != null ? item.n_prof : (item.n != null ? item.n : item._key);
      if (Array.isArray(item.experiencias_eval) && item.experiencias_eval.length > 0 && nProf != null) {
        fallbackEE[String(nProf)] = item.experiencias_eval;
        count += item.experiencias_eval.length;
      }
    }

    if (count > 0) {
      rawEE = fallbackEE;
      avisos.push(obs("warning", "evaluacion_experiencias_anidadas",
        `agent-evaluador anidó experiencias_eval dentro de profesionales_eval (${count} experiencias): se extrajo automáticamente al nivel superior.`,
        "evaluacion.json → experiencias_eval"));
    }
  }

  if (Array.isArray(rawEE)) {
    if (rawEE.length && rawEE.every((x) => Array.isArray(x))) {
      rawEE.forEach((x, k) => { EE[String(k + 1)] = x; });
      avisos.push(obs("critical", "evaluacion_forma_array",
        `experiencias_eval llegó como ARRAY de ${rawEE.length} lista(s): se pareó por POSICIÓN (1..N). `
        + "Si falta la lista de algún profesional, las de abajo se le adjudican a quien no es.",
        "evaluacion.json → experiencias_eval"));
    } else if (rawEE.length && rawEE.every((x) => x && !Array.isArray(x) && x.n_prof != null)) {
      for (const x of rawEE) (EE[String(x.n_prof)] = EE[String(x.n_prof)] || []).push(x);
      avisos.push(obs("warning", "evaluacion_forma_array",
        "agent-evaluador devolvió experiencias_eval como ARRAY plano; se agrupó por el n_prof de cada elemento (nada se perdió).",
        "evaluacion.json → experiencias_eval"));
    } else if (rawEE.length) {
      rawEE.forEach((x, k) => { EE[String(k + 1)] = Array.isArray(x) ? x : [x]; });
      avisos.push(obs("critical", "evaluacion_forma_array",
        "experiencias_eval llegó como ARRAY de forma mixta: se pareó por POSICIÓN (1..N). Verifícalo fila por fila.",
        "evaluacion.json → experiencias_eval"));
    }
  } else if (rawEE && typeof rawEE === "object") {
    EE = rawEE;
  } else if (rawEE != null) {
    avisos.push(obs("critical", "evaluacion_forma_desconocida",
      `experiencias_eval llegó como ${typeof rawEE}, no como objeto indexado por n_prof: ninguna fila queda evaluada.`,
      "evaluacion.json → experiencias_eval"));
  }
  if (_esBaseCero(EE)) {
    EE = _correrUno(EE);
    avisos.push(obs("critical", "evaluacion_indice_base_cero",
      "experiencias_eval venía indexado desde 0 y n_prof empieza en 1: se corrió +1 para parearlo. Verifica fila por fila.",
      "evaluacion.json → experiencias_eval"));
  }

  return { PE, EE, avisos };
}

/**
 * Verifica que la evaluación cubra 1:1 a los profesionales y sus experiencias.
 * NO corrige ni borra nada: devuelve los avisos que van a `observaciones_claude`.
 *
 * @param {object} ev salida cruda de agent-evaluador
 * @param {Array<{n_prof:number, cargo?:string, cargo_bases_nombre?:string,
 *                n_experiencias:number, ns_experiencias?:Array<number>}>} profs
 *        hechos crudos (agent-propuesta-profesional): quién existe, cuántas
 *        experiencias declaró cada uno y —lo importante— CON QUÉ `n`, que es la
 *        llave con la que `main` pega los juicios (`eeByN[x.n]`). Son la verdad
 *        contra la que se coteja. Si `ns_experiencias` no viene, se asume la
 *        numeración contigua 1..n_experiencias.
 * @returns {Array<{severidad:string, tipo:string, mensaje:string, referencia:string}>}
 */
function auditarEvaluacion(ev, profs) {
  const lista = Array.isArray(profs) ? profs.filter((p) => p && p.n_prof != null) : [];
  const { PE, EE, avisos } = normalizarEval(ev);
  if (!lista.length) return avisos;

  const nums = lista.map((p) => Number(p.n_prof));
  const ultimo = nums[nums.length - 1];
  // Presencia ≠ veredicto. `{}` y `{n_prof:1, cumple:null}` producen el MISMO
  // espejo que no mandar nada (cumple/años adicionales en null), así que los dos
  // cuentan como ausente. Medir `Object.keys().length` era mirar la cáscara: el
  // corrimiento del 26-jul dejó objetos presentes con el contenido de otro.
  const conEntrada = (i) => {
    const p = PE[String(i)];
    return !!p && typeof p === "object" && !Array.isArray(p) && Object.keys(p).length > 0;
  };
  const evaluado = (i) => conEntrada(i) && _conValor((PE[String(i)] || {}).cumple);
  const faltan = nums.filter((i) => !evaluado(i));
  // Los que llegaron pero sin veredicto: el operador tiene que saber que el
  // hueco no es "se olvidó de mandarlo", es "lo mandó vacío".
  const vacios = faltan.filter((i) => conEntrada(i));
  const detalleVacios = vacios.length
    ? ` De esos, n_prof ${vacios.join(", ")} SÍ llegó(aron) en profesionales_eval pero con \`cumple\` vacío: `
      + "en el espejo se ve exactamente igual que si no vinieran."
    : "";

  // ── 1 · cobertura de profesionales_eval ──
  if (faltan.length === nums.length) {
    avisos.push(obs("critical", "evaluacion_ausente",
      `agent-evaluador no entregó NINGÚN veredicto utilizable: ninguno de los ${nums.length} profesionales tiene \`cumple\`.`
      + detalleVacios
      + " El espejo sale con TODAS las columnas de juicio en null y aun así valida contra el schema. "
      + "No lo subas: vuelve a correr agent-evaluador.",
      "evaluacion.json → profesionales_eval"));
  } else if (faltan.length === 1 && faltan[0] === ultimo) {
    avisos.push(obs("critical", "evaluacion_corrida",
      `falta EXACTAMENTE el veredicto del ÚLTIMO profesional (n_prof ${ultimo}) y están los de todos los demás: `
      + "es la firma del CORRIMIENTO — cada profesional habría recibido el veredicto del SIGUIENTE y el último se quedó sin nada. "
      + "Coteja veredicto por veredicto contra el nombre y el cargo antes de subir; si está corrido, vuelve a correr agent-evaluador."
      + detalleVacios,
      `evaluacion.json → profesionales_eval[${ultimo}]`));
  } else if (faltan.length) {
    avisos.push(obs("critical", "evaluacion_incompleta",
      `profesionales_eval no cubre a los ${nums.length} profesionales: sin veredicto n_prof ${faltan.join(", ")}. `
      + "Esas hojas salen sin veredicto (cumple/años adicionales en null) y el espejo valida igual."
      + detalleVacios,
      "evaluacion.json → profesionales_eval"));
  }
  const sobran = Object.keys(PE).filter((k) => !nums.includes(Number(k)));
  if (sobran.length) {
    avisos.push(obs("critical", "evaluacion_sobrante",
      `profesionales_eval trae veredicto(s) para ${sobran.map((k) => `"${k}"`).join(", ")}, que no corresponde(n) a ningún profesional `
      + `(los que existen son ${nums.join(", ")}): la evaluación no está pareada con el roster.`,
      "evaluacion.json → profesionales_eval"));
  }

  // ── 2 · cobertura de experiencias_eval (una entrada por experiencia declarada) ──
  for (const p of lista) {
    const i = Number(p.n_prof);
    const quien = `profesional ${i}${p.cargo ? ` (${p.cargo})` : ""}`;
    const decl = Number(p.n_experiencias) || 0;
    const ee = EE[String(i)];
    if (!Array.isArray(ee)) {
      if (decl > 0) {
        avisos.push(obs("critical", "evaluacion_experiencias_ausentes",
          `${quien}: experiencias_eval no trae NADA y el profesional declaró ${decl} experiencia(s). `
          + "Sus filas salen sin días/meses/años, sin «¿cargo de las bases?» y sin «¿tipo de obra?» — todas en null.",
          `evaluacion.json → experiencias_eval[${i}]`));
      }
      continue;
    }
    if (ee.length !== decl) {
      avisos.push(obs("critical", "evaluacion_experiencias_descuadre",
        `${quien}: el evaluador entregó ${ee.length} experiencia(s) evaluada(s) y agent-propuesta-profesional declaró ${decl}. `
        + `No es 1:1 — ${ee.length < decl ? "hay filas que salen sin juicio" : "sobran juicios sin fila"}.`,
        `evaluacion.json → experiencias_eval[${i}]`));
    }

    // ── la LLAVE DE JOIN, que es lo único que decide si un juicio llega a su fila ──
    // `main` pega con `eeByN[x.n]`: un `n` que no existe entre las filas crudas no
    // le llega a nadie, y una fila cuyo `n` nadie cita sale con TODAS sus columnas
    // de juicio en null. El conteo puede cuadrar perfecto en ambos casos.
    const esperados = (Array.isArray(p.ns_experiencias) && p.ns_experiencias.length)
      ? [...new Set(p.ns_experiencias.map(Number).filter(Number.isFinite))]
      : Array.from({ length: decl }, (_, k) => k + 1);

    const sinN = ee.filter((x) => !x || x.n == null || !Number.isFinite(Number(x.n))).length;
    if (sinN) {
      avisos.push(obs("critical", "evaluacion_n_ausente",
        `${quien}: ${sinN} de ${ee.length} entrada(s) de experiencias_eval llegan SIN el campo \`n\`. `
        + "El consolidador pega cada juicio a su fila POR ESE `n`: sin él, todas colapsan en la misma clave "
        + "y ninguna fila recibe juicio (días/meses/años, «¿cargo de las bases?» y «¿tipo de obra?» salen en null), "
        + "aunque el conteo cuadre.",
        `evaluacion.json → experiencias_eval[${i}]`));
    }

    const ns = ee.map((x) => (x && x.n != null ? Number(x.n) : NaN)).filter(Number.isFinite);
    const inexistentes = [...new Set(ns)].filter((n) => !esperados.includes(n));
    if (inexistentes.length) {
      avisos.push(obs("critical", "evaluacion_n_desalineado",
        `${quien}: experiencias_eval cita n=${inexistentes.join(", ")} y las filas de este profesional son n=${esperados.join(", ")}. `
        + "Esos juicios no le llegan a ninguna fila (síntoma de corrimiento o de renumeración).",
        `evaluacion.json → experiencias_eval[${i}]`));
    }
    const sinJuicio = esperados.filter((n) => !ns.includes(n));
    if (sinJuicio.length) {
      avisos.push(obs("critical", "evaluacion_n_sin_juicio",
        `${quien}: ninguna entrada de experiencias_eval cita n=${sinJuicio.join(", ")}, y esa(s) fila(s) SÍ existe(n) en la propuesta. `
        + "Salen con días/meses/años, «¿cargo de las bases?» y «¿tipo de obra?» en null, y el espejo valida igual.",
        `evaluacion.json → experiencias_eval[${i}]`));
    }
    const dup = [...new Set(ns.filter((n, k) => ns.indexOf(n) !== k))];
    if (dup.length) {
      avisos.push(obs("critical", "evaluacion_n_duplicado",
        `${quien}: experiencias_eval repite n=${dup.join(", ")}. Al indexar por n solo sobrevive el ÚLTIMO, `
        + "así que hay filas que se quedan con el juicio de otra.",
        `evaluacion.json → experiencias_eval[${i}]`));
    }

    // ── entradas presentes pero sin NINGÚN campo de juicio: mismo hueco ──
    const huecas = ee
      .filter((x) => x && typeof x === "object" && !_JUICIO_EXP.some((c) => _conValor(x[c])))
      .map((x) => (x.n != null ? x.n : "?"));
    if (huecas.length) {
      avisos.push(obs("critical", "evaluacion_experiencias_vacias",
        `${quien}: la(s) entrada(s) n=${huecas.join(", ")} de experiencias_eval no traen NINGÚN campo de juicio con valor. `
        + "Están presentes y cuentan para el conteo, pero dejan la fila igual que si no vinieran.",
        `evaluacion.json → experiencias_eval[${i}]`));
    }
  }

  // ── 3 · coherencia veredicto ↔ profesional ──
  // Tokens de especialidad de cada cargo (los genéricos de rol no cuentan).
  const espec = new Map();
  for (const p of lista) {
    const t = _toks([p.cargo, p.cargo_bases_nombre].filter(Boolean).join(" "));
    espec.set(Number(p.n_prof), new Set([...t].filter((x) => !_ROL_GENERICO.has(x))));
  }
  for (const p of lista) {
    const i = Number(p.n_prof);
    const pe = PE[String(i)];
    if (!pe || typeof pe !== "object") continue;
    const veredicto = typeof pe.cumple === "string" ? pe.cumple : null;
    if (!veredicto) continue;
    const decl = Number(p.n_experiencias) || 0;
    const quien = `profesional ${i}${p.cargo ? ` ("${p.cargo}")` : ""}`;

    // (a) ¿cita un nº de constancias que no existe?
    // Solo cuentan los números presentados como constancias SUYAS: los que vienen
    // detrás de «declara / exige / mínimo / Anexo / bases» son citas del requisito
    // o del cuadro resumen — redacciones legítimas y frecuentes ("el Anexo 16
    // declara 7 experiencias; solo 3 constancias están en la propuesta").
    const txt = _norm(veredicto);
    const citados = [...new Set(
      [...txt.matchAll(/(\d+)\s+(?:CONSTANCIAS?|CERTIFICADOS?|EXPERIENCIAS?|PERIODOS?)/g)]
        .filter((m) => !_CITA_AJENA.test(txt.slice(Math.max(0, m.index - 45), m.index)))
        .map((m) => parseInt(m[1], 10)).filter(Number.isFinite))];
    const mayores = citados.filter((n) => n > decl);
    if (mayores.length) {
      avisos.push(obs("critical", "veredicto_incoherente",
        `${quien}: su veredicto cita ${mayores.join(", ")} constancia(s)/periodo(s) y solo tiene ${decl} declarada(s). `
        + "No puede estar hablando de este profesional: revísalo antes de subir.",
        `evaluacion.json → profesionales_eval[${i}].cumple`));
    } else if (citados.length && !citados.includes(decl)) {
      avisos.push(obs("warning", "veredicto_incoherente",
        `${quien}: su veredicto cita ${citados.join(", ")} constancia(s)/periodo(s) y el profesional declaró ${decl}. `
        + "Puede ser un subconjunto legítimo (las que acreditan), pero verifica que el veredicto sea el suyo.",
        `evaluacion.json → profesionales_eval[${i}].cumple`));
    }

    // (b) ¿habla de una especialidad que es de OTRO profesional y nunca de la suya?
    const propias = espec.get(i) || new Set();
    const vt = _toks(veredicto);
    if (propias.size && ![...propias].some((t) => vt.has(t))) {
      const ajenas = [];
      for (const q of lista) {
        const j = Number(q.n_prof);
        if (j === i) continue;
        for (const t of (espec.get(j) || [])) {
          if (!propias.has(t) && vt.has(t) && !ajenas.some((a) => a.t === t)) ajenas.push({ t, j });
        }
      }
      if (ajenas.length) {
        avisos.push(obs("critical", "veredicto_ajeno",
          `${quien}: su veredicto no nombra su especialidad (${[...propias].join(", ")}) y sí menciona `
          + `${ajenas.map((a) => `${a.t} (del profesional ${a.j})`).join(", ")} — parece el veredicto de OTRO profesional. `
          + "Es la firma del corrimiento: cotéjalo antes de subir.",
          `evaluacion.json → profesionales_eval[${i}].cumple`));
      }
    }
  }

  return avisos;
}

// ════════════════════════════════════════════════════════════════════════════

function requisitosDe(bases, cargoNum) {
  const c = (bases.personal_clave || []).find((x) => x.numero === cargoNum);
  if (!c) return null;
  return {
    cargos_validos: (c.cargos_similares_validos || []).join("; "),
    tipo_experiencia_valida: `Experiencia mínima: ${c.tiempo_minimo_experiencia}. Profesión aceptada: ${(c.profesiones_aceptadas || []).join(" / ")}.`,
    tipo_obra_valida: c.tipos_obra_validos || null,
    folio: pick(c.folio, c.folio_requisito, c.folio_tdr),   // folio en las BASES → recorte TDR (mejora A)
  };
}

function crossChecks(raw) {
  const out = [];
  for (const cc of (raw || [])) {
    const v = cc.valor || cc;
    const ex = pick(v.extraidas, cc.extraidas), de = pick(v.declaradas, cc.declaradas);
    const cu = (v.cuadra != null ? v.cuadra : cc.cuadra), it = pick(v.intentos, cc.intentos);
    out.push({
      label: pick(cc.label, "Cross-check vs cuadro resumen del Anexo 16:"),
      valor: `extraídas=${ex} · declaradas=${de} · cuadra=${cu === true ? "sí" : cu === false ? "no" : cu} · intentos=${it}`,
    });
  }
  return out;
}

/**
 * Imprime el resultado. Reglas del gate (#45-L3):
 *   · los CRÍTICOS van PRIMERO — un párrafo debajo de un "OK" no lo lee nadie;
 *   · si hay críticos la ÚLTIMA línea NO dice «OK», dice INCOMPLETO, porque el
 *     operador (y el orquestador, que es un LLM leyendo logs) se queda con la
 *     primera y la última;
 *   · `validar_espejo.js` va a decir «OK» igual: hay que decirlo aquí para que
 *     ese OK no se lea como confirmación.
 */
function reportar(outPath, espejo, avisos) {
  const criticos = avisos.filter((a) => a.severidad === "critical");
  const nexp = espejo.profesionales.reduce((s, p) => s + p.experiencias.length, 0);
  const cuerpo = `${espejo.profesionales.length} profesionales · ${nexp} experiencias `
    + `· ${espejo.resumen_evaluacion.factores.length} factores`;

  if (criticos.length) {
    console.log(`⛔ ${criticos.length} aviso(s) CRÍTICO(s) — la evaluación NO está completa:`);
    for (const c of criticos) console.log(`   · [${c.tipo}] ${c.mensaje}`);
    console.log("");
  }
  const otros = avisos.length - criticos.length;
  if (otros) console.log(`⚠ ${otros} aviso(s) más — revisa observaciones_claude.`);

  if (criticos.length) {
    console.log(`⛔ INCOMPLETO · espejo escrito en ${outPath} · ${cuerpo}`);
    console.log("   NO lo subas al backend ni sigas al Paso 5: el espejo VALIDA igual contra el schema");
    console.log("   (validar_espejo.js dirá «OK» y eso no significa que la evaluación esté completa).");
    console.log("   Vuelve a correr agent-evaluador cubriendo lo que falta y consolida de nuevo.");
  } else {
    console.log(`OK · espejo escrito en ${outPath} · ${cuerpo}`);
  }
  return criticos;
}

/**
 * Consolida y devuelve TAMBIÉN el veredicto del candado — que es lo que el CLI
 * convierte en exit code. `main` queda como envoltorio para quien solo quiere el
 * espejo (los tests) sin tocarle el código de salida al proceso.
 */
function consolidar(WS) {
  const bases = rd(path.join(WS, "bases.json"));
  const roster = rd(path.join(WS, "roster_bundles.json"));
  const ev = rd(path.join(WS, "evaluacion.json"));
  const avisos = []; // observaciones_claude que generamos si falta data
  // Mapas normalizados de la evaluación (los avisos de forma los emite auditarEvaluacion).
  const { PE, EE } = normalizarEval(ev);

  // ── profesionales: auto-detecta N de _prof/ ─────────────────────────────────
  const dirProf = path.join(WS, "_prof");
  const nums = (fs.existsSync(dirProf) ? fs.readdirSync(dirProf) : [])
    .map((f) => (f.match(/profesional_(\d+)\.json$/) || [])[1])
    .filter(Boolean).map(Number).sort((a, b) => a - b);
  if (!nums.length) { console.error(`No hay _prof/profesional_NN.json en ${dirProf}`); process.exit(1); }

  const profesionales = [];
  const hechos = [];   // insumo del candado 1:1 (quién existe, cuántas declaró)
  for (const i of nums) {
    const raw = rd(path.join(dirProf, `profesional_${String(i).padStart(2, "0")}.json`));
    const pr = raw.profesional || {};
    const pe = PE[String(i)] || {};
    const ee = EE[String(i)] || [];
    const eeByN = {}; (Array.isArray(ee) ? ee : []).forEach((x) => { if (x) eeByN[x.n] = x; });

    const certs = Array.isArray(pr.certificaciones)
      ? (pr.certificaciones.length ? pr.certificaciones.join("; ") : null)
      : pick(pr.certificaciones);

    const experiencias = (raw.experiencias || []).map((e, idx) => {
      const n = e.n != null ? e.n : idx + 1;
      const j = eeByN[n] || {};
      let pag = intsFrom(e.paginas_pdf);
      const folio = pick(e.folio, pag[0]);
      if (!pag.length) pag = intsFrom(folio);
      const crudoObs = typeof e.observaciones === "string" ? e.observaciones
        : (Array.isArray(e.notas) ? e.notas.join(" ") : null);
      const obsExp = [pick(j.observaciones), crudoObs].filter(Boolean).join(" ⟦crudo: ").concat(crudoObs && j.observaciones ? "⟧" : "");
      return {
        n,
        entidad_emisora: pick(e.entidad_emisora, e.cliente_empleador, e.emisor, e.entidad),
        ruc_emisor: pick(e.ruc_emisor),
        proyecto: pick(e.proyecto),
        cui: pick(e.cui),
        tipo_documento: pick(e.tipo_documento),
        nombre_emisor: pick(e.nombre_emisor, e.firmante),
        cargo_emisor: pick(e.cargo_emisor),
        cargo_valido_emitir: pick(j.cargo_valido_emitir, e.cargo_valido_emitir),
        fecha_inicial: fechaOk(pick(e.fecha_inicial, e.fecha_inicio)),
        fecha_final: fechaOk(pick(e.fecha_final)),
        fecha_emision: fechaOk(pick(e.fecha_emision, e.fecha_emision_constancia)),
        folio: folio,
        paginas_pdf: pag.length ? pag : null,
        // #47 · verificación folio↔emisor hecha por el agente (true/false);
        // null = no reportada (legado). Booleano estricto: cualquier otra cosa
        // se descarta — un "sí" en texto no es una verificación.
        folio_verificado: typeof e.folio_verificado === "boolean" ? e.folio_verificado : null,
        dias: numify(j.dias),
        meses: numify(j.meses),
        anios: numify(j.anios),
        anterior_colegiatura: pick(j.anterior_colegiatura),
        cargo_ocupado: pick(e.cargo_ocupado, e.cargo_desempenado, e.cargo),
        cargo_bases_valido: pick(j.cargo_bases_valido),
        // Segunda puerta del cargo (#31): las funciones son un HECHO del documento
        // (lo extrae agent-propuesta-profesional), no un juicio; el evaluador solo
        // es respaldo. null = el documento no las lista → no acredita funciones,
        // que es lo que el candado del backend necesita distinguir.
        funciones_similares: pick(e.funciones_similares, j.funciones_similares),
        cert_antes_culminar: siNo(j.cert_antes_culminar, e.cert_antes_culminar),
        incluye_covid: siNo(j.incluye_covid, e.incluye_covid),
        tipo_obra_valido: pick(j.tipo_obra_valido),
        traslape: siNo(j.traslape, e.traslape),
        nivel_categoria: pick(e.nivel_categoria),
        area_construida_m2: numify(e.area_construida_m2),
        monto_contrato_soles: numify(e.monto_contrato_soles),
        entidad_contratante: pick(e.entidad_contratante),
        ubicacion: pick(e.ubicacion),
        observaciones: obsExp || pick(j.observaciones),
        // cert multi-obra: pasa la lista de sub-proyectos {proyecto, cui, fechas?}
        // (el backend resuelve cada CUI). Ausente en el caso normal (1 obra → `cui`).
        // fecha_inicial/fecha_final SOLO si el cert dio el rango POR obra (si no, null).
        obras: (Array.isArray(e.obras) && e.obras.length)
          ? e.obras.map((o) => ({
              proyecto: pick(o.proyecto), cui: pick(o.cui),
              fecha_inicial: fechaOk(pick(o.fecha_inicial, o.fecha_inicio)),
              fecha_final: fechaOk(pick(o.fecha_final)),
            }))
          : null,
        _backend: BACKEND(),
      };
    });

    const rRow = ((roster.roster || []).find((r) => r.n_prof === i) || {});
    // Correspondencia cargo↔bases: el número del LLM (agent-evaluador) se corría.
    // Candado determinístico: matchea el `cargo` literal del profesional contra el
    // nombre de cada cargo de `personal_clave`; ese match manda. El LLM es respaldo.
    const cargoDeclarado = pick(pr.cargo, rRow.cargo);
    const cargoLLM = pick(pe.cargo_bases_num, rRow.cargo_bases_num);
    const matchDet = matchCargoBases(cargoDeclarado, bases.personal_clave);
    const cargoNum = pick(matchDet && matchDet.numero, cargoLLM, i);
    if (matchDet && cargoLLM != null && matchDet.numero !== cargoLLM) {
      avisos.push({
        severidad: "warning", tipo: "cargo_corregido",
        mensaje: `n_prof ${i} "${cargoDeclarado}": el evaluador asignó cargo bases N°${cargoLLM}, `
          + `pero el match por nombre da N°${matchDet.numero} (${matchDet.nombre}). Se usó el match por nombre.`,
        referencia: `profesional ${i}`,
      });
    }
    // `pick` DESCARTA las cadenas vacías, así que `pick(x, "")` nunca puede
    // devolver "" — devuelve null, y el template lo imprime como el texto
    // "null" en la celda del Excel (8 celdas así en el análisis de Soritor).
    // El motivo se anexa solo si existe.
    const motivoFactorA = pick(pe.factor_a_cuenta);
    const aniosAd = pe.anios_adicionales != null
      ? (motivoFactorA ? `${pe.anios_adicionales} años — ${motivoFactorA}` : `${pe.anios_adicionales} años`)
      : null;

    const cargoBasesNombre = pick(matchDet && matchDet.nombre, pe.cargo_bases_nombre, rRow.cargo_bases_nombre);
    hechos.push({
      n_prof: i,
      cargo: cargoDeclarado,
      cargo_bases_nombre: cargoBasesNombre,
      n_experiencias: experiencias.length,
      // La llave con la que se pegó cada juicio (`eeByN[x.n]`), tal cual: si el
      // crudo no numeró contiguo, esto —no el conteo— es contra lo que hay que
      // cotejar al evaluador.
      ns_experiencias: experiencias.map((e) => e.n),
    });

    profesionales.push({
      n_prof: i,
      cargo: pick(pr.cargo, rRow.cargo),
      cargo_bases_num: cargoNum,
      cargo_bases_nombre: cargoBasesNombre,
      nombre: pick(pr.nombre, rRow.nombre),
      dni: pick(pr.dni),
      folio_nombre: pick(pr.folio_nombre, rRow.folio_nombre),
      titulo: pick(pr.titulo),
      folio_titulo: pick(pr.folio_titulo),
      profesion_valida: pick(pe.profesion_valida),
      colegiatura: pick(pr.colegiatura),
      fecha_colegiatura: fechaOk(pick(pr.fecha_colegiatura)),
      folio_colegiatura: pick(pr.folio_colegiatura, rRow.folio_colegiatura),
      certificaciones: certs,
      experiencia_total_declarada: declStr(pick(pr.experiencia_total_declarada, rRow.experiencia_total_declarada)),
      folio_anexo: pick(pr.folio_anexo, rRow.folio_anexo, rRow.folio_cuadro_resumen),  // Anexo 16 en la propuesta → recorte (mejora A)
      requisitos: requisitosDe(bases, cargoNum),
      experiencias,
      total: pe.total || {},
      cross_checks: crossChecks(raw.cross_checks),
      notas: Array.isArray(pr.notas) ? pr.notas : [],
      cumple: pick(pe.cumple),
      anios_adicionales: aniosAd,
    });
  }

  // Candado 1:1 (#45-L3): la evaluación tiene que cubrir a TODOS. No corrige nada
  // — solo impide que un hueco pase en silencio (el espejo valida igual con nulls).
  avisos.push(...auditarEvaluacion(ev, hechos));

  // ── postor: SE LEE del mapa (roster.postor), no se hardcodea ─────────────────
  const P = roster.postor || {};
  // OFERTA ECONÓMICA: merge POR CAMPO con dueño por dato, jamás pick del objeto
  // entero. La versión anterior (`pick(ev.oferta, mapa.oferta)`) dejaba que el
  // objeto del evaluador —que suele venir con los números en null y solo prosa—
  // PISARA completo al del mapa, que sí traía la propuesta: en urgente1
  // (e7c0fff6afb1) el mapa trajo propuesta=15,003,890.90 y el espejo salió con
  // las 3 celdas vacías (disparó OFERTA_INCOMPLETA — el candado atrapó la fuga).
  // Dueños: `propuesta` = el MAPA (Anexo 6 de la propuesta, dato del documento);
  // `cuantia`/`limite_inferior` = las BASES (metadata_concurso — es dato del
  // concurso, no de la propuesta); el evaluador solo es respaldo y su prosa va
  // al `detalle`. Un null NUNCA pisa un valor.
  const oeEv = (ev.postor_eval || {}).oferta_economica || {};
  const oeMapa = P.oferta_economica || {};
  const mc = bases.metadata_concurso || {};
  const detalles = [pick(oeEv.detalle), pick(oeMapa.detalle)].filter(Boolean);
  const oe = {
    cuantia: pick(numify(mc.cuantia), numify(oeEv.cuantia), numify(oeMapa.cuantia)),
    limite_inferior: pick(numify(mc.limite_inferior), numify(oeEv.limite_inferior),
                          numify(oeMapa.limite_inferior)),
    propuesta: pick(numify(oeMapa.propuesta), numify(oeEv.propuesta)),
    detalle: detalles.length > 1 && detalles[0] !== detalles[1]
      ? detalles.join(" · ") : (detalles[0] || null),
    es_inferior: pick(oeEv.es_inferior, oeMapa.es_inferior),
    es_superior: pick(oeEv.es_superior, oeMapa.es_superior),
  };

  const formularios = Array.isArray(P.formularios) ? P.formularios.map((f) => ({
    anexo: pick(f.anexo, "—"),
    // Mismo motivo que en `anios_adicionales`: `pick(x, "")` NUNCA devuelve ""
    // (descarta las cadenas vacías) → devolvía null, y el contrato exige string
    // en `observacion` → un formulario sin observación invalidaba el espejo ENTERO.
    documento: pick(f.documento) || "",
    observacion: pick(f.observacion, f["observación"]) || "",
    folio: f.folio != null ? f.folio : "",
  })) : [];
  if (!formularios.length) avisos.push({
    severidad: "warning", tipo: "postor_incompleto",
    mensaje: "roster_bundles.json no trae postor.formularios — el checklist de anexos quedó vacío. El mapa (agent-propuesta-mapa) debe poblarlo.",
    referencia: "postor.formularios",
  });

  // El mapa aporta los HECHOS del cuadro-resumen (emisor, contrato, proyecto,
  // monto, folio); el evaluador aporta el JUICIO por contrato (% objeto, le
  // corresponde, ¿tipo solicitado?). Se pegan por `n`, NO por posición: si el
  // evaluador se salta un contrato, un pegado posicional corre todos los
  // siguientes (misma trampa que el candado 1:1 de los profesionales).
  const pByN = {};
  for (const e of (ev.postor_eval || {}).experiencia_postor || []) {
    if (e && e.n != null) pByN[String(e.n)] = e;
  }
  const experiencia_postor = Array.isArray(P.experiencia_postor) ? P.experiencia_postor.map((x, idx) => {
    const n = x.n != null ? x.n : idx + 1;
    const j = pByN[String(n)] || {};
    return {
      n,
      cliente: pick(x.cliente, x.emisor, x.entidad),
      contrato: pick(x.contrato),
      proyecto: pick(x.proyecto),
      tipo_acreditacion: pick(x.tipo_acreditacion),
      monto: numify(x.monto),
      pct_objeto: pick(j.pct_objeto, x.pct_objeto),
      le_corresponde: pick(j.le_corresponde, x.le_corresponde),
      acredita: pick(x.acredita),
      folio: x.folio != null ? x.folio : null,
      ultimos_20_anios: pick(x.ultimos_20_anios, "POR VERIFICAR (corte 20 años — backend/Comité)"),
      tipo_solicitado: pick(j.tipo_solicitado, x.tipo_solicitado),
      observaciones: pick(j.observaciones, x.observaciones),
    };
  }) : [];
  if (!experiencia_postor.length) avisos.push({
    severidad: "warning", tipo: "postor_incompleto",
    mensaje: "roster_bundles.json no trae postor.experiencia_postor — el bloque de experiencia del postor quedó vacío (req. 3.4, criterio manual del Comité).",
    referencia: "postor.experiencia_postor",
  });

  const espejo = {
    _meta: {
      analisis_id: pick(bases.metadata_concurso && bases.metadata_concurso.analisis_id, path.basename(path.resolve(WS))),
      concurso: pick(bases.metadata_concurso && bases.metadata_concurso.nomenclatura),
      objeto: pick(bases.metadata_concurso && bases.metadata_concurso.objeto),
      entidad: pick(bases.metadata_concurso && bases.metadata_concurso.entidad),
      entidad_ruc: pick(bases.metadata_concurso && bases.metadata_concurso.entidad_ruc),
      cui: pick(bases.metadata_concurso && bases.metadata_concurso.cui),
      // página del PDF de bases con el Cuadro de Factores (4.2 A) → recorte que el
      // backend embebe al final de cada hoja de profesional (issue #32).
      pagina_factores: pick(bases.metadata_concurso && bases.metadata_concurso.pagina_factores),
      postor: pick(P.postor, P.nombre, (roster.postor_nivel || {}).postor),
      postor_ruc: pick(P.postor_ruc, P.ruc, (roster.postor_nivel || {}).postor_ruc),
      fecha_presentacion_oferta: pick(P.fecha_presentacion_oferta),
      version_contrato: "1.2.0",
      generado_por: "claude-code",
    },
    postor: {
      detalle: pick(P.detalle),
      formularios,
      oferta_economica: oe,   // ya mergeada por campo arriba (dueño por dato)
      experiencia_postor,
      experiencia_postor_total: pick((ev.postor_eval || {}).experiencia_postor_total, P.experiencia_postor_total, {}),
      postor_cumple: pick((ev.postor_eval || {}).postor_cumple),
      consorciados: Array.isArray(P.consorciados) ? P.consorciados : [],
    },
    profesionales,
    resumen_evaluacion: {
      factores: (ev.resumen_evaluacion || {}).factores || [],
      puntaje_total: numify((ev.resumen_evaluacion || {}).puntaje_total),
      nota: pick((ev.resumen_evaluacion || {}).nota),
    },
    observaciones_claude: [...avisos, ...(ev.observaciones_claude || [])],
  };

  const outPath = path.join(WS, "espejo.json");
  fs.writeFileSync(outPath, JSON.stringify(espejo, null, 2), "utf-8");
  // El espejo se escribe SIEMPRE (los hechos crudos no se pierden por un hueco
  // del evaluador), pero el reporte manda: si hay críticos, esto no salió bien.
  const criticos = reportar(outPath, espejo, avisos);
  return { espejo, criticos };
}

const main = (WS) => consolidar(WS).espejo;

module.exports = { normalizarEval, auditarEvaluacion, consolidar, main };

if (require.main === module) {
  const WS = process.argv[2];
  if (!WS) { console.error("uso: node scripts/consolidar_espejo.js <carpeta_analisis>"); process.exit(2); }
  const { criticos } = consolidar(WS);
  // El gate: sin esto el candado es decorativo — quien mira el exit code (o la
  // primera línea) concluye que todo salió bien y sigue al Paso 5.
  if (criticos.length) process.exitCode = 1;
}
