"""Compuerta de RUBRO del resolver CUI — caso golden Chinchinga (auditoría 20-jul).

El certificado de un Puesto de SALUD del C.P. Chinchinga se resolvía SILENCIOSAMENTE
(via NOMBRE, riesgo BAJO) a la obra de infraestructura DEPORTIVA del mismo centro
poblado (CUI 2468642), porque los tokens distintivos quedaban en topónimos
({CHINCHINGA, POBLADO}) y el tipo de servicio no participaba de la decisión.

Candidatos congelados de la búsqueda real en InfoObras ("CHINCHINGA", 19-jul-2026).
La obra CORRECTA (2376130) existe pero InfoObras tiene su nombre corrupto en origen
("O DE CHINCHINGA…", sin el inicio "MEJORAMIENTO… DEL PUEST-"): en el MEF su nombre
oficial calza literal con el certificado — por eso el MEF entra como fuente en el
plan de afinamiento. Con solo InfoObras, el resultado honesto es: JAMÁS la obra
deportiva; la correcta si el ranking la deja, o revisión visible.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from resolucion.cui import resolver, rubros_de, _rubro_contradice  # noqa: E402

EXP_CHINCHINGA = {
    "proyecto": ("Mejoramiento y Ampliación de los Servicios del Puesto de Salud "
                 "del Centro Poblado de Chinchinga del distrito de San Pablo de "
                 "Pillao, provincia de Huánuco, región Huánuco"),
    "fecha_inicial": "2021-03-01",
    "fecha_final": "2022-06-30",
}

# Búsqueda real InfoObras "CHINCHINGA" (congelada 19-jul-2026, campos mínimos)
_CANDIDATOS = [
    {"nombrObra": "MEJORAMIENTO DE LOS SERVICIOS DEL ESTADIO DE CHINCHINGA, DISTRITO DE CHINCHAO - HUANUCO - HUANUCO",
     "codUniqInv": "2282043", "codigoObra": 90001, "nombrDepartamento": "HUANUCO"},
    {"nombrObra": "INSTALACION DE LOS SISTEMAS DE AGUA POTABLE Y SANEAMIENTO DE LA LOCALIDAD DE CHINCHINGA, DISTRITO DE CHINCHAO",
     "codUniqInv": "2147776", "codigoObra": 90002, "nombrDepartamento": "HUANUCO"},
    # la obra CORRECTA — con el nombre CORRUPTO tal como lo registra InfoObras
    {"nombrObra": "O DE CHINCHINGA DEL DISTRITO DE SAN PABLO DE PILLAO - PROVINCIA DE HUANUCO - DEPARTAMENTO DE HUANUCO",
     "codUniqInv": "2376130", "codigoObra": 90003, "nombrDepartamento": "HUANUCO"},
    # la obra que GANABA silenciosamente (deportiva, mismo C.P.)
    {"nombrObra": "CREACIÓN DE LOS SERVICIOS DE INFRAESTRUCTURA DEPORTIVA Y RECREATIVA DEL CENTRO POBLADO DE CHINCHINGA DEL DISTRITO DE SAN PABLO DE PILLAO",
     "codUniqInv": "2468642", "codigoObra": 90004, "nombrDepartamento": "HUANUCO"},
]


class ConsultaCongelada:
    def por_codigo(self, codigo):
        return [o for o in _CANDIDATOS
                if str(o.get("codUniqInv")) == str(codigo)]

    def buscar(self, nombre):
        n = (nombre or "").upper()
        return [o for o in _CANDIDATOS if n and n.split()[0] in o["nombrObra"].upper()] \
            or ([] if "CHINCHINGA" not in n else _CANDIDATOS)


def test_rubros_de_clasifica_bien():
    assert "salud" in rubros_de(EXP_CHINCHINGA["proyecto"])
    assert rubros_de(_CANDIDATOS[3]["nombrObra"]) == {"deporte"}
    assert "vial" in rubros_de("REHABILITACION DEL CAMINO VECINAL CHINCHINGA - CRUZ PUNTA")
    # indeterminado (nombre corrupto sin palabras de rubro) → set vacío
    assert rubros_de(_CANDIDATOS[2]["nombrObra"]) == set()


def test_veto_exige_contradiccion_positiva():
    rub_salud = rubros_de(EXP_CHINCHINGA["proyecto"])
    assert _rubro_contradice(rub_salud, _CANDIDATOS[3]["nombrObra"])      # deportiva → veta
    assert not _rubro_contradice(rub_salud, _CANDIDATOS[2]["nombrObra"])  # indeterminado → NO veta
    assert not _rubro_contradice(set(), _CANDIDATOS[3]["nombrObra"])      # cert indeterminado → NO veta


def test_chinchinga_jamas_resuelve_a_la_obra_deportiva():
    r = resolver(EXP_CHINCHINGA, ConsultaCongelada())
    # el error silencioso original: via NOMBRE → CUI 2468642 (deportiva). PROHIBIDO.
    assert r.get("cui") != "2468642", f"regresión: volvió a ganar la obra deportiva ({r})"
    # resultado aceptable: la obra correcta (si el ranking la deja) o revisión VISIBLE
    if r["estado"] == "resuelto":
        assert r["cui"] == "2376130"
    else:
        assert r["estado"] == "revision"
        # la deportiva puede aparecer como candidato para la cola humana — pero
        # etiquetada, nunca auto-resuelta
    # y el veto no borra la evidencia: si todos los candidatos fueron vetados,
    # el motivo lo dice explícitamente
    if r["estado"] == "revision" and "otro rubro" in r["decision"]:
        assert r["candidatos"], "los vetados deben quedar visibles para revisión"


def test_cui_citado_exacto_sigue_siendo_autoritativo():
    # un CUI escrito en el certificado que calza EXACTO gana aunque el rubro del
    # nombre difiera (el cert suele citar un componente del proyecto integral)
    r = resolver({**EXP_CHINCHINGA, "cui": "2376130"}, ConsultaCongelada())
    assert r["estado"] == "resuelto" and r["cui"] == "2376130"
