"""
Tests de la API HTTP (FastAPI + TestClient) — el flujo completo que la demo
recorre: crear concurso → subir análisis → pipeline corre → ver job/extracción/
resumen → resolver revisión → descargar Excel final y ZIP. Sin red externa
(etapas del esqueleto: ingesta real + stubs).
"""
from __future__ import annotations

import importlib
import io
import json
import zipfile

import pytest


ESPEJO = {
    "_meta": {"analisis_id": "api-demo-001", "concurso": "CP-API/2026",
              "postor": "POSTOR API DEMO"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "Profesional Uno",
         "colegiatura": "CIP 12345", "cumple": "SÍ — 4.51 años",
         "total": {"dias": 1645, "anios": 4.51},
         "experiencias": [
             {"n": 1, "proyecto": "Obra API A", "entidad_emisora": "Entidad A",
              "ruc_emisor": "20123456789", "nombre_emisor": "Firma Uno",
              "cargo_emisor": "Gerente General", "fecha_emision": "2023-06-01",
              "tipo_documento": "Constancia", "entidad_contratante": "Entidad Pública",
              "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
              "dias": 724, "cui": "2418877", "folio": "100"},
         ]},
    ],
    "resumen_evaluacion": {"factores": [{"factor": "A", "puntaje": 55}],
                           "puntaje_total": 55},
}


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """App fresca con datos en tmp_path (aisla cada test)."""
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")  # sin red en tests
    import api.app as modulo
    importlib.reload(modulo)
    from fastapi.testclient import TestClient
    return TestClient(modulo.app)


def _subir(cliente, concurso_id: str):
    return cliente.post("/api/pivote/analizar", data={"concurso_id": concurso_id},
                        files={
                            "espejo": ("espejo.json", io.BytesIO(
                                json.dumps(ESPEJO).encode("utf-8")), "application/json"),
                            "excel": ("claude.xlsx", io.BytesIO(b"PK demo"), "application/octet-stream"),
                        })


def test_flujo_completo_de_la_demo(cliente):
    # 1 · crear concurso
    r = cliente.post("/api/pivote/concursos",
                     json={"nomenclatura": "CP-API/2026", "entidad": "Entidad Demo"})
    assert r.status_code == 201
    cid = r.json()["concurso_id"]

    # 2 · subir análisis (el pipeline corre como tarea de fondo del TestClient)
    r = _subir(cliente, cid)
    assert r.status_code == 201
    job_id = r.json()["job_id"]

    # 3 · job procesado: todas las etapas OK (esqueleto), estado completado
    r = cliente.get(f"/api/pivote/jobs/{job_id}")
    assert r.status_code == 200
    job = r.json()
    assert job["estado"] == "completado"
    assert len(job["etapas"]) == len(__import__(
        "schemas.pipeline", fromlist=["Etapa"]
    ).Etapa.orden())
    assert job["origen"] == "dropzone"
    assert "confiabilidad" in job and "hallazgos_criticos" in job

    # 4 · el concurso lista el job
    r = cliente.get(f"/api/pivote/concursos/{cid}")
    assert r.json()["jobs"][0]["job_id"] == job_id
    r = cliente.get("/api/pivote/concursos")
    assert r.json()[0]["n_jobs"] == 1

    # 5 · extracción (profesionales/experiencias para el panel)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/espejo")
    profs = r.json()["profesionales"]
    assert profs[0]["cargo"] == "JEFE DE SUPERVISIÓN"
    assert profs[0]["experiencias"][0]["cui"] == "2418877"
    assert profs[0]["experiencias"][0]["ruc_emisor"] == "20123456789"
    assert profs[0]["experiencias"][0]["nombre_emisor"] == "Firma Uno"
    assert profs[0]["experiencias"][0]["cargo_emisor"] == "Gerente General"
    assert profs[0]["experiencias"][0]["entidad_contratante"] == "Entidad Pública"
    assert profs[0]["veredicto_efectivo"] == profs[0]["cumple"]
    assert profs[0]["estado_efectivo"] == "cumple"
    assert profs[0]["total_efectivo"]["dias"] == 724

    # 6 · resumen (veredictos + factores)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/resumen")
    res = r.json()
    assert res["puntaje_total"] == 55
    assert "confiabilidad" in res and "hallazgos_criticos" in res
    assert res["veredictos"][0]["cumple_claude"].startswith("SÍ")
    assert res["veredictos"][0]["anios_brutos"] == pytest.approx(724 / 365, abs=0.01)
    assert res["veredictos"][0]["estado_efectivo"] == "cumple"
    assert res["conteo_alertas"] == {
        "requieren_atencion": 0, "advertencias": 0,
        "informativas": 0, "total": 0,
    }

    # 7 · Excel final REAL descargable (CLAUDE + Base de Datos + hoja del prof)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/excel")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[:2] == ["CLAUDE", "Base de Datos"]
    assert any(n.startswith("P1.") for n in wb.sheetnames)

    # 8 · ZIP InfoObras descargable (árbol de 4 niveles, sin docs aún)
    r = cliente.get(f"/api/pivote/jobs/{job_id}/zip")
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert any(n.endswith("SIN_DOCUMENTOS.txt") for n in zf.namelist())


