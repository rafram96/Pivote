"""Pulido del entregable: lo que un evaluador ve y no puede quedar contradictorio.

Cuatro defectos, todos encontrados leyendo celda por celda el Excel real del job
Vitarte (`7e9306a321ac`):

1. Un factor cuyo puntaje se RETIRA dejaba la celda muda: la PARTE 5 mostraba el
   Factor A en blanco, la fila del total decía 40 y la NOTA de abajo —un texto
   redactado antes del recálculo— seguía diciendo «80/100 (A=40…)».
2. La CONCLUSIÓN de la hoja del profesional citaba 1267 días y la PARTE 5 de
   arriba mostraba 1269: la misma cantidad contada con y sin los bordes.
3. Jerga de programador visible en el entregable («backend», «candado:»,
   «espejo», las marcas ⟦…⟧ y los nombres de los agentes).
4. El MISMO amarillo fuerte marcaba «esto lo declara el certificado» y «esto está
   por verificar», con una leyenda que solo prometía lo primero.
"""
from __future__ import annotations

import openpyxl
import pytest

from entregables import generar_excel_final
from scripts.generar_excel import (
    FILL_CUMPLE, FILL_PEND, conciliar_conclusion, dias_citados, generar_excel,
    nota_parte5,
)

AMARILLO_FUERTE = "00FFFF00"
AMARILLO_SUAVE = "00FFF2CC"


def _fill(celda) -> str:
    f = celda.fill
    if f is None or f.fill_type is None:
        return ""
    return str(f.fgColor.rgb)


def _celdas(wb):
    for ws in wb.worksheets:
        for fila in ws.iter_rows():
            for c in fila:
                yield ws.title, c


def _buscar(ws, texto):
    """Primera celda cuyo valor contiene `texto` (búsqueda de Ctrl+F)."""
    for fila in ws.iter_rows():
        for c in fila:
            if isinstance(c.value, str) and texto in c.value:
                return c
    return None


# ── 1 · el puntaje retirado y la NOTA ────────────────────────────────────────

