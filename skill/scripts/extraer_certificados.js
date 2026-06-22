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
 * Uso:  node scripts/extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip>
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

async function main() {
  const [espejoPath, propuestaPath, zipPath] = process.argv.slice(2);
  if (!espejoPath || !propuestaPath || !zipPath) {
    console.error("uso: node extraer_certificados.js <espejo.json> <propuesta.pdf> <salida.zip>");
    process.exit(2);
  }
  const espejo = JSON.parse(fs.readFileSync(espejoPath, "utf8"));
  const src = await PDFDocument.load(fs.readFileSync(propuestaPath));
  const total = src.getPageCount();
  const zip = new JSZip();
  let nCerts = 0;
  let sinFolio = 0;
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
      // 1-indexed → índice de página (0-indexed); descartar fuera de rango
      const idxs = paginas.map((p) => p - 1).filter((i) => i >= 0 && i < total);
      if (!idxs.length) continue;
      const cert = await PDFDocument.create();
      const pages = await cert.copyPages(src, idxs);
      pages.forEach((p) => cert.addPage(p));
      zip.file(`P${prof.n_prof}_E${exp.n}.pdf`, await cert.save());
      nCerts++;
    }
  }
  const buf = await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
  fs.writeFileSync(zipPath, buf);
  console.log(
    `OK · ${nCerts} constancias recortadas → ${zipPath}` +
      (sinFolio ? ` · ${sinFolio} experiencias sin folio (omitidas)` : "")
  );
}

main().catch((e) => {
  console.error("ERROR:", e.message);
  process.exit(1);
});
