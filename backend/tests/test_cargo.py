"""Splitter de cargo atómico (schemas.cargo) — la correspondencia con bases sale
del nombre a campos propios, idempotente."""
from schemas.cargo import normalizar_cargos_espejo, partir_cargo


def test_parte_correspondencia_completa():
    nombre, num, base = partir_cargo(
        "Especialista en Supervisión de Estructuras N° 1 (cargo bases N°5 ESPECIALISTA EN ESTRUCTURAS)")
    assert nombre == "Especialista en Supervisión de Estructuras N° 1"
    assert num == 5
    assert base == "ESPECIALISTA EN ESTRUCTURAS"


def test_parte_solo_numero():
    nombre, num, base = partir_cargo(
        "Especialista en Supervisión de la Seguridad y Salud en el Trabajo N° 2 (cargo bases N°12)")
    assert nombre.endswith("Trabajo N° 2")
    assert num == 12
    assert base is None


def test_cargo_limpio_no_se_toca():
    # un "N° 1" en el nombre no debe confundirse con la cola de bases
    nombre, num, base = partir_cargo("Gerente de Supervisión")
    assert (nombre, num, base) == ("Gerente de Supervisión", None, None)
    nombre, num, base = partir_cargo("Especialista en Supervisión de Arquitectura N° 1")
    assert num is None and base is None


def test_normaliza_espejo_idempotente():
    espejo = {"profesionales": [
        {"n_prof": 1, "cargo": "Gerente de Supervisión"},
        {"n_prof": 2, "cargo": "Especialista N° 1 (cargo bases N°5 ESTRUCTURAS)"},
    ]}
    assert normalizar_cargos_espejo(espejo) == 1            # solo el 2º cambia
    p2 = espejo["profesionales"][1]
    assert p2["cargo"] == "Especialista N° 1"
    assert p2["cargo_bases_num"] == 5
    assert p2["cargo_bases_nombre"] == "ESTRUCTURAS"
    assert normalizar_cargos_espejo(espejo) == 0           # 2ª pasada no toca nada


def test_no_pisa_lo_que_la_skill_ya_separo():
    espejo = {"profesionales": [
        {"n_prof": 1, "cargo": "Especialista N° 1", "cargo_bases_num": 5,
         "cargo_bases_nombre": "ESTRUCTURAS"},
    ]}
    assert normalizar_cargos_espejo(espejo) == 0
