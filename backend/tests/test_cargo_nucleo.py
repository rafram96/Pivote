"""
Candado de correspondencia cargo ↔ bases (issue #31).

Caso de referencia: Comité 2026-07-25, huachocolpa P4 «Especialista en
Planeamiento y Costos». Los 4 cargos reales que el Comité declaró NO CUMPLE
están en `fixtures/cargo/planeamiento_costos.json` junto a un control positivo.

La trampa que ataja este candado: «Especialista en Costos, Metrados y
Valorizaciones» comparte el token COSTOS con el cargo exigido → cualquier
matcher laxo (y el LLM) da falso CUMPLE. El núcleo compuesto se exige COMPLETO.
"""
from __future__ import annotations

import json
from pathlib import Path

from schemas.pipeline import Severidad
from validacion import anotar_cargo_nucleo, verificar_espejo
from validacion.cargo_nucleo import (
    derivar_requisito, equivalentes, evaluar_cargo, faltantes,
    funciones_acreditadas, revisar_profesional, veredicto_llm,
)
from validacion.notas import nota_cargo_nucleo

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cargo" / "planeamiento_costos.json"

LISTA_BASES = ("Especialista en Planeamiento y Costos; Responsable de Planeamiento y Costos; "
               "Encargado de Planeamiento y Costos; Ingeniero de Planeamiento y Costos; "
               "Inspector de Planeamiento y Costos")


def _espejo() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _prof(cargos_validos=LISTA_BASES, experiencias=(), **extra) -> dict:
    return {"n_prof": 4, "cargo_bases_nombre": "ESPECIALISTA EN PLANEAMIENTO Y COSTOS",
            "requisitos": {"cargos_validos": cargos_validos},
            "experiencias": list(experiencias), **extra}


def _exp(n, cargo, cargo_bases_valido="SÍ — CUMPLE", funciones=None):
    return {"n": n, "cargo_ocupado": cargo, "cargo_bases_valido": cargo_bases_valido,
            "funciones_similares": funciones}


# ── Derivación del requisito (OR entre alternativas · AND dentro de cada una) ─

def _nucleos(req) -> set:
    return {frozenset(a.terminos) for a in req.alternativas}


def test_variantes_del_mismo_cargo_colapsan_en_un_solo_nucleo():
    """El sustantivo inicial varía y cae solo; el núcleo compuesto queda entero
    y las 5 variantes se deduplican en una sola exigencia."""
    r = derivar_requisito(LISTA_BASES)
    assert _nucleos(r) == {frozenset({"PLANEAMIENTO", "COSTO"})}


def test_nucleo_desde_una_sola_variante_descarta_el_sustantivo():
    r = derivar_requisito("Ingeniero de Planeamiento y Costos")
    assert _nucleos(r) == {frozenset({"PLANEAMIENTO", "COSTO"})}   # INGENIERO no es núcleo


def test_alternativas_distintas_se_evaluan_como_OR():
    """`cargos_similares_validos` son cargos ACEPTABLES, no reformulaciones:
    basta reunir el núcleo de UNA (verificado en 35 espejos reales)."""
    r = derivar_requisito("Especialista en Estructuras; Ingeniero Estructural; Especialista en Cálculo Estructural")
    assert faltantes("Especialista en Estructuras", r) == []
    assert faltantes("Ingeniero de Cálculo Estructural", r) == []
    assert faltantes("Especialista en Arquitectura", r) != []      # ninguna alternativa


def test_ignora_alternativas_que_son_solo_el_sustantivo():
    # las bases suelen escribirlo "especialista / responsable / ... de X":
    # al partir por "/" quedan trozos sin especialidad, que NO deben volver
    # permisivo al requisito (una alternativa vacía aceptaría cualquier cargo)
    r = derivar_requisito("especialista / responsable / encargado / inspector de planeamiento y costos")
    assert _nucleos(r) == {frozenset({"PLANEAMIENTO", "COSTO"})}
    assert faltantes("Especialista en Costos", r) == ["PLANEAMIENTO"]


