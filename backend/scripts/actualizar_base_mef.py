"""
Actualiza la base local MEF que alimenta el resolver de CUI.

Construye una carga inmutable con:
  - inversiones.csv.gz: índice compacto para búsqueda difusa en RAM;
  - inversiones.sqlite: ficha enriquecida para lookup exacto por CUI/SNIP;
  - entidades_publicas.csv: catálogo normalizado;
  - metadata.json: trazabilidad, checksums y métricas.

La publicación se hace con un manifest atómico. Una carga incompleta nunca
reemplaza la última versión buena.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import data_dir  # noqa: E402

csv.field_size_limit(10_000_000)

BASE_URL = "https://fs.datosabiertos.mef.gob.pe/datastorefiles/"
FUENTES = [
    ("DETALLE_INVERSIONES.csv", "ACTIVO"),
    ("CIERRE_INVERSIONES.csv", "CERRADA"),
    ("INVERSIONES_DESACTIVADAS.csv", "DESACTIVADA"),
]

MIN_UNION = 400_000
MIN_POR_FUENTE = 50_000
REINTENTOS_DESCARGA = 3
RETENER_CARGAS = 2
MAX_CAIDA_RELATIVA = 0.25
MIN_BYTES_DESCARGA = 10 * 1024 * 1024

_RE_SIGLA = re.compile(r"[-–]\s*([A-Z]{2,8})\s*$")

_DDL = """
CREATE TABLE inversiones (
    identity_key TEXT PRIMARY KEY,
    cui TEXT,
    snip TEXT,
    nombre TEXT NOT NULL,
    nombre_norm TEXT NOT NULL,
    estado_dataset TEXT NOT NULL,
    estado TEXT,
    situacion TEXT,
    entidad TEXT,
    entidad_norm TEXT,
    ubigeo TEXT,
    dpto TEXT,
    prov TEXT,
    dist TEXT,
    nivel TEXT,
    sector TEXT,
    funcion TEXT,
    tipo_inversion TEXT,
    tipologia TEXT,
    modalidad TEXT,
    monto_viable TEXT,
    costo_actualizado TEXT,
    fecha_registro TEXT,
    fecha_viabilidad TEXT,
    expediente_tecnico TEXT,
    opmi TEXT,
    uf TEXT,
    uei TEXT,
    uep TEXT,
    fuente TEXT NOT NULL,
    fila_origen INTEGER NOT NULL
);
CREATE INDEX inversiones_cui_idx ON inversiones(cui) WHERE cui <> '';
CREATE INDEX inversiones_snip_idx ON inversiones(snip) WHERE snip <> '';
CREATE INDEX inversiones_entidad_idx ON inversiones(entidad_norm);
"""

_SQL_INSERT = """
INSERT OR IGNORE INTO inversiones (
    identity_key, cui, snip, nombre, nombre_norm, estado_dataset, estado,
    situacion, entidad, entidad_norm, ubigeo, dpto, prov, dist, nivel, sector,
    funcion, tipo_inversion, tipologia, modalidad, monto_viable,
    costo_actualizado, fecha_registro, fecha_viabilidad, expediente_tecnico,
    opmi, uf, uei, uep, fuente, fila_origen
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def _col(fieldnames: list[str] | None, *candidatos: str) -> str | None:
    """Primera columna presente, por nombre exacto e insensible a mayúsculas."""
    up = {c.upper(): c for c in (fieldnames or [])}
    for cand in candidatos:
        if cand.upper() in up:
            return up[cand.upper()]
    return None


def _valor(fila: dict, columna: str | None) -> str:
    return (fila.get(columna) or "").strip() if columna else ""


def _decimal_texto(valor: str) -> str:
    """Normaliza un decimal sin introducir errores binarios; vacío queda vacío."""
    valor = (valor or "").strip()
    if not valor:
        return ""
    try:
        numero = Decimal(valor)
        if not numero.is_finite():
            raise InvalidOperation
        return format(numero, "f")
    except InvalidOperation as exc:
        raise ValueError(f"monto no parseable: {valor!r}") from exc


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _load_id() -> str:
    ahora = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ahora}-{uuid.uuid4().hex[:8]}"


