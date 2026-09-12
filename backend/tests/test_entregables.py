"""
Tests offline de los entregables: Excel final (CLAUDE + Base de Datos + hojas
por profesional con hitos) y ZIP InfoObras (árbol de 4 niveles).
"""
from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path

import openpyxl
import pytest

from entregables import construir_zip_infoobras, generar_excel_final, inventariar
from entregables.zip_infoobras import _carpeta_experiencia
from scripts.generar_excel import generar_excel
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

def test_zip_nombre_corto_seguro_sin_cambiar_claves_ni_evidencia(tmp_path):
    import copy
    espejo = copy.deepcopy(ESPEJO)
    exps = espejo["profesionales"][0]["experiencias"]
    exps[0]["proyecto"] = 'Proyecto "sintético" / prueba: ' + "nombre largo " * 30
    exps[1]["proyecto"] = exps[0]["proyecto"]
    # E1 sigue primero en el escaneado, aunque E2 sea más antigua.
    exps[0]["fecha_inicial"], exps[1]["fecha_inicial"] = "2024-01-01", "2020-01-01"
    copia = copy.deepcopy(espejo)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "prueba.pdf").write_bytes(b"evidencia E1")
    (b / "prueba.pdf").write_bytes(b"evidencia E2")
    salida = construir_zip_infoobras(espejo, {(1, 1): a, (1, 2): b}, tmp_path / "nombre.zip")
    with zipfile.ZipFile(salida) as zf:
        for n in (1, 2):
            carpeta = _carpeta_experiencia(n, exps[n - 1]["proyecto"])
            assert carpeta.startswith(f"E{n} Proyecto ")
            assert len(carpeta) <= 40
            assert not any(c in carpeta for c in '<>:"/\\|?*')
            assert zf.read(f"P01 SUPERVISIÓN/{carpeta}/prueba.pdf") == f"evidencia E{n}".encode()
    assert espejo == copia
    assert _carpeta_experiencia(3, None) == "E3 (sin nombre)"
    assert not _carpeta_experiencia(4, "... \n").endswith((".", " "))


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
        # carpeta corta "P{nn} {cargo}" / "E{n} {proyecto}" (límite 260
        # de Windows; el nivel del concurso se omite, va en el indice.txt)
        pref = "P01 SUPERVISIÓN/E1 Obra A/"
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


def test_zip_carpeta_vacia_deja_nota_y_fallos_en_indice(tmp_path):
    vacia = tmp_path / "vacia"
    vacia.mkdir()
    enr = {
        "1:1": {
            "cui": "2418877",
            "descargas_reales": {
                "archivos": 0,
                "secciones": {
                    "InfoObras": {"estado": "error", "esperados": 3, "descargados": 0},
                    "Datos de cierre": {"estado": "sin_documentos", "esperados": 0,
                                         "descargados": 0},
                },
                "avisos": ["InfoObras: no se descargó ninguno de los 3 documentos disponibles."],
            },
        },
    }
    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): vacia}, tmp_path / "vacia.zip", enriquecimiento=enr,
    )

    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert any(n.startswith("P01 SUPERVISIÓN/E1 Obra A/")
                   and n.endswith("SIN_DOCUMENTOS.txt") for n in nombres)
        indice = zf.read("indice.txt").decode("utf-8")
        assert "SECCIÓN InfoObras: consulta fallida (0/3 descargados)" in indice
        assert "SECCIÓN Datos de cierre: sin documentos recuperados en la consulta (0 disponibles)" in indice
        assert "ADVERTENCIA: InfoObras" in indice


def test_zip_arbol_completo_por_experiencia_con_manifiestos(tmp_path):
    # Correctivo issue #80: la deduplicación va en la DESCARGA, no en la
    # entrega. Cada P/E conserva sus PDF reales navegables; el manifiesto
    # deja la huella SHA-256 y el índice explica qué se comparte.
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "original-a.pdf").write_bytes(b"%PDF-1.4 misma evidencia")
    (b / "otro-nombre.pdf").write_bytes(b"%PDF-1.4 misma evidencia")

    enriquecimiento = {
        "1:1": {"obra": {"obra_id": 72056}},
        "1:2": {"obra": {"obra_id": 72056}},
    }
    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): a, (1, 2): b}, tmp_path / "arbol.zip",
        enriquecimiento=enriquecimiento)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        # cero almacén central: los PDF viven dentro de cada experiencia
        assert not any(n.startswith("DOCUMENTOS_COMPARTIDOS/") for n in nombres)
        assert "P01 SUPERVISIÓN/E1 Obra A/original-a.pdf" in nombres
        assert "P01 SUPERVISIÓN/E2 Obra B/otro-nombre.pdf" in nombres
        manifests = [n for n in nombres if n.endswith("MANIFIESTO_DOCUMENTOS.txt")]
        assert len(manifests) == 2
        huellas = [zf.read(m).decode("utf-8") for m in manifests]
        # mismo contenido → misma huella SHA-256 en ambos manifiestos
        sha_a = [l for l in huellas[0].splitlines() if "original-a.pdf ->" in l]
        sha_b = [l for l in huellas[1].splitlines() if "otro-nombre.pdf ->" in l]
        assert sha_a and sha_b
        assert sha_a[0].split("-> ")[1] == sha_b[0].split("-> ")[1]
        indice = zf.read("indice.txt").decode("utf-8")
        # la primera aparición no anuncia compartidos; la segunda sí lo explica
        assert "1 compartido(s) con otras experiencias de esta obra" in indice
        assert "0 propio(s) del periodo" in indice
        assert "+ 0 nota" not in indice


def test_zip_sin_manifiestos_cuando_la_variable_esta_en_cero(tmp_path, monkeypatch):
    # El manifiesto es un documento TÉCNICO; el entregable lo consume un equipo
    # de evaluación no técnico. Con PIVOTE_MANIFIESTOS_ZIP=0 no se escribe ni se
    # anuncia en el índice, pero los PDF y los conteos quedan intactos (el
    # SHA-256 se sigue calculando: el índice depende de él).
    monkeypatch.setenv("PIVOTE_MANIFIESTOS_ZIP", "0")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "original-a.pdf").write_bytes(b"%PDF-1.4 misma evidencia")
    (b / "otro-nombre.pdf").write_bytes(b"%PDF-1.4 misma evidencia")

    enriquecimiento = {
        "1:1": {"obra": {"obra_id": 72056}},
        "1:2": {"obra": {"obra_id": 72056}},
    }
    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): a, (1, 2): b}, tmp_path / "sin-manifiestos.zip",
        enriquecimiento=enriquecimiento)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert not any(n.endswith("MANIFIESTO_DOCUMENTOS.txt") for n in nombres)
        # los documentos del evaluador siguen ahí, en su árbol por experiencia
        assert "P01 SUPERVISIÓN/E1 Obra A/original-a.pdf" in nombres
        assert "P01 SUPERVISIÓN/E2 Obra B/otro-nombre.pdf" in nombres
        indice = zf.read("indice.txt").decode("utf-8")
        assert "MANIFIESTO_DOCUMENTOS.txt" not in indice
        assert "huella SHA-256" not in indice
        # conteos del índice sin cambios (siguen calculándose con el SHA-256)
        assert "1 compartido(s) con otras experiencias de esta obra" in indice
        assert "0 propio(s) del periodo" in indice


# ── Formatos del índice (PIVOTE_INDICE_ZIP) ─────────────────────────────────

# Proyecto de nombre real (>70 chars): el txt lo recorta, el md no.
PROYECTO_LARGO = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE "
                  "SALUD SAN MARTÍN DE PORRES, DISTRITO DE LIRCAY, PROVINCIA DE "
                  "ANGARAES, DEPARTAMENTO DE HUANCAVELICA")


def _espejo_dos_experiencias_misma_obra() -> dict:
    """Un profesional con 2 experiencias de la MISMA obra (comparten documento)."""
    return {
        "_meta": {"concurso": "CP-TEST/2026", "postor": "POSTOR DEMO"},
        "profesionales": [
            {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN",
             "experiencias": [{"n": 1, "proyecto": PROYECTO_LARGO},
                              {"n": 2, "proyecto": PROYECTO_LARGO}]},
        ],
    }


def _dos_carpetas_con_el_mismo_pdf(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "original-a.pdf").write_bytes(b"%PDF-1.4 misma evidencia")
    (b / "otro-nombre.pdf").write_bytes(b"%PDF-1.4 misma evidencia")
    return a, b


