"use strict";
/**
 * Tests OFFLINE del candado 1:1 evaluador ↔ profesionales (#45-L3).
 * Correr: node --test skill/scripts/
 *
 * Reproducen lo que pasó el 26-jul en dos corridas reales del mismo día:
 *   1. el evaluador entregó los veredictos CORRIDOS +1 (cada profesional recibió
 *      el del siguiente y el ÚLTIMO se quedó sin nada),
 *   2. el evaluador no entregó NADA.
 * En ambas el consolidador caía a `{}` / `[]` en silencio y el espejo salía con
 * las columnas de juicio en null — válido contra el schema, mudo para el
 * evaluador humano. Los tests exigen que ahora GRITE, y que en el caso sano NO
 * grite (un candado ruidoso se ignora y deja de servir).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const { auditarEvaluacion, normalizarEval, main } = require("./consolidar_espejo");

// ── el caso real: 3 profesionales de un mismo concurso ──────────────────────
const HECHOS = [
  { n_prof: 1, cargo: "JEFE DE SUPERVISIÓN", n_experiencias: 2 },
  { n_prof: 2, cargo: "ESPECIALISTA EN ESTRUCTURAS", n_experiencias: 3 },
  { n_prof: 3, cargo: "ESPECIALISTA EN ARQUITECTURA", n_experiencias: 1 },
];
const evalDe = (i, cumple) => ({ cumple, total: { dias: 100 }, anios_adicionales: 1 });
const expsDe = (k) => Array.from({ length: k }, (_, j) => ({ n: j + 1, dias: 30 }));

const SANA = {
  profesionales_eval: {
    1: evalDe(1, "CUMPLE — acredita la jefatura de supervisión exigida"),
    2: evalDe(2, "CUMPLE — acredita como especialista en estructuras"),
    3: evalDe(3, "CUMPLE — acredita como especialista en arquitectura"),
  },
  experiencias_eval: { 1: expsDe(2), 2: expsDe(3), 3: expsDe(1) },
};

const tipos = (avisos) => avisos.map((a) => a.tipo);
const criticos = (avisos) => avisos.filter((a) => a.severidad === "critical");
const de = (avisos, tipo) => avisos.find((a) => a.tipo === tipo);

// ── 1 · caso sano: silencio ─────────────────────────────────────────────────
test("caso sano (1:1 completo) → ningún aviso", () => {
  assert.deepStrictEqual(auditarEvaluacion(SANA, HECHOS), [],
    "el candado no debe gritar cuando la evaluación cubre a todos");
});

test("caso sano con un profesional sin experiencias → sigue en silencio", () => {
  const hechos = [{ n_prof: 1, cargo: "JEFE DE SUPERVISIÓN", n_experiencias: 0 }];
  const ev = { profesionales_eval: { 1: evalDe(1, "NO CUMPLE — no presenta constancias") },
               experiencias_eval: {} };
  assert.deepStrictEqual(auditarEvaluacion(ev, hechos), []);
});

// ── 2 · corrimiento: falta EXACTAMENTE el último ────────────────────────────
test("corrimiento (+1): falta el ÚLTIMO profesional → critical que lo nombra", () => {
  const ev = {
    profesionales_eval: {
      1: evalDe(1, "CUMPLE — acredita como especialista en estructuras"),  // el de n_prof 2
      2: evalDe(2, "CUMPLE — acredita como especialista en arquitectura"), // el de n_prof 3
    },
    experiencias_eval: { 1: expsDe(3), 2: expsDe(1) },
  };
  const avisos = auditarEvaluacion(ev, HECHOS);
  const a = de(avisos, "evaluacion_corrida");
  assert.ok(a, `esperaba evaluacion_corrida, hubo: ${tipos(avisos).join(", ")}`);
  assert.strictEqual(a.severidad, "critical");
  assert.match(a.mensaje, /CORRIMIENTO/, "debe decirlo con esas palabras");
  assert.match(a.mensaje, /n_prof 3/, "debe nombrar al profesional que quedó sin veredicto");
});

test("corrimiento: además descuadran las experiencias y el veredicto es ajeno", () => {
  const ev = {
    profesionales_eval: {
      1: evalDe(1, "CUMPLE — acredita como especialista en estructuras"),
      2: evalDe(2, "CUMPLE — acredita como especialista en arquitectura"),
    },
    experiencias_eval: { 1: expsDe(3), 2: expsDe(1) },
  };
  const avisos = auditarEvaluacion(ev, HECHOS);
  // n_prof 1 declaró 2 experiencias y recibió las 3 del siguiente
  const d = de(avisos, "evaluacion_experiencias_descuadre");
  assert.ok(d, `esperaba descuadre, hubo: ${tipos(avisos).join(", ")}`);
  assert.match(d.mensaje, /3 experiencia\(s\) evaluada\(s\)/);
  assert.match(d.mensaje, /declaró 2/);
  // y el veredicto del especialista en estructuras habla de ARQUITECTURA (del 3)
  const aj = avisos.filter((a) => a.tipo === "veredicto_ajeno");
  assert.ok(aj.length >= 1, "el veredicto ajeno debe detectarse");
  assert.match(aj[0].mensaje, /profesional 2/);
  assert.match(aj[0].mensaje, /ARQUITECTURA \(del profesional 3\)/);
  // El profesional 1 ("JEFE DE SUPERVISIÓN") NO se detecta por esta vía: su cargo
  // no tiene ningún token de especialidad (jefe/supervisión son genéricos de rol),
  // así que no hay con qué contrastar. Lo atrapa el descuadre de experiencias.
  assert.ok(!aj.some((a) => /profesional 1/.test(a.mensaje)));
});

// ── 3 · ausencia total ──────────────────────────────────────────────────────
test("el evaluador no entregó NADA → critical evaluacion_ausente", () => {
  for (const ev of [{}, { profesionales_eval: {} }, { profesionales_eval: {}, experiencias_eval: {} }]) {
    const avisos = auditarEvaluacion(ev, HECHOS);
    const a = de(avisos, "evaluacion_ausente");
    assert.ok(a, `esperaba evaluacion_ausente, hubo: ${tipos(avisos).join(", ")}`);
    assert.strictEqual(a.severidad, "critical");
    assert.match(a.mensaje, /valida contra el schema/, "debe explicar por qué pasa desapercibido");
    // y una queja por cada profesional que se quedó sin sus experiencias evaluadas
    assert.strictEqual(avisos.filter((x) => x.tipo === "evaluacion_experiencias_ausentes").length, 3);
  }
});

test("un objeto vacío NO cuenta como veredicto", () => {
  const ev = { profesionales_eval: { 1: {}, 2: SANA.profesionales_eval[2], 3: SANA.profesionales_eval[3] },
               experiencias_eval: SANA.experiencias_eval };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_incompleta");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /n_prof 1/);
});

// El hueco que la versión anterior dejaba pasar: la ENTRADA existe (y con varias
// claves), pero el veredicto viene vacío. Produce el mismo espejo que no mandar
// nada, así que el candado tiene que contarlo como ausente.
test("entradas presentes pero SIN veredicto (cumple null) → grita igual que si faltaran", () => {
  const hueco = (i) => ({ n_prof: i, cumple: null, total: {}, anios_adicionales: null });
  const ev = { profesionales_eval: { 1: hueco(1), 2: hueco(2), 3: hueco(3) },
               experiencias_eval: SANA.experiencias_eval };
  const avisos = auditarEvaluacion(ev, HECHOS);
  const a = de(avisos, "evaluacion_ausente");
  assert.ok(a, `esperaba evaluacion_ausente, hubo: ${tipos(avisos).join(", ")}`);
  assert.strictEqual(a.severidad, "critical");
  assert.match(a.mensaje, /`cumple` vacío/, "debe decir que llegaron pero vacíos, no que faltan");
});

test("un solo veredicto vacío entre veredictos buenos → critical que lo nombra", () => {
  const ev = { profesionales_eval: { ...SANA.profesionales_eval, 2: { n_prof: 2, cumple: "   ", total: { dias: 100 } } },
               experiencias_eval: SANA.experiencias_eval };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_incompleta");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /n_prof 2/);
  assert.match(a.mensaje, /`cumple` vacío/);
});

test("experiencias presentes pero sin NINGÚN campo de juicio → critical", () => {
  const ev = { profesionales_eval: SANA.profesionales_eval,
               experiencias_eval: { 1: [{ n: 1 }, { n: 2 }], 2: expsDe(3), 3: expsDe(1) } };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_experiencias_vacias");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /n=1, 2/);
});

// ── 4 · cobertura de experiencias ───────────────────────────────────────────
test("experiencias_eval con menos entradas → avisa con AMBOS números", () => {
  const ev = { profesionales_eval: SANA.profesionales_eval,
               experiencias_eval: { 1: expsDe(2), 2: expsDe(2), 3: expsDe(1) } };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_experiencias_descuadre");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /entregó 2 experiencia\(s\) evaluada\(s\)/);
  assert.match(a.mensaje, /declaró 3/);
});

test("experiencias_eval ausente para un profesional con experiencias → critical", () => {
  const ev = { profesionales_eval: SANA.profesionales_eval,
               experiencias_eval: { 1: expsDe(2), 3: expsDe(1) } };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_experiencias_ausentes");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /declaró 3 experiencia\(s\)/);
});

// ── 4b · la LLAVE DE JOIN: el conteo cuadra y aun así no se pega nada ───────
// `main` pega con `eeByN[x.n]`. Mirar solo `ee.length` deja pasar los tres casos
// de abajo, que producen el espejo COMPLETAMENTE en null igual que no evaluar.
test("conteo correcto pero SIN campo `n` → critical (todo colapsa en la misma clave)", () => {
  const sinN = (k) => Array.from({ length: k }, () => ({ dias: 30 }));
  const ev = { profesionales_eval: SANA.profesionales_eval,
               experiencias_eval: { 1: sinN(2), 2: sinN(3), 3: sinN(1) } };
  const avisos = auditarEvaluacion(ev, HECHOS);
  const a = de(avisos, "evaluacion_n_ausente");
  assert.ok(a, `esperaba evaluacion_n_ausente, hubo: ${tipos(avisos).join(", ")}`);
  assert.strictEqual(a.severidad, "critical");
  assert.strictEqual(avisos.filter((x) => x.tipo === "evaluacion_n_ausente").length, 3,
    "uno por profesional: los tres pierden el 100% de sus juicios");
  // y además ninguna fila real quedó cubierta
  assert.ok(de(avisos, "evaluacion_n_sin_juicio"));
});

test("conteo correcto con los `n` equivocados → critical en las dos direcciones", () => {
  const conN = (...ns) => ns.map((n) => ({ n, dias: 30 }));
  const ev = { profesionales_eval: SANA.profesionales_eval,
               experiencias_eval: { 1: conN(5, 6), 2: conN(7, 8, 9), 3: conN(4) } };
  const avisos = auditarEvaluacion(ev, HECHOS);
  assert.strictEqual(avisos.filter((x) => x.tipo === "evaluacion_experiencias_descuadre").length, 0,
    "el conteo cuadra: el candado viejo se callaba justo aquí");
  const des = de(avisos, "evaluacion_n_desalineado");
  assert.ok(des && des.severidad === "critical");
  assert.match(des.mensaje, /cita n=5, 6/);
  assert.match(des.mensaje, /filas de este profesional son n=1, 2/);
  const sin = de(avisos, "evaluacion_n_sin_juicio");
  assert.ok(sin && sin.severidad === "critical");
  assert.match(sin.mensaje, /n=1, 2/);
});

test("el evaluador RENUMERA 1..N unas filas que venían 2,3,4 → critical", () => {
  // Falso negativo del check por rango: 1..3 «cabe» en el rango derivado del
  // conteo, pero ninguna de esas claves existe entre las filas crudas.
  const hechos = [{ n_prof: 1, cargo: "ESPECIALISTA EN ESTRUCTURAS", n_experiencias: 3, ns_experiencias: [2, 3, 4] }];
  const ev = { profesionales_eval: { 1: evalDe(1, "CUMPLE — acredita estructuras") },
               experiencias_eval: { 1: [{ n: 1, dias: 30 }, { n: 2, dias: 30 }, { n: 3, dias: 30 }] } };
  const avisos = auditarEvaluacion(ev, hechos);
  assert.match(de(avisos, "evaluacion_n_desalineado").mensaje, /cita n=1\b/);
  assert.match(de(avisos, "evaluacion_n_sin_juicio").mensaje, /n=4/);
});

test("crudo NO contiguo (n=3,4,5) copiado FIELMENTE → silencio (no es falso positivo)", () => {
  const hechos = [{ n_prof: 1, cargo: "ESPECIALISTA EN ESTRUCTURAS", n_experiencias: 3, ns_experiencias: [3, 4, 5] }];
  const ev = { profesionales_eval: { 1: evalDe(1, "CUMPLE — acredita estructuras") },
               experiencias_eval: { 1: [{ n: 3, dias: 30 }, { n: 4, dias: 30 }, { n: 5, dias: 30 }] } };
  assert.deepStrictEqual(auditarEvaluacion(ev, hechos), [],
    "el candado coteja contra los n REALES, no contra un rango 1..N inventado");
});

test("experiencias_eval con n fuera de rango o repetido → critical", () => {
  const ev = {
    profesionales_eval: SANA.profesionales_eval,
    experiencias_eval: {
      1: [{ n: 2 }, { n: 3 }],            // el profesional 1 solo tiene 1..2
      2: [{ n: 1 }, { n: 1 }, { n: 2 }],  // n repetido: al indexar sobrevive el último
      3: expsDe(1),
    },
  };
  const avisos = auditarEvaluacion(ev, HECHOS);
  assert.match(de(avisos, "evaluacion_n_desalineado").mensaje, /n=3/);
  assert.match(de(avisos, "evaluacion_n_duplicado").mensaje, /n=1/);
});

test("veredicto para un n_prof que no existe → critical", () => {
  const ev = { profesionales_eval: { ...SANA.profesionales_eval, 4: evalDe(4, "CUMPLE") },
               experiencias_eval: SANA.experiencias_eval };
  const a = de(auditarEvaluacion(ev, HECHOS), "evaluacion_sobrante");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /"4"/);
});

// ── 5 · coherencia veredicto ↔ profesional ──────────────────────────────────
test("el veredicto cita más constancias de las que existen → critical", () => {
  const ev = {
    profesionales_eval: {
      ...SANA.profesionales_eval,
      3: evalDe(3, "CUMPLE — sus 4 constancias suman 11 años como especialista en arquitectura"),
    },
    experiencias_eval: SANA.experiencias_eval,
  };
  const a = de(auditarEvaluacion(ev, HECHOS), "veredicto_incoherente");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /cita 4 constancia/);
  assert.match(a.mensaje, /solo tiene 1/);
});

test("citar un subconjunto legítimo no es crítico (y no grita si cita el total real)", () => {
  const parcial = {
    profesionales_eval: {
      ...SANA.profesionales_eval,
      2: evalDe(2, "CUMPLE — de sus 3 constancias, 2 acreditan estructuras"),
    },
    experiencias_eval: SANA.experiencias_eval,
  };
  assert.deepStrictEqual(auditarEvaluacion(parcial, HECHOS), [],
    "si el veredicto nombra el total real, los números menores son subconjuntos");

  const soloMenor = {
    profesionales_eval: {
      ...SANA.profesionales_eval,
      2: evalDe(2, "CUMPLE — 2 constancias acreditan estructuras"),
    },
    experiencias_eval: SANA.experiencias_eval,
  };
  const a = de(auditarEvaluacion(soloMenor, HECHOS), "veredicto_incoherente");
  assert.ok(a && a.severidad === "warning", "sin el total real: se avisa, pero no es crítico");
});

// Un candado que grita por redacciones legítimas se ignora, y entonces no sirve
// para nada: los números que el veredicto cita como DECLARADOS o EXIGIDOS no son
// "sus constancias" y no pueden dispararlo.
test("citar lo DECLARADO en el Anexo o lo EXIGIDO por las bases no es incoherencia", () => {
  const sanos = [
    "SÍ CUMPLE — el Anexo 16 declara 7 experiencias; solo 3 constancias están en la propuesta y acreditan estructuras",
    "NO CUMPLE — las bases exigen 5 constancias en establecimientos de salud y solo presenta 3 constancias de estructuras",
    "CUMPLE — supera el mínimo de 6 experiencias requerido; sus 3 constancias de estructuras suman 11 años",
    "CUMPLE — el cuadro resumen declara 9 periodos de estructuras y se verificaron los 3 presentados",
  ];
  for (const cumple of sanos) {
    const ev = { profesionales_eval: { ...SANA.profesionales_eval, 2: evalDe(2, cumple) },
                 experiencias_eval: SANA.experiencias_eval };
    const avisos = auditarEvaluacion(ev, HECHOS);
    assert.deepStrictEqual(avisos, [], `no debía gritar por: "${cumple}" — hubo: ${tipos(avisos).join(", ")}`);
  }
});

test("…pero un nº propio inflado sigue siendo critical", () => {
  const ev = { profesionales_eval: { ...SANA.profesionales_eval, 2: evalDe(2, "CUMPLE — sus 9 constancias acreditan estructuras") },
               experiencias_eval: SANA.experiencias_eval };
  const a = de(auditarEvaluacion(ev, HECHOS), "veredicto_incoherente");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /cita 9 constancia/);
});

test("veredicto que solo nombra la especialidad de otro → critical veredicto_ajeno", () => {
  const ev = {
    profesionales_eval: {
      ...SANA.profesionales_eval,
      2: evalDe(2, "CUMPLE — acredita 12 años como responsable de arquitectura"),
    },
    experiencias_eval: SANA.experiencias_eval,
  };
  const a = de(auditarEvaluacion(ev, HECHOS), "veredicto_ajeno");
  assert.ok(a && a.severidad === "critical");
  assert.match(a.mensaje, /ARQUITECTURA \(del profesional 3\)/);
});

test("un veredicto genérico (sin especialidades) no dispara veredicto_ajeno", () => {
  const ev = {
    profesionales_eval: {
      ...SANA.profesionales_eval,
      2: evalDe(2, "CUMPLE — 15 años 3 meses superan el mínimo exigido de 10 años"),
    },
    experiencias_eval: SANA.experiencias_eval,
  };
  assert.deepStrictEqual(tipos(auditarEvaluacion(ev, HECHOS)), []);
});

// ── 6 · forma de la salida (raíz probable del +1) ───────────────────────────
test("profesionales_eval como ARRAY sin n_prof → critical (indexar por n_prof corre +1)", () => {
  const ev = {
    profesionales_eval: [SANA.profesionales_eval[1], SANA.profesionales_eval[2], SANA.profesionales_eval[3]],
    experiencias_eval: [expsDe(2), expsDe(3), expsDe(1)],
  };
  const { PE } = normalizarEval(ev);
  assert.strictEqual(PE["1"], SANA.profesionales_eval[1], "el 1º elemento es el n_prof 1, no el 2º");
  const avisos = auditarEvaluacion(ev, HECHOS);
  assert.ok(criticos(avisos).some((a) => a.tipo === "evaluacion_forma_array"));
});

test("ARRAY con n_prof adentro → se reindexa sin perder nada (solo warning)", () => {
  const ev = {
    profesionales_eval: [
      { n_prof: 3, ...SANA.profesionales_eval[3] },
      { n_prof: 1, ...SANA.profesionales_eval[1] },
      { n_prof: 2, ...SANA.profesionales_eval[2] },
    ],
    experiencias_eval: SANA.experiencias_eval,
  };
  const { PE } = normalizarEval(ev);
  assert.match(PE["1"].cumple, /jefatura de supervisión/);
  const avisos = auditarEvaluacion(ev, HECHOS);
  assert.strictEqual(criticos(avisos).length, 0, `no debía haber críticos: ${tipos(avisos).join(", ")}`);
  assert.ok(de(avisos, "evaluacion_forma_array"));
});

test("índice desde 0 → se corrige +1 y se avisa como critical", () => {
  const ev = {
    profesionales_eval: { 0: SANA.profesionales_eval[1], 1: SANA.profesionales_eval[2], 2: SANA.profesionales_eval[3] },
    experiencias_eval: { 0: expsDe(2), 1: expsDe(3), 2: expsDe(1) },
  };
  const { PE, EE } = normalizarEval(ev);
  assert.match(PE["1"].cumple, /jefatura de supervisión/);
  assert.strictEqual(EE["2"].length, 3);
  assert.ok(criticos(auditarEvaluacion(ev, HECHOS)).some((a) => a.tipo === "evaluacion_indice_base_cero"));
});

// ── 7 · end-to-end: el aviso llega al espejo y NO se pierden datos ──────────
function taller(evaluacion) {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), "espejo-test-"));
  fs.mkdirSync(path.join(ws, "_prof"));
  const w = (rel, obj) => fs.writeFileSync(path.join(ws, rel), JSON.stringify(obj), "utf-8");
  w("bases.json", {
    metadata_concurso: { nomenclatura: "CP-02-2025", entidad: "GORE X" },
    personal_clave: HECHOS.map((h) => ({
      numero: h.n_prof, cargo: h.cargo, cargos_similares_validos: ["A", "B"],
      tiempo_minimo_experiencia: "5 años", profesiones_aceptadas: ["Ingeniero Civil"],
    })),
  });
  w("roster_bundles.json", {
    roster: HECHOS.map((h) => ({ n_prof: h.n_prof, cargo: h.cargo, nombre: `PROF ${h.n_prof}` })),
    postor: { postor: "CONSORCIO X", formularios: [{ anexo: "1", documento: "Declaración" }],
              experiencia_postor: [{ n: 1, cliente: "GORE X", monto: 100 }] },
  });
  w("evaluacion.json", evaluacion);
  for (const h of HECHOS) {
    w(path.join("_prof", `profesional_0${h.n_prof}.json`), {
      profesional: { n_prof: h.n_prof, cargo: h.cargo, nombre: `PROF ${h.n_prof}` },
      experiencias: Array.from({ length: h.n_experiencias }, (_, j) => ({
        n: j + 1, entidad_emisora: "GORE X", proyecto: `OBRA ${j + 1}`,
        fecha_inicial: "2019-01-01", fecha_final: "2020-01-01", folio: 100 + j,
      })),
    });
  }
  return ws;
}

test("e2e · sin evaluación: el espejo se escribe COMPLETO y el aviso crítico va dentro", () => {
  const ws = taller({});
  const espejo = main(ws);
  const guardado = JSON.parse(fs.readFileSync(path.join(ws, "espejo.json"), "utf-8"));

  // no se borró nada: los hechos crudos siguen ahí
  assert.strictEqual(guardado.profesionales.length, 3);
  assert.strictEqual(guardado.profesionales.reduce((s, p) => s + p.experiencias.length, 0), 6);
  assert.strictEqual(guardado.profesionales[0].experiencias[0].proyecto, "OBRA 1");
  // …pero el hueco de la evaluación quedó gritado en observaciones_claude
  const crit = guardado.observaciones_claude.filter((o) => o.severidad === "critical");
  assert.ok(crit.some((o) => o.tipo === "evaluacion_ausente"),
    `esperaba evaluacion_ausente en el espejo, hubo: ${tipos(guardado.observaciones_claude).join(", ")}`);
  assert.strictEqual(espejo.profesionales[0].cumple, null, "sin evaluador, el veredicto es null (no inventado)");
  fs.rmSync(ws, { recursive: true, force: true });
});

test("e2e · evaluación sana: ningún aviso crítico en el espejo", () => {
  const ws = taller(SANA);
  const espejo = main(ws);
  const crit = espejo.observaciones_claude.filter((o) => o.severidad === "critical");
  assert.deepStrictEqual(crit, [], `no debía haber críticos: ${JSON.stringify(crit)}`);
  assert.match(espejo.profesionales[1].cumple, /estructuras/);
  fs.rmSync(ws, { recursive: true, force: true });
});

// ── 8 · el gate: si nadie consume los críticos, el candado es decoración ─────
// Se corre el CLI DE VERDAD (proceso aparte, offline) porque lo que se está
// probando es justamente el contrato con quien lo invoca: primera línea, última
// línea y exit code.
const cli = (ws) => {
  const r = spawnSync(process.execPath, [path.join(__dirname, "consolidar_espejo.js"), ws], { encoding: "utf-8" });
  return { status: r.status, out: (r.stdout || "").trim() };
};

test("cli · con un crítico: exit code 1 y en ninguna línea dice «OK»", () => {
  const ws = taller({});           // el evaluador no entregó nada
  const { status, out } = cli(ws);
  assert.strictEqual(status, 1, `el consolidador debe FALLAR con críticos:\n${out}`);
  assert.ok(!/^OK/m.test(out), `ninguna línea puede empezar con «OK»:\n${out}`);
  const lineas = out.split(/\r?\n/);
  assert.match(lineas[0], /CRÍTICO/, "los críticos van PRIMERO, no debajo de un OK");
  assert.match(lineas[lineas.length - 1], /consolida de nuevo|INCOMPLETO/,
    "la última línea tiene que ser la instrucción de repetir, no un resumen feliz");
  assert.match(out, /INCOMPLETO/);
  assert.match(out, /NO lo subas/);
  // el espejo se escribe igual: los hechos crudos no se pierden por el hueco
  assert.ok(fs.existsSync(path.join(ws, "espejo.json")));
  fs.rmSync(ws, { recursive: true, force: true });
});

test("cli · corrida sana: exit code 0 y la primera línea es «OK»", () => {
  const ws = taller(SANA);
  const { status, out } = cli(ws);
  assert.strictEqual(status, 0, `una corrida sana no puede fallar:\n${out}`);
  assert.match(out.split(/\r?\n/)[0], /^OK · espejo escrito/);
  assert.ok(!/CRÍTICO/.test(out));
  fs.rmSync(ws, { recursive: true, force: true });
});
