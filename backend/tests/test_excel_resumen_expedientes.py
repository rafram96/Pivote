"""
PARTE 5 de un concurso de ELABORACIÓN DE EXPEDIENTES TÉCNICOS.

Qué se protege aquí
───────────────────
1. **Certeza de identificación por experiencia** (`entregables.certeza`): el
   evaluador tiene que ver si el CUI lo citó el certificado, lo confirmó un
   documento del MEF, lo dedujo el backend por el nombre, o no se sabe.
2. **Una sola fuente de días.** La tabla y la conclusión contaban cosas
   distintas: la tabla leía el ISO literal (descartando en silencio los
   certificados con mes y año) y la conclusión leía el reconciliado. Con el
   mínimo de 24 meses de por medio, eso llegó a imprimir «CUMPLE — 574 días».
   Aquí se exige que DÍAS EFECTIVOS DEL PROFESIONAL sea EXACTAMENTE
   `reconciliar_resultados_profesionales(...)[n]["dias_efectivos"]`.
3. **Que los colores no mientan**: el relleno de «Efectivo (días)» y la fila de
   totales a la que suman esos días salen de la misma clasificación.

Todos los nombres de personas y empresas son ficticios.
"""
from __future__ import annotations

import openpyxl
import pytest

from entregables import generar_excel_final
from entregables.certeza import (
    COLOR_INFERIDO, COLOR_PRIVADA, COLOR_SIN_IDENTIFICAR, COLOR_VERIFICADO,
    clasificar_identificacion, fuente_mef,
)
from entregables.excel_final import (
    desempaquetar_enriquecimiento, inyectar_veredicto_backend,
    reconciliar_resultados_profesionales,
)
from schemas.cargo import etiqueta_hoja

CARGO = "ESPECIALISTA EN INSTALACIONES ELECTRICAS"
MINIMO = {"tipo_experiencia_valida": "Experiencia mínima: 24 meses en el cargo "
                                     "desempeñado."}


def _espejo() -> dict:
    """6 experiencias, una por nivel de certeza (la 6 con fechas de mes)."""
    return {
        "_meta": {"analisis_id": "t-expedientes", "concurso": "CP-FICTICIO/2026",
                  "postor": "CONSORCIO FICTICIO", "tipo_evaluacion": "expedientes"},
        "postor": {},
        "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [{
            "n_prof": 1, "cargo": CARGO, "nombre": "Profesional Ficticio",
            "colegiatura": "CIP 99999", "requisitos": dict(MINIMO),
            "experiencias": [
                {"n": 1, "proyecto": "Expediente técnico del Colegio Ficticio",
                 "entidad_emisora": "MUNICIPALIDAD FICTICIA", "cui": "1111111",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2019-01-01", "fecha_final": "2019-06-30"},
                {"n": 2, "proyecto": "Expediente técnico del Puesto de Salud Ficticio",
                 "entidad_emisora": "CONSULTORA FICTICIA S.A.C.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2020-01-01", "fecha_final": "2020-06-30"},
                {"n": 3, "proyecto": "Expediente técnico del Mercado Ficticio",
                 "entidad_emisora": "INGENIERÍA FICTICIA E.I.R.L.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2021-01-01", "fecha_final": "2021-06-30"},
                {"n": 4, "proyecto": "Expediente técnico del Estadio Ficticio",
                 "entidad_emisora": "ESTUDIO FICTICIO S.R.L.",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2022-01-01", "fecha_final": "2022-06-30"},
                {"n": 5, "proyecto": "Expedientes técnicos varios (multi-obra)",
                 "entidad_emisora": "CONSORCIO FICTICIO DOS",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2023-01-01", "fecha_final": "2023-06-30"},
                {"n": 6, "proyecto": "Expediente técnico del Coliseo Ficticio",
                 "entidad_emisora": "MUNICIPALIDAD FICTICIA DOS", "cui": "6666666",
                 "cargo_ocupado": "Especialista eléctrico",
                 "fecha_inicial": "2024-03 (sin día)", "fecha_final": "2024-08 (sin día)"},
            ]}],
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    }


def _enriquecimiento() -> dict:
    return {
        # 1 · CUI citado en el certificado
        "1:1": {"via": "CUI_TEXTO", "cui": "1111111",
                "obra_nombre": "COLEGIO FICTICIO", "codigo_infoobras": "1",
                "sin_documentos_mef": True},
        # 2 · CUI confirmado por el contrato del MEF (veredicto real: "ok")
        "1:2": {"via": "NOMBRE", "cui": "2222222",
                "obra_nombre": "PUESTO DE SALUD FICTICIO", "codigo_infoobras": "2",
                "verificacion_expediente": {
                    "cui_confirmado": "2222222", "verificado_en_mef": True,
                    "contratista": {"valor": "CONSULTORA FICTICIA S.A.C.",
                                    "declarado": "CONSULTORA FICTICIA S.A.C.",
                                    "veredicto": "ok"},
                    "contrato": {"numero": "015-2020", "fecha": "2019-12-20",
                                 "veredicto": "ok", "elegido_por": "emisor"},
                    "resolucion": {"veredicto": "no_verificable"}}},
        # 3 · CUI inferido por el nombre del proyecto
        "1:3": {"via": "NOMBRE", "cui": "3333333",
                "obra_nombre": "MERCADO FICTICIO", "codigo_infoobras": "3",
                "verificacion_expediente": {
                    "cui_confirmado": "3333333", "verificado_en_mef": True,
                    "contrato": {"numero": "020-2021", "fecha": "2020-12-01",
                                 "veredicto": "no_verificable",
                                 "elegido_por": "unico",
                                 "otros_contratos_expediente": []},
                    "resolucion": {"veredicto": "no_verificable"}},
                "resolucion_aprobacion": {"legible": True, "fecha": "2021-08-10",
                                          "numero": "123-2021-MF",
                                          "coincide_emisor": "no_nombra"}},
        # 4 · sin identificar (el resolver no pudo cerrar la obra)
        "1:4": {"via": "REVISION", "sin_verificar": True},
        # 5 · multi-obra con 0 de 2 identificadas
        "1:5": {"via": "MULTI_OBRA", "identificacion_incompleta": True,
                "sub_obras": [{"cui": None, "estado": "sin_resolver"},
                              {"cui": None, "estado": "sin_resolver"}]},
        # 6 · fechas a nivel de mes + CUI citado
        "1:6": {"via": "CUI_TEXTO", "cui": "6666666",
                "obra_nombre": "COLISEO FICTICIO", "codigo_infoobras": "6",
                "sin_documentos_mef": True},
    }


@pytest.fixture()
def hoja(tmp_path):
    """Excel regenerado por el mismo camino que el backfill (reconcilia y pinta)."""
    espejo, enr = _espejo(), _enriquecimiento()
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "final.xlsx", paral, cuis,
                                 fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, CARGO)]
    return espejo, enr, ws


