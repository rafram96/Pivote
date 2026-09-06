"""
Sección 2 de «Cronología de expedientes»: LÍNEA DE TIEMPO POR PROFESIONAL.

Qué se fija aquí:

  · el eje (rango, granularidad adaptativa y las dos filas de cabecera),
  · qué celdas pinta cada experiencia y con qué color de certeza,
  · dónde caen las marcas C (firma) / R (resolución) / ≈ (fechas de mes),
  · la fila de traslapes en naranja y los totales, que tienen que ser los
    MISMOS de `reconciliar_resultados_profesionales` (una sola fuente de días),
  · que un concurso de OBRAS conserva la tabla comparativa de siempre.

Todos los datos son FICTICIOS (nombres, entidades y CUI inventados).
"""
from __future__ import annotations

from datetime import date

import openpyxl
import pytest
from openpyxl.utils import get_column_letter

from entregables import cronologia
from entregables.excel_final import (
    HOJA_CRONOLOGIA, COLOR_TRASLAPE, construir_hoja_cronologia,
    reconciliar_resultados_profesionales,
)
from entregables.certeza import (
    COLOR_INFERIDO, COLOR_SIN_IDENTIFICAR, COLOR_VERIFICADO,
)

# ── Espejo ficticio ─────────────────────────────────────────────────────────

REQUISITO = {"experiencia": "Experiencia mínima de 1 año en expedientes técnicos"}


def _espejo_expedientes() -> dict:
    """Dos profesionales ficticios en un concurso de EXPEDIENTES.

    P1 — tres experiencias que se pisan, una por cada nivel de certeza.
    P2 — dos experiencias muy separadas en el tiempo (eje de años).
    """
    return {
        "_meta": {"concurso": "CP-99-2099-MUNI-FICTICIA",
                  "postor": "CONSORCIO FICTICIO",
                  "tipo_evaluacion": "expedientes"},
        "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [
            {"n_prof": 1, "nombre": "AURORA QUISPE FICTICIA",
             "cargo": "ESPECIALISTA EN ESTRUCTURAS", "requisitos": dict(REQUISITO),
             "experiencias": [
                 {"n": 1, "proyecto": "Expediente técnico del puente ficticio de Valle Azul",
                  "fecha_inicial": "2022-01-15", "fecha_final": "2022-06-30"},
                 {"n": 2, "proyecto": "Expediente técnico del centro de salud ficticio Los Álamos",
                  "fecha_inicial": "2022-05-01", "fecha_final": "2022-11-30"},
                 {"n": 3, "proyecto": "Expediente técnico de la vía ficticia Km 12",
                  "fecha_inicial": "2023-02 (FEBRERO DEL 2023)",
                  "fecha_final": "2023-05 (MAYO DEL 2023)"},
             ]},
            {"n_prof": 2, "nombre": "BENITO RAMÍREZ FICTICIO",
             "cargo": "ESPECIALISTA EN COSTOS", "requisitos": dict(REQUISITO),
             "experiencias": [
                 {"n": 1, "proyecto": "Expediente técnico del colegio ficticio San Antonio",
                  "fecha_inicial": "2003-03-01", "fecha_final": "2003-12-31"},
                 {"n": 2, "proyecto": "Expediente técnico del mercado ficticio Central",
                  "fecha_inicial": "2025-01-01", "fecha_final": "2025-06-30"},
             ]},
        ],
    }


