"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { normalizarBasesCriticas, auditarFechas, totalPostorDesdeBases, conflictoEventoFecha } = require("./entradas_criticas");

function basesValidas() {
  return {
    experiencia_postor_requisito: {
      estado: "encontrado", monto: 1250000, moneda: "PEN",
      fuente: { pagina_pdf: 27, texto: "Experiencia mínima acumulada de S/ 1 250 000,00." },
    },
    personal_clave: [{ numero: 1, factor_a_aplica: true }],
    reglas_evaluacion: { factor_a: {
      umbral_adicional_requerido: 6, unidad_umbral_adicional: "meses", folio: 31,
      tramos: [
        { desde_porcentaje: 50, desde_inclusivo: true, hasta_porcentaje: 100, hasta_inclusivo: true, puntaje: 40 },
        { desde_porcentaje: 0, desde_inclusivo: false, hasta_porcentaje: 50, hasta_inclusivo: false, puntaje: 20 },
        { desde_porcentaje: 0, desde_inclusivo: true, hasta_porcentaje: 0, hasta_inclusivo: true, puntaje: 0 },
      ],
    } },
  };
}
const criticos = resultado => resultado.avisos.filter(a => a.severidad === "critical");

test("mínimo de las bases prevalece sobre suma, cuantía y evaluador", () => {
  const b = basesValidas();
  b.metadata_concurso = { cuantia: 9000000 };
  const r = normalizarBasesCriticas(b);
  assert.deepEqual(criticos(r), []);
  const total = totalPostorDesdeBases(r.requisito, { monto_requerido: 1, requerido: 2, monto_confirmado: "2000000.00" });
  assert.equal(total.monto_requerido, "1250000.00");
  assert.equal(total.requerido, undefined);
  assert.equal(total.monto_confirmado, "2000000.00");
  assert.equal(total.requisito_fuente.pagina_pdf, 27);
});

test("ausencia de mínimo no se sustituye por cuantía ni cero", () => {
  const r = normalizarBasesCriticas({ metadata_concurso: { cuantia: 1500000 } });
  assert.ok(criticos(r).some(a => a.tipo === "entrada_minimo_postor"));
  assert.equal(totalPostorDesdeBases(r.requisito, { minimo: 1 }).monto_requerido, null);
});

test("no aplica requiere sustento; no encontrado no significa no aplica", () => {
  for (const estado of ["no_aplica", "no_encontrado"]) {
    const b = basesValidas();
    b.experiencia_postor_requisito = { estado, monto: null, moneda: null, fuente: { pagina_pdf: 27, texto: "Revisión de las bases." } };
    const r = normalizarBasesCriticas(b);
    assert.equal(criticos(r).length, estado === "no_aplica" ? 0 : 1);
  }
  const b = basesValidas();
  b.experiencia_postor_requisito = { estado: "no_aplica" };
  assert.ok(criticos(normalizarBasesCriticas(b)).length);
});

test("monto ambiguo, negativo o divisa distinta no se convierte a soles", () => {
  for (const cambio of [{ monto: "1,25 millones" }, { monto: -1 }, { monto: true }, { moneda: "USD" }]) {
    const b = basesValidas(); Object.assign(b.experiencia_postor_requisito, cambio);
    const r = normalizarBasesCriticas(b);
    assert.ok(criticos(r).length);
    assert.equal(r.requisito.monto_requerido, null);
  }
});

test("Factor A: unidades explícitas y equivalencia sin adivinar prosa", () => {
  for (const [unidad, cantidad, esperado] of [["meses", 6, 180], ["años", 2, 730], ["días", 45, 45], ["meses", 12, 360]]) {
    const b = basesValidas();
    Object.assign(b.reglas_evaluacion.factor_a, { umbral_adicional_requerido: cantidad, unidad_umbral_adicional: unidad });
    const r = normalizarBasesCriticas(b);
    assert.equal(r.reglas.factor_a.dias_adicionales_requeridos, esperado);
    assert.deepEqual(criticos(r), []);
  }
});

test("Factor A con condición solo en prosa no genera un tramo universal", () => {
  const b = basesValidas();
  b.reglas_evaluacion.factor_a.tramos = [{ condicion: "La mitad o más", puntaje: 40 }];
  const r = normalizarBasesCriticas(b);
  assert.ok(criticos(r).some(a => a.tipo === "entrada_factor_a"));
  assert.equal(r.reglas.factor_a, null);
});

test("Factor A rechaza huecos, solapes, bordes ausentes y unidades contradictorias", () => {
  for (const cambiar of [
    f => { delete f.tramos[0].desde_inclusivo; },
    f => { f.tramos[1].hasta_inclusivo = true; },
    f => { f.tramos[0].desde_porcentaje = 60; },
    f => { f.dias_adicionales_requeridos = 365; },
    f => { f.unidad_umbral_adicional = "semanas sin equivalencia"; },
  ]) {
    const b = basesValidas(); cambiar(b.reglas_evaluacion.factor_a);
    assert.ok(criticos(normalizarBasesCriticas(b)).some(a => a.tipo === "entrada_factor_a"));
  }
});

test("Factor A en array se recupera, no lo tapa un false del fallback", () => {
  const b = basesValidas();
  b.factores_evaluacion = [{ codigo: "A", ...b.reglas_evaluacion.factor_a }];
  delete b.reglas_evaluacion.factor_a;
  assert.equal(normalizarBasesCriticas(b).reglas.factor_a.dias_adicionales_requeridos, 180);
});