def _celdas(ws) -> dict[str, tuple[int, int]]:
    """{texto: (fila, columna)} de todas las celdas con texto de la hoja."""
    return {str(c.value): (c.row, c.column)
            for f in ws.iter_rows() for c in f if isinstance(c.value, str)}


def _texto(ws) -> str:
    return "\n".join(str(c.value) for f in ws.iter_rows() for c in f
                     if c.value is not None)


def _valor_total(ws, etiqueta):
    for f in ws.iter_rows():
        for c in f:
            if str(c.value or "").startswith(etiqueta):
                return ws.cell(c.row, 19).value
    raise AssertionError(f"no se encontró la fila de totales {etiqueta!r}")


def _rgb(celda) -> str:
    return str((celda.fill.fgColor.rgb or ""))[-6:]


# ── la función pura ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("clave, nivel, etiqueta, color", [
    ("1:1", "citado", "CUI citado en el certificado", COLOR_VERIFICADO),
    ("1:2", "confirmado_mef",
     "CUI confirmado por el MEF (contrato o resolución a nombre del emisor)",
     COLOR_VERIFICADO),
    ("1:3", "inferido", "CUI inferido por el nombre del proyecto", COLOR_INFERIDO),
    ("1:4", "sin_identificar", "Sin identificar", COLOR_SIN_IDENTIFICAR),
    ("1:5", "sin_identificar", "Sin identificar", COLOR_SIN_IDENTIFICAR),
    ("1:6", "citado", "CUI citado en el certificado", COLOR_VERIFICADO),
])
def test_clasificar_identificacion_cubre_los_seis_casos(clave, nivel, etiqueta, color):
    n_exp = int(clave.split(":")[1])
    exp = next(e for e in _espejo()["profesionales"][0]["experiencias"]
               if e["n"] == n_exp)
    certeza = clasificar_identificacion(exp, _enriquecimiento()[clave])
    assert (certeza["nivel"], certeza["etiqueta"], certeza["color"]) == (
        nivel, etiqueta, color)


def test_multi_obra_parcial_dice_cuantas_se_ubicaron():
    """Con 1 de 2 obras ubicadas la identificación es PARCIAL: violeta, no verde."""
    enr = {"via": "MULTI_OBRA", "identificacion_incompleta": True,
           "sub_obras": [{"cui": "9", "estado": "resuelto"},
                         {"cui": None, "estado": "sin_resolver"}]}
    certeza = clasificar_identificacion({"n": 5}, enr)
    assert certeza["nivel"] == "multi_obra"
    assert certeza["etiqueta"] == "1 de 2 obras identificadas"
    assert certeza["color"] == COLOR_INFERIDO


