"use strict";
/**
 * Schema zod del JSON espejo de la skill `analizar-licitacion-osce`.
 * Versión Node del contrato (la PC del ingeniero solo tiene Node, no Python).
 * Equivalente a `backend/schemas/espejo.py` (Pydantic), forma plana real.
 *
 * Contrato **v1.2.0** — mantener en paridad con el Pydantic (los cambios de
 * versión se listan en el docstring de espejo.py). El test de contrato
 * (`tools/test_contrato.py`) corre los mismos fixtures por ambos validadores.
 *
 * El bloque `_backend` es opcional y va vacío/null en la salida de Claude.
 */
const { z } = require("zod");

// ── Tipos flexibles (datos reales) ──────────────────────────────────────────
// Sentinel de la NOTA 12: dato ilegible/no consignado tras reintentos.
const SENTINEL_POR_VERIFICAR = "POR VERIFICAR";
const RE_FECHA_ISO = /^\d{4}-\d{2}-\d{2}$/;          // 2016-06-10
const RE_FECHA_PARCIAL = /^\d{4}-\d{2}(\D.*)?$/;     // "2015-11 (sin día)"

// Fecha: ISO completa, parcial con anotación, o sentinel. Nada más.
const fecha = z
  .string()
  .nullable()
  .optional()
  .refine(
    (v) =>
      v == null ||
      RE_FECHA_ISO.test(v) ||
      v.startsWith(SENTINEL_POR_VERIFICAR) ||
      RE_FECHA_PARCIAL.test(v),
    { message: `fecha inválida (se espera YYYY-MM-DD, 'YYYY-MM (anotación)' o '${SENTINEL_POR_VERIFICAR}…')` }
  );
const monto = z.number().nonnegative().nullable().optional();
const txt = z.string().nullable().optional();
// Folios reales: número (596), rango ("14-32 y 39-41") o texto.
const folioT = z.union([z.string(), z.number()]).nullable().optional();

const Formulario = z.object({
  anexo: z.string().default(""),
  documento: z.string().optional(),      // new_format (columna "DOCUMENTO")
  descripcion: z.string().optional(),    // formato Trujillo (compat)
  observacion: z.string().default(""),
  folio: folioT.default(""),
}).passthrough();

const OfertaEconomica = z.object({
  cuantia: monto, limite_inferior: monto, propuesta: monto, detalle: txt,
}).passthrough();

const ExperienciaPostor = z.object({
  n: z.number().int().min(1),
  cliente: txt, contrato: txt, proyecto: txt, tipo_acreditacion: txt,
  monto, pct_objeto: z.number().min(0).max(1).nullable().optional(),
  le_corresponde: monto,
  acredita: z.union([z.number(), z.string()]).nullable().optional(), // consorciado que acredita (texto) o monto
  folio: folioT,
  ultimos_20_anios: txt, tipo_solicitado: txt, observaciones: txt,
}).strict();

const Backend = z.object({}).passthrough();

// Cert con VARIOS sub-proyectos bajo un mismo vínculo continuo (rol de gestión/
// portafolio, p. ej. "gestión de proyectos de inversión"): 1 experiencia (1
// periodo) que abarca N obras, cada una con su CUI. El TIEMPO se cuenta una sola
// vez (el periodo de la experiencia); estas obras son para que el backend verifique
// cada CUI por separado. Genérico: sirve a cualquier constancia que liste obras con
// su código, no a un formato específico.
const SubObra = z.object({
  proyecto: txt,                 // nombre del sub-proyecto/obra
  cui: txt,                      // CUI/SNIP del sub-proyecto (solo dígitos), o null si no lo cita
  // SOLO si el cert consigna el rango de tiempo POR obra (además del total del
  // vínculo). Habilita el cruce de cobertura por sub-obra; si no, null.
  fecha_inicial: fecha,
  fecha_final: fecha,
}).strict();

const ExperienciaProf = z.object({
  n: z.number().int().min(1),
  entidad_emisora: txt, ruc_emisor: txt,
  proyecto: txt,                 // nombre de obra VERBATIM y completo (sin abreviar ni meter metadata)
  cui: txt,                      // CUI/SNIP citado en el cert (solo dígitos) → Paso 0 determinístico
  cui_fuente: txt,               // "certificado" | "skill" (resuelto por Claude en el Paso 4.5)
  tipo_documento: txt, nombre_emisor: txt,
  cargo_emisor: txt, cargo_valido_emitir: txt,
  fecha_inicial: fecha, fecha_final: fecha, fecha_emision: fecha,
  folio: folioT,
  // páginas FÍSICAS reales del PDF de la constancia (1-indexadas, principal 1ª).
  // El folio impreso del borde ≠ la página del PDF NO siempre → esto evita recortar
  // la hoja equivocada. `folio` queda para citar; `paginas_pdf` para el recorte.
  paginas_pdf: z.array(z.number().int().positive()).nullable().optional(),
  dias: monto, meses: monto, anios: monto,
  anterior_colegiatura: txt, cargo_ocupado: txt, cargo_bases_valido: txt,
  funciones_similares: txt, cert_antes_culminar: txt, incluye_covid: txt,
  tipo_obra_valido: txt,
  traslape: txt,                 // NOTA 9: SÍ/NO/null — Claude marca, backend re-verifica
  nivel_categoria: txt,          // nivel hospitalario del proyecto ("II-1", "Centro de Salud"…)
  area_construida_m2: monto,
  monto_contrato_soles: monto,
  entidad_contratante: txt,      // dueño de la obra (≠ emisor del cert) → score CUI
  ubicacion: txt,                // dpto/prov/distrito si el cert lo cita → score CUI
  observaciones: txt,
  // Sub-proyectos si el cert es multi-obra (1 vínculo, N obras). Vacío/ausente en
  // el caso normal (1 experiencia = 1 obra, va en `cui`). Ver SubObra.
  obras: z.array(SubObra).nullable().optional(),
  _backend: Backend.optional(),
}).strict().superRefine((e, ctx) => {
  const ini = e.fecha_inicial, fin = e.fecha_final;
  // Solo comparable si ambas son fechas ISO completas (no sentinel/parcial).
  if (ini && fin && RE_FECHA_ISO.test(ini) && RE_FECHA_ISO.test(fin) && fin < ini) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: `exp ${e.n}: fecha_final < fecha_inicial` });
  }
});

