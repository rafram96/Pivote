"""
API HTTP del backend del pivote (FastAPI) — el puente real entre el panel /
MCP y el motor del orquestador.

Expone EXACTAMENTE el contrato que el panel ya consume contra sus mocks
(`Panel-InfoObras/frontend/src/app/api/pivote/*`): mismo shape, mismas rutas.
El switch en el panel es una variable de entorno (PIVOTE_API), no código.

Arranque (demo / dev):
    cd backend
    ../venv/Scripts/uvicorn api.app:app --port 8001
Datos en PIVOTE_DATA_DIR (def: ./datos_pivote — jobs, espejos y entregables).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# Carga el .env de la raíz del repo ANTES de leer el entorno o importar módulos
# que fijan constantes desde os.getenv (retries, throttle…). override=False → el
# entorno real y los tests (que setean su propio PIVOTE_ETAPAS) siempre ganan.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from entregables import (
    construir_zip_infoobras, descargar_cui, generar_excel_final, mapear_certificados,
    _zip_carpeta,
)
from orquestador import Motor, RepositorioArchivos, etapas_esqueleto, etapas_reales
from orquestador.progreso import REGISTRO
from schemas import pipeline
from schemas.espejo import JsonEspejo

DATA_DIR = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))

app = FastAPI(title="InfoObras Pivote API", version="0.2.0")
# Persistencia: PIVOTE_DB_URL definida → PostgreSQL (servidor); ausente →
# archivos JSON en DATA_DIR (esta laptop, tests). Los binarios van a DATA_DIR
# en ambos casos. El motor no distingue: ambos implementan el mismo protocolo.
if os.getenv("PIVOTE_DB_URL"):
    from orquestador.repositorio_pg import RepositorioPostgres
    repo = RepositorioPostgres(os.getenv("PIVOTE_DB_URL"), dir_datos=DATA_DIR)
else:
    repo = RepositorioArchivos(DATA_DIR)


def _reportar_progreso(job_id: str, etapa, item_actual: int,
                       items_total: int, descripcion: str) -> None:
    """Puente motor → RegistroProgreso: las etapas reportan su avance fino y la
    API lo lee en /progreso para pintar la barra. Volátil (en memoria)."""
    REGISTRO.reportar(job_id, getattr(etapa, "value", str(etapa)),
                      item_actual, items_total, descripcion)


# PIVOTE_ETAPAS=esqueleto -> stubs (tests/desarrollo sin red); default: reales.
if os.getenv("PIVOTE_ETAPAS", "real") == "esqueleto":
    motor = Motor(etapas_esqueleto(), repo, reportar=_reportar_progreso)
else:
    motor = Motor(etapas_reales(DATA_DIR), repo, reportar=_reportar_progreso)

ETAPA_FUENTE = {
    pipeline.Etapa.SUNAT: "SUNAT",
    pipeline.Etapa.INFOOBRAS: "InfoObras",
    pipeline.Etapa.VALIDACION: "revisión de consistencia",
    pipeline.Etapa.REGLAS: "cálculo de días efectivos",
}

# Etiqueta estable de cada etapa para el stepper del panel (palabras de evaluador,
# sin jerga). El texto por-ítem en vivo (RegistroProgreso) la sobrescribe SOLO
# mientras la etapa está en curso; una etapa ya OK muestra esta etiqueta.
ETAPA_TEXTO = {
    pipeline.Etapa.INGESTA: "Recepción de la propuesta",
    pipeline.Etapa.VALIDACION: "Revisión de consistencia",
    pipeline.Etapa.RESOLUCION_CUI: "Identificación de las obras",
    pipeline.Etapa.INFOOBRAS: "Verificación en el registro de obras públicas",
    pipeline.Etapa.SUNAT: "Verificación de los emisores",
    pipeline.Etapa.REGLAS: "Cálculo de días efectivos",
    pipeline.Etapa.EXCEL: "Armado del Excel de evaluación",
    pipeline.Etapa.PERSISTENCIA: "Guardado del análisis",
}


def _int_env(nombre: str, defecto: int) -> int:
    """int de una var de entorno con fallback silencioso — un valor basura en el
    .env NO tumba el arranque ni la tarea, cae al defecto."""
    try:
        v = int((os.getenv(nombre) or "").strip() or defecto)
    except ValueError:
        return defecto
    return v if v > 0 else defecto


# Límite de análisis concurrentes: cada uno corre el pipeline + baja ~1 GB de
# InfoObras. Sin tope, N uploads simultáneos agotan hilos/red/disco (DoS trivial).
_MAX_ANALISIS = _int_env("PIVOTE_MAX_ANALISIS_CONCURRENTES", 2)
_sem_analisis = threading.BoundedSemaphore(_MAX_ANALISIS)

# Topes de subida (evitan OOM/disco por uploads gigantes cargados en memoria).
_MAX_ESPEJO = _int_env("PIVOTE_MAX_MB_ESPEJO", 30) * (1 << 20)
_MAX_EXCEL = _int_env("PIVOTE_MAX_MB_EXCEL", 60) * (1 << 20)
_MAX_CERTS = _int_env("PIVOTE_MAX_MB_CERTS", 400) * (1 << 20)
_MAX_CERTS_DESCOMP = 800 * (1 << 20)     # tope del ZIP de certs YA descomprimido
_MAX_CERTS_ENTRADAS = 5000               # tope de archivos en el ZIP


async def _leer_limitado(f: UploadFile, tope: int, etiqueta: str) -> bytes:
    """Lee un UploadFile por chunks y aborta con 413 si excede `tope` bytes — sin
    cargar de golpe un archivo gigante en memoria."""
    buf = bytearray()
    while True:
        chunk = await f.read(1 << 20)
        if not chunk:
            break
        buf += chunk
        if len(buf) > tope:
            raise HTTPException(413, f"{etiqueta} excede el límite de {tope // (1 << 20)} MB")
    return bytes(buf)


# ── helpers ──────────────────────────────────────────────────────────────────

def _job_o_404(job_id: str) -> pipeline.Job:
    job = repo.cargar(job_id)
    if job is None:
        raise HTTPException(404, "job no existe")
    return job


def _espejo_o_404(job_id: str) -> dict:
    espejo = repo.cargar_espejo(job_id)
    if espejo is None:
        raise HTTPException(404, "espejo no disponible para este job")
    return espejo


# ── Descarga DIFERIDA de documentos InfoObras ────────────────────────────────
# Los PDFs de InfoObras (~1 GB) solo alimentan el ZIP, no el veredicto/Excel. Por
# eso se bajan DESPUÉS del pipeline (sin bloquear el resultado) y, como red de
# seguridad, también al pedir el /zip. Serializado por job para no duplicar trabajo.
logger = logging.getLogger("pivote.api")
_descargas_guard = threading.Lock()


class _FiltroPolling(logging.Filter):
    """Silencia el ruido del access-log de uvicorn: el panel hace polling (GET
    /jobs/{id}, /salud, /concursos cada ~1s) y ensuciaba la consola con cientos de
    'GET ... 200 OK' que no dicen nada. Deja pasar TODO lo demás (POST/DELETE, la
    creación de jobs, y cualquier 4xx/5xx — los errores sí importan)."""

    _RUIDO = ("/api/pivote/jobs/", "/api/pivote/salud", "/api/pivote/concursos")

    def filter(self, record: logging.LogRecord) -> bool:  # True = se muestra
        msg = record.getMessage()
        if '"GET ' not in msg:
            return True                       # POST/DELETE/PATCH siempre se ven
        if not any(p in msg for p in self._RUIDO):
            return True                       # otros GET (excel, zip…) se ven
        return not (" 200 " in msg or " 304 " in msg)   # ocultar solo el poll OK


logging.getLogger("uvicorn.access").addFilter(_FiltroPolling())
_descargas_locks: dict[str, threading.Lock] = {}


def _lock_descargas(job_id: str) -> threading.Lock:
    with _descargas_guard:
        return _descargas_locks.setdefault(job_id, threading.Lock())


def _mapa_descargas(job_id: str) -> dict:
    """{(n_prof, n_exp): carpeta} de las descargas `P{n}_E{m}` en disco."""
    d = DATA_DIR / f"{job_id}.descargas"
    out: dict[tuple[int, int], Path] = {}
    if d.is_dir():
        for sub in d.iterdir():
            try:
                np_, ne = sub.name.removeprefix("P").split("_E")
                out[(int(np_), int(ne))] = sub
            except ValueError:
                continue
    return out


def _asegurar_descargas(job_id: str) -> None:
    """Idempotente + serializado por job: baja lo que falte de InfoObras, rellena la
    métrica de INFOOBRAS y, al terminar TODO, arma el ZIP COMPLETO antes de marcar
    `descargas_estado="listas"`. La llaman el background task (tras el pipeline) y el
    endpoint /zip (que la reanuda si se cortó). No relanza: deja el estado en el job."""
    job = repo.cargar(job_id)
    if job is None or job.descargas_estado == "listas":
        return
    with _lock_descargas(job_id):
        job = repo.cargar(job_id)                      # re-leer dentro del lock
        if job is None or job.descargas_estado == "listas":
            return
        espejo = repo.cargar_espejo(job_id) or {}
        enr = repo.cargar_enriquecimiento(job_id) or {}
        job.descargas_estado = "en_progreso"
        repo.guardar(job)
        _raw = (os.getenv("PIVOTE_MAX_DESCARGAS") or "").strip()
        try:
            maxd = int(_raw) if _raw else None      # vacío = baja TODO; N = tope (0 = ninguno)
        except ValueError:
            maxd = None                              # basura en el .env → baja todo (seguro)
        t0 = time.time()

        def _rep(i: int, total: int, nombre: str) -> None:
            REGISTRO.reportar(job_id, "descargas", i, total,
                              f"Descargando documentos de la obra {i} de {total} — {nombre}")

        try:
            from orquestador.etapas_reales import descargar_documentos_job
            stats = descargar_documentos_job(espejo, enr, job_id, DATA_DIR,
                                             max_descargas=maxd, reportar=_rep)
            # arma el ZIP COMPLETO recién ahora que están TODOS los documentos
            # (atómico → reemplaza cualquier zip parcial previo).
            ruta_zip = DATA_DIR / f"{job_id}.infoobras.zip"
            with _zip_build_lock:
                construir_zip_infoobras(espejo, _mapa_descargas(job_id), ruta_zip,
                                        enriquecimiento=enr)
            # re-leer JUSTO antes de guardar: una resolución de revisión concurrente
            # pudo tocar el job durante la descarga/armado del ZIP → no pisarla.
            job = repo.cargar(job_id) or job
            io = job.etapa(pipeline.Etapa.INFOOBRAS)
            if io is not None:                          # backfill de la métrica
                io.metrica.descargas = stats["descargas"]
                io.metrica.bytes_descargados = stats["bytes"]
                io.metrica.reintentos = stats["reintentos"]
            job.zip_infoobras = f"/api/pivote/jobs/{job_id}/zip"
            job.descargas_estado = "listas"
            repo.guardar(job)
            REGISTRO.limpiar(job_id)   # job terminal: suelta el progreso fino en memoria
            logger.info("DESCARGAS job %s · %d arch · %.0f MB · %d reintentos · %.0fs",
                        job_id, stats["descargas"], stats["bytes"] / 1_048_576,
                        stats["reintentos"], time.time() - t0)
        except Exception:
            logger.exception("descargas job %s fallaron", job_id)
            job = repo.cargar(job_id) or job
            job.descargas_estado = "error"
            repo.guardar(job)
            REGISTRO.limpiar(job_id)


def _correr_y_descargar(job_id: str) -> None:
    """Background task: corre el pipeline (veredicto/Excel listos en ~1 min) y,
    RECIÉN entonces, baja los documentos InfoObras (lo lento, que solo nutre el ZIP).
    Serializado por `_sem_analisis` para no lanzar N pipelines + N descargas de GBs
    a la vez (protege hilos/red/disco del server ante uploads simultáneos)."""
    with _sem_analisis:
        job = motor.correr(job_id)
        if job is not None:
            logger.info("PIPELINE job %s → %s · %d en revisión", job_id,
                        getattr(job.estado, "value", job.estado), len(job.items_revision))
        if job is not None and job.estado == pipeline.JobEstado.ERROR:
            REGISTRO.limpiar(job_id)   # sin descargas que corran: libera el progreso aquí
            return  # el pipeline falló: no hay enriquecimiento útil que descargar
        try:
            logger.info("DESCARGAS job %s: bajando documentos de InfoObras…", job_id)
            _asegurar_descargas(job_id)
        except Exception:
            logger.exception("descarga diferida del job %s falló", job_id)


@app.on_event("startup")
def _reanudar_pendientes() -> None:
    """Si el backend se reinició con trabajo a medias, lo RETOMA al arrancar: un
    pipeline cortado (estado `en_proceso`) y/o descargas a medias (`en_progreso`).
    Sin esto, un job interrumpido quedaba colgado para siempre sin recuperación."""
    for f in DATA_DIR.glob("*.job.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        jid = j.get("job_id") or f.name[: -len(".job.json")]
        # pipeline cortado a medias (crash/reinicio) → retomar. `motor.correr` es
        # reanudable (salta etapas ya hechas). Si no, el job queda en 'en_proceso'
        # para siempre, sin recuperación ni desde la UI.
        if j.get("estado") == pipeline.JobEstado.EN_PROCESO.value:
            threading.Thread(target=_correr_y_descargar, args=(jid,), daemon=True).start()
            logger.info("reanudando pipeline interrumpido del job %s tras reinicio", jid)
            continue
        # Solo "en_progreso" = descarga genuinamente interrumpida. "pendiente" puede
        # ser un job viejo (el campo se defaulteó) → NO lo re-disparamos.
        if j.get("descargas_estado") == "en_progreso":
            threading.Thread(target=_asegurar_descargas, args=(jid,), daemon=True).start()
            logger.info("reanudando descargas pendientes del job %s tras reinicio", jid)


def _decisiones(job_id: str) -> dict:
    # Vía el repo (antes escribía {id}.decisiones.json directo): así Postgres
    # también las captura y RepositorioArchivos mantiene el mismo archivo.
    return repo.cargar_decisiones(job_id)


def _pendientes(job: pipeline.Job) -> int:
    return sum(1 for it in job.items_revision if not it.resuelto)


# ── Concursos ────────────────────────────────────────────────────────────────

@app.get("/api/pivote/concursos")
def listar_concursos():
    jobs = repo.listar()
    out = []
    for c in repo.listar_concursos():
        propios = [j for j in jobs if j.concurso_id == c.concurso_id]
        out.append({
            **json.loads(c.model_dump_json()),
            "n_jobs": len(propios),
            "pendientes": sum(_pendientes(j) for j in propios),
        })
    return out


@app.post("/api/pivote/concursos", status_code=201)
def crear_concurso(body: dict):
    nomenclatura = (body.get("nomenclatura") or "").strip()
    if not nomenclatura:
        raise HTTPException(400, "nomenclatura es obligatoria")
    c = pipeline.Concurso(
        concurso_id=uuid.uuid4().hex[:10],
        nomenclatura=nomenclatura,
        fecha_presentacion=body.get("fecha_presentacion"),
        creado_en=datetime.now(timezone.utc),
    )
    repo.guardar_concurso(c)
    return json.loads(c.model_dump_json())


@app.patch("/api/pivote/concursos/{concurso_id}")
def editar_concurso(concurso_id: str, body: dict):
    """Edita el nombre (nomenclatura) de un concurso, persistente."""
    c = repo.cargar_concurso(concurso_id)
    if c is None:
        raise HTTPException(404, "concurso no existe")
    if "nomenclatura" in body:
        nom = (body.get("nomenclatura") or "").strip()
        if not nom:
            raise HTTPException(400, "la nomenclatura no puede quedar vacía")
        c.nomenclatura = nom
    repo.guardar_concurso(c)
    return json.loads(c.model_dump_json())


@app.delete("/api/pivote/concursos/{concurso_id}")
def borrar_concurso(concurso_id: str):
    """Borra el concurso y, EN CASCADA, todos sus análisis (jobs) con sus
    artefactos (espejo, excels, ZIP, certs, descargas). Irreversible."""
    c = repo.cargar_concurso(concurso_id)
    if c is None:
        raise HTTPException(404, "concurso no existe")
    jobs = [j for j in repo.listar() if j.concurso_id == concurso_id]
    for j in jobs:
        repo.eliminar(j.job_id)
    repo.eliminar_concurso(concurso_id)
    return {"eliminado": concurso_id, "analisis_eliminados": len(jobs)}


@app.delete("/api/pivote/jobs/{job_id}")
def borrar_job(job_id: str):
    """Borra un análisis (job) y TODOS sus artefactos (espejo, excels, ZIP, certs,
    descargas). No borra el concurso. Irreversible."""
    job = repo.cargar(job_id)
    if job is None:
        raise HTTPException(404, "análisis no existe")
    repo.eliminar(job_id)
    return {"eliminado": job_id, "concurso_id": job.concurso_id}


def _avance_descargas_dict(job: pipeline.Job) -> dict:
    """Avance de descargas (compartido por /descargas y /progreso): cuántas obras
    ya están en disco vs las que deben bajar (las en revisión no bajan) + la obra
    en curso (del RegistroProgreso, si hay una descarga corriendo)."""
    espejo = repo.cargar_espejo(job.job_id) or {}
    todas = [(p["n_prof"], e["n"])
             for p in espejo.get("profesionales", [])
             for e in p.get("experiencias", [])]
    rev = {(it.n_prof, it.n_exp) for it in job.items_revision if not it.resuelto}
    bajan = [x for x in todas if x not in rev]
    carpetas = _mapa_descargas(job.job_id)
    descargadas = sum(1 for x in bajan if x in carpetas)
    total = len(bajan)
    viva = REGISTRO.etapas(job.job_id).get("descargas")
    return {
        "estado": job.descargas_estado,
        "listo": job.descargas_estado == "listas",
        "total": total,
        "descargadas": descargadas,
        "faltan": total - descargadas,
        "en_revision": len(rev),
        "obra_actual": (viva or {}).get("descripcion"),
    }


def armar_progreso(job: pipeline.Job) -> dict:
    """Todo lo que la barra del panel necesita en UN request: pct grueso por
    etapas + texto/contador fino de la(s) etapa(s) en curso + avance de descargas.
    Fusiona el checkpoint persistido (fuente de verdad del estado) con el
    RegistroProgreso en memoria (el 'qué está pasando ahora'). INFOOBRAS ∥ SUNAT
    pueden aparecer ambas 'en_curso' a la vez — es correcto, corren en paralelo."""
    orden = pipeline.Etapa.orden()
    _OK = (pipeline.EstadoEtapa.OK, pipeline.EstadoEtapa.OK_CON_REVISION,
           pipeline.EstadoEtapa.ERROR_PARCIAL)
    completas = sum(1 for e in job.etapas if e.estado in _OK)
    vivas = REGISTRO.etapas(job.job_id)
    etapas = []
    for nombre in orden:
        res = job.etapa(nombre)
        viva = vivas.get(nombre.value)
        item = {"etapa": nombre.value, "texto": ETAPA_TEXTO[nombre]}
        if res is not None and res.estado in _OK:
            item["estado"] = res.estado.value             # terminó → etiqueta estable
        elif viva is not None:
            item["estado"] = "en_curso"
            if viva["descripcion"]:
                item["texto"] = viva["descripcion"]       # texto fino en vivo
            if viva["items_total"]:
                item["item_actual"] = viva["item_actual"]
                item["items_total"] = viva["items_total"]
        elif res is not None:
            item["estado"] = res.estado.value             # pendiente/error del checkpoint
        else:
            item["estado"] = "pendiente"
        etapas.append(item)
    return {
        "job_id": job.job_id,
        "estado": getattr(job.estado, "value", job.estado),
        "pct": round(100 * completas / len(orden), 1),
        "etapas": etapas,
        "descargas": _avance_descargas_dict(job),
        "eta": None,                                       # §4 (ETA por histórico) — futuro
        "pendientes_humano": job.pendientes_humano,
    }


@app.get("/api/pivote/jobs/{job_id}/descargas")
def avance_descargas(job_id: str):
    """Avance real de las descargas InfoObras por experiencia (alimenta la barra del
    ZIP): cuántas obras ya se bajaron vs las que deben bajar (las en revisión no bajan)."""
    job = repo.cargar(job_id)
    if job is None:
        raise HTTPException(404, "análisis no existe")
    return _avance_descargas_dict(job)


@app.get("/api/pivote/jobs/{job_id}/progreso")
def progreso(job_id: str):
    """Avance del análisis para la barra del panel (el panel lo pollea mientras el
    job corre). Fuente ÚNICA: fusiona checkpoints + progreso fino + descargas, así
    el panel arma toda la barra con un solo request."""
    REGISTRO.purgar_viejos()
    job = repo.cargar(job_id)
    if job is None:
        raise HTTPException(404, "análisis no existe")
    return armar_progreso(job)


@app.get("/api/pivote/concursos/{concurso_id}")
def ver_concurso(concurso_id: str):
    c = repo.cargar_concurso(concurso_id)
    if c is None:
        raise HTTPException(404, "concurso no existe")
    jobs = [j for j in repo.listar() if j.concurso_id == concurso_id]
    return {
        **json.loads(c.model_dump_json()),
        "jobs": [json.loads(j.model_dump_json()) for j in jobs],
    }


# ── Análisis (ingesta + pipeline) ────────────────────────────────────────────

def _guardar_certificados(job_id: str, contenido: bytes) -> int:
    """Descomprime el ZIP de certificados de la skill a `{job}.certs/` — solo PDFs
    `P{n}_E{m}.pdf`, ignorando rutas (anti zip-slip). Devuelve cuántos guardó."""
    import io
    import os
    import zipfile
    if not contenido:
        return 0
    cdir = DATA_DIR / f"{job_id}.certs"
    cdir.mkdir(parents=True, exist_ok=True)
    n = 0
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            infos = z.infolist()
            if len(infos) > _MAX_CERTS_ENTRADAS:
                raise HTTPException(413, "el ZIP de certificados tiene demasiados archivos")
            total = 0
            for info in infos:
                total += info.file_size            # tamaño declarado (anti zip-bomb)
                if total > _MAX_CERTS_DESCOMP:
                    raise HTTPException(413, "el ZIP de certificados descomprimido excede el límite")
                base = os.path.basename(info.filename)
                if base.lower().endswith(".pdf") and base.upper().startswith("P"):
                    (cdir / base).write_bytes(z.read(info.filename))
                    n += 1
    except zipfile.BadZipFile:
        pass
    return n


@app.post("/api/pivote/analizar", status_code=201)
async def analizar(
    tareas: BackgroundTasks,
    concurso_id: str = Form(...),
    espejo: UploadFile = File(...),
    excel: UploadFile = File(...),
    origen: str = Form("dropzone"),
    certificados: UploadFile | None = File(None),
):
    if repo.cargar_concurso(concurso_id) is None:
        raise HTTPException(404, "concurso no existe")
    try:
        datos = json.loads((await _leer_limitado(espejo, _MAX_ESPEJO, "el archivo de datos")).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(422, f"el archivo de datos no es JSON válido: {e}")
    try:
        JsonEspejo.model_validate(datos)
    except ValidationError as e:
        raise HTTPException(422, detail={
            "error": "el archivo de datos no pasa el contrato",
            "errores": [
                {"ruta": ".".join(str(x) for x in err["loc"]), "mensaje": err["msg"]}
                for err in e.errors()[:30]
            ],
        })

    job = motor.crear_job(datos, concurso_id=concurso_id)
    job.origen = origen if origen in ("mcp", "dropzone") else "dropzone"
    repo.guardar(job)
    # guardar el Excel de Claude tal cual llegó (referencia/auditoría)
    (DATA_DIR / f"{job.job_id}.claude.xlsx").write_bytes(
        await _leer_limitado(excel, _MAX_EXCEL, "el Excel"))
    # certificados de las experiencias (ZIP de PDFs que recortó la skill) → {job}.certs/
    if certificados is not None:
        _guardar_certificados(job.job_id,
                              await _leer_limitado(certificados, _MAX_CERTS, "los certificados"))

    tareas.add_task(_correr_y_descargar, job.job_id)
    return {"job_id": job.job_id}


@app.get("/api/pivote/jobs/{job_id}")
def ver_job(job_id: str):
    return json.loads(_job_o_404(job_id).model_dump_json())


@app.post("/api/pivote/jobs/{job_id}/revision")
def resolver_revision(job_id: str, tareas: BackgroundTasks, body: dict):
    n_prof, n_exp = body.get("n_prof"), body.get("n_exp")
    if not isinstance(n_prof, int) or not isinstance(n_exp, int):
        raise HTTPException(400, "n_prof y n_exp son obligatorios")
    if not body.get("cui") and body.get("accion") != "no_existe":
        raise HTTPException(400, "se requiere cui o accion='no_existe'")
    # TODO el read-modify-write del job va bajo el lock del job, para que NO se
    # entrelace con `_asegurar_descargas` (que toma el mismo lock): antes,
    # `motor.resolver_revision` guardaba FUERA del lock y una descarga en background
    # podía pisar los `items_revision` recién resueltos (última escritura gana).
    with _lock_descargas(job_id):
        try:
            job = motor.resolver_revision(job_id, n_prof, n_exp, body)
        except ValueError as e:
            raise HTTPException(404, str(e))
        # La obra del item pudo cambiar al re-resolver → invalida SUS PDFs (carpeta
        # + marca .ok) para re-bajarlos frescos; los demás se saltan por su .ok.
        base = DATA_DIR / f"{job_id}.descargas"
        shutil.rmtree(base / f"P{n_prof}_E{n_exp}", ignore_errors=True)
        (base / f"P{n_prof}_E{n_exp}.ok").unlink(missing_ok=True)
        job.descargas_estado = "pendiente"
        repo.guardar(job)
    tareas.add_task(_asegurar_descargas, job_id)   # re-baja en background (fuera del lock)
    return json.loads(job.model_dump_json())


# ── Búsqueda global de profesionales ─────────────────────────────────────────

def _sin_tildes(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if not unicodedata.combining(c)).lower()


@app.get("/api/pivote/profesionales")
def buscar_profesionales(q: str = ""):
    """Busca un profesional por nombre/colegiatura/cargo en TODOS los análisis
    (insensible a mayúsculas y tildes). Devuelve dónde aparece, con link directo
    al análisis. Escanea los espejos persistidos — con decenas de jobs es barato;
    en Postgres esto pasa a la tabla índice `profesionales` (mismo shape).

    Nota: si el MISMO profesional está en varias propuestas, devuelve una fila por
    aparición — eso es información, no ruido (el evaluador ve en qué concursos va)."""
    q = (q or "").strip()
    if len(q) < 2:
        return []
    # Con Postgres, la tabla índice `profesionales` resuelve esto con un LIKE
    # (mismo shape); el escaneo de abajo es el camino del repo de archivos.
    if hasattr(repo, "buscar_profesionales"):
        return repo.buscar_profesionales(q)
    qn = _sin_tildes(q)
    concursos = {c.concurso_id: c.nomenclatura for c in repo.listar_concursos()}
    out = []
    for job in repo.listar():
        espejo = repo.cargar_espejo(job.job_id)
        if not espejo:
            continue
        for p in espejo.get("profesionales", []):
            campos = [p.get("nombre"), p.get("colegiatura"), p.get("cargo")]
            if not any(qn in _sin_tildes(str(v)) for v in campos if v):
                continue
            out.append({
                "nombre": p.get("nombre"),
                "cargo": p.get("cargo"),
                "colegiatura": p.get("colegiatura"),
                "n_prof": p.get("n_prof"),
                "cumple": p.get("cumple"),
                "n_experiencias": len(p.get("experiencias", []) or []),
                "job_id": job.job_id,
                "estado_job": getattr(job.estado, "value", job.estado),
                "concurso_id": job.concurso_id,
                "concurso": concursos.get(job.concurso_id) or job.concurso,
                "postor": job.postor,
            })
    out.sort(key=lambda x: (_sin_tildes(str(x["nombre"] or "")), str(x["job_id"])))
    return out[:50]                 # tope de cortesía; con 2+ letras alcanza y sobra


# ── Vistas derivadas (extracción + resumen) ──────────────────────────────────

@app.get("/api/pivote/jobs/{job_id}/espejo")
def extraccion(job_id: str):
    _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    enr = repo.cargar_enriquecimiento(job_id) or {}
    profesionales = []
    for p in espejo.get("profesionales", []):
        np_ = p.get("n_prof")
        experiencias = []
        for e in p.get("experiencias", []):
            d = {k: e.get(k) for k in (
                "n", "proyecto", "entidad_emisora", "cargo_ocupado",
                "fecha_inicial", "fecha_final", "dias", "cui",
                "incluye_covid", "traslape", "folio")}
            # enriquecimiento del backend: CUI resuelto + quién ejecutó/supervisó
            # la obra en InfoObras (Representante de obra) + verificación SUNAT.
            ev = enr.get(f"{np_}:{e.get('n')}")
            if isinstance(ev, dict):
                obra = ev.get("obra") or {}
                d["cui_resuelto"] = obra.get("cui") or ev.get("cui")
                d["obra_nombre"] = ev.get("obra_nombre") or obra.get("nombre_obra")
                d["via_resolucion"] = ev.get("via")
                d["representante_obra"] = ev.get("representante_obra")
                d["sunat"] = ev.get("sunat")
            experiencias.append(d)
        profesionales.append({
            "n_prof": np_,
            "cargo": p.get("cargo"),
            "cargo_bases_num": p.get("cargo_bases_num"),
            "cargo_bases_nombre": p.get("cargo_bases_nombre"),
            "nombre": p.get("nombre"),
            "dni": p.get("dni"),
            "colegiatura": p.get("colegiatura"),
            "notas": p.get("notas") or [],
            "cumple": p.get("cumple"),
            "total": p.get("total") or {},
            "experiencias": experiencias,
        })
    return {"profesionales": profesionales}


@app.get("/api/pivote/jobs/{job_id}/resumen")
def resumen(job_id: str):
    job = _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    decisiones = _decisiones(job_id)

    enr = repo.cargar_enriquecimiento(job_id)
    veredictos = []
    for p in espejo.get("profesionales", []):
        total = p.get("total") or {}
        np_ = p.get("n_prof")
        d = enr.get(f"prof:{np_}") or {}
        motivo = None
        if d.get("dias_paralizados") or d.get("dias_traslape"):
            partes = []
            if d.get("dias_paralizados"):
                partes.append(f"paralizaciones de obra: -{d['dias_paralizados']} dias")
            if d.get("dias_traslape"):
                partes.append(f"traslapes entre experiencias: -{d['dias_traslape']} dias")
            motivo = " - ".join(partes)
        veredictos.append({
            "n_prof": np_,
            "cargo": p.get("cargo"),
            "cargo_bases_num": p.get("cargo_bases_num"),
            "cargo_bases_nombre": p.get("cargo_bases_nombre"),
            "nombre": p.get("nombre"),
            "cumple_claude": p.get("cumple") or "(sin veredicto en el espejo)",
            "anios_brutos": total.get("anios") or 0,
            "cumple_backend": d.get("cumple_backend"),
            "anios_efectivos": d.get("anios_efectivos"),
            "minimo_anios": d.get("minimo_anios"),
            "motivo_backend": motivo,
            "fuente": "InfoObras" if d.get("dias_paralizados") else ("recalculo" if d else None),
        })

    alertas = []
    # la misma observación suele venir en job.observaciones Y en la etapa que la
    # emitió → deduplicar por (severidad, código, mensaje, referencia) para no
    # mostrar la misma alerta dos veces.
    todas = list(job.observaciones) + [o for e in job.etapas for o in e.observaciones]
    vistas: set = set()
    for i, o in enumerate(todas):
        clave = (o.severidad.value, o.codigo, o.mensaje, o.referencia)
        if clave in vistas:
            continue
        vistas.add(clave)
        aid = f"al-{i}"
        alertas.append({
            "id": aid,
            "codigo": o.codigo or o.severidad.value.upper(),
            "severidad": o.severidad.value,
            "mensaje": o.mensaje,
            "referencia": o.referencia,
            "fuente": ETAPA_FUENTE.get(o.origen, o.origen.value),
            "decision": decisiones.get(aid),
        })

    re_ = espejo.get("resumen_evaluacion") or {}
    factores = [
        {"factor": f.get("factor"), "criterio": f.get("criterio"),
         "puntaje": f.get("puntaje"), "detalle": f.get("detalle")}
        for f in re_.get("factores", [])
    ]
    return {
        "job_id": job_id,
        "postor": job.postor or job.analisis_id,
        "veredictos": veredictos,
        "alertas": alertas,
        "factores": factores,
        "puntaje_total": re_.get("puntaje_total"),
    }


@app.post("/api/pivote/jobs/{job_id}/alertas")
def decidir_alerta(job_id: str, body: dict):
    _job_o_404(job_id)
    alerta_id = body.get("alerta_id")
    relevante = body.get("relevante")
    if not isinstance(alerta_id, str) or not isinstance(relevante, bool):
        raise HTTPException(400, "alerta_id y relevante son obligatorios")
    decisiones = _decisiones(job_id)
    decisiones[alerta_id] = {"relevante": relevante, "razon": body.get("razon")}
    repo.guardar_decisiones(job_id, decisiones)
    return resumen(job_id)


# ── Entregables ──────────────────────────────────────────────────────────────

@app.get("/api/pivote/jobs/{job_id}/excel")
def descargar_excel(job_id: str):
    job = _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    ruta = DATA_DIR / f"{job_id}.final.xlsx"
    if not ruta.exists():
        # Las paralizaciones reales las inyecta la etapa de InfoObras; sin
        # ellas el Excel sale con brutos = efectivos (y se regenera después).
        generar_excel_final(espejo, ruta,
                            certificados=mapear_certificados(DATA_DIR, job_id))
        job.excel_final = f"/api/pivote/jobs/{job_id}/excel"
        repo.guardar(job)
    return FileResponse(
        ruta,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Formato_Evaluacion_{job.analisis_id}.xlsx",
    )


# Serializa el armado del ZIP: dos descargas concurrentes no deben rearmar el
# mismo ZIP de ~1 GB en paralelo (ni renombrarlo mientras otra petición lo sirve).
_zip_build_lock = threading.Lock()


@app.get("/api/pivote/jobs/{job_id}/zip")
def descargar_zip(job_id: str, tareas: BackgroundTasks):
    job = _job_o_404(job_id)
    ruta = DATA_DIR / f"{job_id}.infoobras.zip"
    en_prep = {"descargas_estado": job.descargas_estado,
               "mensaje": "El ZIP se está preparando: descargando los documentos de InfoObras."}
    # Descargando activamente → el zip (si existe) es PARCIAL → no servirlo: 202.
    # El panel pollea `descargas_estado` y habilita la descarga SOLO al quedar "listas".
    if job.descargas_estado == "en_progreso":
        tareas.add_task(_asegurar_descargas, job_id)
        return JSONResponse(status_code=202, content=en_prep)
    if not ruta.exists():
        if job.descargas_estado == "listas":      # listas pero borraron el zip → rearmar
            with _zip_build_lock:
                if not ruta.exists():
                    espejo = _espejo_o_404(job_id)
                    enr = repo.cargar_enriquecimiento(job_id) or {}
                    construir_zip_infoobras(espejo, _mapa_descargas(job_id), ruta, enriquecimiento=enr)
        else:                                      # pendiente/error sin zip → reanuda + 202
            tareas.add_task(_asegurar_descargas, job_id)
            return JSONResponse(status_code=202, content=en_prep)
    # zip presente y NO se está descargando → completo (listas, o job previo) → servir
    return FileResponse(ruta, media_type="application/zip",
                        filename=f"InfoObras_{job.analisis_id}.zip")


# ── Descarga por un solo CUI (sin correr un análisis) ────────────────────────
# Baja TODOS los documentos de InfoObras de una obra a partir de su CUI y los
# entrega en un ZIP, reutilizando la misma maquinaria del ZIP de un análisis.
# Es un "dame los papeles de esta obra" suelto. Se hace como tarea en background
# (un CUI puede traer cientos de MB) con estado polleable, igual que las descargas
# de un job. Estado en {descarga_id}.cui.json; documentos en {id}.cui-descargas/.

def _fecha_opt(s) -> Optional[date]:
    """'AAAA-MM-DD' (o None/vacío) → date | None, sin reventar ante basura."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _ruta_descarga_cui(descarga_id: str) -> Path:
    return DATA_DIR / f"{descarga_id}.cui.json"


