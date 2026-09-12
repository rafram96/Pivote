"""Aplicación y descargas reales del módulo, fuentes falsas, archivos temporales."""
from copy import deepcopy
import json
import zipfile

import pytest

from entregables.investigacion_identidad import preparar_contexto
from entregables.zip_infoobras import construir_zip_infoobras
from orquestador.aplicar_identidad import proyectar_asociaciones, publicar_asociaciones
from orquestador.etapas_reales import descargar_documentos_job
from orquestador.repositorio import RepositorioMemoria

JID = "abcdef123456"


def insumos(tipo="obras"):
    e = {"_meta": {"tipo_evaluacion": tipo}, "profesionales": [{"n_prof": 1,
         "experiencias": [{"n": 1, "proyecto": "Hospital Uno", "cui": None}]}]}
    enr = {"1:1": {"cui": "1000001", "estado": "resuelto", "via": "RUC",
                    "obra": {"obra_id": 10}, "dias_efectivos": 999,
                    "obra_ficha": {"obra_id": 10}, "camino": "obra",
                    "seace": {"estado": "seleccionado", "docs": {"contrato": {
                        "url": "https://oficial.example/anterior.pdf"}}}}}
    p = preparar_contexto(JID, e, enr, tipo)
    r = {"version": 1, "job_id": JID, "huella_contexto": p["huella_contexto"],
         "caso_id": "1:1", "estado": "asociacion_propuesta",
         "seleccion_propuesta": {"candidato_id": "elegido"},
         "candidatos": [{"id": "elegido", "cui": "2000002", "obra_id": 20,
             "intervencion": "Hospital Uno", "procedimiento": {
                 "ocid": "proceso-ejecucion", "nomenclatura": None,
                 "contrato_numero": "contrato-2", "rol": "ejecucion"},
             "evidencias": ["cui", "obra_id", "contrato", "intervencion"]}],
         "evidencias": [{"id": campo, "campo": campo, "tipo_fuente": "oficial",
              "acceso": "leido", "url": "https://oficial.example/fuente", "cita": "Cita literal"}
              for campo in ("cui", "obra_id", "contrato", "intervencion")]}
    return e, enr, r


def ficha(cui, oid):
    return {"estado": "parcial", "ficha": {"cui": cui, "obra_id": oid, "nombre": "Hospital Uno"},
            "fuentes": [{"estado": "disponible"}]}


def procesos(cui):
    return [{"ocid": "proceso-supervision", "tender": {"title": "Supervisión Hospital Uno"}},
            {"ocid": "proceso-ejecucion", "tender": {"title": "Ejecución Hospital Uno",
                 "mainProcurementCategory": "works", "documents": [{
                     "title": "Bases integradas", "documentType": "biddingDocuments",
                     "url": "https://oficial.example/bases.pdf"}]},
             "contracts": [{"id": "contrato-2", "documents": [{
                 "documentType": "contractSigned", "url": "https://oficial.example/nuevo.pdf"}]}]}]


def proyectar(e, enr, r, **kwargs):
    return proyectar_asociaciones(JID, e, enr, e["_meta"]["tipo_evaluacion"], [r],
                                  leer_ficha=kwargs.get("leer_ficha", ficha),
                                  leer_procesos=kwargs.get("leer_procesos", procesos))


@pytest.mark.parametrize("tipo", ["obras", "expedientes"])
def test_identidad_exacta_sin_tocar_declarado_ni_heredar_calculos(tipo):
    e, enr, r = insumos(tipo)
    antes = deepcopy((e, enr))
    nuevo, casos = proyectar(e, enr, r)
    assert (e, enr) == antes
    assert nuevo["1:1"]["obra"]["obra_id"] == 20
    assert nuevo["1:1"]["seace"]["docs"]["contrato"]["url"].endswith("nuevo.pdf")
    assert "dias_efectivos" not in nuevo["1:1"]
    assert "obra_ficha" not in nuevo["1:1"]
    assert nuevo["1:1"]["asociacion_investigada"]["anterior"] == enr["1:1"]
    assert casos[0]["caso_id"] == "1:1"
    with pytest.raises(ValueError, match="Contexto"):
        proyectar(e, nuevo, r)


@pytest.mark.parametrize("cambio", ["huella", "ambiguo", "sin_evidencia", "rol", "contrato", "proceso", "dictamen"])
def test_rechaza_sin_promover_o_descargar(cambio):
    e, enr, r = insumos()
    if cambio == "huella": r["huella_contexto"] = "0" * 64
    if cambio == "ambiguo": r["estado"] = "ambiguo"
    if cambio == "sin_evidencia": r["evidencias"][0]["acceso"] = "no_leido"
    if cambio == "rol": r["candidatos"][0]["procedimiento"]["rol"] = "supervision"
    if cambio == "contrato": r["candidatos"][0]["procedimiento"]["contrato_numero"] = "otro"
    if cambio == "proceso": r["candidatos"][0]["procedimiento"]["ocid"] = "inexistente"
    if cambio == "dictamen": r["cumple"] = True
    antes = deepcopy(enr)
    with pytest.raises(ValueError): proyectar(e, enr, r)
    assert enr == antes


