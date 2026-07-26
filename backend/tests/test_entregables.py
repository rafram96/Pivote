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
from schemas.cargo import etiqueta_hoja
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
    # Pestañas cortas: prefijo genérico fuera, cada palabra a la mitad, Title Case.
    # "Jefe" se conserva (jerarquía); "ESP." no (todos son especialistas).
    assert wb.sheetnames[2] == "P1. Jefe Superv"
    assert wb.sheetnames[3] == "P2. Estruc"


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
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "JEFE DE SUPERVISIÓN")]
    celdas = [str(c.value) for fila in ws.iter_rows() for c in fila if c.value is not None]
    texto = "\n".join(celdas)

    # el marco del certificado existe, con periodo certificado, paralizaciones y tramos
    assert "CERT. N°1" in texto and "DATOS DE LA EXPERIENCIA" in texto
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
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "JEFE DE SUPERVISIÓN")]
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
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "JEFE")]

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
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(2, "ESP. ESTRUCTURAS")]
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
        # carpeta corta "P{nn} {cargo}" / "E{n}" (nombres cortos para el límite 260
        # de Windows; el nivel del concurso se omite, va en el indice.txt)
        pref = "P01 SUPERVISIÓN/E1/"
        assert any(n.startswith(pref) for n in nombres)
        # la experiencia CON descargas trae archivos reales
        con_docs = [n for n in nombres if n.startswith(pref) and not n.endswith("/")]
        assert len(con_docs) >= 1
        # las experiencias SIN descargas llevan la nota, no desaparecen
        sin_docs = [n for n in nombres if n.endswith("SIN_DOCUMENTOS.txt")]
        assert len(sin_docs) == 2  # exp (1,2) y (2,1)
        contenido = zf.read(sin_docs[0]).decode("utf-8")
        assert "Motivo" in contenido
        # índice en la raíz del ZIP
        assert "indice.txt" in nombres
        indice = zf.read("indice.txt").decode("utf-8")
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
                      "fecha_inscripcion": "2010-05-10", "estado": "ACTIVO",
                      "condicion": "HABIDO", "tipo_contribuyente": "SOCIEDAD ANONIMA CERRADA",
                      "actividades_economicas": ["Principal - 7110 - ARQUITECTURA E INGENIERIA"],
                      "domicilio_fiscal": "AV X 123, LIMA"}}
    construir_hoja_profesional(ws, prof, {}, {}, fichas, {}, sunat)
    texto = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "sin anomalía de antigüedad" in texto
    # objeto social (CIIU) mostrado, con el prefijo "Principal -" limpiado
    assert "Objeto social" in texto and "7110" in texto and "ARQUITECTURA E INGENIERIA" in texto
    assert "Principal -" not in texto
    assert "HABIDO" in texto and "SOCIEDAD ANONIMA CERRADA" in texto


