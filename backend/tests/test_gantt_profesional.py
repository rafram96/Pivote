"""Contrato visual e integración del Gantt profesional, con datos sintéticos."""
from __future__ import annotations

import copy
from datetime import date
from io import BytesIO

import openpyxl
import pytest
from PIL import Image
from openpyxl.drawing.image import Image as XLImage

from entregables import generar_excel_final
from entregables.cronologia import construir_eje
from entregables.excel_final import (
    _bloques_linea_de_tiempo, desempaquetar_enriquecimiento,
)
from entregables.gantt_profesional import renderizar_gantt_profesional
from schemas.cargo import etiqueta_hoja


def _bloque(eje=None, filas=None):
    return {
        "cabecera": "PROFESIONAL 1 · Persona Ficticia · 365 días efectivos",
        "escala": "AÑO",
        "eje": eje or [],
        "filas": filas or [],
        "traslapes": [],
        "rotulo_traslapes": "Traslapes · Sin traslapes",
        "total": "TOTAL EFECTIVO NETO · 365 días",
    }


def _abrir_png(resultado):
    contenido, ancho, alto = resultado
    imagen = Image.open(contenido)
    imagen.load()
    return imagen, ancho, alto


def test_pinta_los_tres_colores_reales_sin_amarillo_para_la_privada():
    eje = construir_eje(date(2024, 1, 1), date(2024, 1, 31))
    filas = [
        {"rotulo": "Confirmada", "celdas": [0], "color": "D9EAD3", "marcas": {}},
        {"rotulo": "Inferida", "celdas": [0], "color": "E4D7F5", "marcas": {}},
        {"rotulo": "Privada", "celdas": [0], "color": "D9D9D9", "marcas": {}},
    ]
    imagen, _, _ = _abrir_png(renderizar_gantt_profesional(_bloque(eje, filas)))
    # Muestrear las barras, no las muestras de la leyenda (incluye amarillo).
    y_privada = imagen.height - 24 - 48 - 42 - 21
    assert imagen.getpixel((imagen.width - 40, y_privada - 84)) == (217, 234, 211)
    assert imagen.getpixel((imagen.width - 40, y_privada - 42)) == (228, 215, 245)
    assert imagen.getpixel((imagen.width - 40, y_privada)) == (217, 217, 217)


@pytest.mark.parametrize("ancho", [1100, 1800])
def test_leyenda_visible_completa_con_muestras_y_sin_recortes(monkeypatch, ancho):
    import entregables.gantt_profesional as gantt
    from entregables.leyenda_gantt import COLORES_GANTT, MARCAS_GANTT, NOTAS_GANTT

    textos, limites = [], []
    envolver = gantt._texto_envuelto
    pintar = gantt.ImageDraw.ImageDraw.text

    def registrar(draw, xy, texto, *args, **kwargs):
        textos.append(texto)
        return envolver(draw, xy, texto, *args, **kwargs)

    def registrar_linea(draw, xy, texto, *args, **kwargs):
        limites.append(draw.textbbox(xy, texto, font=kwargs.get("font")))
        return pintar(draw, xy, texto, *args, **kwargs)

    monkeypatch.setattr(gantt, "_texto_envuelto", registrar)
    monkeypatch.setattr(gantt.ImageDraw.ImageDraw, "text", registrar_linea)
    imagen, _, alto = _abrir_png(renderizar_gantt_profesional(_bloque(), ancho))
    for _, significado in (*COLORES_GANTT, *MARCAS_GANTT):
        assert significado in textos
    assert all(nota in textos for nota in NOTAS_GANTT)
    colores = {color for _, color in imagen.getcolors(ancho * alto)}
    for color, _ in COLORES_GANTT:
        assert tuple(bytes.fromhex(color)) in colores
    assert all(0 <= x0 <= x1 < ancho and 0 <= y0 <= y1 < alto
               for x0, y0, x1, y1 in limites)


