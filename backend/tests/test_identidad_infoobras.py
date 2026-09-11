"""La ficha consultada, el cálculo y el corpus comparten identidad; cero red."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
import json
import zipfile

import pytest

from entregables import construir_zip_infoobras
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal, descargar_documentos_job
from orquestador.repositorio import carpeta_job
from schemas import pipeline


def _caso(multi=False):
    espejo = {
        "_meta": {"analisis_id": "identidad", "tipo_evaluacion": "obras"},
        "profesionales": [{"n_prof": 1, "cargo": "SUPERVISOR", "nombre": "Persona",
            "experiencias": [{"n": 1, "proyecto": "Hospital de prueba",
                "cui": "2000001", "fecha_inicial": "2020-01-01",
                "fecha_final": "2020-12-31"}]}],
    }
    info = {"cui": "2000001", "via": "CODIGO", "estado": "resuelto",
            "obra": {"obra_id": 101, "cui": "2000001",
                     "nombre_obra": "Componente inicial", "departamento": "PRUEBA"}}
    enr = {"1:1": {"via": "MULTI_OBRA", "sub_obras": [info]} if multi else info}
    return espejo, enr, info


def _obra(oid=202):
    return SimpleNamespace(
        obra_id=oid, codigo_infoobras=str(oid), nombre="Ficha consultada",
        fecha_inicio=date(2020, 1, 1), fecha_fin=date(2020, 12, 31),
        avances=[SimpleNamespace(anio=2020, mes=m, estado="En ejecución")
                 for m in range(1, 13)],
    )


def _verificar(espejo, enr, fetcher=None):
    ctx = Contexto(job=pipeline.Job(job_id="identidad", analisis_id="identidad"),
                   espejo=espejo, enriquecimiento=enr)
    resultado = EtapaInfoObrasReal(
        fetcher=fetcher or (lambda *_: _obra()), consulta_ocds=lambda _: [],
        verificador_mef=lambda *_: None,
    ).correr(ctx)
    return resultado


@pytest.mark.parametrize("multi", [False, True])
def test_ficha_final_se_propaga_a_descarga_y_zip_sin_cambiar_el_cui(tmp_path, multi):
    espejo, enr, info = _caso(multi)
    declarado = deepcopy(espejo)
    inicial = deepcopy(info["obra"])
    _verificar(espejo, enr)

    assert info["obra"]["obra_id"] == 202
    assert info["obra"]["nombre_obra"] == "Ficha consultada"
    assert info["obra_inicial"] == inicial
    assert info["via"] == "CODIGO" and info["cui"] == "2000001"
    assert espejo == declarado
    ficha = info["ficha"] if multi else info["obra_ficha"]
    assert ficha["obra_id"] == 202 and ficha["codigo_infoobras"] == "202"
    assert len(ficha["valorizaciones"] if multi else info["valorizaciones"]) == 12
    # Repetir la consulta no borra la procedencia ni vuelve a la ficha inicial.
    _verificar(espejo, enr)
    assert info["obra_inicial"] == inicial
    llamadas = []

    def descargar(oid, destino):
        llamadas.append(oid)
        (destino / f"ficha-{oid}.pdf").write_bytes(b"%PDF-1.4 evidencia sintetica")

    descargar_documentos_job(espejo, enr, "identidad", tmp_path, descargar=descargar)
    descargar_documentos_job(espejo, enr, "identidad", tmp_path, descargar=descargar)
    assert llamadas == [202]
    assert info["descargas_reales"]["obra_id"] == 202
    base = carpeta_job(tmp_path, "identidad") / "descargas"
    ruta = construir_zip_infoobras(espejo, {(1, 1): base / "P1_E1"},
                                  tmp_path / "resultado.zip", enriquecimiento=enr)
    with zipfile.ZipFile(ruta) as zf:
        documentos = [n for n in zf.namelist() if n.endswith(".pdf")]
        assert len(documentos) == 1 and documentos[0].endswith("ficha-202.pdf")
        identidad = next(n for n in zf.namelist() if n.endswith("/IDENTIFICACION.txt"))
        texto = zf.read(identidad).decode("utf-8")
        assert "consultada para el contraste: 202" in texto
        assert "búsqueda inicial: 101" in texto
        assert "utilizada para solicitar documentos: 202" in texto


@pytest.mark.parametrize("marca_legada", [False, True])
@pytest.mark.parametrize("falla_nueva", [False, True])
@pytest.mark.parametrize("multi", [False, True])
def test_cambio_de_ficha_no_reutiliza_marca_ni_mezcla_documentos(
        tmp_path, marca_legada, falla_nueva, multi):
    espejo, enr, info = _caso(multi)
    llamadas = []
    intentos = set()

    def descargar(oid, destino):
        llamadas.append(oid)
        if falla_nueva and oid == 202:
            raise ConnectionError("fuente no disponible")
        (destino / f"ficha-{oid}.pdf").write_bytes(b"%PDF-1.4 evidencia sintetica")

    def correr():
        descargar_documentos_job(espejo, enr, "identidad", tmp_path,
            descargar=descargar, intentos_documentos=intentos,
            marcar_intento=intentos.add)

    correr()
    raiz = carpeta_job(tmp_path, "identidad")
    destino = raiz / "descargas" / "P1_E1"
    nombre_marca = "P1_E1_S1" if multi else "P1_E1"
    if multi:
        destino /= "Subobra 01"
    (destino / "BASES_INTEGRADAS.pdf").write_bytes(b"%PDF-1.4 seace independiente")
    if marca_legada:
        (raiz / "descargas" / f"{nombre_marca}.ok").write_text("ok", encoding="utf-8")
        (raiz / "fuentes_descarga" / f"{nombre_marca}.json").unlink(missing_ok=True)
    _verificar(espejo, enr)
    correr()
    correr()
    assert llamadas == [101, 202]
    assert not (destino / "ficha-101.pdf").exists()
    assert (destino / "BASES_INTEGRADAS.pdf").is_file()
    # Retiro recuperable fuera del árbol que se empaqueta, incluso ante fallo.
    assert len(list((raiz / "descargas_previas").rglob("ficha-101.pdf"))) == 1
    assert (destino / "ficha-202.pdf").exists() is not falla_nueva
    assert info["descargas_reales"]["completada"] is not falla_nueva
    assert info["descargas_reales"]["obra_id"] == 202
    if not falla_nueva:
        marca = json.loads((raiz / "descargas" / f"{nombre_marca}.ok").read_text())
        assert marca["obra_id"] == "202"


def test_expediente_solo_mef_no_arrastra_la_ficha_inicial(tmp_path):
    espejo, enr, info = _caso()
    espejo["_meta"]["tipo_evaluacion"] = "expedientes"
    info["via"] = "MEF"
    _verificar(espejo, enr, lambda *_: None)
    assert info["sin_registro_infoobras"] is True
    assert info["obra"]["obra_id"] is None
    assert info["obra_ficha"]["obra_id"] is None
    assert info["obra_inicial"]["obra_id"] == 101
    descargar_documentos_job(espejo, enr, "identidad", tmp_path,
                            descargar=lambda *_: pytest.fail("no descargar ficha descartada"))


def test_retirar_ficha_sin_fuente_nueva_no_deja_documentos_ni_conteo_viejo(tmp_path):
    espejo, enr, info = _caso()

    def descargar(_oid, destino):
        (destino / "anterior.pdf").write_bytes(b"%PDF-1.4 anterior")

    descargar_documentos_job(espejo, enr, "identidad", tmp_path, descargar=descargar)
    info["obra"] = None
    descargar_documentos_job(espejo, enr, "identidad", tmp_path, descargar=descargar)
    raiz = carpeta_job(tmp_path, "identidad")
    assert not (raiz / "descargas" / "P1_E1" / "anterior.pdf").exists()
    assert len(list((raiz / "descargas_previas").rglob("anterior.pdf"))) == 1
    assert info["descargas_reales"]["archivos"] == 0
    assert info["descargas_reales"]["obra_id"] is None


def test_consulta_fallida_no_inventa_una_ficha_final():
    espejo, enr, info = _caso()
    _verificar(espejo, enr, lambda *_: None)
    assert info["sin_verificar"] is True
    assert info["obra"]["obra_id"] == 101
    assert "obra_inicial" not in info
    assert "obra_ficha" not in info


def test_subobra_en_revision_no_se_promueve_ni_se_consulta():
    espejo, enr, info = _caso(multi=True)
    info["estado"] = "revision"
    _verificar(espejo, enr, lambda *_: pytest.fail("no consultar candidato pendiente"))
    assert info["estado"] == "revision"
    assert info["obra"]["obra_id"] == 101
    assert "ficha" not in info
