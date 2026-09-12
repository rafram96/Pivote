"""
T-011 — cruces de fechas contrato/expediente ↔ certificado + hoja «Cronología».

Todo offline y determinístico: el motor de cruces es puro y los fixtures son
sintéticos, calcados de la corrida Vitarte (job `7e9306a321ac`, prof 8 exp 2 —
E.S. Pedro Sánchez Meza, CUI 2337618, proceso AS-SM-28-2021-GRJ-CS-1).

Lo que estos tests fijan, y por qué importa:
  · la aritmética es DÍA-EXACTA (el caso borde «mismo mes, días incompatibles»);
  · el gate anti-circularidad manda: sin identidad confirmada por señales
    ajenas a la fecha, la regla se ABSTIENE — ni dispara ni valida;
  · la ausencia de fuente jamás produce alerta;
  · la hoja nueva es ADITIVA: las hojas del formato congelado salen idénticas.
"""
from __future__ import annotations

import openpyxl

from entregables.excel_final import (
    HOJA_CRONOLOGIA, construir_hoja_cronologia, desempaquetar_enriquecimiento,
    generar_excel_final, inyectar_cruces_fechas, regenerar_excel_final,
)
from reglas.cruces_fechas import (
    COINCIDE, DISPARA, POR_CONFIRMAR, REGLA_INICIO, REGLA_TERMINO,
    TOLERANCIA_DIAS_APROBACION, TOLERANCIA_DIAS_INICIO, cruces_de_experiencia,
    evaluar_inicio_vs_contrato, evaluar_termino_vs_aprobacion,
    fecha_aprobacion_expediente, fecha_en_texto,
)
from validacion.candado_seace import evaluar_candado

# ── Fixtures ─────────────────────────────────────────────────────────────────


def proceso(**over) -> dict:
    """Resumen del proceso real AS-SM-28-2021-GRJ-CS-1 (GORE Junín)."""
    return {
        "entidad_convocante": "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
        "rucs_adjudicatarios": ["20263373058"],
        "fecha_firma": "2021-09-24",
        "fecha_convocatoria": "2021-07-14",
        "vigencia_inicio": "2021-09-25",
        "vigencia_fin": "2024-03-12",
        "monto": 3798760.90,
        "nomenclatura": "AS-SM-28-2021-GRJ-CS-1",
        "tipo": "supervision",
        **over,
    }


def cert(**over) -> dict:
    """Certificado real: constancia de INDECONSULT por la supervisión."""
    base = {
        "entidad_contratante": "GOBIERNO REGIONAL DE JUNÍN",
        "entidad_emisora": "INSTITUTO DE CONSULTORIA S.A.",
        "ruc_emisor": "20263373058",
        "tipo_experiencia": "supervision",
        "fecha_inicial": "2021-10-01",
        "fecha_final": "2023-10-11",
        "monto_contrato_soles": None,
    }
    base.update(over)
    # Los casos positivos de este fixture representan literalmente el servicio
    # indicado por tipo_experiencia; los negativos pueden retirar esta clave.
    tipo = base.get("tipo_experiencia")
    if "servicio_declarado" not in base and tipo in {"supervision", "expediente"}:
        base["servicio_declarado"] = {
            "tipo": "supervision_obra" if tipo == "supervision" else "elaboracion_expediente",
            "texto": "Supervisión de obra" if tipo == "supervision" else "Elaboración del expediente técnico",
            "pagina_pdf": 1, "fuente": "certificado",
        }
    return base


def bloque_seace(proc: dict, c: dict, **over) -> dict:
    """El bloque `seace` tal como lo persiste la etapa, con el candado F5 ya
    evaluado sobre ESTE proceso y ESTE certificado (nada se inventa a mano)."""
    return {
        "estado": "seleccionado",
        "cui": "2337618",
        "proceso_objeto": proc.get("tipo"),
        "fecha_suscripcion": proc.get("fecha_firma"),
        "vigencia": [proc.get("vigencia_inicio"), proc.get("vigencia_fin")],
        "proceso": proc,
        "candado": evaluar_candado(proc, c).como_dict(),
        **over,
    }


# ── 1 · Regla A dispara (caso real sintético, día-exacto) ────────────────────

def test_regla_a_dispara_inicio_anterior_al_contrato():
    """El profesional declara empezar 3 meses antes de que se firme el contrato,
    y todo lo demás (entidad, emisor adjudicatario, objeto) confirma que es EL
    proceso: la incoherencia es de la declaración, no de la identificación."""
    c = cert(fecha_inicial="2021-06-01")
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proceso(), c), c)
    assert cruce.resultado == DISPARA
    assert cruce.dias == 115
    assert cruce.fecha_declarada == "2021-06-01"
    assert cruce.fecha_fuente == "2021-09-24"
    assert "01/06/2021" in cruce.motivo and "24/09/2021" in cruce.motivo


def test_regla_a_borde_mismo_mes_dias_incompatibles():
    """CASO BORDE exigido: inicio 05/01 vs firma 30/01. Comparando MESES los dos
    caen en enero y «coinciden»; comparando DÍAS son 25 días sin respaldo."""
    c = cert(fecha_inicial="2021-01-05", fecha_final="2021-12-31")
    proc = proceso(fecha_firma="2021-01-30", vigencia_inicio="2021-01-30",
                   vigencia_fin="2022-06-30")
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proc, c), c)
    assert cruce.resultado == DISPARA
    assert cruce.dias == 25


def test_regla_a_bordes_exactos_de_la_tolerancia():
    """La tolerancia se aplica en días completos: 15 pasa, 16 no."""
    proc = proceso(fecha_firma="2021-01-16", vigencia_inicio="2021-01-16",
                   vigencia_fin="2022-06-30")
    justo = cert(fecha_inicial="2021-01-01", fecha_final="2021-12-31")
    assert evaluar_inicio_vs_contrato(bloque_seace(proc, justo), justo).dias \
        == TOLERANCIA_DIAS_INICIO
    assert evaluar_inicio_vs_contrato(bloque_seace(proc, justo), justo).resultado == COINCIDE

    uno_mas = cert(fecha_inicial="2020-12-31", fecha_final="2021-12-31")
    fuera = evaluar_inicio_vs_contrato(bloque_seace(proc, uno_mas), uno_mas)
    assert fuera.dias == TOLERANCIA_DIAS_INICIO + 1
    assert fuera.resultado == DISPARA