def test_obra_privada_no_es_un_fallo():
    certeza = clasificar_identificacion({"n": 1}, {"via": "PRIVADA"})
    assert certeza["nivel"] == "privada"
    assert certeza["color"] == COLOR_PRIVADA


def test_fuente_mef_sin_documentos_lo_dice_sin_rodeos():
    mef = fuente_mef({"via": "CUI_TEXTO", "sin_documentos_mef": True})
    assert mef["sin_documentos"] is True
    assert "El MEF no publica contrato ni resolución" in mef["contrato"]
    assert "cuenta por el certificado" in mef["contrato"]


def test_fuente_mef_describe_contrato_resolucion_y_consultor():
    mef = fuente_mef(_enriquecimiento()["1:3"])
    assert "Contrato N° 020-2021" in mef["contrato"]
    assert "elegido por ser el único del expediente" in mef["contrato"]
    assert "Resolución de aprobación N° 123-2021-MF del 10/08/2021" == mef["resolucion"]
    assert mef["consultor"] == ("Consultor según resolución: la resolución no "
                                "nombra al consultor")


def test_fuente_mef_dice_que_la_fecha_de_resolucion_se_descarto():
    mef = fuente_mef({"resolucion_aprobacion": {
        "numero": "777-2024-MF", "fecha": None,
        "fecha_descartada": "1999-01-05", "fecha_motivo": "anterior al contrato",
        "coincide_emisor": "confirma"}})
    assert "fecha no legible con certeza" in mef["resolucion"]
    assert "se descartó 05/01/1999: anterior al contrato" in mef["resolucion"]


# ── la PARTE 5 en la hoja ───────────────────────────────────────────────────

def test_la_fila_de_infoobras_se_sustituye_por_la_del_mef(hoja):
    _, _, ws = hoja
    texto = _texto(ws)
    assert "MEF · contrato" in texto and "MEF · resolución" in texto
    # La antigua sub-fila «Fuente: InfoObras» hablaba de la EJECUCIÓN de la obra,
    # que no prueba nada sobre quién elaboró el expediente.
    celdas = _celdas(ws)
    assert "InfoObras" not in celdas
    assert "Contrato N° 015-2020" in texto


def test_cada_experiencia_trae_su_celda_de_identificacion_con_su_color(hoja):
    _, _, ws = hoja
    esperado = {
        "CUI citado en el certificado": COLOR_VERIFICADO,
        "CUI confirmado por el MEF (contrato o resolución a nombre del emisor)":
            COLOR_VERIFICADO,
        "CUI inferido por el nombre del proyecto": COLOR_INFERIDO,
        "Sin identificar": COLOR_SIN_IDENTIFICAR,
    }
    rotulos = [c for f in ws.iter_rows() for c in f if c.value == "Identificación"]
    assert len(rotulos) == 6            # una por experiencia, ninguna muda
    vistas = set()
    for rot in rotulos:
        celda = ws.cell(rot.row, 15)
        assert celda.value in esperado, celda.value
        assert _rgb(celda) == esperado[celda.value]
        vistas.add(celda.value)
    assert vistas == set(esperado)


def test_alerta_roja_cuando_el_multiobra_no_ubica_ninguna_obra(hoja):
    _, _, ws = hoja
    alertas = [ws.cell(c.row, 15).value
               for f in ws.iter_rows() for c in f if c.value == "Alerta"]
    assert any("2 obras y ninguna ubicada" in str(a) for a in alertas)


def test_alerta_roja_cuando_la_resolucion_nombra_a_otro_consultor(tmp_path):
    espejo, enr = _espejo(), _enriquecimiento()
    enr["1:3"]["resolucion_aprobacion"]["coincide_emisor"] = "nombra_otro"
    enr["1:3"]["resolucion_aprobacion"]["consultores"] = ["OTRA CONSULTORA FICTICIA"]
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "f.xlsx", paral, cuis, fichas,
                                 {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, CARGO)]
    alerta = next(ws.cell(c.row, 15) for f in ws.iter_rows() for c in f
                  if c.value == "Alerta"
                  and "nombra a OTRO consultor" in str(ws.cell(c.row, 15).value))
    assert "OTRA CONSULTORA FICTICIA" in alerta.value
    assert _rgb(alerta) == "F4CCCC"      # FILL_ALERTA


def test_los_dias_efectivos_son_los_de_reconciliar(hoja):
    """El bug que se arregla: tabla y conclusión contaban cosas distintas."""
    espejo, enr, ws = hoja
    esperado = reconciliar_resultados_profesionales(espejo, enr)[1]["dias_efectivos"]
    assert _valor_total(ws, "DÍAS EFECTIVOS DEL PROFESIONAL") == esperado
    # y la conclusión cita ese MISMO número
    conclusion = ws.cell(_celdas(ws)["CONCLUSIÓN DEL TIEMPO EFECTIVO"][0], 7).value
    assert f"{esperado} días efectivos" in conclusion


