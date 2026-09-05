"""Render determinista del Gantt profesional para embeberlo en Excel.

Este modulo no interpreta experiencias ni decide hitos: recibe un bloque ya
resuelto por ``excel_final._bloques_linea_de_tiempo``. Asi la vista grafica no
puede divergir de la cronologia editable ni de sus compuertas C/R.
"""
from __future__ import annotations

import io
import textwrap
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from entregables.leyenda_gantt import COLORES_GANTT, MARCAS_GANTT, NOTAS_GANTT


_FONDO = "#FFFFFF"
_AZUL = "#1F4E78"
_AZUL_CLARO = "#DDEBF7"
_TEXTO = "#17212B"
_REJILLA = "#AAB7C4"
_TRASLAPE = "#F4B183"
_COLORES = {
    "D9EAD3": "#D9EAD3",
    "E4D7F5": "#E4D7F5",
    "FFF2CC": "#FFF2CC",
    "D9D9D9": "#D9D9D9",
}


def _fuente(tamano: int, negrita: bool = False):
    nombres = (["DejaVuSans-Bold.ttf", "arialbd.ttf"] if negrita else
               ["DejaVuSans.ttf", "arial.ttf"])
    for nombre in nombres:
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            pass
    return ImageFont.load_default()


def _lineas(texto: str, caracteres: int) -> list[str]:
    salida: list[str] = []
    for linea in str(texto or "").splitlines() or [""]:
        salida.extend(textwrap.wrap(linea, width=max(8, caracteres),
                                    break_long_words=False) or [""])
    return salida