def _leer_descarga_cui(descarga_id: str) -> Optional[dict]:
    p = _ruta_descarga_cui(descarga_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _guardar_descarga_cui(descarga_id: str, est: dict) -> None:
    _ruta_descarga_cui(descarga_id).write_text(
        json.dumps(est, ensure_ascii=False), encoding="utf-8")


def _correr_descarga_cui(descarga_id: str) -> None:
    """Background: resuelve el CUI, baja sus documentos de InfoObras y arma el ZIP.
    Serializado por `_sem_analisis` (mismo cupo que los análisis, para no saturar
    red/disco). No relanza: deja el estado en el JSON de la descarga."""
    est = _leer_descarga_cui(descarga_id)
    if est is None:
        return
    with _sem_analisis:
        est = _leer_descarga_cui(descarga_id) or est
        if est.get("estado") == "listas":
            return
        carpeta = DATA_DIR / f"{descarga_id}.cui-descargas"
        try:
            r = descargar_cui(est["cui"], carpeta,
                              fecha_inicio=_fecha_opt(est.get("fecha_inicio")),
                              fecha_fin=_fecha_opt(est.get("fecha_fin")))
            est.update({k: r.get(k) for k in
                        ("obra_id", "nombre", "descargados", "fallidos", "error")})
            if r.get("obra_id") is None:
                est["estado"] = "error"
                _guardar_descarga_cui(descarga_id, est)
                logger.info("DESCARGA-CUI %s · CUI %s no resolvió", descarga_id, est["cui"])
                return
            titulo = (f"InfoObras · CUI {est['cui']} · obra {r.get('obra_id')} · "
                      f"{r.get('nombre') or ''}".strip())
            _zip_carpeta(carpeta, DATA_DIR / f"{descarga_id}.cui.zip", titulo)
            est["estado"] = "listas"
            _guardar_descarga_cui(descarga_id, est)
            logger.info("DESCARGA-CUI %s · CUI %s · obra %s · %d arch",
                        descarga_id, est["cui"], r.get("obra_id"), r.get("descargados", 0))
        except Exception:
            logger.exception("descarga por CUI %s falló", descarga_id)
            est["estado"] = "error"
            est["error"] = "fallo al descargar de InfoObras"
            _guardar_descarga_cui(descarga_id, est)


@app.post("/api/pivote/descargar-cui", status_code=201)
def descargar_cui_crear(tareas: BackgroundTasks, body: dict):
    """Dispara la descarga de TODOS los documentos de InfoObras de un solo CUI
    (valorizaciones, informes de control, datos de cierre, aprobación de expediente)
    sin correr un análisis. Devuelve un `descarga_id` para pollear estado y bajar el ZIP.
    Body: {cui, fecha_inicio?, fecha_fin?} (fechas AAAA-MM-DD, acotan los informes)."""
    cui = str(body.get("cui") or "").strip()
    if not cui.isdigit():
        raise HTTPException(400, "cui es obligatorio y debe ser numérico")
    fi, ff = _fecha_opt(body.get("fecha_inicio")), _fecha_opt(body.get("fecha_fin"))
    descarga_id = uuid.uuid4().hex[:12]
    _guardar_descarga_cui(descarga_id, {
        "descarga_id": descarga_id, "cui": cui,
        "fecha_inicio": fi.isoformat() if fi else None,
        "fecha_fin": ff.isoformat() if ff else None,
        "estado": "en_progreso", "obra_id": None, "nombre": None,
        "descargados": 0, "fallidos": 0, "error": None,
        "creado_en": datetime.now(timezone.utc).isoformat(),
    })
    tareas.add_task(_correr_descarga_cui, descarga_id)
    return {"descarga_id": descarga_id, "estado": "en_progreso"}


@app.get("/api/pivote/descargar-cui/{descarga_id}")
def descargar_cui_estado(descarga_id: str):
    est = _leer_descarga_cui(descarga_id)
    if est is None:
        raise HTTPException(404, "descarga no existe")
    est["listo"] = est.get("estado") == "listas"
    return est


@app.get("/api/pivote/descargar-cui/{descarga_id}/zip")
def descargar_cui_zip(descarga_id: str):
    est = _leer_descarga_cui(descarga_id)
    if est is None:
        raise HTTPException(404, "descarga no existe")
    if est.get("estado") == "error":
        raise HTTPException(409, est.get("error") or "la descarga falló")
    ruta = DATA_DIR / f"{descarga_id}.cui.zip"
    if est.get("estado") != "listas" or not ruta.exists():
        return JSONResponse(status_code=202, content={
            "estado": est.get("estado"),
            "mensaje": "El ZIP se está preparando: descargando los documentos de InfoObras."})
    return FileResponse(ruta, media_type="application/zip",
                        filename=f"InfoObras_CUI_{est['cui']}.zip")


# ── Salud de portales ────────────────────────────────────────────────────────

_SALUD_CACHE: dict = {"ts": 0.0, "data": None}
_SALUD_TTL = 60.0  # el panel sondea cada ~30s; cacheamos para no golpear los portales


@app.get("/api/pivote/salud")
def salud():
    # En modo NO-real (tests/esqueleto) no hay portales que sondear → operativo sin red.
    if os.getenv("PIVOTE_ETAPAS") != "real":
        return [
            {"portal": "sunat", "ok": True, "diagnostico": None, "desde": None},
            {"portal": "infoobras", "ok": True, "diagnostico": None, "desde": None},
        ]
    import time
    ahora = time.time()
    if _SALUD_CACHE["data"] and ahora - _SALUD_CACHE["ts"] < _SALUD_TTL:
        return _SALUD_CACHE["data"]
    from scraping.infoobras import sondear as _sondear_infoobras
    from scraping.sunat import sondear as _sondear_sunat
    desde = datetime.now(timezone.utc).isoformat()
    out = []
    for portal, fn in (("sunat", _sondear_sunat), ("infoobras", _sondear_infoobras)):
        try:
            ok, diag = fn()
        except Exception:  # noqa: BLE001 — /salud nunca debe romper
            ok, diag = False, "error interno"
        out.append({"portal": portal, "ok": ok, "diagnostico": diag, "desde": desde})
    _SALUD_CACHE.update(ts=ahora, data=out)
    return out
