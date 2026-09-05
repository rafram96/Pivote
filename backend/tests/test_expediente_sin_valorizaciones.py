"""
Caso real (5-sep, corrida de expedientes): la experiencia «Elaboración del
Expediente Técnico del Proyecto IE 86127» fue enrutada como expediente
(`camino=expediente`, `camino_fuente=declarado`), pero el Excel pintó las 62
valorizaciones de la CONSTRUCCIÓN y el ZIP bajó 208 archivos de la obra. Motivo:
la hoja decidía por «¿hay verificación MEF?» y el MEF no publicaba contrato para
ese CUI; la descarga no miraba el camino en absoluto.

Regla: el camino declarado manda. Un expediente sin fuente pública dice «POR
VERIFICAR», nunca muestra ni descarga la fase de ejecución.
"""
from __future__ import annotations

import openpyxl

from entregables.excel_final import generar_excel_final
from schemas.cargo import etiqueta_hoja
from orquestador.etapas_reales import (
    SECCIONES_EXPEDIENTE, secciones_descarga_por_camino,
)


def test_secciones_por_camino():
    assert secciones_descarga_por_camino({"expediente"}) == SECCIONES_EXPEDIENTE
    assert secciones_descarga_por_camino(["expediente", "expediente"]) == SECCIONES_EXPEDIENTE
    # alguna de obra, o sin camino registrado (espejo viejo) → todo, como antes
    assert secciones_descarga_por_camino({"expediente", "obra"}) is None
    assert secciones_descarga_por_camino({"obra"}) is None
    assert secciones_descarga_por_camino({"desconocido"}) is None
    assert secciones_descarga_por_camino(set()) is None
    assert secciones_descarga_por_camino(None) is None


def _espejo():
    return {
        "_meta": {"analisis_id": "exp-001", "concurso": "CP-EXP", "postor": "P",
                  "tipo_evaluacion": "expedientes"},
        "postor": {},
        "profesionales": [{
            "n_prof": 2, "cargo": "GESTOR BIM", "nombre": "Profesional Dos",
            "colegiatura": "CIP 1", "cumple": "CUMPLE — x",
            "total": {"dias": 400, "anios": 1.1},
            "experiencias": [{
                "n": 1, "proyecto": "Elaboración del Expediente Técnico del Proyecto IE 86127",
                "entidad_emisora": "GORE", "ruc_emisor": "20123456789",
                "fecha_inicial": "2021-05-01", "fecha_final": "2022-06-30",
                "dias": 400, "folio": "10"}],
        }],
        "resumen_evaluacion": {"factores": []},
    }


def _texto_hoja(ws) -> str:
    return " || ".join(str(c.value) for fila in ws.iter_rows() for c in fila
                       if c.value not in (None, ""))


def test_expediente_sin_fuente_mef_no_pinta_valorizaciones(tmp_path):
    ficha = {"cui": "2513467", "codigo_infoobras": 144197, "estado": "Finalizado",
             "monto": 1_000_000, "fecha_inicio": "2022-01-01", "fecha_fin": "2023-06-30",
             "camino": "expediente", "camino_fuente": "declarado",
             "valorizaciones": [{"anio": 2022, "mes": m, "fisico_real": 0.1 * m,
                                 "valorizado_real": 1000 * m, "estado": "Valorizado", "docs": 3}
                                for m in range(1, 7)]}
    salida = generar_excel_final(_espejo(), tmp_path / "f.xlsx", {},
                                 fichas={(2, 1): ficha})
    wb = openpyxl.load_workbook(salida)
    hoja = wb[etiqueta_hoja(2, "GESTOR BIM")]
    texto = _texto_hoja(hoja)
    assert "EXPEDIENTE TÉCNICO — verificación" in texto
    assert "POR VERIFICAR — ni el MEF ni InfoObras publican" in texto
    assert "VALORIZACIONES — en amarillo" not in texto
    assert "2022 / Marzo" not in texto            # ninguna fila de valorización


def test_obra_sigue_pintando_valorizaciones(tmp_path):
    espejo = _espejo()
    espejo["_meta"]["tipo_evaluacion"] = "obras"
    espejo["profesionales"][0]["experiencias"][0]["proyecto"] = "Supervisión de la obra IE 86127"
    ficha = {"cui": "2513467", "codigo_infoobras": 144197, "estado": "Finalizado",
             "monto": 1_000_000, "fecha_inicio": "2021-01-01", "fecha_fin": "2022-12-31",
             "camino": "obra", "camino_fuente": "declarado",
             "valorizaciones": [{"anio": 2022, "mes": 3, "fisico_real": 0.3,
                                 "valorizado_real": 3000, "estado": "Valorizado", "docs": 3}]}
    salida = generar_excel_final(espejo, tmp_path / "o.xlsx", {},
                                 fichas={(2, 1): ficha})
    wb = openpyxl.load_workbook(salida)
    hoja = wb[etiqueta_hoja(2, "GESTOR BIM")]
    texto = _texto_hoja(hoja)
    assert "VALORIZACIONES — en amarillo" in texto
    assert "EXPEDIENTE TÉCNICO — verificación" not in texto
