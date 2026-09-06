"""Regresiones de presentación del Gantt (datos sintéticos, sin red)."""
from __future__ import annotations

import openpyxl

from entregables.excel_final import HOJA_CRONOLOGIA, construir_hoja_cronologia


def _hoja(experiencias, fichas):
    espejo = {
        "_meta": {"tipo_evaluacion": "expedientes"},
        "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [{"n_prof": 1, "nombre": "PERSONA FICTICIA",
                           "cargo": "ESPECIALISTA", "experiencias": experiencias}],
    }
    ws = openpyxl.Workbook().active
    ws.title = HOJA_CRONOLOGIA
    construir_hoja_cronologia(ws, espejo, fichas)
    return ws


def test_gantt_ordena_por_fechas_sin_renumerar_la_identidad_del_escaneado():
    from copy import deepcopy
    experiencias = [
        {"n": 1, "proyecto": "Proyecto reciente", "paginas_pdf": [20],
         "fecha_inicial": "2024-01-01", "fecha_final": "2024-06-30"},
        {"n": 2, "proyecto": "Proyecto antiguo", "paginas_pdf": [21],
         "fecha_inicial": "2020-01-01", "fecha_final": "2020-06-30"},
    ]
    copia = deepcopy(experiencias)
    ws = _hoja(experiencias, {(1, 1): {"via": "CUI_TEXTO", "cui": "9000001"},
                             (1, 2): {"via": "CUI_TEXTO", "cui": "9000002"}})
    rotulos = [c.value for c in ws["A"] if isinstance(c.value, str)
               and c.value.startswith(("1 ·", "2 ·")) and "Inicio:" in c.value]
    assert len(rotulos) == 2
    assert rotulos[0].startswith("2 ·") and "Proyecto antiguo" in rotulos[0] and "9000002" in rotulos[0]
    assert rotulos[1].startswith("1 ·") and "Proyecto reciente" in rotulos[1] and "9000001" in rotulos[1]
    assert experiencias == copia


def test_estados_no_y_pendiente_son_visibles_y_el_detalle_sigue_en_comentario():
    ws = _hoja(
        [{"n": 1, "proyecto": "Expediente ficticio con contradicción",
          "fecha_inicial": "2022-01-01", "fecha_final": "2022-06-30"},
         {"n": 2, "proyecto": "Expediente ficticio sin confirmación",
          "fecha_inicial": "2022-07-01", "fecha_final": "2022-12-31"}],
        {(1, 1): {"via": "CUI_TEXTO", "cui": "9000010",
                  "cruces_fechas": [
                      {"regla": "FECHA_CONTRATO", "resultado": "dispara",
                       "motivo": "detalle A"},
                      {"regla": "FECHA_APROBACION_ET", "resultado": "dispara",
                       "motivo": "detalle B"}]},
         (1, 2): {"via": "REVISION", "cruces_fechas": [
             {"regla": "FECHA_CONTRATO", "resultado": "por_confirmar",
              "motivo": "abstención A"},
             {"regla": "FECHA_APROBACION_ET", "resultado": "por_confirmar",
              "motivo": "abstención B"}]}},
    )
    rotulos = [c.value for c in ws["A"] if isinstance(c.value, str)]
    assert any("Inicio frente al contrato: NO" in r
               and "Término frente a aprobación: NO" in r for r in rotulos), rotulos
    assert any("Inicio frente al contrato: POR VERIFICAR" in r for r in rotulos)
    filas = [c.row for c in ws["A"] if isinstance(c.value, str)
             and "Inicio frente al contrato:" in c.value]
    assert len(filas) == 2
    assert all(ws.cell(f, 1).comment is not None for f in filas)
    assert all("detalle" in ws.cell(f, 1).comment.text
               or "abstención" in ws.cell(f, 1).comment.text for f in filas)


def test_periodo_declarado_y_ano_parcial_son_legibles_y_el_pdf_no_usa_relleno():
    ws = _hoja(
        [{"n": 1, "proyecto": "Expediente anual ficticio",
          "fecha_inicial": "2022-01-01", "fecha_final": "2022-01-31"}],
        {},
    )
    textos = [c.value for fila in ws.iter_rows() for c in fila
              if isinstance(c.value, str)]
    assert "PERÍODO DECLARADO" in textos
    fila_eje = next(c.row for c in ws["A"] if c.value == "Eje: bimestres")
    # Un rango corto usa meses; el año visible sigue siendo de cuatro dígitos.
    assert ws.cell(fila_eje, 2).value == 2022
    assert ws.column_dimensions["B"].width == 2.4
    assert ws.print_area.startswith("'Cronología de expedientes'!$A$1:$CB$")
    assert ws.page_setup.orientation == ws.ORIENTATION_LANDSCAPE
    assert ws.page_setup.fitToWidth is None
    assert ws.page_setup.fitToHeight is None
    assert ws.sheet_properties.pageSetUpPr.fitToPage is False
    assert 10 <= ws.page_setup.scale <= 100


def test_privada_y_sin_fechas_conserva_abstencion_visible():
    ws = _hoja(
        [{"n": 1, "proyecto": "Certificado privado ficticio",
          "fecha_inicial": "SIN DATO", "fecha_final": "SIN DATO"}],
        {(1, 1): {"via": "PRIVADA", "privada_pendiente": True}},
    )
    rotulo = next(c.value for c in ws["A"] if isinstance(c.value, str)
                  and "Certificado privado ficticio" in str(c.value))
    assert "Inicio frente al contrato: REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" in rotulo
    assert "Término frente a aprobación: POR VERIFICAR" in rotulo
    assert "sin fechas computables" in rotulo


