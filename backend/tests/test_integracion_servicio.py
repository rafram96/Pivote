"""El servicio viaja sin reescribir identidad, camino o entregas anteriores."""
from copy import deepcopy
from datetime import date
import io
import json
import zipfile

import openpyxl
import pytest

from entregables.excel_final import generar_excel_final, desempaquetar_enriquecimiento
from entregables.zip_infoobras import construir_zip_infoobras
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal
from reglas.cruces_fechas import cruces_de_experiencia
from schemas.pipeline import Job
from validacion.servicio_experiencia import contrastar_servicio, evidencia_tipo_servicio, fase_servicio_incompatible
from test_api import cliente  # noqa: F401 — fixture con repositorio temporal sin red


def evidencia(tipo, texto, fuente="certificado", pagina=15):
    return {"tipo": tipo, "texto": texto, "fuente": fuente, "pagina_pdf": pagina}


def espejo_prueba(ruta="obras", declarado=None):
    esperado = (evidencia("supervision_obra", "Servicio de supervisión de obra", "bases", 5)
                if ruta == "obras" else
                evidencia("elaboracion_expediente", "Elaboración del expediente técnico", "tdr", 7))
    exp = {"n": 1, "proyecto": "Construcción del hospital de prueba", "entidad_emisora": "Contratista privado",
           "cargo_ocupado": "Especialista", "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31",
           "cui": "2000001", "servicio_declarado": declarado}
    return {"_meta": {"analisis_id": "servicio-prueba", "tipo_evaluacion": ruta, "servicio_esperado": esperado},
            "postor": {}, "resumen_evaluacion": {"factores": []},
            "profesionales": [{"n_prof": 1, "cargo": "ESPECIALISTA", "nombre": "Profesional de prueba",
                                "cumple": "POR VERIFICAR", "experiencias": [exp]}]}


def contexto(espejo, via="CUI_TEXTO", cui="2000001"):
    return Contexto(Job(job_id="servicio-prueba", analisis_id="servicio-prueba"), espejo,
                    enriquecimiento={"1:1": {"cui": cui, "via": via}})


@pytest.mark.parametrize("via,cui", [("CUI_TEXTO", "2000001"), ("PRIVADA", None), ("REVISION", None)])
def test_contraste_existe_con_y_sin_identidad_sin_reclasificar(via, cui, tmp_path):
    esp = espejo_prueba(declarado=evidencia("ejecucion_obra", "Residente de obra"))
    ctx = contexto(esp, via, cui)
    original = deepcopy(esp)
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path, fetcher=lambda *a, **kw: None,
                             consulta_ocds=lambda cui: [])
    resultado = etapa.correr(ctx)
    enr = ctx.enriquecimiento["1:1"]
    assert enr["contraste_servicio"]["estado"] == "difiere"
    assert enr["cui"] == cui and enr["via"] == via
    assert ctx.espejo == original
    assert any(o.codigo == "SERVICIO" for o in resultado.observaciones)


@pytest.mark.parametrize("ruta,declarado", [
    ("obras", evidencia("elaboracion_expediente", "Elaboración del expediente técnico")),
    ("expedientes", evidencia("ejecucion_obra", "Residente de obra")),
])
def test_otra_fase_no_aplica_mef_ni_resta_periodo_de_construccion(ruta, declarado, tmp_path):
    esp = espejo_prueba(ruta, declarado)
    ctx = contexto(esp)
    def no_mef(*args, **kwargs):
        pytest.fail("No consultar contrato de expediente para certificado de otra fase")
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path, fetcher=lambda *a, **kw: None,
        consulta_ocds=lambda cui: [], verificador_mef=no_mef)
    etapa.correr(ctx)
    enr = ctx.enriquecimiento["1:1"]
    assert enr["camino"] == ("obra" if ruta == "obras" else "expediente")
    assert enr["cui"] == "2000001"
    assert enr["servicio_fase_incompatible"] and enr["sin_verificar"]
    assert not enr.get("paralizaciones")
    assert not enr.get("verificacion_expediente")
    cruces = cruces_de_experiencia(enr, esp["profesionales"][0]["experiencias"][0])
    assert cruces and all(c.resultado == "por_confirmar" for c in cruces)
    assert all(c.fecha_fuente is None for c in cruces)


