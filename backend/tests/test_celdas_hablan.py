"""
Las celdas del entregable HABLAN (#55 + pedido del 28-jul): una abstencion en
blanco obliga a buscar el porque en otro lado; la jerga interna no es idioma
del evaluador. Casos calcados del Excel real de urgente1 (job e7c0fff6afb1).
"""
from __future__ import annotations

import openpyxl

from scripts.generar_excel import _sin_jerga, generar_excel


def test_sin_jerga_limpia_lo_medido_en_urgente1():
    assert _sin_jerga("NO DETERMINADO — agent-propuesta-mapa no extrajo monto") \
        == "NO DETERMINADO — la lectura de la propuesta no extrajo monto"
    assert "Nota literal" in _sin_jerga("Traslape. ⟦crudo: El cargo es JEFE⟧")
    assert "⟦" not in _sin_jerga("x ⟦crudo: y⟧")
    assert _sin_jerga("funciones_similares=null") == "funciones: no constan en el certificado"
    assert _sin_jerga("El profesional n_prof=1 firma") == "El profesional profesional 1 firma"
    assert _sin_jerga(123) == 123 and _sin_jerga(None) is None


def _espejo(exp_extra=None, total=None):
    exp = {"n": 1, "entidad_emisora": "CONSORCIO X", "proyecto": "OBRA X",
           "fecha_inicial": "2015-10-12",
           "fecha_final": "POR VERIFICAR (fecha final ilegible en OCR)",
           "dias": None, "meses": None, "anios": None, "folio": 561}
    exp.update(exp_extra or {})
    return {"_meta": {"postor": "P", "concurso": "C"},
            "postor": {"formularios": [], "experiencia_postor": []},
            "profesionales": [{"n_prof": 3, "cargo": "INGENIERO DE CAMPO",
                               "nombre": "N", "experiencias": [exp],
                               "total": total or {"dias": None, "meses": None, "anios": None}}],
            "resumen_evaluacion": {"factores": []}}


def _textos(ruta):
    wb = openpyxl.load_workbook(ruta)
    return [str(c.value) for ws in wb.worksheets for f in ws.iter_rows()
            for c in f if c.value is not None]


def test_abstencion_de_dias_dice_por_verificar(tmp_path):
    # el caso L86-N87: fecha final ilegible -> dias/meses/anios y TOTAL en blanco
    vals = _textos(generar_excel(_espejo(), tmp_path / "a.xlsx"))
    assert sum(1 for v in vals if v == "POR VERIFICAR") >= 3          # dias/meses/anios
    assert any("1 de 1 sin fechas verificables" in v for v in vals)   # el TOTAL explica
    assert any("No constan en el certificado" in v for v in vals)     # funciones null habla


def test_con_fechas_buenas_no_hay_sentinelas(tmp_path):
    e = {"fecha_final": "2016-05-01", "dias": 567, "meses": 18.9, "anios": 1.55}
    vals = _textos(generar_excel(_espejo(e, {"dias": 567, "meses": 18.9, "anios": 1.55}),
                                 tmp_path / "b.xlsx"))
    assert not any(v == "POR VERIFICAR" for v in vals)
    assert not any("sin fechas verificables" in v for v in vals)
