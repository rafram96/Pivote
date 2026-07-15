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
 */
const fs = require("fs");
const path = require("path");
const { matchCargoBases } = require("./match_cargo");

const WS = process.argv[2];
if (!WS) { console.error("uso: node scripts/consolidar_espejo.js <carpeta_analisis>"); process.exit(2); }
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf-8"));
const rdOpt = (p, def) => (fs.existsSync(p) ? rd(p) : def);

const bases = rd(path.join(WS, "bases.json"));
const roster = rd(path.join(WS, "roster_bundles.json"));
const ev = rd(path.join(WS, "evaluacion.json"));
const avisos = []; // observaciones_claude que generamos si falta data

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

function requisitosDe(cargoNum) {
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

// ── profesionales: auto-detecta N de _prof/ ─────────────────────────────────
const dirProf = path.join(WS, "_prof");
const nums = (fs.existsSync(dirProf) ? fs.readdirSync(dirProf) : [])
  .map((f) => (f.match(/profesional_(\d+)\.json$/) || [])[1])
  .filter(Boolean).map(Number).sort((a, b) => a - b);
if (!nums.length) { console.error(`No hay _prof/profesional_NN.json en ${dirProf}`); process.exit(1); }

const profesionales = [];
for (const i of nums) {
  const raw = rd(path.join(dirProf, `profesional_${String(i).padStart(2, "0")}.json`));
  const pr = raw.profesional || {};
  const pe = (ev.profesionales_eval || {})[String(i)] || {};
  const ee = (ev.experiencias_eval || {})[String(i)] || [];
  const eeByN = {}; ee.forEach((x) => { eeByN[x.n] = x; });

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
    const obs = [pick(j.observaciones), crudoObs].filter(Boolean).join(" ⟦crudo: ").concat(crudoObs && j.observaciones ? "⟧" : "");
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
      dias: numify(j.dias),
      meses: numify(j.meses),
      anios: numify(j.anios),
      anterior_colegiatura: pick(j.anterior_colegiatura),
      cargo_ocupado: pick(e.cargo_ocupado, e.cargo_desempenado, e.cargo),
      cargo_bases_valido: pick(j.cargo_bases_valido),
      funciones_similares: null,
      cert_antes_culminar: siNo(j.cert_antes_culminar, e.cert_antes_culminar),
      incluye_covid: siNo(j.incluye_covid, e.incluye_covid),
      tipo_obra_valido: pick(j.tipo_obra_valido),
      traslape: siNo(j.traslape, e.traslape),
      nivel_categoria: pick(e.nivel_categoria),
      area_construida_m2: numify(e.area_construida_m2),
      monto_contrato_soles: numify(e.monto_contrato_soles),
      entidad_contratante: pick(e.entidad_contratante),
      ubicacion: pick(e.ubicacion),
      observaciones: obs || pick(j.observaciones),
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
  const aniosAd = pe.anios_adicionales != null
    ? `${pe.anios_adicionales} años — ${pick(pe.factor_a_cuenta, "")}`.trim()
    : null;

  profesionales.push({
    n_prof: i,
    cargo: pick(pr.cargo, rRow.cargo),
    cargo_bases_num: cargoNum,
    cargo_bases_nombre: pick(matchDet && matchDet.nombre, pe.cargo_bases_nombre, rRow.cargo_bases_nombre),
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
    requisitos: requisitosDe(cargoNum),
    experiencias,
    total: pe.total || {},
    cross_checks: crossChecks(raw.cross_checks),
    notas: Array.isArray(pr.notas) ? pr.notas : [],
    cumple: pick(pe.cumple),
    anios_adicionales: aniosAd,
  });
}

// ── postor: SE LEE del mapa (roster.postor), no se hardcodea ─────────────────
const P = roster.postor || {};
const oe = pick((ev.postor_eval || {}).oferta_economica, P.oferta_economica) || {};

let formularios = Array.isArray(P.formularios) ? P.formularios.map((f) => ({
  anexo: pick(f.anexo, "—"),
  documento: pick(f.documento, ""),
  observacion: pick(f.observacion, f["observación"], ""),
  folio: f.folio != null ? f.folio : "",
})) : [];
if (!formularios.length) avisos.push({
  severidad: "warning", tipo: "postor_incompleto",
  mensaje: "roster_bundles.json no trae postor.formularios — el checklist de anexos quedó vacío. El mapa (agent-propuesta-mapa) debe poblarlo.",
  referencia: "postor.formularios",
});

let experiencia_postor = Array.isArray(P.experiencia_postor) ? P.experiencia_postor.map((x, idx) => ({
  n: x.n != null ? x.n : idx + 1,
  cliente: pick(x.cliente, x.emisor, x.entidad),
  contrato: pick(x.contrato),
  proyecto: pick(x.proyecto),
  tipo_acreditacion: pick(x.tipo_acreditacion),
  monto: numify(x.monto),
  pct_objeto: pick(x.pct_objeto),
  le_corresponde: pick(x.le_corresponde),
  acredita: pick(x.acredita),
  folio: x.folio != null ? x.folio : null,
  ultimos_20_anios: pick(x.ultimos_20_anios, "POR VERIFICAR (corte 20 años — backend/Comité)"),
  tipo_solicitado: pick(x.tipo_solicitado),
  observaciones: pick(x.observaciones),
})) : [];
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
    postor: pick(P.postor, P.nombre, (roster.postor_nivel || {}).postor),
    postor_ruc: pick(P.postor_ruc, P.ruc, (roster.postor_nivel || {}).postor_ruc),
    fecha_presentacion_oferta: pick(P.fecha_presentacion_oferta),
    version_contrato: "1.2.0",
    generado_por: "claude-code",
  },
  postor: {
    detalle: pick(P.detalle),
    formularios,
    oferta_economica: {
      cuantia: numify(oe.cuantia),
      limite_inferior: numify(oe.limite_inferior),
      propuesta: numify(oe.propuesta),
      detalle: pick(oe.detalle),
      es_inferior: pick(oe.es_inferior),
      es_superior: pick(oe.es_superior),
    },
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
const nexp = profesionales.reduce((s, p) => s + p.experiencias.length, 0);
console.log(`OK · espejo escrito en ${outPath} · ${profesionales.length} profesionales · ${nexp} experiencias · ${espejo.resumen_evaluacion.factores.length} factores`);
if (avisos.length) console.log(`⚠ ${avisos.length} aviso(s) de postor incompleto — revisa observaciones_claude.`);
