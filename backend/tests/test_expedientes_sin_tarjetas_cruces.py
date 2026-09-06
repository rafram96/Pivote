"""Retirar repetición visual sin perder incidencias ni tocar la ruta de obras."""
import openpyxl
import pytest

from entregables.excel_final import (
    _bloques_linea_de_tiempo, desempaquetar_enriquecimiento, generar_excel_final,
)

TITULO_ANTERIOR = "CRUCE DE FECHAS CONTRA EL CONTRATO Y LA APROBACIÓN DEL EXPEDIENTE"


def _datos(tipo="expedientes", resultado="dispara", inferida=False):
    espejo = {
        "_meta": {"tipo_evaluacion": tipo},
        "profesionales": [{"n_prof": 1, "nombre": "PERSONA FICTICIA", "cargo": "ESPECIALISTA",
                           "requisitos": {}, "experiencias": [{
                               "n": 1, "proyecto": "PROYECTO FICTICIO",
                               "fecha_inicial": "2024-01-01", "fecha_final": "2024-12-31"}]}],
    }
    enr = {"1:1": {"via": "CUI_TEXTO", "cui": "9000010", "cruces_fechas": [
        {"regla": "FECHA_CONTRATO", "resultado": resultado,
         "fecha_fuente": "2024-02-01", "motivo": "Motivo de inicio conservado."},
        {"regla": "FECHA_APROBACION_ET", "resultado": "coincide",
         "fecha_fuente": "2025-01-01", "inferida": inferida,
         "motivo": "Motivo de aprobación conservado."}]}}
    return espejo, enr


def _generar(tmp_path, espejo, enr):
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    bloques = _bloques_linea_de_tiempo(espejo, fichas, espejo["_meta"]["tipo_evaluacion"])
    salida = generar_excel_final(espejo, tmp_path / "final.xlsx", paral, cuis, fichas, {}, sunat)
    wb = openpyxl.load_workbook(salida)
    return wb, next(ws for ws in wb if ws.title.startswith("P1.")), bloques


@pytest.mark.parametrize("resultado,color,respuesta", [
    ("dispara", "FFC7CE", "NO"), ("por_confirmar", "FFF2CC", "POR VERIFICAR"),
])
def test_incidente_queda_en_ficha_con_motivos_y_en_gantt(tmp_path, resultado, color, respuesta):
    wb, ws, bloques = _generar(tmp_path, *_datos(resultado=resultado))
    assert TITULO_ANTERIOR not in [c.value for c in ws["A"]]
    nota = next(c for c in ws["A"] if str(c.value).startswith("Observación de fechas —"))
    p5 = next(c.row for c in ws["A"] if str(c.value).startswith("PARTE 5"))
    assert nota.row < p5
    assert "Inicio frente al contrato: " + respuesta in nota.value
    assert "Motivo de inicio conservado." in nota.value
    assert "Motivo de aprobación conservado." in nota.value
    assert nota.fill.fgColor.rgb.endswith(color)
    assert "Inicio frente al contrato: " + respuesta in bloques[0]["filas"][0]["rotulo"]
    assert len(ws._images) == 1
    assert ws._images[0].anchor._from.row + 1 > p5
    assert "TOTAL EFECTIVO NETO" in [c.value for c in ws["A"]]
    assert "CONCLUSIÓN DEL TIEMPO EFECTIVO" in [c.value for c in ws["A"]]
    wb.close()


def test_sin_incidencias_no_agrega_nota_redundante(tmp_path):
    wb, ws, _ = _generar(tmp_path, *_datos(resultado="coincide"))
    assert not any(str(c.value).startswith("Observación de fechas —") for c in ws["A"])
    assert TITULO_ANTERIOR not in [c.value for c in ws["A"]]
    wb.close()


def test_fecha_inferida_se_explica_aunque_ambos_cruces_sean_compatibles(tmp_path):
    wb, ws, _ = _generar(tmp_path, *_datos(resultado="coincide", inferida=True))
    nota = next(c for c in ws["A"] if str(c.value).startswith("Observación de fechas —"))
    assert "Fecha de aprobación inferida: 01/01/2025" in nota.value
    assert nota.fill.fgColor.rgb.endswith("E4D7F5")
    wb.close()


@pytest.mark.parametrize("via", [None, "PRIVADA", "NA"])
def test_ausencia_de_fuente_y_ruta_privada_no_desaparecen(tmp_path, via):
    espejo, _ = _datos()
    wb, ws, _ = _generar(tmp_path, espejo, {"1:1": {"via": via}})
    nota = next(c for c in ws["A"] if str(c.value).startswith("Observación de fechas —"))
    assert "POR VERIFICAR" in nota.value
    if via:
        assert "InfoObras, MEF y SEACE no aplican" in nota.value
    assert nota.fill.fgColor.rgb.endswith("FFF2CC")
    wb.close()


def test_obras_conserva_tarjetas_y_no_recibe_nota_nueva(tmp_path):
    wb, ws, _ = _generar(tmp_path, *_datos(tipo="obras"))
    assert TITULO_ANTERIOR in [c.value for c in ws["A"]]
    assert not any(str(c.value).startswith("Observación de fechas —") for c in ws["A"])
    assert not ws._images
    wb.close()
