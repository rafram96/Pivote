"""
DEMO — Buscador interactivo SUNAT + InfoObras (server local, sin dependencias).

Levanta un servidor HTTP local (stdlib, sin Flask) que sirve una UI de búsqueda
y expone 4 endpoints que llaman a los scrapers de Alpamayo-InfoObras en vivo:

  GET /api/sunat/buscar?q=<razon social>   → candidatos por similitud de nombre
  GET /api/sunat/ruc?ruc=<11 dígitos>       → detalle + representantes legales
  GET /api/infoobras/buscar?q=<nombre obra> → candidatos por nombre
  GET /api/infoobras/cui?cui=<código>       → detalle completo de la obra

Pensado para la demo con el cliente: Manuel escribe un nombre o un RUC/CUI,
escoge de la lista de coincidencias, y ve el detalle enriquecido — igual que
hará el backend on-prem.

Uso:
    venv/Scripts/python.exe src/tools/demo_server.py
    → abre http://127.0.0.1:8765 en el navegador

Reusa src/scraping de Alpamayo (NO clona). Datos públicos, en vivo.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ALPAMAYO = Path(r"C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras\Alpamayo-InfoObras")
if not ALPAMAYO.exists():
    print(f"ERROR: no se encuentra repo Alpamayo en {ALPAMAYO}", file=sys.stderr)
    sys.exit(1)
sys.path.insert(0, str(ALPAMAYO))

from src.scraping.sunat import buscar_por_razon_social  # noqa: E402
from src.scraping.infoobras import buscar_obras_por_nombre  # noqa: E402

# Reusa la lógica de detalle ya escrita en demo_scraping.py
sys.path.insert(0, str(Path(__file__).parent))
from demo_scraping import demo_sunat, demo_infoobras  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
# Sirve la presentación unificada (arquitectura + demo con buscador embebido).
# Fallback al buscador simple si la presentación no existe.
DOCS = Path(__file__).resolve().parents[2] / "docs"
UI_PATH = DOCS / "presentaciones" / "pivote_presentacion.html"
if not UI_PATH.exists():
    UI_PATH = Path(__file__).parent / "demo_buscador.html"


# ──────────────────────────────────────────────────────────────────────────
# Búsquedas (candidatos)
# ──────────────────────────────────────────────────────────────────────────
def buscar_sunat(q: str) -> list[dict]:
    cands = buscar_por_razon_social(q) or []
    return [
        {
            "ruc": c.get("ruc"),
            "razon_social": c.get("razon_social"),
            "ubicacion": c.get("ubicacion"),
            "estado": c.get("estado"),
        }
        for c in cands
        if c.get("ruc")
    ]


def buscar_infoobras(q: str) -> list[dict]:
    raw = buscar_obras_por_nombre(q) or []
    out = []
    for o in raw:
        cui = str(o.get("codSnip") or "").strip()
        # Descartar filas basura de InfoObras (warmup: cui vacío, "0" o muy corto)
        if not cui.isdigit() or len(cui) < 3 or int(cui) == 0:
            continue
        out.append({
            "cui": cui,
            "nombre": o.get("nombrObra"),
            "entidad": o.get("nombreEntidad"),
            "ejecutor": o.get("nombreEjecutor"),
            "monto": o.get("montoObraSoles"),
            "departamento": o.get("nombrDepartamento"),
            "modalidad": o.get("nombrModalidad"),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# HTTP handler
# ──────────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # logs más limpios
        sys.stderr.write("  · %s\n" % (fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        q = (qs.get("q", [""])[0]).strip()

        try:
            if path in ("/", "/index.html"):
                self._html(UI_PATH.read_text(encoding="utf-8"))
                return

            if path == "/api/sunat/buscar":
                if len(q) < 3:
                    self._json({"error": "Escribe al menos 3 caracteres"}, 400)
                    return
                self._json({"candidatos": buscar_sunat(q)})
                return

            if path == "/api/sunat/ruc":
                ruc = (qs.get("ruc", [""])[0]).strip()
                if not re.match(r"^\d{11}$", ruc):
                    self._json({"error": "RUC debe tener 11 dígitos"}, 400)
                    return
                self._json(demo_sunat(ruc))
                return

            if path == "/api/infoobras/buscar":
                if len(q) < 4:
                    self._json({"error": "Escribe al menos 4 caracteres"}, 400)
                    return
                self._json({"candidatos": buscar_infoobras(q)})
                return

            if path == "/api/infoobras/cui":
                cui = (qs.get("cui", [""])[0]).strip()
                if not re.match(r"^\d{3,12}$", cui):
                    self._json({"error": "CUI inválido"}, 400)
                    return
                self._json(demo_infoobras(cui))
                return

            self._json({"error": "ruta no encontrada"}, 404)
        except Exception as e:  # noqa: BLE001
            logging.exception("Error sirviendo %s", path)
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if not UI_PATH.exists():
        print(f"ERROR: falta la UI {UI_PATH}", file=sys.stderr)
        return 1

    url = f"http://{HOST}:{PORT}"
    print("━" * 64)
    print("  DEMO — Buscador SUNAT + InfoObras  (server local)")
    print(f"  Abriendo:  {url}")
    print("  Ctrl+C para detener.")
    print("━" * 64)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Detenido.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
