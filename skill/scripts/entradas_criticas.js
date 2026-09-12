"use strict";

// Una sola normalización/auditoría para el control preevaluación y el pegado.
// No interpreta documentos: exige al extractor datos y procedencia comprobables.
const primero = (...vs) => vs.find(v => v !== undefined && v !== null && v !== "") ?? null;
const numero = v => {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v !== "string" || !/^\d+(?:\.\d+)?$/.test(v.trim())) return null;
  const n = Number(v); return Number.isFinite(n) ? n : null;
};
const paginaValida = p => Number.isInteger(p) && p > 0;
const textoValido = t => typeof t === "string" && t.trim().length > 0;
const aviso = (tipo, mensaje, referencia) => ({ severidad: "critical", tipo, mensaje, referencia });

function requisitoPostorDe(bases) {
  const raw = bases.experiencia_postor_requisito || {};
  const fuente = raw.fuente || {};
  const respaldo = paginaValida(fuente.pagina_pdf) && textoValido(fuente.texto);
  const monto = numero(raw.monto);
  const valido = raw.estado === "encontrado" && monto !== null && monto >= 0 && raw.moneda === "PEN" && respaldo;
  const noAplica = raw.estado === "no_aplica" && raw.monto == null && respaldo;
  return {
    requisito: {
      monto_requerido: valido ? monto.toFixed(2) : null,
      requisito_estado: valido ? "encontrado" : noAplica ? "no_aplica" : "por_verificar",
      requisito_moneda: raw.moneda || null,
      requisito_fuente: { ...fuente },
    },
    avisos: valido || noAplica ? [] : [aviso("entrada_minimo_postor",
      "agent-bases: falta mínimo de experiencia del postor válido y sustentado (monto, moneda PEN, página física y texto), " +
      "o un no_aplica documentado. No usar cuantía, oferta o suma acreditada como mínimo. " +
      "Otras monedas/reglas ambiguas requieren revisión, no conversión implícita.", "bases.experiencia_postor_requisito")],
  };
}

function factorCrudoDe(bases) {
  const factores = bases.factores_evaluacion || {};
  return primero(bases.reglas_evaluacion?.factor_a, bases.factor_a,
    Array.isArray(factores) ? null : factores.factor_a,
    Array.isArray(factores) ? factores.find(f => /^\s*(?:FACTOR\s*)?A\b/i.test(String(f.factor || f.codigo || f.nombre || ""))) : null);
}