@contextmanager
def _bloqueo_exclusivo(dir_dest: Path):
    """Impide dos publicaciones simultáneas, también fuera del wrapper Windows."""
    dir_dest.mkdir(parents=True, exist_ok=True)
    ruta = dir_dest / ".actualizar.lock"
    fh = ruta.open("a+b")
    adquirido = False
    try:
        if os.name == "nt":
            import msvcrt
            if ruta.stat().st_size == 0:
                fh.write(b"0")
                fh.flush()
            fh.seek(0)
            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("ya existe una actualización MEF en ejecución") from exc
            adquirido = True
        else:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("ya existe una actualización MEF en ejecución") from exc
            adquirido = True
        yield
    finally:
        try:
            if adquirido and os.name == "nt":
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            elif adquirido:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def _descargar(
    destino_tmp: Path,
    *,
    reintentos: int = REINTENTOS_DESCARGA,
    espera=time.sleep,
) -> None:
    """Descarga streaming con retry/backoff. Nunca publica un parcial."""
    import requests

    destino_tmp.mkdir(parents=True, exist_ok=True)
    for archivo, _ in FUENTES:
        url = BASE_URL + archivo
        final = destino_tmp / archivo
        parcial = destino_tmp / f"{archivo}.parcial"
        ultimo_error: Exception | None = None
        for intento in range(1, reintentos + 1):
            parcial.unlink(missing_ok=True)
            try:
                print(f"  descargando {archivo} (intento {intento}/{reintentos}) …",
                      flush=True)
                with requests.get(url, stream=True, timeout=(30, 600)) as r:
                    r.raise_for_status()
                    total = 0
                    with parcial.open("wb") as fh:
                        for chunk in r.iter_content(chunk_size=1 << 20):
                            if chunk:
                                fh.write(chunk)
                                total += len(chunk)
                if total < MIN_BYTES_DESCARGA:
                    raise RuntimeError(
                        f"descarga sospechosamente corta ({total} bytes) para {archivo}")
                os.replace(parcial, final)
                print(f"    {total/1e6:.0f} MB", flush=True)
                break
            except Exception as exc:  # requests expone varias subclases
                ultimo_error = exc
                parcial.unlink(missing_ok=True)
                if intento == reintentos:
                    raise RuntimeError(
                        f"no se pudo descargar {archivo} tras {reintentos} intentos"
                    ) from exc
                demora = (2 ** (intento - 1)) + random.uniform(0, 0.5)
                print(f"    fallo: {exc}; reintento en {demora:.1f}s", flush=True)
                espera(demora)
        if ultimo_error and not final.exists():
            raise ultimo_error


def _columnas(r: csv.DictReader) -> dict[str, str | None]:
    f = r.fieldnames
    return {
        "cui": _col(f, "CODIGO_UNICO"),
        "snip": _col(f, "CODIGO_SNIP", "COD_SNIP"),
        "nombre": _col(f, "NOMBRE_INVERSION"),
        "estado": _col(f, "ESTADO"),
        "situacion": _col(f, "SITUACION"),
        "ubigeo": _col(f, "UBIGEO"),
        "dpto": _col(f, "DEPARTAMENTO"),
        "prov": _col(f, "PROVINCIA"),
        "dist": _col(f, "DISTRITO"),
        "entidad": _col(f, "ENTIDAD"),
        "nivel": _col(f, "NIVEL"),
        "sector": _col(f, "SECTOR"),
        "funcion": _col(f, "FUNCION"),
        "tipo_inversion": _col(f, "TIPO_INVERSION"),
        "tipologia": _col(f, "DES_TIPOLOGIA"),
        "modalidad": _col(f, "DES_MODALIDAD"),
        "monto_viable": _col(f, "MONTO_VIABLE"),
        "costo_actualizado": _col(f, "COSTO_ACTUALIZADO"),
        "fecha_registro": _col(f, "FECHA_REGISTRO"),
        "fecha_viabilidad": _col(f, "FECHA_VIABILIDAD"),
        "expediente_tecnico": _col(f, "EXPEDIENTE_TECNICO"),
        "opmi": _col(f, "NOMBRE_OPMI", "NOM_OPMI"),
        "uf": _col(f, "NOMBRE_UF", "NOM_UF"),
        "uei": _col(f, "NOMBRE_UEI", "NOM_UEI"),
        "uep": _col(f, "NOMBRE_UEP", "NOM_UEP"),
    }


