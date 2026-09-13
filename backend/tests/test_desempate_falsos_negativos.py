"""
Tests offline del DESEMPATE del resolver de CUI — los falsos negativos que
detectó la auditoría visual de certificados del 12-sep-2026.

Cada bloque ataca UNA causa y trae su caso POSITIVO (la señal existe y desempata)
y su caso NEGATIVO (la señal no alcanza y la experiencia sigue en revisión). El
negativo es la mitad importante: abstenerse cuesta minutos de un evaluador, y
resolver mal cuesta el producto (ADR-005).

Los CUI y los nombres son INVENTADOS. La auditoría lleva datos de un cliente y
vive fuera del repo; lo que se versiona acá es la FORMA del caso, no el caso.
"""
from __future__ import annotations

import re

import pytest

from resolucion.cui import (fase_de, nombre_literal, resolver, resolver_con_dedup,
                           ubigeo_cert, _mismo_proyecto, _ubigeo_coincide)


# ── dobles de prueba ─────────────────────────────────────────────────────────

class FakeBase:
    """Base MEF de juguete: fichas por CUI, con ubicación y entidad."""

    def __init__(self, fichas: dict):
        self.fichas = fichas

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return []                     # sin fusión: los candidatos vienen del portal

    def existe_cui(self, codigo):
        return self.fichas.get(re.sub(r"\D", "", str(codigo or "")))

    def es_entidad_publica(self, nombre):
        return (True, nombre)


class ConsultaFalsa:
    """InfoObras falso: `buscar` devuelve siempre el mismo pool; `por_codigo`
    filtra por CUI (así el checkpoint de fase ve a los hermanos del CUI)."""

    def __init__(self, obras):
        self.obras = list(obras)

    def buscar(self, nombre):
        return list(self.obras)

    def por_codigo(self, codigo):
        c = re.sub(r"\D", "", str(codigo or ""))
        return [o for o in self.obras
                if re.sub(r"\D", "", str(o["codUniqInv"])) == c]


def _obra(cui, obra_id, nombre, depto="ANCASH"):
    return {"codUniqInv": cui, "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


def _ficha(cui, nombre, dpto="ANCASH", prov="", dist="", entidad="GOBIERNO REGIONAL X"):
    return {"cui": cui, "snip": "", "nombre": nombre, "dpto": dpto, "prov": prov,
            "dist": dist, "entidad": entidad, "ubigeo": "", "situacion": "",
            "estado_dataset": "ACTIVO"}


# ═══ CAUSA 1 · la ubicación que el propio certificado declara ════════════════
#
# El campo `ubicacion` del certificado escribe el rótulo SIN «de» («Distrito
# Villa Nueva de Tinsaca»), y el lector de ubigeo exigía el «de»: la provincia y
# el distrito quedaban sin declarar y la coincidencia positiva con la ficha del
# MEF no existía para el resolver.

def test_distrito_con_rotulo_sin_de_se_lee():
    """POSITIVO · «Distrito Villa Nueva de Tinsaca» declara ese distrito."""
    sig = ubigeo_cert({"proyecto": "MEJORAMIENTO DEL PUESTO DE SALUD TINSACA",
                       "ubicacion": "Av. Los Sauces S/N, Distrito Villa Nueva de "
                                    "Tinsaca, Provincia Quenua, Departamento de Ancash"})
    assert "VILLA NUEVA DE TINSACA" in sig["dist"], sig
    assert "QUENUA" in sig["prov"], sig
    assert "ANCASH" in sig["depto_declarado"], sig


def test_ubigeo_coincide_por_termino_de_ubicacion_sin_rotulo():
    """POSITIVO · el certificado da «Villa Rica - Quenua» sin la palabra
    «provincia»; la provincia oficial del MEF es QUENUA → coincidencia real."""
    sig = ubigeo_cert({"proyecto": "CONSTRUCCION DEL HOSPITAL VILLA RICA",
                       "ubicacion": "Villa Rica - Quenua"})
    assert not sig["prov"] and not sig["dist"]          # sin rótulo, no hay nivel
    assert _ubigeo_coincide(sig, _ficha("1234567", "X", prov="QUENUA"))


def test_ubigeo_coincide_no_cuenta_el_departamento():
    """NEGATIVO · la provincia del MEF se llama igual que el DEPARTAMENTO que
    declara el certificado: ADR-005 midió que eso no desempata homónimos."""
    sig = ubigeo_cert({"proyecto": "CONSTRUCCION DEL HOSPITAL DE TACNA",
                       "ubicacion": "Tacna, Departamento de Tacna"})
    assert not _ubigeo_coincide(sig, _ficha("1234567", "X", dpto="TACNA", prov="TACNA"))


# ═══ CAUSA 2 · la fase SALDO del certificado ═════════════════════════════════
#
# InfoObras rotula el saldo de una obra como «… - SALDO DE OBRA PRINCIPAL». Con
# PRINCIPAL evaluado antes que SALDO ese registro se clasificaba PRINCIPAL, y el
# resolver mandaba a revisión diciendo que el CUI «no muestra un registro de
# SALDO» cuando el registro estaba ahí.

def test_saldo_de_obra_principal_es_saldo():
    """POSITIVO · unidad: el rótulo compuesto se clasifica SALDO."""
    assert fase_de("MEJORAMIENTO DEL HOSPITAL QUENUA - SALDO DE OBRA PRINCIPAL") == "SALDO"
    assert fase_de("MEJORAMIENTO DEL HOSPITAL QUENUA - OBRA PRINCIPAL") == "PRINCIPAL"
    assert fase_de("MEJORAMIENTO DEL HOSPITAL QUENUA") is None


_CERT_SALDO = ("Elaboracion del Expediente Tecnico de Saldo de Obra: MEJORAMIENTO "
               "Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL HOSPITAL QUENUA, "
               "DISTRITO DE SAN ELOY, PROVINCIA DE QUENUA Y DEPARTAMENTO DE ANCASH")


def test_certificado_de_saldo_toma_el_registro_de_saldo_del_cui():
    """POSITIVO · el CUI tiene tres registros y uno es el SALDO: se resuelve con
    ese, no se manda a revisión."""
    nom = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL HOSPITAL "
           "QUENUA, DISTRITO DE SAN ELOY, PROVINCIA DE QUENUA Y DEPARTAMENTO DE ANCASH")
    consulta = ConsultaFalsa([
        _obra("1470001", 9001, nom + " - OBRA PRINCIPAL"),
        _obra("1470001", 9002, nom),
        _obra("1470001", 9003, nom + " - SALDO DE OBRA PRINCIPAL"),
    ])
    r = resolver({"proyecto": _CERT_SALDO, "cui": "1470001"}, consulta)
    assert r["estado"] == "resuelto", r
    assert r["cui"] == "1470001", r
    assert "SALDO DE OBRA PRINCIPAL" in (r["obra"] or {})["nombre_obra"], r