def test_salto_antes_de_inicio_separa_cui_y_pregunta():
    ws = _hoja(
        [{"n": 1, "proyecto": "Expediente separado",
          "fecha_inicial": "2022-01-01", "fecha_final": "2022-03-31"}],
        {(1, 1): {"via": "REVISION"}},
    )
    rotulo = next(c.value for c in ws["A"] if isinstance(c.value, str)
                  and "Expediente separado" in str(c.value))
    assert "CUI" in rotulo
    assert " · \nInicio frente al contrato:" not in rotulo
    assert "\nInicio frente al contrato:" in rotulo


def test_privada_no_pendiente_conserva_no_aplica_completo():
    ws = _hoja(
        [{"n": 1, "proyecto": "Expediente privado identificado",
          "fecha_inicial": "2021-01-01", "fecha_final": "2021-03-31"}],
        {(1, 1): {"via": "PRIVADA", "privada_pendiente": False,
                  "tipo_experiencia": "expediente"}},
    )
    rotulo = next(c.value for c in ws["A"] if isinstance(c.value, str)
                  and "Expediente privado identificado" in str(c.value))
    assert "Inicio frente al contrato: FUENTE PÚBLICA NO APLICA — OBRA PRIVADA" in rotulo
    assert ("Término frente a aprobación: POR VERIFICAR — sin fuente pública "
            "localizada; revisar el sustento privado") in rotulo


def test_anos_rotados_solo_para_tramo_de_un_mes():
    casos = [
        ("2022-01-01", "2023-06-30", False),   # mensual: años parciales, varios slots
        ("2008-01-01", "2025-06-30", False),
        ("2003-01-01", "2025-06-30", False),
    ]
    for inicio, fin, rotado in casos:
        ws = _hoja([{"n": 1, "proyecto": "Escala ficticia",
                     "fecha_inicial": inicio, "fecha_final": fin}], {})
        fila = next(c.row for c in ws["A"] if c.value == "Eje: bimestres")
        assert (ws.cell(fila, 2).alignment.textRotation == 90) is rotado
        assert ws.row_dimensions[fila].height == (36 if rotado else 14)
        assert ws.column_dimensions["B"].width == 2.4

    ws = _hoja([{"n": 1, "proyecto": "Trimestre parcial",
                 "fecha_inicial": "2020-12-01", "fecha_final": "2026-03-31"}], {})
    fila = next(c.row for c in ws["A"] if c.value == "Eje: bimestres")
    assert ws.cell(fila, 2).value == 2020
    assert ws.cell(fila, 2).alignment.textRotation == 90
    assert ws.row_dimensions[fila].height == 36


def test_ficha_larga_envuelve_y_layout_legacy_no_recibe_page_setup():
    entidad = "Entidad convocante ficticia " + "con una denominación extraordinariamente larga " * 8
    ws = _hoja(
        [{"n": 1, "proyecto": "Proyecto con ficha SEACE larga",
          "fecha_inicial": "2022-01-01", "fecha_final": "2022-03-31"}],
        {(1, 1): {"via": "CUI_TEXTO", "cui": "9000011",
                  "obra_nombre": "Proyecto con ficha SEACE larga",
                  "seace": {"estado": "seleccionado",
                            "proceso": {"nomenclatura": "CP-FICTICIO",
                                        "entidad_convocante": entidad,
                                        "fecha_firma": "2022-01-01"}}}},
    )
    fila_entidad = next(c.row for c in ws["A"] if c.value == "Entidad que convocó")
    assert ws.cell(fila_entidad, 4).value == entidad.strip()
    assert ws.row_dimensions[fila_entidad].height >= 28

    obras = {
        "_meta": {"tipo_evaluacion": "obras"},
        "profesionales": [{"n_prof": 1, "nombre": "LEGACY", "cargo": "CARGO",
                           "experiencias": [{"n": 1, "proyecto": "Obra legacy",
                                              "fecha_inicial": "2022-01-01",
                                              "fecha_final": "2022-03-31"}]}],
    }
    legacy = openpyxl.Workbook().active
    legacy.title = HOJA_CRONOLOGIA
    construir_hoja_cronologia(legacy, obras, {})
    assert legacy.column_dimensions["A"].width == 26
    assert legacy.page_setup.fitToWidth is None


def test_salto_de_fila_antes_de_todos_los_profesionales():
    espejo = {
        "_meta": {"tipo_evaluacion": "expedientes"},
        "profesionales": [
            {"n_prof": 1, "nombre": "UNO", "cargo": "C",
             "experiencias": [{"n": 1, "proyecto": "P1",
                                "fecha_inicial": "2022-01-01",
                                "fecha_final": "2022-03-31"}]},
            {"n_prof": 2, "nombre": "DOS", "cargo": "C",
             "experiencias": [{"n": 1, "proyecto": "P2",
                                "fecha_inicial": "2022-01-01",
                                "fecha_final": "2022-03-31"}]},
        ],
    }
    ws = openpyxl.Workbook().active
    ws.title = HOJA_CRONOLOGIA
    construir_hoja_cronologia(ws, espejo, {})
    p1 = next(c.row for c in ws["A"] if isinstance(c.value, str)
              and c.value.startswith("PROFESIONAL 1"))
    p2 = next(c.row for c in ws["A"] if isinstance(c.value, str)
              and c.value.startswith("PROFESIONAL 2"))
    saltos = {int(brk.id) for brk in ws.row_breaks.brk}
    assert saltos == {p1 - 1, p2 - 1}