ENR_MISMA_OBRA = {"1:1": {"obra": {"obra_id": 72056}},
                  "1:2": {"obra": {"obra_id": 72056}}}


def test_indice_md_reemplaza_al_txt_y_no_recorta_el_proyecto(tmp_path, monkeypatch):
    # El txt es un muro de líneas kilométricas; el md agrupa por profesional y
    # muestra el nombre COMPLETO de la obra.
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "md")
    a, b = _dos_carpetas_con_el_mismo_pdf(tmp_path)
    salida = construir_zip_infoobras(
        _espejo_dos_experiencias_misma_obra(), {(1, 1): a, (1, 2): b},
        tmp_path / "md.zip", enriquecimiento=ENR_MISMA_OBRA)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert "indice.md" in nombres
        assert "indice.txt" not in nombres
        md = zf.read("indice.md").decode("utf-8")
        assert "# ZIP InfoObras · CP-TEST-2026" in md
        assert "**Postor:** POSTOR DEMO" in md
        assert "## P01 · JEFE DE SUPERVISIÓN" in md
        assert PROYECTO_LARGO in md                       # sin recorte a 70
        assert "### E2 · misma obra que E1" in md         # no repite el titular
        assert "- **Documentos:** 1" in md
        assert ("- **Documentos:** 1 — 1 compartidos con otras experiencias "
                "de esta obra, 0 propios del periodo") in md


def test_indice_json_expone_los_conteos_por_experiencia(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "json")
    a, b = _dos_carpetas_con_el_mismo_pdf(tmp_path)
    salida = construir_zip_infoobras(
        _espejo_dos_experiencias_misma_obra(), {(1, 1): a, (1, 2): b},
        tmp_path / "json.zip", enriquecimiento=ENR_MISMA_OBRA)
    with zipfile.ZipFile(salida) as zf:
        assert "indice.txt" not in zf.namelist()
        datos = json.loads(zf.read("indice.json").decode("utf-8"))
    assert datos["postor"] == "POSTOR DEMO"
    e1, e2 = datos["experiencias"]
    assert (e1["n_prof"], e1["n_exp"], e1["proyecto"]) == (1, 1, PROYECTO_LARGO)
    # el documento es propio de la primera experiencia y compartido en la segunda
    assert (e1["documentos"], e1["compartidos"], e1["propios"]) == (1, 0, 1)
    assert (e2["documentos"], e2["compartidos"], e2["propios"]) == (1, 1, 0)
    assert e1["sin_documentos"] is False and e1["motivo"] is None
    assert e1["notas"] == 0 and e1["advertencias"] == []
    assert "_grupo_obra" not in e1        # clave interna, fuera del contrato


def test_informes_fuera_de_periodo_se_explican_igual_en_los_tres_formatos(
        tmp_path, monkeypatch):
    """Issue #81 R3: la obra SÍ publica informes de control, pero ninguno cae en
    el periodo del certificado. Los tres formatos del índice dicen lo mismo, y no
    lo confunden con «sin documentos publicados»."""
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "txt,md,json")
    carpeta = tmp_path / "P1_E1"
    carpeta.mkdir()
    (carpeta / "val.pdf").write_bytes(b"%PDF-1.4 valorizacion")
    enr = {"1:1": {"obra": {"obra_id": 72056}, "descargas_reales": {
        "archivos": 1,
        "secciones": {"Informes de control": {
            "estado": "sin_documentos", "esperados": 0, "descargados": 0,
            "publicados": 3}},
        "avisos": [],
    }}}
    salida = construir_zip_infoobras(
        ESPEJO, {(1, 1): carpeta}, tmp_path / "fuera.zip", enriquecimiento=enr)
    esperado = ("los informes de control publicados no corresponden al periodo "
                "de este certificado (3 publicados, todos de otros años)")
    with zipfile.ZipFile(salida) as zf:
        txt = zf.read("indice.txt").decode("utf-8")
        md = zf.read("indice.md").decode("utf-8")
        datos = json.loads(zf.read("indice.json").decode("utf-8"))
    assert f"SECCIÓN Informes de control: {esperado}" in txt
    assert f"- Informes de control: {esperado}" in md
    assert datos["experiencias"][0]["secciones_incompletas"] == [
        {"seccion": "Informes de control", "estado": esperado}]
    assert "0 disponibles" not in txt + md


def test_indice_acepta_varios_formatos_a_la_vez(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "txt,md")
    a, b = _dos_carpetas_con_el_mismo_pdf(tmp_path)
    salida = construir_zip_infoobras(
        _espejo_dos_experiencias_misma_obra(), {(1, 1): a, (1, 2): b},
        tmp_path / "ambos.zip", enriquecimiento=ENR_MISMA_OBRA)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert "indice.txt" in nombres and "indice.md" in nombres
        assert "indice.json" not in nombres
        # el txt conserva su formato histórico (línea por experiencia, recortada)
        txt = zf.read("indice.txt").decode("utf-8")
        assert "[P01 / E1]  JEFE DE SUPERVISIÓN · " in txt
        assert PROYECTO_LARGO not in txt


def test_indice_desactivado_no_deja_ningun_indice(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "0")
    a, b = _dos_carpetas_con_el_mismo_pdf(tmp_path)
    salida = construir_zip_infoobras(
        _espejo_dos_experiencias_misma_obra(), {(1, 1): a, (1, 2): b},
        tmp_path / "sin-indice.zip", enriquecimiento=ENR_MISMA_OBRA)
    with zipfile.ZipFile(salida) as zf:
        nombres = zf.namelist()
        assert not any(n.startswith("indice.") for n in nombres)
        carpeta = _carpeta_experiencia(1, PROYECTO_LARGO)
        assert f"P01 SUPERVISIÓN/{carpeta}/original-a.pdf" in nombres


def test_indice_formato_desconocido_cae_al_txt(tmp_path, monkeypatch):
    # Un typo en el .env no puede dejar el entregable sin índice.
    monkeypatch.setenv("PIVOTE_INDICE_ZIP", "markdown")
    a, b = _dos_carpetas_con_el_mismo_pdf(tmp_path)
    salida = construir_zip_infoobras(
        _espejo_dos_experiencias_misma_obra(), {(1, 1): a, (1, 2): b},
        tmp_path / "typo.zip", enriquecimiento=ENR_MISMA_OBRA)
    with zipfile.ZipFile(salida) as zf:
        assert "indice.txt" in zf.namelist()


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
    assert any(v.startswith("¿Estuvo habido durante el periodo certificado?")
               for v in celdas.values())
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


# ── Visibilidad del bloque de obra (issue #46: nombre de la obra + aviso) ─────


def _texto(ws) -> str:
    return "\n".join(str(c.value) for f in ws.iter_rows() for c in f if c.value)


def _celdas(ws) -> list[str]:
    return [str(c.value) for f in ws.iter_rows() for c in f if c.value is not None]


def _hoja_de(salida, n_prof, cargo):
    return openpyxl.load_workbook(salida)[etiqueta_hoja(n_prof, cargo)]


_ESPEJO_1EXP = {
    "_meta": {}, "postor": {},
    "profesionales": [{
        "n_prof": 1, "cargo": "JEFE", "nombre": "N",
        "experiencias": [{"n": 1, "proyecto": "Construcción del Hospital de EsSalud, Tarapoto",
                          "fecha_inicial": "2019-05-01", "fecha_final": "2019-10-31"}],
    }],
    "resumen_evaluacion": {"factores": []},
}


def test_bloque_de_obra_muestra_el_nombre_primero(tmp_path):
    """Punto 1 del issue #46: sin el nombre, un CUI mal resuelto (obra de OTRA
    región) pasa inadvertido detrás de un código y un monto correctos. El nombre
    es el PRIMER campo del bloque, antes del código."""
    fichas = {(1, 1): {"codigo_infoobras": "104710", "cui": "2405647",
                       "obra_nombre": "INSTALACION DE LOS SERVICIOS DE TOMOGRAFIA, "
                                      "PUERTO MALDONADO, MADRE DE DIOS",
                       "estado": "Finalizado", "valorizaciones": []}}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "n.xlsx", fichas=fichas)
    ws = _hoja_de(salida, 1, "JEFE")

    fila_nom = next(c.row for f in ws.iter_rows() for c in f if c.value == "Nombre de la obra")
    fila_cod = next(c.row for f in ws.iter_rows() for c in f if c.value == "Código InfoObras")
    assert fila_nom < fila_cod                      # primero el nombre
    assert "PUERTO MALDONADO" in _texto(ws)
    # el nombre no cabe en una línea y una celda combinada no auto-ajusta el alto
    assert (ws.row_dimensions[fila_nom].height or 15) > 15


