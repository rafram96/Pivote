"""
Tests offline de los entregables: Excel final (CLAUDE + Base de Datos + hojas
por profesional con hitos) y ZIP InfoObras (árbol de 4 niveles).
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from entregables import construir_zip_infoobras, generar_excel_final, inventariar
from reglas import dias_efectivos_profesional

RAIZ = Path(__file__).resolve().parents[2]
FIXTURES = RAIZ / "fixtures"

# Espejo sintético: 2 profesionales; el prof 1 reusa el caso golden JEFE
# (certificado 2021-05-13→2023-05-06 con 3 ventanas de paralización).
ESPEJO = {
    "_meta": {"analisis_id": "t-entregables", "concurso": "CP-TEST/2026",
              "postor": "POSTOR DEMO"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "Profesional Uno",
         "colegiatura": "CIP 11111",
         "experiencias": [
             {"n": 1, "proyecto": "Obra A", "cui": "2418877",
              "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
              "dias": 724, "incluye_covid": "NO", "folio": "100"},
             {"n": 2, "proyecto": "Obra B",
              "fecha_inicial": "2023-11-22", "fecha_final": "2025-07-22",
              "dias": 609, "incluye_covid": "NO", "folio": "120"},
         ]},
        {"n_prof": 2, "cargo": "ESP. ESTRUCTURAS", "nombre": "Profesional Dos",
         "experiencias": [
             {"n": 1, "proyecto": "Obra C",
              "fecha_inicial": "POR VERIFICAR (ilegible)", "fecha_final": "2020-01-01"},
         ]},
    ],
    "resumen_evaluacion": {"factores": [], "puntaje_total": None},
}

PARALIZACIONES = {
    (1, 1): [(date(2021, 10, 1), date(2021, 10, 31)),
             (date(2022, 2, 1), date(2022, 4, 30)),
             (date(2022, 7, 1), date(2022, 9, 30))],
}


# ── Excel final ───────────────────────────────────────────────────────────────

def test_excel_final_estructura_de_hojas(tmp_path):
    salida = generar_excel_final(ESPEJO, tmp_path / "final.xlsx", PARALIZACIONES)
    wb = openpyxl.load_workbook(salida)
    assert wb.sheetnames[0] == "CLAUDE"
    assert wb.sheetnames[1] == "Base de Datos"
    assert wb.sheetnames[2].startswith("P1 ")
    assert wb.sheetnames[3].startswith("P2 ")


def test_excel_final_base_datos_con_filtro_y_colores(tmp_path):
    salida = generar_excel_final(ESPEJO, tmp_path / "final.xlsx", PARALIZACIONES)
    ws = openpyxl.load_workbook(salida)["Base de Datos"]
    assert ws.cell(1, 1).value == "CARGO AL QUE POSTULA"
    # 3 experiencias = 3 filas de datos
    assert ws.cell(2, 1).value == "JEFE DE SUPERVISIÓN"
    assert ws.cell(4, 1).value == "ESP. ESTRUCTURAS"
    assert ws.cell(5, 1).value is None
    assert ws.auto_filter.ref is not None        # con filtros
    # color de fondo distinto por profesional
    assert ws.cell(2, 1).fill.fgColor.rgb != ws.cell(4, 1).fill.fgColor.rgb


def test_excel_final_hoja_profesional_cuadro_de_hitos(tmp_path):
    salida = generar_excel_final(ESPEJO, tmp_path / "final.xlsx", PARALIZACIONES)
    ws = openpyxl.load_workbook(salida)["P1 JEFE DE SUPERVISIÓN"]
    celdas = [str(c.value) for fila in ws.iter_rows() for c in fila if c.value is not None]
    texto = "\n".join(celdas)

    # el cuadro de hitos existe, con periodo certificado, paralizaciones y tramos
    assert "CUADRO DE HITOS" in texto
    assert "Periodo certificado" in texto
    assert "Paralización 1 de la obra (InfoObras)" in texto
    assert "Tramo efectivo 1" in texto
    # los 4 tramos del golden JEFE: 141 + 92 + 61 + 218
    assert "EFECTIVO EXPERIENCIA 1" in texto
    valores = [c.value for fila in ws.iter_rows() for c in fila]
    for esperado in (141, 92, 61, 218, 512):
        assert esperado in valores, f"falta el valor {esperado} del golden"
    # resumen Paso 5 reconcilia con el motor de reglas
    res = dias_efectivos_profesional(
        [(date(2021, 5, 13), date(2023, 5, 6)), (date(2023, 11, 22), date(2025, 7, 22))],
        {0: PARALIZACIONES[(1, 1)]},
    )
    assert res.dias_efectivos in valores
    assert "DÍAS EFECTIVOS" in texto


def test_excel_final_fechas_no_computables_quedan_anotadas(tmp_path):
    salida = generar_excel_final(ESPEJO, tmp_path / "final.xlsx", PARALIZACIONES)
    ws = openpyxl.load_workbook(salida)["P2 ESP. ESTRUCTURAS"]
    texto = "\n".join(str(c.value) for fila in ws.iter_rows() for c in fila if c.value)
    assert "no computables" in texto


def test_excel_final_fixture_libertador(tmp_path):
    ruta = FIXTURES / "new_format" / "libertador_espejo.json"
    if not ruta.exists():
        pytest.skip("fixture local no disponible")
    import json
    espejo = json.loads(ruta.read_text(encoding="utf-8"))
    salida = generar_excel_final(espejo, tmp_path / "libertador_final.xlsx")
    wb = openpyxl.load_workbook(salida)
    # CLAUDE + Base de Datos + 14 hojas de profesional
    assert len(wb.sheetnames) == 2 + 14
    ws = wb["Base de Datos"]
    filas_datos = sum(1 for f in ws.iter_rows(min_row=2) if f[0].value is not None)
    assert filas_datos == 41  # 41 experiencias consolidadas


# ── ZIP InfoObras ─────────────────────────────────────────────────────────────

def test_zip_arbol_de_4_niveles_con_y_sin_documentos(tmp_path):
    # docs reales descargados por el prototipo (gitignored) si están; si no, sintéticos
    origen = RAIZ / "tools" / "_descargas_72056"
    if not origen.is_dir():
        origen = tmp_path / "docs"
        (origen / "Cronograma").mkdir(parents=True)
        (origen / "Cronograma" / "doc1.pdf").write_bytes(b"%PDF-1.4 demo")

    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): origen}, tmp_path / "infoobras.zip")

    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        raiz = "CP-TEST-2026"
        # nivel 1: proyecto · nivel 2: profesional · nivel 3: experiencia
        assert any(n.startswith(f"{raiz}/01 - JEFE DE SUPERVISIÓN/Exp 1 - Obra A/") for n in nombres)
        # la experiencia CON descargas trae archivos reales
        con_docs = [n for n in nombres if "/Exp 1 - Obra A/" in n and not n.endswith("/")]
        assert len(con_docs) >= 1
        # las experiencias SIN descargas llevan la nota, no desaparecen
        sin_docs = [n for n in nombres if n.endswith("SIN_DOCUMENTOS.txt")]
        assert len(sin_docs) == 2  # exp (1,2) y (2,1)
        contenido = zf.read(sin_docs[0]).decode("utf-8")
        assert "Motivo" in contenido
        # índice en la raíz
        assert f"{raiz}/indice.txt" in nombres
        indice = zf.read(f"{raiz}/indice.txt").decode("utf-8")
        assert "SIN DOCUMENTOS" in indice


# ── Inventario (parseo offline del HTML de InfoObras) ───────────────────────

HTML_INVENTARIO = """
<html><script>
var lAvances = [
  {"lImgValorizacion": [{"UrlImg": "Doc/documento1.pdf", "nombreArchivo": "valorizacion enero",
    "Extension": "pdf", "EsFisico": 0}],
   "lImgFisico": [{"UrlImg": "Img/foto1.jpg", "nombreArchivo": "avance fisico",
    "Extension": "jpg", "EsFisico": 1}]}
];
</script>
<body>
<button data-download-url="/InfobrasWeb/Mapa/DownloadFile?filename=expediente%2Fexp.pdf&amp;name=expediente%20tecnico&amp;extension=.pdf"></button>
</body></html>
"""


def test_inventariar_distingue_documentos_de_imagenes():
    inv = inventariar(HTML_INVENTARIO)
    docs = {d["filename"] for d in inv["documentos"]}
    imgs = {i["filename"] for i in inv["imagenes"]}
    assert "Doc/documento1.pdf" in docs
    assert "expediente/exp.pdf" in docs       # botón data-download-url
    assert "Img/foto1.jpg" in imgs            # imagen excluida de documentos
    # una imagen NUNCA se cuela como documento aunque fuera .pdf
    assert not docs & imgs
