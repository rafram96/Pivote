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
    return {
        "entidad_contratante": "GOBIERNO REGIONAL DE JUNÍN",
        "entidad_emisora": "INSTITUTO DE CONSULTORIA S.A.",
        "ruc_emisor": "20263373058",
        "tipo_experiencia": "supervision",
        "fecha_inicial": "2021-10-01",
        "fecha_final": "2023-10-11",
        "monto_contrato_soles": None,
        **over,
    }


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
    assert "2018" in cruce.motivo
    assert cruce.fecha_fuente is None


def test_regla_a_se_abstiene_si_el_proceso_no_publica_la_firma():
    c = cert(fecha_inicial="2021-06-01")
    proc = proceso(fecha_firma=None, fecha_convocatoria=None)
    seace = bloque_seace(proc, c)
    seace["fecha_suscripcion"] = None
    cruce = evaluar_inicio_vs_contrato(seace, c)
    assert cruce.resultado == POR_CONFIRMAR
    assert "no publica la fecha" in cruce.motivo


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
    assert "no publica contratos" in cruce.motivo


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
    assert "Sin procesos verificables" in unido
    assert "no es un defecto de la propuesta" in unido.lower()
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


def test_la_hoja_nueva_no_altera_las_hojas_congeladas(tmp_path):
    """Un job SIN datos SEACE: las hojas del formato (CLAUDE, Base de Datos y
    la del profesional) salen celda por celda idénticas a las de un libro
    construido sin la hoja nueva; lo único que cambia es que aparece una hoja
    más, al final."""
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


def test_inyectar_cruces_respeta_lo_ya_calculado():
    """Lo que se entregó es lo que se guardó: no se recalcula por encima."""
    espejo = _espejo_una_experiencia(cert())
    enr = {"1:1": {"cruces_fechas": [{"regla": REGLA_INICIO,
                                      "resultado": COINCIDE, "motivo": "x"}]}}
    assert inyectar_cruces_fechas(espejo, enr) == 0
    assert enr["1:1"]["cruces_fechas"][0]["motivo"] == "x"
