"""Selección por experiencia, sin InfoObras ni reselección durante la descarga."""
from copy import deepcopy
import hashlib
import json
import zipfile

import pytest

from entregables.zip_infoobras import construir_zip_infoobras
from orquestador.etapas_reales import descargar_documentos_job
from validacion.resolucion_aprobacion import leer_resolucion


def caso():
    espejo = {"_meta": {"tipo_evaluacion": "expedientes"}, "profesionales": [{
        "n_prof": 1, "cargo": "Arquitecto", "experiencias": [
            {"n": 1, "proyecto": "Elaboración del expediente de hospital"}]}]}
    info = {"1:1": {"via": "MEF", "camino": "expediente", "cui": "2000001",
                    "verificacion_expediente": {
                        "cui_confirmado": "2000001", "contrato": {
                            "numero": "CONTRATO-2", "pdf": "https://mef/contrato-2.pdf"}}}}
    return espejo, info


def descargador(llamadas):
    def descargar(url, ruta):
        llamadas.append(url)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b"%PDF-1.4 " + url.encode())
        return True
    return descargar


def test_sin_ficha_descarga_seleccion_no_reconsulta_y_llega_zip(tmp_path, monkeypatch):
    espejo, info = caso()
    llamadas, progreso = [], []
    def prohibido(*a, **kw):
        pytest.fail("No debe consultar ni reelegir contratos/ficha")
    monkeypatch.setattr("scraping.mef.descargar_documentos_expediente", prohibido)
    monkeypatch.setattr("scraping.mef.fetch_contratos", prohibido)
    monkeypatch.setattr("scraping.mef.fetch_ficha_08a", prohibido)
    for _ in range(2):
        descargar_documentos_job(espejo, info, "prueba", tmp_path,
                                 descargar_mef=descargador(llamadas),
                                 reportar=lambda n, total, nombre: progreso.append((n, total)))
    assert llamadas == ["https://mef/contrato-2.pdf"]
    assert progreso == [(1, 1), (1, 1)]
    destino = tmp_path / "prueba/descargas/P1_E1"
    assert info["1:1"]["descargas_reales"]["completada"]
    assert info["1:1"]["descargas_reales"]["archivos"] == 1
    salida = construir_zip_infoobras(espejo, {(1, 1): destino}, tmp_path / "entrega.zip", info)
    with zipfile.ZipFile(salida) as z:
        nombre = next(n for n in z.namelist() if n.endswith("CONTRATO_SELECCIONADO.pdf"))
        assert z.read(nombre).endswith(b"contrato-2.pdf")


def test_mismo_cui_distintos_contratos_y_cache_compartida(tmp_path):
    espejo, info = caso()
    espejo["profesionales"][0]["experiencias"] += [{"n": 2}, {"n": 3}]
    info["1:2"] = deepcopy(info["1:1"])
    info["1:2"]["verificacion_expediente"]["contrato"].update(
        numero="CONTRATO-3", pdf="https://mef/contrato-3.pdf")
    info["1:3"] = deepcopy(info["1:1"])
    llamadas = []
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador(llamadas))
    assert llamadas == ["https://mef/contrato-2.pdf", "https://mef/contrato-3.pdf"]
    raiz = tmp_path / "prueba/descargas"
    assert (raiz / "P1_E2/Verificación MEF/CONTRATO_SELECCIONADO.pdf").read_bytes().endswith(b"3.pdf")
    assert (raiz / "P1_E3/Verificación MEF/CONTRATO_SELECCIONADO.pdf").read_bytes().endswith(b"2.pdf")