// NOTA 1: cross-check contra el cuadro resumen del Anexo 16.
const CrossCheck = z.object({
  label: txt,
  valor: z.union([z.string(), z.record(z.any())]).nullable().optional(),
}).passthrough();

const Profesional = z.object({
  n_prof: z.number().int().min(1),
  cargo: z.string().min(1),            // etiqueta LITERAL del cargo en la propuesta (sin la cola "(cargo bases N°…)")
  cargo_bases_num: z.number().int().nullable().optional(),  // nº del cargo equivalente en el Cuadro de Personal de las bases
  cargo_bases_nombre: txt,             // nombre de ese cargo de bases ("ESPECIALISTA EN ESTRUCTURAS")
  nombre: txt, dni: txt, folio_nombre: folioT, titulo: txt, folio_titulo: folioT,
  profesion_valida: txt, colegiatura: txt,
  fecha_colegiatura: fecha,
  folio_colegiatura: folioT, certificaciones: txt,
  // NOTA 1/5: lo autodeclarado en el Anexo 16 (número o texto literal del cuadro).
  experiencia_total_declarada: z.union([z.number(), z.string()]).nullable().optional(),
  // Requisitos de las bases para este cargo (cargos_validos, tipo_obra, …).
  requisitos: z.record(z.any()).nullable().optional(),
  experiencias: z.array(ExperienciaProf).default([]),
  total: z.record(z.any()).default({}),
  cross_checks: z.array(CrossCheck).optional(),
  notas: z.array(z.string()).optional(),
  cumple: txt, anios_adicionales: txt,
}).passthrough().superRefine((p, ctx) => {
  const ns = p.experiencias.map((e) => e.n);
  const esperado = ns.map((_, i) => i + 1);
  if (ns.length && JSON.stringify(ns) !== JSON.stringify(esperado)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: `profesional ${p.n_prof}: 'n' de experiencias no es 1..N contiguo: [${ns}]` });
  }
});

const Factor = z.object({
  factor: z.string().min(1),
  criterio: txt, folio: folioT, detalle: txt,
  aplica: z.boolean().nullable().optional(),  // false ⇔ puntaje "NO APLICA"
  puntaje: z.union([
    z.number(),
    z.string().refine((s) => s.trim().toUpperCase().startsWith("NO APLICA"),
      { message: "puntaje inválido (número, null o 'NO APLICA…')" }),
  ]).nullable().optional(),
}).strict();

const ResumenEvaluacion = z.object({
  factores: z.array(Factor).default([]),
  puntaje_total: monto,
  nota: txt,
}).passthrough();

// Hallazgo cualitativo de los subagentes (ambigüedad, ilegibilidad, …).
const Observacion = z.object({
  severidad: txt,                // info | warning | critical
  tipo: txt,
  mensaje: txt,
  referencia: txt,
}).passthrough();

const JsonEspejo = z.object({
  _meta: z.object({ analisis_id: z.string().min(1) }).passthrough(),
  postor: z.object({
    detalle: txt,
    formularios: z.array(Formulario).default([]),
    oferta_economica: OfertaEconomica.default({}),
    experiencia_postor: z.array(ExperienciaPostor).default([]),
    experiencia_postor_total: z.record(z.any()).default({}),
    postor_cumple: txt,
    // NOTA 14: quiénes integran el consorcio (para exigir ISO de TODOS).
    consorciados: z.array(z.record(z.any())).nullable().optional(),
  }).passthrough(),
  profesionales: z.array(Profesional).min(1),
  resumen_evaluacion: ResumenEvaluacion.default({}),
  observaciones_claude: z.array(Observacion).optional(),
}).passthrough().superRefine((d, ctx) => {
  const ns = d.profesionales.map((p) => p.n_prof);
  const esperado = ns.map((_, i) => i + 1);
  if (JSON.stringify(ns) !== JSON.stringify(esperado)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: `n_prof debe ser 1..N contiguo y único: [${ns}]` });
  }
});

module.exports = { JsonEspejo, SENTINEL_POR_VERIFICAR };
