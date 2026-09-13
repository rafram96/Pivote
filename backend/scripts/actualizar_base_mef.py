"""
Actualiza la base local MEF que alimenta el resolver de CUI.

Construye una carga inmutable con:
  - inversiones.csv.gz: índice compacto para búsqueda difusa en RAM;
  - PostgreSQL `mef.investments`: ficha enriquecida por CUI/SNIP;
  - entidades_publicas.csv: catálogo normalizado;
  - metadata.json: trazabilidad, checksums y métricas.

La publicación se hace con un manifest atómico. Una carga incompleta nunca
reemplaza la última versión buena.

Cada corrida —termine bien o mal— queda anotada en `bitacora.json` junto al
manifest (`resolucion/bitacora_mef.py`). Conservar la versión anterior cuando el
refresco falla es la garantía; que nadie se entere de que falló era el agujero
(issue #24). El backend lee esa bitácora y avisa.
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

_DDL_PG = """
CREATE SCHEMA IF NOT EXISTS mef;
CREATE TABLE IF NOT EXISTS mef.loads (
    load_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('loading', 'validated', 'published', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    metadata JSONB
);
CREATE TABLE IF NOT EXISTS mef.investments (
    load_id TEXT NOT NULL REFERENCES mef.loads(load_id) ON DELETE CASCADE,
    identity_key TEXT NOT NULL,
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
    monto_viable NUMERIC(18,2),
    costo_actualizado NUMERIC(18,2),
    fecha_registro TEXT,
    fecha_viabilidad TEXT,
    expediente_tecnico TEXT,
    opmi TEXT,
    uf TEXT,
    uei TEXT,
    uep TEXT,
    fuente TEXT NOT NULL,
    fila_origen INTEGER NOT NULL,
    PRIMARY KEY (load_id, identity_key)
);
CREATE INDEX IF NOT EXISTS mef_investments_cui_idx
    ON mef.investments(load_id, cui) WHERE cui <> '';
CREATE INDEX IF NOT EXISTS mef_investments_snip_idx
    ON mef.investments(load_id, snip) WHERE snip <> '';
CREATE INDEX IF NOT EXISTS mef_investments_entidad_idx
    ON mef.investments(load_id, entidad_norm);
CREATE TABLE IF NOT EXISTS mef.active_load (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    load_id TEXT NOT NULL REFERENCES mef.loads(load_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_COPY_PG = """
COPY mef.investments (
    load_id, identity_key, cui, snip, nombre, nombre_norm, estado_dataset, estado,
    situacion, entidad, entidad_norm, ubigeo, dpto, prov, dist, nivel, sector,
    funcion, tipo_inversion, tipologia, modalidad, monto_viable,
    costo_actualizado, fecha_registro, fecha_viabilidad, expediente_tecnico,
    opmi, uf, uei, uep, fuente, fila_origen
) FROM STDIN
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


def _fecha_iso(v: str) -> str:
    """Fecha del CSV del MEF a ISO `AAAA-MM-DD` (o "" si no se reconoce). El
    índice compacto la lleva para que el resolver pueda saber, sin PostgreSQL,
    cuándo se registró la inversión: un certificado anterior al registro no puede
    ser de ese proyecto (precisión a ADR-009: la fecha de registro también vive
    en el índice local; el resto de fechas sigue en PostgreSQL)."""
    v = (v or "").strip()
    if not v:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", v)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", v)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def _valor(fila: dict, columna: str | None) -> str:
    return (fila.get(columna) or "").strip() if columna else ""


def _decimal(valor: str) -> Decimal | None:
    """Parsea un decimal sin introducir errores binarios; vacío queda NULL."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        numero = Decimal(valor)
        if not numero.is_finite():
            raise InvalidOperation
        return numero
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


class ActualizacionEnCurso(RuntimeError):
    """Otra corrida tiene el lock. No es un fallo de ESTA actualización: es que no
    llegó a empezar, así que no se anota en la bitácora — la que sí está corriendo
    anotará su propio resultado."""


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
                raise ActualizacionEnCurso(
                    "ya existe una actualización MEF en ejecución") from exc
            adquirido = True
        else:
            import fcntl
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ActualizacionEnCurso(
                    "ya existe una actualización MEF en ejecución") from exc
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


class CargaPostgres:
    """Carga una versión MEF por COPY y la publica mediante un puntero."""

    def __init__(self, dsn: str, load_id: str):
        self.load_id = load_id
        self._dsn = dsn
        self._con = None
        self._cursor = None
        self._copy = None
        self._copy_cm = None
        self._validada = False

    def __enter__(self):
        import psycopg

        self._con = psycopg.connect(self._dsn, connect_timeout=10)
        self._con.execute(_DDL_PG)
        self._con.commit()
        self._con.execute(
            "INSERT INTO mef.loads(load_id, status) VALUES (%s, 'loading')",
            (self.load_id,),
        )
        self._cursor = self._con.cursor()
        self._copy_cm = self._cursor.copy(_COPY_PG)
        self._copy = self._copy_cm.__enter__()
        return self

    def insertar(self, valores: tuple) -> None:
        self._copy.write_row((self.load_id, *valores))

    def validar(self, meta: dict) -> None:
        from psycopg.types.json import Jsonb

        self._copy_cm.__exit__(None, None, None)
        self._copy = None
        self._copy_cm = None
        total = self._con.execute(
            "SELECT count(*) FROM mef.investments WHERE load_id = %s",
            (self.load_id,),
        ).fetchone()[0]
        esperado = int(meta["identidades"])
        if total != esperado:
            raise RuntimeError(
                f"PostgreSQL contiene {total:,} identidades; se esperaban {esperado:,}")
        self._con.execute(
            """UPDATE mef.loads
               SET status = 'validated', finished_at = now(), metadata = %s
               WHERE load_id = %s""",
            (Jsonb(meta), self.load_id),
        )
        self._con.commit()
        self._validada = True

    def publicar(self) -> None:
        if not self._validada:
            raise RuntimeError("la carga PostgreSQL no fue validada")
        with self._con.transaction():
            self._con.execute(
                """INSERT INTO mef.active_load(singleton, load_id, published_at)
                   VALUES (TRUE, %s, now())
                   ON CONFLICT (singleton) DO UPDATE
                   SET load_id = EXCLUDED.load_id, published_at = now()""",
                (self.load_id,),
            )
            self._con.execute(
                "UPDATE mef.loads SET status = 'published' WHERE load_id = %s",
                (self.load_id,),
            )

    def purgar(self, retener: int) -> None:
        self._con.execute(
            """DELETE FROM mef.loads
               WHERE load_id NOT IN (
                   SELECT load_id FROM mef.loads
                   WHERE status IN ('published', 'validated')
                   ORDER BY finished_at DESC NULLS LAST
                   LIMIT %s
               )
               AND load_id NOT IN (SELECT load_id FROM mef.active_load)""",
            (max(1, retener),),
        )
        self._con.commit()

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._copy_cm is not None:
                self._copy_cm.__exit__(exc_type, exc, tb)
        finally:
            if self._con is not None:
                if exc_type is not None:
                    self._con.rollback()
                if self._cursor is not None:
                    self._cursor.close()
                self._con.close()
            self._copy = None
            self._copy_cm = None
            self._cursor = None
            self._con = None


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
    pg,
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
    f_meta = staging / "metadata.json"
    filas_por_fuente: dict[str, int] = {}
    cabeceras: dict[str, list[str]] = {}
    fuentes_meta: dict[str, dict] = {}
    cuis_distintos: set[str] = set()
    identidades: set[str] = set()
    entidades: dict[str, str] = {}
    duplicados = 0
    anterior = _metadata_activa(dir_dest)

    try:
        with gzip.open(f_inv, "wt", encoding="utf-8", newline="") as gz:
            w = csv.writer(gz)
            w.writerow([
                "cui", "snip", "nombre", "estado_dataset", "situacion",
                "ubigeo", "dpto", "prov", "dist", "entidad", "fecha_registro",
                "fecha_viabilidad",
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
                            nueva_identidad = False
                        else:
                            identidades.add(identity_key)
                            nueva_identidad = True
                        entidad = _valor(fila, cols["entidad"])
                        situacion = _valor(fila, cols["situacion"])
                        w.writerow([
                            cui, snip, nombre, tag, situacion,
                            _valor(fila, cols["ubigeo"]),
                            _valor(fila, cols["dpto"]),
                            _valor(fila, cols["prov"]),
                            _valor(fila, cols["dist"]),
                            entidad,
                            _fecha_iso(_valor(fila, cols["fecha_registro"])),
                            _fecha_iso(_valor(fila, cols["fecha_viabilidad"])),
                        ])
                        if nueva_identidad:
                            pg.insertar((
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
                                _decimal(_valor(fila, cols["monto_viable"])),
                                _decimal(_valor(fila, cols["costo_actualizado"])),
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
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

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
        "postgres": {"schema": "mef", "tabla": "investments"},
        "artefactos": {},
    }
    try:
        meta["avisos_drift"] = _validar_drift(meta, anterior)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    for ruta in (f_inv, f_ent):
        meta["artefactos"][ruta.name] = {
            "bytes": ruta.stat().st_size,
            "sha256": _sha256(ruta),
        }
    try:
        pg.validar(meta)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
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
    pg.publicar()

    _purgar_cargas(cargas, activo=load_id, retener=retener_cargas)
    pg.purgar(retener_cargas)
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


def _con_bitacora(dir_dest: Path, tarea) -> dict:
    """Ejecuta `tarea()` y deja SIEMPRE anotado cómo terminó (issue #24).

    El fallo del refresco dejaba de existir en cuanto la consola se cerraba: la
    versión anterior se conservaba —correcto— pero nadie se enteraba de que los
    datos habían dejado de renovarse. Aquí queda escrito en la carpeta de la
    base, que es lo que el backend sí puede leer y mostrar.

    La corrida que ni siquiera empezó porque otra tenía el lock NO se anota: no
    es un fallo, y pisar la última corrida buena con ella sería mentir."""
    from resolucion import bitacora_mef

    inicio = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    try:
        meta = tarea()
    except ActualizacionEnCurso:
        raise
    except BaseException as exc:
        bitacora_mef.registrar_fallo(
            dir_dest, error=exc, inicio=inicio,
            duracion_s=time.perf_counter() - t0)
        raise
    bitacora_mef.registrar_exito(
        dir_dest, meta=meta, inicio=inicio,
        duracion_s=time.perf_counter() - t0)
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="Actualiza la base local del MEF.")
    ap.add_argument("--desde-dir", type=Path, default=None,
                    help="usa CSV locales de esta carpeta (sin descargar)")
    ap.add_argument("--destino", type=Path, default=None,
                    help="salida (default: <PIVOTE_DATA_DIR>/referencia/mef)")
    args = ap.parse_args()

    dir_dest = Path(args.destino or (data_dir() / "referencia" / "mef"))
    dsn = (os.getenv("PIVOTE_DB_URL") or "").strip()
    if not dsn:
        raise SystemExit("falta PIVOTE_DB_URL: PostgreSQL es obligatorio para el ETL MEF")
    def corrida() -> dict:
        if args.desde_dir:
            dir_csv = Path(args.desde_dir)
            print(f"Procesando CSV locales de {dir_csv}")
        else:
            dir_csv = dir_dest / "tmp"
            print(f"Descargando de {BASE_URL} a {dir_csv}")
            _descargar(dir_csv)
        load_id = _load_id()
        with _bloqueo_exclusivo(dir_dest), CargaPostgres(dsn, load_id) as pg:
            return _procesar(dir_csv, dir_dest, pg=pg, identificador=load_id)

    meta = _con_bitacora(dir_dest, corrida)
    print(
        f"\nOK · carga {meta['load_id']} · {meta['filas_total']:,} filas · "
        f"{meta['cuis_distintos']:,} CUIs · {meta['entidades']:,} entidades"
    )
    print(f"    en {dir_dest}")


if __name__ == "__main__":
    main()
