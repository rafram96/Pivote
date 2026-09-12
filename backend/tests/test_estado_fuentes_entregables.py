"""Propagación offline de estados de fuente hacia API, ZIP y Excel."""
from __future__ import annotations

import io
import json
import zipfile

import openpyxl
import pytest

from entregables import generar_excel_final
from entregables.excel_final import _resumen_sunat_sin_emisor
from entregables.certeza import clasificar_identificacion
from entregables.estado_fuentes import proyectar_estado_fuentes
from entregables.procedencia import procedencia_cui
from entregables.zip_infoobras import construir_zip_infoobras


def _espejo(tipo="expedientes"):
    return {
        "_meta": {"analisis_id": "estado-fuentes-sintetico", "tipo_evaluacion": tipo, "concurso": "CP-SINTETICO/2026",
                  "postor": "POSTOR SINTETICO"},
        "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "ESPECIALISTA", "nombre": "Profesional Sintético",
                            "experiencias": [{"n": 1, "proyecto": "Proyecto privado",
                                               "cui": "1234567",
                                               "fecha_inicial": "2021-01-01",
                                               "fecha_final": "2021-12-31"}]}],
    }


def _enriquecimiento():
    return {"1:1": {
        "consultas_fuentes": {
            "mef_ficha": {"estado": "fuente_no_disponible", "motivo": "timeout"},
            "sunat_nombre": {"estado": "sin_resultados", "motivo": "cero coincidencias explícitas"},
            "sunat_ruc": {"estado": "fuente_no_disponible", "motivo": "detalle no disponible", "ruc": "20111111111"},
            "infoobras_busqueda": {"estado": "respuesta_no_reconocida", "motivo": "respuesta incompleta"},
        },
        "sunat": {"ruc": None, "via": "nombre", "naturaleza": "privada"},
        "descargas_reales": {"secciones": {
            "Documentos SEACE": {"documentos": [
                {"titulo": "Contrato descargado", "estado": "descargado", "leida": False},
            ]},
            "Documentos SEACE (bases)": {"documentos": [
                {"titulo": "Bases fallidas", "estado": "descarga_fallida", "leida": False},
            ]},
            "MEF resolución": {"documentos": [
                {"titulo": "Resolución leída", "estado": "descargado", "leida": True},
            ]},
        }},
    }}


def test_enlace_sin_manifiesto_no_equivale_a_descargado_ni_a_fallo():
    estado = proyectar_estado_fuentes({"seace": {"estado": "seleccionado", "documentos": [
        {"url": "https://fuente.invalid/contrato.pdf", "categoria": "contrato"}]}})
    assert estado["documentos"][0]["estado"] == "enlace_sin_descarga_registrada"
    assert estado["documentos"][0]["correspondencia"] == "por_confirmar"
    assert "fuente_no_disponible" not in str(estado)


def test_proyeccion_conserva_semantica_de_caida_vacio_descarga_y_lectura():
    estado = proyectar_estado_fuentes(_enriquecimiento()["1:1"])
    consultas = estado["consultas"]
    assert consultas["mef_ficha"]["estado"] == "fuente_no_disponible"
    assert consultas["sunat_nombre"]["estado"] == "sin_resultados"
    assert consultas["sunat_ruc"]["estado"] == "fuente_no_disponible"
    assert any("no demuestra inexistencia" in nota.lower() for nota in estado["notas"])
    docs = {d["documento"]: d for d in estado["documentos"]}
    assert docs["Contrato descargado"]["estado"] == "descargado"
    assert docs["Contrato descargado"]["correspondencia"] == "por_confirmar"
    assert docs["Bases fallidas"]["estado"] == "descarga_fallida"
    assert docs["Resolución leída"]["lectura"] == "texto_leido"


@pytest.mark.parametrize("tipo", ["expedientes", "obras"])
def test_api_expone_estado_fuentes_por_experiencia_sin_red(tmp_path, monkeypatch, tipo):
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PIVOTE_ETAPAS", "esqueleto")
    import api.app as modulo
    import importlib
    importlib.reload(modulo)
    from fastapi.testclient import TestClient

    with TestClient(modulo.app) as cliente:
        concurso = cliente.post("/api/pivote/concursos", json={
            "nomenclatura": "CP-SINTETICO/2026", "entidad": "Entidad sintética"})
        assert concurso.status_code == 201
        respuesta = cliente.post(
            "/api/pivote/analizar",
            data={"concurso_id": concurso.json()["concurso_id"]},
            files={"espejo": ("espejo.json", io.BytesIO(json.dumps(_espejo(tipo)).encode()), "application/json"),
                   "excel": ("entrada.xlsx", io.BytesIO(b"PK sintetico"), "application/octet-stream")})
        assert respuesta.status_code == 201
        job_id = respuesta.json()["job_id"]
        modulo.repo.guardar_enriquecimiento(job_id, _enriquecimiento())
        cuerpo = cliente.get(f"/api/pivote/jobs/{job_id}/espejo")
        assert cuerpo.status_code == 200
        estado = cuerpo.json()["profesionales"][0]["experiencias"][0]["estado_fuentes"]

    assert estado == proyectar_estado_fuentes(_enriquecimiento()["1:1"])
    assert estado["consultas"]["mef_ficha"]["estado"] == "fuente_no_disponible"
    assert estado["consultas"]["sunat_nombre"]["estado"] == "sin_resultados"
    assert estado["consultas"]["sunat_ruc"]["estado"] == "fuente_no_disponible"
    assert not any("público" in n.lower() and "privad" in n.lower() for n in estado["notas"])


