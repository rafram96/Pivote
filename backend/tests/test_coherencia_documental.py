"""Tipo documental por etiqueta, rol del servicio y lectura indivisible."""
from copy import deepcopy

import pytest

from scraping import mef
from scraping.seace_abierto import tipo_por_experiencia
from validacion.resolucion_aprobacion import conservar_lectura_resolucion


@pytest.mark.parametrize("fecha,numero", [(None, "B"), ("2021-01-01", None)])
def test_no_completa_fecha_con_otro_pdf(fecha, numero):
    previa = {"coincide_emisor": "confirma", "fecha": fecha, "numero": numero,
              "url": "https://fuente/b.pdf", "archivo": "b.pdf", "sha256": "b"}
    nueva = {"coincide_emisor": "nombra_otro", "fecha": "2025-01-01", "numero": "A",
             "url": "https://fuente/a.pdf", "archivo": "a.pdf", "sha256": "a"}
    antes = deepcopy(previa)
    assert conservar_lectura_resolucion(previa, nueva) == antes
    assert previa == antes


def test_fecha_historica_mezclada_se_retira_con_motivo():
    previa = {"coincide_emisor": "confirma", "fecha": "2025-01-01", "numero": "B",
              "fecha_de_resolucion_numero": "A", "archivo": "b.pdf",
              "resumen": "Resolución de aprobación del 01/01/2025."}
    salida = conservar_lectura_resolucion(previa, {"coincide_emisor": "sin_texto"})
    assert salida["fecha"] is None
    assert salida["fecha_descartada"] == "2025-01-01"
    assert salida["archivo"] == "b.pdf"
    assert "01/01/2025" not in salida["resumen"]
    assert previa["fecha"] == "2025-01-01"


@pytest.mark.parametrize("etiqueta", ["RESOLUCIÓN DE CONTRATO N° 002-2021",
    "Resolucion del contrato 5", "Resolución parcial de contrato", "CARTA NOTARIAL"])
def test_acto_contractual_no_compite_con_aprobacion_pero_se_conserva(etiqueta):
    html = (f'<a href="/downloadArchivoPublico?idArchivo=1">{etiqueta}</a>'
            '<a href="/downloadArchivoPublico?idArchivo=2">Resolución de aprobación N° 007-2024</a>')
    ficha = mef.parsear_ficha_08a(html)
    assert ficha["documentos"][0]["es_aprobacion"] is False
    assert ficha["resolucion"]["url"].endswith("=2")
    verificacion = mef.verificar_expediente({}, ficha, [])
    assert verificacion["documentos_contractuales"][0]["label"] == etiqueta


def test_etiqueta_ambigua_permanece_candidata_no_se_declara_clasificada():
    ficha = mef.parsear_ficha_08a('<a href="/downloadArchivoPublico?idArchivo=1">Resolución N° 009-2024</a>')
    assert ficha["documentos"][0]["es_aprobacion"]
    assert ficha["documentos"][0]["tipo_indicado"] == "por_identificar"


@pytest.mark.parametrize("proyecto", ["CONSTRUCCIÓN DEL HOSPITAL", "RECONSTRUCCION DEL HOSPITAL", "EJECUCION Y EQUIPAMIENTO"])
def test_nombre_no_confiere_rol_al_especialista(proyecto):
    resultado = tipo_por_experiencia(False, {"proyecto": proyecto, "cargo_ocupado": "Especialista de estructuras"})
    assert resultado["tipo"] is None


def test_cargo_de_la_experiencia_tiene_precedencia_no_el_propuesto():
    assert tipo_por_experiencia(False, {"proyecto": "Supervisión de hospital", "cargo_ocupado": "Residente de obra"})["tipo"] == "ejecucion"
    assert tipo_por_experiencia(False, {"proyecto": "Construcción de hospital", "cargo_ocupado": "Supervisor de obra"})["tipo"] == "supervision"
    assert tipo_por_experiencia(False, {"cargo_ocupado": "Residente / supervisor"})["tipo"] is None
    assert tipo_por_experiencia(True, {"cargo_ocupado": "Especialista", "proyecto": "Construcción"})["tipo"] == "expediente"


def test_objeto_de_supervision_de_ejecucion_no_es_contradictorio():
    assert tipo_por_experiencia(False, {"objeto": "Supervisión de la ejecución de la obra", "cargo_ocupado": "Especialista"})["tipo"] == "supervision"


