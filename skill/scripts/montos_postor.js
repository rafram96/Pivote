"use strict";
/**
 * montos_postor.js — rescate DETERMINÍSTICO de los montos de la experiencia del
 * postor (requisito 3.4, de ADMISIÓN) desde el índice OCR.
 *
 * POR QUÉ EXISTE (#62). `agent-propuesta-mapa` devolvió `monto: null` en los 3
 * contratos del postor de divino_nino (job ae368cb5dafa) **teniendo los montos
 * en el OCR de los folios que él mismo citó**. No fue desobediencia: el prompt
 * le manda ACOTAR ese bloque ("nadie la lea a fondo", "sin abrir cada
 * constancia") porque leerlo por VISIÓN costaba ~80% de la corrida. Con Camino A
 * el texto ya está en disco y leerlo cuesta cero — este script recupera el dato
 * SIN que ningún agente abra las páginas, así el ACOTAR sigue vigente.
 *
 * LA TRAMPA, medida en los documentos reales: el monto más grande de la página
 * casi nunca es el que acredita. Ejemplo literal (folio 77):
 *
 *     Monto de Contrato de Consultoria  : S/23,467.84     ← ESTE acredita
 *     Monto de Ejecucion de Obra        : S/939,152.16    ← la obra supervisada
 *     Monto de Adicional de Obra N° 01  : S/63,249.46
 *     Monto Total de Ejecucion de Obra  : S/1'000,237.56  ← el más grande, y el más falso
 *
 * En una consultoría de obra (supervisión) lo que acredita al postor es el monto
 * DEL CONTRATO DE CONSULTORÍA, no el de la obra que supervisó. Por eso la
 * selección es por ETIQUETA, nunca por magnitud. Los adelantos (típicamente 10%
 * del contractual: 211,029.00 → 21,102.90) y los adicionales/deductivos se
 * descartan explícitamente.
 *
 * CONTRATO DE SALIDA: este script **propone con evidencia**, no rellena a ciegas.
 * Cada monto viaja con página, etiqueta y la línea literal de donde salió, y
 * cuando hay ambigüedad NO elige: deja los candidatos a la vista. Misma regla que
 * el resto del sistema — abstenerse cuesta minutos, un dato inventado cuesta el
 * producto (ADR-005).
 *
 * Uso:
 *   node scripts/montos_postor.js <carpeta_analisis> [--escribir]
 *     lee  <carpeta>/roster_bundles.json  +  <carpeta>/_ocr_propuesta/pNNNN.txt
 *     imprime el informe; con --escribir actualiza roster_bundles.json in situ.
 */

const fs = require("fs");
const path = require("path");