def test_ficha_ajena_fuente_caida_y_proceso_duplicado_no_se_aplican():
    e, enr, r = insumos()
    for lector in [lambda *a: {}, lambda *a: ficha("9999999", 20), lambda *a: ficha("2000002", 21)]:
        with pytest.raises(ValueError, match="ficha"):
            proyectar(e, enr, r, leer_ficha=lector)
    for lector in [lambda *a: None, lambda c: procesos(c) + procesos(c)]:
        with pytest.raises(ValueError): proyectar(e, enr, r, leer_procesos=lector)


@pytest.mark.parametrize("fallar", [False, True])
def test_cambio_retira_documentos_antiguos_y_descarga_solo_identidad_nueva(tmp_path, fallar):
    e, enr, r = insumos()
    repo = RepositorioMemoria(); repo.guardar_enriquecimiento(JID, enr)
    raiz = tmp_path / JID; destino = raiz / "descargas/P1_E1"
    destino.mkdir(parents=True)
    (destino / "obra_anterior.pdf").write_bytes(b"%PDF-1.4 anterior")
    (destino / "CONTRATO_FIRMADO.pdf").write_bytes(b"%PDF-1.4 contrato equivocado")
    for nombre in ("P1_E1.ok", "P1_E1.seace.ok"):
        (raiz / "descargas" / nombre).write_text("ok")
    (raiz / "final.xlsx").write_bytes(b"entrega anterior")
    nuevo, casos = proyectar(e, enr, r)
    rev = publicar_asociaciones(repo, raiz, JID, enr, nuevo, casos)
    assert (raiz / "identidad_pendiente.json").exists()
    assert not destino.exists()
    assert (raiz / "identidades_previas" / rev / "descargas/P1_E1/obra_anterior.pdf").exists()
    assert not (raiz / "final.xlsx").exists()
    llamadas = []
    def bajar(oid, ruta):
        llamadas.append(oid)
        if fallar: raise RuntimeError("Fuente no respondió")
        ruta.mkdir(parents=True, exist_ok=True)
        (ruta / "obra_nueva.pdf").write_bytes(b"%PDF-1.4 nueva")
    def bajar_seace(url, ruta):
        llamadas.append(url)
        if fallar: return False
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"%PDF-1.4 documento nuevo")
        return True
    for _ in range(2):
        descargar_documentos_job(e, nuevo, JID, tmp_path,
            descargar=bajar, descargar_seace=bajar_seace)
    assert 10 not in llamadas
    assert not any(str(x).endswith("anterior.pdf") for x in llamadas)
    assert not (destino / "obra_anterior.pdf").exists()
    if not fallar:
        assert llamadas.count(20) == 1
        carpeta_seace = destino / "Documentos SEACE"
        manifiesto = json.loads((carpeta_seace / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))
        assert len(manifiesto["documentos"]) == 2
        assert all(d["estado"] == "descargado" for d in manifiesto["documentos"])
        assert not (destino / "CONTRATO_FIRMADO.pdf").exists()
    if fallar:
        assert not (destino / "CONTRATO_FIRMADO.pdf").exists()
    salida = construir_zip_infoobras(e, {(1, 1): destino}, tmp_path / "validacion.zip", nuevo)
    with zipfile.ZipFile(salida) as z:
        assert not any("obra_anterior" in n or "identidades_previas" in n for n in z.namelist())
        assert not any(b"contrato equivocado" in z.read(n) for n in z.namelist())


def test_interrupcion_publicacion_conserva_diario_y_respaldo(tmp_path):
    e, enr, r = insumos(); nuevo, casos = proyectar(e, enr, r)
    class Falla:
        def guardar_enriquecimiento(self, *args): raise OSError("disco")
    with pytest.raises(OSError): publicar_asociaciones(Falla(), tmp_path, JID, enr, nuevo, casos)
    assert (tmp_path / "identidad_pendiente.json").exists()
    assert list(tmp_path.glob("identidades_previas/*/enriquecimiento.json"))


def test_subobra_corrige_solo_posicion_sin_heredar_periodo_global(tmp_path):
    e, enr, r = insumos()
    e["profesionales"][0]["experiencias"][0].update(
        fecha_inicial="2020-01-01", fecha_final="2025-01-01",
        obras=[{"proyecto": "Uno"}, {"proyecto": "Dos"}])
    sub = enr["1:1"]
    enr = {"1:1": {"via": "MULTI_OBRA", "sub_obras": [sub, {"proyecto": "Dos"}]}}
    r["caso_id"] = "1:1:s1"
    r["huella_contexto"] = preparar_contexto(JID, e, enr, "obras")["huella_contexto"]
    nuevo, casos = proyectar(e, enr, r)
    assert "fecha_inicial" not in nuevo["1:1"]["sub_obras"][0]
    assert nuevo["1:1"]["sub_obras"][1] == enr["1:1"]["sub_obras"][1]
    destino = tmp_path / "descargas/P1_E1/Subobra 02"
    destino.mkdir(parents=True); (destino / "hermano.pdf").write_bytes(b"hermano")
    publicar_asociaciones(RepositorioMemoria(), tmp_path, JID, enr, nuevo, casos)
    assert (destino / "hermano.pdf").read_bytes() == b"hermano"


