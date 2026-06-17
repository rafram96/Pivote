#!/usr/bin/env node
"use strict";
/**
 * generar_excel.js — Genera la hoja "CLAUDE" del Formato de Evaluación (new_format)
 * desde el JSON espejo. Versión Node (la PC del ingeniero solo tiene Node).
 *
 * new_format (hoja CLAUDE): 5 partes, PARTE 3/4 por profesional con labels
 *   "PARTE 3: INFORMACIÓN GENERAL — PROFESIONAL n DE N" y
 *   "PARTE 4: EXPERIENCIA — CARGO — Nombre", + filas de contexto de bases
 *   (cargos/tipo válidos), fila "experiencia total declarada", cross-checks y notas.
 * Las hojas por profesional (días efectivos / Paso 5) las añade el BACKEND luego
 * (vía scraping InfoObras), no este generador.
 *
 * Estilo del ingeniero + resaltado Claude(amarillo)/backend(naranja).
 *
 * Uso:  node scripts/generar_excel.js [ruta_json] [ruta_salida_xlsx]
 */
const fs = require("fs");
const path = require("path");
const ExcelJS = require("exceljs");

const NCOLS = 22;
const _argb = (hex) => "FF" + hex;
const fill = (hex) => ({ type: "pattern", pattern: "solid", fgColor: { argb: _argb(hex) } });
const SIDE = { style: "thin", color: { argb: _argb("999999") } };
const BORDER = { top: SIDE, left: SIDE, right: SIDE, bottom: SIDE };

// Formato del ingeniero (Manuel): blanco + bandas azules + verde/rojo SOLO en
// veredictos. Paridad con backend/scripts/generar_excel.py.
const F_PARTE = { bold: true, size: 11, color: { argb: _argb("FFFFFF") } };
const FILL_PARTE = fill("1F4E78");                  // azul oscuro: banda PARTE
const F_PROF = { bold: true, size: 11, color: { argb: _argb("FFFFFF") } };
const FILL_PROF = fill("2E75B6");                   // azul medio: banda PROFESIONAL
const F_HEAD = { bold: true, size: 9, color: { argb: _argb("1F3864") } };
const FILL_HEAD = fill("DDEBF7");                   // azul claro: headers
const F_CELL = { size: 9 };
const F_BOLD = { bold: true, size: 9 };
const FILL_CUMPLE = fill("C6EFCE");                 // verde: cumple / válido
const FILL_NO_CUMPLE = fill("FFC7CE");              // rojo: no cumple / alerta
const FILL_PEND = fill("FFF2CC");                   // amarillo suave: por verificar

// Marcador sutil de dato que verifica/recalcula el backend on-prem: borde izq. azul.
const SIDE_BE = { style: "medium", color: { argb: _argb("2E75B6") } };
const BORDER_BACKEND = { top: SIDE, left: SIDE_BE, right: SIDE, bottom: SIDE };

const AL_WRAP = { wrapText: true, vertical: "top" };
const AL_HEAD = { wrapText: true, vertical: "middle", horizontal: "center" };
const AL_TITLE = { vertical: "middle", horizontal: "left", wrapText: true };

const FMT_MONEY = "#,##0.00", FMT_DEC = "0.00", FMT_INT = "#,##0";
const WIDTHS = { A: 6, B: 25, C: 35, D: 30, E: 41, F: 22, G: 18, H: 18, I: 20, J: 12,
  K: 10, L: 14, M: 12, N: 10, O: 16, P: 25, Q: 18, R: 20, S: 18, T: 18, U: 18, V: 35 };

const has = (v) => v !== null && v !== undefined && v !== "";

// Verde/rojo de un veredicto, respetando polaridad por campo: "pos" = SÍ es bueno;
// "neg" = SÍ es malo (¿anterior a colegiatura?, ¿emitido antes de culminar?).
function _clasificarVeredicto(value) {
  if (value === null || value === undefined || value === "") return null;
  const t = String(value).trim().replace(/\s+/g, " ").toUpperCase();
  if (t.includes("POR VERIFICAR") || t.includes("NO APLICA") || ["-", "N/A", "?"].includes(t)) return "pend";
  if (/^(NO|✘|✗)/.test(t)) return "no";
  if (/^(SI|SÍ|CUMPLE|ACREDITA|VÁLIDO|VALIDO|✔|✓)/.test(t)) return "si";
  return null; // texto libre → sin color
}
function _fillVeredicto(value, pol) {
  const cl = _clasificarVeredicto(value);
  if (cl === null) return null;
  if (cl === "pend") return FILL_PEND;
  const bueno = pol === "pos" ? cl === "si" : cl === "no";
  return bueno ? FILL_CUMPLE : FILL_NO_CUMPLE;
}