def _texto_envuelto(draw, xy, texto, fuente, ancho_px, color=_TEXTO,
                    interlineado=3) -> int:
    promedio = max(5, int(getattr(fuente, "size", 12) * .57))
    lineas = _lineas(texto, ancho_px // promedio)
    x, y = xy
    alto = int(getattr(fuente, "size", 12) * 1.25)
    for linea in lineas:
        draw.text((x, y), linea, font=fuente, fill=color)
        y += alto + interlineado
    return len(lineas) * (alto + interlineado)


def renderizar_gantt_profesional(bloque: dict, ancho: int = 1800) -> tuple[io.BytesIO, int, int]:
    """Devuelve ``(PNG en memoria, ancho, alto)`` para un bloque resuelto."""
    ancho = max(1100, int(ancho))
    margen = 24
    ancho_rotulo = min(650, max(470, int(ancho * .34)))
    eje = bloque.get("eje") or []
    filas = bloque.get("filas") or []
    fuente_b = _fuente(21, True)
    fuente_c = _fuente(17, True)
    fuente_u = _fuente(15, True)
    fuente_f = _fuente(16)

    alto_cabecera = max(58, len(_lineas(bloque.get("cabecera", ""), 110)) * 30 + 18)
    ancho_col_leyenda = (ancho - 2 * margen - 28) // 2
    ancho_texto_leyenda = ancho_col_leyenda - 96

    def alto_texto(texto, ancho_px):
        caracteres = ancho_px // max(5, int(16 * .57))
        return len(_lineas(texto, caracteres)) * 23

    altos_leyenda = [max(36, alto_texto(color[1], ancho_texto_leyenda) + 10,
                         alto_texto(marca[1], ancho_texto_leyenda) + 10)
                     for color, marca in zip(COLORES_GANTT, MARCAS_GANTT)]
    altos_notas = [alto_texto(nota, ancho - 2 * margen - 28) + 8
                   for nota in NOTAS_GANTT]
    alto_leyenda = 42 + sum(altos_leyenda) + sum(altos_notas) + 10
    alto_eje = 58 if eje else 0
    caracteres_rotulo = max(8, (ancho_rotulo - 18) // max(5, int(16 * .57)))
    altos_fila = [max(42, len(_lineas(f.get("rotulo", ""), caracteres_rotulo)) * 23 + 12)
                  for f in filas]
    alto_traslape = 42 if eje else 0
    alto_total = 48
    alto_aviso = 46 if not eje else 0
    alto = (margen * 2 + alto_cabecera + alto_leyenda + alto_eje + alto_aviso
            + sum(altos_fila) + alto_traslape + alto_total)
    imagen = Image.new("RGB", (ancho, alto), _FONDO)
    d = ImageDraw.Draw(imagen)

    y = margen
    d.rectangle((margen, y, ancho - margen, y + alto_cabecera), fill=_AZUL)
    _texto_envuelto(d, (margen + 14, y + 10), bloque.get("cabecera", ""),
                    fuente_b, ancho - 2 * margen - 28, "#FFFFFF")
    y += alto_cabecera

    d.rectangle((margen, y, ancho - margen, y + alto_leyenda), fill=_AZUL_CLARO)
    d.text((margen + 14, y + 9), "LEYENDA — COLORES Y MARCAS", font=fuente_b, fill=_TEXTO)
    yl = y + 42
    for (color, texto), (marca, significado), h in zip(
            COLORES_GANTT, MARCAS_GANTT, altos_leyenda):
        x = margen + 14
        d.rectangle((x, yl + 4, x + 28, yl + 26), fill="#" + color, outline=_REJILLA)
        _texto_envuelto(d, (x + 42, yl + 3), texto, fuente_f, ancho_texto_leyenda)
        x += ancho_col_leyenda
        d.text((x, yl + 4), marca, font=fuente_c, fill="#9C0006")
        _texto_envuelto(d, (x + 82, yl + 3), significado, fuente_f, ancho_texto_leyenda)
        yl += h
    for nota, h in zip(NOTAS_GANTT, altos_notas):
        _texto_envuelto(d, (margen + 14, yl + 3), nota, fuente_f, ancho - 2 * margen - 28)
        yl += h
    y += alto_leyenda

    if not eje:
        aviso = "Sin período computable: las experiencias se conservan abajo, sin barra."
        d.text((margen + 14, y + 10), aviso, font=fuente_b, fill=_TEXTO)
        y += 46
    else:
        x0 = margen + ancho_rotulo
        unidad = (ancho - margen - x0) / len(eje)
        d.rectangle((margen, y, x0, y + alto_eje), fill=_AZUL, outline=_REJILLA)
        d.text((margen + 10, y + 17), bloque.get("escala") or "Eje temporal",
               font=fuente_c, fill="#FFFFFF")
        for i, u in enumerate(eje):
            xa, xb = x0 + i * unidad, x0 + (i + 1) * unidad
            d.rectangle((xa, y, xb, y + alto_eje), fill=_AZUL_CLARO, outline=_REJILLA)
            etiqueta = str(getattr(u, "etiqueta", "") or "")
            if etiqueta:
                d.text((xa + max(2, (unidad - d.textlength(etiqueta, font=fuente_u)) / 2),
                        y + 31), etiqueta, font=fuente_u, fill=_TEXTO)
        for i0, i1, anio in _tramos_anio(eje):
            xa, xb = x0 + i0 * unidad, x0 + (i1 + 1) * unidad
            texto = str(anio)
            ancho_texto = d.textlength(texto, font=fuente_u)
            if xb - xa >= ancho_texto + 4:
                d.text((xa + (xb - xa - ancho_texto) / 2, y + 6), texto,
                       font=fuente_u, fill=_TEXTO)
            else:
                capa = Image.new("RGBA", (50, 24), (255, 255, 255, 0))
                dc = ImageDraw.Draw(capa)
                dc.text((1, 1), texto, font=fuente_u, fill=_TEXTO)
                giro = capa.rotate(90, expand=True)
                imagen.paste(giro, (int(xa + max(0, (xb - xa - giro.width) / 2)),
                                    int(y + 2)), giro)
        y += alto_eje

    x0 = margen + ancho_rotulo
    unidad = ((ancho - margen - x0) / len(eje)) if eje else 0
    for f, h in zip(filas, altos_fila):
        d.rectangle((margen, y, x0, y + h), fill="#FFFFFF", outline=_REJILLA)
        _texto_envuelto(d, (margen + 9, y + 7), f.get("rotulo", ""), fuente_f,
                        ancho_rotulo - 18)
        if eje:
            for i in range(len(eje)):
                xa, xb = x0 + i * unidad, x0 + (i + 1) * unidad
                relleno = (_COLORES.get(str(f.get("color") or "").upper(), "#FFF2CC")
                           if i in set(f.get("celdas") or []) else "#FFFFFF")
                d.rectangle((xa, y, xb, y + h), fill=relleno, outline=_REJILLA)
            for i, marca in (f.get("marcas") or {}).items():
                xa = x0 + int(i) * unidad
                d.text((xa + max(1, (unidad - d.textlength(str(marca), font=fuente_c)) / 2),
                        y + max(2, (h - 20) / 2)), str(marca), font=fuente_c,
                       fill="#9C0006")
        y += h

    if eje:
        d.rectangle((margen, y, x0, y + alto_traslape), fill="#FFFFFF", outline=_REJILLA)
        d.text((margen + 9, y + 11), bloque.get("rotulo_traslapes", "Traslapes"),
               font=fuente_c, fill=_TEXTO)
        for i in range(len(eje)):
            xa, xb = x0 + i * unidad, x0 + (i + 1) * unidad
            d.rectangle((xa, y, xb, y + alto_traslape),
                        fill=(_TRASLAPE if i in set(bloque.get("traslapes") or []) else _FONDO),
                        outline=_REJILLA)
        y += alto_traslape

    d.rectangle((margen, y, ancho - margen, y + alto_total), fill=_AZUL_CLARO,
                outline=_REJILLA)
    d.text((margen + 10, y + 13), bloque.get("total", ""), font=fuente_b,
           fill=_TEXTO)
    salida = io.BytesIO()
    imagen.save(salida, "PNG", optimize=False)
    salida.seek(0)
    return salida, ancho, alto


def _tramos_anio(eje) -> list[tuple[int, int, int]]:
    tramos: list[tuple[int, int, int]] = []
    for i, unidad in enumerate(eje):
        inicio = getattr(unidad, "inicio", None)
        anio = inicio.year if isinstance(inicio, date) else None
        if tramos and tramos[-1][2] == anio:
            tramos[-1] = (tramos[-1][0], i, anio)
        else:
            tramos.append((i, i, anio))
    return tramos