def _validar_columnas(archivo: str, cols: dict[str, str | None]) -> None:
    requeridas = (
        "cui", "snip", "nombre", "estado", "situacion", "entidad", "nivel",
        "sector", "funcion", "tipo_inversion", "tipologia", "modalidad",
        "monto_viable", "costo_actualizado", "fecha_registro",
        "fecha_viabilidad", "expediente_tecnico", "opmi", "uf", "uei", "uep",
    )
    faltan = [k for k in requeridas
              if cols.get(k) is None]
    if faltan:
        raise ValueError(f"{archivo}: faltan columnas requeridas: {', '.join(faltan)}")


def _metadata_activa(dir_dest: Path) -> dict | None:
    manifest = dir_dest / "manifest.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        load_id = str(data["load_id"])
        if data.get("ruta") != f"cargas/{load_id}":
            return None
        return json.loads(
            (dir_dest / "cargas" / load_id / "metadata.json").read_text(
                encoding="utf-8"))
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _validar_drift(meta: dict, anterior: dict | None) -> list[str]:
    """Bloquea caídas bruscas; cambios no destructivos quedan como advertencia."""
    if not anterior:
        return []
    avisos: list[str] = []
    prev_fuentes = anterior.get("filas_por_fuente") or {}
    for archivo, actual in meta["filas_por_fuente"].items():
        previo = int(prev_fuentes.get(archivo) or 0)
        if previo and actual < previo * (1 - MAX_CAIDA_RELATIVA):
            raise ValueError(
                f"{archivo}: caída de volumen {previo:,} → {actual:,} "
                f"(>{MAX_CAIDA_RELATIVA:.0%})")
        if previo and actual > previo * 1.5:
            avisos.append(
                f"{archivo}: aumento de volumen {previo:,} → {actual:,}")
        prev_headers = set((anterior.get("cabeceras") or {}).get(archivo) or [])
        headers = set(meta["cabeceras"].get(archivo) or [])
        nuevas = sorted(headers - prev_headers)
        retiradas = sorted(prev_headers - headers)
        if nuevas:
            avisos.append(f"{archivo}: columnas nuevas: {', '.join(nuevas)}")
        if retiradas:
            avisos.append(f"{archivo}: columnas retiradas: {', '.join(retiradas)}")
    return avisos


