"use strict";
/**
 * Schema zod del JSON espejo de la skill `analizar-licitacion-osce`.
 * Versión Node del contrato (la PC del ingeniero solo tiene Node, no Python).
 * Equivalente a `backend/schemas/espejo.py` (Pydantic), forma plana real.
 *
 * El bloque `_backend` es opcional y va vacío/null en la salida de Claude.
 */
const { z } = require("zod");

// Datos reales: fechas pueden traer anotaciones; folios pueden ser número o rango.
const fecha = z.string().nullable().optional();
const monto = z.number().nonnegative().nullable().optional();
const txt = z.string().nullable().optional();
const folioT = z.union([z.string(), z.number()]).nullable().optional();

const Formulario = z.object({
  anexo: z.string().default(""),
  documento: z.string().optional(),      // new_format
  descripcion: z.string().optional(),    // formato Trujillo (compat)
  observacion: z.string().default(""),
  folio: z.string().default(""),
}).passthrough();

const OfertaEconomica = z.object({
  cuantia: monto, limite_inferior: monto, propuesta: monto, detalle: txt,
}).passthrough();

const ExperienciaPostor = z.object({
  n: z.number().int().min(1),
  cliente: txt, contrato: txt, proyecto: txt, tipo_acreditacion: txt,
  monto, pct_objeto: z.number().min(0).max(1).nullable().optional(),
  le_corresponde: monto,
  acredita: z.union([z.number(), z.string()]).nullable().optional(), // n° o consorciado
  folio: folioT,
  ultimos_20_anios: txt, tipo_solicitado: txt, observaciones: txt,
}).strict();

const Backend = z.object({}).passthrough();

const ExperienciaProf = z.object({
  n: z.number().int().min(1),
  entidad_emisora: txt, ruc_emisor: txt,
  proyecto: txt,                 // nombre de obra VERBATIM y completo (sin abreviar ni meter metadata)
  cui: txt,                      // CUI/SNIP citado en el cert (solo dígitos) → Paso 0 determinístico
  tipo_documento: txt, nombre_emisor: txt,
  cargo_emisor: txt, cargo_valido_emitir: txt,
  fecha_inicial: fecha, fecha_final: fecha, fecha_emision: fecha,
  folio: folioT,
  dias: monto, meses: monto, anios: monto,
  anterior_colegiatura: txt, cargo_ocupado: txt, cargo_bases_valido: txt,
  funciones_similares: txt, cert_antes_culminar: txt, incluye_covid: txt,
  tipo_obra_valido: txt, observaciones: txt,
  _backend: Backend.optional(),
}).strict().superRefine((e, ctx) => {
  if (e.fecha_inicial && e.fecha_final && e.fecha_final < e.fecha_inicial) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: `exp ${e.n}: fecha_final < fecha_inicial` });
  }
});

const Profesional = z.object({
  n_prof: z.number().int().min(1),
  cargo: z.string().min(1),
  nombre: txt, folio_nombre: folioT, titulo: txt, folio_titulo: folioT,
  profesion_valida: txt, colegiatura: txt, folio_colegiatura: folioT, certificaciones: txt,
  experiencias: z.array(ExperienciaProf).default([]),
  total: z.record(z.any()).default({}),
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
  puntaje: z.union([z.number(), z.string()]).nullable().optional(), // n° o "NO APLICA"
}).strict();

const ResumenEvaluacion = z.object({
  factores: z.array(Factor).default([]),
  puntaje_total: monto,
  nota: txt,
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
  }).passthrough(),
  profesionales: z.array(Profesional).min(1),
  resumen_evaluacion: ResumenEvaluacion.default({}),
}).passthrough().superRefine((d, ctx) => {
  const ns = d.profesionales.map((p) => p.n_prof);
  const esperado = ns.map((_, i) => i + 1);
  if (JSON.stringify(ns) !== JSON.stringify(esperado)) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, message: `n_prof debe ser 1..N contiguo y único: [${ns}]` });
  }
});

module.exports = { JsonEspejo };