def test_arquitectura_no_se_confunde_con_el_sustantivo_arquitecto():
    """La familia derivativa NO se aplica a los sustantivos genéricos: ARQUITECTO
    comparte 9 letras con ARQUITECTURA, que sí es una especialidad real."""
    r = derivar_requisito("Especialista en Arquitectura")
    assert _nucleos(r) == {frozenset({"ARQUITECTURA"})}
    assert faltantes("Especialista en Estructuras", r) == ["ARQUITECTURA"]


def test_sustantivos_de_actividad_no_son_nucleo():
    """Regresión del replay: exigir DESARROLLO/ELABORACIÓN/DISEÑO/EXPEDIENTES
    (los faltantes más reclamados, 94× entre los cuatro) son falsos NO — dicen
    qué se hace, no en qué se es especialista."""
    r = derivar_requisito("Encargado del diseño y elaboración de expedientes técnicos "
                          "de instalaciones sanitarias del estudio definitivo")
    assert _nucleos(r) == {frozenset({"SANITARIA"})}
    assert faltantes("Especialista en Sanitarias", r) == []
    # pero el término que SÍ discrimina se sigue exigiendo
    assert faltantes("Especialista en Instalaciones Eléctricas", r) == ["SANITARIAS"]


def test_cargo_declarado_sin_terminos_distintivos_es_abstencion():
    """«Especialista en Instalaciones» no tiene término de especialidad: no se
    puede afirmar que no acredita → abstención, nunca un falso NO."""
    r = derivar_requisito("Especialista en Instalaciones Sanitarias")
    assert faltantes("Especialista en Instalaciones", r) == []
    assert faltantes("Jefe de Proyecto", r) == []


def test_preambulo_de_la_columna_no_entra_al_nucleo():
    """Regresión del replay: 'Cargos similares: …' exigía «CARGOS» y «SIMILARES»
    → 5 falsos NO en un espejo real."""
    r = derivar_requisito("Cargos similares: especialista en arquitectura")
    assert _nucleos(r) == {frozenset({"ARQUITECTURA"})}
    assert faltantes("ESPECIALISTA EN ARQUITECTURA", r) == []


def test_cualificadores_no_se_exigen():
    """Regresión del replay: exigir «MEDIO» o «TRABAJO» son falsos NO sintácticos."""
    r = derivar_requisito("ESPECIALISTA EN MEDIO AMBIENTE")
    assert faltantes("Especialista en Mitigación Ambiental", r) == []
    r2 = derivar_requisito("ESPECIALISTA EN SEGURIDAD Y SALUD EN EL TRABAJO")
    assert faltantes("Ingeniero Especialista en Seguridad, Salud y Medio Ambiente", r2) == []
    assert faltantes("Jefe de Seguridad", r2) == ["SALUD"]   # esto sí se señala


def test_nombre_del_cuadro_es_alternativa_valida():
    r = derivar_requisito(None, "ESPECIALISTA EN ESTRUCTURAS")
    assert _nucleos(r) == {frozenset({"ESTRUCTURA"})}


def test_sin_datos_no_hay_requisito_el_candado_se_abstiene():
    assert derivar_requisito(None) is None
    assert derivar_requisito("") is None
    assert derivar_requisito("Especialista") is None          # solo sustantivo
    assert derivar_requisito("Especialista de Obra") is None  # sustantivo + ruido


# ── El caso real: los 4 cargos del Comité ────────────────────────────────────

def test_los_cuatro_cargos_reales_son_rechazados():
    espejo = _espejo()
    _, hallazgos = revisar_profesional(espejo["profesionales"][0])
    por_n = {h.n_exp: h for h in hallazgos}

    # 3 acreditan costos pero NO planeamiento
    for n in (1, 2, 3):
        assert por_n[n].faltantes == ("PLANEAMIENTO",), f"exp {n}: {por_n[n]}"
        assert not por_n[n].acredita
    # 1 acredita planeamiento (vía planificación) pero NO costos
    assert por_n[4].faltantes == ("COSTOS",)
    # control positivo: núcleo completo, sin hallazgo
    assert por_n[5].acredita and por_n[5].faltantes == ()


