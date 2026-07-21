"""
Actualiza la base local de inversiones del MEF que alimenta el resolver de CUI.

Descarga (o toma de disco) los 3 CSV públicos del Banco de Inversiones del MEF,
los consolida en una tabla ligera y un catálogo de entidades públicas, y deja todo
en `<PIVOTE_DATA_DIR>/referencia/mef/`. La escritura es ATÓMICA (tmp + os.replace):
si algo falla o la validación de volumen no pasa, la versión anterior queda intacta.

Fuentes (utf-8-sig, campos entrecomillados con saltos de línea embebidos):
  DETALLE_INVERSIONES.csv       — inversiones ACTIVAS
  CIERRE_INVERSIONES.csv        — inversiones CERRADAS
  INVERSIONES_DESACTIVADAS.csv  — inversiones DESACTIVADAS

Uso:
  python -m scripts.actualizar_base_mef                 # descarga desde el MEF
  python -m scripts.actualizar_base_mef --desde-dir DIR # usa copias locales (sin red)
  python -m scripts.actualizar_base_mef --destino DIR   # override del dir de salida
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import data_dir  # noqa: E402

# los CSV traen celdas enormes (memorias descriptivas entrecomilladas con saltos
# de línea); sin subir el límite, csv revienta con "field larger than field limit".
csv.field_size_limit(10_000_000)

BASE_URL = "https://fs.datosabiertos.mef.gob.pe/datastorefiles/"

# (archivo, etiqueta estado_dataset). El nombre de la columna SNIP difiere entre
# archivos (CODIGO_SNIP vs COD_SNIP) → se resuelve por lista de candidatos, no fijo.
FUENTES = [
    ("DETALLE_INVERSIONES.csv", "ACTIVO"),
    ("CIERRE_INVERSIONES.csv", "CERRADA"),
    ("INVERSIONES_DESACTIVADAS.csv", "DESACTIVADA"),
]

COLS_ENTIDAD = ("ENTIDAD", "NOMBRE_UEP", "NOMBRE_OPMI", "NOMBRE_UF", "NOMBRE_UEI")

# umbrales de cordura: una descarga truncada o un CSV vacío no debe reemplazar la
# base buena. Valores holgados respecto a los tamaños reales (148k/117k/228k).
MIN_UNION = 400_000
MIN_POR_FUENTE = 50_000

# sigla al final del nombre de una entidad: "… - AGN", "… - INABIF". Palabra corta
# en mayúsculas tras guion final. Sirve para el match exacto por sigla del resolver.
_RE_SIGLA = re.compile(r"[-–]\s*([A-Z]{2,8})\s*$")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def _col(fieldnames: list[str], *candidatos: str) -> str | None:
    """Primera columna presente (por nombre exacto, insensible a mayúsculas)."""
    up = {c.upper(): c for c in (fieldnames or [])}
    for cand in candidatos:
        if cand.upper() in up:
            return up[cand.upper()]
    return None


def _descargar(destino_tmp: Path) -> None:
    """Descarga los 3 CSV a `destino_tmp` (streaming). Falla ruidoso si un archivo
    baja demasiado corto para ser el CSV real."""
    import requests

    destino_tmp.mkdir(parents=True, exist_ok=True)
    for archivo, _ in FUENTES:
        url = BASE_URL + archivo
        parcial = destino_tmp / (archivo + ".parcial")
        print(f"  descargando {archivo} …", flush=True)
        with requests.get(url, stream=True, timeout=(30, 600)) as r:
            r.raise_for_status()
            total = 0
            with open(parcial, "wb") as fh:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        fh.write(chunk)
                        total += len(chunk)
        if total < 10 * 1024 * 1024:  # los reales pesan 116-244 MB
            raise SystemExit(f"descarga sospechosamente corta ({total} bytes) para {archivo}")
        os.replace(parcial, destino_tmp / archivo)
        print(f"    {total/1e6:.0f} MB", flush=True)


def _procesar(dir_csv: Path, dir_dest: Path) -> dict:
    """Lee los 3 CSV desde `dir_csv`, escribe los artefactos a tmp dentro de
    `dir_dest` y, si la validación de volumen pasa, los mueve a su nombre final.
    Devuelve la metadata. NO toca los artefactos previos si algo falla."""
    dir_dest.mkdir(parents=True, exist_ok=True)
    tmp_inv = dir_dest / "inversiones.csv.gz.tmp"
    tmp_ent = dir_dest / "entidades_publicas.csv.tmp"
    tmp_meta = dir_dest / "metadata.json.tmp"

    filas_por_fuente: dict[str, int] = {}
    cuis_distintos: set[str] = set()
    entidades: dict[str, str] = {}  # nombre_norm -> sigla (o "")

    try:
        with gzip.open(tmp_inv, "wt", encoding="utf-8", newline="") as gz:
            w = csv.writer(gz)
            w.writerow(["cui", "snip", "nombre", "estado_dataset", "situacion",
                        "ubigeo", "dpto", "prov", "dist", "entidad"])
            for archivo, tag in FUENTES:
                ruta = dir_csv / archivo
                if not ruta.exists():
                    raise SystemExit(f"no encontrado: {ruta}")
                n = 0
                with open(ruta, encoding="utf-8-sig", newline="") as f:
                    r = csv.DictReader(f)
                    c_cui = _col(r.fieldnames, "CODIGO_UNICO")
                    c_snip = _col(r.fieldnames, "CODIGO_SNIP", "COD_SNIP")
                    c_nom = _col(r.fieldnames, "NOMBRE_INVERSION")
                    c_sit = _col(r.fieldnames, "SITUACION")
                    c_ubi = _col(r.fieldnames, "UBIGEO")
                    c_dep = _col(r.fieldnames, "DEPARTAMENTO")
                    c_pro = _col(r.fieldnames, "PROVINCIA")
                    c_dis = _col(r.fieldnames, "DISTRITO")
                    c_ent = _col(r.fieldnames, "ENTIDAD")
                    cols_ent = [_col(r.fieldnames, k) for k in COLS_ENTIDAD]
                    for fila in r:
                        cui = (fila.get(c_cui) or "").strip()
                        snip = (fila.get(c_snip) or "").strip() if c_snip else ""
                        w.writerow([
                            cui, snip,
                            (fila.get(c_nom) or "").strip(),
                            tag,
                            (fila.get(c_sit) or "").strip() if c_sit else "",
                            (fila.get(c_ubi) or "").strip() if c_ubi else "",
                            (fila.get(c_dep) or "").strip() if c_dep else "",
                            (fila.get(c_pro) or "").strip() if c_pro else "",
                            (fila.get(c_dis) or "").strip() if c_dis else "",
                            (fila.get(c_ent) or "").strip() if c_ent else "",
                        ])
                        if cui:
                            cuis_distintos.add(cui)
                        for c in cols_ent:
                            if not c:
                                continue
                            nom = _norm(fila.get(c) or "")
                            if len(nom) > 5 and nom not in entidades:
                                m = _RE_SIGLA.search(nom)
                                entidades[nom] = m.group(1) if m else ""
                        n += 1
                filas_por_fuente[archivo] = n
                print(f"  {archivo}: {n:,} filas", flush=True)
    except BaseException:
        tmp_inv.unlink(missing_ok=True)
        raise

    # validación de volumen ANTES de sobrescribir: base corta = base sospechosa.
    total = sum(filas_por_fuente.values())
    problemas = [a for a, n in filas_por_fuente.items() if n < MIN_POR_FUENTE]
    if total < MIN_UNION or problemas:
        tmp_inv.unlink(missing_ok=True)
        raise SystemExit(
            f"validación FALLIDA (unión={total:,} < {MIN_UNION:,} o fuentes cortas "
            f"{problemas}); se conserva la versión anterior")

    # catálogo de entidades
    with open(tmp_ent, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entidad", "sigla"])
        for nom in sorted(entidades):
            w.writerow([nom, entidades[nom]])

    meta = {
        "fecha": date.today().isoformat(),
        "filas_por_fuente": filas_por_fuente,
        "filas_total": total,
        "cuis_distintos": len(cuis_distintos),
        "entidades": len(entidades),
        "urls": {a: BASE_URL + a for a, _ in FUENTES},
    }
    tmp_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # commit atómico de los 3 artefactos
    os.replace(tmp_inv, dir_dest / "inversiones.csv.gz")
    os.replace(tmp_ent, dir_dest / "entidades_publicas.csv")
    os.replace(tmp_meta, dir_dest / "metadata.json")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="Actualiza la base local del MEF.")
    ap.add_argument("--desde-dir", type=Path, default=None,
                    help="usa CSV locales de esta carpeta (sin descargar)")
    ap.add_argument("--destino", type=Path, default=None,
                    help="carpeta de salida (default: <PIVOTE_DATA_DIR>/referencia/mef)")
    args = ap.parse_args()

    dir_dest = args.destino or (data_dir() / "referencia" / "mef")
    dir_dest = Path(dir_dest)

    if args.desde_dir:
        dir_csv = Path(args.desde_dir)
        print(f"Procesando CSV locales de {dir_csv}")
    else:
        dir_csv = dir_dest / "tmp"
        print(f"Descargando de {BASE_URL} a {dir_csv}")
        _descargar(dir_csv)

    meta = _procesar(dir_csv, dir_dest)
    print(f"\nOK · {meta['filas_total']:,} filas · {meta['cuis_distintos']:,} CUIs "
          f"distintos · {meta['entidades']:,} entidades")
    print(f"    en {dir_dest}")


if __name__ == "__main__":
    main()
