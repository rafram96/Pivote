"""
Tests del recálculo determinístico de la Parte 4 (issue #45).

Goldens de días tomados de `test_reglas.py` (los pares verificados contra las
hojas manuales del ingeniero): aquí se comprueba que el recálculo respeta esa
misma convención inclusiva y, sobre todo, **cuándo se abstiene**.

100% offline: espejos sintéticos armados a mano. El único test que toca disco es
el del espejo real, y se salta si no está.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pytest

from schemas.espejo import JsonEspejo
from validacion.recalculo import (
    MOTIVO_CENTINELA,
    MOTIVO_DIAS_DISCREPANTE,
    MOTIVO_INVERTIDO,
    MOTIVO_PARCIAL,
    MOTIVO_SIN_COLEGIATURA,
    MOTIVO_SIN_FECHA,
    MOTIVO_TOTAL_INCOMPLETO,
    NO,
    SI,
    calcular_campos,
    fecha_dura,
    observaciones_recalculo,
    recalcular_espejo,
    solapa_covid,
)

COLEGIATURA = "2011-11-23"


def _exp(n=1, ini=None, fin=None, **extra) -> dict:
    return {"n": n, "fecha_inicial": ini, "fecha_final": fin, **extra}


def _espejo(*experiencias, colegiatura=COLEGIATURA) -> dict:
    return {"profesionales": [{
        "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN",
        "fecha_colegiatura": colegiatura,
        "experiencias": list(experiencias),
    }]}


def _fila(espejo, i=0) -> dict:
    return espejo["profesionales"][0]["experiencias"][i]


def _total(espejo) -> dict:
    return espejo["profesionales"][0].get("total") or {}


# ── Caso normal ──────────────────────────────────────────────────────────────

def test_caso_normal_rellena_las_cinco_columnas():
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31"))
    res = recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e["dias"] == 184                    # inclusivo (golden de test_reglas)
    assert e["meses"] == 6.13                  # 184/30
    assert e["anios"] == 0.5                   # 184/365
    assert e["anterior_colegiatura"] == NO     # 2019 > colegiatura 2011
    assert e["incluye_covid"] == NO
    assert res.por_campo() == {
        "dias": 1, "meses": 1, "anios": 1,
        "anterior_colegiatura": 1, "incluye_covid": 1,
        "total.dias": 1, "total.meses": 1, "total.anios": 1}
    assert res.abstenciones == ()
    assert _total(espejo) == {"dias": 184, "meses": 6.13, "anios": 0.5}


def test_un_solo_dia_cuenta_uno():
    espejo = _espejo(_exp(ini="2020-01-01", fin="2020-01-01"))
    recalcular_espejo(espejo)
    assert _fila(espejo)["dias"] == 1


def test_acepta_fechas_ya_coercionadas_a_date():
    """El espejo llega crudo del JSON o ya pasado por Pydantic; da igual."""
    espejo = _espejo(_exp(ini=date(2016, 6, 10), fin=date(2017, 5, 15)))
    recalcular_espejo(espejo)
    assert _fila(espejo)["dias"] == 340


def test_anterior_colegiatura_si_y_borde_estricto():
    espejo = _espejo(
        _exp(1, "2010-01-01", "2010-06-30"),          # anterior a la colegiatura
        _exp(2, COLEGIATURA, "2012-06-30"),           # empieza el MISMO día
    )
    recalcular_espejo(espejo)
    assert _fila(espejo, 0)["anterior_colegiatura"] == SI
    assert _fila(espejo, 1)["anterior_colegiatura"] == NO


# ── Abstenciones ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor, codigo", [
    ("POR VERIFICAR: folio ilegible tras 2 intentos", MOTIVO_CENTINELA),
    ("2019-03 (el certificado solo consigna mes y año)", MOTIVO_PARCIAL),
    (None, MOTIVO_SIN_FECHA),
    ("", MOTIVO_SIN_FECHA),
])
def test_fecha_no_computable_no_calcula_nada(valor, codigo):
    espejo = _espejo(_exp(ini=valor, fin="2019-10-31"))
    res = recalcular_espejo(espejo)
    e = _fila(espejo)

    assert all(e.get(c) is None for c in
               ("dias", "meses", "anios", "anterior_colegiatura", "incluye_covid"))
    assert res.rellenos == ()
    # La fila TOTAL también se abstiene: sin la única experiencia no hay suma.
    assert {a.codigo for a in res.abstenciones} == {codigo, MOTIVO_TOTAL_INCOMPLETO}
    assert res.vacios_por_campo() == {
        "dias": 1, "meses": 1, "anios": 1,
        "anterior_colegiatura": 1, "incluye_covid": 1,
        "total.dias": 1, "total.meses": 1, "total.anios": 1}
    assert _total(espejo) == {}


def test_fecha_final_parcial_deja_calcular_anterior_colegiatura():
    """Solo falta el fin: los días no salen, pero la comparación con la
    colegiatura solo necesita el inicio."""
    espejo = _espejo(_exp(ini="2010-01-01", fin="2010-06 (sin día)"))
    recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e.get("dias") is None
    assert e.get("incluye_covid") is None
    assert e["anterior_colegiatura"] == SI


def test_periodo_invertido_se_abstiene_de_todo():
    """No se sabe cuál de las dos fechas está mal → no se da vuelta el par."""
    espejo = _espejo(_exp(ini="2020-05-01", fin="2019-05-01"))
    res = recalcular_espejo(espejo)

    assert res.rellenos == ()
    assert {a.codigo for a in res.abstenciones} == {
        MOTIVO_INVERTIDO, MOTIVO_TOTAL_INCOMPLETO}
    assert _fila(espejo).get("anterior_colegiatura") is None


def test_sin_colegiatura_queda_null_no_no():
    """No saber no es lo mismo que saber que no."""
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31"), colegiatura=None)
    res = recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e.get("anterior_colegiatura") is None
    assert e["dias"] == 184                    # lo demás sí se calcula
    codigos = {a.codigo for a in res.abstenciones}
    assert codigos == {MOTIVO_SIN_COLEGIATURA}


def test_colegiatura_centinela_tambien_se_abstiene():
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31"),
                     colegiatura="POR VERIFICAR: no consignada")
    res = recalcular_espejo(espejo)
    assert _fila(espejo).get("anterior_colegiatura") is None
    assert {a.codigo for a in res.abstenciones} == {MOTIVO_CENTINELA}


def test_fecha_iso_imposible_no_revienta():
    espejo = _espejo(_exp(ini="2019-02-30", fin="2019-10-31"))
    res = recalcular_espejo(espejo)
    assert _fila(espejo).get("dias") is None
    assert res.abstenciones      # se abstiene, no lanza


# ── Ventana COVID (bordes exactos) ───────────────────────────────────────────

@pytest.mark.parametrize("ini, fin, esperado", [
    ((2020, 3, 16), (2020, 6, 30), True),    # exactamente la ventana
    ((2019, 1, 1), (2020, 3, 16), True),     # termina el primer día → cuenta
    ((2019, 1, 1), (2020, 3, 15), False),    # termina un día antes → no
    ((2020, 6, 30), (2021, 1, 1), True),     # empieza el último día → cuenta
    ((2020, 7, 1), (2021, 1, 1), False),     # empieza un día después → no
    ((2019, 1, 1), (2021, 1, 1), True),      # la envuelve entera
])
def test_covid_bordes_inclusivos(ini, fin, esperado):
    assert solapa_covid(date(*ini), date(*fin)) is esperado


def test_covid_se_escribe_en_el_espejo():
    espejo = _espejo(_exp(1, "2020-03-16", "2020-06-30"),
                     _exp(2, "2020-07-01", "2021-01-01"))
    recalcular_espejo(espejo)
    assert _fila(espejo, 0)["incluye_covid"] == SI
    assert _fila(espejo, 1)["incluye_covid"] == NO


# ── No sobrescribir por defecto ──────────────────────────────────────────────

def test_no_pisa_valores_existentes_por_defecto():
    """El valor del LLM puede traer matices que no se borran a ciegas."""
    matiz = "NO — el título es posterior, pero el cert acredita la práctica"
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31",
                          dias=999, anterior_colegiatura=matiz))
    res = recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e["dias"] == 999
    assert e["anterior_colegiatura"] == matiz
    # `dias` quedó en discrepancia → NO se derivan meses/años de él (ni el total).
    assert set(res.por_campo()) == {"incluye_covid"}
    assert res.sobrescritos == ()


def test_meses_y_anios_se_derivan_del_dias_vigente():
    """Si no pisamos DÍAS, MESES/AÑOS salen de ESE número: la fila del Excel
    tiene que ser internamente coherente."""
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", dias=183))
    recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e["dias"] == 183
    assert e["meses"] == 6.1        # 183/30, no 184/30
    assert e["anios"] == 0.5


def test_sobrescribir_impone_el_valor_del_backend():
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", dias=999))
    recalcular_espejo(espejo, sobrescribir=True)
    e = _fila(espejo)

    assert e["dias"] == 184
    assert e["meses"] == 6.13
    # Ya impuesto el DÍAS del backend, el TOTAL vuelve a ser calculable.
    assert _total(espejo)["dias"] == 184


def test_sobrescribir_borra_el_matiz_en_prosa_y_lo_deja_asentado():
    """El caso que justifica que el defecto sea `sobrescribir=False`.

    Claude escribió una razón en prosa que contradice al cálculo (la experiencia
    SÍ es anterior a la colegiatura, pero el evaluador humano anotó por qué la
    daría por buena). Con `sobrescribir=True` esa prosa se pierde: tiene que
    quedar registrada como SOBRESCRITURA —no como "relleno"— y salir en las
    observaciones, porque el espejo ya no la tiene.
    """
    matiz = "NO — el título es posterior, pero el cert acredita la práctica"
    espejo = _espejo(_exp(ini="2010-01-01", fin="2010-06-30",
                          anterior_colegiatura=matiz))
    res = recalcular_espejo(espejo, sobrescribir=True)

    assert _fila(espejo)["anterior_colegiatura"] == SI      # el matiz se perdió
    pisados = {r.campo: r for r in res.sobrescritos}
    assert set(pisados) == {"anterior_colegiatura"}
    assert pisados["anterior_colegiatura"].previo == matiz  # queda el rastro
    assert res.sobrescritos_por_campo() == {"anterior_colegiatura": 1}
    # …y no se contabiliza como hueco rellenado.
    assert "anterior_colegiatura" not in res.huecos_por_campo()
    assert [(d.campo, d.valor_calculado) for d in res.discrepancias] \
        == [("anterior_colegiatura", SI)]

    obs = observaciones_recalculo(res)
    avisos = [o for o in obs if "sobrescribir=True" in o.mensaje]
    assert len(avisos) == 1
    assert "anterior_colegiatura" in avisos[0].mensaje
    # El INFO de "calculado por el backend" no incluye lo sobrescrito.
    info = [o for o in obs if o.severidad.value == "info"]
    assert all("anterior_colegiatura" not in o.mensaje for o in info)


def test_sobrescribir_no_inventa_donde_el_backend_se_abstiene():
    """`sobrescribir=True` impone lo CALCULADO, no borra por borrar: si el
    backend no pudo calcular, el dato de la propuesta se queda."""
    espejo = _espejo(_exp(ini="POR VERIFICAR: folio ilegible", fin="2019-10-31",
                          dias=200, anterior_colegiatura="NO"))
    res = recalcular_espejo(espejo, sobrescribir=True)
    e = _fila(espejo)

    assert e["dias"] == 200
    assert e["anterior_colegiatura"] == "NO"
    assert res.sobrescritos == ()


def test_discrepancia_se_reporta_sin_tocar_el_dato():
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", dias=999))
    res = recalcular_espejo(espejo)

    assert _fila(espejo)["dias"] == 999
    assert [(d.campo, d.valor_espejo, d.valor_calculado) for d in res.discrepancias] \
        == [("dias", 999, 184)]


def test_dias_discrepante_no_contamina_meses_ni_anios():
    """Si el backend acaba de decir que ese `dias` no es de fiar, no puede
    derivar de él la columna AÑOS (la que lee el Factor A) ni el TOTAL.

    999 días darían 2.74 años donde la verdad calculable es 0.5 — 5x de error en
    celdas que la observación INFO presentaría como "calculadas por el backend".
    """
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", dias=999))
    res = recalcular_espejo(espejo)
    e = _fila(espejo)

    assert e.get("meses") is None and e.get("anios") is None
    assert _total(espejo) == {}
    codigos = {(a.campo, a.codigo) for a in res.abstenciones}
    assert ("meses", MOTIVO_DIAS_DISCREPANTE) in codigos
    assert ("anios", MOTIVO_DIAS_DISCREPANTE) in codigos
    assert ("total.dias", MOTIVO_TOTAL_INCOMPLETO) in codigos


def test_off_by_one_del_llm_no_se_reporta():
    """El LLM cuenta exclusivo (183) y el proyecto inclusivo (184): diferencia
    sistemática de convención, no un error que valga alertar."""
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", dias=183))
    res = recalcular_espejo(espejo)
    assert res.discrepancias == ()


@pytest.mark.parametrize("meses_espejo", [
    6.1,      # 183/30: el conteo exclusivo del LLM (antes alertaba por 0.03)
    6.05,     # 184/30.4167: divisor 365/12, el que Claude usa en la fila TOTAL
    6.13,     # el nuestro
])
def test_meses_no_se_compara_es_una_conversion_de_dias(meses_espejo):
    """DÍAS es el dato; MESES y AÑOS son su conversión de unidad.

    Alertar sobre ellos es alertar sobre el divisor (30 vs 365/12 vs 360), no
    sobre la experiencia del profesional: en los 37 espejos reales, 33 de 34
    discrepancias de meses/años eran exactamente eso. Un candado con 33 falsos
    positivos por acierto se vuelve invisible. La tolerancia queda en un solo
    número (`TOLERANCIA_DIAS`) sobre la única columna que sí es un dato.
    """
    espejo = _espejo(_exp(ini="2019-05-01", fin="2019-10-31", meses=meses_espejo))
    res = recalcular_espejo(espejo)

    assert _fila(espejo)["dias"] == 184          # el hueco de DÍAS sí se rellena
    assert _fila(espejo)["meses"] == meses_espejo    # y lo suyo no se pisa
    assert res.discrepancias == ()


# ── Fila TOTAL de la Parte 4 ─────────────────────────────────────────────────

def test_total_suma_las_experiencias():
    """El número que el evaluador lee como «años de experiencia»: si las filas
    se recalculan y el total no, el Excel se autocontradice."""
    espejo = _espejo(
        _exp(1, "2019-05-01", "2019-10-31"),          # 184
        _exp(2, "2016-06-10", "2017-05-15"),          # 340
    )
    res = recalcular_espejo(espejo)

    assert _total(espejo) == {"dias": 524, "meses": 17.47, "anios": 1.44}
    assert res.por_campo()["total.dias"] == 1


def test_total_se_abstiene_si_los_periodos_se_traslapan():
    """Con solape la suma bruta EXAGERA, y el backend no puede saber si esa celda
    debía ir bruta o de-solapada.

    Caso real (`013721553f0a` prof 4): Claude puso `total.anios = 5` con la
    columna sumando 8.38 y su veredicto diciendo "de-solapando 2022-2026".
    Escribir ahí la suma bruta habría inflado 3.4 años la celda que decide el
    Factor A. Quien descuenta el solape es el Paso 5.
    """
    espejo = _espejo(
        _exp(1, "2020-01-01", "2020-06-30"),          # 182
        _exp(2, "2020-01-01", "2020-06-30"),          # 182, idéntico periodo
    )
    res = recalcular_espejo(espejo)

    assert _total(espejo) == {}                        # ni 364 ni 182
    motivos = [a.motivo for a in res.abstenciones if a.campo == "total.dias"]
    assert len(motivos) == 1 and "182 días en común" in motivos[0]


def test_periodos_contiguos_no_son_traslape():
    """Uno termina y el otro empieza al día siguiente: no hay día compartido."""
    espejo = _espejo(
        _exp(1, "2020-01-01", "2020-06-30"),          # 182
        _exp(2, "2020-07-01", "2020-12-31"),          # 184
    )
    recalcular_espejo(espejo)
    assert _total(espejo)["dias"] == 366


def test_total_se_abstiene_si_falta_una_experiencia():
    """Un total parcial no se lee como «faltan datos», se lee como la
    experiencia completa del profesional."""
    espejo = _espejo(
        _exp(1, "2019-05-01", "2019-10-31"),
        _exp(2, "POR VERIFICAR: folio ilegible", "2020-04-01"),
    )
    res = recalcular_espejo(espejo)

    assert _fila(espejo, 0)["dias"] == 184             # la fila calculable sí sale
    assert _total(espejo) == {}
    motivos = [a.motivo for a in res.abstenciones if a.campo == "total.dias"]
    assert len(motivos) == 1 and "1 de 2 experiencias" in motivos[0]


def test_total_previo_que_no_cuadra_se_reporta_y_no_se_pisa():
    """El caso real del corpus: total.dias=0 con 758 días ya calculados. El
    Comité manda; el backend alerta (y `notas.totales_cuadran` también)."""
    espejo = _espejo(_exp(1, "2019-05-01", "2019-10-31"))
    espejo["profesionales"][0]["total"] = {"dias": 0, "meses": 0, "anios": 0}
    res = recalcular_espejo(espejo)

    assert _total(espejo) == {"dias": 0, "meses": 0, "anios": 0}
    # UNA alerta, no tres: el defecto es el total, y meses/años tampoco se
    # rederivan de un número que el backend acaba de declarar no confiable.
    assert [(d.campo, d.valor_espejo, d.valor_calculado) for d in res.discrepancias] \
        == [("total.dias", 0, 184)]


def test_total_tolera_el_off_by_one_acumulado():
    """±1 día por experiencia, igual que `notas.totales_cuadran`: 3 experiencias
    contadas en exclusivo dan 3 días menos y eso no es un error."""
    espejo = _espejo(
        _exp(1, "2019-05-01", "2019-10-31"),          # 184
        _exp(2, "2016-06-10", "2017-05-15"),          # 340
        _exp(3, "2020-01-01", "2020-06-30"),          # 182  → 706
    )
    espejo["profesionales"][0]["total"] = {"dias": 703}
    res = recalcular_espejo(espejo)
    assert res.discrepancias == ()
    assert _total(espejo)["dias"] == 703               # se respeta lo del espejo
    assert _total(espejo)["meses"] == 23.43            # …y meses/años salen de ÉL


def test_profesional_sin_experiencias_no_estrena_total():
    espejo = {"profesionales": [{"n_prof": 1, "experiencias": []}]}
    res = recalcular_espejo(espejo)
    assert res.tocadas == 0 and res.abstenciones == ()
    assert "total" not in espejo["profesionales"][0]


def test_covid_contradictorio_no_duplica_la_nota10():
    """Contradecir el `incluye_covid` de Claude es trabajo de NOTA 10."""
    espejo = _espejo(_exp(ini="2020-03-01", fin="2020-04-01", incluye_covid="NO"))
    res = recalcular_espejo(espejo)
    assert res.discrepancias == ()
    assert _fila(espejo)["incluye_covid"] == "NO"


def test_flag_con_tilde_o_sin_ella_no_es_discrepancia():
    espejo = _espejo(_exp(ini="2010-01-01", fin="2010-06-30",
                          anterior_colegiatura="SI"))
    res = recalcular_espejo(espejo)
    assert res.discrepancias == ()


# ── Idempotencia ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sobrescribir", [False, True])
def test_idempotente(sobrescribir):
    espejo = _espejo(
        _exp(1, "2019-05-01", "2019-10-31"),
        _exp(2, "POR VERIFICAR", "2020-04-01"),      # el prof 1 no llega al TOTAL
        _exp(3, "2016-06-10", "2017-05-15", dias=339),
    )
    espejo["profesionales"].append({                  # este sí: el TOTAL se escribe
        "n_prof": 2, "cargo": "ESPECIALISTA", "fecha_colegiatura": COLEGIATURA,
        "experiencias": [_exp(1, "2019-05-01", "2019-10-31"),
                         _exp(2, "2020-01-01", "2020-06-30")],
    })
    recalcular_espejo(espejo, sobrescribir=sobrescribir)
    assert espejo["profesionales"][1]["total"]["dias"] == 366
    primera = json.dumps(espejo, sort_keys=True, default=str)

    res = recalcular_espejo(espejo, sobrescribir=sobrescribir)
    assert json.dumps(espejo, sort_keys=True, default=str) == primera
    assert res.rellenos == ()          # la segunda pasada no toca nada


def test_espejo_sin_profesionales_no_revienta():
    assert recalcular_espejo({}).tocadas == 0
    assert recalcular_espejo({"profesionales": None}).tocadas == 0
    assert recalcular_espejo({"profesionales": [{"n_prof": 1}]}).tocadas == 0


# ── Función pura de cálculo ──────────────────────────────────────────────────

def test_calcular_campos_no_muta_la_experiencia():
    exp = _exp(ini="2019-05-01", fin="2019-10-31")
    antes = dict(exp)
    valores, motivos = calcular_campos(exp, COLEGIATURA)

    assert exp == antes
    assert valores == {"dias": 184, "incluye_covid": NO, "anterior_colegiatura": NO}
    assert motivos == {}


@pytest.mark.parametrize("valor, esperado", [
    ("2019-05-01", date(2019, 5, 1)),
    (date(2019, 5, 1), date(2019, 5, 1)),
    ("2019-05", None),
    ("2019-05-01 (aprox)", None),
    ("POR VERIFICAR", None),
    (None, None),
    (184, None),
])
def test_fecha_dura(valor, esperado):
    assert fecha_dura(valor) == esperado


# ── Observaciones para el pipeline ───────────────────────────────────────────

def test_observaciones_agrupan_por_experiencia():
    espejo = _espejo(
        _exp(1, "2019-05-01", "2019-10-31"),
        _exp(2, "POR VERIFICAR", "2020-04-01"),
        _exp(3, "2019-01-01", "2019-06-30", dias=999),
    )
    obs = observaciones_recalculo(recalcular_espejo(espejo))
    por_sev = {}
    for o in obs:
        por_sev.setdefault(o.severidad.value, []).append(o)

    assert len(por_sev["info"]) == 1                  # un resumen de lo rellenado
    refs = [o.referencia for o in por_sev["advertencia"]]
    # exp 2: 5 columnas sin calcular, un solo motivo → UNA observación
    # exp 3: meses/años no derivados del `dias` en discrepancia → otra
    # TOTAL: no sumable (2 de 3 experiencias) → otra, sin número de experiencia
    assert refs == ["prof=1 exp=2", "prof=1 exp=3", "prof=1"]
    assert len(por_sev["alerta"]) == 1                # la discrepancia de días
    assert all(o.codigo == "RECALCULO" for o in obs)


# ── Espejo real (skip si no está: datos del cliente, fuera de git) ───────────

def _ruta_espejo_real(job: str) -> Path | None:
    """Busca `backend/datos_pivote/<job>/espejo.json` hacia arriba, para que el
    test funcione igual desde el repo o desde un worktree (donde datos_pivote no
    existe porque está gitignoreado)."""
    env = os.environ.get("PIVOTE_DATOS")
    candidatos = [Path(env) / job / "espejo.json"] if env else []
    aqui = Path(__file__).resolve()
    for base in aqui.parents:
        candidatos.append(base / "datos_pivote" / job / "espejo.json")
        candidatos.append(base / "backend" / "datos_pivote" / job / "espejo.json")
    return next((c for c in candidatos if c.exists()), None)


def test_espejo_real_95af_queda_con_dias(capsys):
    """La corrida sin evaluación: 63 experiencias, 0 con `dias`. Tras el
    recálculo deben quedar todas salvo las de fecha no computable."""
    ruta = _ruta_espejo_real("95af90f1578e")
    if ruta is None:
        pytest.skip("espejo real 95af90f1578e no disponible en esta máquina")

    espejo = json.loads(ruta.read_text(encoding="utf-8"))
    profs = espejo["profesionales"]
    exps = [e for p in profs for e in p.get("experiencias", [])]
    assert len(exps) == 63
    assert sum(1 for e in exps if e.get("dias") is not None) == 0   # el bug de #45
    assert all(not p.get("total") for p in profs)                   # y la fila TOTAL vacía

    res = recalcular_espejo(espejo)

    con_dias = sum(1 for e in exps if e.get("dias") is not None)
    sin_dias = [(a.n_prof, a.n_exp, a.motivo) for a in res.abstenciones
                if a.campo == "dias"]
    anteriores = sum(1 for e in exps
                     if str(e.get("anterior_colegiatura") or "").startswith("S"))
    con_total = sum(1 for p in profs if (p.get("total") or {}).get("dias") is not None)
    sin_total = [(a.n_prof, a.motivo) for a in res.abstenciones
                 if a.campo == "total.dias"]
    # ASCII a secas: la consola de Windows (cp1252) revienta con el resto.
    with capsys.disabled():
        print(f"\n  espejo 95af90f1578e: {con_dias}/63 experiencias con DIAS "
              f"({len(sin_dias)} sin fechas computables); "
              f"{anteriores} anteriores a la colegiatura; "
              f"{con_total}/{len(profs)} profesionales con fila TOTAL")
        for n_prof, n_exp, motivo in sin_dias:
            print(f"    prof={n_prof} exp={n_exp}: {motivo}".encode(
                "ascii", "replace").decode())
        for n_prof, motivo in sin_total:
            print(f"    TOTAL prof={n_prof}: {motivo}".encode(
                "ascii", "replace").decode())

    assert con_dias + len(sin_dias) == 63
    assert con_dias == 63          # las 63 traen fechas ISO completas
    assert res.por_campo()["anterior_colegiatura"] == 63
    # `incluye_covid` ya venía de Claude en las 63 → no se toca ninguna.
    assert "incluye_covid" not in res.por_campo()
    # Con las 63 filas calculables, 8 de los 10 profesionales recuperan su TOTAL;
    # los otros 2 tienen periodos traslapados y el backend no inventa el criterio.
    assert con_total == 8
    assert [m for _, m in sin_total] and all("traslapan" in m for _, m in sin_total)
    # El espejo enriquecido sigue cumpliendo el contrato v1.2.0 (lo que se sube
    # al panel y lee el Excel es este mismo dict).
    JsonEspejo.model_validate(espejo)
