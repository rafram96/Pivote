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


def test_excel_final_muestra_periodos_sin_valorizacion(tmp_path):
    # un periodo con tipo 'sin_valorizacion' (hueco) debe verse etiquetado como
    # "obra parada" en la hoja del profesional, no como "Paralización"
    paral = {(1, 1): [
        {"inicio": date(2021, 10, 1), "fin": date(2021, 10, 31), "tipo": "paralizado"},
        {"inicio": date(2022, 1, 1), "fin": date(2022, 3, 31), "tipo": "sin_valorizacion"},
    ]}
    salida = generar_excel_final(ESPEJO, tmp_path / "final.xlsx", paral)
    ws = openpyxl.load_workbook(salida)["P1 JEFE DE SUPERVISIÓN"]
    texto = "\n".join(str(c.value) for f in ws.iter_rows() for c in f if c.value)
    assert "Paralización 1 de la obra (InfoObras)" in texto
    assert "Sin valorización 1 — obra parada (InfoObras)" in texto


def test_excel_final_valorizaciones_resalta_solo_meses_del_certificado(tmp_path):
    # datos reales de la captura del ingeniero: Hospital Ernesto Guzman (CUI
    # 2198319, código 102951, finalizado). Certificado 01/05/19–31/10/19 → solo
    # las valorizaciones de may–oct 2019 deben quedar en amarillo.
    espejo = {
        "_meta": {"analisis_id": "v", "concurso": "CP-V/2026", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "experiencias": [{"n": 1, "proyecto": "Hospital Ernesto Guzman", "folio": "600",
                              "fecha_inicial": "2019-05-01", "fecha_final": "2019-10-31"}],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    fichas = {(1, 1): {
        "codigo_infoobras": "102951", "cui": "2198319", "estado": "Finalizado",
        "monto": 11131864.36, "fecha_inicio": "2019-03-25", "fecha_fin": "2019-07-23",
        "valorizaciones": [
            {"anio": 2020, "mes": 2, "estado": "En ejecución", "fisico_real": 1.0, "valorizado_real": 11131864.36},
            {"anio": 2019, "mes": 10, "estado": "En ejecución", "fisico_real": 0.5172, "valorizado_real": 4974255.19},
            {"anio": 2019, "mes": 5, "estado": "En ejecución", "fisico_real": 0.1564, "valorizado_real": 1738809.21},
            {"anio": 2019, "mes": 3, "estado": "En ejecución", "fisico_real": 0.0216, "valorizado_real": 240053.31},
        ],
    }}
    salida = generar_excel_final(espejo, tmp_path / "v.xlsx", fichas=fichas)
    ws = openpyxl.load_workbook(salida)["P1 JEFE"]

    color = {}
    for fila in ws.iter_rows():
        for c in fila:
            if c.value and " / " in str(c.value):
                color[str(c.value)] = (c.fill.fgColor.rgb or "")

    # may y oct 2019 → dentro del certificado → amarillo
    assert color["2019 / MAYO"].endswith("FFFF00")
    assert color["2019 / OCTUBRE"].endswith("FFFF00")
    # mar 2019 y feb 2020 → fuera → sin resaltar
    assert not color["2019 / MARZO"].endswith("FFFF00")
    assert not color["2020 / FEBRERO"].endswith("FFFF00")

    # la ficha de la obra (código, CUI, estado) aparece en la hoja
    texto = "\n".join(str(c.value) for f in ws.iter_rows() for c in f if c.value)
    assert "102951" in texto and "2198319" in texto and "Finalizado" in texto
    assert "VALORIZACIONES" in texto


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


HTML_POR_AVANCE = """
<html><script>
var lAvances = [
  {"Anio": "2025", "Mes": "FEBRERO",
   "lImgValorizacion": [{"UrlImg": "doc/val12.pdf", "nombreArchivo": "VALORIZACION DE OBRA Nº 0012",
     "Extension": "pdf", "EsFisico": 0}], "lImgFisico": []},
  {"Anio": "2025", "Mes": "ENERO",
   "lImgValorizacion": [{"UrlImg": "doc/val11.pdf", "nombreArchivo": "VALORIZACION Nº 0011",
     "Extension": "pdf", "EsFisico": 0}], "lImgFisico": []}
];
</script>
<body>
<button data-download-url="/InfobrasWeb/Mapa/DownloadFile?filename=expediente%2Fet.pdf&amp;name=expediente&amp;extension=.pdf"></button>
</body></html>
"""


def test_inventariar_por_avance_agrupa_por_hito():
    from entregables.zip_infoobras import inventariar_por_avance, _etiqueta_hito
    inv = inventariar_por_avance(HTML_POR_AVANCE)
    assert len(inv["avances"]) == 2
    feb = next(a for a in inv["avances"] if a["mes"] == "FEBRERO")
    assert feb["anio"] == 2025
    assert feb["documentos"][0]["nombre"] == "VALORIZACION DE OBRA Nº 0012"
    # carpeta del hito, ordenable cronológicamente
    assert _etiqueta_hito(2025, "FEBRERO") == "2025-02 FEBRERO"
    # el expediente es obra-level (no por avance)
    assert any(d["nombre"] == "expediente" for d in inv["obra"]["documentos"])
    assert all(not a_doc["filename"].startswith("expediente")
               for a in inv["avances"] for a_doc in a["documentos"])


def test_descargar_a_carpeta_prefija_nombre_con_fecha(tmp_path):
    """El documento de valorización se guarda con la fecha del hito prefijada en
    el nombre (para identificarlo aunque salga de su carpeta); el obra-level
    conserva su nombre. Sin red: session falsa con contenido fijo."""
    from entregables.zip_infoobras import _descargar_a_carpeta

    class _Resp:
        status_code = 200
        headers: dict = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def iter_content(self, chunk_size=1):
            yield b"%PDF-1.4 contenido de prueba"

    class _Sess:
        def get(self, url, params=None, timeout=None, stream=False):
            return _Resp()

    it = {"filename": "doc/val.pdf", "nombre": "documento20250911", "extension": "pdf"}
    ok = _descargar_a_carpeta(_Sess(), it, tmp_path, timeout=5,
                              prefijo_nombre="2025-09 SEPTIEMBRE · ")
    assert ok
    assert [p.name for p in tmp_path.iterdir()] == [
        "2025-09 SEPTIEMBRE · documento20250911.pdf"]

    # obra-level (sin prefijo) conserva su nombre tal cual
    ok2 = _descargar_a_carpeta(
        _Sess(), {"filename": "exp/et.pdf", "nombre": "expediente", "extension": "pdf"},
        tmp_path / "sec", timeout=5)
    assert ok2 and (tmp_path / "sec" / "expediente.pdf").exists()


def test_get_inventario_reintenta_503_pero_no_4xx(monkeypatch):
    """La página de inventario reintenta ante 503 transitorio y devuelve el HTML
    en el intento que responde 200; un 4xx es permanente (no reintenta)."""
    from entregables import zip_infoobras as z

    class _Resp:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text
        def raise_for_status(self):
            if self.status_code >= 400:
                raise z.requests.HTTPError(f"HTTP {self.status_code}")

    monkeypatch.setattr(z.time, "sleep", lambda *a: None)  # no esperar en el test

    estado = {"n": 0}
    class _Sess503:
        def get(self, url, params=None, timeout=None):
            estado["n"] += 1
            return _Resp(503) if estado["n"] == 1 else _Resp(200, "<html>ok</html>")
    assert z._get_inventario(_Sess503(), 72056, timeout=5, intentos=3) == "<html>ok</html>"
    assert estado["n"] == 2  # cayó la 1ra, respondió la 2da

    estado2 = {"n": 0}
    class _Sess404:
        def get(self, url, params=None, timeout=None):
            estado2["n"] += 1
            return _Resp(404)
    with pytest.raises(z.requests.HTTPError):
        z._get_inventario(_Sess404(), 1, timeout=5, intentos=3)
    assert estado2["n"] == 1  # un 4xx no se reintenta


def test_hoja_profesional_cuadro_emisor_sunat_alt04():
    """La hoja del profesional trae el cuadro EMISOR (SUNAT) al lado, y marca
    ALT04 cuando el certificado se emitió ANTES de la creación de la empresa."""
    import openpyxl
    from entregables.excel_final import construir_hoja_profesional

    ws = openpyxl.Workbook().active
    prof = {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
        {"n": 1, "proyecto": "Obra X", "fecha_inicial": "2019-06-01",
         "fecha_final": "2020-06-30", "fecha_emision": "2019-03-01",  # ANTES de creación
         "ruc_emisor": "20512345678"}]}
    fichas = {(1, 1): {"codigo_infoobras": "111", "cui": "2418877", "valorizaciones": []}}
    sunat = {(1, 1): {"ruc": "20512345678", "razon_social": "CONSORCIO X SAC",
                      "fecha_inscripcion": "2019-06-01", "estado": "ACTIVO"}}
    construir_hoja_profesional(ws, prof, {}, {}, fichas, {}, sunat)

    texto = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "EMISOR DEL CERTIFICADO (SUNAT)" in texto
    assert "CONSORCIO X SAC" in texto
    # creación 2019-06 > emisión 2019-03 → certificado emitido antes de existir la empresa
    assert "ALT04" in texto and "ANTES de" in texto and "creación" in texto


def test_hoja_profesional_emisor_sin_anomalia():
    """Emisor coherente (creado antes del inicio y de la emisión) → ALT04 en verde."""
    import openpyxl
    from entregables.excel_final import construir_hoja_profesional

    ws = openpyxl.Workbook().active
    prof = {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
        {"n": 1, "proyecto": "Obra Y", "fecha_inicial": "2020-01-01",
         "fecha_final": "2021-01-01", "fecha_emision": "2021-02-01",
         "ruc_emisor": "20512345678"}]}
    fichas = {(1, 1): {"cui": "2418877", "valorizaciones": []}}
    sunat = {(1, 1): {"ruc": "20512345678", "razon_social": "EMPRESA OK",
                      "fecha_inscripcion": "2010-05-10", "estado": "ACTIVO"}}
    construir_hoja_profesional(ws, prof, {}, {}, fichas, {}, sunat)
    texto = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "sin anomalía de antigüedad" in texto