@pytest.mark.parametrize("ruta", ["obras", "expedientes"])
def test_misma_evidencia_en_excel_zip_y_desempaquetado(ruta, tmp_path):
    esp = espejo_prueba(ruta, evidencia("ejecucion_obra", "Residente de obra"))
    exp = esp["profesionales"][0]["experiencias"][0]
    contraste = contrastar_servicio(esp, exp)
    enr = {"1:1": {"cui": "2000001", "via": "CUI_TEXTO", "contraste_servicio": contraste}}
    _, _, fichas, _ = desempaquetar_enriquecimiento(enr)
    assert fichas[1, 1]["contraste_servicio"] == contraste
    copia_fichas = deepcopy(fichas)
    salida = generar_excel_final(deepcopy(esp), tmp_path / "servicio.xlsx", fichas=fichas)
    assert fichas == copia_fichas
    wb = openpyxl.load_workbook(salida)
    hoja = wb.worksheets[2]
    texto = " ".join(str(c.value) for fila in hoja for c in fila if c.value is not None)
    assert "Residente de obra" in texto and "página PDF 15" in texto
    assert "SERVICIO ESPERADO (concurso)" not in texto
    assert "SERVICIO DECLARADO (certificado)" not in texto
    assert "CONTRASTE DE SERVICIO" not in texto
    fila_cargo = next(
        " ".join(str(c.value) for c in fila if c.value is not None)
        for fila in hoja.iter_rows()
        if any(str(c.value).strip() == "CARGO QUE OCUPÓ" for c in fila)
    )
    assert "Residente de obra" in fila_cargo
    esperado = ("Supervisión de obra" if ruta == "obras"
                else "Elaboración de expediente técnico")
    assert esperado in fila_cargo
    assert "Por verificar: se espera" in fila_cargo
    salida_zip = construir_zip_infoobras(esp, {}, tmp_path / "servicio.zip", enr)
    with zipfile.ZipFile(salida_zip) as z:
        nombre = next(n for n in z.namelist() if n.endswith("IDENTIFICACION.txt"))
        identidad = z.read(nombre).decode("utf-8")
    assert contraste["motivo"] in identidad
    assert "Residente de obra" in identidad and "página PDF 15" in identidad


@pytest.mark.parametrize("ruta", ["obras", "expedientes"])
def test_servicio_coincidente_no_inserta_aviso_en_fila_cargo(ruta, tmp_path):
    declarado = (evidencia("supervision_obra", "Servicio de supervisión de obra", "certificado", 15)
                 if ruta == "obras" else
                 evidencia("elaboracion_expediente", "Elaboración del expediente técnico", "certificado", 15))
    esp = espejo_prueba(ruta, declarado)
    contraste = contrastar_servicio(esp, esp["profesionales"][0]["experiencias"][0])
    assert contraste["estado"] == "coincide"
    _, _, fichas, _ = desempaquetar_enriquecimiento({"1:1": {"contraste_servicio": contraste}})
    salida = generar_excel_final(esp, tmp_path / "coincide.xlsx", fichas=fichas)
    hoja = openpyxl.load_workbook(salida).worksheets[2]
    fila_cargo = next(
        " ".join(str(c.value) for c in fila if c.value is not None)
        for fila in hoja.iter_rows()
        if any(str(c.value).strip() == "CARGO QUE OCUPÓ" for c in fila)
    )
    assert "Residente de obra" not in fila_cargo
    assert "esperado" not in fila_cargo.lower()
    assert "declarado" not in fila_cargo.lower()


@pytest.mark.parametrize("ruta", ["obras", "expedientes"])
def test_servicio_indeterminado_no_agrega_filas_de_formato(ruta, tmp_path):
    esp = espejo_prueba(ruta)
    contraste = contrastar_servicio(esp, esp["profesionales"][0]["experiencias"][0])
    assert contraste["estado"] == "no_determinado"
    _, _, fichas, _ = desempaquetar_enriquecimiento({"1:1": {"contraste_servicio": contraste}})
    salida = generar_excel_final(esp, tmp_path / "indeterminado.xlsx", fichas=fichas)
    hoja = openpyxl.load_workbook(salida).worksheets[2]
    textos = [str(c.value) for fila in hoja.iter_rows() for c in fila if c.value is not None]
    for rotulo in ("SERVICIO ESPERADO (concurso)", "SERVICIO DECLARADO (certificado)",
                   "CONTRASTE DE SERVICIO", "Por verificar: se espera"):
        assert rotulo not in " ".join(textos)


def test_ficha_de_otra_fase_no_se_rotula_como_trabajo_del_profesional(tmp_path):
    esp = espejo_prueba("expedientes", evidencia("ejecucion_obra", "Residente de obra"))
    ficha = {"obra_nombre": "Proyecto identificado", "cui": "2000001", "camino": "expediente"}
    salida = generar_excel_final(esp, tmp_path / "ficha.xlsx", fichas={(1, 1): ficha})
    texto = " ".join(str(c.value) for fila in openpyxl.load_workbook(salida).worksheets[2]
                     for c in fila if c.value is not None)
    assert "FICHA DEL PROYECTO — servicio de otra fase" in texto
    assert "PROYECTO CUYO EXPEDIENTE TÉCNICO ELABORÓ ESTE CARGO" not in texto
    assert "PROVISIONAL — POR VERIFICAR" in texto