@pytest.mark.parametrize("fallo_excel", [False, True])
def test_api_aplica_en_memoria_y_publica_solo_al_terminar(tmp_path, monkeypatch, fallo_excel):
    from fastapi.testclient import TestClient
    from schemas.pipeline import Job, JobEstado
    import api.app as api
    import orquestador.aplicar_identidad as modulo
    import orquestador.recontraste_identidad as contraste
    from orquestador.recontraste_fuentes import FuentesRecontraste
    e, enr, r = insumos()
    repo = RepositorioMemoria()
    repo.guardar(Job(job_id=JID, analisis_id="prueba", estado=JobEstado.COMPLETADO,
                     descargas_estado="listas"))
    repo.guardar_espejo(JID, e); repo.guardar_enriquecimiento(JID, enr)
    monkeypatch.setattr(api, "repo", repo)
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    monkeypatch.setattr(contraste, "fetch_by_cui", lambda *a, **kw: None)
    monkeypatch.setattr(contraste, "FuentesRecontraste", lambda:
        FuentesRecontraste(ficha=lambda c: None, contratos=lambda c: None,
                          empresa=lambda r: None, buscar=lambda n: [], extras=lambda r: ([], None)))
    original = modulo.proyectar_asociaciones
    monkeypatch.setattr(modulo, "proyectar_asociaciones", lambda *args:
                        original(*args, leer_ficha=ficha, leer_procesos=procesos))
    llamadas = []
    def descargar(jid):
        llamadas.append(jid)
        construir_zip_infoobras(e, {}, tmp_path / jid / "infoobras.zip", repo.cargar_enriquecimiento(jid))
        job = repo.cargar(jid); job.descargas_estado = "listas_con_errores"; repo.guardar(job)
    monkeypatch.setattr(api, "_asegurar_descargas", descargar)
    def generar(espejo, enriquecimiento, salida, *args, **kwargs):
        assert enriquecimiento["1:1"]["asociacion_investigada"]["contraste_derivado"] == "actualizado_con_faltantes"
        assert "obra_ficha" not in enriquecimiento["1:1"]
        if fallo_excel:
            raise OSError("disco simulado")
        salida.write_bytes(b"excel nuevo")
    monkeypatch.setattr(api, "regenerar_excel_final", generar)
    cliente = TestClient(api.app)
    ruta = f"/api/pivote/jobs/{JID}"
    mala = deepcopy(r); mala["huella_contexto"] = "0"*64
    assert cliente.post(ruta + "/investigacion-identidad/aplicar", json={"resultados": [mala]}).status_code == 422
    assert repo.cargar_enriquecimiento(JID) == enr
    assert not llamadas
    respuesta = cliente.post(ruta + "/investigacion-identidad/aplicar", json={"resultados": [r]})
    assert respuesta.status_code == 202, respuesta.text
    assert llamadas == [JID]
    assert repo.cargar_enriquecimiento(JID)["1:1"]["cui"] == "2000002"
    assert repo.cargar_espejo(JID) == e
    assert cliente.get(ruta + "/excel").status_code == (409 if fallo_excel else 200)
    assert (tmp_path / JID / "identidad_pendiente.json").exists() == fallo_excel
    assert (tmp_path / JID / "identidad_contraste_pendiente.json").exists() == fallo_excel
    assert cliente.get(ruta + "/zip").status_code == (409 if fallo_excel else 200)
    assert repo.cargar(JID).revision_estado == ("error" if fallo_excel else "completada")
    assert cliente.post(ruta + "/investigacion-identidad/aplicar", json={"resultados": [r]}).status_code == (409 if fallo_excel else 422)


def test_api_diario_interrumpido_bloquea_zip_y_excel(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from schemas.pipeline import Job, JobEstado
    import api.app as api
    repo = RepositorioMemoria()
    repo.guardar(Job(job_id=JID, analisis_id="prueba", estado=JobEstado.COMPLETADO,
                     descargas_estado="listas"))
    monkeypatch.setattr(api, "repo", repo); monkeypatch.setattr(api, "DATA_DIR", tmp_path)
    raiz = tmp_path / JID; raiz.mkdir()
    (raiz / "identidad_pendiente.json").write_text('{}')
    cliente = TestClient(api.app)
    for entrega in ("excel", "zip"):
        assert cliente.get(f"/api/pivote/jobs/{JID}/{entrega}").status_code == 409


def test_abstencion_explicita_retira_identidad_sin_promover_candidatos():
    e, enr, r = insumos()
    r.update(estado="ambiguo", seleccion_propuesta=None, motivo="Dos intervenciones compatibles",
             consultas=[{"fuente": "InfoObras", "estado": "leido"}])
    nuevo, _ = proyectar(e, enr, r, leer_ficha=lambda *a: pytest.fail("No consultar candidato ambiguo"))
    assert nuevo["1:1"]["estado"] == "revision"
    assert nuevo["1:1"]["obra"] is None
    assert nuevo["1:1"]["seace"]["docs"] == {}