def test_espejo_expone_desglose_multiobra(cliente):
    import api.app as modulo
    from schemas import pipeline

    job = pipeline.Job(job_id="j-multiobra", analisis_id="a")
    modulo.repo.guardar(job)
    modulo.repo.guardar_espejo(job.job_id, {
        "profesionales": [{"n_prof": 1, "cargo": "ARQUITECTO", "nombre": "N",
                            "experiencias": [{"n": 1, "proyecto": "DOS OBRAS"}]}],
    })
    sub_obras = [
        {"proyecto": "OBRA A", "cui": "1234567", "estado": "resuelto", "via": "CUI"},
        {"proyecto": "OBRA B", "cui": None, "estado": "revision", "via": "NOMBRE"},
    ]
    modulo.repo.guardar_enriquecimiento(job.job_id, {
        "1:1": {
            "via": "MULTI_OBRA", "multi_rubro": True, "sub_obras": sub_obras,
            "seace": {
                "estado": "seleccionado",
                "docs": {
                    "bases": {"estado": "disponible", "url": "https://seace/bases.rar"},
                    "contrato": {"estado": "disponible", "url": "https://seace/contrato.pdf"},
                },
                "candado": {"resultado": "confirmado", "motivo": "Coincide."},
            },
        },
    })

    experiencia = cliente.get(f"/api/pivote/jobs/{job.job_id}/espejo").json()[
        "profesionales"][0]["experiencias"][0]
    assert experiencia["sub_obras"] == sub_obras
    assert experiencia["multi_rubro"] is True
    assert experiencia["seace"]["docs"]["bases"]["url"] == "https://seace/bases.rar"
    assert experiencia["seace"]["candado"]["resultado"] == "confirmado"


def test_espejo_invalido_rechazado_con_errores_claros(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "X"}).json()["concurso_id"]
    roto = {"_meta": {"analisis_id": "x"}, "postor": {}, "profesionales": []}
    r = cliente.post("/api/pivote/analizar", data={"concurso_id": cid},
                     files={
                         "espejo": ("e.json", io.BytesIO(json.dumps(roto).encode()), "application/json"),
                         "excel": ("c.xlsx", io.BytesIO(b"PK"), "application/octet-stream"),
                     })
    assert r.status_code == 422
    detalle = r.json()["detail"]
    assert detalle["error"].startswith("el archivo de datos")
    assert detalle["errores"]  # lista campo a campo
    assert cliente.get(f"/api/pivote/concursos/{cid}").json()["jobs"] == []


def test_excel_sobre_limite_no_crea_job_huerfano(cliente, monkeypatch):
    import api.app as modulo

    cid = cliente.post(
        "/api/pivote/concursos", json={"nomenclatura": "XLSX"}
    ).json()["concurso_id"]
    monkeypatch.setattr(modulo, "_MAX_EXCEL", 4)

    r = cliente.post(
        "/api/pivote/analizar",
        data={"concurso_id": cid},
        files={
            "espejo": (
                "e.json", io.BytesIO(json.dumps(ESPEJO).encode()),
                "application/json",
            ),
            "excel": ("c.xlsx", io.BytesIO(b"12345"), "application/octet-stream"),
        },
    )

    assert r.status_code == 413
    assert cliente.get(f"/api/pivote/concursos/{cid}").json()["jobs"] == []


def test_zip_certificados_invalido_no_crea_job_huerfano(cliente):
    cid = cliente.post(
        "/api/pivote/concursos", json={"nomenclatura": "ZIP"}
    ).json()["concurso_id"]

    r = cliente.post(
        "/api/pivote/analizar",
        data={"concurso_id": cid},
        files={
            "espejo": (
                "e.json", io.BytesIO(json.dumps(ESPEJO).encode()),
                "application/json",
            ),
            "excel": ("c.xlsx", io.BytesIO(b"PK"), "application/octet-stream"),
            "certificados": (
                "certs.zip", io.BytesIO(b"esto no es zip"), "application/zip",
            ),
        },
    )

    assert r.status_code == 422
    assert "no es un ZIP válido" in r.json()["detail"]
    assert cliente.get(f"/api/pivote/concursos/{cid}").json()["jobs"] == []