def _espejo_factor_retirado():
    """Reproduce la PARTE 5 de Vitarte: A sin puntaje, B/D tachados, total 40."""
    return {
        "_meta": {"analisis_id": "p5", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [],
        "resumen_evaluacion": {
            "factores": [
                {"factor": "A", "criterio": "Experiencia adicional",
                 "detalle": "Puntaje por confirmar con el cuadro de las bases.",
                 "puntaje": None},
                {"factor": "C", "criterio": "ISO 14001", "puntaje": 10},
                {"factor": "G", "criterio": "ISO 37001", "puntaje": 10},
                {"factor": "J", "criterio": "ISO 9001", "puntaje": 20},
                {"factor": "B", "criterio": "Certificaciones",
                 "puntaje": "NO APLICA"},
                {"factor": "D", "criterio": "Sostenibilidad social",
                 "puntaje": "NO APLICA"},
            ],
            "puntaje_total": 40,
            "nota": "Puntaje técnico total 80/100 (A=40, C=10, G=10, J=20).",
        },
    }


def test_el_puntaje_retirado_habla_y_se_pinta_por_verificar(tmp_path):
    salida = generar_excel(_espejo_factor_retirado(), tmp_path / "p5.xlsx")
    ws = openpyxl.load_workbook(salida)["CLAUDE"]
    cabecera = _buscar(ws, "FACTOR")
    fila_a = cabecera.row + 1
    assert ws.cell(fila_a, 1).value == "A"
    # antes: celda vacía y sin color, al lado de un total distinto de cero
    assert ws.cell(fila_a, 5).value == "POR CONFIRMAR"
    assert _fill(ws.cell(fila_a, 5)) == AMARILLO_SUAVE
    # el resto de la tabla no se toca
    assert ws.cell(fila_a + 1, 5).value == 10
    assert ws.cell(fila_a + 4, 5).value == "NO APLICA"


def test_la_nota_sale_de_la_tabla_y_no_la_contradice(tmp_path):
    salida = generar_excel(_espejo_factor_retirado(), tmp_path / "p5.xlsx")
    ws = openpyxl.load_workbook(salida)["CLAUDE"]
    nota = _buscar(ws, "Puntaje técnico total 40")
    assert nota is not None, "la NOTA debe citar el total que la tabla muestra"
    assert "C 10" in nota.value and "G 10" in nota.value and "J 20" in nota.value
    assert "Por confirmar: A" in nota.value
    assert "No aplican" in nota.value and "B, D" in nota.value
    # La nota numérica del LLM se retira: una segunda autoridad, aunque esté
    # rotulada, volvía contradictorio el entregable.
    assert _buscar(ws, "Observaciones de la evaluación") is None
    assert _buscar(ws, "80/100") is None


def test_nota_parte5_declara_cuando_la_suma_no_da_el_total():
    txt = nota_parte5([{"factor": "A", "puntaje": 10}], puntaje_total=40)
    assert "suman 10" in txt and "revisar la diferencia" in txt


def test_nota_parte5_sin_total_no_inventa_uno():
    txt = nota_parte5([{"factor": "A", "puntaje": None}], puntaje_total=None)
    assert "POR VERIFICAR" in txt and "Por confirmar: A" in txt


# ── 2 · una sola cifra de días ───────────────────────────────────────────────

def test_dias_citados_lee_los_conteos_del_veredicto():
    assert dias_citados("acredita 1267 días (3.47 años)") == [1267]
    assert dias_citados("1,267 dias y otra vez 1,267 días") == [1267]
    assert dias_citados("sin cifras") == []
    assert dias_citados(None) == []


def test_conciliar_reemplaza_la_cifra_del_llm_por_la_autoridad_inclusiva():
    txt = conciliar_conclusion("CUMPLE — acredita 1267 días (3.47 años).",
                               1269, periodos=2)
    assert txt.startswith("CUMPLE según la evaluación inicial — 1269 días declarados")
    assert "1267" not in txt


def test_conciliar_canoniza_aun_si_la_cifra_del_llm_coincide():
    txt = "CUMPLE — acredita 1269 días (3.48 años)."
    assert conciliar_conclusion(txt, 1269, periodos=2) == (
        "CUMPLE según la evaluación inicial — 1269 días declarados "
        "(3.48 años) en 2 periodos computables; el tiempo efectivo verificado "
        "va en la línea siguiente.")


@pytest.mark.parametrize("texto, verificado, periodos", [
    # recorte del Paso 5: 1216 efectivos contra 1218 declarados NO es esto —
    # la distancia es enorme y explicarla como conteo de bordes sería mentir.
    ("CUMPLE — acredita 587 días.", 1218, 2),
    # un margen citado de pasada ("~7 días sobre el mínimo") no es el total
    ("CUMPLE — 740 días. Margen estrecho (~7 días sobre el mínimo).", 740, 1),
    # el veredicto cita MÁS días que el cómputo: eso no lo produce el inclusivo
    ("CUMPLE — acredita 1300 días.", 1269, 2),
    # sin periodos computables no hay desfase que justificar
    ("CUMPLE — acredita 1267 días.", 1269, 0),
])
def test_conciliar_no_publica_una_segunda_cifra(texto, verificado, periodos):
    resultado = conciliar_conclusion(texto, verificado, periodos)
    if periodos:
        assert resultado.startswith("CUMPLE según la evaluación inicial —")
        assert f"{verificado} días declarados" in resultado
    else:
        assert resultado == texto


def test_conciliar_conserva_el_verde_del_veredicto(tmp_path):
    """El prefijo va delante del «CUMPLE», así que el color tiene que salir del
    texto ORIGINAL o la celda perdería el verde justo al arreglarla."""
    espejo = {
        "_meta": {"analisis_id": "dias", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "GERENTE", "nombre": "N",
            "cumple": "CUMPLE — acredita 1267 días (3.47 años) frente a 2 años.",
            "total": {"dias": 1269},
            "total_backend": {"dias_efectivos": 1269, "anios_efectivos": 3.48,
                              "dias_paralizados": 0, "dias_traslape": 0},
            "experiencias": [
                {"n": 1, "proyecto": "A", "fecha_inicial": "2018-05-29",
                 "fecha_final": "2020-03-15", "dias": 657},
                {"n": 2, "proyecto": "B", "fecha_inicial": "2020-07-28",
                 "fecha_final": "2022-03-31", "dias": 612},
            ],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    ws = openpyxl.load_workbook(
        generar_excel_final(espejo, tmp_path / "dias.xlsx"))["CLAUDE"]
    celda = _buscar(ws, "según la evaluación inicial — 1269 días declarados")
    assert celda is not None
    assert _fill(celda) == str(FILL_CUMPLE.fgColor.rgb)

    # y la hoja del profesional dice el mismo número en sus dos superficies
    hoja_p = openpyxl.load_workbook(
        generar_excel_final(espejo, tmp_path / "dias.xlsx")).worksheets[2]
    conclusion = _buscar(hoja_p, "según la evaluación inicial")
    assert conclusion is not None and conclusion.value.startswith("CUMPLE según la evaluación inicial")


# ── 3 · el entregable no habla en jerga ──────────────────────────────────────

PROHIBIDOS = ("backend", "candado:", "espejo", "⟦", "agent-")


def _espejo_con_toda_la_jerga():
    """Un espejo armado para que TODOS los caminos que producían jerga corran."""
    return {
        "_meta": {"analisis_id": "jerga", "concurso": "CP-1", "postor": "P"},
        "postor": {
            "formularios": [{"anexo": "A1", "documento": "Doc", "folio": 1}],
            "oferta_economica": {"cuantia": 100.0, "limite_inferior": 90.0,
                                 "propuesta": 95.0, "detalle": "detalle"},
            "experiencia_postor": [{"n": 1, "cliente": "C", "proyecto": "P",
                                    "observaciones": "revisar con el backend"}],
            "postor_cumple": "SÍ — según agent-evaluador",
        },
        "profesionales": [{
            "n_prof": 1, "cargo": "ESPECIALISTA EN METRADOS, COSTOS Y VALORIZACIONES",
            "nombre": "N", "titulo": "Ingeniero Civil",
            "profesion_valida": "POR CONFIRMAR — verificar folio (backend/evaluador).",
            "colegiatura": "CIP 1", "certificaciones": "ninguna",
            "cumple": "CUMPLE — el backend lo confirma",
            "requisitos": {"cargos_validos": "Especialista en Metrados, Costos y "
                                             "Valorizaciones"},
            "total": {"dias": 100},
            "experiencias": [
                # fechas ilegibles → fila «Fechas no computables …»
                {"n": 1, "proyecto": "Obra sin fechas", "entidad_emisora": "E",
                 "cargo_ocupado": "Ingeniero de Costos",
                 "fecha_inicial": "POR VERIFICAR — folio ilegible",
                 "fecha_final": "POR VERIFICAR — folio ilegible",
                 "observaciones": "lo vio agent-propuesta-mapa"},
                {"n": 2, "proyecto": "Obra con fechas", "entidad_emisora": "E",
                 "cargo_ocupado": "Ingeniero de Costos",
                 "fecha_inicial": "2020-01-01", "fecha_final": "2020-04-09",
                 "dias": 100},
            ],
        }],
        "resumen_evaluacion": {
            "factores": [{"factor": "A", "criterio": "X", "puntaje": None}],
            "puntaje_total": 0,
            "nota": "revisar el espejo del backend",
        },
    }


def test_el_libro_entero_no_dice_una_sola_palabra_de_taller(tmp_path):
    """Búsqueda cerrada: los literales prohibidos, en TODAS las celdas.

    La marca del cargo se aplica antes de generar, que es el orden real del
    pipeline (`etapas_reales`: `anotar_cargo_nucleo` y después el entregable)."""
    from validacion import anotar_cargo_nucleo

    espejo = _espejo_con_toda_la_jerga()
    assert anotar_cargo_nucleo(espejo) >= 1, "el caso tiene que ejercitar la marca"
    wb = openpyxl.load_workbook(generar_excel_final(espejo, tmp_path / "j.xlsx"))

    hallados = [
        f"{hoja}!{c.coordinate} [{p}] {c.value[:120]}"
        for hoja, c in _celdas(wb) if isinstance(c.value, str)
        for p in PROHIBIDOS if p.lower() in c.value.lower()
    ]
    assert not hallados, "jerga visible en el entregable:\n" + "\n".join(hallados)


def test_la_marca_del_cargo_dice_en_castellano_lo_que_pasa():
    from validacion import anotar_cargo_nucleo

    espejo = _espejo_con_toda_la_jerga()
    anotar_cargo_nucleo(espejo)
    marcas = [e.get("cargo_bases_valido")
              for e in espejo["profesionales"][0]["experiencias"]]
    marcada = next(m for m in marcas if m and m.startswith(("NO —", "POR VERIFICAR —")))
    assert "el cargo certificado" in marcada and "exigido" in marcada
    assert "candado" not in marcada


def test_la_fila_de_fechas_ilegibles_manda_al_documento_original(tmp_path):
    espejo = _espejo_con_toda_la_jerga()
    wb = openpyxl.load_workbook(generar_excel_final(espejo, tmp_path / "f.xlsx"))
    celda = _buscar(wb.worksheets[2], "Fechas no computables")
    assert celda is not None
    assert "revisar contra el certificado original" in celda.value


# ── 4 · los dos amarillos ────────────────────────────────────────────────────

def _espejo_por_verificar():
    """Una experiencia en revisión + candado SEACE sin confirmar + ALT04 dudoso:
    los tres sentidos de «por verificar» que compartían el amarillo fuerte."""
    espejo = {
        "_meta": {"analisis_id": "amarillo", "concurso": "C", "postor": "P"},
        "postor": {},
        "profesionales": [{
            "n_prof": 1, "cargo": "JEFE", "nombre": "N",
            "cumple": "CUMPLE — porque sí",
            "experiencias": [{"n": 1, "proyecto": "Obra", "entidad_emisora": "E",
                              "fecha_inicial": "2020-01-01",
                              "fecha_final": "2020-04-09", "dias": 100}],
        }],
        "resumen_evaluacion": {"factores": []},
    }
    extras = {
        "fichas": {(1, 1): {"seace": {"estado": "sin_procesos"}}},
        "revisiones": {(1, 1): ("no se pudo confirmar la obra",
                                "pegar el CUI en el panel")},
        "sunat": {(1, 1): {"ruc": "20100000001", "razon_social": "EMPRESA SA",
                           "alt04": {"estado": "REINSCRIPCION",
                                     "mensaje": "probable reinscripción"}}},
    }
    return espejo, extras


def test_lo_que_esta_por_verificar_usa_el_amarillo_suave(tmp_path):
    espejo, extras = _espejo_por_verificar()
    wb = openpyxl.load_workbook(
        generar_excel_final(espejo, tmp_path / "am.xlsx", **extras))
    hoja = wb.worksheets[2]

    for texto in ("No disponible en datos abiertos", "🟡 ALT04",
                  "PROVISIONAL — POR VERIFICAR"):
        celda = _buscar(hoja, texto)
        assert celda is not None, f"el caso no ejercitó «{texto}»"
        assert _fill(celda) == AMARILLO_SUAVE, (
            f"«{texto}» sigue en el amarillo del dato declarado")


def test_el_amarillo_fuerte_solo_marca_lo_que_la_leyenda_promete(tmp_path):
    """FFFF00 queda para el dato del certificado, la valorización dentro del
    periodo, los separadores y el encabezado CERT — nada más."""
    espejo, extras = _espejo_por_verificar()
    wb = openpyxl.load_workbook(
        generar_excel_final(espejo, tmp_path / "am.xlsx", **extras))
    hoja = wb.worksheets[2]
    permitidos = ("CERT. N°", "Periodo certificado", "Certificado", "—",
                  "2020", "100")
    for fila in hoja.iter_rows():
        for c in fila:
            if _fill(c) != AMARILLO_FUERTE or c.value in (None, ""):
                continue
            v = str(c.value)
            assert any(p in v for p in permitidos), \
                f"amarillo fuerte sobre algo que la leyenda no cubre: {v[:120]!r}"


def test_la_leyenda_de_la_hoja_del_profesional_declara_los_dos_que_faltaban(tmp_path):
    espejo, extras = _espejo_por_verificar()
    wb = openpyxl.load_workbook(
        generar_excel_final(espejo, tmp_path / "am.xlsx", **extras))
    leyenda = _buscar(wb.worksheets[2], "LEYENDA:").value
    assert "amarillo claro = por verificar" in leyenda
    assert "verde = verificado correcto" in leyenda
    # y lo que ya prometía sigue ahí
    assert "amarillo = dato del certificado" in leyenda
    assert "cyan = efectivo verificado" in leyenda


def test_fill_pend_es_el_amarillo_suave():
    """El color de «por verificar» es uno solo en todo el proyecto."""
    assert str(FILL_PEND.fgColor.rgb) == AMARILLO_SUAVE
