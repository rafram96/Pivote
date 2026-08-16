#!/usr/bin/env node
/**
 * Fase 2 — recorta de `propuesta.pdf` las páginas de la CONSTANCIA de cada
 * experiencia (folio ≈ nº de página) a un PDF chico `P{n}_E{m}.pdf`, con la
 * página PRINCIPAL primero (`folio_principal` si la skill lo marcó; si no, el
 * primer folio), y los empaqueta en `certificados.zip` para que el MCP lo suba
 * junto al espejo a `/api/pivote/analizar`. El backend lo renderiza y embebe en
 * cada bloque `CERT N°X`.
 *
 * Son los documentos de la EXPERIENCIA (constancias / conformidades de servicio),
 * NO los títulos/colegiatura (eso es del profesional, no de la experiencia).
 *
 * Mejora A: si se pasa `--tdr`, además recorta por profesional el requisito
 * (`prof.requisitos.folio`) → `P{n}_TDR.pdf` y el Anexo 16
 * (`prof.folio_anexo`, de la propuesta) → `P{n}_ANEXO.pdf`. El backend los embebe
 * ANTES de las experiencias en la hoja del profesional.
 *
 * Issue #32: también recorta de `bases.pdf` la página del Cuadro de Factores
 * (`espejo._meta.pagina_factores`, la tabla de puntaje del "4.2 A") → un
 * `P{n}_FACTOR.pdf` por profesional (misma página replicada). El backend lo
 * embebe AL FINAL de la hoja: es el baremo con el que se puntúa lo de arriba.
 *
 * Uso:
 *   node scripts/extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip> [pdf-comun]
 *   node scripts/extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip> \
 *        --bases <bases.pdf> --tdr <terminos-de-referencia.pdf>
 *
 * El posicional histórico sigue significando que ambos recortes viven en el
 * mismo PDF. Las opciones separadas eliminan ese supuesto (#86).
 */
const fs = require("fs");
const { spawnSync } = require("child_process");
const { PDFDocument } = require("pdf-lib");
const JSZip = require("jszip");

function parseArgs(argv) {
  const [espejoPath, propuestaPath, zipPath, ...resto] = argv;
  if (!espejoPath || !propuestaPath || !zipPath) return null;
  let basesPath = null;
  let tdrPath = null;
  let i = 0;
  if (resto[0] && !resto[0].startsWith("--")) {
    basesPath = tdrPath = resto[0];
    i = 1;
  }
  while (i < resto.length) {
    const opcion = resto[i++];
    const valor = resto[i++];
    if (!valor || !["--bases", "--tdr"].includes(opcion)) {
      throw new Error(`opción inválida o sin valor: ${opcion || "(vacía)"}`);
    }
    if (opcion === "--bases") basesPath = valor;
    if (opcion === "--tdr") tdrPath = valor;
  }
  return { espejoPath, propuestaPath, zipPath, basesPath, tdrPath };
}

// "590" → [590] · "622-625" → [622..625] · "48,52" → [48,52]
function parseFolios(folio) {
  if (folio == null || folio === "") return [];
  const out = [];
  for (const part of String(folio).split(",")) {
    const m = part.trim().match(/^(\d+)\s*[-–—]\s*(\d+)$/);
    if (m) {
      const a = Math.min(+m[1], +m[2]);
      const b = Math.max(+m[1], +m[2]);
      for (let i = a; i <= b; i++) out.push(i);
    } else {
      const n = parseInt(part.trim(), 10);
      if (Number.isFinite(n)) out.push(n);
    }
  }
  return [...new Set(out)];
}

function claveFolios(folios) {
  return [...new Set(folios)].sort((a, b) => a - b).join(",");
}

// Un folio compartido por la mayoría de los cargos casi siempre es la página
// donde EMPIEZA el cuadro, no la página individual de cada requisito (#68).
function foliosTdrSospechosos(profesionales) {
  const claves = profesionales
    .map((p) => claveFolios(parseFolios(p.requisitos && p.requisitos.folio)))
    .filter(Boolean);
  const conteos = new Map();
  for (const k of claves) conteos.set(k, (conteos.get(k) || 0) + 1);
  const umbral = Math.max(3, Math.ceil(claves.length * 0.5));
  return new Set([...conteos].filter(([, n]) => n >= umbral).map(([k]) => k));
}

