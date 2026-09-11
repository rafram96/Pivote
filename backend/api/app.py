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
import threading
import time
import uuid
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# config carga el .env de la raíz ANTES de leer el entorno o importar módulos
# que fijan constantes desde os.getenv (retries, throttle…). override=False → el
# entorno real y los tests (que setean su propio PIVOTE_ETAPAS) siempre ganan.
import config  # noqa: E402 — el import ejecuta load_dotenv

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from entregables import (
    completar_revisiones_privadas, construir_zip_infoobras, descargar_cui,
    generar_excel_final, mapear_certificados, reconciliar_resultados_profesionales,
    regenerar_excel_final, _zip_carpeta,
)
from entregables.certeza import (
    alertas_experiencia, fuente_mef_panel, identificacion_panel,
    normalizar_motivo_fuente, resumen_certeza_profesional,
)
from entregables.procedencia import procedencia_cui
from orquestador import Motor, RepositorioArchivos, etapas_esqueleto, etapas_reales
from orquestador.progreso import REGISTRO
from resolucion.cui import TIPO_EXPEDIENTES, tipo_evaluacion_del_espejo
from schemas import pipeline
from schemas.espejo import JsonEspejo
from schemas.nombres import nombre_descarga
from scraping.renipress import buscar_renipress
from validacion.recalculo import regla_periodos_de

# Carpeta de datos: definible en el .env de la raíz (PIVOTE_DATA_DIR). Rutas
# relativas quedan ancladas a backend/ — no al CWD (ver backend/config.py).
DATA_DIR = config.data_dir()
# Log a archivo (<DATA_DIR>/logs/backend.log) además de consola: sin esto los
# INFO de las etapas (tiempos, reintentos, portales caídos) se perdían.
from infraestructura.registro import configurar_registro  # noqa: E402
configurar_registro(DATA_DIR)

app = FastAPI(title="InfoObras Pivote API", version="0.2.0")
# Persistencia: los ARCHIVOS son siempre la fuente de verdad (una carpeta por
# job en DATA_DIR). Con PIVOTE_DB_URL, Postgres se suma como RESPALDO LÓGICO
# write-through (best-effort: si la BD se cae, el análisis sigue).
repo = RepositorioArchivos(DATA_DIR)
if os.getenv("PIVOTE_DB_URL"):
    from orquestador.repositorio import RepositorioConRespaldo
    from orquestador.repositorio_pg import RepositorioPostgres
    # El respaldo es OPCIONAL, así que su ausencia no puede impedir arrancar:
    # se sondea UNA vez aquí (abre el pool y aplica el DDL) con un tope de
    # PIVOTE_DB_TIMEOUT_BOOT segundos. Si la BD no responde —el caso típico es
    # un `compose up` que levanta Postgres y backend a la vez— se avisa una
    # sola vez y el backend corre 100% sobre archivos, igual que la base MEF
    # cuando su índice no está. No se avisa por request: el respaldo queda
    # simplemente desactivado en esta corrida.
    _respaldo_pg = RepositorioPostgres(os.getenv("PIVOTE_DB_URL"))
    try:
        _respaldo_pg.abrir(timeout=float(os.getenv("PIVOTE_DB_TIMEOUT_BOOT") or 5))
    except Exception as e:  # noqa: BLE001 — cualquier fallo de la BD degrada, no tumba
        logging.getLogger(__name__).warning(
            "Postgres no respondió al arrancar (%s: %s). El respaldo lógico queda "
            "DESACTIVADO en esta corrida; los análisis siguen sobre archivos, que "
            "son la fuente de verdad. Para reactivarlo: levantar la BD y reiniciar "
            "el backend (scripts/migrar_a_postgres.py re-sincroniza lo escrito "
            "mientras estuvo caída).", type(e).__name__, e)
    else:
        repo = RepositorioConRespaldo(repo, _respaldo_pg)


def _dir_job(job_id: str) -> Path:
    """Carpeta única del job en DATA_DIR (ahí viven TODOS sus artefactos)."""
    from orquestador.repositorio import carpeta_job
    return carpeta_job(DATA_DIR, job_id)


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
    # En modo real, la verificación de expedientes contra el MEF (T-003) se activa
    # con PIVOTE_VERIFICAR_MEF=1 (default ON en real; poner 0 para desactivarla).
    _verif_mef = None
    if (os.getenv("PIVOTE_VERIFICAR_MEF", "1") or "1").strip() not in ("0", "no", "false"):
        from scraping.mef import verificar_cui as _verif_mef
    motor = Motor(etapas_reales(DATA_DIR, verificador_mef=_verif_mef),
                  repo, reportar=_reportar_progreso)

