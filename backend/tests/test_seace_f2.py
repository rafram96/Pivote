"""Integración offline de T-004 F2: descarga diferida, ZIP y Excel."""
from __future__ import annotations

import json
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
    assert (destino / "BASES_INTEGRADAS.pdf").read_bytes().startswith(b"%PDF")
    assert (destino / "CONTRATO_FIRMADO.pdf").read_bytes().startswith(b"%PDF")
    assert (base / "P1_E1.seace.ok").exists()
    assert len(llamadas) == 2, "la segunda ejecución debe respetar la marca SEACE"

    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): destino}, tmp_path / "infoobras.zip", enriquecimiento=enr)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        # El árbol conserva ambos documentos aunque tengan bytes idénticos.
        assert any(n.endswith("BASES_INTEGRADAS.pdf") for n in nombres)
        manifiesto = zf.read(next(n for n in nombres
                                  if n.endswith("MANIFIESTO_DOCUMENTOS.txt"))).decode("utf-8")
        assert "BASES_INTEGRADAS.pdf" in manifiesto
        assert "CONTRATO_FIRMADO.pdf" in manifiesto


def test_infoobras_descarga_una_vez_y_materializa_tres_profesionales(tmp_path):
    profesionales = []
    enriquecimiento = {}
    for n_prof in (8, 9, 11):
        profesionales.append({
            "n_prof": n_prof,
            "cargo": f"ESPECIALISTA {n_prof}",
            "nombre": "PEDRO SÁNCHEZ MEZA",
            "experiencias": [{
                "n": 1, "proyecto": "Hospital compartido",
                "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31",
            }],
        })
        enriquecimiento[f"{n_prof}:1"] = {
            "cui": "1", "obra": {"obra_id": 72056},
        }
    espejo = {**ESPEJO, "profesionales": profesionales}
    llamadas = []

    def descargar(obra_id, destino):
        llamadas.append(obra_id)
        (destino / "Valorizaciones/2020-01 ENERO").mkdir(parents=True)
        (destino / "Valorizaciones/2020-01 ENERO/val.pdf").write_bytes(
            b"%PDF compartido"
        )

    descargar_documentos_job(
        espejo, enriquecimiento, "job-tres-profesionales", tmp_path,
        descargar=descargar,
    )

    base = carpeta_job(tmp_path, "job-tres-profesionales") / "descargas"
    assert llamadas == [72056]
    for n_prof in (8, 9, 11):
        assert (base / f"P{n_prof}_E1.ok").is_file()
        assert (base / f"P{n_prof}_E1/Valorizaciones/2020-01 ENERO/val.pdf").is_file()


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
    carpeta = destino / "Documentos SEACE"
    texto = (carpeta / "DOCUMENTOS_SEACE.txt").read_text(encoding="utf-8")
    assert "no fue posible obtener" in texto
    assert "Estado de fuente: fuente_no_disponible" in texto
    manifiesto = json.loads((carpeta / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))
    assert manifiesto["documentos"] == []
    assert not list(carpeta.glob("*.pdf"))


def test_notas_seace_hablan_en_frases_de_evaluador(tmp_path):
    """Las notas dicen qué pasó sin convertir el fallo en tarea de descarga."""
    casos = {
        "sin_tipo": ("Entre los procesos recuperados en esta consulta al SEACE, ninguno "
                     "correspondió al tipo de experiencia buscado. No se obtuvo este documento.",
                     "NO_DISPONIBLE"),
        "sin_procesos": ("La consulta al SEACE no recuperó procesos asociados a esta experiencia. "
                         "Este resultado no determina la causa ni demuestra que el documento no exista.", "NO_DISPONIBLE"),
        "fuente_no_disponible": ("La consulta a los datos abiertos del SEACE no "
                                 "respondió en esta corrida, así que no fue posible "
                                 "obtener este documento.",
                                 "ERROR"),
    }
    for estado, (texto, sufijo) in casos.items():
        enr = {"1:1": {"cui": "2279396", "via": "CUI_TEXTO",
                       "seace": {"estado": estado,
                                 "motivo": "detalle técnico que no va a la nota"}}}
        descargar_documentos_job(ESPEJO, enr, f"job-{estado}", tmp_path)
        destino = carpeta_job(tmp_path, f"job-{estado}") / "descargas" / "P1_E1"
        carpeta = destino / "Documentos SEACE"
        nota = (carpeta / "DOCUMENTOS_SEACE.txt").read_text(encoding="utf-8")
        assert texto in nota
        assert f"Estado de fuente: {estado}" in nota
        assert json.loads((carpeta / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))["documentos"] == []
        assert not list(carpeta.glob("*.pdf"))