function experiencia() {
  return {
    n: 1, paginas_pdf: [47], fecha_inicial: "2021-02-01", fecha_final: "2022-08-18",
    fechas_fuente: {
      fecha_inicial: { valor: "2021-02-01", pagina_pdf: 47, evento: "inicio_servicio", texto: "Periodo: del 01/02/2021", metodo: "visual" },
      fecha_final: { valor: "2022-08-18", pagina_pdf: 47, evento: "fin_servicio", texto: "al 18/08/2022", metodo: "visual" },
    },
  };
}
test("fechas cotejadas no generan alertas", () => assert.deepEqual(auditarFechas([experiencia()], 1), []));
test("fecha plausible distinta de su cotejo visual bloquea, no se autocorrige", () => {
  const e = experiencia(); e.fecha_final = "2022-08-13";
  assert.ok(auditarFechas([e], 1).some(a => a.tipo === "entrada_fecha_discrepante"));
  assert.equal(e.fecha_final, "2022-08-13");
});
test("fecha de orden, emisión o firma no es inicio del desempeño", () => {
  for (const evento of ["orden_servicio", "emision", "firma_contrato"]) {
    const e = experiencia(); e.fechas_fuente.fecha_inicial.evento = evento;
    assert.ok(auditarFechas([e], 1).some(a => a.tipo === "entrada_fecha_evento"));
  }
});
test("fecha ausente o parcial explícita se conserva sin fabricar día", () => {
  const e = experiencia();
  e.fecha_inicial = "POR VERIFICAR — solo figura fecha de la orden";
  e.fecha_final = "2022-08 (sin día)";
  delete e.fechas_fuente;
  assert.deepEqual(auditarFechas([e], 1), []);
});
test("solo OCR, página ajena, calendario imposible o periodo invertido no pasan", () => {
  for (const cambiar of [
    e => { delete e.fechas_fuente; },
    e => { e.fechas_fuente.fecha_final.metodo = "ocr"; },
    e => { e.fechas_fuente.fecha_final.pagina_pdf = 48; },
    e => { e.fecha_final = "2022-02-30"; },
    e => { e.fecha_final = "2020-08-18"; },
  ]) {
    const e = experiencia(); cambiar(e);
    assert.ok(auditarFechas([e], 1).some(a => a.severidad === "critical"));
  }
});

test("el literal de término o inicio de obra contradice el evento personal aunque el enum mienta", () => {
  assert.match(conflictoEventoFecha({ evento: "orden_servicio", texto: "Periodo: 01/02/2021" }, "fecha_inicial"), /evento declarado/);
  assert.match(conflictoEventoFecha({ texto: "TERMINO DE OBRA:31 julio 2019" }, "fecha_final"), /evento de la obra/);
  assert.match(conflictoEventoFecha({ texto: "TÉRMINO DE LA OBRA:30 de mayo 2017" }, "fecha_final"), /evento de la obra/);
  assert.match(conflictoEventoFecha({ texto: "Inicio de obra: 04/02/2018" }, "fecha_inicial"), /evento de la obra/);
  const e = experiencia();
  e.fechas_fuente.fecha_final.texto = "TÉRMINO DE LA OBRA:30 de mayo 2017";
  assert.ok(auditarFechas([e], 1).some(a => a.tipo === "entrada_fecha_evento_literal" && a.severidad === "critical"));
});

test("periodo personal explícito no se rechaza por mencionar la obra", () => {
  for (const texto of [
    "Prestó servicios en la obra del 01/02/2021 al 18/08/2022",
    "El profesional laboró en la obra desde 01/02/2021 hasta 18/08/2022",
  ]) {
    assert.equal(conflictoEventoFecha({ texto }, "fecha_inicial"), null);
    assert.equal(conflictoEventoFecha({ texto }, "fecha_final"), null);
  }
});

test("firma, emisión u orden no acreditan inicio/fin cuando son la única referencia", () => {
  for (const texto of ["Fecha de firma: 01/02/2021", "Fecha de emisión: 18/08/2022", "Orden de servicio: 01/02/2021"]) {
    assert.match(conflictoEventoFecha({ texto }, "fecha_inicial"), /no acredita/);
    assert.match(conflictoEventoFecha({ texto }, "fecha_final"), /no acredita/);
  }
  assert.equal(conflictoEventoFecha({ texto: "Constancia emitida; prestó servicios del 01/02/2021 al 18/08/2022" }, "fecha_final"), null);
});

test("solo rótulos de acto fechados disparan y las menciones incidentales no", () => {
  assert.match(conflictoEventoFecha({ texto: "Fin de obra: 31/07/2019" }, "fecha_final"), /evento de la obra/);
  assert.match(conflictoEventoFecha({ texto: "Fecha de emisión: 31/07/2019" }, "fecha_final"), /no acredita/);
  assert.equal(conflictoEventoFecha({ texto: "Fin del servicio de supervisión de la obra Mejoramiento por orden N°12" }, "fecha_final"), null);
});

test("término de obra junto a periodo personal queda en ambigüedad", () => {
  const motivo = conflictoEventoFecha({ texto: "Término de obra: 31/07/2019.\nPrestó servicios del 01/02/2018 al 18/08/2019" }, "fecha_final");
  assert.match(motivo, /ambigüedad/);
  assert.match(motivo, /evento de la obra/);
  assert.match(motivo, /periodo personal/);
});

module.exports = { basesValidas, experiencia };