def test_legado_se_presenta_como_no_determinado_no_inventa_literal():
    esp = espejo_prueba()
    exp = esp["profesionales"][0]["experiencias"][0]
    exp.pop("servicio_declarado")
    contraste = contrastar_servicio(esp, exp)
    assert contraste["estado"] == "no_determinado"
    assert not (contraste.get("declarado") or {}).get("texto")


def test_supervision_de_expediente_compara_sin_confundirse_con_obra():
    ev = evidencia("supervision_expediente", "Supervisión del expediente técnico")
    esp = espejo_prueba("expedientes", ev)
    esp["_meta"]["servicio_esperado"] = {**ev, "fuente": "bases"}
    exp = esp["profesionales"][0]["experiencias"][0]
    assert contrastar_servicio(esp, exp)["estado"] == "coincide"
    assert evidencia_tipo_servicio(exp)["tipo"] is None  # sin selector SEACE específico
    assert not fase_servicio_incompatible(esp, exp, True)
    assert fase_servicio_incompatible(esp, exp, False)


@pytest.mark.parametrize("literal", ["Construcción del hospital", "Especialista del proyecto: Construcción del hospital",
    "Especialista para el proyecto denominado Construcción del hospital", "Especialista del expediente técnico"])
def test_titulo_no_se_convierte_en_prueba_aunque_venga_tipo_erroneo(literal):
    exp = {"servicio_declarado": evidencia("ejecucion_obra", literal)}
    assert evidencia_tipo_servicio(exp)["tipo"] is None


@pytest.mark.parametrize("ruta", ["obras", "expedientes"])
def test_api_devuelve_el_mismo_contraste_sin_reescribir_cui(cliente, ruta):
    esp = espejo_prueba(ruta, evidencia("ejecucion_obra", "Residente de obra"))
    cid = cliente.post("/api/pivote/concursos", json={"nomenclatura": "Prueba", "entidad": "Entidad"}).json()["concurso_id"]
    respuesta = cliente.post("/api/pivote/analizar", data={"concurso_id": cid}, files={
        "espejo": ("espejo.json", io.BytesIO(json.dumps(esp).encode()), "application/json"),
        "excel": ("claude.xlsx", io.BytesIO(b"PK demo"), "application/octet-stream"),
    })
    assert respuesta.status_code == 201, respuesta.text
    jid = respuesta.json()["job_id"]
    exp = cliente.get(f"/api/pivote/jobs/{jid}/espejo").json()["profesionales"][0]["experiencias"][0]
    assert exp["cui"] == "2000001"
    assert exp["servicio_declarado"] == esp["profesionales"][0]["experiencias"][0]["servicio_declarado"]
    assert exp["contraste_servicio"] == contrastar_servicio(esp, esp["profesionales"][0]["experiencias"][0])


@pytest.mark.parametrize("ruta,tipo,texto", [
    ("expedientes", "ejecucion_obra", "Residente de obra"),
    ("obras", "elaboracion_expediente", "Elaboración del expediente técnico"),
])
def test_recontraste_conserva_identidad_y_abstiene_fechas_de_otra_fase(ruta, tipo, texto):
    from test_aplicar_identidad import insumos, proyectar
    from entregables.investigacion_identidad import preparar_contexto
    from orquestador.recontraste_identidad import recontrastar_asociaciones
    from scraping.infoobras import WorkInfo
    esp, enr, resultado = insumos(ruta)
    exp = esp["profesionales"][0]["experiencias"][0]
    exp["servicio_declarado"] = evidencia(tipo, texto)
    resultado["huella_contexto"] = preparar_contexto(resultado["job_id"], esp, enr, ruta)["huella_contexto"]
    nuevo, _ = proyectar(esp, enr, resultado)
    copia = deepcopy(nuevo)
    class Fuentes:
        def contrastar_mef(self, *args):
            pytest.fail("No debe comprobar otro servicio con el contrato del expediente")
        def contrastar_sunat(self, *args):
            return {}, {"estado": "sin_datos"}, []
    final = recontrastar_asociaciones(esp, nuevo, ["1:1"], fuentes=Fuentes(),
        leer_obra=lambda *a, **kw: WorkInfo(cui="2000002", obra_id=20, nombre="Proyecto identificado",
                                           fecha_inicio=date(2021, 1, 1)))
    assert nuevo == copia
    unidad = final["1:1"]
    assert unidad["cui"] == "2000002" and unidad["obra"]["obra_id"] == 20
    assert unidad["camino"] == ("expediente" if ruta == "expedientes" else "obra")
    assert unidad["servicio_fase_incompatible"] and unidad["sin_verificar"]
    assert not unidad.get("paralizaciones") and not unidad.get("verificacion_expediente")
    assert all(c["resultado"] == "por_confirmar" for c in unidad["cruces_fechas"])
