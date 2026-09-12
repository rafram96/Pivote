"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { prepararProfesional, fechaCompleta, indicadoresTemporales } = require("./preparar_extraccion");

test("emisión y fin completos se comparan aunque el inicio sea parcial", () => {
  assert.deepEqual(indicadoresTemporales({ fecha_inicial: "2020-04", fecha_final: "2020-05-20", fecha_emision: "2020-05-19" }),
    { incluye_covid: null, cert_antes_culminar: "SÍ" });
});
test("array vacío de funciones se convierte en null, nunca llega al schema", () => {
  assert.equal(prepararProfesional({ experiencias: [{ n: 1, funciones_similares: [] }] }, 1).profesional.experiencias[0].funciones_similares, null);
});
test("ítem distinto se revisa y la fuente completa llega a observaciones", () => {
  const r = prepararProfesional({ experiencias: [{ n: 1, proyecto: "Hospital ITEM 2", proyecto_fuente: { texto: "Hospital ÍTEM N° 1: Sala de operaciones", pagina_pdf: 35 } }] }, 1);
  assert.equal(r.revisiones[0].campo, "proyecto");
  assert.match(r.profesional.experiencias[0].observaciones, /Sala de operaciones/);
  assert.equal(r.profesional.experiencias[0].proyecto, "Hospital ITEM 2");
});