function factorADe(bases) {
  const raw = factorCrudoDe(bases);
  const aplica = (bases.personal_clave || []).some(c => c.factor_a_aplica === true || c.aplica === true);
  if ((!raw || raw.aplica === false) && !aplica) return { factor: null, avisos: [] };
  const errores = [];
  const f = raw && typeof raw === "object" ? raw : {};
  if (f.aplica === false && aplica) errores.push("contradicción entre factor no aplicable y cargos participantes");
  let dias = numero(primero(f.dias_adicionales_requeridos, f.minimo_adicional_dias));
  const unidades = { dia: 1, dias: 1, mes: 30, meses: 30, ano: 365, anos: 365 };
  const unidad = String(f.unidad_umbral_adicional || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  if (f.umbral_adicional_requerido != null || f.unidad_umbral_adicional != null) {
    const cantidad = numero(f.umbral_adicional_requerido);
    // Misma convención de cómputo que _minimo_exigido: mes=30, año=365,
    // redondeo superior. La equivalencia explícita de las bases tiene prioridad
    // al extraer la unidad; aquí no se interpreta ni se extraen números de prosa.
    const convertido = cantidad !== null && unidades[unidad] ? Math.ceil(cantidad * unidades[unidad]) : null;
    if (convertido === null || (dias !== null && dias !== convertido)) errores.push("unidad/umbral ausente o contradictorio");
    else dias = convertido;
  }
  if (!Number.isSafeInteger(dias) || dias < 0) errores.push("días adicionales no determinados");
  const tramos = Array.isArray(f.tramos) ? f.tramos.map(t => ({
    desde_porcentaje: numero(primero(t.desde_porcentaje, t.minimo_porcentaje, t.desde)),
    desde_inclusivo: t.desde_inclusivo,
    hasta_porcentaje: numero(primero(t.hasta_porcentaje, t.maximo_porcentaje, t.hasta)),
    hasta_inclusivo: t.hasta_inclusivo,
    puntaje: numero(primero(t.puntaje, t.puntos)),
  })) : [];
  if (!tramos.length) errores.push("sin tramos");
  const formaValida = tramos.every(t => [t.desde_porcentaje, t.hasta_porcentaje].every(v => v !== null && v >= 0 && v <= 100)
    && t.desde_porcentaje <= t.hasta_porcentaje
    && typeof t.desde_inclusivo === "boolean" && typeof t.hasta_inclusivo === "boolean"
    && t.puntaje !== null && t.puntaje >= 0);
  if (!formaValida) errores.push("tramos sin límites 0..100, inclusividad explícita o puntaje");
  if (formaValida && tramos.length) {
    const limites = [...new Set([0, 100, ...tramos.flatMap(t => [t.desde_porcentaje, t.hasta_porcentaje])])].sort((a, b) => a - b);
    const sondas = [...limites, ...limites.slice(1).map((v, i) => (v + limites[i]) / 2)];
    const contiene = (t, x) => (x > t.desde_porcentaje || x === t.desde_porcentaje && t.desde_inclusivo)
      && (x < t.hasta_porcentaje || x === t.hasta_porcentaje && t.hasta_inclusivo);
    if (sondas.some(x => tramos.filter(t => contiene(t, x)).length !== 1)) errores.push("tramos con huecos o solapamientos");
  }
  const folio = primero(f.folio, f.pagina, bases.metadata_concurso?.pagina_factores);
  if (!(paginaValida(folio) || typeof folio === "string" && /^[1-9]\d*(?:-[1-9]\d*)?$/.test(folio))) errores.push("sin página física del baremo");
  return errores.length ? { factor: null, avisos: [aviso("entrada_factor_a",
    `agent-bases: Factor A incompleto (${errores.join("; ")}). Volver a la tabla original; no inferir límites de una condición en prosa.`,
    "bases.reglas_evaluacion.factor_a")] } : {
    factor: { dias_adicionales_requeridos: dias, tramos, folio }, avisos: [],
  };
}

function normalizarBasesCriticas(bases) {
  const postor = requisitoPostorDe(bases);
  const factor = factorADe(bases);
  return { requisito: postor.requisito, reglas: { ...(bases.reglas_evaluacion || {}), factor_a: factor.factor },
    avisos: [...postor.avisos, ...factor.avisos] };
}

function totalPostorDesdeBases(requisito, anterior = {}) {
  const total = { ...anterior };
  // El evaluador no es fuente del mínimo. Tampoco dejar alias que permitan al
  // backend rescatar un mínimo antiguo cuando las bases nuevas se abstienen.
  for (const clave of ["monto_requerido", "requerido", "minimo", "monto_minimo"]) delete total[clave];
  return { ...total, ...requisito };
}

const normalizarTextoFecha = texto => String(texto || "")
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .toLowerCase().replace(/[ \t]+/g, " ").replace(/ *\n+ */g, "\n").trim();

/**
 * Comprueba el acontecimiento que describe el literal, sin extraer ni
 * corregir fechas. Una frase de periodo personal tiene prioridad únicamente
 * cuando es explícita; en caso mixto se devuelve una duda trazable.
 */
function conflictoEventoFecha(fuente, campo) {
  if (!["fecha_inicial", "fecha_final"].includes(campo)) return null;
  const literal = typeof fuente === "string" ? fuente : fuente?.texto ?? fuente?.literal ?? fuente?.rótulo;
  const texto = normalizarTextoFecha(literal);
  const plano = texto.replace(/\n/g, " ").replace(/\s+/g, " ").trim();
  const esperado = campo === "fecha_inicial" ? "inicio_servicio" : "fin_servicio";
  if (fuente && typeof fuente === "object" && fuente.evento != null && fuente.evento !== esperado) {
    return `el evento declarado (${fuente.evento}) no acredita ${esperado}`;
  }
  if (!texto) return null;
  const periodo = /\b(?:desde|del)\s+\d[^.]{0,100}(?:hasta|al)\s+\d/.test(plano);
  const verboPersonal = /\b(?:presto\s+servicios?|laboro|trabajo(?:\s+como)?|desempeno(?:\s+funciones)?|brindo\s+servicios?)\b/.test(plano);
  const rotuloPeriodo = /\b(?:periodo(?: de)? (?:servicios|trabajo|desempeno)|tiempo de servicios)\b/.test(plano);
  const personal = periodo && (verboPersonal || rotuloPeriodo);
  const finObra = /\b(?:fin|termino|culminacion|finalizacion|conclusion)\s+(?:de\s+)?(?:la\s+)?obra\b/.test(plano)
    || /\b(?:la\s+)?obra\s+(?:termino|culmino|finalizo|concluyo)\b/.test(plano);
  const inicioObra = /\b(?:inicio|inici[oó]|inicio de)\s+(?:de\s+)?(?:la\s+)?obra\b/.test(plano)
    || /\b(?:la\s+)?obra\s+(?:se\s+)?inicio\b/.test(plano);
  // Solo actos fechados con rótulo explícito; una mención incidental a
  // "orden", "aprobación" o "firma" no determina qué fecha se está usando.
  const acto = /(?:^|\n)\s*(?:fecha\s+de\s+(?:firma|suscripcion|emision|expedicion|orden(?:\s+de\s+servicio)?|aprobacion)|firma\s+del\s+contrato|orden\s+de\s+servicio)\s*[:\-]/.test(texto)
    || /(?:^|\n)\s*(?:emitid[ao]|firmad[ao]|expedid[ao])\s+(?:el|la)?\s*\d/.test(texto);
  if (finObra || inicioObra) {
    if (personal) return "el literal mezcla un evento de la obra con un periodo personal; no se puede decidir qué fecha usa para este campo (ambigüedad, releer la fuente)";
    return `el literal atribuye ${esperado} a un evento de la obra, no al periodo personal del profesional`;
  }
  if (acto) {
    if (personal) return null;
    return `el literal parece corresponder a firma/emisión/orden y no acredita ${esperado}`;
  }
  return null;
}

function auditarFechas(experiencias, nProf) {
  const avisos = [];
  for (const e of experiencias || []) {
    const ref = `P${nProf} E${e.n}`;
    for (const [campo, evento] of [["fecha_inicial", "inicio_servicio"], ["fecha_final", "fin_servicio"]]) {
      const valor = e[campo] ?? (campo === "fecha_inicial" ? e.fecha_inicio : null);
      if (valor == null || /^POR VERIFICAR\b/.test(valor) || /^\d{4}-(?:0[1-9]|1[0-2])(?:\s+.*)?$/.test(valor)) continue;
      const d = /^\d{4}-\d{2}-\d{2}$/.test(valor) ? new Date(`${valor}T00:00:00Z`) : new Date(NaN);
      if (!Number.isFinite(d.getTime()) || d.toISOString().slice(0, 10) !== valor) {
        avisos.push(aviso("entrada_fecha_formato", `agent-propuesta-profesional: ${campo} no es una fecha de calendario válida.`, ref));
        continue;
      }
      const fuente = e.fechas_fuente?.[campo];
      if (!fuente || !paginaValida(fuente.pagina_pdf) || !(e.paginas_pdf || []).includes(fuente.pagina_pdf)
        || !textoValido(fuente.texto) || !["visual", "texto_pdf_cotejado"].includes(fuente.metodo)) {
        avisos.push(aviso("entrada_fecha_fuente", `agent-propuesta-profesional: ${campo} requiere cotejo del periodo en la página original. OCR solo no confirma un día exacto.`, ref));
        continue;
      }
      if (fuente.valor !== valor) avisos.push(aviso("entrada_fecha_discrepante", `agent-propuesta-profesional: ${campo} difiere de su cotejo (${fuente.valor}). Revisar, no sustituir automáticamente.`, ref));
      if (fuente.evento !== evento) avisos.push(aviso("entrada_fecha_evento", `agent-propuesta-profesional: ${campo} debe acreditar ${evento}; fecha de orden/firma/emisión no acredita el periodo por sí sola.`, ref));
      if (fuente.evento === evento) {
        const conflicto = conflictoEventoFecha(fuente, campo);
        if (conflicto) avisos.push(aviso("entrada_fecha_evento_literal", `agent-propuesta-profesional: ${campo}: ${conflicto}. Revisar el literal, sin inferir ni sustituir la fecha.`, ref));
      }
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(e.fecha_inicial) && /^\d{4}-\d{2}-\d{2}$/.test(e.fecha_final) && e.fecha_final < e.fecha_inicial) {
      avisos.push(aviso("entrada_fecha_rango", "agent-propuesta-profesional: el fin precede al inicio; cotejar ambos extremos.", ref));
    }
  }
  return avisos;
}

module.exports = { normalizarBasesCriticas, factorADe, totalPostorDesdeBases, auditarFechas, conflictoEventoFecha };