def test_sin_eje_conserva_todas_las_filas_y_el_total_dentro_del_lienzo():
    filas = [{"rotulo": f"Experiencia {n} sin fechas computables " * 4,
              "celdas": [], "color": "D9EAD3", "marcas": {}}
             for n in range(1, 8)]
    imagen, ancho, alto = _abrir_png(renderizar_gantt_profesional(_bloque([], filas)))
    assert imagen.size == (ancho, alto)
    # El bloque total se pinta al final y no queda cortado por el borde inferior.
    assert any(imagen.getpixel((x, alto - 25)) != (255, 255, 255)
               for x in range(24, ancho - 24, 20))
    assert alto > 7 * 42


def test_anio_de_un_slot_mensual_rota_su_etiqueta_en_ancho_minimo(monkeypatch):
    # 60 meses conserva grano mensual. Diciembre-2019 y noviembre-2024 dejan
    # ambos años extremos con un solo slot, la rama realmente estrecha.
    eje = construir_eje(date(2019, 12, 1), date(2024, 11, 30))
    fila = {"rotulo": "Experiencia de cinco años", "celdas": list(range(60)),
            "color": "D9EAD3", "marcas": {0: "C/R"}}
    rotaciones = []
    original = Image.Image.rotate

    def espiar_rotacion(self, angle, *args, **kwargs):
        resultado = original(self, angle, *args, **kwargs)
        rotaciones.append((angle, kwargs.get("expand"), self.size, resultado.size,
                           resultado.getbbox()))
        return resultado

    monkeypatch.setattr(Image.Image, "rotate", espiar_rotacion)
    imagen, ancho, alto = _abrir_png(
        renderizar_gantt_profesional(_bloque(eje, [fila]), ancho=1100))
    assert (ancho, alto) == imagen.size
    assert ancho == 1100
    assert len(eje) == 60
    assert any(angle == 90 and expand is True and bbox is not None
               and salida == (entrada[1], entrada[0])
               for angle, expand, entrada, salida, bbox in rotaciones)


def _espejo(tipo="expedientes"):
    return {
        "_meta": {"tipo_evaluacion": tipo, "concurso": "CP-FICTICIO/2026"},
        "postor": {}, "reglas_evaluacion": {"periodos_sin_dia": "mes_completo"},
        "profesionales": [{
            "n_prof": 1, "nombre": "Persona Ficticia",
            "cargo": "ESPECIALISTA FICTICIO", "colegiatura": "CIP 99999",
            "requisitos": {"tipo_experiencia_valida": "Experiencia mínima: 1 año."},
            "experiencias": [{"n": 1, "proyecto": "Expediente ficticio",
                              "entidad_emisora": "Entidad Ficticia", "cui": "1234567",
                              "cargo_ocupado": "Especialista",
                              "fecha_inicial": "2024-01-01",
                              "fecha_final": "2024-12-31"}]}],
        "resumen_evaluacion": {"factores": [], "puntaje_total": None},
    }


def _enriquecimiento():
    return {"1:1": {"via": "CUI_TEXTO", "cui": "1234567",
                     "sin_documentos_mef": True}}


def test_libro_expedientes_agrega_una_imagen_final_y_dentro_del_area_impresa(tmp_path):
    espejo, enr = _espejo(), _enriquecimiento()
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / "expedientes.xlsx", paral,
                                 cuis, fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "ESPECIALISTA FICTICIO")]
    assert len(ws._images) == 1
    fila_imagen = ws._images[0].anchor._from.row + 1
    ultima_fila_datos = max(c.row for fila in ws.iter_rows() for c in fila
                            if c.value is not None and c.row < fila_imagen)
    assert fila_imagen > ultima_fila_datos
    fin_area = int(str(ws.print_area).rsplit("$", 1)[-1])
    assert fila_imagen <= fin_area