def test_bloque_de_obra_sin_nombre_lo_dice(tmp_path):
    """Ficha sin nombre (InfoObras no lo devolvió): se dice, no se omite la fila —
    la ausencia del dato también es información para el evaluador."""
    fichas = {(1, 1): {"codigo_infoobras": "104710", "cui": "2405647", "valorizaciones": []}}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "sn.xlsx", fichas=fichas)
    assert "no devolvió el nombre" in _texto(_hoja_de(salida, 1, "JEFE"))


def test_desempaquetar_enriquecimiento_lleva_el_nombre_a_la_ficha():
    """El nombre NO viene dentro de `obra_ficha`: viaja suelto (`obra_nombre`) o en
    `obra.nombre_obra`. Sin esta traducción nunca llegaba al Excel."""
    from entregables import desempaquetar_enriquecimiento

    _, _, fichas, _ = desempaquetar_enriquecimiento({
        "1:1": {"obra_nombre": "HOSPITAL X", "obra_ficha": {"cui": "1", "codigo_infoobras": "9"}},
        "1:2": {"obra": {"nombre_obra": "HOSPITAL Y"},          # solo el nombre anidado
                "obra_ficha": {"cui": "2", "codigo_infoobras": "8"}},
    })
    assert fichas[(1, 1)]["obra_nombre"] == "HOSPITAL X"
    assert fichas[(1, 2)]["obra_nombre"] == "HOSPITAL Y"


def test_aviso_de_revision_se_pinta_aunque_haya_obra(tmp_path):
    """Punto 2 del issue #46: antes el aviso era `elif` de la obra, así que si el
    resolver proponía una obra el aviso NUNCA se pintaba (40% de los avisos
    invisibles). Ahora va como banda ENCIMA del bloque de la obra."""
    fichas = {(1, 1): {"codigo_infoobras": "1", "cui": "2405647",
                       "obra_nombre": "OBRA PROPUESTA", "valorizaciones": []}}
    revisiones = {(1, 1): ("los candidatos contradicen el rubro del certificado — confirmar",
                           "elegir candidato o pegar CUI")}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "rev.xlsx",
                                 fichas=fichas, revisiones=revisiones)
    ws = _hoja_de(salida, 1, "JEFE")
    texto = _texto(ws)

    assert "EXPERIENCIA EN REVISIÓN" in texto
    assert "contradicen el rubro" in texto
    # La acción se traduce a lenguaje de evaluador: el Comité no usa el panel,
    # así que «elegir candidato o pegar CUI» no le dice qué hacer con el papel.
    assert "elegir candidato" not in texto
    assert ("Acción: Confirmar con el certificado y, si existe, el contrato del "
            "expediente.") in texto
    aviso = next(c for f in ws.iter_rows() for c in f
                 if str(c.value or "").startswith("⚠ EXPERIENCIA EN REVISIÓN"))
    cabecera = next(c for f in ws.iter_rows() for c in f
                    if str(c.value or "").startswith("OBRA EN INFOOBRAS"))
    # misma franja de columnas y ARRIBA del bloque de obra (no como nota al pie)
    assert aviso.column == cabecera.column
    assert aviso.row < cabecera.row
    assert aviso.fill.fgColor.rgb.endswith("FF9999")     # alerta, se ve de lejos


def test_el_aviso_dice_el_motivo_real_y_no_una_narrativa_de_obra(tmp_path):
    """Los ItemRevision los crean 4 etapas y la mayoría no habla de la obra. Un
    aviso que igual grita "la obra no está confirmada, pegue el CUI" sobre un CUI
    correcto es un falso positivo — y un aviso que miente enseña al evaluador a
    ignorar la banda. El motivo y la acción son los del item."""
    fichas = {(1, 1): {"codigo_infoobras": "1", "cui": "2405647",
                       "obra_nombre": "OBRA BIEN IDENTIFICADA", "valorizaciones": []}}
    revisiones = {(1, 1): ("NO CUMPLE pero la(s) experiencia(s) 3 no se contó por una "
                           "fecha sin verificar — confirmarla puede cambiar el veredicto",
                           "verificar la fecha de fin del certificado")}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "rev3.xlsx",
                                 fichas=fichas, revisiones=revisiones)
    texto = _texto(_hoja_de(salida, 1, "JEFE"))

    assert "fecha sin verificar" in texto
    assert "Acción: verificar la fecha de fin del certificado" in texto
    # el motivo se muestra VERBATIM: `.capitalize()` bajaría el veredicto del motor
    assert "NO CUMPLE pero" in texto
    # nada de la narrativa de identidad de obra que antes iba cableada
    assert "PROPUESTA del sistema" not in texto
    assert "pegar el CUI" not in texto


def test_el_aviso_sin_accion_sugerida_no_inventa_una(tmp_path):
    """Un item sin `accion_sugerida` cae a una acción GENÉRICA: mandar a pegar un
    CUI sin saber que el problema es el CUI es fabricar un diagnóstico."""
    fichas = {(1, 1): {"codigo_infoobras": "1", "cui": "2405647",
                       "obra_nombre": "OBRA", "valorizaciones": []}}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "rev4.xlsx", fichas=fichas,
                                 revisiones={(1, 1): "el portal no respondió"})
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "Acción: revisar esta experiencia en el panel" in texto
    assert "pegar el CUI" not in texto


def test_el_aviso_no_encoge_la_fila_del_titulo_de_la_experiencia(tmp_path):
    """El aviso comparte fila con el título de la experiencia (nombre del proyecto
    VERBATIM, que `banda()` ya dimensionó). Fijar la altura cortaba el nombre justo
    en la experiencia marcada como dudosa: la altura solo puede AUMENTAR."""
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N", "experiencias": [{
                "n": 1, "fecha_inicial": "2019-05-01", "fecha_final": "2019-10-31",
                "proyecto": ("MEJORAMIENTO Y AMPLIACIÓN DE LOS SERVICIOS DE SALUD DEL "
                             "ESTABLECIMIENTO DE SALUD I-4 SAN MARTÍN DE PORRES, DISTRITO "
                             "DE MORALES, PROVINCIA DE SAN MARTÍN, DEPARTAMENTO DE SAN "
                             "MARTÍN")}]}],
        "resumen_evaluacion": {"factores": []},
    }
    fichas = {(1, 1): {"codigo_infoobras": "1", "cui": "2405647",
                       "obra_nombre": "OBRA", "valorizaciones": []}}
    sin = generar_excel_final(espejo, tmp_path / "alto_sin.xlsx", fichas=fichas)
    con = generar_excel_final(espejo, tmp_path / "alto_con.xlsx", fichas=fichas,
                              revisiones={(1, 1): ("motivo cualquiera", "hacer algo")})

    def _alto_del_titulo(salida):
        ws = _hoja_de(salida, 1, "JEFE")
        fila = next(c.row for f in ws.iter_rows() for c in f
                    if str(c.value or "").startswith("EXPERIENCIA 1:"))
        return ws.row_dimensions[fila].height or 15

    assert _alto_del_titulo(con) >= _alto_del_titulo(sin) > 15


def test_sin_obra_el_aviso_de_revision_sigue_siendo_el_bloque_completo(tmp_path):
    """Regresión: cuando NO hay obra, el bloque de revisión de siempre (con la
    acción a tomar) sigue ocupando la franja — no se degrada a la banda."""
    revisiones = {(1, 1): "el certificado no cita CUI"}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "rev2.xlsx", revisiones=revisiones)
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "EXPERIENCIA EN REVISIÓN" in texto
    # aquí sí no hubo cruce, así que la acción por defecto es de identidad de obra
    assert "pegar el CUI correcto en el panel" in texto
    assert "OBRA EN INFOOBRAS" not in texto


def test_privada_es_ruta_sunat_y_no_revision_provisional(tmp_path):
    revisiones = {(1, 1): "[PRIVADA]"}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "privada.xlsx",
                                 revisiones=revisiones)
    texto_prof = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "OBRA / CLIENTE PRIVADO" in texto_prof
    assert "InfoObras, MEF y SEACE no aplican" in texto_prof
    assert "La ruta de verificación es SUNAT" in texto_prof
    assert "PROVISIONAL — POR VERIFICAR" not in texto_prof
    assert "DÍAS PROVISIONALES DEL PROFESIONAL" not in texto_prof

    wb = openpyxl.load_workbook(salida, data_only=True)
    observaciones = wb["Base de Datos"].cell(2, 25).value
    assert "OBRA PRIVADA" in observaciones
    assert "SUNAT y la revisión documental" in observaciones

    texto_crono = _texto(wb["Cronología de expedientes"])
    assert "NO APLICA — OBRA PRIVADA" in texto_crono
    assert "La ruta de verificación es SUNAT" in texto_crono