def test_regla_a_coincide_cuando_las_fechas_calzan():
    c = cert()
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proceso(), c), c)
    assert cruce.resultado == COINCIDE
    assert cruce.dias == -7          # el contrato existía 7 días antes


# ── 2 · Regla A se abstiene sin identidad confirmada ─────────────────────────

def test_regla_a_se_abstiene_sin_candado_job_anterior_a_f5():
    """Un job corrido antes del candado no trae señales: no hay con qué sostener
    que el proceso sea el del certificado → abstención, jamás alerta."""
    c = cert(fecha_inicial="2021-06-01")
    seace = bloque_seace(proceso(), c)
    seace.pop("candado")
    cruce = evaluar_inicio_vs_contrato(seace, c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "no había verificado a qué proceso" in cruce.motivo


def test_regla_a_se_abstiene_con_identidad_insuficiente():
    """Sin RUC de emisor y sin entidad contratante solo queda `objeto` a favor:
    una sola señal no sostiene la identidad → abstención (ni dispara ni valida),
    aunque las fechas fueran flagrantes."""
    c = cert(fecha_inicial="2021-06-01", ruc_emisor=None,
             entidad_contratante=None)
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proceso(), c), c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "señales independientes de la fecha" in cruce.motivo


def test_regla_a_no_rescata_historico_entidad_objeto_con_fechas_y_monto():
    """Fechas/monto no convierten la pareja entidad+objeto en identidad.

    Este fixture representa un job histórico sin RUC del emisor: conserva las
    coincidencias visibles, pero el gate no habilita una alerta circular.
    """
    c = cert(ruc_emisor=None,
             entidad_contratante="GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL",
             fecha_inicial="2020-01-01",
             monto_contrato_soles=3798760.90)
    proc = proceso(rucs_adjudicatarios=[], fecha_firma="2021-09-24")
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proc, c), c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "entidad y objeto" in cruce.motivo


def test_regla_a_se_abstiene_si_la_contradiccion_no_es_de_fechas():
    """Entidad distinta = probablemente OTRO proceso. Cruzar sus fechas
    generaría una alerta contra el concurso equivocado."""
    c = cert(fecha_inicial="2021-06-01",
             entidad_contratante="MUNICIPALIDAD DISTRITAL DE SAN JUAN")
    proc = proceso(rucs_adjudicatarios=[])
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proc, c), c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "ajenas a las fechas" in cruce.motivo