test("fechaCompleta exige calendario ISO exacto", () => {
  assert.equal(fechaCompleta("2020-02-29"), true);
  assert.equal(fechaCompleta("2021-02-29"), false);
  assert.equal(fechaCompleta("2020-2-01"), false);
  assert.equal(fechaCompleta("2020-02"), false);
});
test("indicadores usa límites COVID inclusivos y alias", () => {
  assert.deepEqual(indicadoresTemporales({ fecha_inicio: "2020-03-16", fecha_final: "2020-06-30", fecha_emision_constancia: "2020-06-30" }), { incluye_covid: "SÍ", cert_antes_culminar: "NO" });
  assert.deepEqual(indicadoresTemporales({ fecha_inicial: "2020-07-01", fecha_final: "2020-07-02", fecha_emision: "2020-07-03" }), { incluye_covid: "NO", cert_antes_culminar: "NO" });
  assert.deepEqual(indicadoresTemporales({ fecha_inicial: "2020-07", fecha_final: "2020-07-02" }), { incluye_covid: null, cert_antes_culminar: null });
});
test("normaliza funciones, no toma evaluador, conserva raw e idempotencia", () => {
  const raw = { evaluacion: { incluye_covid: "SÍ" }, experiencias: [{ n: 1, paginas_pdf: [7], funciones_similares: ["A", "B"], funciones_fuente: { texto: "Supervisión de campo", pagina_pdf: 7 }, fecha_inicial: "2021-01-01", fecha_final: "2021-02-01" }] };
  const antes = JSON.stringify(raw);
  const r = prepararProfesional(raw, 2);
  assert.equal(JSON.stringify(raw), antes);
  assert.equal(r.profesional.experiencias[0].funciones_similares, "A; B");
  assert.equal(r.profesional.experiencias[0].incluye_covid, "NO");
  assert.deepEqual(prepararProfesional(r.profesional, 2), r);
});
test("tipo inválido se vuelve null y deja revisión con original", () => {
  const r = prepararProfesional({ experiencias: [{ n: 3, funciones_similares: { x: 1 } }] }, 1);
  assert.equal(r.profesional.experiencias[0].funciones_similares, null);
  assert.equal(r.revisiones[0].n_experiencia, 3);
  assert.match(r.revisiones[0].motivo, /original=/);
});
test("emisión estrictamente anterior al fin es SÍ", () => {
  assert.equal(indicadoresTemporales({ fecha_inicial: "2021-01-01", fecha_final: "2021-01-03", fecha_emision: "2021-01-02" }).cert_antes_culminar, "SÍ");
});
test("inicio inválido no permite calcular COVID pero emisión y fin sí son comparables", () => {
  assert.deepEqual(indicadoresTemporales({ fecha_inicial: "2021-02-30", fecha_final: "2021-03-01", fecha_emision: "2021-02-01" }), { incluye_covid: null, cert_antes_culminar: "SÍ" });
});
test("fuente con evento equivocado reemplaza solo la fecha afectada", () => {
  const e = { n: 1, fecha_inicial: "2021-01-01", fecha_final: "2021-02-01", fechas_fuente: { fecha_inicial: { valor: "2021-01-01", evento: "firma_contrato", pagina_pdf: 4, texto: "Firmado el 01/01/2021" } } };
  const r = prepararProfesional({ experiencias: [e] }, 1);
  assert.match(r.profesional.experiencias[0].fecha_inicial, /^POR VERIFICAR/);
  assert.equal(r.profesional.experiencias[0].fecha_final, "2021-02-01");
  assert.equal(r.periodosInciertos[0], 1);
  assert.match(r.profesional.experiencias[0].observaciones, /Firmado/);
  assert.ok(r.avisos.some(a => a.severidad === "warning"));
});
test("rótulo ÍTEM de la fuente sin ítem en proyecto deja revisión", () => {
  const r = prepararProfesional({ experiencias: [{ n: 2, proyecto: "Servicio general", proyecto_fuente: { texto: "ÍTEM   N° 03 — Servicio", pagina_pdf: 8 } }] }, 1);
  assert.equal(r.revisiones.some(x => x.campo === "proyecto"), true);
  assert.match(r.profesional.experiencias[0].observaciones, /fuente en página 8/);
});
test("ITEM sin fuente no genera falso positivo", () => {
  const r = prepararProfesional({ experiencias: [{ n: 2, proyecto: "ITEM 03 — Servicio" }] }, 1);
  assert.equal(r.revisiones.length, 0);
});
test("ITEM ya presente en proyecto no genera falso positivo", () => {
  const r = prepararProfesional({ experiencias: [{ n: 2, proyecto: "ITEM 03 — Servicio", proyecto_fuente: { texto: "ITEM 03 — Servicio", pagina_pdf: 8 } }] }, 1);
  assert.equal(r.revisiones.length, 0);
});
test("null se conserva y array se une sin inventar", () => {
  const r = prepararProfesional({ experiencias: [{ n: 1, funciones_similares: null }, { n: 2, paginas_pdf: [3], funciones_similares: ["A", "B"], funciones_fuente: { texto: "Funciones", pagina_pdf: 3 } }] }, 1);
  assert.equal(r.profesional.experiencias[0].funciones_similares, null);
  assert.equal(r.profesional.experiencias[1].funciones_similares, "A; B");
});
test("función legacy sin fuente queda pendiente y conserva literal", () => {
  const r = prepararProfesional({ experiencias: [{ n: 2, paginas_pdf: [6], funciones_similares: "obra" }] }, 1);
  assert.equal(r.profesional.experiencias[0].funciones_similares, null);
  assert.match(r.profesional.experiencias[0].observaciones, /obra/);
  assert.equal(r.revisiones[0].pagina_pdf, 6);
});
test("fuente de funciones con página no incluida no valida", () => {
  const r = prepararProfesional({ experiencias: [{ n: 2, paginas_pdf: [6], funciones_similares: "obra", funciones_fuente: { texto: "texto", pagina_pdf: 7 } }] }, 1);
  assert.equal(r.profesional.experiencias[0].funciones_similares, null);
});
test("input profundamente inmutable", () => {
  const raw = { experiencias: [{ n: 1, observaciones: ["previa"], proyecto_fuente: { texto: "ÍTEM 4", pagina_pdf: 1 }, proyecto: "Otro" }] };
  const antes = JSON.stringify(raw); prepararProfesional(raw, 1); assert.equal(JSON.stringify(raw), antes);
  const legado = prepararProfesional({ experiencias: [{ n: 1, fecha_inicio: "POR VERIFICAR (ilegible)", notas: ["Emisor no legible"], funciones_similares: "Supervisó" }] }, 1);
  assert.match(legado.profesional.experiencias[0].observaciones, /Emisor no legible/);
  assert.deepEqual(legado.periodosInciertos, [1]);
});
test("repetición sobre fecha preparada no duplica revisión ni nota", () => {
  const raw = { experiencias: [{ n: 1, fecha_inicial: "2021-01-01", fecha_final: "2021-02-01", fechas_fuente: { fecha_inicial: { valor: "2021-01-01", evento: "orden_servicio", texto: "Orden", pagina_pdf: 1 } } }] };
  const una = prepararProfesional(raw, 1), dos = prepararProfesional(una.profesional, 1);
  assert.deepEqual(dos.profesional, una.profesional);
  assert.deepEqual(dos.periodosInciertos, una.periodosInciertos);
  assert.equal((dos.profesional.experiencias[0].observaciones.match(/fuente=/g) || []).length, 1);
  const declarado = prepararProfesional({ experiencias: [{ n: 1, fecha_final: "POR VERIFICAR (solo término de obra)", fechas_fuente: { fecha_final: { valor: "2017-05-30", texto: "TÉRMINO DE OBRA: 30 mayo 2017", evento: "fin_obra", pagina_pdf: 286 } } }] }, 1);
  assert.match(declarado.profesional.experiencias[0].observaciones, /2017-05-30/);
  assert.match(declarado.profesional.experiencias[0].observaciones, /TÉRMINO DE OBRA/);
});
