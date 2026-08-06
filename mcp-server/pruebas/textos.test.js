/**
 * Pruebas de los textos que el MCP muestra en el chat.
 *
 * Dos cosas se vigilan aquí: que digan lo que hay que decir (dónde está el ZIP,
 * por qué falló, qué hacer después) y que NO hablen en jerga de sistemas — el
 * que lee es un evaluador de propuestas, no un integrador.
 */
import { strict as assert } from "node:assert";
import { describe, it } from "node:test";

import { textoBusqueda, textoDescargaEstado, textoDescargaIniciada } from "../textos.js";

// Palabras que no pueden aparecer en lo que ve el evaluador. («http» no está en
// la lista: la dirección de descarga del ZIP es un dato, no jerga.)
const JERGA = ["endpoint", "payload", "job_id", "polling", "backend", "JSON", "traceback", "base64", "request"];

function sinJerga(texto) {
  const bajo = texto.toLowerCase();
  const encontradas = JERGA.filter((p) => bajo.includes(p.toLowerCase()));
  assert.deepEqual(encontradas, [], `el texto usa jerga: ${encontradas.join(", ")}`);
}

const BUSQUEDA_OK = {
  ok: true,
  q: "hospital abancay",
  coincidencia: "nombre",
  base_mef_no_disponible: false,
  total: 2,
  resultados: [
    {
      cui: "2029145",
      snip: null,
      nombre: "CONSTRUCCION DEL SERVICIO DE EMERGENCIA DEL HOSPITAL GUILLERMO DIAZ DE LA VEGA DE ABANCAY",
      ubicacion: "ABANCAY, ABANCAY, APURIMAC",
      entidad: "MINISTERIO DE SALUD",
      situacion: "VIABLE",
      score: 100,
    },
    {
      cui: null,
      snip: "361313",
      nombre: "ELABORACION DEL EXPEDIENTE TECNICO",
      ubicacion: "ABANCAY, APURIMAC",
      entidad: "GOBIERNO REGIONAL APURIMAC",
      situacion: "CERRADO",
      score: 87.4,
    },
  ],
};

describe("textoBusqueda", () => {
  it("lista los candidatos con código, nombre, ubicación y entidad", () => {
    const t = textoBusqueda(BUSQUEDA_OK);
    assert.match(t, /CUI 2029145/);
    assert.match(t, /HOSPITAL GUILLERMO DIAZ DE LA VEGA DE ABANCAY/);
    assert.match(t, /ABANCAY, ABANCAY, APURIMAC/);
    assert.match(t, /MINISTERIO DE SALUD/);
    assert.match(t, /parecido 100%/);
    assert.match(t, /SNIP 361313/, "una inversión sin CUI se identifica por su SNIP");
    sinJerga(t);
  });

  it("un acierto por código lo dice, y no habla de parecidos", () => {
    const t = textoBusqueda({
      ok: true,
      q: "2029145",
      coincidencia: "codigo",
      base_mef_no_disponible: false,
      resultados: [{ cui: "2029145", nombre: "HOSPITAL X", ubicacion: "ABANCAY", entidad: "MINSA", score: 100 }],
    });
    assert.match(t, /El código 2029145 corresponde/);
    assert.doesNotMatch(t, /parecido/, "sobre un código exacto no hay parecido que discutir");
    sinJerga(t);
  });

  it("sin resultados explica qué hacer, no deja un vacío", () => {
    const t = textoBusqueda({ ok: true, q: "planta nuclear", resultados: [], total: 0, base_mef_no_disponible: false });
    assert.match(t, /Sin coincidencias/);
    assert.match(t, /localidad/);
  });

  it("prefiere el aviso del servidor cuando el texto es demasiado genérico", () => {
    const t = textoBusqueda({
      ok: true,
      q: "puesto de salud",
      resultados: [],
      base_mef_no_disponible: false,
      aviso: "El texto es demasiado genérico: agrega el nombre propio del establecimiento.",
    });
    assert.match(t, /demasiado genérico/);
  });

  it("la base ausente se explica, no se disfraza de «sin resultados»", () => {
    const t = textoBusqueda({
      ok: true,
      base_mef_no_disponible: true,
      resultados: [],
      aviso: "La base local de inversiones del MEF no está instalada en este equipo.",
    });
    assert.match(t, /no está instalada/);
  });

  it("un fallo de conexión se dice como fallo, no como «no hay obras»", () => {
    const t = textoBusqueda({ ok: false, error: "no se pudo conectar" });
    assert.match(t, /No se pudo buscar/);
    assert.doesNotMatch(t, /Sin coincidencias/);
  });
});

describe("textoDescargaIniciada", () => {
  it("da el número de seguimiento y avisa que tarda", () => {
    const t = textoDescargaIniciada({
      ok: true,
      cui: "2029145",
      descarga_id: "abc123",
      estado: "en_progreso",
      paso: "En cola: esperando turno para consultar InfoObras.",
    });
    assert.match(t, /CUI 2029145/);
    assert.match(t, /Número de seguimiento: abc123/);
    assert.match(t, /consultar_descarga_cui/);
    assert.match(t, /varios minutos/);
    sinJerga(t);
  });

  it("un fallo al iniciar se dice claro", () => {
    const t = textoDescargaIniciada({ ok: false, error: "El CUI debe ser un número." });
    assert.match(t, /No se pudo iniciar la descarga/);
  });
});

describe("textoDescargaEstado", () => {
  const listo = {
    ok: true,
    descarga_id: "abc123",
    cui: "2029145",
    estado: "listas",
    listo: true,
    obra_id: 111,
    nombre: "HOSPITAL X",
    descargados: 42,
    fallidos: 1,
    avisos: ["Informes de control: la consulta no pudo completarse."],
    zip_url: "http://127.0.0.1:8001/api/pivote/descargar-cui/abc123/zip",
  };

  it("al terminar dice dónde bajar el ZIP y NO manda el archivo", () => {
    const t = textoDescargaEstado(listo);
    assert.match(t, /42 documento\(s\)/);
    assert.match(t, /descargar-cui\/abc123\/zip/);
    assert.match(t, /NO se pueden mandar por el chat/);
    assert.match(t, /Informes de control/, "los avisos de la descarga se muestran");
    sinJerga(t);
  });

  it("en curso muestra el tramo y pide volver a consultar", () => {
    const t = textoDescargaEstado({
      ok: true,
      descarga_id: "abc123",
      cui: "2029145",
      estado: "en_progreso",
      paso: "Descargando los informes de control de la Contraloría.",
      descargados: 0,
      fallidos: 0,
      avisos: [],
    });
    assert.match(t, /En curso/);
    assert.match(t, /informes de control/i);
    assert.doesNotMatch(t, /zip/i, "no se ofrece un ZIP que todavía no existe");
    sinJerga(t);
  });

  it("un número de seguimiento inexistente se dice como tal", () => {
    const t = textoDescargaEstado({ ok: false, status_http: 404, error: { detail: "descarga no existe" } });
    assert.match(t, /número de seguimiento/);
    sinJerga(t);
  });

  it("el error dice el motivo y que se puede reintentar", () => {
    const t = textoDescargaEstado({
      ok: true,
      descarga_id: "abc123",
      cui: "9999999",
      estado: "error",
      paso: "Ese CUI no corresponde a ninguna obra publicada en InfoObras.",
      descargados: 0,
      fallidos: 0,
      avisos: [],
    });
    assert.match(t, /no corresponde a ninguna obra/);
    assert.match(t, /volver a pedirla/);
    sinJerga(t);
  });
});