def test_las_fechas_de_mes_cuentan_y_se_declaran_deducidas(hoja):
    """La experiencia 6 («2024-03 (sin día)») aportaba 0 días a la tabla."""
    espejo, enr, ws = hoja
    texto = _texto(ws)
    assert "Mes completo asumido según bases" in texto
    # 2024-03-01 → 2024-08-31 = 184 días inclusivos, contados como el resto
    fila_6 = next(c.row for f in ws.iter_rows() for c in f
                  if c.column == 1 and c.value == 6)
    assert ws.cell(fila_6, 18).value == 184
    assert ws.cell(fila_6, 19).value == 184
    # el periodo deducido se pinta violeta (dato inferido, no declarado)
    assert _rgb(ws.cell(fila_6, 15)) == COLOR_INFERIDO


def test_los_totales_desglosan_la_certeza_y_cuadran(hoja):
    espejo, enr, ws = hoja
    conf = _valor_total(ws, "DÍAS CON CUI CITADO O CONFIRMADO POR EL MEF")
    inf = _valor_total(ws, "DÍAS CON CUI INFERIDO POR NOMBRE")
    sin = _valor_total(ws, "DÍAS SIN IDENTIFICAR (provisionales)")
    tras = _valor_total(ws, "(−) Traslapes entre experiencias")
    efec = _valor_total(ws, "DÍAS EFECTIVOS DEL PROFESIONAL")
    assert conf + inf + sin - tras == efec
    # exp 1 (181) + exp 2 (182) + exp 6 (184) = 547 con documento
    assert conf == 547
    assert inf == 181                    # exp 3
    assert sin == 181 + 181              # exp 4 y exp 5
    # la vieja fila única ya no existe: decía «TOTAL» sin decir de qué certeza
    assert "TOTAL, DÍAS (suma por experiencia)" not in _texto(ws)


def test_dias_sin_identificar_se_rotulan_provisionales_y_van_sin_relleno(hoja):
    _, _, ws = hoja
    fila_4 = next(c.row for f in ws.iter_rows() for c in f
                  if c.column == 1 and c.value == 4)
    celda = ws.cell(fila_4, 19)
    assert celda.value == "181 PROVISIONAL"
    assert celda.fill.fill_type in (None, "none")


def test_dias_confirmados_en_cyan_e_inferidos_en_violeta(hoja):
    _, _, ws = hoja
    fila_1 = next(c.row for f in ws.iter_rows() for c in f
                  if c.column == 1 and c.value == 1)
    fila_3 = next(c.row for f in ws.iter_rows() for c in f
                  if c.column == 1 and c.value == 3)
    assert _rgb(ws.cell(fila_1, 19)) == "00FFFF"     # FILL_EFECTIVO
    assert _rgb(ws.cell(fila_3, 19)) == COLOR_INFERIDO


def test_la_conclusion_no_dice_cumple_por_debajo_del_minimo(tmp_path):
    """Caso P9: la hoja imprimía «CUMPLE — 574 días» con un mínimo de 24 meses."""
    espejo, enr = _espejo(), _enriquecimiento()
    prof = espejo["profesionales"][0]
    prof["experiencias"] = prof["experiencias"][:2]          # 181 + 182 = 363 días
    prof["cumple"] = "CUMPLE — el postor acredita de sobra la experiencia"
    inyectar_veredicto_backend(espejo, enr)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "f.xlsx", paral, cuis, fichas,
                                 {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, CARGO)]
    conclusion = ws.cell(_celdas(ws)["CONCLUSIÓN DEL TIEMPO EFECTIVO"][0], 7).value
    assert conclusion.startswith("NO CUMPLE")
    assert "363 días efectivos" in conclusion
    assert _valor_total(ws, "DÍAS EFECTIVOS DEL PROFESIONAL") == 363


def test_la_conclusion_declara_cuantos_dias_dependen_de_una_inferencia(hoja):
    _, _, ws = hoja
    conclusion = ws.cell(_celdas(ws)["CONCLUSIÓN DEL TIEMPO EFECTIVO"][0], 7).value
    assert "181 dependen de un CUI inferido por el nombre del proyecto" in conclusion
    assert "362 provienen de experiencias SIN identificar" in conclusion
    # el texto viejo se calculaba desde el DECLARADO, no desde los efectivos
    assert "total declarado recalculado" not in conclusion


def test_sin_fugas_de_interfaz_en_el_entregable(hoja):
    _, _, ws = hoja
    texto = _texto(ws)
    assert "elegir candidato" not in texto
    assert "elegir el RUC correcto en el panel" not in texto
