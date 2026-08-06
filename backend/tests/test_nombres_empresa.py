"""
T-REFACTOR-002 (opción mínima) — prelimpiado compartido de nombres de entidad.

El membrete de un certificado no es una razón social: trae la composición del
consorcio entre paréntesis y a veces la cola «RUC …». Esa basura de entrada
hundía el parecido hasta 46/100 y el candado SEACE la leía como señal FUERTE
«en contra» sobre dos nombres que son el MISMO consorcio.

Los pares de este archivo son REALES: salen de los espejos y enriquecimientos de
`datos_pivote/` (jobs 371fa5a1e704, 8a4b468ac700, 15ee32f32c26, ae368cb5dafa) —
son los 7 casos que el dossier de decisión identificó como «divergencia por
entrada sucia, no por desacuerdo de criterio». Ningún comparador cambió de
criterio: lo único que cambió es lo que se les pasa.
"""
from __future__ import annotations

import pytest

from scraping import mef
from scraping.nombres_empresa import limpiar_nombre_entidad, variantes
from scraping.sunat import score_match_empresa
from validacion.candado_seace import A_FAVOR, EN_CONTRA, UMBRAL_ENTIDAD_A_FAVOR


def mejor(a: str, b: str) -> int:
    """Lo que hace el candado: puntúa las dos formas y se queda con la mejor."""
    return max(score_match_empresa(x, y) for x in variantes(a) for y in variantes(b))

# Los 7 pares reales que el paréntesis rompía. (cert, fuente)
PARES_SUCIOS = [
    ("CONSORCIO HOSPITAL ABANCAY (COLESI Contratistas Generales S.A. & "
     "JOCA Ingenieria y Construccion S.A.)", "CONSORCIO HOSPITAL ABANCAY"),
    ("Consorcio Hospital Abancay (COLESI Contratistas Generales S.A. & "
     "JJCA Ingeniería y Construcción S.A.)", "CONSORCIO HOSPITAL ABANCAY"),
    ("CONSORCIO HOSPITAL ABANCAY (conformado por COLESI CONTRATISTAS GENERALES "
     "S.A. y IOCA INGENIERÍA Y CONSTRUCCIÓN S.A.)", "CONSORCIO HOSPITAL ABANCAY"),
    ("CONSORCIO HOSPITALARIO DE COMAS (COLESI Contratistas Generales S.A. & "
     "MANFER S.A.)", "CONSORCIO HOSPITALARIO DE COMAS"),
    ("CONSORCIO HOSPITALARIO FRONTERA NORTE (conformado por COLESI CONTRATISTAS "
     "GENERALES S.A. y MANFER S.R.L.)", "CONSORCIO HOSPITALARIO FRONTERA NORTE"),
    ("DIESA S.R.L. (Promotora, Constructora e Inmobiliaria Diaz Espinoza "
     "Asociados S.R.L.)", "DIESA SRL"),
    ("ING. VALDEMAR CESAR VERA VASQUEZ (Consultor de la Supervisión de la Obra)",
     "VERA VASQUEZ VALDEMAR CESAR"),
]


# ── el helper, a solas ───────────────────────────────────────────────────────

def test_quita_parentesis_y_cola_ruc():
    f = limpiar_nombre_entidad
    assert f("CONSORCIO HOSPITAL ABANCAY (COLESI & JOCA)") == "CONSORCIO HOSPITAL ABANCAY"
    assert f("INSTITUTO DE CONSULTORIA S.A. RUC 20263373058") == "INSTITUTO DE CONSULTORIA S.A."
    assert f("ACME  S.A.C.   (miembro)  ") == "ACME S.A.C."


def test_nombre_sin_parentesis_queda_igual():
    """Regresión: el prelimpiado NO puede tocar un nombre limpio."""
    for n in ("INSTITUTO DE CONSULTORIA S.A.",
              "SINOHYDRO CORPORATION LIMITED, SUCURSAL DEL PERÚ",
              "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
              "S & S CONSULTORES Y CONTRATISTAS GENERALES S.A.C."):
        assert limpiar_nombre_entidad(n) == n


def test_no_vacia_un_nombre_que_es_solo_parentesis():
    """Guardarraíl: vaciar no es limpiar. Un string vacío hace que los dos
    comparadores respondan 0/False, o sea convierte un dato pobre en una
    respuesta falsa."""
    assert limpiar_nombre_entidad("(sin datos)") == "(sin datos)"
    assert limpiar_nombre_entidad("(CONSORCIO SALUD PICOTA)") == "(CONSORCIO SALUD PICOTA)"
    assert limpiar_nombre_entidad("RUC 20123456789") == "RUC 20123456789"


def test_vacios():
    assert limpiar_nombre_entidad("") == ""
    assert limpiar_nombre_entidad(None) == ""
    assert limpiar_nombre_entidad("   ") == ""


# ── efecto en los comparadores (criterio intacto, entrada limpia) ────────────

