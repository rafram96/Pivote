"""Coherencia entre período, resumen compacto y conclusión de expedientes."""
from __future__ import annotations

import openpyxl

from entregables.excel_final import (desempaquetar_enriquecimiento,
                                     generar_excel_final,
                                     inyectar_veredicto_backend,
                                     presentacion_cruces)


def test_parte_5_conserva_no_computable_y_distingue_totales(tmp_path):
    espejo = {"_meta": {"tipo_evaluacion": "expedientes"},
              "reglas_evaluacion": {"periodos_sin_dia": "no_definida"},
              "profesionales": [{"n_prof": 1, "nombre": "PERSONA FICTICIA",
                                  "cargo": "ESPECIALISTA", "requisitos": {},
                                  "experiencias": [
                                      {"n": 1, "proyecto": "EXPEDIENTE A",
                                       "entidad_emisora": "ENTIDAD", "cargo_ocupado": "CARGO",
                                       "fecha_inicial": "2024-01-01", "fecha_final": "2024-01-31",
                                       "dias": 999},
                                      {"n": 2, "proyecto": "EXPEDIENTE B",
                                       "entidad_emisora": "ENTIDAD", "cargo_ocupado": "CARGO",
                                       "fecha_inicial": None, "fecha_final": None},
                                  ]}]}
    enr = {"1:1": {"via": "CUI_TEXTO", "cui": "7000001",
                    "obra_nombre": "OBRA FICTICIA", "codigo_infoobras": "X",
                    "modificaciones_plazo": [{"tipo": "AMPLIACIÓN", "dias": 10}],
                    "representante_obra": {"nombre": "REPRESENTANTE FICTICIO"},
                    "sub_obras": [{"estado": "resuelto", "cui": "7000002",
                                    "proyecto": "SUBOBRA FICTICIA",
                                    "ficha": {"representante_obra": {
                                        "nombre": "REPRESENTANTE SUBOBRA"}}}]},
           "1:2": {"via": "REVISION", "sin_verificar": True}}
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "final.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    wb = openpyxl.load_workbook(salida)
    hoja = next(ws for ws in wb.worksheets if ws.title.startswith("P1."))
    texto = "\n".join(str(c.value) for row in hoja.iter_rows() for c in row
                       if c.value is not None)
    # leyenda de una línea (limpieza del 12-sep): la explicación larga se retiró
    assert "Efectivo = aporte antes de descontar traslapes." in texto
    assert "Efectivo computado" not in texto
    assert "No computado" in texto
    assert "TOTAL DECLARADO POR EXPERIENCIAS" in texto
    assert "SUMA COMPUTADA ANTES DE TRASLAPES" in texto
    assert "TOTAL EFECTIVO NETO" in texto
    assert "999" not in [str(hoja.cell(r, 18).value) for r in range(1, hoja.max_row + 1)]
    assert "PERIODO (InfoObras)" not in texto
    assert "REPRESENTANTE DE OBRA" not in texto
    assert "MODIFICACIONES DE PLAZO" not in texto
    assert "REPRESENTANTE SUBOBRA" not in texto


def test_alias_na_es_privado_solo_en_concurso_expedientes(tmp_path):
    exp = {"n": 1, "proyecto": "EXPERIENCIA PRIVADA", "entidad_emisora": "EMPRESA",
           "cargo_ocupado": "ESPECIALISTA", "fecha_inicial": "2024-01-01",
           "fecha_final": "2024-01-31"}
    fx = {"via": "NA"}
    cruce_exp = presentacion_cruces(exp, fx, "expedientes")
    cruce_obra = presentacion_cruces(exp, fx, "obras")
    assert "OBRA PRIVADA" in cruce_exp["resp_a"]
    assert "OBRA PRIVADA" not in cruce_obra["resp_a"]

    espejo = {"_meta": {"tipo_evaluacion": "expedientes"},
              "profesionales": [{"n_prof": 1, "nombre": "PERSONA FICTICIA",
                                  "cargo": "ESPECIALISTA", "requisitos": {},
                                  "experiencias": [exp]}]}
    enr = {"1:1": fx}
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "na.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    hoja = next(ws for ws in openpyxl.load_workbook(salida).worksheets
                if ws.title.startswith("P1."))
    texto = "\n".join(str(c.value) for row in hoja.iter_rows() for c in row
                       if c.value is not None)
    assert "identificación del emisor privado pendiente" in texto
    assert "identificación del expediente pendiente" not in texto
