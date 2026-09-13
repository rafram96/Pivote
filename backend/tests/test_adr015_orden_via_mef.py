"""
ADR-015 §2 · ORDEN CON LA VÍA MEF (solo camino A, expedientes).

El candado de ADR-005 §1 («un candidato que solo el MEF respalda no gana sin
corroboración dura») se escribió para OBRAS. En un EXPEDIENTE, que InfoObras no
devuelva el proyecto por NOMBRE no es sospechoso: el Banco de Inversiones es su
fuente primaria y la fusión trae el registro por CÓDIGO, con `origen == "mef"` y
sin `solo_ficha`. Con el orden viejo, ese candidato —el correcto— se demotaba,
un homónimo más débil ocupaba su lugar y la vía MEF terminaba evaluando a un
SUSTITUTO: el motivo de revisión citaba un CUI ajeno (auditoría 12-sep, casos
12:3 y 16:1).

Ahora `ranked[0]` de origen 'mef' pasa PRIMERO por los candados PROPIOS de la
vía MEF (nombre oficial ≥ 95, cobertura ≥ 80 %, sin contradicción de ubicación,
sin rubro ajeno, sin ficha rival). Si no los supera, se demota exactamente como
antes. Ningún umbral se mueve y el camino B (obras) no cambia — el caso
Chinchinga de `test_resolucion_fusion.py` sigue verde sin tocarse.

CUI y nombres INVENTADOS: el repo es público.
"""
from __future__ import annotations

from resolucion.cui import CLAVE_TIPO_EVALUACION, resolver

CUI_BUENO = "2011111"
CUI_RIVAL = "2022222"

NOMBRE_OFICIAL = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD "
                  "VILLA SOLAR, DISTRITO Y PROVINCIA DE PAMPACRUZ, DEPARTAMENTO DE LORETO")
NOMBRE_RIVAL = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL PUESTO DE SALUD MIRADOR ALTO, "
                "DISTRITO DE MIRADOR, PROVINCIA DE PAMPACRUZ, DEPARTAMENTO DE LORETO")
PROYECTO = ("Elaboración del Expediente Técnico del proyecto: MEJORAMIENTO DE LOS "
            "SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD VILLA SOLAR, DISTRITO Y "
            "PROVINCIA DE PAMPACRUZ, DEPARTAMENTO DE LORETO")
UBICACION = "Distrito y Provincia de Pampacruz, Departamento de Loreto"
OBRA_ID_BUENO = "OB-90001"


def _ficha(cui, nombre, score, dpto="LORETO", prov="PAMPACRUZ", dist="VILLA SOLAR"):
    return {"cui": cui, "snip": "", "nombre": nombre, "ubigeo": "", "dpto": dpto,
            "prov": prov, "dist": dist, "entidad": "GOBIERNO REGIONAL LORETO",
            "estado_dataset": "ACTIVO", "situacion": "", "score": score}


def _registro(cui, nombre, obra_id, dpto="LORETO"):
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id,
            "nombrObra": nombre, "nombrDepartamento": dpto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


class _Base:
    def __init__(self, fichas):
        self.fichas = list(fichas)

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return list(self.fichas[:topn])

    def existe_cui(self, codigo):
        return next((f for f in self.fichas if f["cui"] == str(codigo)), None)


class _Consulta:
    """InfoObras devuelve por NOMBRE solo al rival; el proyecto bueno existe pero
    únicamente se alcanza por CÓDIGO (es el patrón que produce `origen == 'mef'`
    sin `solo_ficha`)."""

    def __init__(self, por_nombre, por_codigo):
        self._nombre = list(por_nombre)
        self._codigo = dict(por_codigo)

    def buscar(self, nombre):
        return [dict(o) for o in self._nombre]

    def por_codigo(self, codigo):
        return [dict(o) for o in self._codigo.get(str(codigo), [])]


def _exp(proyecto=PROYECTO, ubicacion=UBICACION, tipo="expedientes"):
    return {"proyecto": proyecto, "ubicacion": ubicacion,
            "entidad_emisora": "CONSULTORA DEL NORTE EIRL",
            "fecha_inicial": "2021-03-01", "fecha_final": "2021-11-30",
            CLAVE_TIPO_EVALUACION: tipo}


def _escenario(score_bueno=99.2, score_rival=88.0):
    base = _Base([_ficha(CUI_BUENO, NOMBRE_OFICIAL, score_bueno),
                  _ficha(CUI_RIVAL, NOMBRE_RIVAL, score_rival, dist="MIRADOR")])
    consulta = _Consulta(
        por_nombre=[_registro(CUI_RIVAL, NOMBRE_RIVAL, "OB-90002")],
        por_codigo={CUI_BUENO: [_registro(CUI_BUENO, NOMBRE_OFICIAL, OBRA_ID_BUENO)]})
    return base, consulta


def test_el_candidato_mef_del_expediente_se_evalua_antes_del_candado():
    """12:3 y 16:1 de la auditoría: el candidato correcto llega por la fusión (por
    CÓDIGO), el candado lo demotaba y ganaba un homónimo. Ahora resuelve por la
    vía MEF, que es la que tiene los candados propios."""
    base, consulta = _escenario()
    r = resolver(_exp(), consulta, base=base)
    assert r["estado"] == "resuelto", r
    assert r["via"] == "MEF" and r["cui"] == CUI_BUENO, r
    # el registro de InfoObras existe (llegó por código): su obra_id se conserva
    assert r["obra"]["obra_id"] == OBRA_ID_BUENO, r


def test_nombre_oficial_por_debajo_del_umbral_sigue_demotado():
    """El orden cambia; los candados NO. Con el nombre oficial flojo (< 95) el
    candidato se demota igual que antes y la experiencia va a revisión con él
    visible."""
    base, consulta = _escenario(score_bueno=90.0)
    r = resolver(_exp(), consulta, base=base)
    assert r["estado"] != "resuelto", r
    assert any(c["cui"] == CUI_BUENO for c in r["candidatos"]), r


def test_una_ficha_rival_casi_igual_de_parecida_no_resuelve():
    """El candado de rival de la vía MEF (`_DELTA_RIVAL_MEF`) manda: dos fichas a
    menos de 3 puntos de score MEF son un empate, no una identificación."""
    base, consulta = _escenario(score_bueno=99.2, score_rival=98.0)
    r = resolver(_exp(), consulta, base=base)
    assert r["estado"] != "resuelto", r


def test_para_una_obra_el_candado_sigue_intacto():
    """Camino B: la vía MEF no existe y el candado de ADR-005 §1 demota como
    siempre (es el patrón del caso Chinchinga, que no se toca)."""
    base, consulta = _escenario()
    exp = _exp(proyecto="Supervisión de la obra: " + NOMBRE_OFICIAL, tipo="obras")
    r = resolver(exp, consulta, base=base)
    assert not (r["estado"] == "resuelto" and r.get("cui") == CUI_BUENO), r