def test_certificado_de_saldo_sin_registro_de_saldo_sigue_en_revision():
    """NEGATIVO · el CUI solo registra la obra principal: la abstención se queda."""
    nom = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL HOSPITAL "
           "QUENUA, DISTRITO DE SAN ELOY, PROVINCIA DE QUENUA Y DEPARTAMENTO DE ANCASH")
    consulta = ConsultaFalsa([_obra("1470001", 9001, nom + " - OBRA PRINCIPAL")])
    r = resolver({"proyecto": _CERT_SALDO, "cui": "1470001"}, consulta)
    assert r["estado"] == "revision", r
    assert "SALDO" in r["decision"], r


# ═══ CAUSA 5 · nombre literal del certificado como desempate ═════════════════
#
# El score de nombre mide parecido de vocabulario: da ~100 a dos nombres que
# comparten las palabras en cualquier orden. El guard de empate pide una señal
# DURA que separe a los candidatos, y «el nombre del certificado, palabra por
# palabra, está en UN SOLO candidato» es exactamente esa señal.

def test_nombre_literal_unidad():
    cert = ("Elaboracion del Expediente Tecnico del Proyecto: MEJORAMIENTO DE LOS "
            "SERVICIOS DE SALUD EN EL HOSPITAL QUENUA, PROVINCIA DE QUENUA")
    # el nombre oficial contiene al del certificado palabra por palabra
    assert nombre_literal(cert, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                                "HOSPITAL QUENUA, PROVINCIA DE QUENUA-REGION ANCASH")
    # otro proyecto del mismo departamento: comparte vocabulario, no el nombre
    assert not nombre_literal(cert, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                                    "HOSPITAL TINSACA, PROVINCIA DE TINSACA-REGION ANCASH")
    # un rótulo de tres palabras no es un nombre
    assert not nombre_literal("HOSPITAL DE ESSALUD", "HOSPITAL DE ESSALUD DE QUENUA")


_CERT_LIT = ("Expediente Tecnico del proyecto denominado: Mejoramiento de los "
             "Servicios de Salud en el Hospital de Quenua, en la Provincia de "
             "Quenua - Ancash")


