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
 * Mejora A: si se pasa `bases.pdf`, además recorta por profesional el requisito
 * del TDR (`prof.requisitos.folio`, de las bases) → `P{n}_TDR.pdf` y el Anexo 16
 * (`prof.folio_anexo`, de la propuesta) → `P{n}_ANEXO.pdf`. El backend los embebe
 * ANTES de las experiencias en la hoja del profesional.
 *
 * Uso:  node scripts/extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip> [bases.pdf]
 */
const fs = require("fs");
const { PDFDocument } = require("pdf-lib");
const JSZip = require("jszip");

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

// Recorta `folios` (1-indexed) de `src` (con `total` páginas) → buffer PDF, o null.
async function recortar(src, total, folios) {
  const idxs = folios.map((p) => p - 1).filter((i) => i >= 0 && i < total);
  if (!idxs.length) return null;
  const out = await PDFDocument.create();
  const pages = await out.copyPages(src, idxs);
  pages.forEach((p) => out.addPage(p));
  return out.save();
}

async function main() {
  const [espejoPath, propuestaPath, zipPath, basesPath] = process.argv.slice(2);
  if (!espejoPath || !propuestaPath || !zipPath) {
    console.error("uso: node extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip> [bases.pdf]");
    process.exit(2);
  }
  const espejo = JSON.parse(fs.readFileSync(espejoPath, "utf8"));
  const src = await PDFDocument.load(fs.readFileSync(propuestaPath));
  const total = src.getPageCount();
  // bases.pdf (opcional) → recorte del TDR por cargo (mejora A)
  let bases = null, basesTotal = 0;
  if (basesPath && fs.existsSync(basesPath)) {
    bases = await PDFDocument.load(fs.readFileSync(basesPath));
    basesTotal = bases.getPageCount();
  }
  const zip = new JSZip();
  let nCerts = 0, nAnexo = 0, nTdr = 0, sinFolio = 0;
  for (const prof of espejo.profesionales || []) {
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
    const tdrFolios = parseFolios(prof.requisitos && prof.requisitos.folio);
    if (bases && tdrFolios.length) {
      const b = await recortar(bases, basesTotal, tdrFolios);
      if (b) { zip.file(`P${prof.n_prof}_TDR.pdf`, b); nTdr++; }
    }
  }
  const buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(zipPath, buf);
  console.log(
    `OK · ${nCerts} constancias` +
      (nAnexo ? ` · ${nAnexo} anexos` : "") +
      (nTdr ? ` · ${nTdr} TDR` : "") +
      ` recortados → ${zipPath}` +
      (sinFolio ? ` · ${sinFolio} experiencias sin folio (omitidas)` : "") +
      (basesPath && !bases ? ` · ⚠ bases.pdf no hallado (sin recortes TDR)` : "")
  );
}

main().catch((e) => {
  console.error("ERROR:", e.message);
  process.exit(1);
});