def test_falso_pdf_en_zip_no_crea_job_huerfano(cliente):
    cid = cliente.post(
        "/api/pivote/concursos", json={"nomenclatura": "PDF"}
    ).json()["concurso_id"]
    certs = io.BytesIO()
    with zipfile.ZipFile(certs, "w") as archivo:
        archivo.writestr("carpeta/P1_E1.pdf", b"esto no es un PDF")

    r = cliente.post(
        "/api/pivote/analizar",
        data={"concurso_id": cid},
        files={
            "espejo": (
                "e.json", io.BytesIO(json.dumps(ESPEJO).encode()),
                "application/json",
            ),
            "excel": ("c.xlsx", io.BytesIO(b"PK"), "application/octet-stream"),
            "certificados": (
                "certs.zip", io.BytesIO(certs.getvalue()), "application/zip",
            ),
        },
    )

    assert r.status_code == 422
    assert "no contiene un PDF válido" in r.json()["detail"]
    assert cliente.get(f"/api/pivote/concursos/{cid}").json()["jobs"] == []


def test_zip_certificados_valido_conserva_pdf(cliente, tmp_path):
    cid = cliente.post(
        "/api/pivote/concursos", json={"nomenclatura": "PDF-OK"}
    ).json()["concurso_id"]
    certs = io.BytesIO()
    with zipfile.ZipFile(certs, "w") as archivo:
        archivo.writestr("recortes/P1_E1.pdf", b"%PDF-1.4\ncertificado")

    r = cliente.post(
        "/api/pivote/analizar",
        data={"concurso_id": cid},
        files={
            "espejo": (
                "e.json", io.BytesIO(json.dumps(ESPEJO).encode()),
                "application/json",
            ),
            "excel": ("c.xlsx", io.BytesIO(b"PK"), "application/octet-stream"),
            "certificados": (
                "certs.zip", io.BytesIO(certs.getvalue()), "application/zip",
            ),
        },
    )

    assert r.status_code == 201
    guardado = tmp_path / r.json()["job_id"] / "certs" / "P1_E1.pdf"
    assert guardado.read_bytes().startswith(b"%PDF-")