def test_privada_sin_ruc_sunat_queda_etiquetada_y_provisional(tmp_path):
    from entregables import completar_revisiones_privadas

    revisiones = completar_revisiones_privadas({}, {
        "1:1": {"via": "PRIVADA", "sunat": {"no_encontrado": True}},
    })
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "privada_pendiente.xlsx",
                                 revisiones=revisiones)
    texto_prof = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" in texto_prof
    assert "PROVISIONAL — POR VERIFICAR" in texto_prof
    assert "DÍAS PROVISIONALES DEL PROFESIONAL" in texto_prof

    wb = openpyxl.load_workbook(salida, data_only=True)
    assert "REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" in (
        wb["Base de Datos"].cell(2, 25).value)
    assert "REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" in _texto(
        wb["Cronología de expedientes"])


def test_clasificacion_privada_exige_ruc_sunat_inequivoco():
    from entregables import completar_revisiones_privadas

    revisiones = completar_revisiones_privadas({}, {
        "1:1": {"via": "PRIVADA", "sunat": {"ruc": "20123456789"}},
        "1:2": {"via": "PRIVADA", "sunat": {"no_encontrado": True}},
        "1:3": {"via": "PRIVADA", "sunat": {"ambiguo": 2}},
    })
    assert revisiones[(1, 1)] == "[PRIVADA]"
    assert revisiones[(1, 2)][0].startswith("[PRIVADA_PENDIENTE]")
    assert revisiones[(1, 3)][0].startswith("[PRIVADA_PENDIENTE]")


def test_resultado_compartido_no_resta_ejecucion_a_expediente_o_privada():
    from entregables import reconciliar_resultados_profesionales

    espejo = {
        "profesionales": [{
            "n_prof": 1,
            "cumple": "CUMPLE — declarado",
            "requisitos": {"experiencia": "Experiencia mínima: 24 meses"},
            "experiencias": [
                {"n": 1, "proyecto": "Supervisión del expediente técnico del hospital",
                 "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31"},
                {"n": 2, "proyecto": "Clínica privada",
                 "fecha_inicial": "2021-01-01", "fecha_final": "2021-12-31"},
            ],
        }],
    }
    enriquecimiento = {
        "1:1": {"paralizaciones": [{"inicio": "2020-01-01", "fin": "2020-12-31"}],
                "cobertura_baja": 0},
        "1:2": {"via": "PRIVADA", "sunat": {"ruc": "20123456789"},
                "sin_verificar": True,
                "paralizaciones": [{"inicio": "2021-01-01", "fin": "2021-12-31"}]},
        "prof:1": {"dias_efectivos": 0,
                   "cumple_backend": "NO CUMPLE — resultado histórico"},
    }

    resultado = reconciliar_resultados_profesionales(espejo, enriquecimiento)[1]

    assert resultado["dias_paralizados"] == 0
    assert resultado["dias_efectivos"] == 731
    assert resultado.get("cumple_backend") is None
    assert not resultado.get("veredicto_provisional")


def test_resultado_compartido_deja_privada_sin_ruc_por_confirmar():
    from entregables import reconciliar_resultados_profesionales

    espejo = {"profesionales": [{
        "n_prof": 1,
        "requisitos": {"experiencia": "Experiencia mínima: 1 año"},
        "experiencias": [{"n": 1, "proyecto": "Cliente privado",
                           "fecha_inicial": "2021-01-01", "fecha_final": "2021-12-31"}],
    }]}
    resultado = reconciliar_resultados_profesionales(espejo, {
        "1:1": {"via": "PRIVADA", "sunat": {"ambiguo": 2}},
    })[1]

    assert resultado["veredicto_provisional"] == [1]
    assert resultado["cumple_backend"].startswith("POR VERIFICAR")
    assert "SUNAT" in resultado["cumple_backend"]


def test_sin_obra_el_bloque_usa_la_accion_del_item_si_la_trae(tmp_path):
    """…pero si el item trae su propia acción, manda la del item."""
    revisiones = {(1, 1): ("no se pudo verificar en InfoObras — veredicto provisional",
                           "reintentar la consulta o verificar la obra a mano")}
    salida = generar_excel_final(_ESPEJO_1EXP, tmp_path / "rev5.xlsx", revisiones=revisiones)
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "Acción: reintentar la consulta o verificar la obra a mano" in texto
    assert "pegar el CUI" not in texto


def test_una_obra_repetida_se_detalla_completa_en_cada_experiencia(tmp_path):
    """El bloque de UNA EXPERIENCIA se pinta siempre completo, aunque la obra ya
    esté detallada arriba: es la evidencia de esa experiencia, en la franja pegada
    a su cuadro de hitos. El colapso (issue #46 punto 6) solo aplica a las
    SubExperiencias repetidas de un cert multi-obra.

    Además cubre el caso que hizo RETIRAR la primera versión del colapso: mismo
    CUI, obras DISTINTAS (la ventana del certificado desambigua). La clave es
    (CUI, código InfoObras), así que ni siquiera son la misma obra."""
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N", "experiencias": [
                {"n": 1, "proyecto": "Tramo 1", "fecha_inicial": "2019-01-01",
                 "fecha_final": "2019-06-30"},
                {"n": 2, "proyecto": "Tramo 2", "fecha_inicial": "2021-01-01",
                 "fecha_final": "2021-12-31"}]}],
        "resumen_evaluacion": {"factores": []},
    }
    fichas = {
        (1, 1): {"cui": "2418877", "codigo_infoobras": "111", "obra_nombre": "OBRA A",
                 "valorizaciones": [{"anio": 2019, "mes": 3, "estado": "En ejecución"}]},
        # mismo CUI, OTRA obra y otro periodo: sin valorizaciones registradas
        (1, 2): {"cui": "2418877", "codigo_infoobras": "999", "obra_nombre": "OBRA B",
                 "valorizaciones": []},
    }
    salida = generar_excel_final(espejo, tmp_path / "dup.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    texto = "\n".join(celdas)

    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert "999" in texto and "OBRA B" in texto          # la 2ª ficha no se borró
    assert "YA DETALLADA" not in texto


def test_la_misma_obra_en_dos_experiencias_se_detalla_una_vez(tmp_path):
    """Los hitos de ambos certificados se conservan; la ficha idéntica se
    sustituye por un puntero local para no repetir cientos de filas."""
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N", "experiencias": [
                {"n": 1, "proyecto": "Orden 1", "fecha_inicial": "2019-01-01",
                 "fecha_final": "2019-06-30"},
                {"n": 2, "proyecto": "Orden 2", "fecha_inicial": "2019-01-01",
                 "fecha_final": "2019-06-30"}]}],
        "resumen_evaluacion": {"factores": []},
    }
    ficha = {"cui": "2418877", "codigo_infoobras": "111", "obra_nombre": "OBRA A",
             "estado": "Finalizado", "valorizaciones": []}
    salida = generar_excel_final(espejo, tmp_path / "dup2.xlsx",
                                 fichas={(1, 1): dict(ficha), (1, 2): dict(ficha)})
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 1
    assert any(v.startswith("OBRA YA DETALLADA") for v in celdas)


# ── Colapso de sub-obras repetidas (issue #46 punto 6, rediseñado) ────────────
# Fixtures MODELADAS COMO EL PIPELINE REAL: `_enriquecer_subobra` SIEMPRE mete
# las valorizaciones de la obra dentro de `ficha`, así que una sub-obra con
# `valorizaciones: []` solo representa a una obra que InfoObras no valorizó.

def _espejo_multi(n_exps: int, periodos: list[tuple[str, str]]) -> dict:
    return {
        "_meta": {}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "experiencias": [
                {"n": i, "proyecto": f"Orden de servicio {i}",
                 "fecha_inicial": periodos[i - 1][0], "fecha_final": periodos[i - 1][1]}
                for i in range(1, n_exps + 1)],
        }],
        "resumen_evaluacion": {"factores": []},
    }