ETAPA_FUENTE = {
    pipeline.Etapa.SUNAT: "SUNAT",
    pipeline.Etapa.INFOOBRAS: "InfoObras",
    pipeline.Etapa.RENIPRESS: "RENIPRESS",
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
    pipeline.Etapa.RENIPRESS: "Consulta del registro de establecimientos de salud",
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
# eso se bajan DESPUÉS del pipeline (sin bloquear el resultado). GET /zip solo
# empaqueta lo ya persistido; nunca abre una nueva descarga.
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
    d = _dir_job(job_id) / "descargas"
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
    """Ejecuta una sola pasada lógica por fuente y arma el ZIP con lo hallado.

    Cada clave se persiste antes de tocar red. Un fallo, reinicio, GET /zip o
    regeneración no vuelve a descargar la misma fuente.
    """
    job = repo.cargar(job_id)
    if job is None or job.descargas_estado in {"listas", "listas_con_errores"}:
        return
    with _lock_descargas(job_id):
        job = repo.cargar(job_id)                      # re-leer dentro del lock
        if job is None or job.descargas_estado in {"listas", "listas_con_errores"}:
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
            intentos = set(job.descargas_intentos or [])

            def _marcar_intento(clave: str) -> None:
                nonlocal job
                if clave in intentos:
                    return
                intentos.add(clave)
                job.descargas_intentos = sorted(intentos)
                repo.guardar(job)  # antes de la llamada de red

            stats = descargar_documentos_job(espejo, enr, job_id, DATA_DIR,
                                             max_descargas=maxd, reportar=_rep,
                                             intentos_documentos=intentos,
                                             marcar_intento=_marcar_intento)
            # El manifiesto por experiencia es parte del enriquecimiento persistente:
            # alimenta tanto el Excel como el índice y sobrevive a un reinicio.
            repo.guardar_enriquecimiento(job_id, enr)
            # arma el ZIP COMPLETO recién ahora que están TODOS los documentos
            # (atómico → reemplaza cualquier zip parcial previo).
            ruta_zip = _dir_job(job_id) / "infoobras.zip"
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
            parciales = [d for k, d in enr.items() if ":" in k and not k.startswith("prof:")
                         and isinstance(d, dict)
                         and isinstance(d.get("descargas_reales"), dict)
                         and not d["descargas_reales"].get("completada")]
            job.descargas_estado = "listas_con_errores" if parciales else "listas"
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
    # Vía el repo (NO glob de *.job.json): con PIVOTE_DB_URL los jobs viven en
    # Postgres y el glob no encontraría nada — la reanudación quedaba muerta.
    try:
        jobs = repo.listar()
    except Exception:  # noqa: BLE001 — un arranque nunca debe caerse por esto
        logger.exception("no se pudo listar jobs para reanudar")
        return
    for j in jobs:
        jid = j.job_id
        # pipeline cortado a medias (crash/reinicio) → retomar. `motor.correr` es
        # reanudable (salta etapas ya hechas). Si no, el job queda en 'en_proceso'
        # para siempre, sin recuperación ni desde la UI.
        if j.estado == pipeline.JobEstado.EN_PROCESO:
            threading.Thread(target=_correr_y_descargar, args=(jid,), daemon=True).start()
            logger.info("reanudando pipeline interrumpido del job %s tras reinicio", jid)
            continue
        # Solo "en_progreso" = descarga genuinamente interrumpida. "pendiente" puede
        # ser un job viejo (el campo se defaulteó) → NO lo re-disparamos.
        if j.descargas_estado == "en_progreso":
            threading.Thread(target=_asegurar_descargas, args=(jid,), daemon=True).start()
            logger.info("continuando documentos nunca intentados del job %s tras reinicio", jid)


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
    """Avance compartido por /descargas y /progreso: experiencias ya procesadas
    frente a las descargables (las que están en revisión no bajan), más la obra en
    curso. Procesada no implica que la fuente tuviera documentos publicados."""
    espejo = repo.cargar_espejo(job.job_id) or {}
    enr = repo.cargar_enriquecimiento(job.job_id) or {}

    def _tiene_fuente(clave: tuple[int, int]) -> bool:
        d = enr.get(f"{clave[0]}:{clave[1]}") or {}
        obra = d.get("obra") if isinstance(d.get("obra"), dict) else {}
        return bool(obra.get("obra_id") or d.get("seace"))

    todas = [(p["n_prof"], e["n"])
             for p in espejo.get("profesionales", [])
             for e in p.get("experiencias", [])
             if _tiene_fuente((p["n_prof"], e["n"]))]
    rev = {(it.n_prof, it.n_exp) for it in job.items_revision if not it.resuelto}
    bajan = [x for x in todas if x not in rev]

    def _procesada(clave: tuple[int, int]) -> bool:
        datos = enr.get(f"{clave[0]}:{clave[1]}") or {}
        manifiesto = datos.get("descargas_reales")
        if isinstance(manifiesto, dict):
            return bool(manifiesto.get("completada"))

        # Compatibilidad con jobs anteriores al manifiesto: las marcas solo se
        # publican al terminar cada fuente. Una experiencia sin documentos puede
        # estar correctamente procesada y no debe quedar como pendiente perpetua.
        base = _dir_job(job.job_id) / "descargas"
        obra = datos.get("obra") if isinstance(datos.get("obra"), dict) else {}
        infoobras_ok = (not obra.get("obra_id")
                        or (base / f"P{clave[0]}_E{clave[1]}.ok").exists())
        seace_ok = (not datos.get("seace")
                    or (base / f"P{clave[0]}_E{clave[1]}.seace.ok").exists())
        return bool(infoobras_ok and seace_ok)

    descargadas = sum(
        1 for x in bajan if _procesada(x)
    )
    total = len(bajan)
    viva = REGISTRO.etapas(job.job_id).get("descargas")
    return {
        "estado": job.descargas_estado,
        "listo": job.descargas_estado in {"listas", "listas_con_errores"},
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
    RegistroProgreso en memoria (el 'qué está pasando ahora'). INFOOBRAS, SUNAT
    y RENIPRESS pueden aparecer 'en_curso' a la vez: corren en paralelo."""
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

def _validar_certificados(contenido: bytes) -> list[tuple[str, bytes]]:
    """Valida el ZIP completo antes de que exista un job.

    Conserva el filtro histórico de nombres y las defensas contra ZIP bomb y
    path traversal, pero deja de aceptar en silencio un ZIP roto o un archivo
    con extensión PDF cuyo contenido no sea PDF.
    """
    import io
    import os
    import zipfile
    if not contenido:
        return []
    certificados: list[tuple[str, bytes]] = []
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
                    pdf = z.read(info.filename)
                    if not pdf.startswith(b"%PDF-"):
                        raise HTTPException(422, f"{base} no contiene un PDF válido")
                    certificados.append((base, pdf))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            422, "el archivo de certificados no es un ZIP válido"
        ) from exc
    return certificados


def _guardar_certificados(
    job_id: str, certificados: list[tuple[str, bytes]]
) -> int:
    """Guarda certificados ya validados en la carpeta actual del job."""
    if not certificados:
        return 0
    cdir = _dir_job(job_id) / "certs"
    cdir.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in certificados:
        (cdir / nombre).write_bytes(contenido)
    return len(certificados)


def _aplicar_tipo_evaluacion(datos: dict, form_valor: Optional[str]) -> Optional[str]:
    """ADR-010 · deja `_meta.tipo_evaluacion` canónico antes de crear el job.

    Precedencia: parámetro del espejo (lo declaró la skill leyendo las bases) >
    form-field del dropzone/MCP (override manual). Un valor fuera del vocabulario
    cerrado es 422: el enrutado expediente/obra no puede quedar ambiguo en
    silencio, porque decide qué fuentes se consultan para TODO el análisis.
    Devuelve el tipo aplicado o None (sin parámetro → env/texto, como antes).
    """
    from resolucion.cui import normalizar_tipo_evaluacion

    meta = datos.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        datos["_meta"] = meta
    declarado = meta.get("tipo_evaluacion")
    if declarado not in (None, ""):
        tipo = normalizar_tipo_evaluacion(declarado)
        if tipo is None:
            raise HTTPException(422, {
                "error": "tipo_evaluacion del espejo no reconocido",
                "valor": str(declarado)[:60],
                "permitidos": ["expedientes", "obras"]})
        meta["tipo_evaluacion"] = tipo
        return tipo
    if form_valor not in (None, ""):
        tipo = normalizar_tipo_evaluacion(form_valor)
        if tipo is None:
            raise HTTPException(422, {
                "error": "tipo_evaluacion no reconocido",
                "valor": str(form_valor)[:60],
                "permitidos": ["expedientes", "obras"]})
        meta["tipo_evaluacion"] = tipo
        return tipo
    return None


@app.post("/api/pivote/analizar", status_code=201)
async def analizar(
    tareas: BackgroundTasks,
    concurso_id: str = Form(...),
    espejo: UploadFile = File(...),
    excel: UploadFile = File(...),
    origen: str = Form("dropzone"),
    certificados: UploadFile | None = File(None),
    tipo_evaluacion: str | None = Form(None),
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
    _aplicar_tipo_evaluacion(datos, tipo_evaluacion)

    contenido_excel = await _leer_limitado(excel, _MAX_EXCEL, "el Excel")
    contenido_certs = (
        await _leer_limitado(certificados, _MAX_CERTS, "los certificados")
        if certificados is not None
        else b""
    )
    certificados_validados = _validar_certificados(contenido_certs)

    # A partir de aquí todos los insumos ya pasaron sus validaciones. Crear el
    # job antes dejaría huérfanos ante un Excel grande, ZIP roto o falso PDF.
    job = motor.crear_job(datos, concurso_id=concurso_id)
    job.origen = origen if origen in ("mcp", "dropzone") else "dropzone"
    repo.guardar(job)
    # guardar el Excel de Claude tal cual llegó (referencia/auditoría)
    (_dir_job(job.job_id) / "claude.xlsx").write_bytes(contenido_excel)
    # certificados de las experiencias (ZIP de PDFs que recortó la skill) → {job}.certs/
    _guardar_certificados(job.job_id, certificados_validados)

    tareas.add_task(_correr_y_descargar, job.job_id)
    return {"job_id": job.job_id}


@app.get("/api/pivote/jobs/{job_id}")
def ver_job(job_id: str):
    return json.loads(_job_o_404(job_id).model_dump_json())


def _confiabilidad_excel(job: pipeline.Job) -> dict:
    """Contrato único para el banner de confiabilidad del Excel."""
    return {
        "veredicto": job.confiabilidad,
        "hallazgos_criticos": [
            o.model_dump(mode="json") for o in job.hallazgos_criticos
        ],
    }


def _sembrar_ledger_legado(job: pipeline.Job) -> None:
    """Migra jobs terminales previos al ledger sin repetir ninguna descarga."""
    if job.descargas_intentos or job.descargas_estado not in {
            "listas", "listas_con_errores", "error"}:
        return
    from orquestador.descargas_seace import clave_archivo_seace

    claves: set[str] = set()
    for dato in (repo.cargar_enriquecimiento(job.job_id) or {}).values():
        if not isinstance(dato, dict):
            continue
        obra = dato.get("obra") if isinstance(dato.get("obra"), dict) else {}
        if obra.get("obra_id"):
            claves.add(f"infoobras:{obra['obra_id']}")
        seace = dato.get("seace") if isinstance(dato.get("seace"), dict) else {}
        for doc in (seace.get("docs") or {}).values():
            if isinstance(doc, dict) and doc.get("url"):
                claves.add(f"seace:{clave_archivo_seace(doc['url'])}")
    job.descargas_intentos = sorted(claves)
    repo.guardar(job)


def _marcar_correccion(
        job: pipeline.Job, correccion_id: str, estado: str) -> None:
    correccion = next(
        (c for c in job.correcciones_humanas
         if c.correccion_id == correccion_id), None)
    if correccion is None:
        return
    correccion.estado = estado
    if estado == "aplicada":
        correccion.aplicado_en = datetime.now(timezone.utc)


def _resolver_revision_background(
        job_id: str, n_prof: int, n_exp: int, body: dict,
        correccion_id: str):
    """Re-ejecuta la experiencia fuera del request y deja un estado consultable."""
    with _lock_descargas(job_id):
        try:
            previo = repo.cargar(job_id)
            if previo is not None:
                _sembrar_ledger_legado(previo)
            job = motor.resolver_revision(job_id, n_prof, n_exp, body)
            # La obra/CUI puede cambiar. El ledger permitirá únicamente fuentes
            # lógicas nuevas; las ya intentadas se reutilizan desde disco.
            job.descargas_estado = "pendiente"
            job.revision_estado = "completada"
            job.revision_error = None
            _marcar_correccion(job, correccion_id, "aplicada")
            repo.guardar(job)
        except Exception as exc:  # el fallo debe sobrevivir al log y llegar al panel
            logger.exception("falló revisión background job=%s item=%s:%s", job_id, n_prof, n_exp)
            job = repo.cargar(job_id)
            if job:
                job.revision_estado = "error"
                job.revision_error = str(exc) or type(exc).__name__
                _marcar_correccion(job, correccion_id, "error")
                repo.guardar(job)
            return
    _asegurar_descargas(job_id)  # solo intentará fuentes lógicas nuevas


@app.post("/api/pivote/jobs/{job_id}/revision", status_code=202)
def resolver_revision(job_id: str, tareas: BackgroundTasks, body: dict):
    n_prof, n_exp = body.get("n_prof"), body.get("n_exp")
    if not isinstance(n_prof, int) or not isinstance(n_exp, int):
        raise HTTPException(400, "n_prof y n_exp son obligatorios")
    if not body.get("cui") and body.get("accion") != "no_existe":
        raise HTTPException(400, "se requiere cui o accion='no_existe'")
    with _lock_descargas(job_id):
        job = _job_o_404(job_id)
        item = next((it for it in job.items_revision
                     if it.n_prof == n_prof and it.n_exp == n_exp and not it.resuelto), None)
        if item is None:
            raise HTTPException(
                404, f"no hay ItemRevision pendiente para prof={n_prof} exp={n_exp}")
        if job.revision_estado == "en_curso":
            raise HTTPException(409, "ya hay una revisión guardándose para este análisis")
        enr = repo.cargar_enriquecimiento(job_id) or {}
        anterior = (enr.get(f"{n_prof}:{n_exp}") or {}).get("cui")
        correccion_id = uuid.uuid4().hex[:12]
        job.correcciones_humanas.append(pipeline.CorreccionHumana(
            correccion_id=correccion_id,
            n_prof=n_prof,
            n_exp=n_exp,
            campo="cui",
            accion=("no_existe" if body.get("accion") == "no_existe"
                    else "confirmado"),
            valor_anterior=str(anterior) if anterior else None,
            valor_corregido=(str(body.get("cui")) if body.get("cui") else None),
            creado_en=datetime.now(timezone.utc),
        ))
        job.revision_estado = "en_curso"
        job.revision_item = f"{n_prof}:{n_exp}"
        job.revision_error = None
        repo.guardar(job)
    tareas.add_task(
        _resolver_revision_background, job_id, n_prof, n_exp, dict(body),
        correccion_id)
    return json.loads(job.model_dump_json())


def _corregir_ruc_background(
        job_id: str, n_prof: int, n_exp: int, ruc: str,
        correccion_id: str) -> None:
    """Recalcula SUNAT y el Excel sin tocar el corpus de descargas."""
    with _lock_descargas(job_id):
        try:
            job = motor.corregir_ruc(job_id, n_prof, n_exp, ruc)
            if job.estado == pipeline.JobEstado.ERROR:
                raise RuntimeError("el reanálisis terminó con un error estructural")
            job.revision_estado = "completada"
            job.revision_error = None
            _marcar_correccion(job, correccion_id, "aplicada")
            repo.guardar(job)
        except Exception as exc:  # el estado debe sobrevivir al request 202
            logger.exception(
                "falló corrección RUC job=%s item=%s:%s", job_id, n_prof, n_exp)
            job = repo.cargar(job_id)
            if job:
                job.revision_estado = "error"
                job.revision_error = str(exc) or type(exc).__name__
                _marcar_correccion(job, correccion_id, "error")
                repo.guardar(job)


@app.post("/api/pivote/jobs/{job_id}/correcciones/ruc", status_code=202)
def corregir_ruc(job_id: str, tareas: BackgroundTasks, body: dict):
    """Corrige el RUC de una experiencia y regenera resultados/Excel.

    No reejecuta InfoObras ni cambia el ledger de descargas. El CUI se corrige
    por la cola de revisión, donde sí se recalculan las fuentes de la obra.
    """
    n_prof, n_exp = body.get("n_prof"), body.get("n_exp")
    if not isinstance(n_prof, int) or not isinstance(n_exp, int):
        raise HTTPException(400, "n_prof y n_exp son obligatorios")
    ruc_bruto = str(body.get("ruc") or "").strip()
    ruc = "".join(c for c in ruc_bruto if c.isdigit())
    if len(ruc) != 11 or any(c.isalpha() for c in ruc_bruto):
        raise HTTPException(400, "el RUC debe tener exactamente 11 dígitos")

    with _lock_descargas(job_id):
        job = _job_o_404(job_id)
        if job.revision_estado == "en_curso":
            raise HTTPException(409, "ya hay una corrección guardándose para este análisis")
        espejo = _espejo_o_404(job_id)
        profesional = next(
            (p for p in espejo.get("profesionales", [])
             if p.get("n_prof") == n_prof), None)
        experiencia = next(
            (e for e in (profesional or {}).get("experiencias", [])
             if e.get("n") == n_exp), None)
        if experiencia is None:
            raise HTTPException(
                404, f"no existe experiencia para prof={n_prof} exp={n_exp}")
        anterior = "".join(
            c for c in str(experiencia.get("ruc_emisor") or "") if c.isdigit())
        if anterior == ruc:
            raise HTTPException(409, "ese RUC ya está aplicado a la experiencia")

        correccion_id = uuid.uuid4().hex[:12]
        job.correcciones_humanas.append(pipeline.CorreccionHumana(
            correccion_id=correccion_id,
            n_prof=n_prof,
            n_exp=n_exp,
            campo="ruc_emisor",
            accion="corregido",
            valor_anterior=anterior or None,
            valor_corregido=ruc,
            creado_en=datetime.now(timezone.utc),
        ))
        job.revision_estado = "en_curso"
        job.revision_item = f"{n_prof}:{n_exp}"
        job.revision_error = None
        repo.guardar(job)

    tareas.add_task(
        _corregir_ruc_background, job_id, n_prof, n_exp, ruc, correccion_id)
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


# ── Consulta RENIPRESS ───────────────────────────────────────────────────────

@app.get("/api/pivote/renipress")
def consultar_renipress(q: str = "", solo_activos: bool = True, limite: int = 50):
    """Consulta RENIPRESS con un contrato apto para integraciones.

    HTTP 200 + `sin_resultados` significa que la fuente respondió sin filas.
    HTTP 503 + `portal_no_disponible` conserva la incertidumbre cuando SUSALUD
    falla; un integrador no debe interpretar ambos escenarios de igual manera.
    """
    q = (q or "").strip()
    if len(q) < 2 or len(q) > 120:
        raise HTTPException(400, "q debe tener entre 2 y 120 caracteres")
    if not 1 <= limite <= 500:
        raise HTTPException(400, "limite debe estar entre 1 y 500")
    resultado = buscar_renipress(
        q, solo_activos=solo_activos, max_filas=limite
    )
    contenido = resultado.to_dict()
    if resultado.estado == "portal_no_disponible":
        return JSONResponse(status_code=503, content=contenido)
    return contenido


# ── Vistas derivadas (extracción + resumen) ──────────────────────────────────

def _estado_veredicto(texto: str) -> str:
    """Clasificación estructurada; evita que la UI interprete prosa libre."""
    normalizado = texto.strip().upper()
    if "NO CUMPLE" in normalizado:
        return "no_cumple"
    if normalizado.startswith(("POR VERIFICAR", "POR CONFIRMAR", "PENDIENTE")):
        return "por_confirmar"
    if "CUMPLE" in normalizado or normalizado.startswith(("SÍ", "SI ", "SI—", "SI —")):
        return "cumple"
    return "por_confirmar"


@app.get("/api/pivote/jobs/{job_id}/investigacion-identidad")
def contexto_investigacion_identidad(job_id: str):
    """Foto de lectura del primer resultado; no activa investigación ni descargas."""
    job = _job_o_404(job_id)
    estado = getattr(job.estado, "value", job.estado)
    if estado not in {"completado", "requiere_revision"}:
        raise HTTPException(409, "El resultado inicial todavía no está disponible para investigar")
    from entregables.investigacion_identidad import preparar_contexto
    espejo = _espejo_o_404(job_id)
    tipo = tipo_evaluacion_del_espejo(espejo)
    if tipo not in {"obras", "expedientes"}:
        raise HTTPException(409, "La ruta de evaluación debe estar determinada antes de investigar")
    return preparar_contexto(job_id, espejo, repo.cargar_enriquecimiento(job_id) or {},
                             tipo)


def _descargar_identidad_aplicada(job_id: str):
    from orquestador.recontraste_identidad import recontrastar_asociaciones
    directorio = _dir_job(job_id)
    try:
        with _lock_descargas(job_id):
            pendiente = json.loads((directorio / "identidad_contraste_pendiente.json").read_text(encoding="utf-8"))
            espejo = repo.cargar_espejo(job_id)
            nuevo = recontrastar_asociaciones(espejo, repo.cargar_enriquecimiento(job_id), pendiente["casos"])
            repo.guardar_enriquecimiento(job_id, nuevo)
        _asegurar_descargas(job_id)
        with _lock_descargas(job_id):
            job = repo.cargar(job_id)
            if not job or job.descargas_estado not in {"listas", "listas_con_errores"}:
                raise RuntimeError("Descarga incompleta")
            if not (directorio / "infoobras.zip").is_file():
                raise RuntimeError("ZIP no publicado")
            actual = json.loads((directorio / "identidad_contraste_pendiente.json").read_text(encoding="utf-8"))
            if actual["revision"] != pendiente["revision"]:
                raise RuntimeError("La revisión cambió durante la publicación")
            enr = repo.cargar_enriquecimiento(job_id)
            afectados = {tuple(map(int, cid.split(":")[:2])) for cid in pendiente["casos"]}
            revisiones = {(it.n_prof, it.n_exp): (it.motivo, it.accion_sugerida)
                          for it in job.items_revision if not it.resuelto and (it.n_prof, it.n_exp) not in afectados}
            for np, ne in afectados:
                revisiones[np, ne] = ((enr.get(f"{np}:{ne}") or {}).get("decision"),
                                      "Revisar las fuentes corregidas; el sistema no emite dictamen.")
            # El respaldo conserva la cola anterior. La cola activa no debe
            # seguir diciendo que falta el CUI que acaba de corregirse.
            etapas_identidad = {pipeline.Etapa.RESOLUCION_CUI, pipeline.Etapa.INFOOBRAS, pipeline.Etapa.REGLAS}
            job.items_revision = [it for it in job.items_revision
                if (it.n_prof, it.n_exp) not in afectados or it.etapa not in etapas_identidad]
            for np, ne in sorted(afectados):
                motivo, accion = revisiones[np, ne]
                job.items_revision.append(pipeline.ItemRevision(n_prof=np, n_exp=ne,
                    etapa=pipeline.Etapa.INFOOBRAS, motivo=motivo or "Identidad corregida; revisar evidencia.",
                    accion_sugerida=accion))
            completar_revisiones_privadas(revisiones, enr)
            temporal = directorio / "identidad_nueva.xlsx"
            regenerar_excel_final(deepcopy(espejo), deepcopy(enr), temporal, revisiones,
                                  mapear_certificados(DATA_DIR, job_id), confiabilidad=_confiabilidad_excel(job))
            os.replace(temporal, directorio / "final.xlsx")
            job.excel_final = f"/api/pivote/jobs/{job_id}/excel"
            job.revision_estado = "completada"
            job.revision_error = None
            job.observaciones.append(pipeline.Observacion(codigo="IDENTIDAD_ACTUALIZADA",
                mensaje="Fuentes y contraste actualizados tras corrección de identidad; faltantes explícitos en cada experiencia. Las observaciones de etapas anteriores son históricas.",
                origen=pipeline.Etapa.INFOOBRAS))
            repo.guardar(job)
            # El diario principal se retira al final: no existe ventana con un
            # entregable habilitado mientras el otro todavía conserva datos viejos.
            (directorio / "identidad_contraste_pendiente.json").unlink()
            (directorio / "identidad_pendiente.json").unlink()
    except Exception:
        logger.exception("Recontraste de identidad job %s incompleto", job_id)
        with _lock_descargas(job_id):
            job = repo.cargar(job_id)
            if job:
                job.revision_estado = "error"
                job.revision_error = "Publicación de identidad incompleta; entregables bloqueados y respaldo conservado."
                repo.guardar(job)


@app.post("/api/pivote/jobs/{job_id}/investigacion-identidad/aplicar", status_code=202)
def aplicar_investigacion_identidad(job_id: str, tareas: BackgroundTasks, body: dict):
    """Aplica selecciones explícitas a fuentes documentales, nunca dictámenes."""
    from orquestador.aplicar_identidad import proyectar_asociaciones, publicar_asociaciones
    with _lock_descargas(job_id):
        job = _job_o_404(job_id)
        if (getattr(job.estado, "value", job.estado) not in {"completado", "requiere_revision"}
                or job.revision_estado == "en_curso" or job.descargas_estado == "en_progreso"
                or (_dir_job(job_id) / "identidad_pendiente.json").exists()):
            raise HTTPException(409, "El job está ocupado o tiene una aplicación pendiente")
        espejo = _espejo_o_404(job_id)
        tipo = tipo_evaluacion_del_espejo(espejo)
        if tipo not in {"obras", "expedientes"}:
            raise HTTPException(409, "Ruta de evaluación indeterminada")
        previo = repo.cargar_enriquecimiento(job_id) or {}
        try:
            nuevo, afectados = proyectar_asociaciones(
                job_id, espejo, previo, tipo, body.get("resultados"))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        _sembrar_ledger_legado(job)
        revision = publicar_asociaciones(repo, _dir_job(job_id), job_id, previo, nuevo, afectados)
        job.estado = pipeline.JobEstado.REQUIERE_REVISION
        job.confiabilidad = "revisar"
        job.observaciones.append(pipeline.Observacion(
            mensaje="Identidad investigada aplicada: actualización de fuentes y contraste en curso. No reutilizar conclusiones anteriores.",
            origen=pipeline.Etapa.INFOOBRAS, severidad=pipeline.Severidad.ADVERTENCIA))
        job.descargas_estado = "pendiente"
        job.revision_estado = "en_curso"
        job.revision_error = None
        repo.guardar(job)
    tareas.add_task(_descargar_identidad_aplicada, job_id)
    return {"revision": revision, "casos_aplicados": [c["caso_id"] for c in afectados],
            "descargas_estado": "pendiente", "contraste_derivado": "pendiente",
            "aviso": "Se actualizan fuentes, contraste y cálculos auxiliares; no es un dictamen. Entregables bloqueados hasta finalizar."}


@app.get("/api/pivote/jobs/{job_id}/espejo")
def extraccion(job_id: str):
    _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    enr = repo.cargar_enriquecimiento(job_id) or {}
    resultados = reconciliar_resultados_profesionales(espejo, enr)
    # ADR-010 · la certeza de identificación solo tiene sentido en un concurso de
    # ELABORACIÓN DE EXPEDIENTES (es lo que decide la PARTE 5 de esa hoja). En
    # «obras» la respuesta queda EXACTAMENTE como estaba.
    tipo_eval = tipo_evaluacion_del_espejo(espejo)
    certeza_aplica = tipo_eval == TIPO_EXPEDIENTES
    regla_periodos = regla_periodos_de(espejo)
    profesionales = []
    for p in espejo.get("profesionales", []):
        np_ = p.get("n_prof")
        experiencias = []
        for e in p.get("experiencias", []):
            d = {k: e.get(k) for k in (
                "n", "proyecto", "entidad_emisora", "cargo_ocupado",
                "fecha_inicial", "fecha_final", "dias", "cui",
                "incluye_covid", "traslape", "folio", "ruc_emisor",
                "nombre_emisor", "cargo_emisor", "fecha_emision",
                "tipo_documento", "entidad_contratante")}
            # enriquecimiento del backend: CUI resuelto + quién ejecutó/supervisó
            # la obra en InfoObras (Representante de obra) + verificación SUNAT.
            ev = enr.get(f"{np_}:{e.get('n')}")
            if isinstance(ev, dict):
                obra = ev.get("obra") or {}
                d["cui_resuelto"] = (procedencia_cui(e, ev)["cui_utilizado"]
                                     if certeza_aplica else obra.get("cui") or ev.get("cui"))
                d["obra_nombre"] = ev.get("obra_nombre") or obra.get("nombre_obra")
                d["via_resolucion"] = ev.get("via")
                d["representante_obra"] = ev.get("representante_obra")
                d["sunat"] = ev.get("sunat")
                d["verificacion_expediente"] = ev.get("verificacion_expediente")
                # El panel necesita los documentos y el candado del proceso para
                # explicar qué evidencia abre cada enlace (bases/contrato) y con
                # qué nivel de confianza fue asociado al certificado.
                d["seace"] = ev.get("seace")
                d["sub_obras"] = ev.get("sub_obras")
                d["multi_rubro"] = ev.get("multi_rubro")
                # Evidencia del MEF que la PARTE 5 del Excel ya lee: se expone
                # cruda para que el Panel pueda enlazar el documento y contrastar
                # fechas sin re-derivar nada.
                d["resolucion_aprobacion"] = ev.get("resolucion_aprobacion")
                d["camino"] = ev.get("camino")
                d["sin_documentos_mef"] = ev.get("sin_documentos_mef")
                d["contrato_emisor"] = ev.get("contrato_emisor")
                d["identificacion_incompleta"] = ev.get("identificacion_incompleta")
                d["cruces_fechas"] = ev.get("cruces_fechas")
            if certeza_aplica:
                # Misma clasificación (y mismos textos) que pinta el entregable:
                # una sola fuente de verdad para Excel y Panel.
                evd = ev if isinstance(ev, dict) else {}
                d["identificacion"] = identificacion_panel(e, evd)
                d["alertas"] = alertas_experiencia(e, evd)
                d["fuente_mef"] = fuente_mef_panel(evd)
                cruces = evd.get("cruces_fechas")
                if isinstance(cruces, list):
                    d["cruces_fechas"] = [
                        ({**cruce,
                          "motivo": normalizar_motivo_fuente(cruce.get("motivo"))}
                         if isinstance(cruce, dict) else cruce)
                        for cruce in cruces
                    ]
            experiencias.append(d)
        resultado = resultados.get(np_) or {}
        veredicto_efectivo = resultado.get("cumple_backend") or p.get("cumple")
        texto_efectivo = str(veredicto_efectivo or "").upper()
        estado_efectivo = _estado_veredicto(texto_efectivo)
        certeza = (resumen_certeza_profesional(p, enr, regla_periodos, tipo_eval)
                   if certeza_aplica else None)
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
            "cumple_backend": resultado.get("cumple_backend"),
            "veredicto_efectivo": veredicto_efectivo,
            "estado_efectivo": estado_efectivo,
            "total_efectivo": {
                "dias": resultado.get("dias_efectivos"),
                "anios": resultado.get("anios_efectivos"),
                "provisional": bool(resultado.get("veredicto_provisional")),
            },
            "certeza": certeza,
            "experiencias": experiencias,
        })
    return {"profesionales": profesionales, "tipo_evaluacion": tipo_eval}


@app.get("/api/pivote/jobs/{job_id}/resumen")
def resumen(job_id: str):
    job = _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    decisiones = _decisiones(job_id)

    enr = repo.cargar_enriquecimiento(job_id)
    resultados = reconciliar_resultados_profesionales(espejo, enr)
    # ADR-010 · igual que en /espejo: el desglose por certeza es de expedientes.
    tipo_eval = tipo_evaluacion_del_espejo(espejo)
    certeza_aplica = tipo_eval == TIPO_EXPEDIENTES
    regla_periodos = regla_periodos_de(espejo)
    veredictos = []
    for p in espejo.get("profesionales", []):
        total = p.get("total") or {}
        np_ = p.get("n_prof")
        d = resultados.get(np_) or {}
        motivo = None
        if d.get("dias_paralizados") or d.get("dias_traslape"):
            partes = []
            if d.get("dias_paralizados"):
                partes.append(f"periodos no efectivos: -{d['dias_paralizados']} días")
            if d.get("dias_traslape"):
                partes.append(f"traslapes entre experiencias: -{d['dias_traslape']} días")
            motivo = " · ".join(partes)
        veredicto_efectivo = d.get("cumple_backend") or p.get("cumple")
        texto_efectivo = str(veredicto_efectivo or "").upper()
        estado_efectivo = _estado_veredicto(texto_efectivo)
        veredictos.append({
            "n_prof": np_,
            "cargo": p.get("cargo"),
            "cargo_bases_num": p.get("cargo_bases_num"),
            "cargo_bases_nombre": p.get("cargo_bases_nombre"),
            "nombre": p.get("nombre"),
            "cumple_claude": p.get("cumple") or "(sin veredicto en el espejo)",
            "anios_brutos": (round(d["dias_brutos"] / 365, 2)
                              if d.get("dias_brutos") is not None
                              else total.get("anios")),
            "cumple_backend": d.get("cumple_backend"),
            "veredicto_efectivo": veredicto_efectivo,
            "estado_efectivo": estado_efectivo,
            "anios_efectivos": d.get("anios_efectivos"),
            "minimo_anios": d.get("minimo_anios"),
            "motivo_backend": motivo,
            "fuente": "verificación determinística" if d else None,
            "certeza": (resumen_certeza_profesional(p, enr or {}, regla_periodos,
                                                    tipo_eval)
                        if certeza_aplica else None),
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
    # Contrato v1.4: un factor puede estar CONDICIONADO (puntaje None con un rango
    # confirmado/máximo). Sin estos campos el Panel solo veía el None y pintaba
    # un puntaje mudo, indistinguible de «no aplica».
    factores = [
        {"factor": f.get("factor"), "criterio": f.get("criterio"),
         "puntaje": f.get("puntaje"), "detalle": f.get("detalle"),
         "aplica": f.get("aplica"),
         "estado_puntaje": f.get("estado_puntaje"),
         "puntaje_confirmado": f.get("puntaje_confirmado"),
         "puntaje_maximo_posible": f.get("puntaje_maximo_posible")}
        for f in re_.get("factores", [])
    ]
    conteo_alertas = {
        "requieren_atencion": sum(a["severidad"] in ("critica", "alerta") for a in alertas),
        "advertencias": sum(a["severidad"] == "advertencia" for a in alertas),
        "informativas": sum(a["severidad"] == "info" for a in alertas),
        "total": len(alertas),
    }
    return {
        "job_id": job_id,
        "postor": job.postor or job.analisis_id,
        "tipo_evaluacion": tipo_eval,
        "confiabilidad": job.confiabilidad,
        "hallazgos_criticos": [
            o.model_dump(mode="json") for o in job.hallazgos_criticos
        ],
        "veredictos": veredictos,
        "alertas": alertas,
        "conteo_alertas": conteo_alertas,
        "factores": factores,
        "puntaje_total": re_.get("puntaje_total"),
        "puntaje_confirmado": re_.get("puntaje_confirmado"),
        "puntaje_maximo_posible": re_.get("puntaje_maximo_posible"),
        "estado_puntaje": re_.get("estado_puntaje"),
        "nota_puntaje": re_.get("nota"),
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
    if any((_dir_job(job_id) / n).exists() for n in
           ("identidad_pendiente.json", "identidad_contraste_pendiente.json")):
        raise HTTPException(409, "Identidad corregida: contraste derivado pendiente; no se sirve un Excel anterior")
    espejo = _espejo_o_404(job_id)
    ruta = _dir_job(job_id) / "final.xlsx"
    if not ruta.exists():
        enr = repo.cargar_enriquecimiento(job_id) or {}
        revisiones = {
            (it.n_prof, it.n_exp): (it.motivo, it.accion_sugerida)
            for it in job.items_revision if not it.resuelto and it.n_exp is not None
        }
        completar_revisiones_privadas(revisiones, enr)
        regenerar_excel_final(
            espejo, enr, ruta, revisiones, mapear_certificados(DATA_DIR, job_id),
            confiabilidad=_confiabilidad_excel(job),
        )
        job.excel_final = f"/api/pivote/jobs/{job_id}/excel"
        repo.guardar(job)
    return FileResponse(
        ruta,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nombre_descarga(job, espejo, "xlsx"),
    )


# Serializa el armado del ZIP: dos descargas concurrentes no deben rearmar el
# mismo ZIP de ~1 GB en paralelo (ni renombrarlo mientras otra petición lo sirve).
_zip_build_lock = threading.Lock()


@app.get("/api/pivote/jobs/{job_id}/zip")
def descargar_zip(job_id: str):
    job = _job_o_404(job_id)
    if any((_dir_job(job_id) / n).exists() for n in
           ("identidad_pendiente.json", "identidad_contraste_pendiente.json")):
        raise HTTPException(409, "Aplicación de identidad o descarga pendiente; ZIP anterior retirado")
    ruta = _dir_job(job_id) / "infoobras.zip"
    en_prep = {"descargas_estado": job.descargas_estado,
               "mensaje": "El ZIP se está preparando: descargando los documentos de InfoObras."}
    # Descargando activamente → el zip (si existe) es PARCIAL → no servirlo: 202.
    # El panel habilita al quedar `listas` o `listas_con_errores`.
    if job.descargas_estado in {"pendiente", "en_progreso"}:
        return JSONResponse(status_code=202, content=en_prep)
    if not ruta.exists():
        if job.descargas_estado in {"listas", "listas_con_errores"}:
            with _zip_build_lock:
                if not ruta.exists():
                    espejo = _espejo_o_404(job_id)
                    enr = repo.cargar_enriquecimiento(job_id) or {}
                    construir_zip_infoobras(espejo, _mapa_descargas(job_id), ruta, enriquecimiento=enr)
        else:
            return JSONResponse(status_code=409, content={
                "descargas_estado": job.descargas_estado,
                "mensaje": "El ZIP no está disponible.",
            })
    # ZIP terminal: puede contener todo lo encontrado o faltantes explícitos.
    return FileResponse(ruta, media_type="application/zip",
                        filename=nombre_descarga(job, ext="zip"))


# ── Descarga por un solo CUI (sin correr un análisis) ────────────────────────
# Baja TODOS los documentos de InfoObras de una obra a partir de su CUI y los
# entrega en un ZIP, reutilizando la misma maquinaria del ZIP de un análisis.
# Es un "dame los papeles de esta obra" suelto.
#
# Es un TRABAJO, no un request: el POST responde 201 al instante con un
# `descarga_id` y el trabajo sigue en background (un CUI puede traer cientos de
# MB y varios minutos — un request largo termina en ECONNRESET del otro lado).
# El estado vive en disco, no en memoria, así que sobrevive a un reinicio del
# backend y se consulta por polling:
#
#   POST /api/pivote/descargar-cui            → {descarga_id, estado}
#   GET  /api/pivote/descargar-cui/{id}       → {estado, paso, descargados, …}
#   GET  /api/pivote/descargar-cui/{id}/zip   → 202 mientras prepara, 200 el ZIP
#
# `estado` ∈ {en_progreso, listas, error} — los mismos tres nombres que usan las
# descargas de un job, para no tener dos vocabularios para lo mismo; `paso` es la
# frase en castellano de lo que está ocurriendo ahora. Estado en
# {descarga_id}.cui.json; documentos en {id}.cui-descargas/.

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
    red/disco). No relanza: deja el estado en el JSON de la descarga.

    Cada tramo se persiste apenas empieza (`paso`), así el que pollea ve avanzar
    algo aunque una sección tarde minutos. Mientras la descarga espera su turno
    del semáforo el paso dice justamente eso: esperar en cola no es estar colgado."""
    est = _leer_descarga_cui(descarga_id)
    if est is None:
        return

    def _anotar(mensaje: str) -> None:
        est["paso"] = mensaje
        est["actualizado_en"] = datetime.now(timezone.utc).isoformat()
        _guardar_descarga_cui(descarga_id, est)

    with _sem_analisis:
        est = _leer_descarga_cui(descarga_id) or est
        if est.get("estado") == "listas":
            return
        carpeta = DATA_DIR / f"{descarga_id}.cui-descargas"
        try:
            r = descargar_cui(est["cui"], carpeta,
                              fecha_inicio=_fecha_opt(est.get("fecha_inicio")),
                              fecha_fin=_fecha_opt(est.get("fecha_fin")),
                              progreso=_anotar)
            est.update({k: r.get(k) for k in
                        ("obra_id", "nombre", "descargados", "fallidos",
                         "secciones", "avisos", "error")})
            if r.get("obra_id") is None:
                est["estado"] = "error"
                est["paso"] = ("Ese CUI no corresponde a ninguna obra publicada "
                               "en InfoObras.")
                _guardar_descarga_cui(descarga_id, est)
                logger.info("DESCARGA-CUI %s · CUI %s no resolvió", descarga_id, est["cui"])
                return
            _anotar("Armando el ZIP con los documentos.")
            titulo = (f"InfoObras · CUI {est['cui']} · obra {r.get('obra_id')} · "
                      f"{r.get('nombre') or ''}".strip())
            _zip_carpeta(carpeta, DATA_DIR / f"{descarga_id}.cui.zip", titulo)
            est["estado"] = "listas"
            est["paso"] = (f"Listo: {r.get('descargados') or 0} documento(s) "
                           f"en el ZIP.")
            _guardar_descarga_cui(descarga_id, est)
            logger.info("DESCARGA-CUI %s · CUI %s · obra %s · %d arch",
                        descarga_id, est["cui"], r.get("obra_id"), r.get("descargados", 0))
        except Exception:
            logger.exception("descarga por CUI %s falló", descarga_id)
            est["estado"] = "error"
            est["error"] = "fallo al descargar de InfoObras"
            est["paso"] = ("La descarga se interrumpió: InfoObras no respondió "
                           "como se esperaba. Puedes volver a pedirla.")
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
        "paso": "En cola: esperando turno para consultar InfoObras.",
        "creado_en": datetime.now(timezone.utc).isoformat(),
        "actualizado_en": datetime.now(timezone.utc).isoformat(),
    })
    tareas.add_task(_correr_descarga_cui, descarga_id)
    # Respuesta inmediata: el trabajo recién arranca. Quien pide sigue por polling.
    return {"descarga_id": descarga_id, "estado": "en_progreso",
            "paso": "En cola: esperando turno para consultar InfoObras."}