def test_decision_de_alerta_persiste(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "Y"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    # sin alertas en el esqueleto: decidir una inexistente igual persiste el registro
    r = cliente.post(f"/api/pivote/jobs/{job_id}/alertas",
                     json={"alerta_id": "al-0", "relevante": False, "razon": "verificado a mano"})
    assert r.status_code == 200


def test_revision_inexistente_404(cliente):
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "Z"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    r = cliente.post(f"/api/pivote/jobs/{job_id}/revision",
                     json={"n_prof": 9, "n_exp": 9, "cui": "123"})
    assert r.status_code == 404


def test_revision_responde_202_y_deja_estado_consultable(cliente, monkeypatch):
    """#42: el request no ejecuta el reproceso pesado antes de responder."""
    from api import app as modulo
    from schemas import pipeline

    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "REV-ASYNC"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    job = modulo.repo.cargar(job_id)
    job.items_revision.append(pipeline.ItemRevision(
        n_prof=1, n_exp=1, etapa=pipeline.Etapa.RESOLUCION_CUI,
        motivo="elegir CUI", candidatos=[]))
    modulo.repo.guardar(job)

    def resolver(job_id_, n_prof, n_exp, body):
        actualizado = modulo.repo.cargar(job_id_)
        actualizado.items_revision[0].resuelto = True
        modulo.repo.guardar(actualizado)
        return actualizado

    monkeypatch.setattr(modulo.motor, "resolver_revision", resolver)
    monkeypatch.setattr(modulo, "_asegurar_descargas", lambda *_: None)
    r = cliente.post(
        f"/api/pivote/jobs/{job_id}/revision",
        json={"n_prof": 1, "n_exp": 1, "cui": "2418877"})
    assert r.status_code == 202
    assert r.json()["revision_estado"] == "en_curso"
    final = cliente.get(f"/api/pivote/jobs/{job_id}").json()
    assert final["revision_estado"] == "completada"
    assert final["items_revision"][0]["resuelto"] is True


def test_revision_background_persiste_error_consultable(cliente, monkeypatch):
    """#42: una excepción ya no corta la conexión ni deja el job en `en_curso`."""
    from api import app as modulo
    from schemas import pipeline

    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "REV-ERROR"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    job = modulo.repo.cargar(job_id)
    job.items_revision.append(pipeline.ItemRevision(
        n_prof=1, n_exp=1, etapa=pipeline.Etapa.RESOLUCION_CUI,
        motivo="elegir CUI", candidatos=[]))
    modulo.repo.guardar(job)

    def fallar(*_args, **_kwargs):
        raise RuntimeError("fallo controlado de revisión")

    monkeypatch.setattr(modulo.motor, "resolver_revision", fallar)
    r = cliente.post(
        f"/api/pivote/jobs/{job_id}/revision",
        json={"n_prof": 1, "n_exp": 1, "cui": "2418877"})
    assert r.status_code == 202
    final = cliente.get(f"/api/pivote/jobs/{job_id}").json()
    assert final["revision_estado"] == "error"
    assert final["revision_error"] == "fallo controlado de revisión"
    assert final["items_revision"][0]["resuelto"] is False


def test_revision_no_purga_una_descarga_documental_previa(cliente, monkeypatch):
    """Resolver el análisis no autoriza redescargar documentos ya intentados."""
    from api import app as modulo
    from schemas import pipeline

    cid = cliente.post("/api/pivote/concursos",
                       json={"nomenclatura": "REV-CACHE"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    job = modulo.repo.cargar(job_id)
    job.items_revision.append(pipeline.ItemRevision(
        n_prof=1, n_exp=1, etapa=pipeline.Etapa.RESOLUCION_CUI,
        motivo="elegir CUI", candidatos=[]))
    modulo.repo.guardar(job)
    modulo.repo.guardar_enriquecimiento(job_id, {"1:1": {"obra": {"obra_id": 72056}}})

    entrada = modulo._dir_job(job_id) / "cache_obras" / "72056"
    (entrada / "Informes de control").mkdir(parents=True)
    (entrada / "Informes de control" / "resto.pdf").write_bytes(b"%PDF")
    (entrada / "Valorizaciones").mkdir()
    (entrada / "Valorizaciones" / "val.pdf").write_bytes(b"%PDF")
    (entrada / ".estado.json").write_text(
        json.dumps({"secciones": {"InfoObras": {"esperados": 1, "descargados": 1},
                                  "Informes de control": {"error": True}}}),
        encoding="utf-8")
    (entrada / ".completa").write_text("ok\n", encoding="utf-8")   # marca heredada

    def resolver(job_id_, n_prof, n_exp, body):
        actualizado = modulo.repo.cargar(job_id_)
        actualizado.items_revision[0].resuelto = True
        modulo.repo.guardar(actualizado)
        return actualizado

    monkeypatch.setattr(modulo.motor, "resolver_revision", resolver)
    monkeypatch.setattr(modulo, "_asegurar_descargas", lambda *_: None)
    assert cliente.post(f"/api/pivote/jobs/{job_id}/revision",
                        json={"n_prof": 1, "n_exp": 1, "cui": "2418877"}
                        ).status_code == 202

    assert (entrada / ".completa").exists()
    assert not (entrada / ".parcial").exists()
    assert (entrada / "Informes de control/resto.pdf").is_file()
    assert (entrada / "Valorizaciones" / "val.pdf").is_file(), (
        "lo sano se reutiliza: la revisión no re-descarga la obra entera")


# ── Descarga por un solo CUI (endpoint suelto) ───────────────────────────────

def test_descargar_cui_valida_entrada(cliente):
    assert cliente.post("/api/pivote/descargar-cui", json={}).status_code == 400
    assert cliente.post("/api/pivote/descargar-cui", json={"cui": "abc"}).status_code == 400


def test_descargar_cui_estado_y_zip_inexistentes_404(cliente):
    assert cliente.get("/api/pivote/descargar-cui/nope").status_code == 404
    assert cliente.get("/api/pivote/descargar-cui/nope/zip").status_code == 404


def test_descargar_cui_flujo_feliz(cliente, monkeypatch):
    # el background task del TestClient corre sincrónico → al volver el POST ya terminó.
    # Monkeypatcheamos la descarga real (red) por una que deja un archivo en la carpeta;
    # el _zip_carpeta REAL lo empaqueta.
    import api.app as modulo

    def fake_descargar_cui(cui, carpeta, *, fecha_inicio=None, fecha_fin=None, **k):
        d = (carpeta / "Valorizaciones" / "2020-09")
        d.mkdir(parents=True, exist_ok=True)
        (d / "doc.pdf").write_bytes(b"%PDF-1.4 demo")
        return {"cui": cui, "obra_id": 111, "nombre": "OBRA DEMO",
                "descargados": 1, "fallidos": 0, "error": None}

    monkeypatch.setattr(modulo, "descargar_cui", fake_descargar_cui)

    r = cliente.post("/api/pivote/descargar-cui",
                     json={"cui": "2418877", "fecha_inicio": "2020-01-01"})
    assert r.status_code == 201
    did = r.json()["descarga_id"]

    r = cliente.get(f"/api/pivote/descargar-cui/{did}")
    assert r.status_code == 200
    body = r.json()
    assert body["estado"] == "listas" and body["listo"] is True
    assert body["obra_id"] == 111 and body["descargados"] == 1

    r = cliente.get(f"/api/pivote/descargar-cui/{did}/zip")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    nombres = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "indice.txt" in nombres and any(n.endswith("doc.pdf") for n in nombres)


def test_descargar_cui_no_resuelto_marca_error_y_zip_409(cliente, monkeypatch):
    import api.app as modulo
    monkeypatch.setattr(modulo, "descargar_cui",
                        lambda cui, carpeta, **k: {"cui": cui, "obra_id": None,
                                                   "nombre": None, "descargados": 0,
                                                   "fallidos": 0, "error": "no resolvió"})
    did = cliente.post("/api/pivote/descargar-cui",
                       json={"cui": "9999999"}).json()["descarga_id"]
    est = cliente.get(f"/api/pivote/descargar-cui/{did}").json()
    assert est["estado"] == "error"
    # el porqué se dice en castellano, no se deja adivinar por el estado
    assert "no corresponde a ninguna obra" in est["paso"]
    assert cliente.get(f"/api/pivote/descargar-cui/{did}/zip").status_code == 409


def test_descargar_cui_responde_al_instante_y_deja_seguimiento(cliente, monkeypatch):
    """El POST NO espera a la descarga: contesta con el número de seguimiento y
    el trabajo sigue atrás. (La lección del ECONNRESET con obras pesadas.)"""
    import api.app as modulo
    lanzadas = []
    # se sustituye el arranque de la tarea de fondo: el POST no debe depender de ella
    monkeypatch.setattr(modulo.BackgroundTasks, "add_task",
                        lambda self, fn, *a, **k: lanzadas.append((fn.__name__, a)))

    r = cliente.post("/api/pivote/descargar-cui", json={"cui": "2418877"})
    assert r.status_code == 201
    b = r.json()
    assert b["estado"] == "en_progreso" and b["paso"].startswith("En cola")
    assert lanzadas == [("_correr_descarga_cui", (b["descarga_id"],))]

    # el estado ya es consultable aunque el trabajo no haya empezado
    est = cliente.get(f'/api/pivote/descargar-cui/{b["descarga_id"]}').json()
    assert est["estado"] == "en_progreso" and est["listo"] is False
    assert est["creado_en"] and est["actualizado_en"]
    # y el ZIP todavía no: 202 con el motivo, nunca un archivo a medias
    z = cliente.get(f'/api/pivote/descargar-cui/{b["descarga_id"]}/zip')
    assert z.status_code == 202 and z.json()["paso"].startswith("En cola")


def test_descargar_cui_persiste_el_avance_tramo_a_tramo(cliente, monkeypatch):
    """Cada tramo se escribe en disco apenas empieza: quien pollea ve avanzar
    algo aunque una sección tarde minutos, y el estado sobrevive a un reinicio."""
    import api.app as modulo
    vistos = []

    def fake_descargar_cui(cui, carpeta, *, progreso=None, **k):
        for frase in ("Buscando la obra en InfoObras a partir del CUI.",
                      "Descargando las valorizaciones y los documentos de la obra."):
            progreso(frase)
            # se lee del DISCO, no de la memoria del proceso
            vistos.append(json.loads(
                (carpeta.parent / f"{carpeta.name.split('.')[0]}.cui.json")
                .read_text(encoding="utf-8"))["paso"])
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "doc.pdf").write_bytes(b"%PDF-1.4 demo")
        return {"cui": cui, "obra_id": 7, "nombre": "OBRA", "descargados": 1,
                "fallidos": 0, "error": None}

    monkeypatch.setattr(modulo, "descargar_cui", fake_descargar_cui)
    did = cliente.post("/api/pivote/descargar-cui",
                       json={"cui": "2418877"}).json()["descarga_id"]

    assert vistos == ["Buscando la obra en InfoObras a partir del CUI.",
                      "Descargando las valorizaciones y los documentos de la obra."]
    est = cliente.get(f"/api/pivote/descargar-cui/{did}").json()
    assert est["estado"] == "listas" and est["paso"] == "Listo: 1 documento(s) en el ZIP."


def test_descargar_cui_progreso_roto_no_tumba_la_descarga(cliente, monkeypatch, tmp_path):
    """Un contador que revienta no puede costar el corpus descargado."""
    from entregables.zip_infoobras import descargar_cui as real

    def fetch(cui, *a):
        return type("O", (), {"obra_id": 9, "nombre": "OBRA", "aprobacion_expediente": None})()

    import entregables.zip_infoobras as zi
    monkeypatch.setattr(zi, "descargar_documentos_obra_por_hito",
                        lambda *a, **k: {"descargados": 0, "fallidos": 0, "inventario": {}})
    monkeypatch.setattr(zi, "descargar_informes_control", lambda *a, **k: {})
    monkeypatch.setattr(zi, "descargar_datos_cierre", lambda *a, **k: {})

    def progreso_roto(_):
        raise RuntimeError("el que informa se cayó")

    r = real("2418877", tmp_path / "docs", fetch=fetch, progreso=progreso_roto)
    assert r["obra_id"] == 9 and r["error"] is None


# ── Buscador de la base local del MEF ────────────────────────────────────────

@pytest.fixture()
def con_base_mini(dir_mef_mini, monkeypatch):
    """El endpoint busca contra los fixtures mini, no contra la base real de la
    máquina (medio millón de filas y resultados dependientes del equipo)."""
    from resolucion import base_mef, busqueda_mef
    monkeypatch.setattr(busqueda_mef, "_base_por_defecto",
                        lambda: base_mef.BaseMef(dir_mef_mini))


def test_mef_buscar_por_nombre(cliente, con_base_mini):
    r = cliente.get("/api/pivote/mef/buscar", params={"q": "hospital regional"})
    assert r.status_code == 200
    b = r.json()
    assert b["base_mef_no_disponible"] is False
    assert {x["cui"] for x in b["resultados"]} == {"2200145", "2366120"}
    assert b["resultados"][0]["ubicacion"] and b["resultados"][0]["entidad"]


def test_mef_buscar_con_filtros_y_limite(cliente, con_base_mini):
    r = cliente.get("/api/pivote/mef/buscar",
                    params={"q": "hospital regional", "dpto": "huanuco", "limite": 1})
    assert r.status_code == 200
    b = r.json()
    assert b["total"] == 1 and b["resultados"][0]["cui"] == "2366120"


def test_mef_buscar_por_cui(cliente, con_base_mini):
    b = cliente.get("/api/pivote/mef/buscar", params={"q": "2200145"}).json()
    assert b["coincidencia"] == "codigo" and b["resultados"][0]["cui"] == "2200145"


def test_mef_buscar_valida_entrada(cliente, con_base_mini):
    assert cliente.get("/api/pivote/mef/buscar", params={"q": "a"}).status_code == 400
    assert cliente.get("/api/pivote/mef/buscar").status_code == 400
    assert cliente.get("/api/pivote/mef/buscar",
                       params={"q": "hospital", "limite": 999}).status_code == 400


def test_mef_buscar_sin_base_responde_200_con_bandera(cliente, tmp_path, monkeypatch):
    """La base ausente NO es un 500 ni un traceback: 200 con bandera y aviso,
    para que el integrador distinga «no hay base» de «no hay resultados»."""
    from resolucion import base_mef, busqueda_mef
    vacia = tmp_path / "sin_mef"
    vacia.mkdir()
    monkeypatch.setattr(busqueda_mef, "_base_por_defecto",
                        lambda: base_mef.BaseMef(vacia))
    r = cliente.get("/api/pivote/mef/buscar", params={"q": "hospital regional"})
    assert r.status_code == 200
    b = r.json()
    assert b["base_mef_no_disponible"] is True
    assert b["resultados"] == [] and b["aviso"]


# ── Progreso del análisis (barra del panel) ──────────────────────────────────

def test_progreso_endpoint_job_terminado(cliente):
    """Al terminar el pipeline, /progreso muestra 100% y todas las etapas OK."""
    cid = cliente.post("/api/pivote/concursos",
                       json={"nomenclatura": "CP-PROG/2026"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]

    r = cliente.get(f"/api/pivote/jobs/{job_id}/progreso")
    assert r.status_code == 200
    p = r.json()
    assert p["job_id"] == job_id
    assert p["estado"] == "completado"
    assert p["pct"] == 100.0
    assert [e["etapa"] for e in p["etapas"]] == [x.value for x in __import__(
        "schemas.pipeline", fromlist=["Etapa"]).Etapa.orden()]
    assert all(e["estado"] in ("ok", "ok_con_revision", "error_parcial")
               for e in p["etapas"])
    # descargas embebidas + obra en curso (None: ya no corre nada)
    assert "descargas" in p and "obra_actual" in p["descargas"]
    assert p["eta"] is None
    assert p["pendientes_humano"] == 0


def test_progreso_404_si_no_existe(cliente):
    assert cliente.get("/api/pivote/jobs/nope/progreso").status_code == 404


def test_avance_descargas_excluye_privadas_y_cuenta_procesadas_sin_documentos(cliente):
    import api.app as modulo
    from schemas import pipeline

    job = pipeline.Job(job_id="j-desc-real", analisis_id="a")
    job.items_revision.append(pipeline.ItemRevision(
        n_prof=1, n_exp=4, etapa=pipeline.Etapa.RESOLUCION_CUI, motivo="confirmar",
    ))
    modulo.repo.guardar(job)
    modulo.repo.guardar_espejo(job.job_id, {
        "profesionales": [{"n_prof": 1, "experiencias": [
            {"n": 1}, {"n": 2}, {"n": 3}, {"n": 4},
        ]}],
    })
    modulo.repo.guardar_enriquecimiento(job.job_id, {
        "1:1": {"obra": {"obra_id": 11},
                "descargas_reales": {"completada": True, "archivos": 2}},
        "1:2": {"via": "PRIVADA"},
        "1:3": {"obra": {"obra_id": 13},
                "descargas_reales": {"completada": True, "archivos": 0}},
        "1:4": {"obra": {"obra_id": 14}},
    })

    avance = modulo._avance_descargas_dict(job)
    assert avance == {
        "estado": "pendiente", "listo": False,
        "total": 2, "descargadas": 2, "faltan": 0,
        "en_revision": 1, "obra_actual": None,
    }


def test_avance_descargas_job_antiguo_usa_marcas_de_fuente(cliente):
    import api.app as modulo
    from schemas import pipeline

    job = pipeline.Job(job_id="j-desc-legado", analisis_id="a")
    modulo.repo.guardar(job)
    modulo.repo.guardar_espejo(job.job_id, {
        "profesionales": [{"n_prof": 1, "experiencias": [{"n": 1}, {"n": 2}]}],
    })
    modulo.repo.guardar_enriquecimiento(job.job_id, {
        "1:1": {"obra": {"obra_id": 11}},
        "1:2": {"seace": {"estado": "seleccionado"}},
    })
    base = modulo._dir_job(job.job_id) / "descargas"
    base.mkdir(parents=True)
    (base / "P1_E1.ok").write_text("ok", encoding="utf-8")
    (base / "P1_E2.seace.ok").write_text("ok", encoding="utf-8")

    avance = modulo._avance_descargas_dict(job)
    assert avance["descargadas"] == 2
    assert avance["faltan"] == 0


def test_armar_progreso_fusiona_vivo_y_checkpoint(cliente):
    """Etapa ya OK (checkpoint) vs etapa en curso (RegistroProgreso) vs pendiente."""
    import api.app as modulo
    from schemas import pipeline

    job = pipeline.Job(job_id="jx", analisis_id="a")
    job.etapas.append(pipeline.ResultadoEtapa(
        etapa=pipeline.Etapa.INGESTA, estado=pipeline.EstadoEtapa.OK))
    modulo.REGISTRO.reportar("jx", "infoobras", 4, 9, "Verificando la obra 4 de 9")
    try:
        prog = modulo.armar_progreso(job)
        et = {e["etapa"]: e for e in prog["etapas"]}
        assert et["ingesta"]["estado"] == "ok"
        assert et["ingesta"]["texto"] == "Recepción de la propuesta"      # etiqueta estable
        assert et["infoobras"]["estado"] == "en_curso"
        assert et["infoobras"]["item_actual"] == 4
        assert et["infoobras"]["items_total"] == 9
        assert et["infoobras"]["texto"] == "Verificando la obra 4 de 9"   # texto fino en vivo
        assert et["sunat"]["estado"] == "pendiente"
        total = len(__import__(
            "schemas.pipeline", fromlist=["Etapa"]
        ).Etapa.orden())
        assert prog["pct"] == round(100 / total, 1)
    finally:
        modulo.REGISTRO.limpiar("jx")


# ── Búsqueda global de profesionales ─────────────────────────────────────────

def test_buscar_profesionales_por_nombre_sin_tildes(cliente):
    cid = cliente.post("/api/pivote/concursos",
                       json={"nomenclatura": "CP-BUSCA/2026"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]

    # "profesional uno" matchea "Profesional Uno" (case-insensitive); "unó" prueba tildes
    for q in ("profesional uno", "UNÓ"):
        r = cliente.get("/api/pivote/profesionales", params={"q": q})
        assert r.status_code == 200
        hits = r.json()
        assert any(h["job_id"] == job_id for h in hits), f"sin match para {q!r}"
    h = next(x for x in cliente.get("/api/pivote/profesionales",
                                    params={"q": "profesional uno"}).json()
             if x["job_id"] == job_id)
    assert h["nombre"] == "Profesional Uno"
    assert h["cargo"] == "JEFE DE SUPERVISIÓN"
    assert h["n_prof"] == 1 and h["n_experiencias"] == 1
    assert h["concurso_id"] == cid and h["concurso"] == "CP-BUSCA/2026"
    assert h["postor"] == "POSTOR API DEMO"


def test_buscar_profesionales_por_colegiatura_y_cargo(cliente):
    cid = cliente.post("/api/pivote/concursos",
                       json={"nomenclatura": "CP-BUSCA2/2026"}).json()["concurso_id"]
    job_id = _subir(cliente, cid).json()["job_id"]
    assert any(h["job_id"] == job_id for h in cliente.get(
        "/api/pivote/profesionales", params={"q": "CIP 12345"}).json())
    assert any(h["job_id"] == job_id for h in cliente.get(
        "/api/pivote/profesionales", params={"q": "jefe de supervision"}).json())


def test_buscar_profesionales_query_corta_o_sin_match(cliente):
    assert cliente.get("/api/pivote/profesionales", params={"q": "x"}).json() == []
    assert cliente.get("/api/pivote/profesionales", params={"q": ""}).json() == []
    assert cliente.get("/api/pivote/profesionales",
                       params={"q": "zzz-nadie-zzz"}).json() == []


# ── RENIPRESS integrable ────────────────────────────────────────────────────

def test_renipress_expone_resultado_sano(cliente, monkeypatch):
    import api.app as modulo
    from scraping.renipress import EstablecimientoRENIPRESS, ResultadoRENIPRESS

    resultado = ResultadoRENIPRESS(
        estado="encontrado",
        termino="00008215",
        tipo_consulta="codigo",
        solo_activos=True,
        establecimientos=[
            EstablecimientoRENIPRESS(
                codigo_unico="00008215",
                nombre_razon_social="MEDICENTRO SAN ISIDRO",
                coincidencia_exacta=True,
            )
        ],
        total=1,
    )
    monkeypatch.setattr(modulo, "buscar_renipress", lambda *a, **k: resultado)

    r = cliente.get("/api/pivote/renipress", params={"q": "00008215"})

    assert r.status_code == 200
    assert r.json()["estado"] == "encontrado"
    assert r.json()["ambiguo"] is False
    assert r.json()["establecimientos"][0]["codigo_unico"] == "00008215"


def test_renipress_portal_caido_es_503(cliente, monkeypatch):
    import api.app as modulo
    from scraping.renipress import ResultadoRENIPRESS

    resultado = ResultadoRENIPRESS(
        estado="portal_no_disponible",
        termino="CLINICA",
        tipo_consulta="texto",
        solo_activos=True,
        detalle_error="timeout",
    )
    monkeypatch.setattr(modulo, "buscar_renipress", lambda *a, **k: resultado)

    r = cliente.get("/api/pivote/renipress", params={"q": "CLINICA"})

    assert r.status_code == 503
    assert r.json()["estado"] == "portal_no_disponible"


def test_renipress_valida_parametros_sin_tocar_la_red(cliente, monkeypatch):
    import api.app as modulo

    def no_llamar(*args, **kwargs):
        raise AssertionError("no debía consultar RENIPRESS")

    monkeypatch.setattr(modulo, "buscar_renipress", no_llamar)

    assert cliente.get("/api/pivote/renipress", params={"q": "x"}).status_code == 400
    assert cliente.get(
        "/api/pivote/renipress", params={"q": "CLINICA", "limite": 501}
    ).status_code == 400


# ── Reanudación al arrancar (vía repo, no glob de archivos) ──────────────────

def test_startup_reanuda_job_en_proceso(tmp_path, monkeypatch):
    """Un job que quedó `en_proceso` (crash) se retoma al arrancar la app. La
    reanudación lee del REPO (no glob *.job.json) → funciona igual con Postgres."""
    import importlib
    import time

    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    importlib.reload(modulo)

    # pre-sembrar un job interrumpido + su espejo, como los dejaría un corte
    from schemas import pipeline as pl
    job = modulo.motor.crear_job(ESPEJO)
    job.estado = pl.JobEstado.EN_PROCESO
    modulo.repo.guardar(job)

    from fastapi.testclient import TestClient
    with TestClient(modulo.app) as c:          # `with` dispara el evento startup
        for _ in range(50):                     # el hilo de reanudación es async
            estado = c.get(f"/api/pivote/jobs/{job.job_id}").json()["estado"]
            if estado in ("completado", "requiere_revision"):
                break
            time.sleep(0.1)
        assert estado == "completado"