// ── Montos: solo con FORMA de monto (miles agrupados o ≥6 dígitos). Nunca un
// "90" suelto — misma lección que el parser de la oferta económica (#52).
// Se admite el separador de millón con apóstrofe que usan los documentos
// peruanos ("1'000,237.56") y el OCR suele ensuciar con espacios.
// `[,\s]\s?` porque el OCR parte los grupos de miles con coma+espacio
// ("S/23, 467.84" — literal del folio 77).
const RE_MONTO =
  /(?:S\/\.?|soles)\s*([0-9]{1,3}(?:['’]\s?[0-9]{3})?(?:[,\s]\s?[0-9]{3})+(?:\.[0-9]{2})?|[0-9]{6,}(?:\.[0-9]{2})?)/gi;

// Etiquetas que ACREDITAN al postor (monto del contrato que él firmó).
// `_S` = separador tolerante al OCR: los escaneos meten puntos, comas y basura
// entre palabras ("CLÁUSULA TERCERA: MONTO. CONTRACTUAL" — literal del folio 48).
// La primera alternativa es el boilerplate estándar de los contratos públicos
// peruanos ("El monto total del presente contrato asciende a S/ …"), que es
// donde vive el dato en 2 de los 3 contratos medidos.
const _S = "[\\s.,:;*_·-]{1,4}";
const RE_ACREDITA = new RegExp(
  [
    `monto${_S}total${_S}(?:de[l]?${_S})?(?:presente${_S})?contrato`,
    `monto${_S}contract?ual`,
    `monto${_S}(?:de|del)${_S}(?:la${_S})?contrat`,
    `monto${_S}contratad[oa]`,
    `monto${_S}(?:de${_S})?(?:la${_S})?consultor[ií]a`,
    `valor${_S}(?:del${_S})?contrato`,
    "retribuci[oó]n", "honorarios",
  ].join("|"),
  "i",
);
// Etiquetas de la OBRA SUPERVISADA: dato útil, pero NO es lo que acredita.
const RE_OBRA = /(ejecuci[oó]n\s+de\s+(?:la\s+)?obra|monto\s+de\s+(?:la\s+)?obra|valor\s+(?:referencial\s+)?de\s+(?:la\s+)?obra|costo\s+de\s+(?:la\s+)?obra)/i;
// Ruido: jamás acreditan.
const RE_DESCARTE = /(adelanto|adicional|deductiv|penalidad|mora|reajuste|igv|retenci[oó]n|saldo|amortizaci[oó]n)/i;

function _num(txt) {
  // "1'000,237.56" → 1000237.56 · "756,307.16" → 756307.16
  const limpio = String(txt).replace(/['’\s]/g, "").replace(/,/g, "");
  const v = parseFloat(limpio);
  return Number.isFinite(v) && v > 0 ? v : null;
}

/**
 * Páginas que cubre el `folio` de un contrato: "49-56", "78; 115", "121-133".
 * `holgura` extiende el rango a ambos lados porque el mapa los da APROXIMADOS
 * ("49-56 aprox.") y el contrato real puede arrancar una página antes — medido:
 * el de Huarmaca declaraba 49-56 y su MONTO CONTRACTUAL está en la 48. La
 * holgura es segura SOLO junto al candado de emisor (`emisorCalza`): sin él,
 * ampliar el rango invita a robarle el monto al contrato vecino.
 */
function paginasDeFolio(folio, tope, holgura = 2) {
  const s = String(folio || "");
  const pags = new Set();
  const add = (a, b) => {
    for (let i = Math.max(1, a - holgura); i <= b + holgura; i++) pags.add(i);
  };
  for (const m of s.matchAll(/(\d{1,4})\s*[-–]\s*(\d{1,4})/g)) {
    const a = +m[1], b = +m[2];
    if (b >= a && b - a <= 60) add(a, b);
  }
  const soloRangos = s.replace(/(\d{1,4})\s*[-–]\s*(\d{1,4})/g, " ");
  for (const m of soloRangos.matchAll(/\d{1,4}/g)) add(+m[0], +m[0]);
  return [...pags].filter((p) => p >= 1 && (!tope || p <= tope)).sort((a, b) => a - b);
}

// Palabras que NO identifican a una entidad (aparecen en casi todas).
const _STOP_EMISOR = new Set([
  "MUNICIPALIDAD", "DISTRITAL", "PROVINCIAL", "DISTRITO", "PROVINCIA",
  "REGION", "REGIONAL", "DEPARTAMENTO", "GOBIERNO", "LOCAL", "ENTIDAD",
  "CONSORCIO", "EMPRESA", "GENERALES", "CONTRATISTAS", "INGENIERIA",
  "CONSULTORES", "SERVICIOS", "OBRA", "OBRAS", "SOCIEDAD", "ANONIMA",
]);

function _tokensEmisor(emisor) {
  return String(emisor || "")
    .normalize("NFKD").replace(/[̀-ͯ]/g, "")
    .toUpperCase().replace(/[^A-Z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((t) => t.length > 3 && !_STOP_EMISOR.has(t));
}

/**
 * CANDADO DE PROCEDENCIA (#62, misma lógica que #47): ¿esta página pertenece al
 * contrato de ESE emisor? Sin él, un rango de folios aproximado que se solapa
 * con el contrato vecino produce un monto plausible y ajeno — el error más caro
 * del sistema (cf. #58: heredar por folio sin mirar el emisor).
 * Tolera el destrozo del OCR exigiendo solo el prefijo del token (HUARMACA →
 * "HUARMAC" en el escaneo real).
 */
function emisorCalza(texto, emisor) {
  const toks = _tokensEmisor(emisor);
  if (!toks.length) return null; // sin emisor declarado no se puede juzgar
  const t = String(texto || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase();
  return toks.some((k) => t.includes(k.slice(0, Math.max(5, k.length - 1))));
}

function _etiquetaDe(txt) {
  if (RE_DESCARTE.test(txt)) return "descartado";
  if (RE_ACREDITA.test(txt)) return "acredita";
  if (RE_OBRA.test(txt)) return "obra_supervisada";
  return "sin_etiqueta";
}

/**
 * Candidatos de monto en un texto de página, con su etiqueta y línea literal.
 *
 * La etiqueta se toma de la PROPIA línea; solo si la línea no dice nada de sí
 * misma se mira la anterior (caso "CLÁUSULA TERCERA: MONTO CONTRACTUAL" con el
 * número debajo). Mirar siempre atrás contaminaba: en el folio 77, el "Monto de
 * Ejecucion de Obra" heredaba el "acredita" del "Monto de Contrato de
 * Consultoria" de la línea de arriba y el script elegía la obra — justo lo que
 * este módulo existe para no hacer.
 */
function candidatosDePagina(texto, pagina) {
  const out = [];
  const lineas = String(texto || "").split(/\r?\n/);
  lineas.forEach((linea, i) => {
    RE_MONTO.lastIndex = 0;
    for (const m of linea.matchAll(RE_MONTO)) {
      const valor = _num(m[1]);
      if (valor === null) continue;
      let etiqueta = _etiquetaDe(linea);
      if (etiqueta === "sin_etiqueta" && i > 0) etiqueta = _etiquetaDe(lineas[i - 1]);
      out.push({ valor, etiqueta, pagina, linea: linea.trim().slice(0, 140) });
    }
  });
  return out;
}

/** ¿`a` es ~10% de algún otro candidato? → adelanto directo disfrazado. */
function esAdelantoDe(a, todos) {
  return todos.some(
    (b) => b !== a && b.valor > a.valor && Math.abs(a.valor - b.valor * 0.1) < Math.max(1, b.valor * 0.001),
  );
}

/**
 * Elige el monto que acredita, o null con los candidatos a la vista.
 * Devuelve { monto, procedencia, candidatos, motivo }.
 */
function elegirMonto(candidatos) {
  const vivos = candidatos.filter(
    (c) => c.etiqueta !== "descartado" && !esAdelantoDe(c, candidatos),
  );
  const acredita = vivos.filter((c) => c.etiqueta === "acredita");
  const uniq = (arr) => [...new Set(arr.map((c) => c.valor))];

  if (acredita.length) {
    // varias etiquetas "acredita" con valores distintos → no adivinar
    if (uniq(acredita).length > 1) {
      return { monto: null, candidatos: acredita, motivo: "varios montos etiquetados como contractuales — elegir a mano" };
    }
    const g = acredita[0];
    return {
      monto: g.valor,
      procedencia: { pagina: g.pagina, etiqueta: g.etiqueta, linea: g.linea },
      candidatos: vivos,
      motivo: null,
    };
  }
  // sin etiqueta contractual: NO se elige por magnitud (la obra supervisada
  // suele ser 10-40× el contrato de supervisión — adivinar aquí infla el 3.4)
  const soloObra = vivos.length && vivos.every((c) => c.etiqueta === "obra_supervisada");
  return {
    monto: null,
    candidatos: vivos,
    motivo: soloObra
      ? "solo se hallaron montos de la OBRA supervisada, no del contrato de consultoría — confirmar cuál acredita"
      : vivos.length
        ? "montos hallados sin etiqueta que los identifique como contractuales — confirmar"
        : "no se hallaron montos en los folios citados",
  };
}

/** Procesa el bloque del postor. `leerPagina(n)` → texto o null. */
function rescatarMontos(experienciaPostor, leerPagina, { topePagina = null } = {}) {
  return (experienciaPostor || []).map((c, idx) => {
    const n = c.n != null ? c.n : idx + 1;
    if (c.monto != null) return { n, ...c, _rescate: null }; // ya lo trae el mapa
    const pags = paginasDeFolio(c.folio, topePagina);
    const cands = [];
    const descartadasPorEmisor = [];
    for (const p of pags) {
      const t = leerPagina(p);
      if (!t) continue;
      // el candado de procedencia manda: una página cuyo emisor no calza NO
      // aporta montos, aunque los tenga con la etiqueta perfecta.
      if (emisorCalza(t, c.emisor) === false) {
        if (candidatosDePagina(t, p).length) descartadasPorEmisor.push(p);
        continue;
      }
      cands.push(...candidatosDePagina(t, p));
    }
    const r = elegirMonto(cands);
    return {
      n,
      ...c,
      monto: r.monto,
      _rescate: {
        origen: "montos_postor.js (índice OCR)",
        paginas_barridas: pags,
        paginas_descartadas_por_emisor: descartadasPorEmisor,
        elegido: r.procedencia || null,
        motivo: r.motivo,
        candidatos: r.candidatos.slice(0, 6),
      },
    };
  });
}

module.exports = {
  rescatarMontos, elegirMonto, candidatosDePagina, paginasDeFolio, emisorCalza, _num,
};

// ── CLI ──────────────────────────────────────────────────────────────────────
if (require.main === module) {
  const carpeta = process.argv[2];
  const escribir = process.argv.includes("--escribir");
  if (!carpeta) {
    console.error("uso: node scripts/montos_postor.js <carpeta_analisis> [--escribir]");
    process.exit(2);
  }
  const rutaRoster = path.join(carpeta, "roster_bundles.json");
  const dirOcr = ["_ocr_propuesta", "ocr_propuesta", "_ocr"]
    .map((d) => path.join(carpeta, d))
    .find((d) => fs.existsSync(d));
  if (!fs.existsSync(rutaRoster)) {
    console.error(`no existe ${rutaRoster}`);
    process.exit(2);
  }
  if (!dirOcr) {
    console.error("sin índice OCR (Camino B): este rescate no aplica — el mapa es la única vía");
    process.exit(3);
  }
  const roster = JSON.parse(fs.readFileSync(rutaRoster, "utf8"));
  const postor = roster.postor || roster;
  const leerPagina = (n) => {
    const f = path.join(dirOcr, `p${String(n).padStart(4, "0")}.txt`);
    return fs.existsSync(f) ? fs.readFileSync(f, "utf8") : null;
  };

  const antes = postor.experiencia_postor || [];
  const despues = rescatarMontos(antes, leerPagina);
  let rescatados = 0, sinResolver = 0;
  for (const c of despues) {
    const r = c._rescate;
    if (!r) { console.log(`  n=${c.n}  monto ya venía del mapa: ${c.monto}`); continue; }
    if (c.monto != null) {
      rescatados++;
      console.log(`  ✓ n=${c.n}  ${c.monto}  ← p${r.elegido.pagina} [${r.elegido.etiqueta}]`);
      console.log(`       «${r.elegido.linea}»`);
    } else {
      sinResolver++;
      console.log(`  ⚠ n=${c.n}  SIN MONTO — ${r.motivo}`);
      for (const k of r.candidatos) console.log(`       cand: ${k.valor} p${k.pagina} [${k.etiqueta}] «${k.linea.slice(0, 80)}»`);
    }
  }
  console.log(`\nrescatados ${rescatados} · sin resolver ${sinResolver} · total ${despues.length}`);

  if (escribir) {
    postor.experiencia_postor = despues;
    fs.writeFileSync(rutaRoster, JSON.stringify(roster, null, 2), "utf8");
    console.log(`→ ${rutaRoster} actualizado`);
  }
}
