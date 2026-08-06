/**
 * Pruebas del cliente HTTP del MCP — sin backend y sin red: se sustituye
 * `globalThis.fetch` por un doble que registra lo pedido y responde lo que el
 * caso necesita.
 *
 *   node --test pruebas/          (o `npm test` desde mcp-server/)
 *
 * Lo que se ejerce es el CONTRATO con el backend: qué ruta se llama, con qué
 * parámetros, y cómo se traduce la respuesta. La redacción de los mensajes se
 * prueba aparte, en textos.test.js.
 */
import { strict as assert } from "node:assert";
import { after, beforeEach, describe, it } from "node:test";

import { crearCliente } from "../cliente.js";

const BASE = "http://127.0.0.1:8001";
const fetchReal = globalThis.fetch;
let pedidos = [];

function responder(status, data) {
  globalThis.fetch = async (url, opciones = {}) => {
    pedidos.push({ url: String(url), metodo: opciones.method, cuerpo: opciones.body });
    return { ok: status >= 200 && status < 300, status, text: async () => JSON.stringify(data) };
  };
}

beforeEach(() => {
  pedidos = [];
});

after(() => {
  globalThis.fetch = fetchReal;
});

const cli = () => crearCliente({ serverUrl: BASE });

// ── buscar_cui ───────────────────────────────────────────────────────────────

describe("buscarCui", () => {
  it("arma la consulta con los filtros que sí se pasaron", async () => {
    responder(200, { q: "hospital abancay", resultados: [], total: 0 });
    await cli().buscarCui({ q: " hospital abancay ", dpto: "Apurímac", prov: "", limite: 5 });

    const url = new URL(pedidos[0].url);
    assert.equal(url.pathname, "/api/pivote/mef/buscar");
    assert.equal(url.searchParams.get("q"), "hospital abancay");
    assert.equal(url.searchParams.get("dpto"), "Apurímac");
    assert.equal(url.searchParams.get("limite"), "5");
    assert.equal(url.searchParams.has("prov"), false, "un filtro vacío no se manda");
    assert.equal(url.searchParams.has("dist"), false);
  });

  it("devuelve los resultados del servidor tal cual, con ok", async () => {
    responder(200, {
      q: "hospital abancay",
      coincidencia: "nombre",
      total: 1,
      base_mef_no_disponible: false,
      resultados: [{ cui: "2029145", nombre: "HOSPITAL X", ubicacion: "ABANCAY, APURIMAC", score: 100 }],
    });
    const r = await cli().buscarCui({ q: "hospital abancay" });
    assert.equal(r.ok, true);
    assert.equal(r.resultados[0].cui, "2029145");
    assert.equal(r.coincidencia, "nombre");
  });

  it("no llama al servidor si el texto es demasiado corto", async () => {
    responder(200, {});
    const r = await cli().buscarCui({ q: "h" });
    assert.equal(r.ok, false);
    assert.equal(pedidos.length, 0);
  });

  it("un 400 del servidor llega como no-ok, sin lanzar", async () => {
    responder(400, { detail: "limite debe estar entre 1 y 50" });
    const r = await cli().buscarCui({ q: "hospital", limite: 999 });
    assert.equal(r.ok, false);
    assert.equal(r.status_http, 400);
  });
});

// ── descargar por CUI ────────────────────────────────────────────────────────

describe("descargarPorCui", () => {
  it("postea el CUI y devuelve el número de seguimiento y la dirección del ZIP", async () => {
    responder(201, { descarga_id: "abc123", estado: "en_progreso", paso: "En cola: esperando turno." });
    const r = await cli().descargarPorCui({ cui: "2029145", fecha_inicio: "2020-01-01" });

    assert.equal(pedidos[0].metodo, "POST");
    assert.equal(new URL(pedidos[0].url).pathname, "/api/pivote/descargar-cui");
    assert.deepEqual(JSON.parse(pedidos[0].cuerpo), {
      cui: "2029145",
      fecha_inicio: "2020-01-01",
      fecha_fin: null,
    });
    assert.equal(r.ok, true);
    assert.equal(r.descarga_id, "abc123");
    assert.equal(r.zip_url, `${BASE}/api/pivote/descargar-cui/abc123/zip`);
  });

  it("rechaza un CUI que no es número sin molestar al servidor", async () => {
    responder(201, {});
    const r = await cli().descargarPorCui({ cui: "el del hospital" });
    assert.equal(r.ok, false);
    assert.equal(pedidos.length, 0);
  });
});

describe("consultarDescargaCui", () => {
  it("traduce el estado del servidor y arma la dirección del ZIP", async () => {
    responder(200, {
      descarga_id: "abc123",
      cui: "2029145",
      estado: "listas",
      paso: "Listo: 42 documento(s) en el ZIP.",
      obra_id: 111,
      nombre: "HOSPITAL X",
      descargados: 42,
      fallidos: 1,
      avisos: ["Informes de control: la consulta no pudo completarse."],
    });
    const r = await cli().consultarDescargaCui("abc123");
    assert.equal(r.ok, true);
    assert.equal(r.listo, true);
    assert.equal(r.descargados, 42);
    assert.deepEqual(r.avisos, ["Informes de control: la consulta no pudo completarse."]);
    assert.equal(r.zip_url, `${BASE}/api/pivote/descargar-cui/abc123/zip`);
  });

  it("en curso NO es listo", async () => {
    responder(200, { descarga_id: "abc123", estado: "en_progreso", paso: "Descargando las valorizaciones." });
    const r = await cli().consultarDescargaCui("abc123");
    assert.equal(r.listo, false);
    assert.equal(r.estado, "en_progreso");
  });

  it("un 404 llega como no-ok", async () => {
    responder(404, { detail: "descarga no existe" });
    const r = await cli().consultarDescargaCui("no-existe");
    assert.equal(r.ok, false);
    assert.equal(r.status_http, 404);
  });

  it("sin número de seguimiento no se llama al servidor", async () => {
    responder(200, {});
    const r = await cli().consultarDescargaCui("");
    assert.equal(r.ok, false);
    assert.equal(pedidos.length, 0);
  });
});
