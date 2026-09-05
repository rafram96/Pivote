"""Regresiones de paridad entre enriquecimiento crudo y fichas del Excel."""
from __future__ import annotations

import openpyxl

from entregables.certeza import clasificar_identificacion, fuente_mef
from entregables.excel_final import (
    _bloques_linea_de_tiempo,
    desempaquetar_enriquecimiento,
    generar_excel_final,
)
from entregables.expedientes import reconciliar_expedientes
from schemas.cargo import etiqueta_hoja


CARGO = "ESPECIALISTA EN ESTRUCTURAS"


def _espejo():
    return {
        "_meta": {"tipo_evaluacion": "expedientes", "analisis_id": "proyeccion",
                  "concurso": "CP-SINTETICO/2026", "postor": "POSTOR SINTETICO"},
        "postor": {},
        "reglas_evaluacion": {"periodos_sin_dia": "no_definida"},
        "profesionales": [{
            "n_prof": 1, "nombre": "Persona Sintética", "cargo": CARGO,
            "cumple": "CUMPLE histórico",
            "requisitos": {"experiencia": "Experiencia mínima: 1 año"},
            "experiencias": [
                {"n": 1, "proyecto": "Expediente con CUI citado",
                 "entidad_emisora": "Entidad Pública", "cargo_ocupado": "Especialista",
                 "fecha_inicial": "2020-01-01", "fecha_final": "2020-01-31"},
                {"n": 2, "proyecto": "Expediente privado identificado",
                 "entidad_emisora": "Privada Uno", "cargo_ocupado": "Especialista",
                 "fecha_inicial": "2020-02-01", "fecha_final": "2020-02-29"},
                {"n": 3, "proyecto": "Expediente privado pendiente",
                 "entidad_emisora": "Privada Dos", "cargo_ocupado": "Especialista",
                 "fecha_inicial": "2020-03-01", "fecha_final": "2020-03-31"},
                {"n": 4, "proyecto": "Certificado de dos expedientes",
                 "entidad_emisora": "Consorcio Público", "cargo_ocupado": "Especialista",
                 "fecha_inicial": "2020-04-01", "fecha_final": "2020-04-30"},
                {"n": 5, "proyecto": "Expediente con fechas invertidas",
                 "entidad_emisora": "Entidad Pública", "cargo_ocupado": "Especialista",
                 "fecha_inicial": "2020-06-30", "fecha_final": "2020-06-01"},
            ],
        }],
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    }


def _enriquecimiento():
    return {
        "1:1": {"via": "CUI_TEXTO", "cui": "1234567", "sin_verificar": True},
        "1:2": {"via": "PRIVADA", "sunat": {"ruc": "20123456789"}},
        "1:3": {"via": "PRIVADA"},
        "1:4": {"via": "MULTI_OBRA", "sub_obras": [
            {"estado": "sin_resolver"}, {"estado": "sin_resolver"},
        ]},
        "1:5": {"via": "NOMBRE", "cui": "7654321"},
    }


def _fila_experiencia(ws, numero):
    cabecera = next(
        c.row for fila in ws.iter_rows() for c in fila
        if c.value == "Declarado (días)"
    )
    return next(
        c.row for fila in ws.iter_rows(min_row=cabecera + 1) for c in fila
        if c.column == 1 and c.value == numero
    )


def _columna(ws, titulo):
    return next(c.column for fila in ws.iter_rows() for c in fila if c.value == titulo)


def test_proyeccion_conserva_cui_certeza_y_fuente_mef():
    espejo, crudo = _espejo(), _enriquecimiento()
    _, cuis, fichas, sunat = desempaquetar_enriquecimiento(crudo)
    experiencias = {e["n"]: e for e in espejo["profesionales"][0]["experiencias"]}

    assert cuis[(1, 1)] == "1234567"
    assert fichas[(1, 1)]["cui"] == "1234567"
    for numero, exp in experiencias.items():
        proyectado = {**fichas[(1, numero)], "sunat": sunat.get((1, numero))}
        assert clasificar_identificacion(exp, crudo[f"1:{numero}"]) == (
            clasificar_identificacion(exp, proyectado))
        assert fuente_mef(crudo[f"1:{numero}"]) == fuente_mef(proyectado)


def test_parte5_distingue_pendiente_computable_de_no_computado(tmp_path):
    espejo, crudo = _espejo(), _enriquecimiento()
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(crudo)
    salida = generar_excel_final(espejo, tmp_path / "proyeccion.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida, data_only=True)[etiqueta_hoja(1, CARGO)]
    fila = _fila_experiencia(ws, 1)
    observacion = str(ws.cell(fila, _columna(ws, "Observación breve")).value)

    assert ws.cell(fila, 18).value == 31
    assert ws.cell(fila, 19).value == 31
    assert "pendiente" in observacion.lower()
    assert "No computado" not in observacion


def test_parte5_excluye_invertida_sin_publicar_dias_negativos(tmp_path):
    espejo, crudo = _espejo(), _enriquecimiento()
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(crudo)
    salida = generar_excel_final(espejo, tmp_path / "invertida.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida, data_only=True)[etiqueta_hoja(1, CARGO)]
    fila = _fila_experiencia(ws, 5)
    observacion = str(ws.cell(fila, _columna(ws, "Observación breve")).value)

    assert ws.cell(fila, 18).value == "—"
    assert ws.cell(fila, 19).value == "No computado"
    assert "No computado" in observacion
    assert all(
        not isinstance(ws.cell(_fila_experiencia(ws, n), columna).value, (int, float))
        or ws.cell(_fila_experiencia(ws, n), columna).value >= 0
        for n in range(1, 6) for columna in (18, 19)
    )


def test_gantt_proyectado_repite_estado_del_reconciliado_api():
    espejo, crudo = _espejo(), _enriquecimiento()
    _, _, fichas, sunat = desempaquetar_enriquecimiento(crudo)
    proyectado = {
        f"1:{n}": {**fichas[(1, n)], "sunat": sunat.get((1, n))}
        for n in range(1, 6)
    }
    esperado = reconciliar_expedientes(espejo, crudo)[1]
    proyectado_resultado = reconciliar_expedientes(espejo, proyectado)[1]
    bloque = _bloques_linea_de_tiempo(espejo, fichas, "expedientes")[0]

    assert proyectado_resultado["dias_efectivos"] == esperado["dias_efectivos"]
    assert proyectado_resultado["cumple_backend"] == esperado["cumple_backend"]
    assert f"{esperado['dias_efectivos']} días efectivos" in bloque["cabecera"]
    assert bloque["cabecera"].endswith("POR VERIFICAR")