def _fichas() -> dict:
    """La proyección del enriquecimiento que consume la hoja.

    · (1,1) vía NOMBRE con CUI → identificación INFERIDA (violeta).
    · (1,2) vía CUI_TEXTO con CUI → CITADO (verde), con contrato del emisor
      (marca C) y resolución de aprobación (marca R).
    · (1,3) vía REVISION, sin CUI → SIN IDENTIFICAR (amarillo).
    """
    return {
        (1, 1): {"via": "NOMBRE", "cui": "9000001",
                 "obra_nombre": "Expediente técnico del puente ficticio de Valle Azul"},
        (1, 2): {"via": "CUI_TEXTO", "cui": "9000002",
                 "obra_nombre": "Expediente técnico del centro de salud ficticio Los Álamos",
                 "seace": {"estado": "seleccionado",
                           "proceso": {"fecha_firma": "2022-04-20"},
                           "candado": {"senales": [
                               {"nombre": "entidad", "fuerza": "fuerte", "sentido": "a_favor"},
                               {"nombre": "objeto", "fuerza": "fuerte", "sentido": "a_favor"}]}},
                 "contrato_emisor": {"fecha": "2022-04-20"},
                 "resolucion_aprobacion": {"fecha": "2022-12-05", "legible": True,
                                            "coincide_emisor": "confirma"},
                 "verificacion_expediente": {"resolucion": {"fecha": "2022-12-05"}}},
        (1, 3): {"via": "REVISION"},
        (2, 1): {"via": "REVISION"},
        (2, 2): {"via": "REVISION"},
    }


def _hoja(espejo, fichas):
    ws = openpyxl.Workbook().active
    ws.title = HOJA_CRONOLOGIA
    filas = construir_hoja_cronologia(ws, espejo, fichas)
    return ws, filas


def _rotulos(ws) -> dict[str, int]:
    """{texto de la columna A: fila} — la columna A es el rótulo de todo."""
    return {str(f[0].value): f[0].row for f in ws.iter_rows(min_col=1, max_col=1)
            if isinstance(f[0].value, str)}


def _fila_que_empieza(ws, prefijo: str) -> int:
    for f in ws.iter_rows(min_col=1, max_col=1):
        if isinstance(f[0].value, str) and f[0].value.startswith(prefijo):
            return f[0].row
    raise AssertionError(f"no hay ninguna fila que empiece con {prefijo!r}")


def _color(celda) -> str:
    return (celda.fill.fgColor.rgb or "")[-6:]


def _pintadas(ws, fila: int, color: str) -> list[int]:
    """Índices del eje (0-based) pintados con ese color en la fila."""
    return [c - 2 for c in range(2, ws.max_column + 1)
            if _color(ws.cell(fila, c)) == color]


# ── (a) Tres experiencias que se pisan · eje mensual ────────────────────────

@pytest.fixture()
def hoja_p1():
    espejo = _espejo_expedientes()
    ws, filas = _hoja(espejo, _fichas())
    return espejo, ws, filas


