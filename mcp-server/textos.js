/**
 * Los textos que ve el evaluador en el chat.
 *
 * Viven aparte de `mcp.js` por dos razones: se pueden probar sin levantar el
 * transporte stdio, y así queda un solo sitio donde revisar que el MCP habla en
 * castellano de evaluador y no en jerga de sistemas. Nada de "job", "endpoint",
 * "polling", "payload" ni "backend" en lo que sale por aquí.
 *
 * Regla de la casa que estos textos respetan: los archivos NUNCA viajan por una
 * tool — se devuelve la dirección de descarga, no el ZIP.
 */

function _linea(...partes) {
  return partes.filter((p) => p !== null && p !== undefined && String(p).trim() !== "").join("  ·  ");
}

/** El motivo que devolvió el servidor, en una frase, sin volcar estructuras. */
function _motivo(r, porDefecto) {
  if (typeof r?.error === "string") return r.error;
  if (typeof r?.error?.detail === "string") return r.error.detail;
  return porDefecto;
}

/** Resultado de `buscar_cui` en lenguaje llano. */
export function textoBusqueda(r, { q } = {}) {
  if (!r || r.ok === false) {
    return `No se pudo buscar: ${_motivo(r, "el servidor de InfoObras no respondió.")}`;
  }
  if (r.base_mef_no_disponible) {
    return r.aviso || "La base de inversiones del MEF no está instalada en el servidor, así que no hay dónde buscar.";
  }
  const resultados = Array.isArray(r.resultados) ? r.resultados : [];
  if (resultados.length === 0) {
    return r.aviso || `Sin coincidencias para «${r.q ?? q ?? ""}». Prueba con el nombre del establecimiento o de la localidad.`;
  }

  const porCodigo = r.coincidencia === "codigo";
  const cabecera = porCodigo
    ? `El código ${r.q} corresponde a esta inversión:`
    : `Encontré ${resultados.length} inversión(es) para «${r.q ?? q ?? ""}»:`;

  const cuerpo = resultados.map((x, i) => {
    const codigo = x.cui ? `CUI ${x.cui}` : x.snip ? `SNIP ${x.snip}` : "sin código";
    // El parecido sólo tiene sentido si se buscó por nombre: sobre un código
    // exacto, hablar de «100% de parecido» sugiere una duda que no existe.
    const parecido = !porCodigo && x.score !== null && x.score !== undefined
      ? `parecido ${Math.round(x.score)}%`
      : null;
    return [
      `${i + 1}. ${codigo}${parecido ? `  (${parecido})` : ""}`,
      `   ${x.nombre ?? "(sin nombre)"}`,
      `   ${_linea(x.ubicacion, x.entidad, x.situacion)}`,
    ].join("\n");
  });

  const pie =
    porCodigo
      ? "Para bajar sus documentos: descargar_documentos_cui con ese CUI."
      : "Si alguna es la obra que buscas, pide sus documentos con descargar_documentos_cui y su CUI.";

  return [cabecera, "", ...cuerpo, "", pie].join("\n");
}

/** Confirmación de `descargar_documentos_cui`. */
export function textoDescargaIniciada(r) {
  if (!r || r.ok === false) {
    return `No se pudo iniciar la descarga: ${_motivo(r, "el servidor de InfoObras no respondió.")}`;
  }
  return [
    `Empecé a bajar los documentos de la obra del CUI ${r.cui} desde InfoObras.`,
    "",
    `Número de seguimiento: ${r.descarga_id}`,
    r.paso ? `Ahora mismo: ${r.paso}` : null,
    "",
    "Puede tardar varios minutos (una obra grande trae cientos de archivos).",
    `Consulta cómo va con consultar_descarga_cui y ese número.`,
  ]
    .filter((l) => l !== null)
    .join("\n");
}

/** Avance de `consultar_descarga_cui`. */
export function textoDescargaEstado(r) {
  if (r?.status_http === 404) {
    return "No encuentro esa descarga. Revisa el número de seguimiento que te di al iniciarla.";
  }
  if (!r || r.ok === false) {
    return `No se pudo consultar la descarga: ${_motivo(r, "el servidor de InfoObras no respondió.")}`;
  }
  const obra = _linea(r.nombre, r.obra_id ? `obra ${r.obra_id}` : null);
  const encabezado = `Descarga ${r.descarga_id} · CUI ${r.cui ?? "?"}${obra ? `\n${obra}` : ""}`;

  if (r.estado === "listas") {
    return [
      encabezado,
      "",
      `Listo: ${r.descargados} documento(s) descargados${r.fallidos ? `, ${r.fallidos} que la fuente no entregó` : ""}.`,
      "",
      "Los archivos NO se pueden mandar por el chat. Descarga el ZIP desde:",
      r.zip_url,
      ...(r.avisos.length ? ["", "Ojo con esto:", ...r.avisos.map((a) => `· ${a}`)] : []),
    ].join("\n");
  }
  if (r.estado === "error") {
    return [
      encabezado,
      "",
      r.paso || "La descarga no pudo completarse.",
      "",
      "Puedes volver a pedirla con descargar_documentos_cui.",
    ].join("\n");
  }
  return [
    encabezado,
    "",
    `En curso. ${r.paso || "Consultando InfoObras."}`,
    "",
    "Vuelve a consultar en un momento con el mismo número de seguimiento.",
  ].join("\n");
}