@app.get("/api/pivote/descargar-cui/{descarga_id}")
def descargar_cui_estado(descarga_id: str):
    """Estado de una descarga por CUI: `estado` (en_progreso/listas/error),
    `paso` (qué está ocurriendo ahora, en castellano), cuántos documentos van y
    qué secciones respondieron. `listo` es el atajo para "ya se puede bajar"."""
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
            "paso": est.get("paso"),
            "mensaje": "El ZIP se está preparando: descargando los documentos de InfoObras."})
    return FileResponse(ruta, media_type="application/zip",
                        filename=f"InfoObras_CUI_{est['cui']}.zip")


# ── Buscador de la base local del MEF ────────────────────────────────────────

@app.get("/api/pivote/mef/buscar")
def buscar_en_base_mef(q: str = "", dpto: str = "", prov: str = "", dist: str = "",
                       entidad: str = "", limite: int = 10):
    """Busca inversiones (CUI/SNIP) en la base local del MEF, sin salir a la red.

    `q` es el nombre de la obra o directamente un CUI/SNIP; `dpto`/`prov`/`dist`/
    `entidad` acotan por coincidencia parcial; `limite` corta la lista (1..50).

    Contrato de fallo, a propósito:
      · 400 si lo que se pidió no se puede buscar (texto muy corto, límite fuera
        de rango) — es un error de quien pregunta.
      · **200 con `base_mef_no_disponible: true`** si la base no está instalada
        en el equipo. No es un fallo del servicio: es que no hay dónde buscar, y
        el integrador debe distinguirlo de «no hay resultados» mirando la
        bandera, no la lista vacía. Nunca un 500 ni un traceback.
    """
    from resolucion.busqueda_mef import ConsultaInvalida, buscar

    try:
        return buscar(q, dpto=dpto, prov=prov, dist=dist, entidad=entidad,
                      limite=limite)
    except ConsultaInvalida as e:
        raise HTTPException(400, str(e)) from None


