"""
Tests del escudo de integridad de la evaluación (issue #45).

Dos capas:

1. **Sintéticos** — reproducen los dos síntomas medidos el 26-jul (corrimiento
   +1 y ausencia total), el caso sano y —sobre todo— los BORDES de falsos
   positivos: los patrones de redacción que las corridas buenas sí producen y
   que no deben disparar nada (sustentos escuetos y numéricos, menciones de
   pasada de la especialidad vecina, abreviaturas del postor en el cargo).
2. **Espejos REALES** — los tres jobs que fijan la calibración. Viven fuera de
   git (`backend/datos_pivote/<job>/espejo.json`), así que se saltan si no
   están; corriendo desde un worktree se buscan también en el checkout
   principal, que es donde de verdad viven. El criterio más importante es el
   tercero: la corrida SANA no debe producir NI UN hallazgo. Un escudo que
   grita en las corridas buenas se termina ignorando, y entonces no protege de
   las malas.

Calibración fijada contra los 37 espejos reales disponibles en esta máquina
(26-jul): 27 `confiable`, 5 `revisar` (columnas realmente vacías) y 5
`no_confiable` — los tres jobs de la issue más `12b7cb15ab1e` (corrida sin
evaluación) y `9c292da2de3e`/`fc3d8236815c`, que son otro corrimiento +1 real
descubierto por estos candados: cada profesional cargaba los requisitos y el
sustento del siguiente. Las correcciones de la ronda 2 (cobertura por
profesional, patrón para invalidar, fallar cerrado, `cargos_validos` en los
requisitos) no movieron ni un veredicto de esos 37.

Ronda 3 (el hueco de nivel PROFESIONAL y la ceguera ante lo que rellena el
propio backend). Medido sobre los mismos 37, ninguno de los 27 `confiable` se
movió ni ganó un hallazgo; lo que cambió fue todo hacia el lado seguro:
  · `95af90f1578e` volvió de `revisar` a `no_confiable` — llegó SIN una sola
    respuesta del evaluador y el recálculo del backend (días, colegiatura) la
    disfrazaba de corrida a medias. Es la trampa que documenta el cableado.
  · `36d710f27694` recupera el `PROFESIONAL SIN EVALUAR` del nº10, por lo mismo.
  · `COBERTURA NULA` baja de 23 a 14 avisos: los 9 que se van son de columnas
    (días, colegiatura) que hoy calcula el backend — avisos falsos.
  · el candado nuevo de nivel profesional dispara UNA vez en los 37
    (`fc3d8236815c`, ya `no_confiable`): sin falsos positivos en masa.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config import data_dir
from validacion.integridad import (
    ADVERTENCIA, ALERTA, CODIGOS, CRITICA,
    a_observaciones, cobertura_evaluador, evaluar_confiabilidad,
    referencias_inexistentes, requisitos_de_otro_cargo, revisar_integridad,
    sospecha_declarada, veredicto_faltante_al_final, veredictos_ajenos,
)


# ── Constructores de espejos sintéticos ─────────────────────────────────────

def _exp(n: int, **campos) -> dict:
    # Las fechas van de verdad para que `recalcular_espejo` pueda correr sobre
    # estos mismos espejos: los tests del orden lo necesitan.
    base = {"n": n, "folio": 100 + n, "fecha_inicial": "2018-01-01",
            "fecha_final": "2018-12-31", "dias": 365, "cargo_bases_valido": "SÍ",
            "tipo_obra_valido": "SÍ", "anterior_colegiatura": "NO"}
    base.update(campos)
    return base


def _prof(n: int, cargo: str, cumple: str | None = None, *, validos: str = "",
          exps: list | None = None, bases_nombre: str | None = None, **campos) -> dict:
    base = {
        "n_prof": n,
        "cargo": cargo,
        "cargo_bases_num": n,
        "cargo_bases_nombre": cargo if bases_nombre is None else bases_nombre,
        "requisitos": {"cargos_validos": validos},
        "cumple": cumple,
        "profesion_valida": "SÍ — el título acredita la profesión que piden las bases.",
        "experiencias": [_exp(1), _exp(2), _exp(3)] if exps is None else exps,
    }
    base.update(campos)
    return base


def _espejo(profs: list[dict], avisos: list | None = None, postor: dict | None = None) -> dict:
    return {"profesionales": profs, "observaciones_claude": avisos or [], "postor": postor or {}}


# Roster de referencia. NO es el caso fácil: reproduce los tres estilos de
# sustento que el corpus real muestra en corridas SANAS —
#   · escueto y numérico, sin nombrar la especialidad (4 espejos reales así),
#   · nombrando el cargo tal cual,
#   · nombrando de pasada la especialidad del vecino JUNTO con la propia
#     (~10 espejos reales así) —
# porque son justamente los que un candado mal calibrado convierte en falsos
# positivos. Con este roster el escudo tiene que quedarse callado.
SANO = [
    _prof(1, "JEFE DE SUPERVISIÓN",
          "SÍ CUMPLE – experiencia total bruta 1,577 días ≥ 24 meses requeridos.",
          validos="supervisor; inspector; residente; jefe de proyecto; coordinador"),
    _prof(2, "ESPECIALISTA EN ESTRUCTURAS",
          "CUMPLE – 800 días acreditados frente a los 540 exigidos.",
          validos="Estructuras; Diseño estructural"),
    _prof(3, "ESPECIALISTA EN ARQUITECTURA",
          "CUMPLE — las constancias lo consignan como responsable de arquitectura; "
          "el mismo expediente lo firma el de estructuras, sin cruce de funciones.",
          validos="Arquitectura; Acabados"),
    _prof(4, "ESPECIALISTA EN INSTALACIONES SANITARIAS",
          "CUMPLE — el cargo certificado 'Ingeniero Sanitario' figura en la lista "
          "vigente y suma 700 días.",
          validos="Instalaciones Sanitarias; Ingeniero Sanitario"),
    _prof(5, "ESPECIALISTA EN PLANEAMIENTO, COSTOS Y VALORIZACIONES",
          "SÍ CUMPLE – 1,120 días útiles, por encima del mínimo.",
          validos="Costos; Metrados; Valorizaciones"),
    _prof(6, "ESPECIALISTA EN SEGURIDAD Y SALUD OCUPACIONAL",
          "CUMPLE – 900 días en obras de establecimientos de salud.",
          validos="Seguridad; Salud Ocupacional"),
]


def _codigos(hallazgos) -> list[str]:
    return [h.codigo for h in hallazgos]


# ── Caso sano: el escudo se queda callado ───────────────────────────────────

def test_corrida_sana_no_dispara_nada():
    hallazgos = revisar_integridad(_espejo(SANO))
    assert hallazgos == [], [f"{h.codigo}: {h.mensaje}" for h in hallazgos]
    assert evaluar_confiabilidad(_espejo(SANO)).veredicto == "confiable"
    assert evaluar_confiabilidad(_espejo(SANO)).confiable is True


def test_sustentos_escuetos_y_numericos_no_disparan():
    """4 espejos reales sanos escriben así: sin nombrar NUNCA la especialidad.
    Si eso bastara para acusar, el escudo gritaría en corridas buenas."""
    profs = [dict(p, cumple=f"SÍ CUMPLE – experiencia total bruta {800 + i * 37} días "
                            f"≥ 24 meses requeridos.")
             for i, p in enumerate(SANO)]
    assert veredictos_ajenos(_espejo(profs)) == []


def test_mencionar_de_pasada_la_especialidad_vecina_no_es_veredicto_ajeno():
    """Mientras el sustento hable TAMBIÉN de lo suyo, nombrar al vecino es
    redacción, no corrimiento."""
    profs = list(SANO)
    profs[1] = dict(SANO[1], cumple="CUMPLE — sus estructuras se coordinaron con "
                                    "arquitectura y con instalaciones sanitarias.")
    assert veredictos_ajenos(_espejo(profs)) == []


# ── Síntoma B · ausencia de evaluación ──────────────────────────────────────

def _sin_evaluar(prof: dict) -> dict:
    """Deja el profesional como lo entrega el consolidador cuando el evaluador
    no devolvió su fila: todo lo que produce el evaluador en null."""
    p = dict(prof, cumple=None, profesion_valida=None)
    p["experiencias"] = [dict(e, dias=None, cargo_bases_valido=None,
                              tipo_obra_valido=None, anterior_colegiatura=None)
                         for e in prof["experiencias"]]
    return p


def test_ausencia_total_es_critica():
    espejo = _espejo([_sin_evaluar(p) for p in SANO])
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "no_confiable"
    assert "SIN_EVALUACION" in _codigos(conf.hallazgos)
    assert conf.hallazgos[0].severidad == CRITICA


def test_un_solo_profesional_evaluado_no_es_una_corrida_confiable():
    """EL fallo del consolidador es por índice: `profesionales_eval[String(i)]`.
    Que UNO venga completo no puede tapar a los otros nueve sin evaluar."""
    profs = [SANO[0]] + [_sin_evaluar(p) for p in SANO[1:]]
    conf = evaluar_confiabilidad(_espejo(profs))
    assert conf.veredicto == "no_confiable"
    assert conf.hallazgos[0].codigo == "EVALUACION_INCOMPLETA"
    sin_evaluar = [h.n_prof for h in conf.hallazgos if h.codigo == "PROFESIONAL_SIN_EVALUAR"]
    assert sin_evaluar == [2, 3, 4, 5, 6]      # los señala UNO POR UNO


def test_un_profesional_sin_evaluar_entre_muchos_se_reporta_y_no_pasa_como_sano():
    """Un solo hueco no invalida la corrida, pero jamás sale 'confiable'."""
    profs = list(SANO)
    profs[3] = _sin_evaluar(SANO[3])
    conf = evaluar_confiabilidad(_espejo(profs))
    assert conf.veredicto == "revisar"
    assert _codigos(conf.hallazgos) == ["PROFESIONAL_SIN_EVALUAR"]
    assert conf.hallazgos[0].n_prof == 4 and conf.hallazgos[0].severidad == ALERTA


def test_experiencia_suelta_sin_evaluar_apunta_a_la_fila():
    """Mismo fallo un nivel abajo (`eeByN[n]`): se pierde una fila y ese periodo
    queda sin calcular dentro de un profesional que vino completo."""
    hueca = _exp(2, dias=None, cargo_bases_valido=None,
                 tipo_obra_valido=None, anterior_colegiatura=None)
    profs = list(SANO)
    profs[0] = dict(SANO[0], experiencias=[_exp(1), hueca, _exp(3)])
    hallazgos = cobertura_evaluador(_espejo(profs))
    assert _codigos(hallazgos) == ["EXPERIENCIA_SIN_EVALUAR"]
    assert hallazgos[0].referencia == "prof=1 exp=2"
    assert hallazgos[0].severidad == ALERTA


def test_muchas_filas_huecas_se_agregan_en_un_solo_aviso():
    """Un panel con 19 avisos de la misma cosa no se lee."""
    huecas = [_exp(n, dias=None, cargo_bases_valido=None, tipo_obra_valido=None,
                   anterior_colegiatura=None) for n in range(1, 6)]
    profs = list(SANO)
    profs[0] = dict(SANO[0], experiencias=huecas + [_exp(6)])
    hallazgos = [h for h in cobertura_evaluador(_espejo(profs))
                 if h.codigo == "EXPERIENCIA_SIN_EVALUAR"]
    assert len(hallazgos) == 1 and hallazgos[0].n_exp is None
    assert "5 de las 6" in hallazgos[0].mensaje


def test_veredicto_sin_ningun_calculo_detras_se_reporta():
    """El veredicto y el cálculo se piden por separado: un profesional puede
    traer 'CUMPLE' y ninguna de sus experiencias calculada. El formato se ve
    lleno donde importa y vacío donde se sustenta."""
    huecas = [_exp(n, dias=None, cargo_bases_valido=None, tipo_obra_valido=None,
                   anterior_colegiatura=None) for n in (1, 2, 3)]
    profs = list(SANO)
    profs[2] = dict(SANO[2], experiencias=huecas)
    hallazgos = cobertura_evaluador(_espejo(profs))
    assert _codigos(hallazgos) == ["EXPERIENCIA_SIN_EVALUAR"]
    assert hallazgos[0].n_prof == 3 and hallazgos[0].n_exp is None
    assert "no se apoya en ningún dato" in hallazgos[0].mensaje


def test_si_a_nadie_le_calcularon_nada_se_dice_una_vez_como_columna():
    """Sin contraste no es un problema DE ese profesional: es la columna entera,
    y repetirlo por cabeza sería ruido."""
    profs = [dict(p, experiencias=[_exp(n, dias=None, cargo_bases_valido=None,
                                        tipo_obra_valido=None, anterior_colegiatura=None)
                                   for n in (1, 2, 3)]) for p in SANO]
    assert set(_codigos(cobertura_evaluador(_espejo(profs)))) == {"COBERTURA_NULA"}


def test_columna_vacia_suelta_es_alerta_no_critica():
    """Falta una columna, no la evaluación entera: se avisa, no se invalida."""
    profs = [dict(p, experiencias=[dict(e, tipo_obra_valido=None)
                                   for e in p["experiencias"]])
             for p in SANO]
    hallazgos = cobertura_evaluador(_espejo(profs))
    assert _codigos(hallazgos) == ["COBERTURA_NULA"]
    assert hallazgos[0].severidad == ALERTA
    assert "tipo de obra" in hallazgos[0].mensaje
    assert evaluar_confiabilidad(_espejo(profs)).veredicto == "revisar"


def test_un_dato_faltante_aislado_es_legitimo():
    """Un dato ilegible en UNA fila NO es una falla del evaluador: el criterio es
    cobertura CERO, nunca un porcentaje."""
    profs = [dict(SANO[0],
                  experiencias=[_exp(1, tipo_obra_valido=None), _exp(2), _exp(3)])] + SANO[1:]
    assert cobertura_evaluador(_espejo(profs)) == []


def test_pocas_experiencias_no_alcanzan_para_hablar_de_columna_vacia():
    """Con 2 experiencias, ambas sin ese dato pueden ser dos folios ilegibles."""
    profs = [dict(SANO[0], experiencias=[_exp(1, tipo_obra_valido=None),
                                         _exp(2, tipo_obra_valido=None)])]
    assert "COBERTURA_NULA" not in _codigos(cobertura_evaluador(_espejo(profs)))


def test_los_dias_ya_no_son_senal_porque_los_calcula_el_backend():
    """Que el evaluador no mande días dejó de ser una falla: el backend los
    calcula (son aritmética). Alertar ahí sería gritar en corridas buenas — y un
    escudo que grita en las buenas se termina ignorando."""
    profs = [dict(p, experiencias=[dict(e, dias=None, meses=None, anios=None,
                                        anterior_colegiatura=None)
                                   for e in p["experiencias"]])
             for p in SANO]
    assert revisar_integridad(_espejo(profs)) == []


# ── El veredicto no llegó, pero el cálculo sí (el agujero TODO-O-NADA) ──────
#
# El consolidador busca DOS veces con el mismo índice: el veredicto por un lado
# (`profesionales_eval`) y el cálculo de las experiencias por otro
# (`experiencias_eval`). Si falla solo la PRIMERA, al profesional «le llegó algo»
# —sus filas— y el candado de cobertura lo daba por evaluado; sus dos columnas de
# nivel profesional salían en blanco sin que nadie avisara, porque `COBERTURA_NULA`
# es todo-o-nada y le bastaba UN profesional con veredicto para callarse.

def _sin_veredicto(prof: dict) -> dict:
    """Le llegó el cálculo de sus experiencias, pero no el veredicto."""
    return dict(prof, cumple=None, profesion_valida=None)


def test_veredicto_vaciado_en_la_mayoria_con_las_filas_intactas_es_critico():
    """EL grave: 5 de 6 sin veredicto y las experiencias intactas. Antes esto
    devolvía «confiable» y CERO hallazgos — un Excel con la columna donde se
    decide cada resultado en blanco, presentado como sano."""
    profs = [SANO[0]] + [_sin_veredicto(p) for p in SANO[1:]]
    conf = evaluar_confiabilidad(_espejo(profs))
    assert conf.veredicto == "no_confiable"
    assert conf.hallazgos[0].codigo == "VEREDICTOS_INCOMPLETOS"
    assert conf.hallazgos[0].severidad == CRITICA
    assert "5 de los 6" in conf.hallazgos[0].mensaje


def test_un_solo_profesional_sin_veredicto_se_senala_y_no_pasa_como_sano():
    """Un hueco suelto no invalida la corrida, pero jamás sale «confiable»."""
    profs = list(SANO)
    profs[3] = _sin_veredicto(SANO[3])
    conf = evaluar_confiabilidad(_espejo(profs))
    assert conf.veredicto == "revisar"
    assert _codigos(conf.hallazgos) == ["PROFESIONAL_SIN_VEREDICTO"]
    assert conf.hallazgos[0].n_prof == 4 and conf.hallazgos[0].severidad == ALERTA


def test_falta_un_solo_campo_del_veredicto_y_tambien_se_dice():
    """El consolidador puede perder solo una de las dos celdas."""
    profs = list(SANO)
    profs[2] = dict(SANO[2], profesion_valida=None)
    hallazgos = cobertura_evaluador(_espejo(profs))
    assert _codigos(hallazgos) == ["PROFESIONAL_SIN_VEREDICTO"]
    assert "la profesión" in hallazgos[0].mensaje
    assert "veredicto de cumplimiento" not in hallazgos[0].mensaje


def test_muchos_sin_veredicto_se_agregan_en_un_solo_aviso():
    """Un panel con 29 avisos de la misma cosa no se lee."""
    profs = [SANO[0], SANO[1]] + [_sin_veredicto(p) for p in SANO[2:]]
    hallazgos = [h for h in cobertura_evaluador(_espejo(profs))
                 if h.codigo == "PROFESIONAL_SIN_VEREDICTO"]
    assert len(hallazgos) == 1 and hallazgos[0].n_prof is None
    assert "4 de los 6" in hallazgos[0].mensaje


def test_si_a_nadie_le_llego_el_veredicto_se_dice_una_vez_como_columna():
    """Sin contraste no es un problema DE nadie en particular: es la columna
    entera, y eso ya lo dice `COBERTURA NULA`. Repetirlo por cabeza sería ruido."""
    profs = [_sin_veredicto(p) for p in SANO]
    codigos = _codigos(cobertura_evaluador(_espejo(profs)))
    assert "PROFESIONAL_SIN_VEREDICTO" not in codigos
    assert codigos.count("COBERTURA_NULA") == 2


def test_un_solo_profesional_no_tiene_con_quien_contrastar():
    """Sin hermanos no se puede decir «a él le faltó lo que a los demás sí llegó»,
    porque no hay demás: el candado se abstiene igual que el de las filas."""
    profs = [_sin_veredicto(SANO[0])]
    assert "PROFESIONAL_SIN_VEREDICTO" not in _codigos(cobertura_evaluador(_espejo(profs)))


# ── El escudo no se ciega con lo que rellena el propio backend ──────────────

def test_el_recalculo_del_backend_no_ciega_al_escudo():
    """LA trampa del cableado: el recálculo rellena días y colegiatura. Si esas
    celdas contaran como «entregado», una corrida SIN una sola respuesta del
    evaluador se vería completa apenas el backend la rellenara."""
    from validacion.recalculo import recalcular_espejo

    espejo = _espejo([_sin_evaluar(p) for p in SANO])
    assert evaluar_confiabilidad(espejo).veredicto == "no_confiable"

    recalculo = recalcular_espejo(espejo)
    assert recalculo.rellenos, "el recálculo tiene que haber llenado celdas"
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "no_confiable"
    assert "SIN_EVALUACION" in _codigos(conf.hallazgos)


def test_la_marca_del_candado_de_cargo_no_cuenta_como_respuesta_del_evaluador():
    """`anotar_cargo_nucleo` reescribe `cargo bases válido`. Sobre una celda vacía
    el texto es 100% del backend; sobre una contestada conserva lo del evaluador
    entre ⟦…⟧. Solo el segundo caso prueba que el evaluador contestó."""
    from validacion.cargo_nucleo import Hallazgo as HallazgoCargo, _texto_marca

    h = HallazgoCargo(n_exp=1, cargo_ocupado="RESIDENTE", faltantes=("supervisión",),
                      referencia=None, funciones=False, llm=None)
    del_backend = _texto_marca(h, None, "POR VERIFICAR (candado:")
    con_eco = _texto_marca(h, "SÍ", "NO (candado:")

    profs = [dict(SANO[0], cumple=None, profesion_valida=None,
                  experiencias=[_exp(1, cargo_bases_valido=del_backend,
                                     tipo_obra_valido=None)])] + SANO[1:]
    conf = evaluar_confiabilidad(_espejo(profs))
    assert "PROFESIONAL_SIN_EVALUAR" in _codigos(conf.hallazgos)

    profs[0] = dict(profs[0], experiencias=[_exp(1, cargo_bases_valido=con_eco,
                                                 tipo_obra_valido=None)])
    codigos = _codigos(evaluar_confiabilidad(_espejo(profs)).hallazgos)
    assert "PROFESIONAL_SIN_EVALUAR" not in codigos   # sí contestó: solo falta el veredicto
    assert "PROFESIONAL_SIN_VEREDICTO" in codigos


# ── Síntoma A · corrimiento / veredicto ajeno ───────────────────────────────

def _corrido(profs: list[dict]) -> list[dict]:
    """Cada uno carga el sustento del siguiente; el último se queda sin ninguno."""
    return [dict(p, cumple=(profs[i + 1]["cumple"] if i + 1 < len(profs) else None))
            for i, p in enumerate(profs)]


# Roster con sustentos que SÍ nombran la especialidad (para que el corrimiento
# sea detectable) y corrido un puesto: 4 de 4 evaluables desplazados.
CON_ESPECIALIDAD = [
    _prof(1, "JEFE DE SUPERVISIÓN",
          "CUMPLE — dirigió la supervisión completa, 1,500 días.",
          validos="supervisor; inspector; jefe de proyecto"),
    _prof(2, "ESPECIALISTA EN ESTRUCTURAS",
          "CUMPLE — las constancias lo acreditan en estructuras, 800 días.",
          validos="Estructuras; Diseño estructural"),
    _prof(3, "ESPECIALISTA EN ARQUITECTURA",
          "CUMPLE — las constancias lo acreditan en arquitectura, 900 días.",
          validos="Arquitectura; Acabados"),
    _prof(4, "ESPECIALISTA EN INSTALACIONES SANITARIAS",
          "CUMPLE — las constancias lo acreditan en sanitarias, 700 días.",
          validos="Instalaciones Sanitarias"),
    _prof(5, "ESPECIALISTA EN INSTALACIONES ELÉCTRICAS",
          "CUMPLE — las constancias lo acreditan en eléctricas, 640 días.",
          validos="Instalaciones Eléctricas"),
]
CORRIDO = _corrido(CON_ESPECIALIDAD)


def test_veredicto_ajeno_identifica_al_dueno_del_texto():
    hallazgos = veredictos_ajenos(_espejo(CORRIDO))
    ajenos = [h for h in hallazgos if h.codigo == "VEREDICTO_AJENO"]
    assert [h.n_prof for h in ajenos] == [1, 2, 3, 4]
    assert "N°2" in ajenos[0].mensaje and "ESTRUCTURAS" in ajenos[0].mensaje


def test_el_mensaje_cita_palabras_enteras_no_raices_truncadas():
    """El Ing. Manuel lee «valorizaciones», no «valoriz»."""
    profs = [_prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                   "CUMPLE — acredita metrados y valorizaciones del expediente.",
                   validos="Estructuras"),
             _prof(2, "ESPECIALISTA EN METRADOS, COSTOS Y VALORIZACIONES",
                   "CUMPLE — 900 días.", validos="Costos")]
    mensaje = veredictos_ajenos(_espejo(profs))[0].mensaje
    assert "«valorizaciones»" in mensaje and "«metrados»" in mensaje
    assert "valoriz»" not in mensaje.replace("valorizaciones»", "")


def test_corrimiento_sistematico_es_critico():
    hallazgos = veredictos_ajenos(_espejo(CORRIDO))
    corrimiento = [h for h in hallazgos if h.codigo == "CORRIMIENTO"]
    assert len(corrimiento) == 1
    assert corrimiento[0].severidad == CRITICA
    assert "siguiente" in corrimiento[0].mensaje
    assert evaluar_confiabilidad(_espejo(CORRIDO)).veredicto == "no_confiable"


def test_dos_coincidencias_sueltas_no_invalidan_la_corrida():
    """El borde que el revisor rompió: en un roster de 6, dos sustentos que
    suenan al vecino son ruido de redacción. Se avisa; NO se manda a repetir
    todo el análisis."""
    profs = list(SANO)
    profs[0] = dict(SANO[0], cumple=SANO[1]["cumple"] + " Revisión de estructuras.")
    profs[1] = dict(SANO[1], cumple="CUMPLE — responsable de arquitectura del expediente.")
    conf = evaluar_confiabilidad(_espejo(profs))
    codigos = _codigos(conf.hallazgos)
    assert conf.veredicto == "revisar"
    assert "CORRIMIENTO" not in codigos
    assert codigos.count("VEREDICTO_AJENO") == 2
    assert "POSIBLE_CORRIMIENTO" in codigos


def test_dos_coincidencias_con_evidencia_independiente_si_invalidan():
    """Lo que convierte dos coincidencias en corrimiento no es el propio candado
    léxico, es evidencia de otra fuente: la skill ya tuvo que corregir cargos."""
    profs = list(SANO)
    profs[0] = dict(SANO[0], cumple=SANO[1]["cumple"] + " Revisión de estructuras.")
    profs[1] = dict(SANO[1], cumple="CUMPLE — responsable de arquitectura del expediente.")
    avisos = [_aviso("cargo_corregido") for _ in range(2)]
    conf = evaluar_confiabilidad(_espejo(profs, avisos))
    assert conf.veredicto == "no_confiable"
    assert conf.hallazgos[0].codigo == "CORRIMIENTO"
    assert "corregir el cargo" in conf.hallazgos[0].mensaje


def test_veredicto_escueto_no_basta_para_acusar():
    """Sin mencionar nada de nadie no hay ajeno: un texto pobre no es una mentira."""
    profs = [dict(p, cumple="CUMPLE — supera el mínimo exigido.") for p in SANO]
    assert veredictos_ajenos(_espejo(profs)) == []


def test_sinonimo_de_las_bases_no_se_confunde_con_ajeno():
    """El sustento puede nombrar el cargo como lo escriben las bases y no como
    lo declaró el postor ('tecnología de información' por 'TIC')."""
    profs = SANO[:2] + [_prof(
        3, "ESPECIALISTA EN TIC",
        "CUMPLE — el cargo certificado 'Especialista en Tecnología y Comunicaciones' "
        "acredita por equivalencia el cargo de la lista vigente.",
        validos="especialista de tecnología de información y comunicaciones")]
    assert veredictos_ajenos(_espejo(profs)) == []


def test_cargos_repetidos_hacen_que_el_candado_se_abstenga():
    """Dos profesionales con el mismo cargo: nada distingue a uno de otro, así
    que no se puede afirmar de quién es un texto → no se afirma."""
    profs = [_prof(1, "ESPECIALISTA EN ESTRUCTURAS", SANO[2]["cumple"]),
             _prof(2, "ESPECIALISTA EN ESTRUCTURAS", SANO[2]["cumple"])]
    assert veredictos_ajenos(_espejo(profs)) == []


def test_ultimo_sin_veredicto_es_la_firma_del_corrimiento():
    hallazgos = veredicto_faltante_al_final(_espejo(CORRIDO))
    assert _codigos(hallazgos) == ["VEREDICTO_COLA"]
    assert hallazgos[0].n_prof == 5


def test_nadie_con_veredicto_no_es_corrimiento_sino_ausencia():
    espejo = _espejo([_sin_evaluar(p) for p in SANO])
    assert veredicto_faltante_al_final(espejo) == []


# ── El sustento cita experiencias que no existen ────────────────────────────

def test_experiencia_citada_que_no_existe():
    prof = _prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                 "NO CUMPLE — n1 y n2 no acreditan el cargo, y n4 es posterior.",
                 exps=[_exp(1), _exp(2), _exp(3)])
    hallazgos = referencias_inexistentes(_espejo([prof]))
    assert _codigos(hallazgos) == ["EXPERIENCIA_INEXISTENTE"]
    assert hallazgos[0].severidad == ALERTA
    assert "n°4" in hallazgos[0].mensaje


def test_numero_de_profesional_no_se_lee_como_experiencia():
    """'N° 8' numera profesionales o anexos; leerlo como experiencia inventaría
    hallazgos en cada corrida."""
    prof = _prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                 "CUMPLE — a diferencia del profesional N° 8, aquí no falta ningún "
                 "término del núcleo (ver Anexo N°16).",
                 exps=[_exp(1), _exp(2), _exp(3)])
    assert referencias_inexistentes(_espejo([prof])) == []


def test_conteo_de_documentos_descuadrado_es_solo_advertencia():
    """Un certificado puede cubrir varios periodos: el descuadre es pista, no prueba."""
    prof = _prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                 "CUMPLE — las 2 constancias acreditan el cargo.",
                 exps=[_exp(1), _exp(2), _exp(3)])
    hallazgos = referencias_inexistentes(_espejo([prof]))
    assert _codigos(hallazgos) == ["CONTEO_DESCUADRA"]
    assert hallazgos[0].severidad == ADVERTENCIA


def test_conteo_que_cuadra_no_dispara():
    prof = _prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                 "CUMPLE — las 3 constancias acreditan el cargo.",
                 exps=[_exp(1), _exp(2), _exp(3)])
    assert referencias_inexistentes(_espejo([prof])) == []


# ── Requisitos de otro cargo ────────────────────────────────────────────────

def test_requisitos_de_otra_especialidad():
    """Con dueño identificado: el de al lado sí declara ese cargo."""
    profs = [_prof(1, "ESPECIALISTA EN INSTALACIONES SANITARIAS", SANO[3]["cumple"],
                   bases_nombre="Especialista en Instalaciones Eléctricas",
                   validos="Instalaciones Eléctricas"),
             _prof(2, "ESPECIALISTA EN INSTALACIONES ELÉCTRICAS", SANO[1]["cumple"],
                   validos="Instalaciones Eléctricas")]
    hallazgos = requisitos_de_otro_cargo(_espejo(profs))
    assert _codigos(hallazgos) == ["REQUISITO_AJENO"]
    assert hallazgos[0].severidad == ALERTA
    assert "N°2" in hallazgos[0].mensaje       # dice de quién eran los requisitos


def test_abreviatura_del_postor_no_es_una_acusacion():
    """'ESPECIALISTA EN IIEE' contra 'Especialista en Instalaciones Eléctricas':
    el cargo de bases es el CORRECTO y nadie más reclama ese cargo. Decirle al
    evaluador 'su resultado no vale' sería un falso positivo."""
    profs = [_prof(1, "ESPECIALISTA EN IIEE", "CUMPLE — 900 días acreditados.",
                   bases_nombre="Especialista en Instalaciones Eléctricas",
                   validos="Instalaciones Eléctricas; Electricista"),
             _prof(2, "ESPECIALISTA EN ESTRUCTURAS", "CUMPLE — 800 días.",
                   validos="Estructuras")]
    hallazgos = requisitos_de_otro_cargo(_espejo(profs))
    assert _codigos(hallazgos) == ["REQUISITO_DUDOSO"]
    assert hallazgos[0].severidad == ADVERTENCIA
    assert evaluar_confiabilidad(_espejo(profs)).veredicto == "confiable"


def test_sinonimo_en_cargos_validos_evita_el_falso_positivo():
    """'COORDINADOR DE OBRA' medido con el cargo 'Jefe de Supervisión' cuyos
    cargos válidos incluyen 'coordinador': las bases sí lo admiten."""
    profs = [_prof(1, "COORDINADOR DE OBRA", "CUMPLE — 1,200 días.",
                   bases_nombre="Jefe de Supervisión",
                   validos="supervisor; inspector; coordinador; jefe de proyecto"),
             _prof(2, "ESPECIALISTA EN ESTRUCTURAS", "CUMPLE — 800 días.",
                   validos="Estructuras")]
    assert requisitos_de_otro_cargo(_espejo(profs)) == []


def test_mismo_cargo_escrito_distinto_no_dispara():
    """'Supervisor de Obra' y 'Jefe de Supervisión de Obra' son el mismo cargo."""
    profs = [_prof(1, "SUPERVISOR DE OBRA", SANO[0]["cumple"],
                   bases_nombre="JEFE DE SUPERVISIÓN DE OBRA")]
    assert requisitos_de_otro_cargo(_espejo(profs)) == []


def test_sin_cargo_de_bases_el_candado_se_abstiene():
    """Espejos reales enteros vienen sin `cargo_bases_nombre` (30 profesionales
    en 3289eca1419b): la ausencia del dato no es evidencia de nada."""
    profs = [dict(p, cargo_bases_nombre=None) for p in SANO]
    assert requisitos_de_otro_cargo(_espejo(profs)) == []


def _roster_corrido_en_requisitos(n: int) -> list[dict]:
    """n profesionales; los n-1 primeros con el cargo de bases del siguiente."""
    cargos = ["JEFE DE SUPERVISIÓN", "ESPECIALISTA EN ESTRUCTURAS",
              "ESPECIALISTA EN ARQUITECTURA", "ESPECIALISTA EN INSTALACIONES SANITARIAS",
              "ESPECIALISTA EN INSTALACIONES ELÉCTRICAS", "ESPECIALISTA EN GEOTECNIA",
              "ESPECIALISTA EN IMPACTO AMBIENTAL", "ESPECIALISTA EN METRADOS",
              "ESPECIALISTA EN EQUIPAMIENTO", "ESPECIALISTA EN CLIMATIZACIÓN",
              "ESPECIALISTA EN TOPOGRAFÍA", "ESPECIALISTA EN GEOLOGÍA"][:n]
    return [_prof(i + 1, c, "CUMPLE — 900 días acreditados.",
                  bases_nombre=cargos[i + 1] if i + 1 < len(cargos) else c)
            for i, c in enumerate(cargos)]


def test_requisitos_corridos_en_bloque_son_criticos():
    hallazgos = requisitos_de_otro_cargo(_espejo(_roster_corrido_en_requisitos(5)))
    assert hallazgos[0].codigo == "CORRIMIENTO_REQUISITOS"
    assert hallazgos[0].severidad == CRITICA
    assert _codigos(hallazgos).count("REQUISITO_AJENO") == 4


def test_dos_requisitos_ajenos_en_un_roster_grande_no_invalidan_todo():
    """Dos profesionales mal medidos entre doce son dos problemas, no una corrida
    perdida: se avisa de los dos y el resto del análisis sigue en pie."""
    profs = _roster_corrido_en_requisitos(12)
    for i in range(2, 11):                     # deshace el corrimiento salvo en 1-2
        profs[i] = dict(profs[i], cargo_bases_nombre=profs[i]["cargo"])
    hallazgos = requisitos_de_otro_cargo(_espejo(profs))
    assert _codigos(hallazgos) == ["REQUISITO_AJENO", "REQUISITO_AJENO"]
    assert evaluar_confiabilidad(_espejo(profs)).veredicto == "revisar"


# ── Sospecha declarada por la propia skill ──────────────────────────────────

def _aviso(tipo: str) -> dict:
    return {"severidad": "warning", "tipo": tipo, "mensaje": "…", "referencia": "profesional 1"}


def test_un_cargo_corregido_alerta():
    hallazgos = sospecha_declarada(_espejo(SANO, [_aviso("cargo_corregido")]))
    assert _codigos(hallazgos) == ["CARGO_CORREGIDO"]
    assert hallazgos[0].severidad == ALERTA


def test_muchos_cargos_corregidos_mandan_a_revisar_pero_no_invalidan_solos():
    """El número de cargo YA lo corrigió el candado determinístico: la señal es
    indirecta. Lo que hay que leer son los sustentos — invalidar exige evidencia
    directa (y si la hay, la aporta el candado del texto o el de requisitos)."""
    avisos = [_aviso("cargo_corregido") for _ in range(7)]
    hallazgos = sospecha_declarada(_espejo(SANO, avisos))
    assert hallazgos[0].severidad == ALERTA
    assert "7" in hallazgos[0].mensaje
    assert evaluar_confiabilidad(_espejo(SANO, avisos)).veredicto == "revisar"


def test_aviso_con_llave_codigo_tambien_cuenta():
    """Los espejos reales usan `tipo` en unas corridas y `codigo` en otras."""
    aviso = {"severidad": "warning", "codigo": "cargo_corregido", "mensaje": "…"}
    assert _codigos(sospecha_declarada(_espejo(SANO, [aviso]))) == ["CARGO_CORREGIDO"]


def test_otros_avisos_no_disparan():
    assert sospecha_declarada(_espejo(SANO, [_aviso("tachado_pdf")])) == []


# ── Fallar CERRADO ante lo que no se pudo revisar ───────────────────────────

@pytest.mark.parametrize("basura", [
    None, {}, [], "texto",
    {"profesionales": None},
    {"profesionales": []},
    {"profesionales": [None, "x"]},
    {"profesionales": {"1": {"n_prof": 1}}},   # objeto, no lista
])
def test_espejo_sin_forma_no_es_confiable_sino_no_revisable(basura):
    """La ausencia de datos JAMÁS se reporta como luz verde. Un escudo que llama
    sano a lo que no pudo mirar es peor que no tener escudo."""
    conf = evaluar_confiabilidad(basura)
    assert conf.veredicto == "no_revisable"
    assert conf.confiable is False
    assert _codigos(conf.hallazgos) == ["NO_REVISABLE"]
    assert "no se pudo mirar" in conf.motivo


def test_profesional_vacio_es_ausencia_de_evaluacion_no_silencio():
    conf = evaluar_confiabilidad({"profesionales": [{"n_prof": 1}]})
    assert conf.veredicto == "no_confiable"
    assert _codigos(conf.hallazgos) == ["SIN_EVALUACION"]


# ── Contrato de salida ──────────────────────────────────────────────────────

def test_hallazgos_ordenados_de_lo_mas_grave_a_lo_menos():
    hallazgos = revisar_integridad(_espejo([_sin_evaluar(p) for p in CORRIDO[:3]] + CORRIDO[3:],
                                           [_aviso("cargo_corregido") for _ in range(3)]))
    severidades = [h.severidad for h in hallazgos]
    assert severidades == sorted(severidades, key=[CRITICA, ALERTA, ADVERTENCIA].index)


def test_referencia_en_formato_del_validador():
    prof = _prof(7, "ESPECIALISTA EN ESTRUCTURAS",
                 "CUMPLE — n9 acredita el cargo.", exps=[_exp(1)])
    hallazgo = referencias_inexistentes(_espejo([prof]))[0]
    assert hallazgo.referencia == "prof=7"


def test_conversion_a_observaciones_del_pipeline():
    from schemas.pipeline import Etapa, Severidad

    obs = a_observaciones(revisar_integridad(_espejo(CORRIDO)))
    assert obs and all(o.origen is Etapa.VALIDACION for o in obs)
    assert obs[0].severidad is Severidad.CRITICA
    assert all(o.mensaje for o in obs)


# ── Cableado: la etapa VALIDACIÓN del pipeline ──────────────────────────────

def _correr_validacion(espejo: dict):
    """La etapa real, sin red ni disco."""
    from orquestador.etapas import Contexto
    from orquestador.etapas_reales import EtapaValidacionReal

    ctx = Contexto(job=None, espejo=espejo, enriquecimiento={})
    return EtapaValidacionReal().correr(ctx), ctx


def test_la_etapa_de_validacion_emite_los_hallazgos_del_escudo():
    from schemas.pipeline import EstadoEtapa, Etapa, Severidad

    res, _ctx = _correr_validacion(_espejo(CORRIDO))
    del_escudo = [o for o in res.observaciones if o.codigo in CODIGOS]
    assert "CORRIMIENTO" in {o.codigo for o in del_escudo}
    assert any(o.severidad is Severidad.CRITICA for o in del_escudo)
    assert all(o.origen is Etapa.VALIDACION for o in del_escudo)
    # No bloquea (el evaluador prefiere un Excel con alerta a no tener Excel),
    # pero tampoco termina en verde.
    assert res.estado is EstadoEtapa.OK_CON_REVISION


def test_la_etapa_de_validacion_de_una_corrida_sana_termina_en_verde():
    from schemas.pipeline import EstadoEtapa

    res, _ctx = _correr_validacion(_espejo(SANO))
    assert [o.codigo for o in res.observaciones if o.codigo in CODIGOS] == []
    assert res.estado is EstadoEtapa.OK


def test_la_etapa_mira_el_espejo_ANTES_de_que_el_backend_lo_rellene():
    """Si el escudo corriera después del recálculo, vería días y colegiatura
    llenos POR EL BACKEND y daría por entregado lo que nunca llegó."""
    from schemas.pipeline import EstadoEtapa

    espejo = _espejo([_sin_evaluar(p) for p in SANO])
    res, ctx = _correr_validacion(espejo)
    assert "SIN_EVALUACION" in {o.codigo for o in res.observaciones}
    assert res.estado is EstadoEtapa.OK_CON_REVISION
    # y el recálculo sí corrió: la etapa completa lo que puede, no se planta
    assert ctx.espejo["profesionales"][0]["experiencias"][0]["dias"] == 365


# Un espejo por cada código: el test de lenguaje los recorre TODOS (antes solo
# veía tres de los dieciséis y los peores mensajes nunca se revisaban).
def _un_espejo_por_codigo() -> dict[str, list]:
    huecas = [_exp(n, dias=None, cargo_bases_valido=None, tipo_obra_valido=None,
                   anterior_colegiatura=None) for n in (1, 2, 3, 4, 5)]
    citas = _prof(1, "ESPECIALISTA EN ESTRUCTURAS",
                  "CUMPLE — las 2 constancias y la experiencia n7 acreditan el cargo.",
                  validos="Estructuras", exps=[_exp(1), _exp(2), _exp(3)])
    dos_ajenos = list(SANO)
    dos_ajenos[0] = dict(SANO[0], cumple=SANO[1]["cumple"] + " Revisión de estructuras.")
    dos_ajenos[1] = dict(SANO[1], cumple="CUMPLE — responsable de arquitectura del expediente.")
    dudoso = [_prof(1, "ESPECIALISTA EN IIEE", "CUMPLE — 900 días.",
                    bases_nombre="Especialista en Instalaciones Eléctricas",
                    validos="Instalaciones Eléctricas"),
              _prof(2, "ESPECIALISTA EN ESTRUCTURAS", "CUMPLE — 800 días.",
                    validos="Estructuras")]
    un_hueco = list(SANO)
    un_hueco[3] = _sin_veredicto(SANO[3])
    return {
        "SIN_EVALUACION": revisar_integridad(_espejo([_sin_evaluar(p) for p in SANO])),
        "EVALUACION_INCOMPLETA": revisar_integridad(
            _espejo([SANO[0]] + [_sin_evaluar(p) for p in SANO[1:]])),
        "VEREDICTOS_INCOMPLETOS": revisar_integridad(
            _espejo([SANO[0]] + [_sin_veredicto(p) for p in SANO[1:]])),
        "PROFESIONAL_SIN_VEREDICTO": revisar_integridad(_espejo(un_hueco)),
        "COBERTURA_NULA": revisar_integridad(_espejo(
            [dict(p, experiencias=[dict(e, tipo_obra_valido=None)
                                   for e in p["experiencias"]])
             for p in SANO])),
        "EXPERIENCIA_SIN_EVALUAR": revisar_integridad(_espejo(
            [dict(SANO[0], experiencias=huecas + [_exp(6)]),
             dict(SANO[1], experiencias=[_exp(1), huecas[0], _exp(3)])] + SANO[2:])),
        "CORRIMIENTO": revisar_integridad(_espejo(CORRIDO)),
        "POSIBLE_CORRIMIENTO": revisar_integridad(_espejo(dos_ajenos)),
        "EXPERIENCIA_INEXISTENTE": revisar_integridad(_espejo([citas])),
        "CORRIMIENTO_REQUISITOS": revisar_integridad(
            _espejo(_roster_corrido_en_requisitos(5))),
        "REQUISITO_DUDOSO": revisar_integridad(_espejo(dudoso)),
        "CARGO_CORREGIDO": revisar_integridad(_espejo(SANO, [_aviso("cargo_corregido")])),
        "POSTOR_SIN_MONTOS": revisar_integridad(_espejo(SANO, postor={"experiencia_postor": [{"monto": None}]})),
        "NO_REVISABLE": revisar_integridad(None),
    }


def test_los_escenarios_cubren_todos_los_codigos():
    """Si mañana se agrega un código, este test obliga a darle un escenario — y
    con él, la revisión de lenguaje de abajo."""
    vistos = {h.codigo for hallazgos in _un_espejo_por_codigo().values() for h in hallazgos}
    assert vistos == set(CODIGOS), set(CODIGOS) ^ vistos


def test_mensajes_sin_jerga_tecnica():
    """Los lee el evaluador, no un programador: nada de nombres de campos, de
    agentes ni de raíces truncadas en el texto visible."""
    prohibidas = ("null", "None", "json", "agent-", "schema", "consolidador",
                  "índice", "campo ")
    for hallazgos in _un_espejo_por_codigo().values():
        for h in hallazgos:
            assert not any(p in h.mensaje for p in prohibidas), f"{h.codigo}: {h.mensaje}"
            # Un guion bajo en el texto visible solo puede venir de un nombre de
            # campo del espejo (`cargo_bases_valido`, `profesionales_eval`…).
            assert "_" not in h.mensaje, f"{h.codigo}: {h.mensaje}"
            assert h.mensaje.strip() and h.mensaje.rstrip().endswith(".")
            assert h.mensaje[0].isupper() or h.mensaje[0].isdigit()


def test_espejo_incompleto_no_ensucia_los_mensajes():
    """`n_prof`, `n` y `folio` llegan vacíos en espejos reales. El texto que lee
    el evaluador no puede terminar diciendo «N°None» ni «folio None»."""
    hueca = {"n": None, "folio": None, "dias": None, "cargo_bases_valido": None,
             "tipo_obra_valido": None, "anterior_colegiatura": None}
    completo = dict(SANO[0], experiencias=[_exp(1), hueca, _exp(3)])
    anonimo = {"n_prof": None, "cargo": None, "cumple": None,
               "profesion_valida": None, "experiencias": [dict(hueca)]}
    hallazgos = revisar_integridad(_espejo([completo, anonimo] + SANO[1:]))
    assert {"EXPERIENCIA_SIN_EVALUAR", "PROFESIONAL_SIN_EVALUAR"} <= set(_codigos(hallazgos))
    for h in hallazgos:
        assert "None" not in h.mensaje and "_" not in h.mensaje, h.mensaje


def test_ningun_mensaje_habla_de_cero_o_de_un_solo_elemento_en_plural():
    """'en NINGUNO de los 1 profesionales' delata un candado disparando con
    evidencia insuficiente."""
    for hallazgos in _un_espejo_por_codigo().values():
        for h in hallazgos:
            assert " los 1 " not in h.mensaje and " las 1 " not in h.mensaje, h.mensaje
            assert " los 0 " not in h.mensaje and " las 0 " not in h.mensaje, h.mensaje


# ── Espejos REALES (fuera de git: se saltan si no están) ────────────────────

def _carpetas_de_datos() -> list[Path]:
    """Dónde buscar los espejos reales.

    `data_dir()` es la carpeta que usa la API (respeta PIVOTE_DATA_DIR) y es la
    que vale en el servidor. Corriendo desde un worktree de git esa carpeta está
    vacía, así que se busca además en los `backend/datos_pivote` de los
    directorios padre — que es donde viven en el checkout principal. Sin esto,
    los tres tests que fijan la calibración se saltaban siempre y la evidencia
    contra falsos positivos no corría nunca.
    """
    candidatas = [data_dir()]
    candidatas += [p / "backend" / "datos_pivote" for p in Path(__file__).resolve().parents]
    vistas, out = set(), []
    for c in candidatas:
        if c not in vistas:
            vistas.add(c)
            out.append(c)
    return out


def _espejo_real(job: str) -> dict:
    for carpeta in _carpetas_de_datos():
        ruta = carpeta / job / "espejo.json"
        if ruta.exists():
            return json.loads(ruta.read_text(encoding="utf-8"))
    pytest.skip(f"espejo real no disponible en esta máquina: {job}")


def test_real_corrimiento_36d710f27694():
    """10 profesionales con el veredicto del siguiente y el nº10 sin veredicto."""
    conf = evaluar_confiabilidad(_espejo_real("36d710f27694"))
    codigos = set(_codigos(conf.hallazgos))
    assert conf.veredicto == "no_confiable"
    assert {"CORRIMIENTO", "VEREDICTO_AJENO", "VEREDICTO_COLA", "CARGO_CORREGIDO"} <= codigos

    ajenos = {h.n_prof for h in conf.hallazgos if h.codigo == "VEREDICTO_AJENO"}
    assert {1, 2, 3, 7, 8} <= ajenos          # 7 es el caso citado en la issue
    cola = [h for h in conf.hallazgos if h.codigo == "VEREDICTO_COLA"]
    assert cola[0].n_prof == 10
    # El nº10 no recibió NADA del evaluador; se dice de él, no del promedio.
    solos = {h.n_prof for h in conf.hallazgos if h.codigo == "PROFESIONAL_SIN_EVALUAR"}
    assert solos == {10}

    # El nº4 sigue cargando los requisitos del cargo siguiente (es el que
    # produciría el falso CUMPLE). El nº5 ya no se acusa: el cargo de bases que
    # se le aplicó admite "Instalaciones Eléctricas" entre sus cargos válidos, y
    # acusar ahí es exactamente el falso positivo que la ronda 2 corrigió.
    ajenos_req = {h.n_prof for h in conf.hallazgos if h.codigo == "REQUISITO_AJENO"}
    assert ajenos_req == {4}


def test_real_ausencia_total_95af90f1578e():
    """0 de 63 experiencias y 0 de 10 profesionales con campos del evaluador."""
    conf = evaluar_confiabilidad(_espejo_real("95af90f1578e"))
    assert conf.veredicto == "no_confiable"
    assert "SIN_EVALUACION" in _codigos(conf.hallazgos)
    assert "63" in conf.motivo and "10" in conf.motivo


def test_real_ausencia_parcial_95af90f1578e_no_se_diluye():
    """El escenario con el que el revisor tumbó la ronda 1: se llena UN
    profesional del espejo sin evaluación y el escudo daba luz verde."""
    espejo = _espejo_real("95af90f1578e")
    prof = espejo["profesionales"][-1]
    prof["cumple"] = "CUMPLE — acredita 900 días de experiencia específica."
    prof["profesion_valida"] = "SÍ — el título acredita la profesión."
    prof["experiencias"][0].update(dias=900, cargo_bases_valido="SÍ",
                                   tipo_obra_valido="SÍ", anterior_colegiatura="NO")
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "no_confiable"
    assert conf.hallazgos[0].codigo == "EVALUACION_INCOMPLETA"
    assert len([h for h in conf.hallazgos if h.codigo == "PROFESIONAL_SIN_EVALUAR"]) == 9


def test_real_corrida_sana_ffbda008a346_sin_falsos_positivos():
    """El criterio más importante: la corrida buena no produce NI UN hallazgo."""
    conf = evaluar_confiabilidad(_espejo_real("ffbda008a346"))
    assert conf.hallazgos == [], [f"{h.codigo}: {h.mensaje}" for h in conf.hallazgos]
    assert conf.veredicto == "confiable"


def test_real_veredicto_vaciado_3289eca1419b_no_pasa_como_sano():
    """El escenario con el que el revisor tumbó la ronda 2, sobre el espejo real
    de 30 profesionales: se vacía el VEREDICTO de 29 y se dejan las experiencias
    intactas. El escudo devolvía «confiable» y CERO hallazgos."""
    espejo = _espejo_real("3289eca1419b")
    for prof in espejo["profesionales"][1:]:
        prof["cumple"] = prof["profesion_valida"] = None
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "no_confiable"
    assert conf.hallazgos[0].codigo == "VEREDICTOS_INCOMPLETOS"
    assert "29 de los 30" in conf.hallazgos[0].mensaje


def test_real_sana_ffbda008a346_sigue_sana_despues_de_que_el_backend_la_toque():
    """La corrida buena no puede empezar a producir hallazgos porque el backend
    haya rellenado sus columnas — ni al revés, taparlos."""
    from validacion.cargo_nucleo import anotar_cargo_nucleo
    from validacion.recalculo import recalcular_espejo

    espejo = _espejo_real("ffbda008a346")
    recalcular_espejo(espejo)
    anotar_cargo_nucleo(espejo)
    conf = evaluar_confiabilidad(espejo)
    assert conf.hallazgos == [], [f"{h.codigo}: {h.mensaje}" for h in conf.hallazgos]
    assert conf.veredicto == "confiable"


def test_real_ausencia_total_95af90f1578e_sobrevive_al_recalculo():
    """El mismo espejo sin evaluación, pasado por el backend antes del escudo:
    días y colegiatura quedan llenos por el recálculo y la corrida sigue siendo
    la que llegó vacía. Es la trampa del cableado, medida sobre datos reales."""
    from validacion.cargo_nucleo import anotar_cargo_nucleo
    from validacion.recalculo import recalcular_espejo

    espejo = _espejo_real("95af90f1578e")
    recalcular_espejo(espejo)
    anotar_cargo_nucleo(espejo)
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "no_confiable"
    assert "SIN_EVALUACION" in _codigos(conf.hallazgos)


def test_real_corrida_sana_ffbda008a346_con_un_hueco_si_lo_reporta():
    """La contracara: sobre la MISMA corrida sana, un solo profesional sin
    evaluar ya no pasa desapercibido."""
    espejo = _espejo_real("ffbda008a346")
    prof = espejo["profesionales"][2]
    prof["cumple"] = prof["profesion_valida"] = None
    for exp in prof["experiencias"]:
        exp.update(dias=None, cargo_bases_valido=None, tipo_obra_valido=None,
                   anterior_colegiatura=None)
    conf = evaluar_confiabilidad(espejo)
    assert conf.veredicto == "revisar"
    assert _codigos(conf.hallazgos) == ["PROFESIONAL_SIN_EVALUAR"]
    assert conf.hallazgos[0].n_prof == 3


def test_cobertura_postor_sin_montos():
    """Alerta cuando la experiencia del postor tiene contratos registrados pero 0 montos extraídos."""
    from validacion.integridad import cobertura_postor
    espejo = {
        "profesionales": [{"n_prof": 1, "cargo": "Jefe", "cumple": "CUMPLE", "experiencias": []}],
        "postor": {
            "experiencia_postor": [
                {"n": 1, "cliente": "GORE", "monto": None},
                {"n": 2, "cliente": "MUNI", "monto": 0},
            ]
        }
    }
    hallazgos = cobertura_postor(espejo)
    assert len(hallazgos) == 1
    assert hallazgos[0].codigo == "POSTOR_SIN_MONTOS"
    assert "REQ 3.4" in hallazgos[0].mensaje


def test_extraer_montos_prosa():
    """Prueba el parser fallback de oferta económica sobre texto en prosa."""
    from scripts.generar_excel import _extraer_montos_prosa
    prosa = "La cuantía del proceso es S/ 1,500,000.00 con un límite inferior de 1,350,000.00 y una propuesta económica de S/ 1,420,000.00."
    parsed = _extraer_montos_prosa(prosa)
    assert parsed.get("cuantia") == 1500000.0
    assert parsed.get("limite_inferior") == 1350000.0
    assert parsed.get("propuesta") == 1420000.0

