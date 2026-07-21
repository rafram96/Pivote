"""
Tests offline de la FUSIÓN base MEF ↔ resolver de CUI (F3). Sin red.

Cablea la costura `base` en el resolver:
  A1 · CUI citado que solo existe en el MEF → pista en el motivo de revisión.
  A2 · fusión: rescatar por `por_codigo` los CUIs que el MEF sugiere y InfoObras
       no trajo por nombre (tope de 5 fetches, PortalNoResponde por candidato).
  A3 · señales de identidad (nombre oficial, dpto, entidad) en el scoring.

La equivalencia con `base=None` la cubren los tests de test_resolucion_cui.py
(siguen verdes sin tocarse); aquí se añade una verificación explícita de la forma.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from resolucion.base_mef import BaseMef, instancia
from resolucion.cui import _bonus_mef, norm, resolver

FIX = Path(__file__).parent / "fixtures" / "mef"


@pytest.fixture
def base_real(tmp_path) -> BaseMef:
    """BaseMef sobre una copia de los fixtures mini con los nombres canónicos."""
    shutil.copy(FIX / "mef_mini.csv.gz", tmp_path / "inversiones.csv.gz")
    shutil.copy(FIX / "entidades_mini.csv", tmp_path / "entidades_publicas.csv")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"fecha": date.today().isoformat(), "cuis_distintos": 23}),
        encoding="utf-8")
    return instancia(dir_base=tmp_path)


# ── dobles de prueba ─────────────────────────────────────────────────────────

class FakeBase:
    """Base MEF de juguete: candidatos y fichas controlados (para medir umbrales
    y contar fetches sin depender del scoring real de rapidfuzz)."""

    def __init__(self, candidatos, fichas=None):
        self.candidatos = list(candidatos)
        self.fichas = fichas or {}

    def disponible(self):
        return True

    def buscar_candidatos(self, nombre, topn=10):
        return list(self.candidatos[:topn])

    def existe_cui(self, codigo):
        return self.fichas.get(re.sub(r"\D", "", str(codigo or "")))


class _Consulta:
    """InfoObras falso: `buscar` no trae nada (fuerza la fusión), `por_codigo`
    devuelve lo que dicta `por_cod` y CUENTA las llamadas."""

    def __init__(self, por_cod=None):
        self.por_cod = por_cod or {}
        self.llamadas: list[str] = []

    def por_codigo(self, codigo):
        self.llamadas.append(str(codigo))
        v = self.por_cod.get(str(codigo))
        if isinstance(v, Exception):
            raise v
        return list(v or [])

    def buscar(self, nombre):
        return []


def _obra(cui, obra_id, nombre, depto="LIMA"):
    return {"codUniqInv": cui, "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None,
            "rucEjecutor": "", "rucSupervisor": ""}


def _mef_cand(cui, nombre, score, dpto="LIMA", entidad="GOBIERNO REGIONAL"):
    return {"cui": cui, "snip": "", "nombre": nombre, "score": score,
            "dpto": dpto, "entidad": entidad, "ubigeo": "", "prov": "", "dist": "",
            "situacion": "", "estado_dataset": "ACTIVO"}


# ── A2 · Chinchinga: nombre corrupto en InfoObras, rescatado por el MEF ───────

def test_chinchinga_fusion_rescata_por_codigo(base_real):
    """InfoObras solo trae basura por nombre; el CUI correcto (salud) existe en el
    MEF. La fusión lo trae por `por_codigo` y, con el nombre oficial del MEF, resuelve
    al CUI correcto marcado origen 'mef'."""
    proyecto = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DEL PUESTO DE SALUD DEL "
                "CENTRO POBLADO DE CHINCHINGA DEL DISTRITO DE SAN PABLO DE PILLAO - "
                "PROVINCIA DE HUANUCO")
    # por_codigo del CUI correcto devuelve un registro con NOMBRE CORRUPTO
    consulta = _Consulta(por_cod={
        "2376130": [_obra("2376130", 55, "REGISTRO SIN NOMBRE 44821", depto="HUANUCO")]})
    r = resolver({"proyecto": proyecto}, consulta, base=base_real)
    assert r["estado"] == "resuelto", r
    assert r["cui"] == "2376130", r
    assert any(c.get("origen") == "mef" for c in r["candidatos"]), r


# ── A2 · umbral de score: candidato débil NO dispara fetch ───────────────────

def test_candidato_bajo_score_no_dispara_fetch():
    base = FakeBase([_mef_cand("2000070", "OBRA DEBIL", 70)])   # 70 < 75
    consulta = _Consulta()
    r = resolver({"proyecto": "algo que no matchea nada"}, consulta, base=base)
    assert consulta.llamadas == []      # jamás se fetcheó por código
    assert r["estado"] == "revision"


# ── A2 · tope de 5 fetches por experiencia ───────────────────────────────────

def test_tope_de_cinco_fetches():
    cands = [_mef_cand(f"200000{i}", f"OBRA {i}", 80) for i in range(8)]  # 8 ≥ 75
    base = FakeBase(cands)
    consulta = _Consulta()                    # por_codigo devuelve [] para todos
    resolver({"proyecto": "consulta cualquiera"}, consulta, base=base)
    assert len(consulta.llamadas) == 5        # cap de 5, aunque haya 8 candidatos


# ── A2 · PortalNoResponde por candidato → se descarta ese, la experiencia sigue ─

def test_portal_no_responde_en_un_fetch_no_rompe():
    from resolucion.cui import PortalNoResponde
    base = FakeBase([
        _mef_cand("2000001", "OBRA UNO", 90),
        _mef_cand("2200145", "CREACION DEL HOSPITAL REGIONAL DE LIRCAY", 88,
                  dpto="HUANCAVELICA")])
    consulta = _Consulta(por_cod={
        "2000001": PortalNoResponde("caída"),        # este candidato revienta
        "2200145": [_obra("2200145", 70,
                          "CREACION DEL HOSPITAL REGIONAL DE LIRCAY", "HUANCAVELICA")]})
    exp = {"proyecto": "Creación del Hospital Regional de Lircay, Huancavelica"}
    r = resolver(exp, consulta, base=base)     # no debe lanzar
    assert set(consulta.llamadas) == {"2000001", "2200145"}   # ambos intentados
    assert r["cui"] == "2200145", r            # el bueno resolvió pese a la caída


# ── A3 · señal de entidad: +15 solo con match ≥ 90 ───────────────────────────

def test_senal_entidad_suma_solo_con_match_alto():
    cand = {"nombrObra": "X", "nombrDepartamento": ""}
    ficha = {"nombre": "X", "dpto": "", "entidad": "GOBIERNO REGIONAL DE HUANUCO"}
    fichas = {"1": ficha}
    b_ok = _bonus_mef(cand, "1", {"entidad_contratante": "Gobierno Regional de Huánuco"},
                      None, fichas, norm("X"), set())
    b_no = _bonus_mef(cand, "1", {"entidad_contratante": "Municipalidad de Lima"},
                      None, fichas, norm("X"), set())
    assert b_ok == 15.0        # entidad idéntica → +15
    assert b_no == 0.0         # entidad distinta → no suma (ni resta)


def test_senal_dpto_extra_solo_si_ambos_contradicen():
    # dpto MEF coincide con hint → +10
    cand = {"nombrObra": "X", "nombrDepartamento": "LIMA"}
    ficha = {"nombre": "X", "dpto": "HUANUCO", "entidad": ""}
    mas = _bonus_mef(cand, "1", {}, None, {"1": ficha}, norm("X"), {"HUANUCO"})
    assert mas == 10.0
    # InfoObras (LIMA) Y MEF (LIMA) contradicen el hint HUANUCO → −10 extra
    ficha2 = {"nombre": "X", "dpto": "LIMA", "entidad": ""}
    menos = _bonus_mef(cand, "1", {}, None, {"1": ficha2}, norm("X"), {"HUANUCO"})
    assert menos == -10.0


# ── A1 · CUI citado que solo existe en el MEF → pista en revisión ─────────────

def test_cui_citado_solo_en_mef_agrega_pista(base_real):
    """El certificado cita un CUI que InfoObras no tiene, pero el MEF sí. No se
    resuelve por ello (InfoObras es la fuente del cruce), pero el nombre oficial del
    MEF aparece como pista en el motivo de la revisión."""
    exp = {"cui": "2376130",
           "proyecto": "Supervisión de una obra sin nombre reconocible ZZZ"}
    consulta = _Consulta()          # por_codigo del CUI citado → [] (no está en InfoObras)
    r = resolver(exp, consulta, base=base_real)
    assert r["estado"] == "revision", r
    assert "CHINCHINGA" in (r["decision"] or ""), r["decision"]


# ── base=None: forma IDÉNTICA a la histórica (sin 'origen', sin pista) ────────

def test_base_none_no_agrega_origen_ni_pista():
    consulta_con = _Consulta()

    class _ConNombre:
        def por_codigo(self, c):
            return []

        def buscar(self, n):
            return [_obra("2777777", 7,
                          "MEJORAMIENTO DE LA INFRAESTRUCTURA EDUCATIVA KREAR, "
                          "DISTRITO DE TRUJILLO", "LA LIBERTAD")]

    exp = {"proyecto": "Mejoramiento de la Infraestructura Educativa 'KREAR', "
                       "Distrito de Trujillo - La Libertad", "fecha_inicial": "2018-06-01"}
    r = resolver(exp, _ConNombre(), base=None)
    assert r["estado"] == "resuelto" and r["cui"] == "2777777"
    # sin base: los candidatos NO llevan 'origen' (contrato idéntico al histórico)
    assert all("origen" not in c for c in r["candidatos"]), r
