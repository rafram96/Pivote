"""Integración offline de T-004 F2: descarga diferida, ZIP y Excel."""
from __future__ import annotations

import zipfile

import openpyxl

from entregables import (construir_zip_infoobras, desempaquetar_enriquecimiento,
                          generar_excel_final)
from orquestador.etapas_reales import descargar_documentos_job
from orquestador.repositorio import carpeta_job
from schemas.cargo import etiqueta_hoja


ESPEJO = {
    "_meta": {"analisis_id": "seace-f2", "concurso": "CP-TEST", "postor": "P"},
    "postor": {},
    "profesionales": [{
        "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "N",
        "experiencias": [{
            "n": 1, "proyecto": "Supervisión del Hospital",
            "fecha_inicial": "2021-01-01", "fecha_final": "2022-01-01",
        }],
    }],
    "resumen_evaluacion": {"factores": []},
}


def _seace(*, ambiguo=False):
    return {
        "estado": "seleccionado",
        "cui": "2279396",
        "proceso_objeto": "supervision",
        "seleccion": "objeto",
        "ambiguo": ambiguo,
        "motivo": "único proceso de supervisión del CUI",
        "fecha_suscripcion": "2021-04-01",
        "docs": {
            "bases": {"estado": "disponible", "url": "https://estado/bases.pdf"},
            "contrato": {"estado": "disponible", "url": "https://estado/contrato.pdf"},
        },
    }


def _espejo_dos_experiencias():
    profesional = {**ESPEJO["profesionales"][0]}
    primera = {**profesional["experiencias"][0]}
    profesional["experiencias"] = [
        primera,
        {**primera, "n": 2, "proyecto": "Supervisión del segundo hospital"},
    ]
    return {**ESPEJO, "profesionales": [profesional]}


def test_descarga_seace_sin_obra_id_es_idempotente_y_entra_al_zip(tmp_path):
    enr = {"1:1": {"cui": "2279396", "via": "CUI_TEXTO", "seace": _seace()}}
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-1.4 prueba")
        return True

    descargar_documentos_job(
        ESPEJO, enr, "job-seace", tmp_path, descargar_seace=descargar)
    descargar_documentos_job(
        ESPEJO, enr, "job-seace", tmp_path, descargar_seace=descargar)

    base = carpeta_job(tmp_path, "job-seace") / "descargas"
    destino = base / "P1_E1"
    assert (destino / "SEACE_01_BASES_INTEGRADAS.pdf").read_bytes().startswith(b"%PDF")
    assert (destino / "SEACE_02_CONTRATO_FIRMADO.pdf").read_bytes().startswith(b"%PDF")
    assert (base / "P1_E1.seace.ok").exists()
    assert len(llamadas) == 2, "la segunda ejecución debe respetar la marca SEACE"

    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): destino}, tmp_path / "infoobras.zip", enriquecimiento=enr)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        # El fake devuelve bytes idénticos para ambos documentos: el ZIP guarda
        # el contenido una sola vez y el manifiesto conserva las dos identidades.
        assert any(n.endswith("SEACE_01_BASES_INTEGRADAS.pdf") for n in nombres)
        manifiesto = zf.read(next(n for n in nombres
                                  if n.endswith("MANIFIESTO_DOCUMENTOS.txt"))).decode("utf-8")
        assert "SEACE_01_BASES_INTEGRADAS.pdf" in manifiesto
        assert "SEACE_02_CONTRATO_FIRMADO.pdf" in manifiesto


def test_marca_infoobras_previa_no_salta_seace(tmp_path):
    enr = {"1:1": {
        "cui": "2279396", "via": "CUI_TEXTO",
        "obra": {"obra_id": 99}, "seace": _seace(),
    }}
    base = carpeta_job(tmp_path, "job-mixto") / "descargas"
    base.mkdir(parents=True)
    (base / "P1_E1.ok").write_text("ok", encoding="utf-8")
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF")
        return True

    descargar_documentos_job(
        ESPEJO, enr, "job-mixto", tmp_path,
        descargar=lambda *_: (_ for _ in ()).throw(AssertionError("InfoObras no debe repetirse")),
        descargar_seace=descargar)
    assert len(llamadas) == 2
    assert (base / "P1_E1.seace.ok").exists()


def test_descarga_seace_escribe_notas_honestas(tmp_path):
    enr = {"1:1": {
        "cui": "2279396", "via": "CUI_TEXTO",
        "seace": {
            "estado": "fuente_no_disponible",
            "motivo": "la fuente no respondió; reintentar",
        },
    }}
    descargar_documentos_job(ESPEJO, enr, "job-notas", tmp_path)
    destino = carpeta_job(tmp_path, "job-notas") / "descargas" / "P1_E1"
    notas = sorted(p.name for p in destino.glob("SEACE_*_ERROR.txt"))
    assert notas == [
        "SEACE_01_BASES_INTEGRADAS_ERROR.txt",
        "SEACE_02_CONTRATO_FIRMADO_ERROR.txt",
    ]
    assert "reintentar" in (destino / notas[0]).read_text(encoding="utf-8")


def test_seace_descarga_filecode_una_vez_para_dos_experiencias_y_jobs(tmp_path):
    espejo = _espejo_dos_experiencias()
    seace = _seace()
    seace["docs"]["bases"]["url"] = (
        "https://prod1.seace.gob.pe/x?fileCode=BASE-COMPARTIDA"
    )
    seace["docs"]["contrato"] = {"estado": "no_disponible", "url": None}
    enriquecimiento = {
        "1:1": {"cui": "1", "seace": seace},
        "1:2": {"cui": "1", "seace": seace},
    }
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-1.7\ncontenido compartido")
        return True

    descargar_documentos_job(
        espejo, enriquecimiento, "job-uno", tmp_path,
        descargar_seace=descargar,
    )
    descargar_documentos_job(
        ESPEJO, {"1:1": enriquecimiento["1:1"]}, "job-dos", tmp_path,
        descargar_seace=descargar,
    )

    assert len(llamadas) == 1
    entregables = [
        carpeta_job(tmp_path, "job-uno") / "descargas" / "P1_E1"
        / "SEACE_01_BASES_INTEGRADAS.pdf",
        carpeta_job(tmp_path, "job-uno") / "descargas" / "P1_E2"
        / "SEACE_01_BASES_INTEGRADAS.pdf",
        carpeta_job(tmp_path, "job-dos") / "descargas" / "P1_E1"
        / "SEACE_01_BASES_INTEGRADAS.pdf",
    ]
    assert all(ruta.is_file() for ruta in entregables)
    assert len({ruta.read_bytes() for ruta in entregables}) == 1


def test_excel_muestra_documentos_seace_y_ambiguedad(tmp_path):
    enr = {"1:1": {"cui": "2279396", "seace": _seace(ambiguo=True)}}
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(
        ESPEJO, tmp_path / "final.xlsx", paral, cuis, fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "JEFE DE SUPERVISIÓN")]
    celdas = [c for fila in ws.iter_rows() for c in fila if c.value is not None]
    texto = "\n".join(str(c.value) for c in celdas)
    assert "DOCUMENTOS DEL PROCESO (SEACE)" in texto
    assert "Bases Integradas" in texto
    assert "Contrato firmado" in texto
    aviso = next(c for c in celdas if str(c.value).startswith("Por confirmar"))
    assert (aviso.fill.fgColor.rgb or "").endswith("FFFF00")