def _sub(cui, cod, nombre, vals, obra_nombre=None, **extra):
    """Sub-obra como la deja `_enriquecer_subobra`. `nombre` es el proyecto tal
    como lo DECLARA el certificado y `obra_nombre` el de InfoObras: en los certs
    multi-obra reales pueden diferir (dos establecimientos declarados aparte que
    son una sola obra registrada)."""
    return {"estado": "resuelto", "cui": cui, "via": "CODIGO", "proyecto": nombre,
            "fecha_inicial": None, "fecha_final": None,
            "ficha": {"cui": cui, "codigo_infoobras": cod,
                      "obra_nombre": obra_nombre or nombre,
                      "estado": "En Ejecución", "monto": 100.0,
                      "fecha_inicio": "2018-01-01", "fecha_fin": "2019-01-01",
                      "modificaciones_plazo": [], "valorizaciones": vals},
            **extra}


def test_subobras_identicas_de_ordenes_consecutivas_se_colapsan(tmp_path):
    """El caso real del job 95af90f1578e / P3. Arquit: 4 órdenes de servicio
    consecutivas del mismo contrato, cada una certificando las MISMAS 3 obras →
    12 bloques de detalle idénticos. Se pintan 3 y las 9 repeticiones quedan como
    puntero a la fila donde está el detalle."""
    periodos = [("2025-06-11", "2025-08-31"), ("2025-09-02", "2025-12-30"),
                ("2026-01-28", "2026-03-31"), ("2026-04-07", "2026-06-30")]
    espejo = _espejo_multi(4, periodos)
    subs = [_sub("2377760", "92111", "OBRA PONGO", []),
            _sub("2377762", "92112", "OBRA CHAZUTA", []),
            _sub("2377764", "92168", "OBRA TABALOSOS", [])]
    fichas = {(1, i): {"sub_obras": [dict(s) for s in subs]} for i in range(1, 5)}
    salida = generar_excel_final(espejo, tmp_path / "multi.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))

    # las 12 SubExperiencias SIGUEN estando: cada certificado declara esas obras y
    # ese hecho es evidencia de ESE certificado — lo que se colapsa es el detalle.
    assert sum(1 for v in celdas if v.startswith("SubExperiencia ")) == 12
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 3
    assert sum(1 for v in celdas if v.startswith("OBRA YA DETALLADA")) == 9
    texto = "\n".join(celdas)
    # el puntero nombra la obra, dónde está el detalle y QUÉ hay allá
    assert "código InfoObras 92111" in texto
    assert "SubExperiencia 1.1" in texto
    assert "InfoObras no registra valorizaciones de esta obra" in texto


def test_dos_subobras_del_mismo_cert_al_mismo_cui_colapsan_una_vez(tmp_path):
    """Caso real P1. Jefe Superv exp 3: dos sub-obras declaradas con nombres
    distintos (C.S. TONGOD y P.S. PISIT) resuelven a la MISMA obra de InfoObras
    → un detalle y un puntero. El nombre declarado de la 2ª NO se pierde."""
    espejo = _espejo_multi(1, [("2024-06-12", "2024-09-16")])
    vals = [{"anio": 2024, "mes": 10, "estado": "En ejecución",
             "fisico_real": 71.6, "valorizado_real": 3142323.82, "docs": 1}]
    obra = "MEJORAMIENTO ... C.S TONGOD Y P.S PISIT ... SAN MIGUEL - CAJAMARCA"
    fichas = {(1, 1): {"sub_obras": [
        _sub("2440017", "504249", "C.S. TONGOD", list(vals), obra_nombre=obra),
        _sub("2440017", "504249", "P.S. PISIT", list(vals), obra_nombre=obra)]}}
    salida = generar_excel_final(espejo, tmp_path / "tongod.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    texto = "\n".join(celdas)

    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 1
    assert sum(1 for v in celdas if v.startswith("OBRA YA DETALLADA")) == 1
    # los DOS nombres declarados siguen visibles (las cabeceras no se colapsan):
    # que dos establecimientos declarados sean una sola obra es justo lo que el
    # evaluador tiene que ver.
    assert "P.S. PISIT" in texto and "C.S. TONGOD" in texto
    assert "su única valorización" in texto


def test_colapsa_ficha_aunque_el_periodo_del_certificado_cambie(tmp_path):
    """El periodo propio sigue visible en los hitos; no justifica duplicar toda
    la ficha y las valorizaciones de la misma obra."""
    espejo = _espejo_multi(2, [("2019-03-01", "2019-03-31"),
                               ("2019-05-01", "2019-05-31")])
    vals = [{"anio": 2019, "mes": 3, "estado": "En ejecución"},
            {"anio": 2019, "mes": 5, "estado": "En ejecución"}]
    fichas = {(1, i): {"sub_obras": [_sub("2418877", "111", "OBRA A", list(vals))]}
              for i in (1, 2)}
    salida = generar_excel_final(espejo, tmp_path / "per.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 1
    assert any(v.startswith("OBRA YA DETALLADA") for v in celdas)


def test_colapsa_por_obra_aunque_los_periodos_sean_distintos(tmp_path):
    """Las fechas del certificado viven en su propio bloque; la evidencia de
    InfoObras idéntica se detalla una sola vez."""
    espejo = _espejo_multi(2, [("2021-01-01", "2021-01-31"),
                               ("2022-06-01", "2022-06-30")])
    vals = [{"anio": 2019, "mes": 3, "estado": "En ejecución"}]
    fichas = {(1, i): {"sub_obras": [_sub("2418877", "111", "OBRA A", list(vals))]}
              for i in (1, 2)}
    salida = generar_excel_final(espejo, tmp_path / "perb.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 1
    assert any(v.startswith("OBRA YA DETALLADA") for v in celdas)


def test_no_colapsa_si_cambian_los_montos_de_las_valorizaciones(tmp_path):
    """Mismo número de valorizaciones no es el mismo contenido. El portal de
    InfoObras es inestable (tablas que varían entre corridas): si dos fichas de
    la misma obra traen importes distintos, esa diferencia es justo lo que hay
    que ver, no lo que hay que esconder tras un puntero."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    fichas = {
        (1, 1): {"sub_obras": [_sub("2418877", "111", "OBRA A", [
            {"anio": 2019, "mes": 3, "estado": "En ejecución", "valorizado_real": 100.0}])]},
        (1, 2): {"sub_obras": [_sub("2418877", "111", "OBRA A", [
            {"anio": 2019, "mes": 3, "estado": "En ejecución", "valorizado_real": 999.0}])]},
    }
    salida = generar_excel_final(espejo, tmp_path / "mon.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)
    assert 999.0 in [c.value for f in _hoja_de(salida, 1, "JEFE").iter_rows() for c in f]


@pytest.mark.parametrize("campo,valor", [
    ("obra_nombre", "OTRA OBRA"),
    ("estado", "Finalizado"),
    ("monto", 999.0),
    ("fecha_inicio", "2010-01-01"),
    ("fecha_fin", "2030-12-31"),
    ("modificaciones_plazo", [{"tipo": "Ampliación", "dias": 30}]),
    ("representante_obra", {"contratistas": [{"ruc": "20100000001",
                                              "nombre_empresa": "CONSTRUCTORA X"}]}),
])
def test_no_colapsa_si_difiere_cualquier_campo_de_la_ficha(tmp_path, campo, valor):
    """Cada campo que el bloque pinta entra en la huella. Si la 2ª aparición de la
    misma obra trae algo distinto — otro estado, otro monto, otras fechas de obra,
    una ampliación de plazo, el representante — se pinta completa: esa diferencia
    es información, y esconderla tras "igual que arriba" sería mentir."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    sub2 = _sub("2418877", "111", "OBRA A", [])
    sub2["ficha"][campo] = valor
    fichas = {(1, 1): {"sub_obras": [_sub("2418877", "111", "OBRA A", [])]},
              (1, 2): {"sub_obras": [sub2]}}
    salida = generar_excel_final(espejo, tmp_path / f"{campo}.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)


def test_no_colapsa_si_una_ficha_es_expediente_y_la_otra_obra(tmp_path):
    """Misma obra, mismo periodo, pero una aparición trae la verificación del
    EXPEDIENTE TÉCNICO (MEF) y la otra no: son bloques que dicen cosas distintas."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    verif = {"contratista": {"valor": "CONSORCIO X", "veredicto": "ok"},
             "contrato": {"numero": "007"}, "resolucion": {"numero": "R-1"},
             "cui_confirmado": "2418877", "fuentes": ["MEF"]}
    sub_con = _sub("2418877", "111", "OBRA A", [])
    sub_con["ficha"]["verificacion_expediente"] = verif
    fichas = {(1, 1): {"sub_obras": [sub_con]},
              (1, 2): {"sub_obras": [_sub("2418877", "111", "OBRA A", [])]}}
    salida = generar_excel_final(espejo, tmp_path / "exp.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    texto = "\n".join(celdas)
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)
    assert "VERIFICACIÓN SEACE / MEF" in texto and "CONSORCIO X" in texto


def test_colapso_de_bloque_de_expediente_dice_que_es_un_expediente(tmp_path):
    """Cuando lo repetido SÍ es un bloque de expediente, el puntero lo nombra:
    nunca dice "valorizaciones" donde no las hay."""
    espejo = _espejo_multi(1, [("2019-01-01", "2019-12-31")])
    verif = {"contratista": {"valor": "CONSORCIO X", "veredicto": "ok"},
             "contrato": {"numero": "007"}, "resolucion": {"numero": "R-1"},
             "cui_confirmado": "2418877", "fuentes": ["MEF"]}

    def _con_verif(nombre):
        s = _sub("2418877", "111", nombre, [], obra_nombre="OBRA A")
        s["ficha"]["verificacion_expediente"] = dict(verif)
        return s

    fichas = {(1, 1): {"sub_obras": [_con_verif("Tramo A"), _con_verif("Tramo B")]}}
    salida = generar_excel_final(espejo, tmp_path / "expc.xlsx", fichas=fichas)
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "OBRA YA DETALLADA" in texto
    assert "la verificación del expediente técnico" in texto
    assert "valorizaciones de esta obra" not in texto


def test_no_colapsa_si_una_ficha_trae_valorizaciones_y_la_otra_no(tmp_path):
    """La trampa que hundió la primera versión: una ficha SIN valorizaciones
    referida a otra que SÍ las tiene renderiza una AUSENCIA de dato como puntero
    a evidencia. Aunque sea la misma obra y el mismo periodo, no se colapsa."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    fichas = {
        (1, 1): {"sub_obras": [_sub("2418877", "111", "OBRA A",
                                    [{"anio": 2019, "mes": 3, "estado": "En ejecución"}])]},
        (1, 2): {"sub_obras": [_sub("2418877", "111", "OBRA A", [])]},
    }
    salida = generar_excel_final(espejo, tmp_path / "vac.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)
    assert "Sin valorizaciones registradas en InfoObras" in "\n".join(celdas)


def test_no_colapsa_dos_obras_distintas_del_mismo_cui(tmp_path):
    """Mismo CUI, códigos InfoObras distintos = obras distintas (`_fetch_obra`
    desambigua por la ventana del certificado). La clave lleva los dos."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    fichas = {
        (1, 1): {"sub_obras": [_sub("2418877", "111", "OBRA A", [])]},
        (1, 2): {"sub_obras": [_sub("2418877", "999", "OBRA B", [])]},
    }
    salida = generar_excel_final(espejo, tmp_path / "cui.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert "OBRA B" in "\n".join(celdas)
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)


def test_sin_codigo_infoobras_no_hay_identidad_y_no_se_colapsa(tmp_path):
    """Sin código de obra no hay identidad comprobable: ausencia de dato NUNCA
    habilita el colapso."""
    espejo = _espejo_multi(2, [("2019-01-01", "2019-12-31"),
                               ("2019-01-01", "2019-12-31")])
    sub = _sub("2418877", None, "OBRA A", [])
    fichas = {(1, i): {"sub_obras": [dict(sub)]} for i in (1, 2)}
    salida = generar_excel_final(espejo, tmp_path / "sincod.xlsx", fichas=fichas)
    celdas = _celdas(_hoja_de(salida, 1, "JEFE"))
    assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 2
    assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas)


def test_el_registro_de_obras_pintadas_es_por_hoja_de_profesional(tmp_path):
    """Un "ver SubExperiencia 1.1, fila 92" que apunte a la pestaña de OTRO
    profesional es inservible: cada hoja arranca de cero."""
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "JEFE", "nombre": "Uno",
             "experiencias": [{"n": 1, "proyecto": "Orden 1",
                               "fecha_inicial": "2019-01-01", "fecha_final": "2019-12-31"}]},
            {"n_prof": 2, "cargo": "ESTRUCTURAS", "nombre": "Dos",
             "experiencias": [{"n": 1, "proyecto": "Orden 1",
                               "fecha_inicial": "2019-01-01", "fecha_final": "2019-12-31"}]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    sub = _sub("2418877", "111", "OBRA A", [])
    fichas = {(1, 1): {"sub_obras": [dict(sub)]}, (2, 1): {"sub_obras": [dict(sub)]}}
    salida = generar_excel_final(espejo, tmp_path / "hojas.xlsx", fichas=fichas)
    for n_prof, cargo in ((1, "JEFE"), (2, "ESTRUCTURAS")):
        celdas = _celdas(_hoja_de(salida, n_prof, cargo))
        assert sum(1 for v in celdas if v.startswith("OBRA EN INFOOBRAS")) == 1, cargo
        assert not any(v.startswith("OBRA YA DETALLADA") for v in celdas), cargo


def test_el_colapso_no_pisa_la_cobertura_de_la_subexperiencia(tmp_path):
    """La cobertura del tiempo es POR sub-experiencia (la ventana del certificado
    contra las valorizaciones), no de la obra: se sigue pintando aunque el detalle
    de la obra se haya colapsado."""
    espejo = _espejo_multi(1, [("2019-01-01", "2019-12-31")])
    fichas = {(1, 1): {"sub_obras": [
        _sub("2418877", "111", "OBRA A", []),
        _sub("2418877", "111", "OBRA A", [],
             cobertura={"cubierto": False, "pct": 40, "cert_ini": "2019-01-01",
                        "cert_fin": "2019-12-31"})]}}
    salida = generar_excel_final(espejo, tmp_path / "cob.xlsx", fichas=fichas)
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "OBRA YA DETALLADA" in texto
    assert "cobertura 40%" in texto and "PARCIAL, revisar" in texto


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


def test_parte4_muestra_total_declarado_y_descuentos_backend(tmp_path):
    espejo = {
        "_meta": {"analisis_id": "tot", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "BIM", "nombre": "N",
            "total": {"dias": 781, "meses": 26.03, "anios": 2.14},
            "total_backend": {
                "dias_declarados": 781, "dias_paralizados": 0,
                "dias_traslape": 65, "dias_efectivos": 716,
                "anios_efectivos": 1.96,
            },
            "experiencias": [{
                "n": 1, "proyecto": "Obra", "fecha_inicial": "2024-01-01",
                "fecha_final": "2026-02-19", "dias": 781,
            }],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    salida = generar_excel_final(espejo, tmp_path / "totales.xlsx")
    texto = _texto(openpyxl.load_workbook(salida)["CLAUDE"])
    assert "TOTAL DECLARADO (suma de filas)" in texto
    assert "(−) Traslapes entre experiencias" in texto
    assert "TOTAL EFECTIVO VERIFICADO" in texto
    assert "781" in texto and "716" in texto and "65" in texto


def test_supuestos_tienen_procedencia_y_color_propio(tmp_path):
    """#65: el violeta nace de `supuestos`, no de buscar una palabra en el valor.

    Un hecho que contiene la palabra ASUMIDO no se pinta; un proyecto inferido
    sin esa palabra sí. La marca llega a CLAUDE, Base de Datos y el recap del
    profesional, y la leyenda no la confunde con el amarillo por verificar.
    """
    espejo = {
        "_meta": {"analisis_id": "sup", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "ASUMIDO ES UN APELLIDO",
            "supuestos": [],
            "experiencias": [{
                "n": 1, "entidad_emisora": "ENTIDAD LITERAL",
                "proyecto": "Proyecto inferido sin etiqueta textual",
                "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31",
                "cargo_ocupado": "Supervisor", "supuestos": ["proyecto", "fecha_inicial"],
            }],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    salida = generar_excel_final(espejo, tmp_path / "supuestos.xlsx")
    wb = openpyxl.load_workbook(salida)

    def color(celda):
        return celda.fill.fgColor.rgb[-6:] if celda.fill.patternType else None

    claude = wb["CLAUDE"]
    proyecto = next(c for row in claude.iter_rows() for c in row
                     if c.value == "Proyecto inferido sin etiqueta textual")
    nombre = next(c for row in claude.iter_rows() for c in row
                  if c.value == "ASUMIDO ES UN APELLIDO")
    assert color(proyecto) == "E4D7F5"
    assert color(nombre) != "E4D7F5"
    assert "Violeta = dato supuesto" in "\n".join(
        str(c.value) for row in claude.iter_rows() for c in row if c.value)

    base = wb["Base de Datos"]
    assert color(base.cell(2, 7)) == "E4D7F5"      # proyecto
    assert color(base.cell(2, 6)) != "E4D7F5"      # emisor literal

    prof = wb[etiqueta_hoja(1, "JEFE")]
    fila_proyecto = next(row for row in prof.iter_rows(min_col=1, max_col=4)
                         if row[0].value == "PROYECTO U OBRA")
    assert color(fila_proyecto[1]) == "E4D7F5"
    # La misma procedencia alcanza el cuadro de hitos y la Parte 5, no solo el recap.
    fila_periodo = next(row for row in prof.iter_rows(min_col=1, max_col=4)
                        if row[0].value == "Periodo certificado")
    assert color(fila_periodo[1]) == "E4D7F5"
    proyectos_violeta = [c for row in prof.iter_rows() for c in row
                         if c.value == "Proyecto inferido sin etiqueta textual"
                         and color(c) == "E4D7F5"]
    assert len(proyectos_violeta) >= 2  # recap + Parte 5


def test_confiabilidad_y_puntaje_ausente_son_visibles(tmp_path):
    salida = generar_excel_final(
        ESPEJO, tmp_path / "confiabilidad.xlsx",
        confiabilidad={
            "veredicto": "no_confiable",
            "hallazgos_criticos": [{
                "codigo": "VEREDICTO_SIN_SUSTENTO",
                "mensaje": "El veredicto no explica su sustento.",
                "referencia": "prof=1",
            }],
        },
    )
    ws = openpyxl.load_workbook(salida)["CLAUDE"]
    texto = _texto(ws)
    assert "CONFIABILIDAD: NO CONFIABLE" in texto
    assert "VEREDICTO_SIN_SUSTENTO" in texto
    assert "PUNTAJE TÉCNICO TOTAL" in texto
    assert "no se recibió un puntaje total calculable" in texto


def test_job_antiguo_sin_confiabilidad_no_muestra_alerta_roja(tmp_path):
    salida = generar_excel_final(
        ESPEJO, tmp_path / "legado.xlsx",
        confiabilidad={"veredicto": None, "hallazgos_criticos": []},
    )
    texto = _texto(openpyxl.load_workbook(salida)["CLAUDE"])
    assert "CONFIABILIDAD:" not in texto


def test_archivos_zip_muestra_encontrados_no_estado_de_descarga(tmp_path):
    espejo = {
        "_meta": {"analisis_id": "d", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "experiencias": [{
                "n": 1, "proyecto": "OBRA", "entidad_emisora": "E",
                "cargo_ocupado": "SUP", "fecha_inicial": "2020-01-01",
                "fecha_final": "2020-01-31",
            }],
        }],
        "resumen_evaluacion": {"factores": [], "puntaje_total": 1},
    }
    fichas = {(1, 1): {
        "obra_nombre": "OBRA", "codigo_infoobras": "I-1",
        "valorizaciones": [{"anio": 2020, "mes": 1, "docs": 9}],
        "descargas_reales": {"archivos": 2, "por_hito": {"2020-01": 2}},
    }}
    salida = generar_excel_final(espejo, tmp_path / "real.xlsx", fichas=fichas)
    hoja = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "JEFE")]
    cabecera = next(c for row in hoja.iter_rows() for c in row
                    if c.value == "ARCHIVOS ENCONTRADOS")
    assert hoja.cell(cabecera.row + 1, cabecera.column).value == "9 archivos encontrados"


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


def test_tdr_multipagina_se_rotula_como_cuadro_completo(tmp_path):
    """#68: un fallback amplio no puede presentarse como recorte individual exacto."""
    fitz = pytest.importorskip("fitz")
    tdr = tmp_path / "tdr-rango.pdf"
    doc = fitz.open()
    for n in range(3):
        doc.new_page().insert_text((72, 100), f"PERSONAL CLAVE PAGINA {n + 1}")
    doc.save(str(tdr))
    doc.close()
    espejo = {
        "_meta": {}, "postor": {}, "resumen_evaluacion": {"factores": []},
        "profesionales": [{
            "n_prof": 1, "cargo": "ESPECIALISTA", "nombre": "JUAN",
            "requisitos": {"cargos_validos": "ESPECIALISTA"},
            "experiencias": [],
        }],
    }
    salida = generar_excel_final(
        espejo, tmp_path / "tdr.xlsx", certificados={(1, "TDR"): tdr})
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))
    assert _fila_de(ws, "REQUISITO DEL TDR — cuadro completo de personal clave") > 0


# ── Factor de evaluación embebido al final de la hoja (issue #32) ────────────

_ESPEJO_FACTOR = {
    "_meta": {"pagina_factores": 48},
    "postor": {},
    "profesionales": [{
        "n_prof": 1, "cargo": "ESPECIALISTA EN ARQUITECTURA", "nombre": "JUANA",
        "colegiatura": "CAP 1",
        "experiencias": [{"n": 1, "proyecto": "Hospital X", "fecha_inicial": "2019-01-01",
                          "fecha_final": "2020-01-01", "entidad_emisora": "GR",
                          "cargo_ocupado": "Arquitecta"}],
    }],
    "resumen_evaluacion": {"factores": []},
}


def _pdf_una_pagina(destino: Path, texto: str) -> Path:
    """PDF mínimo de 1 página, con PyMuPDF — el mismo motor con el que el generador
    rasteriza los recortes."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), texto)
    doc.save(str(destino))
    doc.close()
    return destino


def _fila_de(ws, texto: str) -> int:
    """Nº de fila cuya columna A empieza con `texto` (0 si no está)."""
    return next((c.row for (c,) in ws.iter_rows(min_col=1, max_col=1)
                 if str(c.value or "").startswith(texto)), 0)


def test_excel_final_embebe_factor_al_final(tmp_path):
    """El recorte del Cuadro de Factores cierra la hoja del profesional, DESPUÉS de
    la PARTE 5 — y sin pisarla."""
    factor = _pdf_una_pagina(tmp_path / "factor.pdf",
                             "4.2 FACTORES DE EVALUACION - FACTOR A EXPERIENCIA ADICIONAL")
    salida = generar_excel_final(_ESPEJO_FACTOR, tmp_path / "factor.xlsx",
                                 certificados={(1, "FACTOR"): factor})
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))

    fila_banda = _fila_de(ws, "FACTOR DE EVALUACIÓN")
    fila_anios = _fila_de(ws, "AÑOS EFECTIVOS")
    # (1) el recorte está, y (2) va DESPUÉS de la PARTE 5 (al final, no al inicio)
    assert fila_banda > 0 and fila_anios > 0
    assert fila_banda > fila_anios
    # La banda no puede pisar el cierre numérico de la Parte 5.
    assert isinstance(ws.cell(fila_anios, 19).value, (int, float))
    assert len(ws._images) == 1


def test_excel_final_rechaza_recorte_que_no_es_factor_a(tmp_path):
    factor = _pdf_una_pagina(tmp_path / "factor-jk.pdf", "FACTORES J Y K - PUNTAJE")
    salida = generar_excel_final(_ESPEJO_FACTOR, tmp_path / "factor-mal.xlsx",
                                 certificados={(1, "FACTOR"): factor})
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))
    texto = "\n".join(_celdas(ws))
    assert "FACTOR A NO EMBEBIDO" in texto
    assert not ws._images


def test_base_de_datos_usa_cui_resuelto_y_rotula_colegiatura_pendiente(tmp_path):
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "ESP", "nombre": "N",
                            "experiencias": [{"n": 1, "proyecto": "OBRA",
                                               "anterior_colegiatura": None}]}],
        "resumen_evaluacion": {"factores": []},
    }
    salida = generar_excel_final(espejo, tmp_path / "bd.xlsx", cuis={(1, 1): "2227389"})
    ws = openpyxl.load_workbook(salida)["Base de Datos"]
    assert ws["H2"].value == "2227389"
    assert ws["U2"].value == "POR VERIFICAR"


def test_excel_final_sin_factor_no_cambia_la_hoja(tmp_path):
    """Corrida sin el recorte (agent-bases no capturó la página): la hoja sale igual
    que siempre, sin imagen ni banda — no se rompe la generación."""
    salida = generar_excel_final(_ESPEJO_FACTOR, tmp_path / "sin_factor.xlsx")
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))
    assert _fila_de(ws, "FACTOR DE EVALUACIÓN") == 0
    assert _fila_de(ws, "AÑOS EFECTIVOS") > 0
    assert not ws._images


def test_regenerar_excel_final_conserva_los_embeds(tmp_path):
    """Regresión: `regenerar_excel_final` no pasaba `certificados`, así que el
    backfill dejaba el entregable SIN ninguna imagen (constancias, TDR, Anexo). Ahora
    mapea la carpeta `certs/` hermana del Excel."""
    from entregables import regenerar_excel_final

    job = tmp_path / "job-1"
    (job / "certs").mkdir(parents=True)
    _pdf_una_pagina(job / "certs" / "P1_FACTOR.pdf", "FACTOR A - EXPERIENCIA ADICIONAL")
    _pdf_una_pagina(job / "certs" / "P1_E1.pdf", "CONSTANCIA")

    salida = regenerar_excel_final(_ESPEJO_FACTOR, {}, job / "final.xlsx")
    ws = next(s for s in openpyxl.load_workbook(salida).worksheets if s.title.startswith("P1"))
    assert len(ws._images) == 2        # constancia de la experiencia + factor
    fila_anios = _fila_de(ws, "AÑOS EFECTIVOS")
    assert fila_anios > 0
    assert _fila_de(ws, "FACTOR DE EVALUACIÓN") > fila_anios


def test_generar_excel_parte_1_documento_o_descripcion(tmp_path):
    espejo = {
        "_meta": {"analisis_id": "test", "concurso": "C", "postor": "P"},
        "postor": {
            "formularios": [
                {"anexo": "Anexo 1", "documento": "Documento Vigente", "folio": "10"},
                {"anexo": "Anexo 2", "descripcion": "Descripcion Trujillo", "folio": "20"}
            ]
        },
        "profesionales": [],
        "resumen_evaluacion": {"factores": []}
    }
    salida = tmp_path / "claude.xlsx"
    generar_excel(espejo, salida)
    wb = openpyxl.load_workbook(salida)
    ws = wb["CLAUDE"]
    texto = "\n".join(str(c.value) for fila in ws.iter_rows() for c in fila if c.value)
    assert "Documento Vigente" in texto
    assert "Descripcion Trujillo" in texto


def test_excel_cui_rotulo_distingue_certificado_vs_sistema(tmp_path):
    """Fix #60: El rótulo CÓDIGO (CUI/SNIP) distingue si el CUI vino en el certificado
    o fue identificado por el sistema."""
    espejo = {
        "_meta": {"analisis_id": "test", "concurso": "C", "postor": "P"},
        "postor": {"formularios": []},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "JUAN PEREZ",
            "experiencias": [
                {"n": 1, "proyecto": "OBRA 1", "cui": "111111"},
                {"n": 2, "proyecto": "OBRA 2", "cui": None}
            ]
        }],
        "resumen_evaluacion": {"factores": []}
    }
    cuis = {(1, 1): "111111", (1, 2): "222222"}
    salida = tmp_path / "rotulo.xlsx"
    generar_excel_final(espejo, salida, cuis=cuis)
    wb = openpyxl.load_workbook(salida)
    ws = next(s for s in wb.worksheets if s.title.startswith("P1"))
    celdas = [str(c.value) for r in ws.iter_rows() for c in r if c.value]

    assert "CUI 111111 (declarado y utilizado)" in celdas
    assert "CUI declarado: no consignado · CUI utilizado: 222222" in celdas
    assert "Citado en el certificado y verificado: 111111" not in celdas


@pytest.mark.parametrize("tipo_evaluacion", ["obras", "expedientes"])
@pytest.mark.parametrize(
    ("declarado", "utilizado", "con_revision", "esperado"),
    [
        ("111111", None, True,
         "CUI declarado: 111111 · CUI utilizado: no registrado"),
        ("111111", "111111", False, "CUI 111111 (declarado y utilizado)"),
        ("111111", "222222", False,
         "CUI declarado: 111111 · CUI utilizado: 222222"),
        (None, "222222", False,
         "CUI declarado: no consignado · CUI utilizado: 222222"),
        (None, None, False,
         "CUI declarado: no consignado · CUI utilizado: no registrado"),
    ],
)
def test_generar_excel_final_rotula_procedencia_cui_en_ambas_rutas(
    tmp_path, tipo_evaluacion, declarado, utilizado, con_revision, esperado
):
    """El generador conserva declarado/utilizado sin convertir igualdad en verificación."""
    espejo = {
        "_meta": {"tipo_evaluacion": tipo_evaluacion}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "experiencias": [{
                "n": 1, "proyecto": "Obra de prueba", "cui": declarado,
                "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31",
            }],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    cuis = {(1, 1): utilizado} if utilizado else {}
    fichas = {(1, 1): {"cui": utilizado}} if utilizado is not None else {}
    revisiones = {(1, 1): "REVISION"} if con_revision else {}
    salida = generar_excel_final(
        espejo, tmp_path / f"{tipo_evaluacion}-{declarado}-{utilizado}.xlsx",
        cuis=cuis, fichas=fichas, revisiones=revisiones,
    )
    texto = _texto(_hoja_de(salida, 1, "JEFE"))
    assert esperado in texto
    assert "Citado en el certificado y verificado:" not in texto
    ws = _hoja_de(salida, 1, "JEFE")
    fila_cui = next(c.row for fila in ws.iter_rows()
                    for c in fila if c.value == "CÓDIGO (CUI/SNIP)")
    assert ws.cell(fila_cui, 2).value == esperado
    encabezado = next(c.value for fila in ws.iter_rows() for c in fila
                      if isinstance(c.value, str) and c.value.startswith("EXPERIENCIA 1:"))
    assert esperado in encabezado


@pytest.mark.parametrize("tipo_evaluacion", ["obras", "expedientes"])
def test_generar_excel_final_no_promueve_cui_declarado_sin_mapa_ni_ficha(
    tmp_path, tipo_evaluacion
):
    from entregables import desempaquetar_enriquecimiento

    # Este es el caso observado: REVISION conserva la procedencia del backend,
    # pero no registra un CUI utilizado; el CUI del certificado sigue siendo solo
    # declarado.
    _, cuis, fichas, _ = desempaquetar_enriquecimiento({
        "1:1": {"via": "REVISION", "cui": None, "sin_verificar": True},
    })
    espejo = {
        "_meta": {"tipo_evaluacion": tipo_evaluacion}, "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "experiencias": [{"n": 1, "proyecto": "Divino Niño", "cui": "2458463"}],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    salida = generar_excel_final(
        espejo, tmp_path / f"sin-promocion-{tipo_evaluacion}.xlsx",
        cuis=cuis, fichas=fichas,
    )
    ws = _hoja_de(salida, 1, "JEFE")
    esperado = "CUI declarado: 2458463 · CUI utilizado: no registrado"
    fila_cui = next(c.row for fila in ws.iter_rows()
                    for c in fila if c.value == "CÓDIGO (CUI/SNIP)")
    assert ws.cell(fila_cui, 2).value == esperado
    encabezado = next(c.value for fila in ws.iter_rows() for c in fila
                      if isinstance(c.value, str) and c.value.startswith("EXPERIENCIA 1:"))
    assert esperado in encabezado
    assert "CUI 2458463" not in ws.cell(fila_cui, 2).value




def test_folio_no_verificado_no_embebe_y_avisa(tmp_path):
    """#47: si la skill no pudo confirmar que la pagina citada muestre al emisor
    (folio_verificado=False), el certificado NO se embebe y el aviso queda
    visible — una imagen equivocada es el sustento que audita el Comite."""
    import copy
    espejo = copy.deepcopy(_ESPEJO_1EXP)
    espejo["profesionales"][0]["experiencias"][0]["folio_verificado"] = False
    espejo["profesionales"][0]["experiencias"][0]["folio"] = "358"
    salida = generar_excel_final(espejo, tmp_path / "f47.xlsx")
    t = _texto(_hoja_de(salida, 1, "JEFE"))
    assert "DOCUMENTO NO EMBEBIDO" in t and "358" in t


def test_folio_verificado_true_no_cambia_nada(tmp_path):
    import copy
    espejo = copy.deepcopy(_ESPEJO_1EXP)
    espejo["profesionales"][0]["experiencias"][0]["folio_verificado"] = True
    salida = generar_excel_final(espejo, tmp_path / "f47b.xlsx")
    assert "DOCUMENTO NO EMBEBIDO" not in _texto(_hoja_de(salida, 1, "JEFE"))