@pytest.mark.parametrize("cert,fuente", PARES_SUCIOS)
def test_los_siete_pares_reales_dejan_de_divergir(cert, fuente):
    """Antes: el de MEF decía SÍ y el de SUNAT NO. Ahora los dos dicen SÍ."""
    assert score_match_empresa(cert, fuente) < UMBRAL_ENTIDAD_A_FAVOR   # antes
    assert mejor(cert, fuente) >= UMBRAL_ENTIDAD_A_FAVOR                # ahora
    assert mef._nombres_coinciden(cert, fuente)


def test_variantes_no_repite_cuando_no_hay_nada_que_limpiar():
    assert variantes("INSTITUTO DE CONSULTORIA S.A.") == ("INSTITUTO DE CONSULTORIA S.A.",)
    assert variantes("ACME (miembro)") == ("ACME (miembro)", "ACME")
    assert variantes("") == ("",)


def test_el_parentesis_que_SI_es_la_identidad_no_se_pierde():
    """Caso real inverso (job 15ee32f32c26 exp 2:1): afuera quedó la sigla y
    dentro del paréntesis está la razón social entera. Prelimpiar a secas
    hundía el parecido de 93 a 15 — un `ok` que se volvía `no_verificable`.
    Por eso se puntúan AMBAS formas y gana la mejor: el cambio es monótono."""
    cert = ("DIESA S.R.L. (Promotora, Constructora e Inmobiliaria "
            "Diaz Espinoza Asociados S.R.L.)")
    razon = "PROMOTORA, CONSTRUCTORA INMOBILIARIA DIAZ ESPINOZA ASOCIADOS S.R.L."
    assert score_match_empresa(limpiar_nombre_entidad(cert), razon) < 20
    assert mejor(cert, razon) >= UMBRAL_ENTIDAD_A_FAVOR
    assert mef._nombres_coinciden(cert, razon)
    # y la otra punta del mismo emisor (el nombre comercial) también entra
    assert mejor(cert, "DIESA SRL") >= UMBRAL_ENTIDAD_A_FAVOR


def test_caso_abancay_el_candado_deja_de_contradecir():
    """El caso estrella del dossier: la MISMA empresa (mismo RUC) producía una
    señal FUERTE «en contra» — 46/100 — en el candado SEACE, mientras el bloque
    MEF del mismo Excel la daba por `ok`."""
    from validacion.candado_seace import _senal_entidad

    cert = {"entidad_contratante": PARES_SUCIOS[0][0]}
    proceso = {"entidad_convocante": PARES_SUCIOS[0][1]}
    assert score_match_empresa(cert["entidad_contratante"],
                               proceso["entidad_convocante"]) == 46   # antes
    s = _senal_entidad(proceso, cert)
    assert s.sentido == A_FAVOR
    assert "100/100" in s.detalle
    # la frase sigue citando lo que el documento dice, con paréntesis y todo:
    # se limpia lo que se puntúa, no lo que se le muestra al evaluador.
    assert "COLESI" in s.detalle


def test_entidades_distintas_siguen_siendo_distintas():
    """Regresión: el prelimpiado no debe volver compatible lo incompatible."""
    from validacion.candado_seace import _senal_entidad

    s = _senal_entidad({"entidad_convocante": "MUNICIPALIDAD DISTRITAL DE USQUIL"},
                       {"entidad_contratante": "CONSORCIO SALUD PICOTA (ACME S.A.C.)"})
    assert s.sentido == EN_CONTRA
    assert not mef._nombres_coinciden("CONSORCIO PUERTO INCA (ACME S.A.C.)",
                                      "CONSORCIO D&D")


def test_el_cambio_es_monotono_sobre_los_pares_del_corpus():
    """La propiedad que sostiene todo lo demás: puntuar la mejor de las dos
    formas solo puede SUBIR el parecido. Ningún `ok` puede volverse
    `no_verificable` por este cambio."""
    for a, b in PARES_SUCIOS + [("INSTITUTO DE CONSULTORIA S.A.", "INDECONSULT S.A."),
                                ("CONSORCIO SUPERVISOR URPA", "CONSORCIO SUPERVISOR YANAHUANCA"),
                                ("GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL", "GOB. REG. JUNÍN")]:
        assert mejor(a, b) >= score_match_empresa(a, b)


def test_verificar_expediente_acepta_el_membrete_con_miembros():
    """El bloque MEF del Excel: emisor con paréntesis vs contratista del DWH."""
    contratos = [{"numero": "C-1", "contratista": "CONSORCIO HOSPITALARIO DE COMAS",
                  "monto": 1.0, "objeto": "ELABORACION DE EXPEDIENTE TECNICO",
                  "nomenclatura": "", "fecha_suscripcion": None,
                  "valor_referencial": None, "url_pdf": None}]
    exp = {"nombre_emisor": PARES_SUCIOS[3][0]}
    bloque = mef.verificar_expediente(exp, {}, contratos)
    assert bloque["contratista"]["veredicto"] == "ok"