# Lectura investigativa: sin selección automática, cálculo ni descarga de PDFs.
@app.get("/api/pivote/infoobras/candidatos")
def listar_fichas_infoobras(cui: str):
    from scraping.consulta_infoobras import ConsultaIdentidadInvalida, listar_fichas
    try:
        return listar_fichas(cui)
    except ConsultaIdentidadInvalida as exc:
        raise HTTPException(400, str(exc)) from None


@app.get("/api/pivote/infoobras/ficha")
def consultar_ficha_infoobras(cui: str, obra_id: str):
    from scraping.consulta_infoobras import ConsultaIdentidadInvalida, consultar_ficha
    try:
        return consultar_ficha(cui, obra_id)
    except ConsultaIdentidadInvalida as exc:
        raise HTTPException(400, str(exc)) from None


# ── Salud de portales ────────────────────────────────────────────────────────

_SALUD_CACHE: dict = {"ts": 0.0, "data": None}
_SALUD_TTL = 60.0  # el panel sondea cada ~30s; cacheamos para no golpear los portales


@app.get("/api/pivote/salud")
def salud():
    from resolucion.base_mef import instancia as _base_mef

    estado_mef = _base_mef().estado_operativo()
    # `ok: false` también cuando la base está al día pero su última actualización
    # automática falló (`refresco_fallido`): es justo el caso que antes no se veía
    # en ningún lado — la base sigue sirviendo, pero dejó de renovarse (issue #24).
    salud_mef = {
        "portal": "base_mef",
        "ok": estado_mef["estado"] == "ok",
        "diagnostico": None if estado_mef["estado"] == "ok" else estado_mef["estado"],
        "desde": None,
        "load_id": estado_mef["load_id"],
        "edad_dias": estado_mef["edad_dias"],
        "postgres": estado_mef["postgres"],
        "umbral_dias": estado_mef["umbral_dias"],
        "ultimo_refresco": estado_mef["ultimo_refresco"],
        "mensaje": estado_mef["mensaje"],
    }
    # En modo NO-real (tests/esqueleto) no hay portales que sondear → operativo sin red.
    if os.getenv("PIVOTE_ETAPAS") != "real":
        return [
            {"portal": "sunat", "ok": True, "diagnostico": None, "desde": None},
            {"portal": "infoobras", "ok": True, "diagnostico": None, "desde": None},
            salud_mef,
        ]
    import time
    ahora = time.time()
    if _SALUD_CACHE["data"] and ahora - _SALUD_CACHE["ts"] < _SALUD_TTL:
        return _SALUD_CACHE["data"]
    from scraping.infoobras import sondear as _sondear_infoobras
    from scraping.sunat import sondear as _sondear_sunat
    desde = datetime.now(timezone.utc).isoformat()
    out = [salud_mef]
    for portal, fn in (("sunat", _sondear_sunat), ("infoobras", _sondear_infoobras)):
        try:
            ok, diag = fn()
        except Exception:  # noqa: BLE001 — /salud nunca debe romper
            ok, diag = False, "error interno"
        out.append({"portal": portal, "ok": ok, "diagnostico": diag, "desde": desde})
    _SALUD_CACHE.update(ts=ahora, data=out)
    return out
