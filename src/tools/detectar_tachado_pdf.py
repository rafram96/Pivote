"""Detecta y remueve el TACHADO de un PDF born-digital de bases OSCE.

En las "Bases Integradas Definitivas" el texto tachado son **requisitos que se
ELIMINARON** durante la integración. Al imprimirse a PDF el `w:strike` de Word
se convierte en una línea/rectángulo dibujado que cruza el texto: la visión y el
OCR NO lo distinguen y leen lo eliminado como vigente, en silencio.

Cuando existe el DOCX hay que usar `skill/scripts/limpiar_bases_docx.py` (quita
los runs `w:strike` de forma determinística). Este script es para el caso en que
**solo hay PDF** y es born-digital: detecta la línea de tachado geométricamente y
descarta los caracteres que cruza, char a char.

Salidas:
  <salida>.txt  texto completo SIN lo tachado, marcado por `===== PAGINA N =====`
  <salida>.md   reporte de qué se eliminó, por página

Uso:
  venv/Scripts/python.exe src/tools/detectar_tachado_pdf.py bases.pdf _prep/bases_texto
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import fitz

# Una línea de tachado es un rect muy fino y ancho. Tolerancias en puntos PDF.
ALTURA_MAX_LINEA = 2.6  # más gruesa que esto es un borde de tabla / subrayado grueso
ANCHO_MIN_LINEA = 3.0  # más corta que esto es ruido (puntos, viñetas)
# El tachado cruza el glifo por la mitad; el subrayado va al pie. Se acepta la
# línea solo si cae en la banda central de la altura del carácter.
BANDA_CENTRAL = (0.25, 0.75)
SOLAPE_MIN = 0.55  # fracción del ancho del char que la línea debe cubrir


def _lineas_horizontales(pagina: fitz.Page) -> list[fitz.Rect]:
    """Rects finos y horizontales dibujados en la página (candidatos a tachado)."""
    lineas: list[fitz.Rect] = []
    for dibujo in pagina.get_drawings():
        for item in dibujo["items"]:
            tipo = item[0]
            if tipo == "l":  # línea: ("l", p1, p2)
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) <= ALTURA_MAX_LINEA and abs(p1.x - p2.x) >= ANCHO_MIN_LINEA:
                    y = (p1.y + p2.y) / 2
                    lineas.append(fitz.Rect(min(p1.x, p2.x), y - 0.6, max(p1.x, p2.x), y + 0.6))
            elif tipo == "re":  # rectángulo relleno usado como línea
                r = item[1]
                if r.height <= ALTURA_MAX_LINEA and r.width >= ANCHO_MIN_LINEA:
                    lineas.append(fitz.Rect(r))
    return lineas


def _esta_tachado(bbox: fitz.Rect, lineas: list[fitz.Rect]) -> bool:
    if bbox.height <= 0 or bbox.width <= 0:
        return False
    y_min = bbox.y0 + bbox.height * BANDA_CENTRAL[0]
    y_max = bbox.y0 + bbox.height * BANDA_CENTRAL[1]
    for linea in lineas:
        y_linea = (linea.y0 + linea.y1) / 2
        if not (y_min <= y_linea <= y_max):
            continue
        solape = min(bbox.x1, linea.x1) - max(bbox.x0, linea.x0)
        if solape / bbox.width >= SOLAPE_MIN:
            return True
    return False


def procesar(ruta_pdf: Path, base_salida: Path) -> dict:
    doc = fitz.open(ruta_pdf)
    texto_limpio: list[str] = []
    eliminado_por_pagina: dict[int, list[str]] = defaultdict(list)
    total_chars_tachados = 0

    for n, pagina in enumerate(doc, start=1):
        lineas = _lineas_horizontales(pagina)
        partes_pagina: list[str] = []
        # Se recorre char a char para respetar tachado PARCIAL dentro de un párrafo.
        for bloque in pagina.get_text("rawdict")["blocks"]:
            if bloque.get("type") != 0:
                continue
            for linea_txt in bloque["lines"]:
                buffer_ok: list[str] = []
                buffer_tachado: list[str] = []
                for span in linea_txt["spans"]:
                    for ch in span["chars"]:
                        bbox = fitz.Rect(ch["bbox"])
                        if lineas and _esta_tachado(bbox, lineas):
                            buffer_tachado.append(ch["c"])
                            total_chars_tachados += 1
                        else:
                            buffer_ok.append(ch["c"])
                if buffer_ok:
                    partes_pagina.append("".join(buffer_ok))
                if buffer_tachado:
                    frag = "".join(buffer_tachado).strip()
                    if len(frag) >= 3:  # fragmentos de 1-2 chars son casi siempre bordes de tabla
                        eliminado_por_pagina[n].append(frag)
        texto_limpio.append(f"===== PAGINA {n} =====\n" + "\n".join(partes_pagina))

    txt = base_salida.with_suffix(".txt")
    txt.write_text("\n".join(texto_limpio), encoding="utf-8")

    lineas_md = [
        f"# Tachado detectado en `{ruta_pdf.name}`",
        "",
        f"- Páginas: **{doc.page_count}**",
        f"- Caracteres tachados removidos: **{total_chars_tachados}**",
        f"- Páginas con tachado: **{len(eliminado_por_pagina)}**",
        "",
        "> Lo tachado son **requisitos ELIMINADOS**. El texto limpio "
        f"(`{txt.name}`) es la fuente de requisitos, no el PDF.",
        "",
    ]
    if eliminado_por_pagina:
        lineas_md.append("## Qué se eliminó, por página")
        lineas_md.append("")
        for n in sorted(eliminado_por_pagina):
            fragmentos = eliminado_por_pagina[n]
            lineas_md.append(f"### pág {n} — {len(fragmentos)} fragmento(s)")
            for frag in fragmentos[:40]:
                lineas_md.append(f"- `{frag[:300]}`")
            if len(fragmentos) > 40:
                lineas_md.append(f"- … y {len(fragmentos) - 40} más")
            lineas_md.append("")
    else:
        lineas_md.append("**No se detectó tachado.** El PDF se puede leer directo.")
        lineas_md.append("")

    base_salida.with_suffix(".md").write_text("\n".join(lineas_md), encoding="utf-8")
    doc.close()
    return {
        "paginas": len(texto_limpio),
        "chars_tachados": total_chars_tachados,
        "paginas_con_tachado": sorted(eliminado_por_pagina),
    }


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    ruta_pdf = Path(sys.argv[1])
    base_salida = Path(sys.argv[2])
    base_salida.parent.mkdir(parents=True, exist_ok=True)
    r = procesar(ruta_pdf, base_salida)
    print(
        f"{ruta_pdf.name}: {r['paginas']} págs · "
        f"{r['chars_tachados']} chars tachados · "
        f"págs con tachado: {r['paginas_con_tachado'] or 'ninguna'}"
    )


if __name__ == "__main__":
    main()
