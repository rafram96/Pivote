/**
 * Servidor HTTP de prueba — simula el backend on-prem de InfoObras.
 *
 * Propósito: validar que un MCP local lanzado por Cowork puede alcanzar
 * este servidor (que en producción correría en la red del cliente, no
 * expuesto a internet) y recibir respuesta.
 *
 * Sin dependencias — solo módulos nativos de Node (http).
 *
 * Endpoints:
 *   GET  /health           → { ok: true, ... }   (test de conectividad puro)
 *   POST /echo             → devuelve el body recibido (test ida y vuelta)
 *   POST /subir_y_validar  → simula el flujo real: recibe {excel, json},
 *                            devuelve un reporte de validación FALSO
 *                            (faltantes, alertas) con la forma del real.
 *
 * Configuración por env var:
 *   PORT   (default 8090)
 *   HOST   (default 0.0.0.0 — escucha en todas las interfaces, incluida la
 *           IP LAN, para poder probar desde otra máquina de la red)
 *
 * Uso:
 *   node server.js
 *   PORT=9000 HOST=0.0.0.0 node server.js
 */
import http from "node:http";
import os from "node:os";

const PORT = parseInt(process.env.PORT || "8090", 10);
const HOST = process.env.HOST || "0.0.0.0";

// ── Helpers ────────────────────────────────────────────────────────────────

function enviarJSON(res, status, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function leerBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    const LIMITE = 50 * 1024 * 1024; // 50 MB — propuestas grandes
    req.on("data", (c) => {
      size += c.length;
      if (size > LIMITE) {
        reject(new Error("body excede 50MB"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

function listarIPsLAN() {
  const ifaces = os.networkInterfaces();
  const ips = [];
  for (const nombre of Object.keys(ifaces)) {
    for (const iface of ifaces[nombre] || []) {
      if (iface.family === "IPv4" && !iface.internal) {
        ips.push({ interfaz: nombre, ip: iface.address });
      }
    }
  }
  return ips;
}

function ahora() {
  // Date dentro de Node está permitido (no es el sandbox de workflows)
  return new Date().toISOString();
}

// ── Reporte de validación simulado ───────────────────────────────────────────
// Forma que tendrá el reporte REAL del refactor (faltantes, alertas SUNAT/
// InfoObras). Aquí es 100% falso — solo para probar el transporte.

function reporteFalso(payload) {
  const nExperiencias =
    (payload && payload.json && Array.isArray(payload.json.experiencias)
      ? payload.json.experiencias.length
      : null);

  return {
    recibido_ok: true,
    timestamp: ahora(),
    tamanos: {
      excel_bytes: payload?.excel ? String(payload.excel).length : 0,
      json_keys: payload?.json ? Object.keys(payload.json).length : 0,
      experiencias_detectadas: nExperiencias,
    },
    // Reporte SIMULADO — en producción esto vendría del validador + scrapers
    validacion: {
      faltantes: [
        { tipo: "experiencia_omitida", detalle: "(simulado) fila 7 sin folio" },
      ],
      alertas_sunat: [
        {
          tipo: "firmante_verificado",
          detalle: "(simulado) Danitza Echandía = Gerente General confirmado",
        },
      ],
      alertas_infoobras: [
        {
          tipo: "paralizacion",
          detalle: "(simulado) obra con 2 meses paralizados en el periodo",
        },
      ],
    },
    nota: "RESPUESTA SIMULADA — el servidor de prueba solo valida transporte, no procesa de verdad.",
  };
}

// ── Router ───────────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const ruta = url.pathname;
  const metodo = req.method;
  console.error(`[${ahora()}] ${metodo} ${ruta} desde ${req.socket.remoteAddress}`);

  // CORS abierto (por si se prueba desde un navegador en la LAN)
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (metodo === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  try {
    if (metodo === "GET" && ruta === "/health") {
      enviarJSON(res, 200, {
        ok: true,
        servicio: "infoobras-server-prueba",
        timestamp: ahora(),
        escuchando_en: { host: HOST, port: PORT },
        ips_lan: listarIPsLAN(),
      });
      return;
    }

    if (metodo === "POST" && ruta === "/echo") {
      const raw = await leerBody(req);
      let parsed = raw;
      try {
        parsed = JSON.parse(raw);
      } catch {
        /* dejar como string si no es JSON */
      }
      enviarJSON(res, 200, {
        ok: true,
        eco: parsed,
        bytes_recibidos: Buffer.byteLength(raw),
        timestamp: ahora(),
      });
      return;
    }

    if (metodo === "POST" && ruta === "/subir_y_validar") {
      const raw = await leerBody(req);
      let payload;
      try {
        payload = JSON.parse(raw);
      } catch (e) {
        enviarJSON(res, 400, { ok: false, error: "body no es JSON válido" });
        return;
      }
      enviarJSON(res, 200, reporteFalso(payload));
      return;
    }

    enviarJSON(res, 404, { ok: false, error: `ruta no encontrada: ${metodo} ${ruta}` });
  } catch (err) {
    enviarJSON(res, 500, { ok: false, error: String(err?.message || err) });
  }
});

server.listen(PORT, HOST, () => {
  console.error("─".repeat(60));
  console.error("  Servidor de prueba InfoObras (simula backend on-prem)");
  console.error("─".repeat(60));
  console.error(`  Escuchando en:  http://${HOST}:${PORT}`);
  console.error("  IPs de esta máquina en la LAN:");
  for (const { interfaz, ip } of listarIPsLAN()) {
    console.error(`     • ${ip}  (${interfaz})  →  http://${ip}:${PORT}/health`);
  }
  console.error("  Endpoints:");
  console.error("     GET  /health");
  console.error("     POST /echo");
  console.error("     POST /subir_y_validar");
  console.error("─".repeat(60));
});