def test_trampa_del_token_compartido():
    """ASSERTION EXPLÍCITA (criterio del issue): COSTOS presente NO basta.

    Es el falso CUMPLE que produce el matcher laxo — y el que escribió el LLM.
    """
    r = derivar_requisito(LISTA_BASES)
    trampa = "Especialista en Costos, Metrados y Valorizaciones"
    assert any("COSTO" in a.terminos for a in r.alternativas)   # el token existe…
    assert faltantes(trampa, r) == ["PLANEAMIENTO"]             # …y no acredita


def test_caso_positivo_pasa_sin_alerta():
    r = derivar_requisito(LISTA_BASES)
    assert faltantes("Especialista en Planeamiento y Costos de Obra", r) == []
    assert faltantes("Responsable de Costos y Planeamiento", r) == []   # orden libre


def test_equivalencia_planificacion_es_planeamiento():
    r = derivar_requisito(LISTA_BASES)
    assert faltantes("Especialista en Planificación y Costos", r) == []


def test_presupuestos_no_equivale_a_costos():
    """La equivalencia costos≈presupuestos NO está avalada por el Comité: si se
    admitiera, el cargo 1 del caso real pasaría a acreditar y volvería el falso
    CUMPLE. Este test la mantiene cerrada."""
    r = derivar_requisito("Especialista en Costos")
    assert faltantes("Ingeniero de Presupuestos", r) == ["COSTOS"]


def test_se_cita_la_alternativa_mas_cercana():
    r = derivar_requisito("Especialista en Arquitectura; Especialista en Planeamiento y Costos")
    falt, alt = evaluar_cargo("Ingeniero de Costos", r)
    assert falt == ["PLANEAMIENTO"]                      # la más cercana, no ARQUITECTURA
    assert "Planeamiento" in alt.texto


# ── Familia derivativa (para NO crear falsos negativos) ──────────────────────

def test_familia_derivativa_supervision_supervisor():
    r = derivar_requisito("Jefe de Supervisión de Obra")
    assert _nucleos(r) == {frozenset({"SUPERVISION"})}
    assert faltantes("Supervisor de Obra", r) == []


def test_familia_derivativa_no_abre_la_trampa():
    assert not equivalentes("PLANEAMIENTO", "PRESUPUESTO")
    assert not equivalentes("COSTO", "COSTEO")       # términos cortos: solo exacto
    assert equivalentes("ESTRUCTURA", "ESTRUCTURAL")
    assert equivalentes("ELECTRICA", "ELECTRICIDAD")


def test_plural_y_tildes_no_afectan():
    r = derivar_requisito("Especialista en Estructuras")
    assert faltantes("ESPECIALISTA EN ESTRUCTURA", r) == []
    r2 = derivar_requisito("Especialista en Instalaciones Eléctricas")
    assert faltantes("Ingeniero de instalaciones electricas", r2) == []


def test_cargo_ocupado_vacio_no_produce_falso_no():
    r = derivar_requisito(LISTA_BASES)
    assert faltantes(None, r) == []
    assert faltantes("", r) == []


# ── Segunda puerta: funciones ────────────────────────────────────────────────

def test_funciones_null_no_acredita():
    assert funciones_acreditadas({"funciones_similares": None}) is False
    assert funciones_acreditadas({"funciones_similares": "   "}) is False
    assert funciones_acreditadas({"funciones_similares": "NO — el cert solo consigna el cargo"}) is False
    assert funciones_acreditadas({"funciones_similares": "POR VERIFICAR"}) is False


def test_funciones_listadas_si_acreditan():
    assert funciones_acreditadas(
        {"funciones_similares": "SÍ — el anexo lista: elaboración de valorizaciones, "
                                "programación de obra y control de costos"}) is True