def test_gantt_queda_despues_del_factor_cuando_el_factor_existe(tmp_path):
    import fitz

    factor = tmp_path / "P1_FACTOR.pdf"
    doc = fitz.open()
    pagina = doc.new_page(width=300, height=200)
    pagina.insert_text((30, 50), "FACTOR A - EXPERIENCIA DEL PERSONAL CLAVE")
    doc.save(factor)
    doc.close()

    espejo, enr = _espejo(), _enriquecimiento()
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(
        espejo, tmp_path / "con_factor.xlsx", paral, cuis, fichas, {}, sunat,
        {(1, "FACTOR"): factor})
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "ESPECIALISTA FICTICIO")]
    filas_imagen = [imagen.anchor._from.row + 1 for imagen in ws._images]
    assert len(filas_imagen) == 2
    assert filas_imagen[-1] > filas_imagen[0]
    fin_area = int(str(ws.print_area).rsplit("$", 1)[-1])
    assert filas_imagen[-1] <= fin_area


def test_libro_de_obras_no_agrega_gantt_profesional(tmp_path):
    espejo = _espejo("obras")
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(_enriquecimiento())
    salida = generar_excel_final(espejo, tmp_path / "obras.xlsx", paral,
                                 cuis, fichas, {}, sunat)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(1, "ESPECIALISTA FICTICIO")]
    assert ws._images == []


def test_bloque_respeta_guardas_cr_y_no_muta_entradas():
    espejo = _espejo()
    fichas = {(1, 1): {
        "via": "CUI_TEXTO", "cui": "1234567",
        "verificacion_expediente": {
            "verificado_en_mef": False,
            "contrato": {"fecha": "2023-12-01", "veredicto": "discrepancia"},
            "resolucion": {"fecha": "2025-01-15", "veredicto": "no_verificable"}},
    }}
    antes_espejo, antes_fichas = copy.deepcopy(espejo), copy.deepcopy(fichas)
    bloque = _bloques_linea_de_tiempo(espejo, fichas, "expedientes")[0]
    assert all("C" not in str(marca) and "R" not in str(marca)
               for fila in bloque["filas"] for marca in fila["marcas"].values())
    assert espejo == antes_espejo
    assert fichas == antes_fichas


def test_png_en_memoria_se_puede_guardar_y_reabrir_con_openpyxl(tmp_path):
    eje = construir_eje(date(2024, 1, 1), date(2024, 1, 31))
    contenido, ancho, alto = renderizar_gantt_profesional(_bloque(eje, []))
    assert isinstance(contenido, BytesIO)
    wb = openpyxl.Workbook()
    imagen = XLImage(contenido)
    imagen.width, imagen.height = ancho, alto
    wb.active.add_image(imagen, "A2")
    salida = tmp_path / "imagen.xlsx"
    wb.save(salida)
    assert len(openpyxl.load_workbook(salida).active._images) == 1


def test_render_continuo_conserva_marcas_y_filas_sin_fechas_sin_mutar(monkeypatch):
    from entregables.cronologia import GRANO_BIMESTRE
    from PIL import ImageDraw
    eje = construir_eje(date(2000, 1, 1), date(2024, 12, 31), GRANO_BIMESTRE)
    bloque = _bloque(eje, [
        {"rotulo": "Largo", "celdas": list(range(150)), "marcas": {35: "C", 36: "R"}},
        {"rotulo": "Sin fechas", "celdas": [], "marcas": {}},
    ])
    bloque["traslapes"] = {35, 36}
    antes = copy.deepcopy(bloque)
    textos = []
    original = ImageDraw.ImageDraw.text
    def espiar(self, xy, text, *args, **kwargs):
        textos.append(text)
        return original(self, xy, text, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", espiar)
    renderizar_gantt_profesional(bloque)
    assert textos.count("LEYENDA — COLORES Y MARCAS") == 1
    assert textos.count("Largo") == textos.count("Sin fechas") == 1
    assert "C" in textos and "R" in textos
    assert not any("Continúa" in t for t in textos)
    assert bloque == antes


def test_fechas_asumidas_no_se_presentan_como_exactas_documentadas():
    espejo = _espejo()
    espejo["profesionales"][0]["experiencias"][0]["supuestos"] = ["fecha_final"]
    rotulo = _bloques_linea_de_tiempo(espejo, {}, "expedientes")[0]["filas"][0]["rotulo"]
    assert "Inicio: 01/01/2024 · Fin: 31/12/2024" in rotulo
    assert "Fecha asumida en la extracción: fin" in rotulo
