"""Recorrido offline de identidad SEACE ambigua hasta el materializador."""

import json
import zipfile
from datetime import date
from types import SimpleNamespace

from entregables import construir_zip_infoobras
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal, descargar_documentos_job
from orquestador.repositorio import carpeta_job
from schemas import pipeline


def _obra():
    return SimpleNamespace(
        obra_id=101, codigo_infoobras="101", nombre="Obra sintética",
        fecha_inicio=date(2020, 1, 1), fecha_fin=date(2020, 12, 31),
        avances=[],
    )


def _proceso(ocid, inicio, titulo):
    return {
        "ocid": ocid,
        "date": inicio,
        "tender": {"title": titulo},
        "contracts": [{
            "id": f"contrato-{ocid}", "title": f"Contrato {ocid}",
            "period": {"startDate": inicio, "endDate": inicio[:4] + "-12-31"},
            "documents": [{"documentType": "contractSigned",
                            "title": "Contrato firmado", "url": f"https://x/{ocid}.pdf"}],
        }],
    }


def test_proceso_ambiguo_pasa_a_revision_y_no_descarga_seace_ni_filtra_por_fecha(tmp_path):
    espejo = {
        "_meta": {"analisis_id": "ambiguedad", "tipo_evaluacion": "obras"},
        "profesionales": [{"n_prof": 1, "cargo": "SUPERVISOR", "nombre": "Persona",
            "experiencias": [{"n": 1, "proyecto": "Obra sintética", "cui": "2000001",
                "fecha_inicial": "2020-03-01", "fecha_final": "2020-10-31"}]}],
    }
    info = {"cui": "2000001", "via": "CODIGO", "estado": "resuelto",
            "obra": {"obra_id": 101, "cui": "2000001", "nombre_obra": "Obra sintética"}}
    procesos = [
        _proceso("ocid-nuevo", "2022-01-01", "Supervisión de la obra sintética"),
        _proceso("ocid-viejo", "2019-01-01", "Supervisión de la obra sintética"),
    ]
    ctx = Contexto(job=pipeline.Job(job_id="ambiguedad", analisis_id="ambiguedad"),
                   espejo=espejo, enriquecimiento={"1:1": info})
    EtapaInfoObrasReal(
        fetcher=lambda *_: _obra(), consulta_ocds=lambda _: procesos,
        verificador_mef=lambda *_: None,
    ).correr(ctx)

    seace = ctx.enriquecimiento["1:1"]["seace"]
    assert seace["estado"] == "identidad_pendiente"
    assert seace["seleccion"] is None and seace["cui"] == "2000001"
    assert seace["motivo"] == (
        "identidad de contratación pendiente: 2 procesos de supervision; "
        "confirmar cuál corresponde al certificado"
    )
    assert [a["ocid"] for a in seace["alternativas"]] == ["ocid-nuevo", "ocid-viejo"]

    llamadas_seace = []
    descargar_documentos_job(
        espejo, ctx.enriquecimiento, "ambiguedad", tmp_path,
        descargar=lambda *_: None,
        descargar_seace=lambda *args, **kwargs: llamadas_seace.append(args),
    )
    assert llamadas_seace == []
    manifiesto = (carpeta_job(tmp_path, "ambiguedad") / "descargas" / "P1_E1"
                  / "Documentos SEACE" / "DOCUMENTOS_SEACE.json")
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert datos["estado_fuente"] == "identidad_pendiente"
    assert datos["motivo"] == seace["motivo"]

    zip_path = construir_zip_infoobras(
        espejo, {(1, 1): manifiesto.parent}, tmp_path / "resultado.zip",
        enriquecimiento=ctx.enriquecimiento,
    )
    with zipfile.ZipFile(zip_path) as archivo:
        nombres = archivo.namelist()
        texto = "\n".join(archivo.read(n).decode("utf-8", errors="replace")
                            for n in nombres if n.endswith(".txt"))
    assert seace["motivo"] in texto
    assert not any(n.endswith(".pdf") for n in nombres)