def test_hoja_profesional_representantes_e_historico_del_emisor():
    """Issue #30: el cuadro del emisor lista los representantes legales y responde
    —en el TÍTULO del campo— si estaba habido al emitir y durante la obra; el
    histórico va en un cuadro contiguo (R:U) y el representante de obra se corre
    a W:Z."""
    import openpyxl
    from entregables.excel_final import construir_hoja_profesional

    ws = openpyxl.Workbook().active
    prof = {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
        {"n": 1, "proyecto": "Obra Z", "fecha_inicial": "2021-05-13",
         "fecha_final": "2023-05-06", "fecha_emision": "2023-06-01",
         "ruc_emisor": "20512345678"}]}
    fichas = {(1, 1): {"cui": "2418877", "valorizaciones": [],
                       "representante_obra": {"contratistas": [
                           {"nombre_empresa": "EJECUTORA SAC", "ruc": "20111111111"}]}}}
    sunat = {(1, 1): {
        "ruc": "20512345678", "razon_social": "CONSTRUCTORA X SAC",
        "fecha_inscripcion": "2010-01-05", "estado": "ACTIVO", "condicion": "HABIDO",
        "representantes": [
            {"tipo_documento": "CE", "nro_documento": "001748034",
             "nombre": "ZHANG XIA", "cargo": "APODERADO", "fecha_desde": "2020-08-17"},
            {"tipo_documento": "CE", "nro_documento": "002143422",
             "nombre": "LI WENXUE", "cargo": "APODERADO", "fecha_desde": "2020-12-09"}],
        "historico": {"razones_sociales": [
            {"nombre": "CONSTRUCTORA X EIRL", "fecha_baja": "2016-05-04"}],
            "domicilios": [{"direccion": "JR. AREQUIPA 55", "fecha_baja": "2016-05-04"}]},
        "habido": {
            "emision": {"fecha": "2023-06-01", "condicion": "HABIDO", "ok": True},
            "periodo": {"desde": "2021-05-13", "hasta": "2023-05-06",
                        "tramos": [
                            {"condicion": "HABIDO", "desde": "2021-05-13", "hasta": "2022-06-30"},
                            {"condicion": "NO HABIDO", "desde": "2022-07-01", "hasta": "2022-09-30"}],
                        "tramos_no_habido": [
                            {"condicion": "NO HABIDO", "desde": "2022-07-01", "hasta": "2022-09-30"}],
                        "ok": False}}}}
    construir_hoja_profesional(ws, prof, {}, {}, fichas, {}, sunat)

    celdas = {c.coordinate: str(c.value) for row in ws.iter_rows() for c in row if c.value}
    texto = "\n".join(celdas.values())

    # representantes: todos, con cargo y fecha desde — y SIN cruce con el firmante
    assert "Representantes legales (SUNAT)" in texto
    assert "ZHANG XIA" in texto and "LI WENXUE" in texto
    assert "APODERADO" in texto and "17/08/20" in texto
    assert "ALT12" not in texto and "firmante" not in texto

    # la pregunta va en el TÍTULO del campo, no solo en el valor
    assert any(v.startswith("¿Estaba habido al emitir el certificado?")
               for v in celdas.values())
    assert any(v.startswith("¿Estuvo habido durante la obra?") for v in celdas.values())
    assert "NO — NO HABIDO 01/07/22–30/09/22" in texto

    # cuadro histórico contiguo: arranca en R (col 18), en la misma fila que el emisor
    emisor = next(k for k, v in celdas.items() if v == "EMISOR DEL CERTIFICADO (SUNAT)")
    hist = next(k for k, v in celdas.items() if v == "HISTÓRICO SUNAT DEL EMISOR")
    assert emisor[0] == "M" and hist[0] == "R"
    assert emisor[1:] == hist[1:], "los dos cuadros del emisor arrancan en la misma fila"
    assert "CONSTRUCTORA X EIRL" in texto and "JR. AREQUIPA 55" in texto

    # el representante de obra (InfoObras) se corrió a W:Z
    rep_obra = next(k for k, v in celdas.items() if v == "REPRESENTANTE DE OBRA (InfoObras)")
    assert rep_obra[0] == "W"


def test_hoja_profesional_sin_historico_no_dibuja_el_cuadro():
    """Emisor sin información histórica: no se dibuja el cuadro contiguo (queda
    'no verificable' en el campo del emisor) y no se rompe nada."""
    import openpyxl
    from entregables.excel_final import construir_hoja_profesional

    ws = openpyxl.Workbook().active
    prof = {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
        {"n": 1, "proyecto": "Obra W", "fecha_inicial": "2020-01-01",
         "fecha_final": "2021-01-01", "ruc_emisor": "20512345678"}]}
    sunat = {(1, 1): {"ruc": "20512345678", "razon_social": "EMPRESA OK",
                      "fecha_inscripcion": "2010-05-10", "estado": "ACTIVO",
                      "condicion": "HABIDO", "representantes": [], "historico": None,
                      "habido": None}}
    construir_hoja_profesional(ws, prof, {}, {}, {(1, 1): {"valorizaciones": []}}, {}, sunat)

    texto = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "HISTÓRICO SUNAT DEL EMISOR" not in texto
    assert "Representantes legales" not in texto
    assert "¿Estaba habido al emitir y durante la obra?" in texto
    assert "Sin información histórica en SUNAT" in texto


# ── Hoja CLAUDE: formato de Manuel (blanco + verde/rojo semántico) ─────────────

def test_clasificar_veredicto_polaridad():
    """Verde/rojo según polaridad: en campos donde "SÍ" es malo (¿anterior a
    colegiatura?, ¿antes de culminar?) el SÍ debe salir ROJO, no verde."""
    from scripts.generar_excel import _fill_veredicto

    def color(v, pol):
        f = _fill_veredicto(v, pol)
        return None if f is None else f.fgColor.rgb[-6:]

    assert color("SÍ", "pos") == "C6EFCE"          # verde
    assert color("NO", "pos") == "FFC7CE"          # rojo
    assert color("SÍ", "neg") == "FFC7CE"          # SÍ malo → rojo
    assert color("NO", "neg") == "C6EFCE"          # NO bueno → verde
    assert color("CUMPLE", "pos") == "C6EFCE"
    assert color("NO CUMPLE", "pos") == "FFC7CE"
    assert color("POR VERIFICAR (x)", "pos") == "FFF2CC"   # amarillo
    assert color("NO APLICA", "pos") == "FFF2CC"
    assert color("texto libre", "pos") is None     # sin color
    assert color("", "pos") is None