def test_veredicto_llm():
    assert veredicto_llm({"cargo_bases_valido": "SÍ — figura en la lista"}) == "si"
    assert veredicto_llm({"cargo_bases_valido": "NO — no corresponde"}) == "no"
    assert veredicto_llm({"cargo_bases_valido": None}) is None
    assert veredicto_llm({"cargo_bases_valido": "revisar con el Comité"}) is None


# ── Observaciones ────────────────────────────────────────────────────────────

def test_alerta_cuando_contradice_el_si_de_claude():
    prof = _prof(experiencias=[_exp(1, "Ingeniero de Costos y Presupuestos")])
    obs = nota_cargo_nucleo(prof)
    assert len(obs) == 1
    o = obs[0]
    assert o.codigo == "CARGO_NUCLEO" and o.severidad == Severidad.ALERTA
    assert "no acredita cargo ni funciones — a ratificación del Comité" in o.mensaje
    assert "«PLANEAMIENTO»" in o.mensaje and o.referencia == "prof=4 exp=1"


def test_advertencia_cuando_claude_ya_lo_habia_marcado_no():
    prof = _prof(experiencias=[
        _exp(1, "Ingeniero de Costos", cargo_bases_valido="NO — no corresponde al cargo")])
    obs = nota_cargo_nucleo(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.ADVERTENCIA
    assert "concuerda" in obs[0].mensaje


def test_advertencia_cuando_hay_funciones_declaradas():
    prof = _prof(experiencias=[
        _exp(1, "Ingeniero de Costos", funciones="SÍ — el anexo lista programación y costos")])
    obs = nota_cargo_nucleo(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.ADVERTENCIA
    assert "acreditación por funciones" in obs[0].mensaje


def test_nucleo_completo_no_dispara_nada():
    prof = _prof(experiencias=[_exp(1, "Especialista en Planeamiento y Costos de Obra")])
    assert nota_cargo_nucleo(prof) == []


def test_posible_falso_negativo_se_señala_como_info():
    prof = _prof(experiencias=[
        _exp(1, "Especialista en Planeamiento y Costos", cargo_bases_valido="NO — no corresponde")])
    obs = nota_cargo_nucleo(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.INFO
    assert "posible falso negativo" in obs[0].mensaje


def test_abstencion_emite_info_una_sola_vez():
    prof = _prof(cargos_validos=None, experiencias=[
        _exp(1, "Ingeniero de Costos"), _exp(2, "Especialista en Planificación")])
    prof["cargo_bases_nombre"] = None
    obs = nota_cargo_nucleo(prof)
    assert len(obs) == 1 and obs[0].severidad == Severidad.INFO
    assert "se abstuvo" in obs[0].mensaje


def test_fixture_completo_por_verificar_espejo():
    espejo = _espejo()
    obs = [o for o in verificar_espejo(espejo) if o.codigo == "CARGO_NUCLEO"]
    assert len(obs) == 4                                   # las 4 reales; el control no
    assert all(o.severidad == Severidad.ALERTA for o in obs)
    assert {o.referencia for o in obs} == {
        "prof=4 exp=1", "prof=4 exp=2", "prof=4 exp=3", "prof=4 exp=4"}


# ── Marca en el espejo (lo que se ve en rojo en el Excel) ────────────────────

def test_anotar_marca_las_cuatro_y_respeta_el_control():
    espejo = _espejo()
    assert anotar_cargo_nucleo(espejo) == 4
    exps = espejo["profesionales"][0]["experiencias"]
    for e in exps[:4]:
        assert e["cargo_bases_valido"].startswith("NO (candado:")
        assert "a ratificación del Comité" in e["cargo_bases_valido"]
        assert "⟦Claude:" in e["cargo_bases_valido"]        # traza del juicio original
    assert exps[4]["cargo_bases_valido"].startswith("SÍ")    # control positivo intacto


def test_marca_se_pinta_roja_en_el_excel():
    """El Excel pinta por el texto: 'NO…' en columna 'pos' → rojo. Sin tocar el
    formato congelado (no hay columnas nuevas)."""
    from scripts.generar_excel import _clasificar_veredicto, _fill_veredicto, FILL_NO_CUMPLE

    espejo = _espejo()
    anotar_cargo_nucleo(espejo)
    marcado = espejo["profesionales"][0]["experiencias"][0]["cargo_bases_valido"]
    assert _clasificar_veredicto(marcado) == "no"
    assert _fill_veredicto(marcado, "pos") == FILL_NO_CUMPLE


def test_anotar_es_idempotente():
    espejo = _espejo()
    assert anotar_cargo_nucleo(espejo) == 4
    antes = [e["cargo_bases_valido"] for e in espejo["profesionales"][0]["experiencias"]]
    assert anotar_cargo_nucleo(espejo) == 0                # 2ª pasada no toca nada
    assert [e["cargo_bases_valido"] for e in espejo["profesionales"][0]["experiencias"]] == antes


def test_anotar_no_pisa_el_no_de_claude_ni_las_que_tienen_funciones():
    espejo = {"profesionales": [_prof(experiencias=[
        _exp(1, "Ingeniero de Costos", cargo_bases_valido="NO — ya marcada por Claude"),
        _exp(2, "Ingeniero de Costos", funciones="SÍ — el anexo lista las actividades"),
        _exp(3, "Especialista en Planeamiento y Costos"),
    ])]}
    assert anotar_cargo_nucleo(espejo) == 0
    valores = [e["cargo_bases_valido"] for e in espejo["profesionales"][0]["experiencias"]]
    assert valores == ["NO — ya marcada por Claude", "SÍ — CUMPLE", "SÍ — CUMPLE"]


def test_sin_veredicto_de_claude_la_marca_es_amarilla():
    """Calibración del replay: sin un SÍ que desmentir no se afirma el NO — se
    pide confirmación (amarillo), que es donde la precisión del candado es menor."""
    espejo = {"profesionales": [_prof(experiencias=[
        _exp(1, "Ingeniero de Costos", cargo_bases_valido=None)])]}
    assert anotar_cargo_nucleo(espejo) == 1
    marcado = espejo["profesionales"][0]["experiencias"][0]["cargo_bases_valido"]
    assert marcado.startswith("POR VERIFICAR (candado:")

    from scripts.generar_excel import _clasificar_veredicto
    assert _clasificar_veredicto(marcado) == "pend"        # amarillo, no rojo


def test_las_dos_marcas_son_idempotentes_entre_si():
    espejo = {"profesionales": [_prof(experiencias=[
        _exp(1, "Ingeniero de Costos", cargo_bases_valido=None),
        _exp(2, "Ingeniero de Costos", cargo_bases_valido="SÍ — CUMPLE")])]}
    assert anotar_cargo_nucleo(espejo) == 2
    exps = espejo["profesionales"][0]["experiencias"]
    assert exps[0]["cargo_bases_valido"].startswith("POR VERIFICAR (candado:")
    assert exps[1]["cargo_bases_valido"].startswith("NO (candado:")
    assert anotar_cargo_nucleo(espejo) == 0


def test_anotar_no_toca_el_computo_de_dias():
    """Decisión explícita (plan F3): el candado señala, no descuenta tiempo."""
    espejo = _espejo()
    dias_antes = [e.get("dias") for e in espejo["profesionales"][0]["experiencias"]]
    total_antes = dict(espejo["profesionales"][0]["total"])
    anotar_cargo_nucleo(espejo)
    assert [e.get("dias") for e in espejo["profesionales"][0]["experiencias"]] == dias_antes
    assert espejo["profesionales"][0]["total"] == total_antes


def test_espejo_sin_requisitos_no_rompe():
    espejo = {"profesionales": [{"n_prof": 1, "experiencias": [{"n": 1, "cargo_ocupado": "X"}]}]}
    assert anotar_cargo_nucleo(espejo) == 0
    assert derivar_requisito({}.get("cargos_validos")) is None