def test_nombre_literal_unico_desempata_el_guard_de_empate():
    """POSITIVO · dos candidatos a menos de 4 puntos; el nombre del certificado
    está literalmente en uno solo → se resuelve ese, con los dos visibles."""
    consulta = ConsultaFalsa([
        # score 100 · el nombre del certificado, palabra por palabra
        _obra("1470010", 9001, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                               "HOSPITAL DE QUENUA, EN LA PROVINCIA DE QUENUA - ANCASH"),
        # score ~97 · otro establecimiento (el hospital RURAL), a menos de 4 puntos
        _obra("1470011", 9002, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                               "HOSPITAL RURAL DE QUENUA, EN LA PROVINCIA DE "
                               "QUENUA - ANCASH"),
    ])
    r = resolver({"proyecto": _CERT_LIT}, consulta)
    assert r["estado"] == "resuelto", r
    assert r["cui"] == "1470010", r
    assert {c["cui"] for c in r["candidatos"]} == {"1470010", "1470011"}, r


def test_dos_candidatos_con_el_mismo_nombre_literal_siguen_en_revision():
    """NEGATIVO · el Estado registra inversiones DISTINTAS cuyos nombres contienen
    los dos, palabra por palabra, el del certificado («Hospital Quenua» y
    «Hospital Quenua II»). Dos nombres literales no separan nada: la UNICIDAD es la
    garantía del desempate, y sin ella la experiencia sigue en revisión."""
    consulta = ConsultaFalsa([
        _obra("1470010", 9001, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                               "HOSPITAL DE QUENUA, EN LA PROVINCIA DE QUENUA - ANCASH"),
        _obra("1470012", 9002, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL "
                               "HOSPITAL QUENUA II DE LA PROVINCIA DE QUENUA - ANCASH"),
    ])
    r = resolver({"proyecto": _CERT_LIT}, consulta)
    assert r["estado"] == "revision", r
    assert r["cui"] is None, r


def test_homonimo_en_otra_provincia_sigue_en_revision():
    """NEGATIVO · un homónimo real en OTRA provincia, con el mismo nombre literal
    que el certificado: el veto de ubicación lo aparta y el guard deja la
    experiencia en revisión con los dos a la vista. La señal de nombre literal no
    puede pasar por encima de una contradicción de ubicación."""
    nom = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL HOSPITAL DE QUENUA, EN "
           "LA PROVINCIA DE QUENUA - ANCASH")
    base = FakeBase({
        "1470010": _ficha("1470010", nom, prov="QUENUA", dist="QUENUA"),
        "1470013": _ficha("1470013", nom, prov="TINSACA", dist="TINSACA"),
    })
    consulta = ConsultaFalsa([_obra("1470010", 9001, nom),
                              _obra("1470013", 9002, nom)])
    r = resolver({"proyecto": _CERT_LIT,
                  "ubicacion": "Provincia de Quenua - Ancash"}, consulta, base=base)
    assert r["estado"] == "revision", r
    assert r["cui"] is None, r


# ═══ CAUSA 3 · consistencia dentro de la misma propuesta ═════════════════════
#
# La MISMA obra quedaba RESUELTA en una experiencia y PENDIENTE en otra del mismo
# expediente, con el candidato correcto a la vista en las dos.

_P1 = ("Supervision del Expediente Tecnico del Proyecto: MEJORAMIENTO DE LOS "
       "SERVICIOS DE SALUD DEL HOSPITAL II QUENUA DE LA RED ASISTENCIAL QUENUA "
       "EN EL DISTRITO DE SAN ELOY, PROVINCIA DE QUENUA")
_P2 = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL HOSPITAL II QUENUA DE LA RED "
       "ASISTENCIAL QUENUA EN EL DISTRITO DE SAN ELOY, PROVINCIA DE QUENUA")


def test_mismo_proyecto_unidad():
    assert _mismo_proyecto(_P1, _P2)
    assert not _mismo_proyecto(_P1, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL "
                                    "PUESTO DE SALUD TINSACA, DISTRITO DE TINSACA")


def _cands(*cuis):
    return [{"cui": c, "nombre_obra": "X", "departamento": "ANCASH", "score": 90}
            for c in cuis]


def test_la_misma_obra_no_queda_resuelta_en_una_y_pendiente_en_otra(monkeypatch):
    """POSITIVO · la hermana ya identificó la obra y el mismo CUI figura entre los
    candidatos de la pendiente → se hereda, vía DEDUP."""
    guiones = iter([
        {"estado": "resuelto", "cui": "1470020", "via": "NOMBRE", "decision": "ok",
         "candidatos": _cands("1470020"), "obra": {"cui": "1470020", "obra_id": 9001,
                                                   "nombre_obra": "X",
                                                   "departamento": "ANCASH"}},
        {"estado": "revision", "cui": None, "via": "NOMBRE", "decision": "dudo",
         "candidatos": _cands("1470020", "1470021"), "obra": None},
    ])
    monkeypatch.setattr("resolucion.cui.resolver", lambda *a, **k: next(guiones))
    out = dict(resolver_con_dedup([({"proyecto": _P2}, "1:2"),
                                   ({"proyecto": _P1}, "2:2")], None))
    assert out["2:2"]["estado"] == "resuelto", out["2:2"]
    assert out["2:2"]["cui"] == "1470020", out["2:2"]
    assert out["2:2"]["via"] == "DEDUP", out["2:2"]