@pytest.mark.parametrize("tipo", ["expedientes", "obras"])
def test_zip_conserva_estados_y_excel_omite_bloque_de_fuentes(tmp_path, monkeypatch, tipo):
    espejo, enr = _espejo(tipo), _enriquecimiento()
    origen = tmp_path / "descargas"
    origen.mkdir()
    (origen / "CONTRATO_SEACE.pdf").write_bytes(b"PDF sintetico")
    (origen / "BASES_SEACE_ERROR.txt").write_text("fallo sintetico", encoding="utf-8")
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "json")
    zip_path = construir_zip_infoobras(espejo, {(1, 1): origen}, tmp_path / "entrega.zip", enr)
    with zipfile.ZipFile(zip_path) as archivo:
        indice = json.loads(archivo.read("indice.json"))
        registro = indice["experiencias"][0]
        identificacion = next(n for n in archivo.namelist() if n.endswith("/IDENTIFICACION.txt"))
        texto_identidad = archivo.read(identificacion).decode("utf-8")
    assert registro["estado_fuentes"] == proyectar_estado_fuentes(enr["1:1"])
    assert registro["estado_fuentes"]["consultas"]["mef_ficha"]["estado"] == "fuente_no_disponible"
    assert any(d["estado"] == "descarga_fallida" for d in registro["estado_fuentes"]["documentos"])
    assert "no se pudo completar la consulta" in texto_identidad.lower()
    assert "verific" not in texto_identidad.lower() or "por confirmar" in texto_identidad.lower()

    salida = generar_excel_final(espejo, tmp_path / "final.xlsx",
                                 fichas={(1, 1): enr["1:1"]})
    libro = openpyxl.load_workbook(salida, read_only=True, data_only=True)
    hojas_profesionales = libro.worksheets[2:]
    filas = [[str(c.value) for c in fila if c.value]
             for hoja in hojas_profesionales for fila in hoja.iter_rows()]
    textos = [texto for fila in filas for texto in fila]
    libro.close()
    rotulos_bloque = (
        "Estado de fuentes y documentos",
        "InfoObras · búsqueda:", "InfoObras · ejecución:", "InfoObras · preparación:",
        "MEF · ficha 08-A:", "MEF · contratos:", "SUNAT · búsqueda por nombre:",
        "SUNAT · ficha RUC:",
    )
    # El bloque se materializaba como filas propias (la primera celda llevaba
    # el rótulo); no se prohíben observaciones SEACE legítimas dentro de una
    # fila de experiencia ya existente.
    filas_bloque = [fila for fila in filas if fila and fila[0].startswith(rotulos_bloque)]
    assert filas_bloque == []
    # La eliminación es solo de la banda de fuentes: la tarjeta conserva la
    # explicación de identidad que el evaluador necesita para cotejar el CUI.
    assert any("CUI declarado:" in t for t in textos)
    assert any("CUI utilizado:" in t for t in textos)


def test_privada_sin_ficha_ruc_no_se_vuelve_publica_ni_cambia_cui():
    exp = {"n": 1, "proyecto": "Proyecto privado", "cui": "1234567"}
    enr = {"via": "PRIVADA", "sunat": None}
    procedencia = procedencia_cui(exp, enr)
    identidad = clasificar_identificacion(exp, enr)
    assert identidad["nivel"] == "privada"
    assert procedencia["cui_declarado"] == "1234567"
    assert procedencia["cui_utilizado"] is None
    assert enr == {"via": "PRIVADA", "sunat": None}


def test_fuentes_ausentes_y_seace_ambiguo_no_se_convierten_en_fallo():
    desconocido = proyectar_estado_fuentes({
        "descargas_reales": {"secciones": {"Documentos SEACE": {"documentos": []}}},
    })
    assert desconocido["consultas"] == {}
    assert any("no registrados" in nota.lower() for nota in desconocido["notas"])
    assert not any("sin resultados" in nota.lower() for nota in desconocido["notas"])

    ambiguo = proyectar_estado_fuentes({
        "seace": {"estado": "identidad_pendiente"},
    })
    assert any("no quedó identificado" in nota.lower() for nota in ambiguo["notas"])
    assert any("no se elige" in nota.lower() for nota in ambiguo["notas"])
    assert not any("fuente no disponible" in nota.lower() for nota in ambiguo["notas"])


@pytest.mark.parametrize("estado,esperado", [
    ("con_resultados", "datos recibidos, emisor por identificar"),
    ("sin_resultados", "sin coincidencias"),
    ("fuente_no_disponible", "consulta no completada"),
    ("respuesta_no_reconocida", "respuesta no interpretable"),
    ("no_consultado", "no consultado"),
    ("no_registrado", "consulta sin detalle"),
])
def test_resumen_sunat_conserva_causa_sin_repetir_traza(estado, esperado):
    ficha = {"consultas_fuentes": {"sunat_nombre": {
        "estado": estado, "motivo": "detalle técnico extenso que no va en la tarjeta",
    }}}
    assert _resumen_sunat_sin_emisor(ficha) == f"SUNAT — nombre: {esperado}"
    assert ficha["consultas_fuentes"]["sunat_nombre"]["motivo"].startswith("detalle técnico")


def test_resumen_sunat_no_mezcla_busqueda_vacia_y_detalle_fallido():
    ficha = {"consultas_fuentes": {
        "sunat_nombre": {"estado": "sin_resultados"},
        "sunat_ruc": {"estado": "fuente_no_disponible"},
    }}
    assert _resumen_sunat_sin_emisor(ficha) == (
        "SUNAT — nombre: sin coincidencias; RUC: consulta no completada")
    assert _resumen_sunat_sin_emisor({}) == "Emisor por verificar; consulta SUNAT no registrada."
