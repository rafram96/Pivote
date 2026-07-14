"""F0 — congela fixtures HTML+JSON del MEF para los tests offline de scraping/mef.py.
CUIs elegidos para cubrir los casos: completo, flaco (entidad no llenó), reformulado,
etiqueta de resolución distinta."""
import json
import re
from pathlib import Path

import requests

DEST = Path("tests/fixtures/mef")
DEST.mkdir(parents=True, exist_ok=True)

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"

# (cui, snip, nota)
CASOS = [
    ("2324482", "361313", "completo · 6 contratos · Yuyapichis (target del reformulado)"),
    ("2148076", "",       "flaco · entidad no llenó el 08-A"),
    ("2140959", "",       "reformulado viejo (su data vive en 2448758)"),
    ("2427358", "",       "PRONIS · etiqueta 'RESOLUCION JEFATURAL'"),
    ("2303684", "",       "completo · educación"),
]

idx = {}
for cui, snip, nota in CASOS:
    # 1) ficha de ejecución (08-A) — HTML
    html = s.get(f"https://ofi5.mef.gob.pe/invierte/ejecucion/verFichaEjecucion/{cui}", timeout=45).text
    (DEST / f"{cui}_ficha08a.html").write_text(html, encoding="utf-8")
    # 2) contratos SEACE — JSON (necesita snip; si no lo tengo, lo saco del propio HTML)
    if not snip:
        m = re.search(r"C[oó]digo SNIP\D+(\d{5,7})", re.sub(r"<[^>]+>", " ", html))
        snip = m.group(1) if m else ""
    contratos = []
    try:
        r = s.post("https://ofi5.mef.gob.pe/invierteWS/Ssi/traeContratoSeaceDWH",
                   data={"id": cui, "codsnip": snip or "0", "vers": "v2"},
                   headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
        contratos = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else []
    except Exception as e:  # noqa: BLE001
        contratos = [{"_error": str(e)[:80]}]
    (DEST / f"{cui}_contratos.json").write_text(
        json.dumps(contratos, ensure_ascii=False, indent=1), encoding="utf-8")
    idx[cui] = {"snip": snip, "nota": nota,
                "ficha_kb": round(len(html) / 1024),
                "n_contratos": len(contratos) if isinstance(contratos, list) else 0}
    print(f"  {cui} · snip {snip or '—'} · ficha {idx[cui]['ficha_kb']}KB · {idx[cui]['n_contratos']} contratos · {nota}")

(DEST / "INDEX.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
print("\nfixtures en", DEST.resolve())
