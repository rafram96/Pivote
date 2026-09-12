#!/usr/bin/env node
"use strict";
const fs = require("fs");
const path = require("path");
const { z } = require("zod");

const Codigo = z.string().regex(/^[0-9]{1,10}$/);
const Huella = z.string().regex(/^[a-f0-9]{64}$/);
const CasoId = z.string().regex(/^[1-9][0-9]*:[1-9][0-9]*(?::s[1-9][0-9]*)?$/);
const Caso = z.object({
  caso_id: CasoId, n_prof: z.number().int().positive(), n_exp: z.number().int().positive(),
  subobra: z.number().int().positive().nullable(),
  declarado: z.record(z.unknown()), contexto_backend: z.record(z.unknown()),
  accion: z.enum(["investigar", "comprobar_fichas"]), disparadores: z.array(z.string()),
}).passthrough().superRefine((c, ctx) => {
  const clave = `${c.n_prof}:${c.n_exp}${c.subobra ? `:s${c.subobra}` : ""}`;
  if (clave !== c.caso_id) ctx.addIssue({ code: "custom", message: "P/E/subobra no coincide con caso_id" });
});
const Paquete = z.object({
  version: z.literal(1), job_id: z.string().regex(/^[a-f0-9]{12}$/),
  huella_contexto: Huella, tipo_evaluacion: z.enum(["obras", "expedientes"]),
  casos: z.array(Caso), omitidos: z.array(z.record(z.unknown())),
}).passthrough();
const Procedimiento = z.object({
  ocid: z.string().min(1).nullable(), nomenclatura: z.string().min(1).nullable(),
  contrato_numero: z.string().min(1).nullable(),
  rol: z.enum(["ejecucion", "supervision", "expediente", "consorcio", "otro"]).nullable(),
}).strict();
const Candidato = z.object({
  id: z.string().min(1), cui: Codigo.nullable(),
  obra_id: z.number().int().positive().max(2147483647).nullable(),
  intervencion: z.string().min(1).nullable(), procedimiento: Procedimiento.nullable(),
  evidencias: z.array(z.string().min(1)), motivo: z.string().min(1),
}).strict();
const Evidencia = z.object({
  id: z.string().min(1), campo: z.enum(["cui", "intervencion", "obra_id", "contrato", "naturaleza_privada", "otro"]),
  fuente: z.string().min(1), tipo_fuente: z.enum(["oficial", "propuesta", "secundaria"]),
  url: z.string().url().regex(/^https?:\/\//).nullable(),
  ubicacion: z.string().min(1), pagina_pdf: z.number().int().positive().nullable(),
  cita: z.string().min(3).max(1500), acceso: z.enum(["leido", "no_leido"]),
}).strict().superRefine((e, ctx) => {
  if (e.tipo_fuente !== "propuesta" && !e.url)
    ctx.addIssue({ code: "custom", message: "Una fuente externa necesita URL" });
});
const Resultado = z.object({
  version: z.literal(1), job_id: z.string(), huella_contexto: Huella, caso_id: CasoId,
  estado: z.enum(["asociacion_propuesta", "ambiguo", "sin_candidato", "no_aplica_publica", "fuente_no_respondio", "no_ejecutado"]),
  seleccion_propuesta: z.object({ candidato_id: z.string().min(1), motivo: z.string().min(1) }).strict().nullable(),
  candidatos: z.array(Candidato), evidencias: z.array(Evidencia),
  discrepancias: z.array(z.string().min(1)), faltantes: z.array(z.string().min(1)),
  consultas: z.array(z.object({
    fuente: z.string().min(1), consulta: z.string().min(1),
    estado: z.enum(["leido", "sin_resultados", "error_http", "fuente_no_respondio", "no_consultado"]),
    detalle: z.string().min(1),
  }).strict()),
  motivo: z.string().min(1), limites: z.array(z.string().min(1)),
}).strict();

function validarPaquete(valor) {
  const p = Paquete.parse(valor);
  if (new Set(p.casos.map(c => c.caso_id)).size !== p.casos.length)
    throw new Error("El paquete duplica casos");
  return p;
}

function planificar(valor, listados = {}) {
  const paquete = validarPaquete(valor);
  const tareas = [], sinAlerta = [];
  for (const c of paquete.casos) {
    const cui = String(c.contexto_backend.cui || "");
    const listado = listados[cui];
    const razones = [...c.disparadores];
    // También cubrir paquetes anteriores: una ficha única no audita el contrato.
    if (String(c.contexto_backend.via || "").toUpperCase() === "RUC")
      razones.push("contratista_no_demuestra_intervencion");
    if (c.contexto_backend.seace?.estado === "seleccionado")
      razones.push("contrato_requiere_contraste_de_rol_y_emisor");
    if (String(c.contexto_backend.via || "").toUpperCase() === "PRIVADA"
        || c.contexto_backend.estado === "privada")
      razones.push("naturaleza_privada_requiere_cotejo_del_proyecto");
    if (c.contexto_backend.documentos_prioritarios?.length)
      razones.push("documentos_prioritarios_requieren_lectura");
    if (c.accion === "comprobar_fichas" && !razones.length) {
      const obra = c.contexto_backend.obra || {};
      const ficha = c.contexto_backend.ficha || {};
      const oid = String(obra.obra_id || ficha.obra_id || ficha.codigo_infoobras || "");
      const filas = listado?.candidatos;
      const leido = listado?.ok !== false && listado?.estado === "disponible"
        && listado.cui_consultado === cui && Array.isArray(filas);
      if (leido && filas.length === 1 && oid && String(filas[0]?.obra_id) === oid) {
        sinAlerta.push({ caso_id: c.caso_id, estado: "sin_alerta_en_listado_consultado",
          listado_completo_verificado: listado.listado_completo_verificado === true,
          advertencia: "No es comprobación de correspondencia con el certificado ni de exactitud del CUI." });
        continue;
      }
      razones.push(!leido ? "listado_no_comprobado" : filas.length > 1
        ? "varias_fichas_del_cui" : "ficha_vigente_no_unica_en_consulta");
    }
    tareas.push({ ...c, disparadores: [...new Set(razones)], listado_infoobras: listado || null });
  }
  return { tareas, sin_alerta_en_listado: sinAlerta, omitidos: paquete.omitidos };
}

function validarResultado(valor, paquete, casoId) {
  paquete = validarPaquete(paquete);
  const r = Resultado.parse(valor);
  if (r.job_id !== paquete.job_id || r.huella_contexto !== paquete.huella_contexto
      || r.caso_id !== casoId || !paquete.casos.some(c => c.caso_id === casoId))
    throw new Error("Resultado de otro job, caso o contexto; no se puede consolidar");
  const evidencias = new Map(r.evidencias.map(e => [e.id, e]));
  const candidatos = new Map(r.candidatos.map(c => [c.id, c]));
  if (evidencias.size !== r.evidencias.length || candidatos.size !== r.candidatos.length)
    throw new Error("IDs locales de evidencia o candidato duplicados");
  for (const c of r.candidatos) {
    if (c.evidencias.some(id => !evidencias.has(id))) throw new Error("Referencia a evidencia inexistente");
  }
  if (r.estado === "asociacion_propuesta") {
    const c = candidatos.get(r.seleccion_propuesta?.candidato_id);
    if (!c || !c.cui || !c.intervencion) throw new Error("Una propuesta necesita candidato, CUI e intervención");
    const campos = new Set(c.evidencias.map(id => evidencias.get(id))
      .filter(e => e.acceso === "leido" && e.tipo_fuente !== "secundaria").map(e => e.campo));
    const necesarios = ["cui", "intervencion"];
    if (c.obra_id !== null) necesarios.push("obra_id");
    if (c.procedimiento && Object.values(c.procedimiento).some(v => v !== null)) necesarios.push("contrato");
    if (necesarios.some(campo => !campos.has(campo)))
      throw new Error("La propuesta carece de evidencia leída para alguno de sus identificadores");
    const oficiales = new Set(c.evidencias.map(id => evidencias.get(id))
      .filter(e => e.acceso === "leido" && e.tipo_fuente === "oficial").map(e => e.campo));
    if (necesarios.filter(campo => campo !== "intervencion").some(campo => !oficiales.has(campo)))
      throw new Error("Identificadores externos requieren evidencia oficial leída; el certificado solo los declara");
    if ((!c.obra_id || !c.procedimiento || !Object.values(c.procedimiento).some(v => v !== null)) && !r.faltantes.length)
      throw new Error("Ficha o contratación desconocida debe quedar explícita en faltantes");
  } else if (r.seleccion_propuesta !== null) {
    throw new Error("Una abstención no puede dejar selección propuesta");
  }
  if (r.estado === "no_aplica_publica" && !r.evidencias.some(e => e.campo === "naturaleza_privada"
      && e.acceso === "leido" && e.tipo_fuente !== "secundaria"))
    throw new Error("Naturaleza privada necesita evidencia sobre el proyecto, no solo el emisor");
  if (r.estado !== "no_ejecutado" && !r.consultas.length)
    throw new Error("Registrar consultas realizadas o indicar no_ejecutado");
  // Registro de cobertura, no un clasificador semántico ni prueba de lectura real.
  const caso = paquete.casos.find(c => c.caso_id === casoId);
  for (const d of caso.contexto_backend.documentos_prioritarios || []) {
    if (r.estado === "no_ejecutado") break;
    const consultas = r.consultas.filter(c => c.consulta === `documento:${d.referencia}`);
    if (consultas.length !== 1)
      throw new Error(`Registrar una consulta por documento prioritario: ${d.referencia}`);
    if (consultas[0].estado === "leido" && (!d.url || !r.evidencias.some(e =>
      e.url === d.url && e.tipo_fuente === "oficial" && e.acceso === "leido"
      && e.pagina_pdf !== null)))
      throw new Error(`Documento leído requiere URL, página física y cita del contenido: ${d.referencia}`);
  }
  return r;
}

const nombreCaso = c => `P${c.n_prof}_E${c.n_exp}${c.subobra ? `_S${c.subobra}` : ""}`;
const leer = p => JSON.parse(fs.readFileSync(p, "utf8").replace(/^\uFEFF/, ""));
const escribir = (p, valor) => fs.writeFileSync(p, JSON.stringify(valor, null, 2) + "\n", { flag: "wx" });

function finalizarCaso(carpeta, casoId) {
  const { paquete: valor } = leer(path.join(carpeta, "lote.json"));
  const paquete = validarPaquete(valor);
  const caso = paquete.casos.find(c => c.caso_id === casoId);
  if (!caso) throw new Error("Caso ajeno al lote");
  const destino = path.join(carpeta, nombreCaso(caso));
  const borrador = leer(path.join(destino, "borrador.json"));
  const metadatos = { version: 1, job_id: paquete.job_id,
    huella_contexto: paquete.huella_contexto, caso_id: casoId };
  // No corregir silenciosamente una respuesta que declara pertenecer a otro lote.
  for (const [campo, esperado] of Object.entries(metadatos))
    if (Object.hasOwn(borrador, campo) && borrador[campo] !== esperado)
      throw new Error(`Metadato contradictorio: ${campo}`);
  const resultado = validarResultado({ ...borrador, ...metadatos }, paquete, casoId);
  escribir(path.join(destino, "resultado.json"), resultado);
  return resultado;
}

function prepararCarpeta(paquete, listados, carpeta) {
  paquete = validarPaquete(paquete);
  const plan = planificar(paquete, listados);
  fs.mkdirSync(carpeta); // Directorio nuevo: no sobreescribir investigación previa.
  for (const caso of plan.tareas) {
    const destino = path.join(carpeta, nombreCaso(caso));
    fs.mkdirSync(destino);
    escribir(path.join(destino, "entrada.json"), {
      version: 1, job_id: paquete.job_id, huella_contexto: paquete.huella_contexto,
      tipo_evaluacion: paquete.tipo_evaluacion, ...caso,
    });
  }
  escribir(path.join(carpeta, "plan.json"), plan);
  escribir(path.join(carpeta, "lote.json"), { paquete, listados });
  return plan;
}

function consolidarCarpeta(carpeta) {
  const { paquete, listados } = leer(path.join(carpeta, "lote.json"));
  const plan = planificar(paquete, listados);
  const resultados = [], pendientes = [];
  const pendientesDocumentales = [];
  for (const caso of plan.tareas) {
    const archivo = path.join(carpeta, nombreCaso(caso), "resultado.json");
    if (!fs.existsSync(archivo)) { pendientes.push(caso.caso_id); continue; }
    resultados.push(validarResultado(leer(archivo), paquete, caso.caso_id));
  }
  for (const caso of plan.tareas) {
    const r = resultados.find(r => r.caso_id === caso.caso_id);
    for (const d of caso.contexto_backend.documentos_prioritarios || []) {
      if (r?.estado !== "no_ejecutado" && r?.consultas.some(c =>
        c.consulta === `documento:${d.referencia}` && c.estado === "leido")) continue;
      pendientesDocumentales.push({ caso_id: caso.caso_id, referencia: d.referencia,
        url: d.url || null, motivo: r?.consultas.find(c =>
          c.consulta === `documento:${d.referencia}`)?.detalle || "Sin lectura registrada" });
    }
  }
  return { version: 1, job_id: paquete.job_id, huella_contexto: paquete.huella_contexto,
    cobertura: pendientes.length || resultados.some(r => r.estado === "no_ejecutado") ? "parcial" : "completa",
    aplicado_al_job: false, resultados, pendientes,
    pendientes_documentales: pendientesDocumentales,
    sin_alerta_en_listado: plan.sin_alerta_en_listado, omitidos: plan.omitidos,
    limite: "Validación estructural, no prueba que las citas sean verdaderas ni que la asociación sea correcta." };
}

module.exports = { validarPaquete, planificar, validarResultado, prepararCarpeta, consolidarCarpeta, finalizarCaso };
if (require.main === module) {
  try {
    const [comando, archivo, listados, salida] = process.argv.slice(2);
    if (comando === "preparar" && archivo && listados && salida) {
      const plan = prepararCarpeta(leer(archivo), leer(listados), salida);
      console.log(`${plan.tareas.length} casos para investigar; ${plan.sin_alerta_en_listado.length} sin alerta en el listado consultado (no verificados).`);
    } else if (comando === "finalizar" && archivo && listados && !salida) {
      finalizarCaso(archivo, listados);
      console.log("Resultado validado y vinculado al lote. Nada aplicado al job.");
    } else if (comando === "consolidar" && archivo && !salida) {
      const resultado = consolidarCarpeta(archivo);
      escribir(listados || path.join(archivo, "investigacion_identidad.json"), resultado);
      console.log(`${resultado.cobertura}: ${resultado.resultados.length} resultados, ${resultado.pendientes.length} sin respuesta. Nada aplicado al job.`);
      if (resultado.cobertura === "parcial") process.exitCode = 2;
    } else throw new Error("Uso: investigacion_identidad.js preparar <paquete.json> <listados.json> <carpeta_nueva> | finalizar <carpeta_lote> <caso_id> | consolidar <carpeta_lote> [salida_nueva.json]");
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