def contexto(expediente=True):
    from orquestador.etapas import Contexto
    from schemas.pipeline import Job
    espejo = {"_meta": {"tipo_evaluacion": "expedientes" if expediente else "obras"},
              "profesionales": [{"n_prof": 1, "experiencias": [{
                  "n": 1, "proyecto": "Elaboración del expediente del hospital" if expediente else "Construcción del hospital",
                  "cargo_ocupado": "Especialista", "entidad_emisora": "Consultor Uno"}]}]}
    return Contexto(Job(job_id="coherencia", analisis_id="prueba"), espejo,
                    enriquecimiento={"1:1": {"cui": "2000001", "via": "MEF" if expediente else "CUI_TEXTO"}})


@pytest.mark.parametrize("falla_nueva_lectura", [False, True])
def test_etapa_mantiene_url_numero_y_fecha_del_mismo_documento(tmp_path, falla_nueva_lectura):
    from orquestador.etapas_reales import EtapaInfoObrasReal
    ctx = contexto()
    ctx.enriquecimiento["1:1"]["resolucion_aprobacion"] = {
        "coincide_emisor": "confirma", "fecha": None, "numero": "B", "url": "https://mef/b.pdf", "archivo": "b.pdf"}
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path,
        verificador_mef=lambda *a: {"verificado_en_mef": True, "resolucion": {"numero": "A", "url": "https://mef/a.pdf"}},
        lector_resolucion=lambda *a, **kw: None if falla_nueva_lectura else {
            "coincide_emisor": "no_nombra", "numero": "A", "url": "https://mef/a.pdf", "fecha": "2025-01-01"},
        consulta_ocds=lambda cui: [])
    etapa.correr(ctx)
    unidad = ctx.enriquecimiento["1:1"]
    resumen = unidad["verificacion_expediente"]["resolucion"]
    assert resumen["numero"] == "B" and resumen["url"].endswith("b.pdf")
    assert resumen["fecha"] is None and unidad["resolucion_aprobacion"]["fecha"] is None
    assert resumen["veredicto"] == "no_verificable"
    assert not any("que aprobó" in o.mensaje for o in ctx.job.observaciones)


def test_etapa_no_pierde_carta_cuando_no_hay_aprobacion(tmp_path):
    from orquestador.etapas_reales import EtapaInfoObrasReal, descargar_documentos_job
    ctx = contexto()
    ficha = mef.parsear_ficha_08a('<a href="/downloadArchivoPublico?idArchivo=1">Carta notarial</a>')
    verificacion = mef.verificar_expediente({}, ficha, [])
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path,
        verificador_mef=lambda *a: deepcopy(verificacion), consulta_ocds=lambda cui: [])
    etapa.correr(ctx)
    unidad = ctx.enriquecimiento["1:1"]
    assert not unidad.get("sin_documentos_mef")
    assert not unidad["verificacion_expediente"]["verificado_en_mef"]
    def descargar(url, ruta):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"%PDF-1.4 carta")
        return True
    descargar_documentos_job(ctx.espejo, ctx.enriquecimiento, "coherencia", tmp_path, descargar_mef=descargar)
    assert list((tmp_path / "coherencia/descargas/P1_E1").rglob("ACTO_CONTRACTUAL_*.pdf"))


def test_etapa_no_descarga_proceso_ejecutor_por_nombre(tmp_path):
    from orquestador.etapas_reales import EtapaInfoObrasReal, descargar_documentos_job
    ctx = contexto(False)
    # No ficha externa: se ejercita el bloque SEACE con CUI ya identificado.
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path, fetcher=lambda *a, **kw: None,
        consulta_ocds=lambda cui: [{"ocid": "ejecutor", "tender": {"title": "Ejecución de la obra"},
            "contracts": [{"documents": [{"documentType": "contractSigned", "url": "https://fuente/ejecutor.pdf"}]}]}])
    etapa.correr(ctx)
    seace = ctx.enriquecimiento["1:1"]["seace"]
    assert seace["estado"] == "tipo_indeterminado"
    assert seace["documentos"] == []
    descargar_documentos_job(ctx.espejo, ctx.enriquecimiento, "coherencia", tmp_path,
                             descargar_seace=lambda *a: pytest.fail("No descargar ejecutor"))
    nota = tmp_path / "coherencia/descargas/P1_E1/Documentos SEACE/DOCUMENTOS_SEACE.txt"
    texto = nota.read_text(encoding="utf-8")
    assert "No se seleccionaron documentos SEACE" in texto
    assert "Estado de fuente: tipo_indeterminado" in texto