def _procesar(
    dir_csv: Path,
    dir_dest: Path,
    *,
    min_union: int = MIN_UNION,
    min_por_fuente: int = MIN_POR_FUENTE,
    retener_cargas: int = RETENER_CARGAS,
    identificador: str | None = None,
) -> dict:
    """Construye y publica una carga inmutable; devuelve su metadata."""
    dir_dest.mkdir(parents=True, exist_ok=True)
    cargas = dir_dest / "cargas"
    cargas.mkdir(exist_ok=True)
    load_id = identificador or _load_id()
    staging = cargas / f".{load_id}.tmp"
    final = cargas / load_id
    if staging.exists() or final.exists():
        raise FileExistsError(f"load_id ya existe: {load_id}")
    staging.mkdir()

    f_inv = staging / "inversiones.csv.gz"
    f_ent = staging / "entidades_publicas.csv"
    f_db = staging / "inversiones.sqlite"
    f_meta = staging / "metadata.json"
    filas_por_fuente: dict[str, int] = {}
    cabeceras: dict[str, list[str]] = {}
    fuentes_meta: dict[str, dict] = {}
    cuis_distintos: set[str] = set()
    identidades: set[str] = set()
    entidades: dict[str, str] = {}
    duplicados = 0
    anterior = _metadata_activa(dir_dest)

    db = sqlite3.connect(f_db)
    try:
        db.executescript(_DDL)
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        with gzip.open(f_inv, "wt", encoding="utf-8", newline="") as gz:
            w = csv.writer(gz)
            w.writerow([
                "cui", "snip", "nombre", "estado_dataset", "situacion",
                "ubigeo", "dpto", "prov", "dist", "entidad",
            ])
            for archivo, tag in FUENTES:
                ruta = dir_csv / archivo
                if not ruta.is_file():
                    raise FileNotFoundError(f"no encontrado: {ruta}")
                n = 0
                sin_identidad = 0
                sin_nombre = 0
                with ruta.open(encoding="utf-8-sig", newline="") as f:
                    r = csv.DictReader(f)
                    cols = _columnas(r)
                    _validar_columnas(archivo, cols)
                    cabeceras[archivo] = list(r.fieldnames or [])
                    for fila_origen, fila in enumerate(r, start=2):
                        cui = _valor(fila, cols["cui"])
                        snip = _valor(fila, cols["snip"])
                        nombre = _valor(fila, cols["nombre"])
                        if not cui and not snip:
                            sin_identidad += 1
                            continue
                        if not nombre:
                            sin_nombre += 1
                        identity_key = f"CUI:{cui}" if cui else f"SNIP:{snip}"
                        if identity_key in identidades:
                            duplicados += 1
                        else:
                            identidades.add(identity_key)
                        entidad = _valor(fila, cols["entidad"])
                        situacion = _valor(fila, cols["situacion"])
                        w.writerow([
                            cui, snip, nombre, tag, situacion,
                            _valor(fila, cols["ubigeo"]),
                            _valor(fila, cols["dpto"]),
                            _valor(fila, cols["prov"]),
                            _valor(fila, cols["dist"]),
                            entidad,
                        ])
                        db.execute(_SQL_INSERT, (
                            identity_key, cui, snip, nombre, _norm(nombre), tag,
                            _valor(fila, cols["estado"]), situacion,
                            entidad, _norm(entidad),
                            _valor(fila, cols["ubigeo"]),
                            _valor(fila, cols["dpto"]),
                            _valor(fila, cols["prov"]),
                            _valor(fila, cols["dist"]),
                            _valor(fila, cols["nivel"]),
                            _valor(fila, cols["sector"]),
                            _valor(fila, cols["funcion"]),
                            _valor(fila, cols["tipo_inversion"]),
                            _valor(fila, cols["tipologia"]),
                            _valor(fila, cols["modalidad"]),
                            _decimal_texto(_valor(fila, cols["monto_viable"])),
                            _decimal_texto(_valor(fila, cols["costo_actualizado"])),
                            _valor(fila, cols["fecha_registro"]),
                            _valor(fila, cols["fecha_viabilidad"]),
                            _valor(fila, cols["expediente_tecnico"]),
                            _valor(fila, cols["opmi"]),
                            _valor(fila, cols["uf"]),
                            _valor(fila, cols["uei"]),
                            _valor(fila, cols["uep"]),
                            archivo, fila_origen,
                        ))
                        if cui:
                            cuis_distintos.add(cui)
                        for concepto in ("entidad", "opmi", "uf", "uei", "uep"):
                            nom = _norm(_valor(fila, cols[concepto]))
                            if len(nom) > 5 and nom not in entidades:
                                m = _RE_SIGLA.search(nom)
                                entidades[nom] = m.group(1) if m else ""
                        n += 1
                if sin_identidad:
                    raise ValueError(
                        f"{archivo}: {sin_identidad} filas sin identidad")
                filas_por_fuente[archivo] = n
                fuentes_meta[archivo] = {
                    "filas": n,
                    "filas_sin_nombre": sin_nombre,
                    "bytes": ruta.stat().st_size,
                    "sha256": _sha256(ruta),
                    "columnas": len(r.fieldnames or []),
                }
                print(f"  {archivo}: {n:,} filas", flush=True)
        db.commit()
        db.execute("PRAGMA optimize")
        resultado = db.execute("PRAGMA integrity_check").fetchone()
        if not resultado or resultado[0] != "ok":
            raise RuntimeError(f"SQLite integrity_check falló: {resultado}")
    except BaseException:
        db.close()
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass

    total = sum(filas_por_fuente.values())
    cortas = [a for a, n in filas_por_fuente.items() if n < min_por_fuente]
    if total < min_union or cortas:
        shutil.rmtree(staging, ignore_errors=True)
        raise ValueError(
            f"validación FALLIDA (unión={total:,} < {min_union:,}; "
            f"fuentes cortas={cortas})")

    with f_ent.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entidad", "sigla"])
        for nombre in sorted(entidades):
            w.writerow([nombre, entidades[nombre]])

    meta = {
        "schema_version": 1,
        "load_id": load_id,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "filas_por_fuente": filas_por_fuente,
        "filas_total": total,
        "identidades": len(identidades),
        "duplicados": duplicados,
        "cuis_distintos": len(cuis_distintos),
        "entidades": len(entidades),
        "fuentes": fuentes_meta,
        "cabeceras": cabeceras,
        "urls": {a: BASE_URL + a for a, _ in FUENTES},
        "artefactos": {},
    }
    try:
        meta["avisos_drift"] = _validar_drift(meta, anterior)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    for ruta in (f_inv, f_ent, f_db):
        meta["artefactos"][ruta.name] = {
            "bytes": ruta.stat().st_size,
            "sha256": _sha256(ruta),
        }
    f_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                      encoding="utf-8")

    os.replace(staging, final)
    manifest_tmp = dir_dest / "manifest.json.tmp"
    manifest_tmp.write_text(json.dumps({
        "load_id": load_id,
        "ruta": f"cargas/{load_id}",
        "publicado_en": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(manifest_tmp, dir_dest / "manifest.json")

    _purgar_cargas(cargas, activo=load_id, retener=retener_cargas)
    return meta


def _purgar_cargas(cargas: Path, *, activo: str, retener: int) -> None:
    """Retiene las N cargas publicadas más recientes. Nunca borra la activa."""
    candidatas = sorted(
        (p for p in cargas.iterdir() if p.is_dir() and not p.name.startswith(".")),
        key=lambda p: p.name,
        reverse=True,
    )
    conservar = {p.name for p in candidatas[:max(1, retener)]}
    conservar.add(activo)
    for ruta in candidatas:
        if ruta.name not in conservar:
            shutil.rmtree(ruta)


def main() -> None:
    ap = argparse.ArgumentParser(description="Actualiza la base local del MEF.")
    ap.add_argument("--desde-dir", type=Path, default=None,
                    help="usa CSV locales de esta carpeta (sin descargar)")
    ap.add_argument("--destino", type=Path, default=None,
                    help="salida (default: <PIVOTE_DATA_DIR>/referencia/mef)")
    args = ap.parse_args()

    dir_dest = Path(args.destino or (data_dir() / "referencia" / "mef"))
    if args.desde_dir:
        dir_csv = Path(args.desde_dir)
        print(f"Procesando CSV locales de {dir_csv}")
    else:
        dir_csv = dir_dest / "tmp"
        print(f"Descargando de {BASE_URL} a {dir_csv}")
        _descargar(dir_csv)

    with _bloqueo_exclusivo(dir_dest):
        meta = _procesar(dir_csv, dir_dest)
    print(
        f"\nOK · carga {meta['load_id']} · {meta['filas_total']:,} filas · "
        f"{meta['cuis_distintos']:,} CUIs · {meta['entidades']:,} entidades"
    )
    print(f"    en {dir_dest}")


if __name__ == "__main__":
    main()