def test_regla_a_se_abstiene_sin_proceso_publicado():
    """Pre-2018: el CUI no figura en datos abiertos. Sin fuente no hay alerta."""
    c = cert(fecha_inicial="2015-01-01", fecha_final="2016-01-01")
    cruce = evaluar_inicio_vs_contrato(
        {"estado": "sin_procesos", "cui": "2337618"}, c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "2018" not in cruce.motivo
    assert "no demuestra que no exista" in cruce.motivo
    assert cruce.fecha_fuente is None


def test_regla_a_se_abstiene_si_el_proceso_no_publica_la_firma():
    c = cert(fecha_inicial="2021-06-01")
    proc = proceso(fecha_firma=None, fecha_convocatoria=None)
    seace = bloque_seace(proc, c)
    seace["fecha_suscripcion"] = None
    cruce = evaluar_inicio_vs_contrato(seace, c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "no dispone de la fecha" in cruce.motivo


# ── 3 · Regla B (expedientes) ────────────────────────────────────────────────

def enr_expediente(**over) -> dict:
    """Enriquecimiento de una experiencia de expediente ya verificada en el MEF
    (contratista coincide con el emisor) y con su documento de aprobación."""
    base = {
        "cui": "2303684",
        "verificacion_expediente": {
            "verificado_en_mef": True,
            "contratista": {"valor": "INSTITUTO DE CONSULTORIA S.A.",
                            "veredicto": "ok"},
            "contrato": {"numero": "116-2017-GRH/GR", "veredicto": "ok"},
            "resolucion": {"numero": "262-2023-GRH/GRI", "veredicto": "ok"},
        },
        "aprobacion_expediente": {"fecha": "2023-08-14",
                                  "nombre": "R.G.R. N° 262-2023-GRH/GRI"},
    }
    base.update(over)
    return base


def test_regla_b_dispara_termino_posterior_a_la_aprobacion():
    c = cert(tipo_experiencia="expediente", fecha_final="2024-03-31")
    cruce = evaluar_termino_vs_aprobacion(enr_expediente(), c)
    assert cruce.resultado == DISPARA
    assert cruce.dias == 230
    assert "14/08/2023" in cruce.motivo
    assert cruce.inferida is True     # la fecha sale del documento, no escrita


def test_regla_b_bordes_exactos_de_la_tolerancia():
    enr = enr_expediente()
    justo = cert(tipo_experiencia="expediente", fecha_final="2023-09-13")
    r = evaluar_termino_vs_aprobacion(enr, justo)
    assert r.dias == TOLERANCIA_DIAS_APROBACION and r.resultado == COINCIDE
    uno_mas = cert(tipo_experiencia="expediente", fecha_final="2023-09-14")
    r2 = evaluar_termino_vs_aprobacion(enr, uno_mas)
    assert r2.dias == TOLERANCIA_DIAS_APROBACION + 1 and r2.resultado == DISPARA


def test_regla_b_coincide_cuando_termina_antes_de_aprobarse():
    c = cert(tipo_experiencia="expediente", fecha_final="2023-06-30")
    assert evaluar_termino_vs_aprobacion(enr_expediente(), c).resultado == COINCIDE


def test_regla_b_se_abstiene_sin_verificacion_mef():
    """El MEF no confirmó el expediente: no hay identidad que sostenga el cruce."""
    enr = enr_expediente()
    enr["verificacion_expediente"]["verificado_en_mef"] = False
    cruce = evaluar_termino_vs_aprobacion(enr, cert(fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert "no dispone de contratos" in cruce.motivo


def test_regla_b_se_abstiene_si_el_contratista_no_coincide():
    """Aprobación de OTRO proyectista → comparar sería comparar otro encargo."""
    enr = enr_expediente()
    enr["verificacion_expediente"]["contratista"]["veredicto"] = "no_verificable"
    cruce = evaluar_termino_vs_aprobacion(enr, cert(fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert "otro encargo" in cruce.motivo


def test_regla_b_se_abstiene_si_la_resolucion_no_trae_fecha():
    """«N° 262-2023-GRH/GRI» no es una fecha: deducir el día está prohibido."""
    enr = enr_expediente()
    enr.pop("aprobacion_expediente")
    cruce = evaluar_termino_vs_aprobacion(enr, cert(fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert "sin fecha" in cruce.motivo


def test_regla_b_lee_la_fecha_del_rotulo_de_la_resolucion():
    enr = enr_expediente()
    enr.pop("aprobacion_expediente")
    enr["verificacion_expediente"]["resolucion"]["documento"] = (
        "R.G.R. N° 262-2023-GRH/GRI DE FECHA 14/08/2023")
    f, fuente, inferida = fecha_aprobacion_expediente(enr)
    assert f.isoformat() == "2023-08-14" and inferida is False
    assert "08-A" in fuente


def test_fecha_en_texto_no_acepta_medias_fechas():
    """Ni «2023» ni «08/2023»: sin día no hay fecha con la que concluir."""
    assert fecha_en_texto("R.G.R. N° 262-2023-GRH/GRI") is None
    assert fecha_en_texto("aprobado en 08/2023") is None
    assert fecha_en_texto("del 14/08/2023").isoformat() == "2023-08-14"


def test_regla_b_no_aplica_a_una_supervision():
    """Una experiencia que no es de expediente no recibe la pregunta."""
    assert evaluar_termino_vs_aprobacion(
        {"seace": bloque_seace(proceso(), cert())}, cert()) is None


def test_cruces_de_experiencia_devuelve_ambas_reglas_en_un_expediente():
    enr = enr_expediente()
    enr["seace"] = bloque_seace(proceso(tipo="expediente"),
                                cert(tipo_experiencia="expediente"))
    reglas = [c.regla for c in cruces_de_experiencia(
        enr, cert(tipo_experiencia="expediente"))]
    assert reglas == [REGLA_INICIO, REGLA_TERMINO]


# ── 3 bis · Los seis textos que la revisión de las 12 hojas encontró mal ─────
#
# Todo lo de aquí abajo son DATOS FICTICIOS (empresa «CONSORCIO EJEMPLO», CUI
# 9999999): lo que se fija es la redacción, no ningún expediente real.


def _ve_contrato(**over) -> dict:
    """`verificacion_expediente` con SOLO el contrato del MEF: el caso en que
    SEACE no identificó el proceso pero el 08-A sí publica el contrato."""
    contrato = {"numero": "CONTRATO N° 001-2022-EJEMPLO", "fecha": "2022-08-18",
                "objeto": "ELABORACIÓN DEL EXPEDIENTE TÉCNICO", "veredicto": "ok"}
    contrato.update(over)
    return {"cui": "9999999",
            "verificacion_expediente": {"verificado_en_mef": True,
                                        "contratista": {"valor": "CONSORCIO EJEMPLO",
                                                        "veredicto": "ok"},
                                        "contrato": contrato}}


# 1 · Regla A cae al contrato del MEF cuando no hay proceso SEACE.

def test_regla_a_usa_el_contrato_del_mef_cuando_no_hay_proceso_seace():
    """Sin proceso en SEACE, el contrato del 08-A firmado por el EMISOR es una
    firma tan oficial como la del proceso: la regla ya no se calla."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-09-05",
             fecha_final="2022-11-11")
    cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c, _ve_contrato())
    assert cruce.resultado == COINCIDE
    assert cruce.fecha_fuente == "2022-08-18"
    assert cruce.fuente == "contrato del expediente (MEF)"
    assert "publicado por el MEF" in cruce.motivo


def test_regla_a_dispara_con_el_contrato_del_mef():
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-01-10",
             fecha_final="2022-11-11")
    cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c, _ve_contrato())
    assert cruce.resultado == DISPARA
    assert cruce.dias == 220
    assert cruce.fuente == "contrato del expediente (MEF)"


def test_regla_a_acepta_el_rotulo_nuevo_del_contrato_del_emisor():
    """`veredicto=coincide` y `elegido_por=emisor` son la nomenclatura nueva; el
    módulo no puede depender del orden en que aterricen los cambios."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-09-05")
    for over in ({"veredicto": "coincide"},
                 {"veredicto": "no_verificable", "elegido_por": "emisor"}):
        cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c,
                                           _ve_contrato(**over))
        assert cruce.resultado == COINCIDE, over
        assert cruce.fecha_fuente == "2022-08-18"


def test_regla_a_prefiere_el_contrato_que_resolvio_la_via():
    """`contrato_emisor` es el contrato que ATÓ emisor y expediente: manda sobre
    el que la ficha del MEF eligió por su cuenta, que puede ser otro."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-09-05")
    enr = _ve_contrato(veredicto="no_verificable")
    enr["contrato_emisor"] = {"numero": "CONTRATO N° 007-2022-EJEMPLO",
                              "contratista": "CONSORCIO EJEMPLO",
                              "fecha": "2022-07-01"}
    cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c, enr)
    assert cruce.resultado == COINCIDE
    assert cruce.fecha_fuente == "2022-07-01"
    assert cruce.fuente == "contrato del expediente (MEF)"


def test_regla_a_no_cruza_contra_un_contrato_elegido_por_heuristica():
    """`elegido_por` «unico»/«mas_barato» son formas de escoger, no evidencia de
    que ese contrato sea del emisor: contra eso no se cruza nada."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-01-10",
             fecha_final="2022-11-11")
    for como in ("unico", "mas_barato"):
        enr = _ve_contrato(veredicto="no_verificable", elegido_por=como)
        cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c, enr)
        assert cruce.resultado == POR_CONFIRMAR, como
        assert "es de otro contratista" in cruce.motivo


def test_regla_a_se_abstiene_si_el_contrato_del_mef_es_de_otro_contratista():
    """Comparar contra el contrato de otra empresa es el fallo que el gate
    anti-circularidad existe para evitar: se dice y no se compara."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-01-10",
             fecha_final="2022-11-11")
    enr = _ve_contrato(veredicto="no_verificable")
    cruce = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c, enr)
    assert cruce.resultado == POR_CONFIRMAR
    assert cruce.fecha_fuente is None
    assert ("el único contrato publicado por el MEF es de otro contratista; "
            "no se compara") in cruce.motivo


def test_regla_a_sin_enriquecimiento_se_comporta_como_antes():
    """La firma tercera es OPCIONAL: los dos argumentos de siempre siguen
    valiendo (scripts y jobs viejos llaman así)."""
    c = cert(fecha_inicial="2015-01-01", fecha_final="2016-01-01")
    assert evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, c).resultado \
        == POR_CONFIRMAR


# 2 · Una fecha no demuestra por qué la búsqueda no obtuvo procesos.

def test_motivo_sin_proceso_no_inventa_causa_por_antiguedad():
    viejo = cert(fecha_inicial="2015-01-01", fecha_final="2016-01-01")
    m = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, viejo).motivo
    assert "cobertura" not in m
    assert "no demuestra que no exista ni establece la causa" in m

    nuevo = cert(tipo_experiencia="expediente", fecha_inicial="2022-01-10",
                 fecha_final="2022-11-11")
    m2 = evaluar_inicio_vs_contrato({"estado": "sin_procesos"}, nuevo).motivo
    assert "2018" not in m2
    assert ("no se halló el proceso de contratación de este expediente en los "
            "datos abiertos de SEACE") in m2


def test_motivo_sin_proceso_en_el_borde_exacto_de_2018():
    """A ambos lados del año se informa el resultado, no una causa inferida."""
    assert "cobertura" not in evaluar_inicio_vs_contrato(
        {"estado": "sin_procesos"},
        cert(fecha_inicial="2016-01-01", fecha_final="2017-12-31")).motivo
    assert "cobertura" not in evaluar_inicio_vs_contrato(
        {"estado": "sin_procesos"},
        cert(fecha_inicial="2017-06-01", fecha_final="2018-01-02")).motivo


# 3 · Los tres textos distintos sobre la resolución en la Regla B.

def test_regla_b_dice_que_el_mef_no_publica_la_resolucion():
    """`resolucion` sin número ni fecha: decir «figura solo con su número» era
    falso — y el Excel lo mostraba junto a una celda de resolución en «—»."""
    enr = enr_expediente()
    enr.pop("aprobacion_expediente")
    enr["verificacion_expediente"]["resolucion"] = {
        "veredicto": "no_verificable",
        "detalle": "sin documento de aprobación en el 08-A del MEF"}
    cruce = evaluar_termino_vs_aprobacion(enr, cert(tipo_experiencia="expediente",
                                                    fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert cruce.motivo == ("Este análisis no dispone de una resolución de "
                            "aprobación utilizable; no se puede comparar el término.")
    assert "figura solo con su número" not in cruce.motivo


def test_regla_b_mantiene_el_texto_de_la_resolucion_sin_fecha():
    """Con número y sin fecha, el texto de siempre sigue siendo el correcto."""
    enr = enr_expediente()
    enr.pop("aprobacion_expediente")
    cruce = evaluar_termino_vs_aprobacion(enr, cert(tipo_experiencia="expediente",
                                                    fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert "figura solo con su número, sin fecha" in cruce.motivo


def test_regla_b_explica_la_fecha_descartada_por_implausible():
    """`fecha_descartada`/`fecha_motivo` (lectura de la resolución): la fecha se
    leyó y se tiró; el evaluador tiene que ver cuál y por qué."""
    enr = enr_expediente()
    enr.pop("aprobacion_expediente")
    enr["resolucion_aprobacion"] = {
        "legible": True, "fecha": None, "coincide_emisor": "confirma",
        "fecha_descartada": "2019-05-03",
        "fecha_motivo": "es anterior al contrato que aprueba (18/08/2022)"}
    cruce = evaluar_termino_vs_aprobacion(enr, cert(tipo_experiencia="expediente",
                                                    fecha_final="2024-03-31"))
    assert cruce.resultado == POR_CONFIRMAR
    assert cruce.motivo == (
        "La fecha leída en la resolución (03/05/2019) no es plausible: es "
        "anterior al contrato que aprueba (18/08/2022); se omite el cruce.")


# 4 · `coincide_emisor == "no_nombra"`: sigue POR VERIFICAR, pero con la cifra.

def _enr_no_nombra(coincide: str = "no_nombra") -> dict:
    """Expediente cuyo contratista MEF NO es el emisor (el gate falla) y cuya
    resolución sí trae fecha, leída y sin nombrar a nadie."""
    return {"cui": "9999999",
            "verificacion_expediente": {
                "verificado_en_mef": True,
                "contratista": {"valor": "OTRA EMPRESA S.A.",
                                "veredicto": "no_verificable"},
                "resolucion": {"numero": "168-2022-EJEMPLO", "fecha": "2022-08-23",
                               "veredicto": "ok"}},
            "resolucion_aprobacion": {
                "legible": True, "fecha": "2022-08-23",
                "coincide_emisor": coincide,
                "detalle_emisor": ("CONSORCIO TERCERO"
                                   if coincide == "nombra_otro" else None)}}


def test_regla_b_no_nombra_mantiene_la_abstencion_pero_da_la_referencia():
    c = cert(tipo_experiencia="expediente", fecha_final="2022-11-11")
    cruce = evaluar_termino_vs_aprobacion(_enr_no_nombra(), c)
    assert cruce.resultado == POR_CONFIRMAR
    assert cruce.respuesta == "POR VERIFICAR"
    assert "comparar con otro encargo" in cruce.motivo
    assert ("Referencia: el término declarado (11/11/2022) es 80 días posterior "
            "a la aprobación publicada (23/08/2022).") in cruce.motivo


def test_regla_b_referencia_dice_anterior_cuando_toca():
    c = cert(tipo_experiencia="expediente", fecha_final="2022-08-03")
    cruce = evaluar_termino_vs_aprobacion(_enr_no_nombra(), c)
    assert "es 20 días anterior a la aprobación publicada (23/08/2022)" in cruce.motivo


def test_regla_b_nombra_otro_no_lleva_referencia():
    """Ahí ya se nombra al otro consultor: la cifra no aporta y confundiría."""
    c = cert(tipo_experiencia="expediente", fecha_final="2022-11-11")
    cruce = evaluar_termino_vs_aprobacion(_enr_no_nombra("nombra_otro"), c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "CONSORCIO TERCERO" in cruce.motivo
    assert "Referencia:" not in cruce.motivo


# 5 · La frase de cierre de la Regla A cambia con el tipo de experiencia.

def test_regla_a_usa_la_frase_de_expediente_en_un_expediente():
    c = cert(tipo_experiencia="expediente", fecha_inicial="2021-06-01")
    proc = proceso(tipo="expediente")
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proc, c), c)
    assert cruce.resultado == DISPARA
    assert ("No se puede elaborar un expediente cuyo contrato aún no se ha "
            "firmado.") in cruce.motivo
    assert "supervisar" not in cruce.motivo


def test_regla_a_conserva_la_frase_generica_en_una_supervision():
    c = cert(fecha_inicial="2021-06-01")           # tipo_experiencia=supervision
    cruce = evaluar_inicio_vs_contrato(bloque_seace(proceso(), c), c)
    assert cruce.resultado == DISPARA
    assert ("No se puede prestar el servicio de un contrato que todavía no "
            "existe.") in cruce.motivo


# 6 · Las dos oraciones del Excel ya no salen pegadas.

def test_los_motivos_de_las_dos_reglas_se_concatenan_con_punto():
    """El Excel une los motivos de A y B con un espacio; sin el punto final del
    de A salía «…comparar el inicio declarado No se compara el término…»."""
    c = cert(tipo_experiencia="expediente", fecha_inicial="2022-09-05",
             fecha_final="2022-11-11")
    enr = enr_expediente()
    enr["verificacion_expediente"]["contratista"]["veredicto"] = "no_verificable"
    cruces = cruces_de_experiencia(enr, c)
    unido = " ".join(x.motivo for x in cruces)
    assert "declarado No se compara" not in unido
    assert "declarado. No se compara el término declarado" in unido
    for x in cruces:
        assert x.motivo.rstrip().endswith("."), x.motivo


# ── 4 · Cableado en la etapa REGLAS ──────────────────────────────────────────

def _espejo_una_experiencia(exp: dict) -> dict:
    return {
        "_meta": {"concurso": "AS-SM-28-2021-GRJ", "postor": "INDECONSULT"},
        "profesionales": [{
            "n_prof": 1, "nombre": "PEDRO SÁNCHEZ MEZA", "cargo": "Especialista",
            "experiencias": [{"n": 1, "proyecto": "Mejoramiento del E.S.", **exp}],
        }],
    }


def _correr_reglas(espejo: dict, enriquecimiento: dict):
    from orquestador.etapas import Contexto
    from orquestador.etapas_reales import EtapaReglasReal
    ctx = Contexto(job=None, espejo=espejo, enriquecimiento=enriquecimiento)
    res = EtapaReglasReal().correr(ctx)
    return res, ctx


def test_etapa_reglas_emite_alerta_cuando_el_cruce_dispara():
    c = cert(fecha_inicial="2021-06-01")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": {"seace": bloque_seace(proceso(), c)}}
    res, ctx = _correr_reglas(espejo, enr)
    codigos = [o.codigo for o in res.observaciones]
    assert REGLA_INICIO in codigos
    alerta = next(o for o in res.observaciones if o.codigo == REGLA_INICIO)
    assert alerta.severidad.value == "alerta"
    assert alerta.referencia == "prof=1 exp=1"
    guardado = ctx.enriquecimiento["1:1"]["cruces_fechas"]
    assert guardado[0]["resultado"] == DISPARA


def test_etapa_reglas_no_alerta_cuando_el_cruce_se_abstiene():
    """Sin fuente: se persiste la abstención con su razón, y NINGUNA alerta."""
    c = cert(fecha_inicial="2015-01-01", fecha_final="2016-01-01")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": {"seace": {"estado": "sin_procesos", "cui": "2337618"}}}
    res, ctx = _correr_reglas(espejo, enr)
    assert not [o for o in res.observaciones
                if o.codigo in (REGLA_INICIO, REGLA_TERMINO)]
    cruce = ctx.enriquecimiento["1:1"]["cruces_fechas"][0]
    assert cruce["resultado"] == POR_CONFIRMAR
    assert cruce["motivo"]


def test_etapa_reglas_no_rompe_una_experiencia_sin_enriquecimiento():
    espejo = _espejo_una_experiencia(cert())
    res, ctx = _correr_reglas(espejo, {})
    assert res.estado.value == "ok"
    assert ctx.enriquecimiento["1:1"]["cruces_fechas"][0]["resultado"] == POR_CONFIRMAR


# ── 5 · Hoja «Cronología de expedientes» ─────────────────────────────────────

def _hoja(espejo: dict, enriquecimiento: dict):
    inyectar_cruces_fechas(espejo, enriquecimiento)
    _p, _c, fichas, _s = desempaquetar_enriquecimiento(enriquecimiento)
    ws = openpyxl.Workbook().active
    filas = construir_hoja_cronologia(ws, espejo, fichas)
    textos = [str(c.value) for fila in ws.iter_rows() for c in fila
              if c.value is not None]
    return ws, filas, textos


def test_hoja_cronologia_con_datos_muestra_ficha_y_tabla():
    c = cert(fecha_inicial="2021-06-01")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": {"cui": "2337618", "obra_nombre": "MEJORAMIENTO E.S. PEDRO SÁNCHEZ MEZA",
                   "seace": bloque_seace(proceso(), c)}}
    ws, filas, textos = _hoja(espejo, enr)
    assert filas == 1
    unido = " | ".join(textos)
    assert "CRONOLOGÍA DE EXPEDIENTES Y CONTRATOS" in unido
    assert "AS-SM-28-2021-GRJ-CS-1" in unido           # ficha del proyecto
    assert "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL" in unido
    assert "24/09/2021" in unido                        # firma en la ficha
    assert "¿EMPEZÓ DESPUÉS DE FIRMADO EL CONTRATO?" in unido
    # la respuesta de la tabla comparativa: NO (con su explicación al lado)
    assert "NO" in textos
    assert any("no se puede prestar el servicio" in t.lower() for t in textos)


def test_hoja_cronologia_pinta_los_veredictos_con_color():
    c = cert(fecha_inicial="2021-06-01")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": {"cui": "2337618", "seace": bloque_seace(proceso(), c)}}
    ws, _filas, _t = _hoja(espejo, enr)
    fila = next(f[0].row for f in ws.iter_rows(min_col=9, max_col=9)
                if f[0].value == "NO")
    assert ws.cell(fila, 9).fill.fgColor.rgb.endswith("FFC7CE")     # rojo


def test_hoja_cronologia_marca_en_violeta_la_fecha_deducida():
    """Convención vigente: violeta = supuesto/inferido. La fecha de aprobación
    sale del nombre del archivo, no escrita en el documento."""
    c = cert(tipo_experiencia="expediente", fecha_final="2024-03-31")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": enr_expediente()}
    ws, _filas, _t = _hoja(espejo, enr)
    fila = next(f[0].row for f in ws.iter_rows(min_col=10, max_col=10)
                if f[0].value == "NO")
    assert ws.cell(fila, 8).fill.fgColor.rgb.endswith("E4D7F5")     # violeta


def test_hoja_cronologia_de_un_job_viejo_sin_datos_lleva_nota():
    """Sin SEACE ni MEF la hoja EXISTE y dice por qué está vacía — nunca en
    silencio (y nunca insinuando que la propuesta esté mal)."""
    espejo = _espejo_una_experiencia(cert())
    ws, filas, textos = _hoja(espejo, {"1:1": {"cui": "2337618"}})
    unido = " ".join(textos)
    assert "En esta corrida no se obtuvo" in unido
    assert "Esto no prueba que no existan" in unido
    assert "cobertura empieza" not in unido
    assert filas == 1                       # la experiencia igual se lista
    assert "POR VERIFICAR" in textos


def test_hoja_cronologia_sin_jerga():
    """#55 — ni jerga interna ni enums crudos en las celdas del evaluador."""
    c = cert(fecha_inicial="2021-06-01")
    espejo = _espejo_una_experiencia(c)
    espejo["profesionales"][0]["experiencias"][0]["proyecto"] = (
        "Obra leída por agent-propuesta-mapa ⟦crudo: dudoso⟧")
    enr = {"1:1": {"cui": "2337618", "seace": bloque_seace(proceso(), c)}}
    _ws, _filas, textos = _hoja(espejo, enr)
    unido = " ".join(textos)
    for prohibido in ("agent-", "⟦", "⟧", "backend", "null",
                      "por_confirmar", "sin_dato", "a_favor", "en_contra"):
        assert prohibido not in unido, prohibido


# ── 6 · La hoja es ADITIVA (el formato congelado no se mueve) ────────────────

def _volcado(ws) -> list:
    return [(c.row, c.column, c.value) for fila in ws.iter_rows() for c in fila]


def test_la_hoja_nueva_va_al_final_y_no_reordena_el_libro(tmp_path):
    """La hoja de cronología es la ÚLTIMA del libro y no cambia el orden ni el
    contenido de las que ya había.

    Ojo con el alcance: desde el híbrido aprobado el 5-ago, las hojas por
    profesional SÍ ganan el bloque de cruces al final de la hoja — es un
    apéndice bajo la PARTE 5, verificado aparte
    (`test_bloque_por_profesional_va_despues_de_la_parte_5`) y contra el libro
    de `HEAD` sobre un job real. CLAUDE y Base de Datos no se tocan."""
    espejo = _espejo_una_experiencia(cert())
    salida = tmp_path / "final.xlsx"
    generar_excel_final(espejo, salida)
    wb = openpyxl.load_workbook(salida)
    assert wb.sheetnames[-1] == HOJA_CRONOLOGIA
    congeladas = {n: _volcado(wb[n]) for n in wb.sheetnames if n != HOJA_CRONOLOGIA}

    # Referencia: el MISMO libro sin la hoja nueva.
    wb2 = openpyxl.load_workbook(salida)
    del wb2[HOJA_CRONOLOGIA]
    otra = tmp_path / "referencia.xlsx"
    wb2.save(otra)
    wb3 = openpyxl.load_workbook(otra)
    assert wb3.sheetnames == list(congeladas)
    for nombre, celdas in congeladas.items():
        assert _volcado(wb3[nombre]) == celdas


def test_regenerar_un_job_viejo_no_rompe_y_agrega_la_hoja(tmp_path):
    """Compatibilidad: enriquecimiento anterior a T-011 (sin `cruces_fechas`) →
    se regenera sin excepción y la hoja aparece con lo que se pueda decir."""
    c = cert(fecha_inicial="2021-06-01")
    espejo = _espejo_una_experiencia(c)
    enr = {"1:1": {"cui": "2337618", "seace": bloque_seace(proceso(), c)},
           "prof:1": {"dias_efectivos": 100}}
    salida = tmp_path / "final.xlsx"
    regenerar_excel_final(espejo, enr, salida)
    wb = openpyxl.load_workbook(salida)
    assert HOJA_CRONOLOGIA in wb.sheetnames
    assert enr["1:1"]["cruces_fechas"][0]["resultado"] == DISPARA


# ── 7 · Bloque por profesional dentro de cada hoja P (híbrido) ──────────────

TITULO_BLOQUE = "CRUCE DE FECHAS CONTRA EL CONTRATO Y LA APROBACIÓN DEL EXPEDIENTE"


def _libro(espejo: dict, enriquecimiento: dict, tmp_path):
    inyectar_cruces_fechas(espejo, enriquecimiento)
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enriquecimiento)
    salida = tmp_path / "final.xlsx"
    generar_excel_final(espejo, salida, paral, cuis, fichas, {}, sunat, {})
    return openpyxl.load_workbook(salida)


def _buscar(ws, prefijo: str):
    """(fila, celda) de la primera celda que empieza con `prefijo`, o (None, None)."""
    for fila in ws.iter_rows():
        for c in fila:
            if isinstance(c.value, str) and c.value.startswith(prefijo):
                return c.row, c
    return None, None


def _espejo_dos_experiencias() -> dict:
    """Un profesional con dos experiencias: una con proceso publicado y otra sin
    él — el caso que obliga a que la abstención se vea, y no desaparezca."""
    espejo = _espejo_una_experiencia(cert(fecha_inicial="2021-06-01"))
    espejo["profesionales"][0]["experiencias"].append(
        {"n": 2, "proyecto": "Obra antigua sin proceso publicado",
         **cert(fecha_inicial="2013-03-04", fecha_final="2014-08-30")})
    return espejo


def _filas_etiqueta(ws, etiqueta: str, desde: int) -> list[int]:
    """Filas (≥ desde) cuya col A es exactamente `etiqueta` — en el formato
    vertical cada experiencia repite las mismas etiquetas."""
    return [f[0].row for f in ws.iter_rows(min_row=desde, min_col=1, max_col=1)
            if f[0].value == etiqueta]


def test_bloque_por_profesional_una_entrada_por_experiencia(tmp_path):
    espejo = _espejo_dos_experiencias()
    enr = {"1:1": {"cui": "2337618",
                   "seace": bloque_seace(proceso(), cert(fecha_inicial="2021-06-01"))},
           "1:2": {"cui": "2088779", "seace": {"estado": "sin_procesos",
                                               "cui": "2088779"}}}
    wb = _libro(espejo, enr, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    assert fila, "el bloque de cruces no aparece en la hoja del profesional"

    # Formato vertical: una TARJETA por experiencia, con el TIPO en el título y
    # solo las preguntas que aplican — una obra no lleva filas de expediente.
    assert _buscar(ws, "EXPERIENCIA 1 · obra")[0]
    assert _buscar(ws, "EXPERIENCIA 2 · obra")[0]
    preguntas_a = _filas_etiqueta(ws, "¿Empezó después de firmado el contrato?", fila)
    preguntas_b = _filas_etiqueta(ws, "¿Terminó antes de aprobarse el expediente?", fila)
    assert len(preguntas_a) == 2 and not preguntas_b

    # Respuestas en la col B de cada tarjeta.
    assert ws.cell(preguntas_a[0], 2).value == "NO"              # la regla A dispara
    assert ws.cell(preguntas_a[1], 2).value == "POR VERIFICAR"   # sin proceso → abstención

    # La abstención se ROTULA, no desaparece (la explicación de la tarjeta 2).
    fila_exp2 = _buscar(ws, "EXPERIENCIA 2 · obra")[0]
    notas = " ".join(str(f[0].value) for f in ws.iter_rows(
        min_row=fila_exp2, min_col=1, max_col=1) if f[0].value)
    assert "no se halló el proceso" in notas and "2018" not in notas
    assert "no demuestra que no exista" in notas


def test_bloque_por_profesional_colorea_como_la_hoja_global(tmp_path):
    espejo = _espejo_dos_experiencias()
    enr = {"1:1": {"cui": "2337618",
                   "seace": bloque_seace(proceso(), cert(fecha_inicial="2021-06-01"))},
           "1:2": {"cui": "2088779", "seace": {"estado": "sin_procesos"}}}
    wb = _libro(espejo, enr, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    preguntas_a = _filas_etiqueta(ws, "¿Empezó después de firmado el contrato?", fila)
    preguntas_b = _filas_etiqueta(ws, "¿Terminó antes de aprobarse el expediente?", fila)
    assert ws.cell(preguntas_a[0], 2).fill.fgColor.rgb.endswith("FFC7CE")   # rojo
    assert ws.cell(preguntas_a[1], 2).fill.fgColor.rgb.endswith("FFF2CC")   # amarillo
    # En obras la pregunta del término NO existe (antes iba «NO APLICA» sin
    # color; ahora el tipo va en el título y la fila se omite).
    assert not preguntas_b


def test_tarjeta_de_expediente_muestra_el_termino_y_la_aprobacion(tmp_path):
    """La tarjeta de un expediente lleva las 6 filas: término declarado,
    aprobación (violeta si es deducida) y la Regla B pintada."""
    c = cert(tipo_experiencia="expediente", fecha_final="2024-03-31")
    espejo = _espejo_una_experiencia(c)
    wb = _libro(espejo, {"1:1": enr_expediente()}, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    assert _buscar(ws, "EXPERIENCIA 1 · expediente")[0]

    from datetime import datetime as _dt
    f_term = _filas_etiqueta(ws, "Término declarado", fila)[0]
    assert isinstance(ws.cell(f_term, 2).value, _dt)
    assert ws.cell(f_term, 2).number_format == "dd/mm/yyyy"

    f_aprob = _filas_etiqueta(ws, "Aprobación del expediente", fila)[0]
    assert ws.cell(f_aprob, 2).fill.fgColor.rgb.endswith("E4D7F5")   # violeta

    f_b = _filas_etiqueta(ws, "¿Terminó antes de aprobarse el expediente?", fila)[0]
    assert ws.cell(f_b, 2).value == "NO"
    assert ws.cell(f_b, 2).fill.fgColor.rgb.endswith("FFC7CE")       # rojo


def test_las_fechas_llevan_formato_de_fecha_en_las_dos_vistas(tmp_path):
    """El defecto que Rafael detectó: la celda mostraba `2018-05-29 00:00:00`.
    Las cuatro columnas de fecha de las dos vistas llevan `dd/mm/yyyy`, con año
    de cuatro dígitos (aquí el año ES el dato)."""
    from datetime import datetime as _dt

    espejo = _espejo_una_experiencia(cert(fecha_inicial="2021-06-01"))
    enr = {"1:1": {"cui": "2337618",
                   "seace": bloque_seace(proceso(), cert(fecha_inicial="2021-06-01"))}}
    wb = _libro(espejo, enr, tmp_path)

    global_ = wb[HOJA_CRONOLOGIA]
    fila, _c = _buscar(global_, "PROFESIONAL")
    for col in (5, 6, 7):                    # DESDE · HASTA · FIRMA
        c = global_.cell(fila + 1, col)
        assert isinstance(c.value, _dt), col
        assert c.number_format == "dd/mm/yyyy", (col, c.number_format)

    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    # Tarjeta de obra: inicio y firma. (El término declarado, que solo aparece
    # en tarjetas de expediente, se verifica en el test de la tarjeta de
    # expediente.)
    for etiqueta in ("Inicio declarado", "Firma del contrato"):
        f = _filas_etiqueta(ws, etiqueta, fila)[0]
        c = ws.cell(f, 2)
        assert isinstance(c.value, _dt), etiqueta
        assert c.number_format == "dd/mm/yyyy", (etiqueta, c.number_format)


def test_bloque_por_profesional_va_despues_de_la_parte_5(tmp_path):
    """Estrictamente APENDICE: todo lo que ya había en la hoja queda arriba y
    sin mover — el bloque nace debajo de la conclusión del tiempo efectivo."""
    espejo = _espejo_una_experiencia(cert())
    wb = _libro(espejo, {"1:1": {}}, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila_bloque, _a = _buscar(ws, TITULO_BLOQUE)
    fila_p5, _b = _buscar(ws, "PARTE 5")
    fila_concl, _c = _buscar(ws, "CONCLUSIÓN DEL TIEMPO EFECTIVO")
    assert fila_p5 < fila_concl < fila_bloque


def test_bloque_por_profesional_en_un_job_sin_datos(tmp_path):
    """Sin SEACE ni MEF el bloque existe igual, con la abstención rotulada."""
    espejo = _espejo_una_experiencia(cert())
    wb = _libro(espejo, {"1:1": {"cui": "2337618"}}, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    assert fila
    f = _filas_etiqueta(ws, "¿Empezó después de firmado el contrato?", fila)[0]
    assert ws.cell(f, 2).value == "POR VERIFICAR"
    notas = " ".join(str(x[0].value) for x in ws.iter_rows(min_row=fila,
                                                           min_col=1, max_col=1)
                     if x[0].value)
    # Experiencia de 2021-2023: la coletilla de cobertura NO aplica.
    assert "no se halló el proceso de contratación" in notas
    assert "2018" not in notas


def test_bloque_por_profesional_sin_jerga(tmp_path):
    espejo = _espejo_una_experiencia(cert(fecha_inicial="2021-06-01"))
    espejo["profesionales"][0]["experiencias"][0]["proyecto"] = (
        "Obra leída por agent-propuesta-mapa ⟦crudo: dudoso⟧")
    enr = {"1:1": {"cui": "2337618",
                   "seace": bloque_seace(proceso(), cert(fecha_inicial="2021-06-01"))}}
    wb = _libro(espejo, enr, tmp_path)
    ws = wb[[n for n in wb.sheetnames
             if n not in ("CLAUDE", "Base de Datos", HOJA_CRONOLOGIA)][0]]
    fila, _c = _buscar(ws, TITULO_BLOQUE)
    textos = " ".join(str(c.value) for f in ws.iter_rows(min_row=fila)
                      for c in f if c.value is not None)
    for prohibido in ("agent-", "⟦", "⟧", "por_confirmar", "sin_dato", "null"):
        assert prohibido not in textos, prohibido


def test_una_sola_fuente_para_las_dos_vistas():
    """La hoja global y el bloque local leen `presentacion_cruces`: si un texto
    cambia, cambia en los dos. El test lo fija llamándola directo."""
    from entregables.excel_final import presentacion_cruces
    c = cert(fecha_inicial="2021-06-01")
    enr = {"1:1": {"cui": "2337618", "seace": bloque_seace(proceso(), c)}}
    espejo = _espejo_una_experiencia(c)
    inyectar_cruces_fechas(espejo, enr)
    _p, _c2, fichas, _s = desempaquetar_enriquecimiento(enr)
    p = presentacion_cruces(espejo["profesionales"][0]["experiencias"][0],
                            fichas[(1, 1)])
    assert p["resp_a"] == "NO" and p["aplica_b"] is False
    assert p["firma"].isoformat() == "2021-09-24"
    assert "no se puede prestar el servicio" in p["motivo"].lower()


def test_inyectar_cruces_respeta_lo_ya_calculado():
    """Lo que se entregó es lo que se guardó: no se recalcula por encima."""
    espejo = _espejo_una_experiencia(cert())
    enr = {"1:1": {"cruces_fechas": [{"regla": REGLA_INICIO,
                                      "resultado": COINCIDE, "motivo": "x"}]}}
    assert inyectar_cruces_fechas(espejo, enr) == 0
    assert enr["1:1"]["cruces_fechas"][0]["motivo"] == "x"