function ampliarTdr(folios, rangoDeclarado, total) {
  const declarado = parseFolios(rangoDeclarado).filter((p) => p >= 1 && p <= total);
  if (declarado.length) return declarado;
  // Fallback conservador y ruidoso: cuadro de hasta 5 páginas desde la página
  // repetida. Es preferible contexto amplio a una precisión falsa.
  const inicio = Math.min(...folios);
  const fin = Math.min(total, inicio + 4);
  return Array.from({ length: fin - inicio + 1 }, (_, i) => inicio + i);
}

// Recorta `folios` (1-indexed) de `src` (con `total` páginas) → buffer PDF, o null.
async function recortar(src, total, folios) {
  const idxs = folios.map((p) => p - 1).filter((i) => i >= 0 && i < total);
  if (!idxs.length) return null;
  const out = await PDFDocument.create();
  const pages = await out.copyPages(src, idxs);
  pages.forEach((p) => out.addPage(p));
  return out.save();
}

function validarTextoFactor(texto) {
  const limpio = String(texto || "").replace(/\s+/g, " ").trim();
  if (limpio.length < 20) return "no_verificado";
  const normal = limpio.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  if (/FACTORES? DE EVALUACION/.test(normal)
      || (/PUNTAJE/.test(normal) && /EXPERIENCIA.+PERSONAL CLAVE/.test(normal))) {
    return "verificado";
  }
  return "incorrecto";
}

function comprobarPaginaFactor(ruta, folios, ejecutar = spawnSync) {
  if (!ruta || !folios.length) return { estado: "no_verificado", detalle: "sin fuente o páginas" };
  const paginas = [...folios].sort((a, b) => a - b);
  const r = ejecutar("pdftotext", [
    "-f", String(paginas[0]), "-l", String(paginas[paginas.length - 1]), ruta, "-",
  ], { encoding: "utf8", windowsHide: true });
  if (r.error || r.status !== 0) {
    return { estado: "no_verificado", detalle: "pdftotext no disponible o falló" };
  }
  const estado = validarTextoFactor(r.stdout);
  return {
    estado,
    detalle: estado === "no_verificado"
      ? "la página no tiene texto extraíble; requiere comprobación visual"
      : estado === "incorrecto"
        ? "el texto no contiene Factores de evaluación/Puntaje del personal clave"
        : "texto del baremo reconocido",
  };
}

