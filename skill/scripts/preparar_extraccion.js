"use strict";

// Prepara hechos declarados sin convertirlos en hechos verificados. Las fechas
// solo se sustituyen cuando la fuente acredita expresamente otro evento.
const { conflictoEventoFecha } = require("./entradas_criticas");

const COPIA = v => {
  if (v === undefined) return undefined;
  return JSON.parse(JSON.stringify(v));
};

function fechaCompleta(valor) {
  if (typeof valor !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(valor)) return false;
  const [y, m, d] = valor.split("-").map(Number);
  if (m < 1 || m > 12 || d < 1 || d > 31) return false;
  const fecha = new Date(Date.UTC(y, m - 1, d));
  return Number.isFinite(fecha.getTime())
    && fecha.getUTCFullYear() === y && fecha.getUTCMonth() === m - 1
    && fecha.getUTCDate() === d;
}

function parISO(inicio, fin) {
  return fechaCompleta(inicio) && fechaCompleta(fin) && inicio <= fin;
}

function indicadoresTemporales(experiencia) {
  const inicio = experiencia && (experiencia.fecha_inicial ?? experiencia.fecha_inicio);
  const fin = experiencia && experiencia.fecha_final;
  const emision = experiencia && (experiencia.fecha_emision ?? experiencia.fecha_emision_constancia);
  const covidInicio = "2020-03-16", covidFin = "2020-06-30";
  const incluye = inicio <= covidFin && fin >= covidInicio;
  return {
    incluye_covid: parISO(inicio, fin) ? (incluye ? "SÍ" : "NO") : null,
    cert_antes_culminar: fechaCompleta(fin) && fechaCompleta(emision) ? (emision < fin ? "SÍ" : "NO") : null,
  };
}

function serializar(v) {
  try { return JSON.stringify(v); } catch (_) { return String(v); }
}

function agregarObservacion(experiencia, texto) {
  const previo = experiencia.observaciones ?? (Array.isArray(experiencia.notas) ? experiencia.notas : null);
  if (typeof previo === "string") {
    if (!previo.includes(texto)) experiencia.observaciones = `${previo}; ${texto}`;
  } else if (Array.isArray(previo)) {
    const contenido = previo.map(v => typeof v === "string" ? v : serializar(v)).join("; ");
    experiencia.observaciones = contenido.includes(texto) ? contenido : `${contenido}${contenido ? "; " : ""}${texto}`;
  } else if (previo == null) experiencia.observaciones = texto;
  else experiencia.observaciones = `${serializar(previo)}; ${texto}`;
}

function revisar(revisiones, nProf, nExp, campo, pagina, texto, motivo) {
  const r = { n_prof: nProf, n_experiencia: nExp, campo,
    pagina_pdf: pagina ?? null, texto: texto ?? null, motivo };
  if (!revisiones.some(x => x.n_prof === r.n_prof && x.n_experiencia === r.n_experiencia
      && x.campo === r.campo && x.motivo === r.motivo)) revisiones.push(r);
}

function experienciaLista(profesional) {
  return Array.isArray(profesional?.experiencias) ? profesional.experiencias : [];
}

function normalizarFunciones(e, nProf, nExp, revisiones) {
  const valor = e.funciones_similares;
  const fuente = e.funciones_fuente;
  const fuenteValida = fuente && typeof fuente.texto === "string" && fuente.texto.trim()
    && Number.isInteger(fuente.pagina_pdf) && fuente.pagina_pdf > 0
    && Array.isArray(e.paginas_pdf) && e.paginas_pdf.includes(fuente.pagina_pdf);
  if (Array.isArray(valor) && valor.every(x => typeof x === "string")) {
    if (!valor.length) e.funciones_similares = null;
    else if (fuenteValida) {
      e.funciones_similares = valor.join("; ");
      agregarObservacion(e, `funciones_fuente: página ${fuente.pagina_pdf}; ${fuente.texto}`);
    } else if (valor.length) {
      e.funciones_similares = null;
      const motivo = `por verificar, falta cotejo de funciones; original=${serializar(valor)}`;
      agregarObservacion(e, motivo);
      revisar(revisiones, nProf, nExp, "funciones_similares", e.paginas_pdf?.[0], null, motivo);
    }
  } else if (typeof valor === "string") {
    if (valor.trim() && !fuenteValida) {
      e.funciones_similares = null;
      const motivo = `por verificar, falta cotejo de funciones; original=${serializar(valor)}`;
      agregarObservacion(e, motivo);
      revisar(revisiones, nProf, nExp, "funciones_similares", e.paginas_pdf?.[0], null, motivo);
    } else if (valor.trim() && fuenteValida) {
      agregarObservacion(e, `funciones_fuente: página ${fuente.pagina_pdf}; ${fuente.texto}`);
    }
  } else if (valor !== null && valor !== undefined && typeof valor !== "string") {
    e.funciones_similares = null;
    const original = serializar(valor);
    const motivo = `funciones_similares con tipo inválido; original=${original}`;
    agregarObservacion(e, motivo);
    revisar(revisiones, nProf, nExp, "funciones_similares", null, null, motivo);
  }
}

