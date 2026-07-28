"""
Tests del bloque de OFERTA ECONÓMICA (#52): parser de rescate desde la prosa
del DETALLE + render siempre-visible con avisos. Sin red.

El caso de calibración es la PROSA REAL de Lircay-supervisión (auditoría
27-jul): los 3 montos existían pero vivían en el texto — y el parser ingenuo
capturaba «90» (del "90% de la cuantía") como límite inferior.
"""
from __future__ import annotations

import openpyxl

from scripts.generar_excel import _extraer_montos_prosa, generar_excel

# La prosa REAL (Lircay-supervisión, celda DETALLE) — abreviada sin alterar la
# estructura numérica que rompía al parser viejo.
PROSA_LIRCAY = (
    "La oferta del postor (S/15,003,890.90, folio 345) COINCIDE EXACTAMENTE, "
    "al céntimo, con el límite inferior calculado (90% de la cuantía "
    "S/16,670,989.88); el margen es CERO — la oferta está exactamente en el "
    "piso legal permitido, lo cual es inusual; se recomienda que el Comité "
    "verifique con especial cuidado el redondeo."
)


def test_prosa_real_lircay_rescata_cuantia_y_propuesta():
    r = _extraer_montos_prosa(PROSA_LIRCAY)
    assert r["cuantia"] == 16670989.88
    assert r["propuesta"] == 15003890.90


def test_prosa_real_lircay_no_inventa_el_90_como_limite():
    """Regresión del bug del parser inicial: «límite inferior calculado (90% …»
    producía limite_inferior=90.0. Un número sin forma de monto JAMÁS entra; y
    si la ventana pesca la cuantía, se descarta por coherencia. Preferimos un
    None ruidoso (candado OFERTA_INCOMPLETA) a un monto inventado."""
    r = _extraer_montos_prosa(PROSA_LIRCAY)
    assert r["limite_inferior"] != 90.0
    assert r["limite_inferior"] is None       # la prosa no trae el monto del límite


def test_prosa_etiquetada_rescata_los_tres():
    prosa = ("Cuantía: S/ 1,234,567.00 · Límite inferior: S/ 1,111,110.30 · "
             "Propuesta económica: S/ 1,200,000.00 (folio 12)")
    r = _extraer_montos_prosa(prosa)
    assert r == {"cuantia": 1234567.0, "limite_inferior": 1111110.30,
                 "propuesta": 1200000.0}


def test_sin_montos_con_forma_no_rescata_nada():
    r = _extraer_montos_prosa("La propuesta cumple el 90% y el puntaje es 100.")
    assert r == {"cuantia": None, "limite_inferior": None, "propuesta": None}


def test_formato_es_pe_con_puntos_de_miles():
    r = _extraer_montos_prosa("cuantía asciende a S/ 16.670.989,88 según bases")
    assert r["cuantia"] == 16670989.88


# ── render: el bloque SIEMPRE se pinta y lo que falta GRITA ──────────────────

def _espejo_min(oferta: dict | None) -> dict:
    return {"_meta": {"postor": "CONSORCIO X", "concurso": "CP-TEST"},
            "postor": {"formularios": [], "experiencia_postor": [],
                       **({"oferta_economica": oferta} if oferta is not None else {})},
            "profesionales": [], "resumen_evaluacion": {"factores": []}}


def _textos(ruta) -> str:
    wb = openpyxl.load_workbook(ruta)
    return "\n".join(str(c.value) for ws in wb.worksheets
                     for f in ws.iter_rows() for c in f if c.value is not None)


def test_bloque_oferta_se_pinta_aunque_falte_todo(tmp_path):
    salida = generar_excel(_espejo_min(None), tmp_path / "oe1.xlsx")
    t = _textos(salida)
    assert "CUANTÍA" in t and "LÍMITE INFERIOR" in t          # el bloque existe
    assert "OFERTA INCOMPLETA" in t                            # y grita


def test_rescate_desde_prosa_queda_marcado(tmp_path):
    salida = generar_excel(_espejo_min({"cuantia": None, "limite_inferior": None,
                                        "propuesta": None, "detalle": PROSA_LIRCAY}),
                           tmp_path / "oe2.xlsx")
    t = _textos(salida)
    assert "recuperado" in t                                   # rescate visible
    assert "OFERTA INCOMPLETA" in t and "LÍMITE INFERIOR" in t  # lo no rescatado grita


def test_oferta_completa_sin_avisos(tmp_path):
    salida = generar_excel(_espejo_min({"cuantia": 100.0, "limite_inferior": 90.0,
                                        "propuesta": 95.0, "detalle": ""}),
                           tmp_path / "oe3.xlsx")
    t = _textos(salida)
    assert "OFERTA INCOMPLETA" not in t and "recuperado" not in t
