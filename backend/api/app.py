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
import os
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
from fastapi.responses import FileResponse
from pydantic import ValidationError

from entregables import construir_zip_infoobras, generar_excel_final
from orquestador import Motor, RepositorioArchivos, etapas_esqueleto, etapas_reales
from schemas import pipeline
from schemas.espejo import JsonEspejo

DATA_DIR = Path(os.getenv("PIVOTE_DATA_DIR", "datos_pivote"))

app = FastAPI(title="InfoObras Pivote API", version="0.2.0")
repo = RepositorioArchivos(DATA_DIR)
# PIVOTE_ETAPAS=esqueleto -> stubs (tests/desarrollo sin red); default: reales.
if os.getenv("PIVOTE_ETAPAS", "real") == "esqueleto":
    motor = Motor(etapas_esqueleto(), repo)
else:
    motor = Motor(etapas_reales(DATA_DIR), repo)

ETAPA_FUENTE = {
    pipeline.Etapa.SUNAT: "SUNAT",
    pipeline.Etapa.INFOOBRAS: "InfoObras",
    pipeline.Etapa.VALIDACION: "revisión de consistencia",
    pipeline.Etapa.REGLAS: "cálculo de días efectivos",
}


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


def _decisiones_path(job_id: str) -> Path:
    return DATA_DIR / f"{job_id}.decisiones.json"


def _decisiones(job_id: str) -> dict:
    p = _decisiones_path(job_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


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
        entidad=body.get("entidad"),
        fecha_presentacion=body.get("fecha_presentacion"),
        creado_en=datetime.now(timezone.utc),
    )
    repo.guardar_concurso(c)
    return json.loads(c.model_dump_json())


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

@app.post("/api/pivote/analizar", status_code=201)
async def analizar(
    tareas: BackgroundTasks,
    concurso_id: str = Form(...),
    espejo: UploadFile = File(...),
    excel: UploadFile = File(...),
    origen: str = Form("dropzone"),
):
    if repo.cargar_concurso(concurso_id) is None:
        raise HTTPException(404, "concurso no existe")
    try:
        datos = json.loads((await espejo.read()).decode("utf-8"))
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
    (DATA_DIR / f"{job.job_id}.claude.xlsx").write_bytes(await excel.read())

    tareas.add_task(motor.correr, job.job_id)
    return {"job_id": job.job_id}


@app.get("/api/pivote/jobs/{job_id}")
def ver_job(job_id: str):
    return json.loads(_job_o_404(job_id).model_dump_json())


@app.post("/api/pivote/jobs/{job_id}/revision")
def resolver_revision(job_id: str, body: dict):
    n_prof, n_exp = body.get("n_prof"), body.get("n_exp")
    if not isinstance(n_prof, int) or not isinstance(n_exp, int):
        raise HTTPException(400, "n_prof y n_exp son obligatorios")
    if not body.get("cui") and body.get("accion") != "no_existe":
        raise HTTPException(400, "se requiere cui o accion='no_existe'")
    try:
        job = motor.resolver_revision(job_id, n_prof, n_exp, body)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return json.loads(job.model_dump_json())


# ── Vistas derivadas (extracción + resumen) ──────────────────────────────────

@app.get("/api/pivote/jobs/{job_id}/espejo")
def extraccion(job_id: str):
    _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    profesionales = []
    for p in espejo.get("profesionales", []):
        profesionales.append({
            "n_prof": p.get("n_prof"),
            "cargo": p.get("cargo"),
            "nombre": p.get("nombre"),
            "colegiatura": p.get("colegiatura"),
            "cumple": p.get("cumple"),
            "total": p.get("total") or {},
            "experiencias": [
                {k: e.get(k) for k in (
                    "n", "proyecto", "entidad_emisora", "cargo_ocupado",
                    "fecha_inicial", "fecha_final", "dias", "cui",
                    "incluye_covid", "traslape", "folio")}
                for e in p.get("experiencias", [])
            ],
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
            "nombre": p.get("nombre"),
            "cumple_claude": p.get("cumple") or "(sin veredicto en el espejo)",
            "anios_brutos": total.get("anios") or 0,
            "cumple_backend": d.get("cumple_backend"),
            "anios_efectivos": d.get("anios_efectivos"),
            "motivo_backend": motivo,
            "fuente": "InfoObras" if d.get("dias_paralizados") else ("recalculo" if d else None),
        })

    alertas = []
    todas = list(job.observaciones) + [o for e in job.etapas for o in e.observaciones]
    for i, o in enumerate(todas):
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
        {"factor": f.get("factor"), "puntaje": f.get("puntaje"), "detalle": f.get("detalle")}
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
    _decisiones_path(job_id).write_text(
        json.dumps(decisiones, ensure_ascii=False, indent=1), encoding="utf-8")
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
        generar_excel_final(espejo, ruta)
        job.excel_final = f"/api/pivote/jobs/{job_id}/excel"
        repo.guardar(job)
    return FileResponse(
        ruta,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"Formato_Evaluacion_{job.analisis_id}.xlsx",
    )


@app.get("/api/pivote/jobs/{job_id}/zip")
def descargar_zip(job_id: str):
    job = _job_o_404(job_id)
    espejo = _espejo_o_404(job_id)
    ruta = DATA_DIR / f"{job_id}.infoobras.zip"
    if not ruta.exists():
        descargas_dir = DATA_DIR / f"{job_id}.descargas"
        descargas: dict[tuple[int, int], Path] = {}
        if descargas_dir.is_dir():
            for sub in descargas_dir.iterdir():  # carpetas "P{n}_E{m}"
                try:
                    np_, ne = sub.name.removeprefix("P").split("_E")
                    descargas[(int(np_), int(ne))] = sub
                except ValueError:
                    continue
        construir_zip_infoobras(espejo, descargas, ruta)
        job.zip_infoobras = f"/api/pivote/jobs/{job_id}/zip"
        repo.guardar(job)
    return FileResponse(ruta, media_type="application/zip",
                        filename=f"InfoObras_{job.analisis_id}.zip")


# ── Salud de portales ────────────────────────────────────────────────────────

@app.get("/api/pivote/salud")
def salud():
    # La etapa real de scraping alimentará el diagnóstico (captcha_real /
    # estructura_desconocida); por ahora reporta operativo.
    return [
        {"portal": "sunat", "ok": True, "diagnostico": None, "desde": None},
        {"portal": "infoobras", "ok": True, "diagnostico": None, "desde": None},
    ]
