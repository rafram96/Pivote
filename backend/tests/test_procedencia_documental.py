"""Procedencia y ausencias sin causas inventadas; datos exclusivamente sintéticos."""
import copy
import json
import zipfile

import pytest

from entregables.certeza import identificacion_panel
from entregables.procedencia import procedencia_cui, rotulo_cui
from entregables.zip_infoobras import construir_zip_infoobras
from orquestador.descargas_seace import nota_seace_ausencia


@pytest.mark.parametrize("enr,utilizado", [
    ({}, None),
    ({"cui": "2222222", "via": "PROBABLE"}, "2222222"),
    ({"obra": {"cui": "3333333"}, "cui": "2222222"}, "3333333"),
    ({"verificacion_expediente": {"cui_confirmado": "4444444"}}, "4444444"),
])
def test_procedencia_no_confunde_declaracion_uso_y_certeza(enr, utilizado):
    exp = {"cui": "1111111"}
    copia = copy.deepcopy(enr)
    p = procedencia_cui(exp, enr)
    assert p["cui_declarado"] == "1111111"
    assert p["cui_utilizado"] == utilizado
    assert "confirmado" not in rotulo_cui(p)
    assert enr == copia


def test_codigo_sin_metodo_no_inventa_confirmacion_ni_dice_sin_cui():
    identidad = identificacion_panel({"cui": "1111111"}, {})
    assert identidad["nivel"] == "sin_identificar"
    assert "1111111" in identidad["detalle"]
    assert "Sin CUI" not in identidad["detalle"]


def test_multiobra_conserva_identidades_pendientes():
    p = procedencia_cui(None, {"via": "MULTI_OBRA", "sub_obras": [
        {"nombre": "Escuela A", "cui": "1111111", "estado": "resuelto"},
        {"nombre": "Escuela B", "estado": "revision"},
    ]})
    assert p["cui_utilizado"] is None
    assert [s["cui"] for s in p["sub_obras"]] == ["1111111", None]
    assert "Multi-obra" in rotulo_cui(p)


@pytest.mark.parametrize("estado", ["sin_tipo", "sin_procesos", "seleccionado", "sin_proceso", None])
def test_ausencia_seace_no_inventa_antiguedad_o_no_publicacion(estado):
    texto = nota_seace_ausencia(estado)
    assert "2018" not in texto
    assert "no figura publicado" not in texto
    assert "solo publica" not in texto
    assert "consulta" in texto


@pytest.mark.parametrize("con_pdf", [True, False])
@pytest.mark.parametrize("enr", [{}, {"cui": "2222222", "via": "PROBABLE"}])
def test_zip_conserva_procedencia_con_y_sin_documentos(tmp_path, monkeypatch, con_pdf, enr):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "txt,md,json")
    espejo = {"_meta": {"tipo_evaluacion": "expedientes"}, "profesionales": [
        {"n_prof": 1, "cargo": "Especialista", "experiencias": [
            {"n": 4, "proyecto": "Proyecto sintético", "cui": "1111111"}]}]}
    origen = tmp_path / "documentos"
    origen.mkdir()
    if con_pdf:
        (origen / "contrato.pdf").write_bytes(b"%PDF-1.4 sintetico")
    zip_path = construir_zip_infoobras(espejo, {(1, 4): origen}, tmp_path / "entrega.zip", {"1:4": enr})
    with zipfile.ZipFile(zip_path) as zf:
        registro = json.loads(zf.read("indice.json"))["experiencias"][0]
        assert registro["n_exp"] == 4
        assert registro["documentos"] == int(con_pdf)
        assert registro["notas"] == 0  # el resumen no es una descarga ni una nota de error
        assert registro["procedencia"]["cui_declarado"] == "1111111"
        assert registro["procedencia"]["cui_utilizado"] == enr.get("cui")
        assert registro["identificacion"]["nivel"] == ("inferido" if enr else "sin_identificar")
        nota = next(n for n in zf.namelist() if n.endswith("/IDENTIFICACION.txt"))
        for archivo in ["indice.txt", "indice.md", nota]:
            texto = zf.read(archivo).decode("utf-8")
            assert "CUI declarado: 1111111" in texto
            assert "CUI utilizado: " + (enr.get("cui") or "no registrado") in texto


def test_zip_sin_indice_y_sin_carpeta_no_oculta_cui_declarado(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "0")
    espejo = {"profesionales": [{"n_prof": 1, "experiencias": [{"n": 1, "cui": "1111111"}]}]}
    salida = construir_zip_infoobras(espejo, {}, tmp_path / "sin.zip")
    with zipfile.ZipFile(salida) as zf:
        texto = "\n".join(zf.read(n).decode("utf-8") for n in zf.namelist())
        assert "1111111" in texto
        assert "CUI utilizado: no registrado" in texto
        assert "resuelto" not in texto


def test_zip_actualiza_notas_historicas_sin_modificar_originales(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "txt")
    carpeta = tmp_path / "docs"
    carpeta.mkdir()
    nota = carpeta / "BASES_INTEGRADAS_NO_DISPONIBLE.txt"
    nota.write_text("esta contratación es anterior a 2018", encoding="utf-8")
    espejo = {"profesionales": [{"n_prof": 1, "experiencias": [{"n": 1}]}]}
    salida = construir_zip_infoobras(espejo, {(1, 1): carpeta}, tmp_path / "actual.zip", {
        "1:1": {"seace": {"estado": "sin_procesos"}, "descargas_reales": {
            "avisos": ["Bases Integradas (SEACE): no publicado por la fuente."]}}})
    with zipfile.ZipFile(salida) as zf:
        contenido = "\n".join(zf.read(n).decode("utf-8") for n in zf.namelist())
        assert "2018" not in contenido
        assert "no publicado por la fuente" not in contenido
    assert "2018" in nota.read_text(encoding="utf-8")
