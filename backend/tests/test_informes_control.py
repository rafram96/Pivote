"""Filtro de informes de control por periodo de la experiencia (lógica pura, sin red).

Regla del cliente: descarga los informes cuyo AÑO cae dentro del periodo de la
experiencia. Exp 2016–2018 + informes 2018–2022 → solo el de 2018."""
from datetime import date

from entregables.zip_infoobras import _anio_informe, _items_descarga, informes_relevantes

INFORMES = [
    {"Anio": "2018", "FechaEmision": "11/04/2018", "NroInforme": "351-2018"},
    {"Anio": "2019", "FechaEmision": "20/03/2019", "NroInforme": "10-2019"},
    {"Anio": "2020", "FechaEmision": "05/06/2020", "NroInforme": "33-2020"},
    {"Anio": "2021", "FechaEmision": "01/02/2021", "NroInforme": "47-2021"},
    {"Anio": "2022", "FechaEmision": "09/09/2022", "NroInforme": "62-2022"},
]


def _anios(infs):
    return sorted(i["Anio"] for i in infs)


def test_exp_2016_2018_solo_trae_2018():
    rel = informes_relevantes(INFORMES, date(2016, 1, 1), date(2018, 12, 31))
    assert _anios(rel) == ["2018"]   # el caso textual del cliente


def test_exp_2018_2022_trae_todo_el_rango():
    rel = informes_relevantes(INFORMES, date(2018, 6, 1), date(2022, 1, 1))
    assert _anios(rel) == ["2018", "2019", "2020", "2021", "2022"]


def test_exp_posterior_no_trae_nada():
    rel = informes_relevantes(INFORMES, date(2023, 1, 1), date(2024, 12, 31))
    assert rel == []


def test_sin_periodo_trae_todos():
    assert len(informes_relevantes(INFORMES, None, None)) == len(INFORMES)


def test_anio_cae_de_fecha_si_falta_Anio():
    inf = {"FechaEmision": "15/07/2017"}
    assert _anio_informe(inf) == 2017
    assert informes_relevantes([inf], date(2016, 1, 1), date(2018, 1, 1)) == [inf]


def test_informe_sin_anio_legible_se_incluye_por_las_dudas():
    inf = {"NroInforme": "x"}  # ni Anio ni FechaEmision
    assert informes_relevantes([inf], date(2016, 1, 1), date(2018, 1, 1)) == [inf]


# ── Datos de cierre (mejora D): parser de los botones de descarga ────────────

def test_items_descarga_botones_y_href():
    html = (
        '<a data-download-url="/Mapa/DownloadFile?filename=cierre/acta.pdf'
        '&name=Acta de Recepción&extension=.pdf">Descargar</a>'
        '<a href="https://x/Mapa/DownloadFile?filename=cierre/liquidacion.pdf'
        '&amp;name=Liquidación">Descargar</a>'
        '<a data-download-url="/Mapa/DownloadFile?filename=cierre/acta.pdf&name=dup">x</a>'
    )
    items = _items_descarga(html)
    assert [i["filename"] for i in items] == ["cierre/acta.pdf", "cierre/liquidacion.pdf"]  # dedup
    assert items[1]["nombre"] == "Liquidación"
    assert all(i["extension"] == "pdf" for i in items)  # ext del filename si falta el param


def test_items_descarga_sin_botones():
    assert _items_descarga("<html>sin descargas</html>") == []