function prepararProfesional(raw, nProf) {
  const profesional = COPIA(raw);
  const avisos = [], revisiones = [], inciertos = new Set();
  const experiencias = experienciaLista(profesional);
  for (const e of experiencias) {
    if (!e || typeof e !== "object") continue;
    const nExp = e.n ?? e.n_experiencia;
    normalizarFunciones(e, nProf, nExp, revisiones);
    const fechas = [
      ["fecha_inicial", "inicio_servicio", e.fecha_inicial ?? e.fecha_inicio],
      ["fecha_final", "fin_servicio", e.fecha_final],
    ];
    for (const [campo, evento, valor] of fechas) {
      const fuente = e.fechas_fuente?.[campo] || (campo === "fecha_inicial" ? e.fechas_fuente?.fecha_inicio : null);
      // La abstención inicial también debe conservar el literal en el espejo,
      // porque fechas_fuente es únicamente un campo del crudo.
      if (!fechaCompleta(valor)) {
        if (typeof valor === "string" && /^POR VERIFICAR\b/.test(valor) && typeof fuente?.texto === "string") {
          agregarObservacion(e, `${campo}: fuente=${serializar(fuente.texto)}; original=${serializar(fuente.valor)}`);
        }
        continue;
      }
      const motivo = conflictoEventoFecha(fuente, campo);
      if (!motivo) continue;
      const literal = fuente?.valor ?? valor;
      const mensaje = "POR VERIFICAR (evento del periodo no confirmado; ver observaciones)";
      e[campo] = mensaje;
      agregarObservacion(e, `${campo}: fuente=${serializar(fuente?.texto)}; original=${serializar(literal)}; ${motivo}`);
      revisar(revisiones, nProf, nExp, campo, fuente?.pagina_pdf, fuente?.texto,
        `${motivo}; original=${serializar(literal)}`);
      inciertos.add(nExp);
    }
    const prev = indicadoresTemporales(e);
    for (const campo of ["incluye_covid", "cert_antes_culminar"]) {
      if (e[campo] != null && e[campo] !== prev[campo]) {
        avisos.push({ severidad: "warning", tipo: "indicador_temporal_discrepante",
          mensaje: `${campo} recalculado desde fechas declaradas.`, referencia: `P${nProf} E${nExp}` });
      }
      e[campo] = prev[campo];
    }
    const inicioDeclarado = e.fecha_inicial ?? e.fecha_inicio;
    if (typeof inicioDeclarado === "string" && /^POR VERIFICAR\b/.test(inicioDeclarado)
      || typeof e.fecha_final === "string" && /^POR VERIFICAR\b/.test(e.fecha_final)) inciertos.add(nExp);
    // El alcance/ITEM se conserva: esta guard únicamente deja trazabilidad.
    if (e.proyecto_fuente && typeof e.proyecto_fuente === "object") e.proyecto_fuente = COPIA(e.proyecto_fuente);
    const normalizarRotulo = valor => String(valor ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
    const items = valor => [...normalizarRotulo(valor).matchAll(/\bITEM\s*(?:N(?:\s*[°º.]?)?\s*)?(\d+)\b/g)].map(m => Number(m[1]));
    if (e.proyecto_fuente && items(e.proyecto_fuente.texto).some(item => !items(e.proyecto).includes(item))) {
      const motivo = "alcance/ítem por verificar";
      agregarObservacion(e, `${motivo}; proyecto=${serializar(e.proyecto)}; fuente en página ${e.proyecto_fuente.pagina_pdf}: ${serializar(e.proyecto_fuente.texto)}`);
      revisar(revisiones, nProf, nExp, "proyecto", e.proyecto_fuente?.pagina_pdf, e.proyecto_fuente?.texto, motivo);
    }
  }
  for (const r of revisiones) {
    const aviso = { severidad: "warning", tipo: "hecho_por_verificar", mensaje: r.motivo,
      referencia: `P${r.n_prof} E${r.n_experiencia}` };
    if (!avisos.some(a => a.tipo === aviso.tipo && a.referencia === aviso.referencia && a.mensaje === aviso.mensaje)) avisos.push(aviso);
  }
  return { profesional, avisos, revisiones, periodosInciertos: [...inciertos].filter(x => x != null) };
}

module.exports = { prepararProfesional, fechaCompleta, indicadoresTemporales };