def test_no_se_hereda_un_cui_que_la_pendiente_nunca_vio(monkeypatch):
    """NEGATIVO · misma obra, pero el CUI resuelto NO está entre los candidatos de
    la pendiente: heredarlo sería inventarle una obra que su búsqueda no encontró."""
    guiones = iter([
        {"estado": "resuelto", "cui": "1470020", "via": "NOMBRE", "decision": "ok",
         "candidatos": _cands("1470020"), "obra": None},
        {"estado": "revision", "cui": None, "via": "NOMBRE", "decision": "dudo",
         "candidatos": _cands("1470021", "1470022"), "obra": None},
    ])
    monkeypatch.setattr("resolucion.cui.resolver", lambda *a, **k: next(guiones))
    out = dict(resolver_con_dedup([({"proyecto": _P2}, "1:2"),
                                   ({"proyecto": _P1}, "2:2")], None))
    assert out["2:2"]["estado"] == "revision", out["2:2"]


def test_no_se_hereda_entre_proyectos_distintos(monkeypatch):
    """NEGATIVO · dos obras distintas que comparten el prefijo genérico: el CUI
    resuelto está entre los candidatos de la otra, pero no es la misma obra."""
    otra = ("MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL PUESTO DE SALUD TINSACA, "
            "DISTRITO DE TINSACA, PROVINCIA DE QUENUA")
    guiones = iter([
        {"estado": "resuelto", "cui": "1470020", "via": "NOMBRE", "decision": "ok",
         "candidatos": _cands("1470020"), "obra": None},
        {"estado": "revision", "cui": None, "via": "NOMBRE", "decision": "dudo",
         "candidatos": _cands("1470020", "1470021"), "obra": None},
    ])
    monkeypatch.setattr("resolucion.cui.resolver", lambda *a, **k: next(guiones))
    out = dict(resolver_con_dedup([({"proyecto": _P2}, "1:2"),
                                   ({"proyecto": otra}, "2:2")], None))
    assert out["2:2"]["estado"] == "revision", out["2:2"]


# ═══ CAUSA 4 · el motivo de revisión no puede citar un candidato ajeno ═══════

def test_el_motivo_de_la_via_mef_nombra_al_candidato_de_mayor_puntaje():
    """El candado de ADR-005 §1 puede demotar al candidato de mayor puntaje y
    dejar como `best` a una ficha más débil; el motivo presentaba ESA ficha como
    «el proyecto con ese nombre» y el evaluador leía un CUI que no reconocía.
    Ahora el mensaje nombra también al candidato de mayor puntaje y dice por qué
    se apartó."""
    from resolucion.cui import _via_mef_expediente
    ranked = [{"cui": "1470030", "score": 120.0, "nombre_obra": "OBRA FUERTE",
               "mef_score": 100.0},
              {"cui": "1470031", "score": 91.0, "nombre_obra": "OTRA COSA",
               "mef_score": 80.0}]
    r = _via_mef_expediente({"proyecto": "Elaboracion del Expediente Tecnico del "
                                         "Hospital Quenua"},
                            ranked[1], ranked, [], None, False)
    assert r["estado"] == "revision", r
    assert "1470031" in r["decision"], r
    assert "1470030" in r["decision"], r          # el de mayor puntaje, nombrado


@pytest.mark.parametrize("texto,esperado", [
    ("distrito de San Eloy, provincia de Quenua", ("SAN ELOY", "QUENUA")),
    ("Distrito San Eloy, Provincia Quenua", ("SAN ELOY", "QUENUA")),
    ("distrito y provincia de Quenua", (None, "QUENUA")),
])
def test_lectura_de_rotulos_geograficos(texto, esperado):
    """La opcionalidad del «de» no puede inventar niveles: en «distrito y
    provincia de Quenua» el distrito queda SIN declarar (el enganche vacío se
    descarta por largo), que es lo correcto — no se infiere."""
    sig = ubigeo_cert({"proyecto": "MEJORAMIENTO DEL HOSPITAL", "ubicacion": texto})
    dist, prov = esperado
    if dist:
        assert dist in sig["dist"], sig
    else:
        assert not any(len(d) > 2 for d in sig["dist"]), sig
    assert prov in sig["prov"], sig