async function cargarPdf(ruta) {
  if (!ruta || !fs.existsSync(ruta)) return { doc: null, total: 0 };
  const doc = await PDFDocument.load(fs.readFileSync(ruta));
  return { doc, total: doc.getPageCount() };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args) {
    console.error("uso: node extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip> [pdf-comun] [--bases bases.pdf] [--tdr tdr.pdf]");
    process.exit(2);
  }
  const { espejoPath, propuestaPath, zipPath, basesPath, tdrPath } = args;
  const espejo = JSON.parse(fs.readFileSync(espejoPath, "utf8"));
  const src = await PDFDocument.load(fs.readFileSync(propuestaPath));
  const total = src.getPageCount();
  const { doc: bases, total: basesTotal } = await cargarPdf(basesPath);
  const { doc: tdr, total: tdrTotal } = await cargarPdf(tdrPath);
  // Factor de evaluación (issue #32): UNA sola página de las bases — la del Cuadro
  // de Factores / "4.2 A" con la tabla de puntaje — que el backend embebe AL FINAL
  // de cada hoja de profesional. Es la misma para todos, así que se recorta una vez
  // y se replica como `P{n}_FACTOR.pdf`: pesa KBs y evita casos especiales aguas
  // abajo (el ingest solo acepta nombres `P*` y el Excel reparte por n_prof).
  const factorPags = parseFolios(espejo._meta && espejo._meta.pagina_factores);
  let factorBuf = null;
  let factorComprobacion = { estado: "no_verificado", detalle: "sin recorte" };
  if (bases && factorPags.length) {
    factorBuf = await recortar(bases, basesTotal, factorPags);
    if (factorBuf) {
      factorComprobacion = comprobarPaginaFactor(basesPath, factorPags);
      // Texto extraíble que contradice la finalidad del recorte: no adjuntar una
      // evidencia sabidamente equivocada. Si es escaneada, se conserva pero se
      // rotula como no verificada para revisión visual.
      if (factorComprobacion.estado === "incorrecto") factorBuf = null;
    }
  }
  const zip = new JSZip();
  let nCerts = 0, nAnexo = 0, nTdr = 0, nFactor = 0, sinFolio = 0;
  let tdrAmpliados = 0;
  const profesionales = espejo.profesionales || [];
  const sospechosos = foliosTdrSospechosos(profesionales);
  const rangoPersonal = espejo._meta && espejo._meta.paginas_personal_clave;
  for (const prof of profesionales) {
    for (const exp of prof.experiencias || []) {
      // Páginas FÍSICAS reales del PDF si la skill las marcó (vienen con la
      // principal primero). El folio impreso del borde ≠ la página del PDF NO
      // siempre, así que esto es lo correcto. Si no hay, fallback: folio ≈ página.
      let paginas = Array.isArray(exp.paginas_pdf)
        ? exp.paginas_pdf.map((p) => parseInt(p, 10)).filter(Number.isFinite)
        : [];
      if (!paginas.length) paginas = parseFolios(exp.folio); // fallback (puede desfasar)
      if (!paginas.length) {
        sinFolio++;
        continue;
      }
      const buf = await recortar(src, total, paginas);
      if (!buf) continue;
      zip.file(`P${prof.n_prof}_E${exp.n}.pdf`, buf);
      nCerts++;
    }
    // Mejora A: Anexo 16 (de la propuesta) + requisito del TDR (de las bases) por
    // profesional → P{n}_ANEXO.pdf / P{n}_TDR.pdf. El backend los embebe ANTES de
    // las experiencias en la hoja del profesional.
    const anexoFolios = parseFolios(prof.folio_anexo);
    if (anexoFolios.length) {
      const b = await recortar(src, total, anexoFolios);
      if (b) { zip.file(`P${prof.n_prof}_ANEXO.pdf`, b); nAnexo++; }
    }
    let tdrFolios = parseFolios(prof.requisitos && prof.requisitos.folio);
    const folioRepetido = sospechosos.has(claveFolios(tdrFolios));
    if (folioRepetido && tdrFolios.length) {
      tdrFolios = ampliarTdr(tdrFolios, rangoPersonal, tdrTotal);
      tdrAmpliados++;
    }
    if (tdr && tdrFolios.length) {
      const b = await recortar(tdr, tdrTotal, tdrFolios);
      if (b) { zip.file(`P${prof.n_prof}_TDR.pdf`, b); nTdr++; }
    }
    if (factorBuf) { zip.file(`P${prof.n_prof}_FACTOR.pdf`, factorBuf); nFactor++; }
  }
  const buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(zipPath, buf);
  // el recorte del factor es silencioso si falla → avisar explícitamente por qué,
  // que es la única señal que tiene la skill para dejar la observación al usuario.
  let avisoFactor = "";
  if (bases && !factorPags.length) {
    avisoFactor = " · ⚠ sin `_meta.pagina_factores` (el Excel saldrá SIN el recorte del factor)";
  } else if (bases && !factorBuf) {
    avisoFactor = factorComprobacion.estado === "incorrecto"
      ? ` · ⚠ Factor OMITIDO: ${factorComprobacion.detalle}`
      : ` · ⚠ pagina_factores=${espejo._meta.pagina_factores} fuera del rango ` +
        `1..${basesTotal} de bases.pdf (sin recorte del factor)`;
  } else if (factorBuf && factorComprobacion.estado === "no_verificado") {
    avisoFactor = ` · ⚠ factor recortado pero NO verificado: ${factorComprobacion.detalle}`;
  }
  console.log(
    `OK · ${nCerts} constancias` +
      (nAnexo ? ` · ${nAnexo} anexos` : "") +
      (nTdr ? ` · ${nTdr} TDR` : "") +
      (tdrAmpliados ? ` · ⚠ ${tdrAmpliados} TDR ampliados al cuadro completo (folio repetido)` : "") +
      (nFactor ? ` · ${nFactor} factor ${factorComprobacion.estado === "verificado" ? "verificado" : "recortado"}` : "") +
      ` recortados → ${zipPath}` +
      (sinFolio ? ` · ${sinFolio} experiencias sin folio (omitidas)` : "") +
      (tdrPath && !tdr ? ` · ⚠ TDR no hallado (sin recortes TDR)` : "") +
      (basesPath && !bases ? ` · ⚠ bases no halladas (sin recorte Factor A)` : "") +
      avisoFactor
  );
}

if (require.main === module) {
  main().catch((e) => {
    console.error("ERROR:", e.message);
    process.exit(1);
  });
}

module.exports = {
  parseArgs, parseFolios, foliosTdrSospechosos, ampliarTdr,
  validarTextoFactor, comprobarPaginaFactor,
};