def test_hoja_claude_blanca_con_veredictos(tmp_path):
    """La hoja CLAUDE es blanca dominante con verde/rojo SOLO en veredictos."""
    espejo = {
        "_meta": {"analisis_id": "t", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "ESP", "nombre": "N", "profesion_valida": "SÍ",
            "cumple": "CUMPLE — 5 años efectivos",
            "experiencias": [{
                "n": 1, "proyecto": "Obra", "fecha_inicial": "2020-01-01",
                "fecha_final": "2021-01-01", "cargo_valido_emitir": "SÍ",
                "anterior_colegiatura": "SÍ", "cert_antes_culminar": "NO",
                "dias": 367, "folio": "1",
            }],
        }],
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    }
    salida = generar_excel_final(espejo, tmp_path / "f.xlsx", {})
    ws = openpyxl.load_workbook(salida)["CLAUDE"]
    from collections import Counter
    fills = Counter(c.fill.fgColor.rgb[-6:] if (c.fill and c.fill.patternType) else None
                    for row in ws.iter_rows() for c in row)
    # blanco dominante; verde y rojo presentes (veredictos)
    assert fills[None] > sum(v for k, v in fills.items() if k)
    assert fills["C6EFCE"] >= 2     # ¿profesión? + ¿válido emitir? + ¿cumple? → verde
    assert fills["FFC7CE"] >= 1     # ¿anterior a colegiatura? SÍ → rojo
    # ya NO se usa el amarillo de "llenado por Claude" en cada celda
    assert "Verde = cumple" in "\n".join(
        str(c.value) for row in ws.iter_rows() for c in row if c.value)


def test_excel_final_requisitos_lista_no_crashea(tmp_path):
    """Regresión: `requisitos.*` puede llegar como lista (el espejo permite
    record(any)); openpyxl no escribe listas en celdas. El generador coerce
    list/dict→string en vez de reventar (bloque del TDR por profesional, mejora A)."""
    espejo = {
        "_meta": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "Esp", "nombre": "JUAN", "colegiatura": "CIP1",
            "requisitos": {
                "cargos_validos": ["Residente de obra", "Jefe de obra", "Supervisor de obra"],
                "tipo_experiencia_valida": "5 años",
                "tipo_obra_valida": ["Hospital II-1", "Hospital II-2"],  # LISTA → antes crasheaba
            },
            "experiencias": [{"n": 1, "proyecto": "H", "fecha_inicial": "2019-01-01",
                              "fecha_final": "2020-01-01", "entidad_emisora": "GR",
                              "cargo_ocupado": "Sup"}],
        }],
        "resumen_evaluacion": {"factores": []}, "postor": {},
    }
    salida = generar_excel_final(espejo, tmp_path / "lista.xlsx")   # NO debe crashear
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))
    rows = {str(row[0].value or ""): row[1].value for row in ws.iter_rows(min_col=1, max_col=2)}
    cargos = next((rows[k] for k in rows if "CARGOS VÁLIDOS" in k), None)
    assert cargos == "Residente de obra; Jefe de obra; Supervisor de obra"


def test_excel_final_parte1_usa_documento_o_descripcion(tmp_path):
    """PARTE 1, columna DESCRIPCIÓN. El contrato admite DOS claves: `documento`
    (formato vigente, lo que emite la skill hoy) y `descripcion` (formato
    Trujillo). El render leía solo `descripcion` → la columna salía VACÍA en
    todos los espejos nuevos (medido: 371/371 formularios reales usan
    `documento`)."""
    espejo = {**ESPEJO, "postor": {**ESPEJO.get("postor", {}), "formularios": [
        {"anexo": "ANEXO N° 01", "documento": "Declaración Jurada del Postor",
         "observacion": "Presenta", "folio": 5},
        {"anexo": "ANEXO N° 02", "descripcion": "Pacto de Integridad (Trujillo)",
         "observacion": "Presenta", "folio": 8},
    ]}}
    salida = generar_excel_final(espejo, tmp_path / "p1.xlsx")
    ws = openpyxl.load_workbook(salida)["CLAUDE"]
    textos = [[str(c.value or "") for c in fila] for fila in ws.iter_rows(max_row=40)]
    fila1 = next(f for f in textos if f and f[0] == "ANEXO N° 01")
    fila2 = next(f for f in textos if f and f[0] == "ANEXO N° 02")
    assert fila1[1] == "Declaración Jurada del Postor"      # clave nueva
    assert fila2[1] == "Pacto de Integridad (Trujillo)"     # clave legacy sigue viva