def test_nota_seace_de_descarga_fallida_es_terminal(tmp_path):
    enr = {"1:1": {"cui": "2279396", "via": "CUI_TEXTO", "seace": _seace()}}
    descargar_documentos_job(ESPEJO, enr, "job-falla", tmp_path,
                             descargar_seace=lambda _url, _destino: False)
    destino = carpeta_job(tmp_path, "job-falla") / "descargas" / "P1_E1"
    assert (destino / "BASES_INTEGRADAS_ERROR.txt").read_text(encoding="utf-8") == (
        "Se encontró un enlace para este documento, pero no se pudo obtener "
        "un archivo utilizable en esta corrida.\n")


def test_notas_seace_llegan_al_zip_con_el_nombre_completo(tmp_path):
    # Sin el prefijo `SEACE_0…` el nombre cabe en el recorte de 38 por
    # componente del ZIP: antes salía `SEACE_01_BASES_INTEGRADAS_N~2c5e00.txt`
    # y no se distinguía «no publicado» de «error de la fuente».
    enr = {"1:1": {
        "cui": "2279396", "via": "CUI_TEXTO",
        "seace": {"estado": "sin_proceso",
                  "motivo": "el CUI no tiene procesos publicados"},
    }}
    descargar_documentos_job(ESPEJO, enr, "job-nombres", tmp_path)
    destino = carpeta_job(tmp_path, "job-nombres") / "descargas" / "P1_E1"
    carpeta = destino / "Documentos SEACE"
    assert (carpeta / "DOCUMENTOS_SEACE.txt").is_file()
    texto = (carpeta / "DOCUMENTOS_SEACE.txt").read_text(encoding="utf-8")
    assert "Estado de fuente: sin_proceso" in texto
    assert not list(carpeta.glob("*.pdf"))

    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): destino}, tmp_path / "notas.zip", enriquecimiento=enr)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert any(n.endswith("/Documentos SEACE/DOCUMENTOS_SEACE.txt") for n in nombres)
        assert any(n.endswith("/Documentos SEACE/DOCUMENTOS_SEACE.json") for n in nombres)
        # una nota no es un documento: la experiencia sigue SIN DOCUMENTOS
        indice = zf.read("indice.txt").decode("utf-8")
        assert "SIN DOCUMENTOS" in indice
        # El índice cuenta la sección, no inventa documentos a partir de notas.
        assert "SECCIÓN Documentos SEACE: sin documentos" in indice
        assert "BASES_INTEGRADAS_NO_DISPONIBLE" not in indice


def test_nombres_seace_historicos_siguen_reconociendose(tmp_path):
    # Jobs ya descargados tienen `SEACE_01_…`: su ZIP debe seguir saliendo bien
    # (documento = documento, nota = nota) aunque el generador ya no los use.
    destino = tmp_path / "P1_E1"
    destino.mkdir()
    (destino / "SEACE_01_BASES_INTEGRADAS.pdf").write_bytes(b"%PDF viejo")
    (destino / "SEACE_02_CONTRATO_FIRMADO_ERROR.txt").write_text("falló\n",
                                                                 encoding="utf-8")
    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): destino}, tmp_path / "viejo.zip",
        enriquecimiento={"1:1": {"cui": "2279396"}})
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert any(n.endswith("/SEACE_01_BASES_INTEGRADAS.pdf") for n in nombres)
        assert any(n.endswith("/SEACE_02_CONTRATO_FIRMADO_ERROR.txt") for n in nombres)
        # 1 documento real + 1 nota (la nota no infla el conteo)
        indice = zf.read("indice.txt").decode("utf-8")
        assert "1 documento(s) + 1 nota(s)" in indice


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
        / "BASES_INTEGRADAS.pdf",
        carpeta_job(tmp_path, "job-uno") / "descargas" / "P1_E2"
        / "BASES_INTEGRADAS.pdf",
        carpeta_job(tmp_path, "job-dos") / "descargas" / "P1_E1"
        / "BASES_INTEGRADAS.pdf",
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
    assert "Bases integradas" in texto
    assert "Adjuntos del contrato" in texto
    assert "Contenido de los documentos" not in texto
    assert "SERVICIO ESPERADO (concurso)" not in texto
    assert "SERVICIO DECLARADO (certificado)" not in texto
    assert "CONTRASTE DE SERVICIO" not in texto
    aviso = next(c for c in celdas if str(c.value).startswith("Por confirmar"))
    # Amarillo SUAVE: es «por verificar», no un dato del certificado. El amarillo
    # fuerte (FFFF00) quedó reservado para lo que la leyenda de la hoja promete.
    assert (aviso.fill.fgColor.rgb or "").endswith("FFF2CC")