def preparar_lectura(tmp_path, info):
    raiz = tmp_path / "prueba/resoluciones"
    raiz.mkdir(parents=True)
    contenido = b"%PDF-1.4 Documento B efectivamente leido"
    (raiz / "leida.pdf").write_bytes(contenido)
    info["1:1"]["resolucion_aprobacion"] = {
        "numero": "B", "url": "https://mef/leida.pdf", "archivo": "leida.pdf",
        "sha256": hashlib.sha256(contenido).hexdigest(), "fecha": "2020-01-01"}
    info["1:1"]["verificacion_expediente"]["resolucion"] = {
        "numero": "A", "url": "https://mef/candidata-distinta.pdf"}
    return raiz / "leida.pdf"


def test_publica_pdf_leido_no_el_candidato_mef(tmp_path):
    espejo, info = caso()
    origen = preparar_lectura(tmp_path, info)
    llamadas = []
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador(llamadas))
    carpeta = tmp_path / "prueba/descargas/P1_E1/Verificación MEF"
    assert (carpeta / "RESOLUCION_SELECCIONADA.pdf").read_bytes() == origen.read_bytes()
    assert llamadas == ["https://mef/contrato-2.pdf"]
    registro = json.loads((carpeta / "DOCUMENTOS_MEF.json").read_text(encoding="utf-8"))
    assert registro["documentos"][1]["sha256_entregado"] == info["1:1"]["resolucion_aprobacion"]["sha256"]


@pytest.mark.parametrize("defecto", ["falta", "cambio", "sin_huella", "ruta"])
def test_lectura_no_verificable_no_se_reemplaza(tmp_path, defecto):
    espejo, info = caso()
    origen = preparar_lectura(tmp_path, info)
    lectura = info["1:1"]["resolucion_aprobacion"]
    if defecto == "falta":
        origen.unlink()
    elif defecto == "cambio":
        origen.write_bytes(b"%PDF-1.4 otro")
    elif defecto == "sin_huella":
        lectura.pop("sha256")
    else:
        lectura["archivo"] = "../fuera.pdf"
    llamadas = []
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador(llamadas))
    assert llamadas == ["https://mef/contrato-2.pdf"]
    estado = info["1:1"]["descargas_reales"]
    assert not estado["completada"]
    assert estado["secciones"]["Verificación MEF"]["estado"] == "parcial"
    assert not (tmp_path / "prueba/descargas/P1_E1/Verificación MEF/RESOLUCION_SELECCIONADA.pdf").exists()


def test_fallo_es_terminal_no_inexistencia_ni_seleccion_alternativa(tmp_path):
    espejo, info = caso()
    llamadas = []
    intentos = set()
    def fallo(url, ruta):
        llamadas.append(url)
        return False
    for _ in range(2):
        descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=fallo,
                                 intentos_documentos=intentos, marcar_intento=intentos.add)
    assert llamadas == ["https://mef/contrato-2.pdf"]
    estado = info["1:1"]["descargas_reales"]
    assert not estado["completada"]
    assert any("no se eligió otro" in a for a in estado["avisos"])
    assert estado["archivos"] == 0
    nota = tmp_path / "prueba/descargas/P1_E1/Verificación MEF/DOCUMENTOS_MEF.txt"
    assert "no se eligió otro" in nota.read_text(encoding="utf-8")


def test_multiobra_no_activa_privada_ni_pendiente(tmp_path):
    espejo, info = caso()
    sub = info["1:1"]
    sub["estado"] = "resuelto"
    info["1:1"] = {"via": "MULTI_OBRA", "sub_obras": [sub,
        {**deepcopy(sub), "estado": "revision"},
        {**deepcopy(sub), "estado": "privada", "via": "PRIVADA"}]}
    llamadas = []
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador(llamadas))
    assert len(llamadas) == 1
    assert (tmp_path / "prueba/descargas/P1_E1/Subobra 01/Verificación MEF/CONTRATO_SELECCIONADO.pdf").exists()


