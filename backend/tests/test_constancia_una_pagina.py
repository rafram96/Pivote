"""
La hoja del profesional embebe SOLO la constancia; el PDF completo va al ZIP.

Contexto (2026-09-12): el postor adjunta detrás de la constancia lo que quiere
—una resolución gerencial de diez páginas, por ejemplo— y la hoja del Excel se
inflaba en cientos de filas sin aportar nada a la evaluación. Ahora la hoja
muestra la primera página y avisa; el PDF íntegro entra al ZIP como
`CONSTANCIA_P{n}_E{m}.pdf`, rotulado como ADJUNTO de la propuesta y sin contar
como documento descargado de una fuente oficial.

Sin red y sin datos del cliente: los PDFs se generan con fitz en `tmp_path`.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
import pytest

from entregables import construir_zip_infoobras, generar_excel_final

_AVISO = ("Documento de 3 páginas; el PDF completo está en el ZIP "
          "(carpeta de la experiencia).")

ESPEJO = {
    "_meta": {"analisis_id": "t-constancia", "concurso": "CP-TEST/2026",
              "postor": "POSTOR DEMO"},
    "postor": {},
    "profesionales": [{
        "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "Profesional Uno",
        "colegiatura": "CIP 11111",
        "experiencias": [{
            "n": 1, "proyecto": "Obra Sintética A", "entidad_emisora": "EMISOR DEMO",
            "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
            "dias": 724, "incluye_covid": "NO", "folio": "100",
        }],
    }],
    "resumen_evaluacion": {"factores": [], "puntaje_total": None},
}


def _pdf(destino: Path, paginas: int) -> Path:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for n in range(paginas):
        doc.new_page().insert_text((72, 100), f"CONSTANCIA PAGINA {n + 1}")
    doc.save(str(destino))
    doc.close()
    return destino


def _filas_usadas(ws) -> int:
    return max((c.row for (c,) in ws.iter_rows(min_col=1, max_col=1)
                if c.value not in (None, "")), default=0)


def _hoja_prof(salida: Path):
    return next(s for s in openpyxl.load_workbook(salida).worksheets
                if s.title.startswith("P1"))


def _textos(ws) -> list[str]:
    return [str(c.value) for (c,) in ws.iter_rows(min_col=1, max_col=1) if c.value]


def test_hoja_profesional_embebe_solo_la_constancia(tmp_path):
    """3 páginas → 1 imagen y una sola fila de aviso; nada de 'Página 2/3'."""
    cert = _pdf(tmp_path / "P1_E1.pdf", 3)
    salida = generar_excel_final(ESPEJO, tmp_path / "tres.xlsx",
                                 certificados={(1, 1): cert})
    ws = _hoja_prof(salida)
    assert len(ws._images) == 1
    textos = _textos(ws)
    assert textos.count(_AVISO) == 1
    assert not any(t.startswith("Página 2") or t.startswith("Página 3")
                   for t in textos)
    assert "Página principal" in textos


def test_constancia_de_una_pagina_no_lleva_aviso(tmp_path):
    cert = _pdf(tmp_path / "P1_E1.pdf", 1)
    salida = generar_excel_final(ESPEJO, tmp_path / "una.xlsx",
                                 certificados={(1, 1): cert})
    ws = _hoja_prof(salida)
    assert len(ws._images) == 1
    assert not any(t.startswith("Documento de ") for t in _textos(ws))


def test_hoja_mas_corta_que_con_todas_las_paginas(tmp_path):
    """La medida del cambio: la hoja con el adjunto completo era mucho más larga."""
    cert = _pdf(tmp_path / "P1_E1.pdf", 3)
    filas_1 = _filas_usadas(_hoja_prof(generar_excel_final(
        ESPEJO, tmp_path / "a.xlsx", certificados={(1, 1): cert})))
    # ruta antigua (equivalente): las 3 páginas embebidas
    import entregables.excel_final as ef
    original = ef._render_cert_pages
    try:
        ef._render_cert_pages = (
            lambda pdf, dpi=130, q=70, max_pag=12: original(pdf, dpi, q, 12))
        filas_3 = _filas_usadas(_hoja_prof(generar_excel_final(
            ESPEJO, tmp_path / "b.xlsx", certificados={(1, 1): cert})))
    finally:
        ef._render_cert_pages = original
    assert filas_1 < filas_3


def test_zip_lleva_la_constancia_completa_como_adjunto(tmp_path):
    cert = _pdf(tmp_path / "P1_E1.pdf", 3)
    docs = tmp_path / "docs"
    (docs / "Cronograma").mkdir(parents=True)
    (docs / "Cronograma" / "doc1.pdf").write_bytes(b"%PDF-1.4 demo")
    salida = construir_zip_infoobras(ESPEJO, {(1, 1): docs},
                                     tmp_path / "entrega.zip",
                                     certificados={(1, 1): cert})
    with zipfile.ZipFile(salida) as zf:
        ruta = next(n for n in zf.namelist() if n.endswith("CONSTANCIA_P1_E1.pdf"))
        # va DENTRO de la carpeta P/E de la experiencia, y es el PDF íntegro
        assert ruta.startswith("P01 ") and "/E1 " in ruta
        assert zf.read(ruta) == cert.read_bytes()
        indice = zf.read("indice.txt").decode("utf-8")
        manifiesto = next(zf.read(n).decode("utf-8") for n in zf.namelist()
                          if n.endswith("MANIFIESTO_DOCUMENTOS.txt"))
    rotulo = "Constancia presentada en la propuesta (3 páginas)"
    assert rotulo in indice
    assert rotulo in manifiesto
    assert "no descargado de una fuente oficial" in manifiesto
    # NO cuenta como documento descargado: sigue habiendo 1 solo documento
    assert "1 documento(s)" in indice


def test_zip_sin_certificados_no_cambia(tmp_path):
    """Sin `certificados` el ZIP es el de siempre: el parámetro es opcional."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "doc1.pdf").write_bytes(b"%PDF-1.4 demo")
    salida = construir_zip_infoobras(ESPEJO, {(1, 1): docs}, tmp_path / "sin.zip")
    with zipfile.ZipFile(salida) as zf:
        assert not any("CONSTANCIA_" in n for n in zf.namelist())
        assert "Constancia presentada" not in zf.read("indice.txt").decode("utf-8")


def test_zip_constancia_sin_descargas_no_levanta_sin_documentos(tmp_path):
    """Una experiencia sin descargas sigue diciendo SIN DOCUMENTOS: la constancia
    es un adjunto de la propuesta, no evidencia recuperada de una fuente."""
    cert = _pdf(tmp_path / "P1_E1.pdf", 2)
    salida = construir_zip_infoobras(ESPEJO, {}, tmp_path / "solo-cert.zip",
                                     certificados={(1, 1): cert})
    with zipfile.ZipFile(salida) as zf:
        assert any(n.endswith("CONSTANCIA_P1_E1.pdf") for n in zf.namelist())
        indice = zf.read("indice.txt").decode("utf-8")
    assert "SIN DOCUMENTOS" in indice
    assert "Constancia presentada en la propuesta (2 páginas)" in indice