const P4_HEAD = ["No", "ENTIDAD/EMPRESA QUE EMITE", "Proyecto u Obra", "TIPO DE DOCUMENTO",
  "NOMBRE DEL EMISOR", "CARGO DEL EMISOR", "¿Cargo válido para emitir?", "FECHA INICIAL",
  "FECHA FINAL", "FECHA DE EMISIÓN", "Folio", "DÍAS", "MESES", "AÑOS", "¿Anterior a la colegiatura?",
  "CARGO QUE OCUPÓ", "¿Cargo indicado en bases?", "¿Actividades similares?",
  "¿Emitido antes de culminar?", "¿Incluye periodo COVID?", "¿Tipo de obra solicitado?", "OBSERVACIONES"];

class Builder {
  constructor(ws) { this.ws = ws; this.r = 1; }

  _band(text, font, fillStyle, height) {
    this.ws.mergeCells(this.r, 1, this.r, NCOLS);
    const c = this.ws.getRow(this.r).getCell(1);
    c.value = text; c.font = font; c.fill = fillStyle; c.alignment = AL_TITLE;
    this.ws.getRow(this.r).height = height;
    this.r++;
  }
  parte(t) { this._band(t, F_PARTE, FILL_PARTE, 22); this.blank(); }
  profParte(t) { this._band(t, F_PROF, FILL_PROF, 22); }

  headers(vals) {
    const row = this.ws.getRow(this.r);
    vals.forEach((v, idx) => {
      const c = row.getCell(idx + 1);
      c.value = v; c.font = F_HEAD; c.fill = FILL_HEAD; c.border = BORDER; c.alignment = AL_HEAD;
    });
    row.height = 32; this.r++;
  }

  row(vals, opts = {}) {
    const { bold = false, fmts = {}, verdicts = {}, backendCols = new Set() } = opts;
    const row = this.ws.getRow(this.r);
    vals.forEach((v, idx) => {
      const i = idx + 1;
      const c = row.getCell(i);
      c.value = (v === undefined ? null : v);
      c.font = bold ? F_BOLD : F_CELL; c.alignment = AL_WRAP;
      c.border = backendCols.has(i) ? BORDER_BACKEND : BORDER;
      if (fmts[i] !== undefined && typeof v === "number") c.numFmt = fmts[i];
      if (verdicts[i] !== undefined) {
        const f = _fillVeredicto(v, verdicts[i]);
        if (f) c.fill = f;
      }
    });
    this.r++;
  }

  kv(label, value, fmt, verdict) {
    const row = this.ws.getRow(this.r);
    row.getCell(1).value = label; row.getCell(1).font = F_BOLD;
    this.ws.mergeCells(this.r, 2, this.r, NCOLS);
    const c = row.getCell(2);
    c.value = (value === undefined ? null : value); c.font = F_CELL; c.alignment = AL_WRAP;
    if (fmt && typeof value === "number") c.numFmt = fmt;
    if (verdict) { const f = _fillVeredicto(value, verdict); if (f) c.fill = f; }
    this.r++;
  }

  bc(label, value, verdict) {
    const row = this.ws.getRow(this.r);
    const a = row.getCell(2);
    a.value = label; a.font = F_BOLD; a.alignment = AL_WRAP; a.border = BORDER;
    this.ws.mergeCells(this.r, 3, this.r, NCOLS);
    const c = row.getCell(3);
    c.value = (value === undefined ? null : value); c.font = F_CELL; c.alignment = AL_WRAP; c.border = BORDER;
    if (verdict) { const f = _fillVeredicto(value, verdict); if (f) c.fill = f; }
    this.r++;
  }

  leyenda() {
    const row = this.ws.getRow(this.r);
    row.getCell(1).value = "Leyenda:"; row.getCell(1).font = F_BOLD;
    const swatches = [
      [2, 3, "Verde = cumple / válido", FILL_CUMPLE, BORDER],
      [4, 5, "Rojo = no cumple / alerta", FILL_NO_CUMPLE, BORDER],
      [6, 8, "Amarillo = por verificar", FILL_PEND, BORDER],
      [9, 12, "Borde azul izq. = verifica/recalcula el backend on-prem", null, BORDER_BACKEND],
    ];
    swatches.forEach(([ini, fin, txt, fillStyle, border]) => {
      this.ws.mergeCells(this.r, ini, this.r, fin);
      const c = row.getCell(ini);
      c.value = txt; c.font = F_CELL; c.border = border; c.alignment = AL_TITLE;
      if (fillStyle) c.fill = fillStyle;
    });
    this.r++;
  }

  blank() { this.r++; }
}