def test_la_seccion_2_es_la_linea_de_tiempo_con_su_leyenda(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    textos = " | ".join(str(c.value) for f in ws.iter_rows() for c in f
                        if c.value is not None)
    assert "2 · LÍNEA DE TIEMPO POR PROFESIONAL" in textos
    assert "TABLA COMPARATIVA" not in textos
    # la leyenda, UNA sola vez y con todo lo que hay que saber leer
    assert textos.count("Naranja: traslape") == 1
    for pieza in ("verde", "violeta", "amarillo", "gris",
                  "C: fecha de firma del contrato", "R: fecha de la resolución", "≈"):
        assert pieza.lower() in textos.lower(), pieza
    assert ("Las barras representan los períodos declarados. Su color indica "
            "la certeza de identificación del proyecto") in textos
    from entregables.leyenda_gantt import COLORES_GANTT, MARCAS_GANTT, NOTAS_GANTT
    assert "LEYENDA — COLORES Y MARCAS" in textos
    for color, significado in COLORES_GANTT:
        celda = next(c for fila in ws for c in fila if c.value == significado)
        assert celda.fill.fgColor.rgb[-6:] == color
    assert all(significado in textos for _, significado in MARCAS_GANTT)
    assert all(nota in textos for nota in NOTAS_GANTT)


def test_cabecera_del_bloque_cita_los_dias_de_reconciliar(hoja_p1):
    espejo, ws, _filas = hoja_p1
    esperado = reconciliar_resultados_profesionales(espejo, None)[1]
    fila = _fila_que_empieza(ws, "PROFESIONAL 1 · ")
    cabecera = ws.cell(fila, 1).value
    assert "AURORA QUISPE FICTICIA" in cabecera
    assert "ESPECIALISTA EN ESTRUCTURAS" in cabecera
    assert f"{esperado['dias_efectivos']} días efectivos" in cabecera
    assert f"({esperado['dias_traslape']} de traslape)" in cabecera
    # Sin identificación persistida, el estado conservador es POR VERIFICAR.
    assert cabecera.endswith("POR VERIFICAR")
    assert esperado["dias_efectivos"] == 440 and esperado["dias_traslape"] == 61


def test_el_eje_es_bimestral_y_lleva_las_dos_filas_de_cabecera(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    fila = _fila_que_empieza(ws, "PROFESIONAL 1 · ")
    assert ws.cell(fila + 1, 1).value == "Eje: bimestres"
    unidades = [ws.cell(fila + 2, 2 + i).value for i in range(9)]
    assert unidades == list(cronologia.BIMESTRES) + list(cronologia.BIMESTRES[:3])
    assert ws.cell(fila + 2, 2).alignment.textRotation == 90
    assert ws.cell(fila + 2, 11).value is None
    assert ws.cell(fila + 2, 1).value == "PERÍODO DECLARADO"
    # 2022 combinado sobre seis bimestres, 2023 sobre tres.
    assert ws.cell(fila + 1, 2).value == 2022
    assert ws.cell(fila + 1, 8).value == 2023
    combinados = {str(m) for m in ws.merged_cells.ranges}
    assert f"B{fila + 1}:G{fila + 1}" in combinados
    assert f"H{fila + 1}:J{fila + 1}" in combinados


def test_cada_barra_ocupa_sus_meses_con_el_color_de_certeza(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    rot = _rotulos(ws)
    f1 = _fila_que_empieza(ws, "1 · Expediente técnico del puente")
    f2 = _fila_que_empieza(ws, "2 · Expediente técnico del centro")
    f3 = _fila_que_empieza(ws, "3 · Expediente técnico de la vía")
    assert f1 < f2 < f3                                  # orden por fecha de inicio

    # 15/01/2022 – 30/06/2022 → enero a junio · CUI inferido → violeta
    assert _pintadas(ws, f1, COLOR_INFERIDO) == [0, 1, 2]
    # 01/05/2022 – 30/11/2022 → mayo a noviembre · CUI citado → verde
    assert _pintadas(ws, f2, COLOR_VERIFICADO) == [2, 3, 4, 5]
    # 02/2023 – 05/2023 (mes completo) → febrero a mayo de 2023 · sin identificar
    assert _pintadas(ws, f3, COLOR_SIN_IDENTIFICAR) == [6, 7, 8]
    assert rot  # sanity: la columna A tiene rótulos


def test_los_hitos_del_mef_caen_en_su_mes_y_no_borran_la_barra(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    f2 = _fila_que_empieza(ws, "2 · Expediente técnico del centro")
    # C = firma del contrato del emisor, 20/04/2022 → Mar–Abr (índice 1), fuera de
    # la barra (que empieza en mayo): la celda lleva la marca y ningún relleno.
    assert ws.cell(f2, 2 + 1).value == "C"
    assert ws.cell(f2, 2 + 1).font.bold
    # R cae en Nov–Dic, compartiendo columna con la barra que termina en noviembre.
    assert ws.cell(f2, 2 + 5).value == "R"
    assert "C: 20/04/2022" in ws.cell(f2, 1).value
    assert "R: 05/12/2022" in ws.cell(f2, 1).value
    # y dentro de la barra la marca convive con el relleno de certeza
    assert _color(ws.cell(f2, 2 + 5)) == COLOR_VERIFICADO


def test_las_fechas_de_mes_se_marcan_con_la_tilde_y_lo_dicen_en_el_rotulo(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    f3 = _fila_que_empieza(ws, "3 · Expediente técnico de la vía")
    assert ws.cell(f3, 2 + 6).value == "≈"
    assert _color(ws.cell(f3, 2 + 6)) == COLOR_SIN_IDENTIFICAR
    assert "(fechas de mes; se asume mes completo)" in ws.cell(f3, 1).value


def test_el_rotulo_lleva_el_cui_o_dice_que_no_hay(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    assert "CUI 9000001" in ws.cell(
        _fila_que_empieza(ws, "1 · Expediente técnico del puente"), 1).value
    assert "sin CUI" in ws.cell(
        _fila_que_empieza(ws, "3 · Expediente técnico de la vía"), 1).value


def test_el_rotulo_conserva_las_reglas_a_y_b_como_comentario(hoja_p1):
    """Al retirar la tabla comparativa las respuestas NO se pierden: viajan en
    el comentario de la celda del rótulo, a un clic del evaluador."""
    _espejo, ws, _filas = hoja_p1
    for prefijo in ("1 · Expediente técnico del puente",
                    "2 · Expediente técnico del centro"):
        comentario = ws.cell(_fila_que_empieza(ws, prefijo), 1).comment
        assert comentario is not None, prefijo
        assert "¿Empezó después de firmado el contrato?" in comentario.text
        assert "¿Terminó antes de aprobarse el expediente?" in comentario.text


def test_la_fila_de_traslapes_pinta_naranja_solo_los_meses_pisados(hoja_p1):
    espejo, ws, _filas = hoja_p1
    fila = _fila_que_empieza(ws, "Traslapes · ")
    # 01/05/2022 – 30/06/2022 son los únicos días con dos experiencias vivas
    assert _pintadas(ws, fila, COLOR_TRASLAPE) == [2]
    esperado = reconciliar_resultados_profesionales(espejo, None)[1]
    assert ws.cell(fila, 1).value == (
        f"Traslapes · {esperado['dias_traslape']} días de traslape")


def test_la_fila_de_total_repite_los_numeros_de_la_cabecera(hoja_p1):
    espejo, ws, _filas = hoja_p1
    d = reconciliar_resultados_profesionales(espejo, None)[1]
    fila = _fila_que_empieza(ws, "Total: ")
    assert ws.cell(fila, 1).value == (
        f"Total: {d['dias_brutos']} días declarados · {d['dias_traslape']} "
        f"traslape · {d['dias_efectivos']} efectivos")


def test_devuelve_una_fila_por_experiencia(hoja_p1):
    _espejo, _ws, filas = hoja_p1
    assert filas == 5           # 3 del profesional 1 + 2 del profesional 2


def test_los_bloques_van_en_orden_de_n_prof(hoja_p1):
    _espejo, ws, _filas = hoja_p1
    assert (_fila_que_empieza(ws, "PROFESIONAL 1 · ")
            < _fila_que_empieza(ws, "PROFESIONAL 2 · "))


# ── (b) Rango largo · granularidad por años ────────────────────────────────

def test_un_profesional_con_veinte_anios_conserva_un_solo_eje_bimestral(hoja_p1):
    """No se divide ni se degrada a trimestres/años por una trayectoria larga."""
    _espejo, ws, _filas = hoja_p1
    fila = _fila_que_empieza(ws, "PROFESIONAL 2 · ")
    assert ws.cell(fila + 1, 1).value == "Eje: bimestres"
    assert ws.column_dimensions["B"].width == cronologia.ANCHO_UNIDAD
    assert ws.cell(fila + 2, 2).value == "Mar–Abr"
    assert ws.cell(fila + 2, 135).value == "May–Jun"
    assert ws.cell(fila + 2, 136).value is None
    assert sum(str(c.value).startswith("PROFESIONAL 2 · ") for c in ws["A"]) == 1
    f1 = _fila_que_empieza(ws, "1 · Expediente técnico del colegio")
    f2 = _fila_que_empieza(ws, "2 · Expediente técnico del mercado")
    assert _pintadas(ws, f1, COLOR_SIN_IDENTIFICAR)
    assert _pintadas(ws, f2, COLOR_SIN_IDENTIFICAR)
    assert "Inicio:" in ws.cell(f1, 1).value and "Fin:" in ws.cell(f2, 1).value
    assert ws.cell(_fila_que_empieza(ws, "Traslapes · Sin traslapes"), 1).value


def test_dos_mil_ocho_a_dos_mil_veinticinco_cae_en_trimestres():
    """El umbral es de MESES, no de años: 2008-2025 son 209 meses (≤ 240), así
    que el eje se dibuja por trimestres. Se hacen falta más de 20 años de rango
    para pasar a un eje de años."""
    assert cronologia.granularidad(date(2008, 3, 1),
                                   date(2025, 6, 30)) == cronologia.GRANO_TRIMESTRE


def test_una_experiencia_en_varios_tramos_se_cuenta_una_sola_vez():
    espejo = _espejo_expedientes()
    espejo["profesionales"] = espejo["profesionales"][:1]
    espejo["profesionales"][0]["experiencias"] = [
        {"n": 1, "proyecto": "Expediente ficticio prolongado",
         "fecha_inicial": "2010-01-17", "fecha_final": "2025-06-23"}]
    ws, filas = _hoja(espejo, {})
    assert filas == 1
    rotulos = [c.value for c in ws["A"] if str(c.value).startswith("1 · Expediente")]
    assert len(rotulos) == 1
    assert all("Inicio: 17/01/2010 · Fin: 23/06/2025" in r for r in rotulos)


def test_un_profesional_sin_periodos_computables_lo_dice_y_no_dibuja_eje():
    espejo = _espejo_expedientes()
    espejo["profesionales"] = [{
        "n_prof": 1, "nombre": "CECILIA TORRES FICTICIA", "cargo": "ESPECIALISTA",
        "experiencias": [{"n": 1, "proyecto": "Expediente ficticio sin fechas",
                          "fecha_inicial": "POR VERIFICAR — ilegible",
                          "fecha_final": "POR VERIFICAR — ilegible"}],
    }]
    ws, filas = _hoja(espejo, {})
    assert filas == 1
    textos = " | ".join(str(c.value) for f in ws.iter_rows() for c in f
                        if c.value is not None)
    assert "Sin periodos computables" in textos


# ── (c) Concursos de OBRAS: la tabla comparativa no se toca ────────────────

def test_un_concurso_de_obras_conserva_la_tabla_comparativa():
    espejo = _espejo_expedientes()
    espejo["_meta"]["tipo_evaluacion"] = "obras"
    ws, filas = _hoja(espejo, _fichas())
    textos = " | ".join(str(c.value) for f in ws.iter_rows() for c in f
                        if c.value is not None)
    assert "2 · TABLA COMPARATIVA" in textos
    assert "LÍNEA DE TIEMPO" not in textos
    assert "¿EMPEZÓ DESPUÉS DE FIRMADO EL CONTRATO?" in textos
    assert filas == 5
    # y conserva sus anchos de columna de siempre (A = 26, no el rótulo ancho)
    assert ws.column_dimensions["A"].width == 26
    assert ws.page_setup.fitToWidth is None
    assert ws.page_setup.orientation != ws.ORIENTATION_LANDSCAPE


def test_sin_tipo_declarado_tambien_conserva_la_tabla():
    """Espejos anteriores al parámetro (ADR-010): desconocido ≠ expedientes."""
    espejo = _espejo_expedientes()
    espejo["_meta"].pop("tipo_evaluacion")
    ws, _filas = _hoja(espejo, _fichas())
    textos = " ".join(str(c.value) for f in ws.iter_rows() for c in f
                      if c.value is not None)
    assert "TABLA COMPARATIVA" in textos


# ── La ficha por proyecto (sección 1) sigue legible bajo la rejilla nueva ───

def test_la_seccion_1_conserva_un_ancho_util_con_la_rejilla_de_la_linea():
    """La ficha combina A:C (etiqueta) y D:última (valor). Con un eje corto el
    valor se quedaría en veinte caracteres: el mínimo de columnas lo evita."""
    espejo = _espejo_expedientes()
    espejo["profesionales"] = espejo["profesionales"][:1]
    espejo["profesionales"][0]["experiencias"] = [
        {"n": 1, "proyecto": "Expediente ficticio corto",
         "fecha_inicial": "2024-01-01", "fecha_final": "2024-03-31"}]
    ws, _filas = _hoja(espejo, {})
    assert ws.max_column >= cronologia.MIN_COLUMNAS
    assert ws.column_dimensions["A"].width == cronologia.ANCHO_ROTULO
    assert ws.column_dimensions["B"].width == cronologia.ANCHO_UNIDAD
    ancho_valor = sum(ws.column_dimensions[get_column_letter(i)].width or 0
                      for i in range(4, ws.max_column + 1))
    # La ficha conserva el mínimo útil y el rango imprimible llega a su última
    # columna real; el contenido se envuelve y conserva el área imprimible.
    assert ancho_valor >= 180
    assert ws.print_area.startswith("'Cronología de expedientes'!$A$1:$CB$")


# ── Layout puro (`entregables.cronologia`) ─────────────────────────────────

def test_umbrales_de_granularidad():
    assert cronologia.granularidad(date(2020, 1, 1), date(2024, 12, 31)) == \
        cronologia.GRANO_MES                       # 60 meses justos
    assert cronologia.granularidad(date(2020, 1, 1), date(2025, 1, 1)) == \
        cronologia.GRANO_TRIMESTRE                 # 61 meses
    assert cronologia.granularidad(date(2005, 1, 1), date(2024, 12, 31)) == \
        cronologia.GRANO_TRIMESTRE                 # 240 meses justos
    assert cronologia.granularidad(date(2005, 1, 1), date(2025, 1, 1)) == \
        cronologia.GRANO_ANIO                      # 241 meses


def test_bimestres_de_calendario_respetan_bisiesto_y_cambio_de_anio():
    eje = cronologia.construir_eje(date(2023, 12, 17), date(2024, 3, 2),
                                  cronologia.GRANO_BIMESTRE)
    assert [u.etiqueta for u in eje] == ["Nov–Dic", "Ene–Feb", "Mar–Abr"]
    assert eje[1].inicio == date(2024, 1, 1)
    assert eje[1].fin == date(2024, 2, 29)
    assert cronologia.indice_unidad(eje, date(2024, 1, 8)) == 1
    assert cronologia.indice_unidad(eje, date(2024, 2, 29)) == 1
    assert cronologia.indice_unidad(eje, date(2024, 3, 1)) == 2
    # Compartir bimestre no equivale a tener días traslapados.
    assert cronologia.unidades_con_traslape(eje, [
        (date(2024, 1, 1), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29))]) == set()


def test_el_eje_estira_para_un_hito_cercano_y_no_para_uno_lejano():
    periodos = [(date(2022, 5, 1), date(2022, 8, 31))]
    # firma dos meses antes → entra
    assert cronologia.rango_eje(periodos, [date(2022, 3, 10)]) == (
        date(2022, 3, 10), date(2022, 8, 31))
    # resolución dos años después → el eje no se estira (aplastaría las barras)
    assert cronologia.rango_eje(periodos, [date(2024, 8, 1)]) == (
        date(2022, 5, 1), date(2022, 8, 31))
    assert cronologia.rango_eje([], [date(2022, 3, 10)]) is None


def test_las_unidades_de_traslape_se_miden_dentro_de_la_columna():
    eje = cronologia.construir_eje(date(2022, 1, 1), date(2022, 4, 30),
                                   cronologia.GRANO_MES)
    # dos periodos consecutivos que NO se pisan aunque compartan columna
    sin_pisar = [(date(2022, 1, 1), date(2022, 2, 10)),
                 (date(2022, 2, 11), date(2022, 4, 30))]
    assert cronologia.unidades_con_traslape(eje, sin_pisar) == set()
    # un solo día compartido dentro de febrero ya cuenta
    pisados = [(date(2022, 1, 1), date(2022, 2, 11)),
               (date(2022, 2, 11), date(2022, 4, 30))]
    assert cronologia.unidades_con_traslape(eje, pisados) == {1}


def test_la_prioridad_del_hito_de_firma():
    """El contrato elegido por heurística NO pinta una «C»: puede ser de otro
    consultor del mismo expediente."""
    assert cronologia.hito_firma(
        {"contrato_emisor": {"fecha": "2022-04-20"},
         "verificacion_expediente": {"contrato": {"fecha": "2019-01-01",
                                                  "veredicto": "ok"}}}
    ) == date(2022, 4, 20)
    assert cronologia.hito_firma(
        {"verificacion_expediente": {"contrato": {"fecha": "2019-01-01",
                                                  "elegido_por": "emisor"}}}
    ) == date(2019, 1, 1)
    assert cronologia.hito_firma(
        {"verificacion_expediente": {"contrato": {"fecha": "2019-01-01",
                                                  "elegido_por": "mas_barato"}}}
    ) is None
    # sin nada del MEF, un proceso SEACE válido requiere identidad estructurada
    assert cronologia.hito_firma(
        {"seace": {"estado": "seleccionado",
                   "proceso": {"fecha_firma": "2021-09-24"},
                   "candado": {"senales": [
                       {"nombre": "entidad", "fuerza": "fuerte", "sentido": "a_favor"},
                       {"nombre": "objeto", "fuerza": "fuerte", "sentido": "a_favor"}]}}}
    ) == date(2021, 9, 24)


def test_el_rotulo_recorta_el_proyecto_y_ordena_las_marcas():
    largo = "Expediente técnico " + "muy largo " * 10
    rotulo = cronologia.rotulo_experiencia(7, largo, None,
                                           [cronologia.NOTA_MES_COMPLETO])
    assert rotulo.startswith("7 · Expediente técnico muy largo")
    assert "…" in rotulo and "sin CUI" in rotulo
    assert rotulo.endswith(cronologia.NOTA_MES_COMPLETO)
    assert cronologia.marcas_de_columna({3: ["R", "C", "≈"]}) == {3: "≈CR"}


def test_un_hito_fuera_del_eje_se_anuncia_en_el_rotulo():
    espejo = _espejo_expedientes()
    espejo["profesionales"] = espejo["profesionales"][:1]
    espejo["profesionales"][0]["experiencias"] = [
        {"n": 1, "proyecto": "Expediente ficticio con resolución tardía",
         "fecha_inicial": "2022-01-01", "fecha_final": "2022-03-31"}]
    fichas = {(1, 1): {"via": "CUI_TEXTO", "cui": "9000009",
                       "resolucion_aprobacion": {"fecha": "2025-06-18",
                                                  "coincide_emisor": "confirma"},
                       "verificacion_expediente": {"resolucion": {"fecha": "2025-06-18"}}}}
    ws, _filas = _hoja(espejo, fichas)
    rotulo = ws.cell(_fila_que_empieza(ws, "1 · Expediente ficticio con"), 1).value
    assert "R 18/06/2025 fuera de rango" in rotulo
