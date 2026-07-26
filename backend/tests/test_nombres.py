"""
Tests de la nomenclatura de los entregables (issue #29): pestañas del Excel y
nombres de los archivos que descarga el evaluador.

Goldens deliberados: si alguien cambia la regla, estos tests le dicen EXACTAMENTE
qué verá el Comité en la pestaña y en la carpeta de Descargas.
"""
from __future__ import annotations

import pytest

from schemas.cargo import abreviar_cargo, etiqueta_hoja
from schemas.nombres import nombre_descarga, slug_concurso, slug_postor


class _Job:
    def __init__(self, analisis_id="", postor="", slug=None):
        self.analisis_id, self.postor, self.slug = analisis_id, postor, slug


# ── Pestañas ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cargo,esperado", [
    # "Jefe" se conserva: marca jerarquía y distingue al P1 de los demás.
    ("Jefe de Supervisión", "Jefe Superv"),
    ("JEFE DE SUPERVISIÓN", "Jefe Superv"),
    # "Especialista" NO: todos lo son, no distingue.
    ("ESPECIALISTA EN ESTRUCTURAS", "Estruc"),
    ("Especialista en Arquitectura", "Arquit"),
    ("ESP. ESTRUCTURAS", "Estruc"),
    ("Ingeniero Residente", "Resid"),
    # El caso que disparó el issue: no tenía "en", así que el regex viejo no
    # quitaba el prefijo y Excel truncaba a "P4 ESPECIALISTA PLANEAMIENTO Y".
    ("ESPECIALISTA PLANEAMIENTO Y COSTOS", "Planea Costo"),
    ("Especialista en Instalaciones Sanitarias", "Instala Sanit"),
    ("Especialista en Instalaciones Eléctricas", "Instala Eléct"),
])
def test_abreviar_cargo(cargo, esperado):
    assert abreviar_cargo(cargo) == esperado


def test_etiqueta_hoja_formato_pedido_por_el_cliente():
    assert etiqueta_hoja(1, "Jefe de Supervisión") == "P1. Jefe Superv"
    assert etiqueta_hoja(4, "ESPECIALISTA PLANEAMIENTO Y COSTOS") == "P4. Planea Costo"


def test_etiqueta_hoja_no_depende_del_casing_del_pdf_del_postor():
    """La divergencia vieja: el mismo cargo daba pestañas distintas según cómo lo
    hubiera escrito el postor en su propuesta."""
    assert (etiqueta_hoja(4, "INSTALACIONES SANITARIAS")
            == etiqueta_hoja(4, "Instalaciones Sanitarias")
            == "P4. Instala Sanit")


def test_etiqueta_hoja_respeta_el_limite_de_excel():
    largo = "Especialista en Supervisión de Obras de Saneamiento Rural y Urbano"
    assert len(etiqueta_hoja(12, largo)) <= 31


def test_etiqueta_hoja_sin_cargo_sigue_siendo_unica():
    assert etiqueta_hoja(3, "") == "P3"
    assert etiqueta_hoja(3, "") != etiqueta_hoja(4, "")


def test_etiqueta_hoja_cargo_que_es_solo_el_prefijo_no_queda_vacio():
    assert etiqueta_hoja(1, "Especialista") == "P1. Especi"


# ── Slug del concurso ────────────────────────────────────────────────────────

@pytest.mark.parametrize("analisis_id,esperado", [
    ("cp001-2025-mdh-huachocolpa", "huachocolpa"),   # el ejemplo del cliente
    ("divino-nino-2026-07-14", "divino-nino"),
    ("divino-nino-20260707", "divino-nino"),
    ("divino_nino_002-2026-GRC", "divino-nino"),
    ("essalud-vitarte-cp02-2025", "essalud-vitarte"),
    ("pichanaqui-cp36-2025-grj", "pichanaqui"),
    ("cp01-2025-pucara", "pucara"),
    ("soritor-cp01-2026-pronis", "soritor-pronis"),
    ("trujillo-cp02-2025--2026-05-30T12:00:00", "trujillo"),
])
def test_slug_desde_analisis_id(analisis_id, esperado):
    assert slug_concurso(analisis_id=analisis_id) == esperado


def test_slug_sin_nada_util_cae_al_id_saneado():
    """`001-2025-MDH-CS1__IDC`: puros códigos y siglas. No inventamos: se devuelve
    lo que hay, que es lo mismo que se veía antes del cambio."""
    assert slug_concurso(analisis_id="001-2025-MDH-CS1__IDC") == "001-2025-mdh-cs1-idc"


def test_slug_de_la_skill_gana_sobre_la_heuristica():
    espejo = {"_meta": {"analisis_id": "cp001-2025-mdh-huachocolpa",
                        "slug": "Huachocolpa"}}
    assert slug_concurso(espejo, "cp001-2025-mdh-huachocolpa") == "huachocolpa"


# ── Postor y nombre final ────────────────────────────────────────────────────

@pytest.mark.parametrize("postor,esperado", [
    ("CONSORCIO VIAL HUANCAVELICA", "cons-vial"),
    ("Consorcio Supervisor Divino Niño", "cons-supervisor"),
    ("JOSE CARLOS INGENIEROS S.A.C.", "jose-carlos"),
    ("", ""),
])
def test_slug_postor(postor, esperado):
    assert slug_postor(postor) == esperado


def test_nombre_descarga_excel_y_zip_comparten_nombre_base():
    job = _Job("cp001-2025-mdh-huachocolpa", "CONSORCIO VIAL HUANCAVELICA")
    assert nombre_descarga(job, None, "xlsx") == "Analisis_huachocolpa_cons-vial.xlsx"
    assert nombre_descarga(job, None, "zip") == "Analisis_huachocolpa_cons-vial.zip"


def test_nombre_descarga_distingue_postores_del_mismo_concurso():
    """El flujo del Comité es comparar postores del MISMO concurso: sin el postor
    en el nombre, el segundo Excel cae como '… (1).xlsx'."""
    a = nombre_descarga(_Job("cp001-2025-mdh-huachocolpa", "CONSORCIO VIAL"), None)
    b = nombre_descarga(_Job("cp001-2025-mdh-huachocolpa", "CONSTRUCTORA ANDINA"), None)
    assert a != b


def test_nombre_descarga_sin_postor_no_deja_guion_colgando():
    assert nombre_descarga(_Job("cp01-2025-pucara", "")) == "Analisis_pucara.xlsx"


def test_nombre_descarga_no_necesita_el_espejo():
    """La descarga del ZIP nombra el archivo SIN abrir el espejo: leer MB de disco
    para armar un string sería absurdo, y un espejo corrupto tumbaría una descarga
    que por lo demás está completa. El slug viaja en el Job desde la ingesta."""
    job = _Job("001-2025-MDH-CS1__IDC", "CONSORCIO VIAL", slug="huachocolpa")
    assert nombre_descarga(job, None, "zip") == "Analisis_huachocolpa_cons-vial.zip"


def test_slug_del_job_gana_sobre_la_heuristica_del_id():
    assert slug_concurso(analisis_id="cp001-2025-mdh-x", slug="Huachocolpa") == "huachocolpa"


def test_job_viejo_sin_slug_cae_a_la_heuristica():
    """Los jobs anteriores a este cambio no tienen slug ni en el Job ni en el
    espejo → siguen nombrándose por el analisis_id, como hasta ahora."""
    assert nombre_descarga(_Job("cp001-2025-mdh-huachocolpa", "")) == "Analisis_huachocolpa.xlsx"