async function generarExcel(espejo, salida) {
  const wb = new ExcelJS.Workbook();
  const ws = wb.addWorksheet("CLAUDE");
  Object.entries(WIDTHS).forEach(([letter, w]) => { ws.getColumn(letter).width = w; });
  const b = new Builder(ws);
  const meta = espejo._meta || {};
  const p = espejo.postor || {};
  const profs = espejo.profesionales || [];
  const N = profs.length;

  // Encabezado
  b.kv("Nombre del postor:", p.detalle || meta.postor || "");
  b.kv("Concurso:", meta.concurso || "");
  b.leyenda();
  b.blank();

  // PARTE 1
  b.parte("PARTE 1: FORMULARIOS DEL POSTOR");
  b.headers(["ANEXO", "DOCUMENTO", "OBSERVACIÓN (¿presenta?, ¿corresponde?)", "N° de Folio"]);
  (p.formularios || []).forEach((f) => b.row([f.anexo || "", f.documento || f.descripcion || "", f.observacion || "", f.folio || ""]));
  b.blank();
  const oe = p.oferta_economica || {};
  if (Object.keys(oe).length) {
    b.headers(["", "CUANTÍA", "LÍMITE INFERIOR", "PROPUESTA", "¿INFERIOR AL LÍMITE?", "¿SUPERIOR AL LÍMITE?"]);
    b.row(["Monto", oe.cuantia, oe.limite_inferior, oe.propuesta, oe.es_inferior || oe.detalle || "", oe.es_superior || ""],
      { fmts: { 2: FMT_MONEY, 3: FMT_MONEY, 4: FMT_MONEY } });
  }
  b.blank();

  // PARTE 2
  b.parte("PARTE 2: EXPERIENCIA DEL POSTOR");
  b.headers(["No", "CLIENTE QUE EMITE", "CONTRATO Y/O OS Y/O FACTURA", "Nombre del Proyecto", "TIPO DE ACREDITACIÓN",
    "MONTO (S/)", "% POR OBJETO U CONTRATO", "LE CORRESPONDE (S/)", "ACREDITA (consorciado)", "Folio",
    "¿Últimos 20 años?", "¿Tipo solicitado en bases?", "OBSERVACIONES"]);
  const m2 = { 6: FMT_MONEY, 7: FMT_DEC, 8: FMT_MONEY };
  // ¿últimos 20/25 años? (11) y ¿tipo solicitado? (12) son veredictos "pos";
  // la antigüedad (11) la recalcula el backend.
  const V2 = { 11: "pos", 12: "pos" }, BE2 = new Set([11]);
  (p.experiencia_postor || []).forEach((e) => b.row([e.n, e.cliente, e.contrato, e.proyecto, e.tipo_acreditacion,
    e.monto, e.pct_objeto, e.le_corresponde, e.acredita, e.folio, e.ultimos_20_anios, e.tipo_solicitado, e.observaciones],
    { fmts: m2, verdicts: V2, backendCols: BE2 }));
  const tot = p.experiencia_postor_total || {};
  if (Object.keys(tot).length) {
    const tv = (tot.le_corresponde !== undefined ? tot.le_corresponde : tot.acredita);
    b.row(["", "", "", "", "", "", "", "TOTAL (le corresponde):", tv, "", "", "", ""], { bold: true, fmts: { 9: FMT_MONEY } });
  }
  if (p.postor_cumple) b.bc("EL POSTOR CUMPLE EL REQUISITO 3.4:", p.postor_cumple, "pos");
  b.blank();

  // PARTE 3 + 4 por profesional
  const m4 = { 12: FMT_INT, 13: FMT_DEC, 14: FMT_DEC };
  // Veredictos PARTE 4: "pos" = SÍ bueno; "neg" = SÍ malo (¿anterior a
  // colegiatura? 15, ¿emitido antes de culminar? 19). ¿COVID? (20) informativo.
  const V4 = { 7: "pos", 15: "neg", 17: "pos", 18: "pos", 19: "neg", 21: "pos" };
  // Backend: ¿válido emitir? (SUNAT), días/meses/años (Paso 5), ¿ant. coleg.? (ALT03).
  const BE4 = new Set([7, 12, 13, 14, 15]);
  for (const prof of profs) {
    b.parte(`PARTE 3: INFORMACIÓN GENERAL — PROFESIONAL ${prof.n_prof} DE ${N}`);
    b.headers(["No", "CARGO", "DETALLE", "INFORMACIÓN DE LA PROPUESTA", "N° de Folio", "OBSERVACIÓN"]);
    b.row([prof.n_prof, prof.cargo, "NOMBRE DEL PROFESIONAL", prof.nombre, prof.folio_nombre, ""]);
    b.row(["", "", "TÍTULO PROFESIONAL (profesión)", prof.titulo, prof.folio_titulo || "", ""]);
    b.row(["", "", "¿La profesión es la indicada en bases?", prof.profesion_valida, "", ""], { verdicts: { 4: "pos" } });
    b.row(["", "", "N° DE COLEGIATURA y fecha", prof.colegiatura, prof.fecha_colegiatura || prof.folio_colegiatura || "", ""]);
    b.row(["", "", "B. CERTIFICACIONES DEL PERSONAL CLAVE", prof.certificaciones, "", ""]);
    if (has(prof.experiencia_total_declarada)) {
      b.row(["", "", "Experiencia total declarada (años)", prof.experiencia_total_declarada, "", ""],
        { fmts: { 4: FMT_DEC } });
    }
    b.blank();

    b.profParte(`PARTE 4: EXPERIENCIA — ${prof.cargo || ""} — ${prof.nombre || ""}`);
    const req = prof.requisitos || {};
    if (req.cargos_validos) b.bc("Cargos válidos según bases:", req.cargos_validos);
    if (req.tipo_experiencia_valida) b.bc("Tipo de experiencia válida:", req.tipo_experiencia_valida);
    if (req.tipo_obra_valida) b.bc("Tipo de obra válida:", req.tipo_obra_valida);
    b.headers(P4_HEAD);
    for (const e of (prof.experiencias || [])) {
      b.row([e.n, e.entidad_emisora, e.proyecto, e.tipo_documento, e.nombre_emisor, e.cargo_emisor,
        e.cargo_valido_emitir, e.fecha_inicial, e.fecha_final, e.fecha_emision, e.folio,
        e.dias, e.meses, e.anios, e.anterior_colegiatura, e.cargo_ocupado, e.cargo_bases_valido,
        e.funciones_similares, e.cert_antes_culminar, e.incluye_covid, e.tipo_obra_valido, e.observaciones],
        { fmts: m4, verdicts: V4, backendCols: BE4 });
    }
    const t = prof.total || {};
    b.row(["", "", "", "", "", "", "", "", "", "", "TOTAL", t.dias, t.meses, t.anios, "", "", "", "", "", "", "", ""],
      { bold: true, fmts: m4, backendCols: new Set([12, 13, 14]) });
    // cross-checks (new_format) o, en su defecto, cumple/años adicionales (compat)
    if (Array.isArray(prof.cross_checks) && prof.cross_checks.length) {
      prof.cross_checks.forEach((cc) => b.bc(cc.label, cc.valor));
    } else {
      if (prof.cumple) b.bc("¿EL PROFESIONAL CUMPLE?", prof.cumple, "pos");
      if (prof.anios_adicionales) b.bc("Años adicionales (Factor A):", prof.anios_adicionales);
    }
    (prof.notas || []).forEach((n) => b.bc("Nota:", n));
    b.blank();
  }

  // PARTE 5
  const re = espejo.resumen_evaluacion || {};
  b.parte("PARTE 5: RESUMEN DE LA EVALUACIÓN — FACTORES DE EVALUACIÓN (Cap. IV)");
  b.headers(["FACTOR", "CRITERIO", "FOLIO", "DETALLE / OBSERVACIONES", "PUNTAJE"]);
  (re.factores || []).forEach((f) => b.row([f.factor, f.criterio, f.folio, f.detalle, f.puntaje], { fmts: { 5: FMT_INT } }));
  if (re.puntaje_total !== null && re.puntaje_total !== undefined) {
    b.row(["PUNTAJE TÉCNICO TOTAL", "", "", "", re.puntaje_total], { bold: true, fmts: { 5: FMT_INT } });
  }
  if (re.nota) b.bc("Conclusión:", re.nota);

  fs.mkdirSync(path.dirname(salida), { recursive: true });
  await wb.xlsx.writeFile(salida);
  return salida;
}

module.exports = { generarExcel };

if (require.main === module) {
  (async () => {
    const base = path.resolve(__dirname, "../..");
    const jsonPath = process.argv[2] || path.join(base, "fixtures", "new_format", "libertador_espejo.json");
    const outPath = process.argv[3] || path.join(base, "fixtures", "new_format", "_generado_newfmt.xlsx");
    const espejo = JSON.parse(fs.readFileSync(jsonPath, "utf-8"));
    const res = await generarExcel(espejo, outPath);
    const nprof = (espejo.profesionales || []).length;
    const nexp = (espejo.profesionales || []).reduce((s, p) => s + (p.experiencias ? p.experiencias.length : 0), 0);
    console.log(`OK · ${nprof} profesionales · ${nexp} experiencias · ${res}`);
  })().catch((e) => { console.error(e); process.exit(1); });
}