def test_lector_no_comparte_pdf_por_numero_ni_cui(tmp_path):
    llamadas = []
    args = {"emisor": "Consultor", "cui": "2000001", "numero": None,
            "descargar": descargador(llamadas), "extraer_texto": lambda p: ("", "nativo", 1)}
    a = leer_resolucion("https://mef/a.pdf", tmp_path, **args)
    b = leer_resolucion("https://mef/b.pdf", tmp_path, **args)
    assert a["archivo"] != b["archivo"] and a["sha256"] != b["sha256"]
    assert len(llamadas) == 2


def test_cache_infoobras_no_mezcla_mef_de_otras_experiencias(tmp_path):
    espejo, info = caso()
    info["1:1"]["obra"] = {"obra_id": 101}
    info["1:2"] = deepcopy(info["1:1"])
    info["1:2"]["verificacion_expediente"]["contrato"].update(
        numero="OTRO", pdf="https://mef/otro.pdf")
    espejo["profesionales"][0]["experiencias"].append({"n": 2})
    def corpus(oid, destino):
        # Simula cache legado que contiene un contrato elegido por ficha.
        ruta = destino / "Verificación MEF"
        ruta.mkdir(parents=True)
        (ruta / "mas_barato.pdf").write_bytes(b"%PDF-1.4 ajeno")
    descargar_documentos_job(espejo, info, "prueba", tmp_path,
                             descargar=corpus, descargar_mef=descargador([]))
    for n, nombre in [(1, b"contrato-2.pdf"), (2, b"otro.pdf")]:
        carpeta = tmp_path / f"prueba/descargas/P1_E{n}/Verificación MEF"
        assert not (carpeta / "mas_barato.pdf").exists()
        assert (carpeta / "CONTRATO_SELECCIONADO.pdf").read_bytes().endswith(nombre)


def test_cambio_de_seleccion_con_fallo_retira_corpus_anterior(tmp_path):
    espejo, info = caso()
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador([]))
    info["1:1"]["verificacion_expediente"]["contrato"].update(
        numero="NUEVO", pdf="https://mef/falla.pdf")
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=lambda *a: False)
    carpeta = tmp_path / "prueba/descargas/P1_E1/Verificación MEF"
    assert not (carpeta / "CONTRATO_SELECCIONADO.pdf").exists()
    assert list((tmp_path / "prueba/descargas_previas").rglob("CONTRATO_SELECCIONADO.pdf"))
    assert not info["1:1"]["descargas_reales"]["completada"]


def test_retirar_seleccion_sin_otra_fuente_no_deja_mef_viejo(tmp_path):
    espejo, info = caso()
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador([]))
    info["1:1"].pop("verificacion_expediente")
    descargar_documentos_job(espejo, info, "prueba", tmp_path,
                             descargar_mef=lambda *a: pytest.fail("no hay selección"))
    assert not (tmp_path / "prueba/descargas/P1_E1/Verificación MEF").exists()
    assert info["1:1"]["descargas_reales"]["archivos"] == 0
    assert list((tmp_path / "prueba/descargas_previas").rglob("CONTRATO_SELECCIONADO.pdf"))


def test_actos_contractuales_se_descargan_sin_rotular_aprobacion(tmp_path):
    espejo, info = caso()
    info["1:1"]["verificacion_expediente"]["documentos_contractuales"] = [
        {"label": "Resolución de contrato", "url": "https://mef/terminacion.pdf"},
        {"label": "Carta notarial", "url": "https://mef/carta.pdf"}]
    llamadas = []
    descargar_documentos_job(espejo, info, "prueba", tmp_path, descargar_mef=descargador(llamadas))
    carpeta = tmp_path / "prueba/descargas/P1_E1/Verificación MEF"
    assert len(list(carpeta.glob("ACTO_CONTRACTUAL_*.pdf"))) == 2
    assert not (carpeta / "RESOLUCION_SELECCIONADA.pdf").exists()
    assert len(llamadas) == 3
    assert "contenido por confirmar" in (carpeta / "DOCUMENTOS_MEF.txt").read_text(encoding="utf-8")
