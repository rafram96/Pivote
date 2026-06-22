/**
 * Cliente HTTP del backend on-prem de InfoObras (Camino A del pivote).
 *
 * Se exporta aparte de `mcp.js` para poder EJERCERLO en pruebas sin levantar el
 * transporte stdio del MCP (ver `probar_contra_backend.js`).
 *
 * Endpoints reales del backend (FastAPI · backend/api/app.py):
 *   GET  /api/pivote/salud                    → estado de portales
 *   GET  /api/pivote/concursos                → lista
 *   POST /api/pivote/concursos    (JSON)      → crea  {concurso_id, …}
 *   POST /api/pivote/analizar     (multipart) → concurso_id + espejo(file) + excel(file) + origen  ⇒ {job_id}
 *   GET  /api/pivote/jobs/{id}                → estado del job
 *
 * Requiere Node 18+ (fetch, FormData, Blob, Buffer globales).
 */

export function crearCliente({ serverUrl, token = null, timeoutMs = 60000, log = () => {} }) {
  const base = String(serverUrl).replace(/\/$/, "");

  async function pedir(metodo, ruta, { json, form } = {}) {
    const url = `${base}/${ruta.replace(/^\//, "")}`;
    const headers = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    let body;
    if (form) {
      body = form; // NO fijar Content-Type: fetch pone el boundary del multipart
    } else if (json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(json);
    }
    // GET es idempotente → se reintenta ante fallos transitorios de conexión
    // (p.ej. el primer fetch que tropieza con IPv6 ::1 en Windows). POST NO se
    // reintenta, para no arriesgar un doble envío.
    const intentos = metodo === "GET" ? 3 : 1;
    let ultimo = "sin respuesta";
    for (let i = 0; i < intentos; i++) {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), timeoutMs);
      log(`→ ${metodo} ${url}${i ? ` (intento ${i + 1})` : ""}`);
      try {
        const resp = await fetch(url, { method: metodo, headers, body, signal: ctrl.signal });
        const texto = await resp.text();
        let data;
        try { data = JSON.parse(texto); } catch { data = { _raw: texto }; }
        log(`← ${resp.status} (${texto.length} bytes)`);
        return { status: resp.status, ok: resp.ok, data };
      } catch (err) {
        ultimo = err?.name === "AbortError" ? `timeout tras ${timeoutMs}ms` : String(err?.message || err);
        log(`✗ error: ${ultimo}`);
      } finally {
        clearTimeout(t);
      }
      if (i < intentos - 1) await new Promise((r) => setTimeout(r, 300));
    }
    return { status: 0, ok: false, data: { error: ultimo } };
  }

  return {
    serverUrl: base,

    async probarConexion() {
      const r = await pedir("GET", "/api/pivote/salud");
      return { conexion_exitosa: r.ok, server_url: base, status_http: r.status, portales: r.data };
    },

    async listarConcursos() {
      const r = await pedir("GET", "/api/pivote/concursos");
      return { ok: r.ok, status_http: r.status, concursos: r.data };
    },

    /**
     * Sube el análisis: resuelve el concurso (lo crea si no se pasa concurso_id)
     * y POSTea el espejo + Excel como multipart al backend real.
     */
    async subirAnalisis({ json_espejo, excel_base64 = null, certificados_base64 = null, concurso_id = null, concurso = null }) {
      if (!json_espejo || typeof json_espejo !== "object") {
        return { ok: false, error: "json_espejo es obligatorio (objeto)" };
      }

      // 1) resolver/crear el concurso
      if (!concurso_id) {
        const meta = json_espejo._meta || {};
        const nomenclatura =
          (concurso && concurso.nomenclatura) || meta.concurso || meta.analisis_id || "Concurso sin nombre";
        const cr = await pedir("POST", "/api/pivote/concursos", {
          json: {
            nomenclatura,
            entidad: concurso && concurso.entidad,
            fecha_presentacion: concurso && concurso.fecha_presentacion,
          },
        });
        if (!cr.ok) return { ok: false, etapa: "crear_concurso", status_http: cr.status, error: cr.data };
        concurso_id = cr.data && cr.data.concurso_id;
      }

      // 2) multipart → /analizar (espejo + excel son File en el backend)
      const fd = new FormData();
      fd.set("concurso_id", concurso_id);
      fd.set("origen", "mcp");
      fd.set("espejo", new Blob([JSON.stringify(json_espejo)], { type: "application/json" }), "espejo.json");
      const xls = excel_base64
        ? new Blob([Buffer.from(excel_base64, "base64")], {
            type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          })
        : new Blob([""], { type: "application/octet-stream" });
      fd.set("excel", xls, excel_base64 ? "analisis.xlsx" : "pendiente.xlsx");
      // certificados: ZIP de PDFs P{n}_E{m}.pdf (constancias recortadas por la skill) — opcional
      if (certificados_base64) {
        fd.set(
          "certificados",
          new Blob([Buffer.from(certificados_base64, "base64")], { type: "application/zip" }),
          "certificados.zip"
        );
      }

      const r = await pedir("POST", "/api/pivote/analizar", { form: fd });
      if (!r.ok) return { ok: false, etapa: "analizar", concurso_id, status_http: r.status, error: r.data };

      const job_id = r.data && r.data.job_id;
      return {
        ok: true,
        concurso_id,
        job_id,
        siguiente: `consultar_estado("${job_id}")`,
        excel_url: `${base}/api/pivote/jobs/${job_id}/excel`,
        zip_url: `${base}/api/pivote/jobs/${job_id}/zip`,
      };
    },

    async consultarEstado(job_id) {
      if (!job_id) return { ok: false, error: "job_id es obligatorio" };
      const r = await pedir("GET", `/api/pivote/jobs/${encodeURIComponent(job_id)}`);
      if (!r.ok) return { ok: false, status_http: r.status, error: r.data };
      const j = r.data || {};
      const items = Array.isArray(j.items_revision) ? j.items_revision : [];
      return {
        ok: true,
        job_id,
        estado: j.estado ?? null,
        etapa_actual: j.etapa_actual ?? null,
        pendientes_revision: items.filter((it) => !it.resuelto).length,
        excel_url: `${base}/api/pivote/jobs/${job_id}/excel`,
        zip_url: `${base}/api/pivote/jobs/${job_id}/zip`,
      };
    },
  };
}
