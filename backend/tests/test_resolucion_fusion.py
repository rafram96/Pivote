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

def test_chinchinga_fusion_rescata_pero_no_resuelve_sin_corroborar(base_real):
    """CANDADO MEF (F7): InfoObras solo trae basura por nombre; el CUI correcto
    existe en el MEF y la fusión lo TRAE por `por_codigo` (queda VISIBLE en la cola
    de revisión, origen 'mef'), pero un candidato que SOLO existe por la fusión NO
    puede GANAR por puro score de nombre — sin señal dura (RUC / N° de institución /
    entidad) va a REVISIÓN, no se auto-resuelve. Esto ataca los homónimos estatales
    de nombre limpio que inflaban el score (diagnóstico F7)."""
    proyecto = ("MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DEL PUESTO DE SALUD DEL "
                "CENTRO POBLADO DE CHINCHINGA DEL DISTRITO DE SAN PABLO DE PILLAO - "
                "PROVINCIA DE HUANUCO")
    consulta = _Consulta(por_cod={
        "2376130": [_obra("2376130", 55, "REGISTRO SIN NOMBRE 44821", depto="HUANUCO")]})
    r = resolver({"proyecto": proyecto}, consulta, base=base_real)
    assert r["estado"] == "revision", r          # no resuelve sin corroboración
    assert r["cui"] is None, r
    # pero el candidato rescatado por la fusión SIGUE visible para el humano
    assert any(c.get("cui") == "2376130" and c.get("origen") == "mef"
               for c in r["candidatos"]), r


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
    # la caída de un fetch no rompe: el otro candidato mef se recolecta y queda
    # VISIBLE. Sin corroboración no gana (candado F7), pero la experiencia no crashea.
    assert any(c.get("cui") == "2200145" for c in r["candidatos"]), r


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


# ── F5 · público-primero: candado de entidad + clasificación de privada al final ──

def _fake_por_nombre(obras):
    """InfoObras falso: `buscar` devuelve `obras`, `por_codigo` nada (fuerza el
    PASO 2 por nombre para ejercitar las compuertas de _compuertas)."""
    class _C:
        def por_codigo(self, c): return []
        def buscar(self, n): return list(obras)
    return _C()


# proyecto con 3 tokens distintivos (ALFA/BETA/GAMMA); la obra comparte SOLO ALFA
# (n_hit=1) pero es muy similar en texto (score ≥ 90) → cae en la rama PROBABLE,
# el único punto donde actúa el candado de entidad. La obra es de salud → el rubro
# no la veta.
_PROY_PROBABLE = "MEJORAMIENTO DEL HOSPITAL REGIONAL ALFA BETA GAMMA DE ICA"
_OBRA_PROBABLE = _obra("2000001", 5, "MEJORAMIENTO DEL HOSPITAL REGIONAL ALFA DE ICA",
                       depto="ICA")


def test_candado_probable_no_bloquea_entidad_publica(base_real):
    """(2) El candado de entidad NO degrada un PROBABLE cuya entidad contratante SÍ
    se reconoce como pública (INEN / IMARPE están en las fixtures mini)."""
    for entidad in ("INSTITUTO NACIONAL DE ENFERMEDADES NEOPLASICAS - INEN", "IMARPE"):
        exp = {"proyecto": _PROY_PROBABLE, "fecha_inicial": "2020-01-01",
               "entidad_contratante": entidad}
        r = resolver(exp, _fake_por_nombre([_OBRA_PROBABLE]), base=base_real)
        assert r["estado"] == "resuelto" and r["via"] == "PROBABLE", (entidad, r)
        assert r["cui"] == "2000001"
        assert "posible_privada" not in r


def test_candado_probable_degrada_entidad_no_reconocida(base_real):
    """(4) Un candidato fuerte por nombre cuya entidad contratante NO se reconoce
    como pública (una S.A.C.) se degrada de PROBABLE a revisión — sin resolver."""
    exp = {"proyecto": _PROY_PROBABLE, "fecha_inicial": "2020-01-01",
           "entidad_contratante": "CONSTRUCTORA ALFA BETA S.A.C."}
    r = resolver(exp, _fake_por_nombre([_OBRA_PROBABLE]), base=base_real)
    assert r["estado"] == "revision", r
    assert r["cui"] is None
    assert "no se reconoce como pública" in r["decision"]
    # los candidatos siguen visibles para el humano
    assert any(c["cui"] == "2000001" for c in r["candidatos"]), r


def test_candado_probable_inerte_sin_base():
    """(3) Sin base (base=None) el candado es INERTE: el mismo PROBABLE resuelve, y
    la clasificación de privada solo puede ser léxica (comportamiento como hoy salvo
    el orden — la búsqueda ya ocurrió)."""
    exp = {"proyecto": _PROY_PROBABLE, "fecha_inicial": "2020-01-01",
           "entidad_contratante": "CONSTRUCTORA ALFA BETA S.A.C."}
    r = resolver(exp, _fake_por_nombre([_OBRA_PROBABLE]), base=None)
    assert r["estado"] == "resuelto" and r["via"] == "PROBABLE", r
    assert r["cui"] == "2000001"
    # sin base, una experiencia sin señal léxica y sin match NO es posible_privada:
    # cae a la revisión normal "sin candidato fiable".
    r2 = resolver({"proyecto": "Construccion del local comunal de Santa Rosa",
                   "entidad_contratante": "ORDEN DE SAN AGUSTIN"},
                  _fake_por_nombre([]), base=None)
    assert r2["estado"] == "revision" and "posible_privada" not in r2, r2
    assert "sin candidato fiable" in r2["decision"]


def test_posible_privada_entidad_no_publica(base_real):
    """(1) Experiencia SIN señal léxica de privada, SIN match público y con entidad
    contratante no reconocida como pública ('ORDEN DE SAN AGUSTIN', score 82 < 90)
    → revisión con `posible_privada=True` y el motivo nuevo."""
    exp = {"proyecto": "Construccion del local comunal de Santa Rosa",
           "entidad_contratante": "ORDEN DE SAN AGUSTIN"}
    r = resolver(exp, _fake_por_nombre([]), base=base_real)
    assert r["estado"] == "revision" and r["via"] == "NOMBRE", r
    assert r.get("posible_privada") is True, r
    assert "no se reconoce como pública" in r["decision"]
    assert "posible obra privada" in r["decision"]


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


# ── F7 · CANDADO MEF: solo-mef gana SOLO con corroboración dura ───────────────

def test_mef_con_num_de_institucion_si_resuelve():
    """Un candidato de origen 'mef' (solo la fusión lo trajo) SÍ resuelve cuando una
    señal DURA lo corrobora: aquí el N° de I.E. del certificado también está en el
    nombre de la obra que trajo `por_codigo`. Es el contrapunto del candado."""
    base = FakeBase([_mef_cand("2000050", "IE 1234 SANTA ROSA", 90, dpto="TACNA")])
    consulta = _Consulta(por_cod={"2000050": [_obra(
        "2000050", 9, "MEJORAMIENTO DE LA I.E. N 1234 SANTA ROSA DE TACNA", "TACNA")]})
    exp = {"proyecto": "Mejoramiento de la I.E. N° 1234 Santa Rosa de Tacna",
           "fecha_inicial": "2019-01-01"}
    r = resolver(exp, consulta, base=base)
    assert r["estado"] == "resuelto" and r["cui"] == "2000050", r
    assert any(c.get("origen") == "mef" for c in r["candidatos"]), r


def test_mef_con_ruc_del_emisor_si_resuelve():
    """Otra corroboración dura: el RUC del emisor es ejecutor/supervisor de la obra
    mef → resuelve vía RUC pese a venir solo de la fusión."""
    base = FakeBase([_mef_cand("2000060", "OBRA X", 88, dpto="TACNA")])
    obra = _obra("2000060", 9, "REGISTRO SIN NOMBRE 771", "TACNA")
    obra["rucEjecutor"] = "20123456789"
    consulta = _Consulta(por_cod={"2000060": [obra]})
    exp = {"proyecto": "Mejoramiento del servicio X de Tacna",
           "ruc_emisor": "20123456789", "fecha_inicial": "2019-01-01"}
    r = resolver(exp, consulta, base=base)
    assert r["estado"] == "resuelto" and r["via"] == "RUC" and r["cui"] == "2000060", r


# ── F7 · GUARD DE EMPATE entre CUIs distintos ────────────────────────────────

def _fake_lista(obras):
    class _C:
        def por_codigo(self, c): return []
        def buscar(self, n): return list(obras)
    return _C()


def test_empate_homonimos_sin_senal_abstiene():
    """Dos CUIs distintos con nombre casi idéntico, score ≈ igual y SIN señal que
    los separe → el guard de empate manda a REVISIÓN (no arriesga un CUI). Funciona
    sin base (base=None): el candado no depende del MEF."""
    obras = [_obra("2000010", 1, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL "
                   "HOSPITAL SANTA ROSA DE ICA", "ICA"),
             _obra("2000011", 2, "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL "
                   "HOSPITAL SANTA ROSA DE ICA", "ICA")]
    exp = {"proyecto": "Mejoramiento de los Servicios de Salud del Hospital "
                       "Santa Rosa de Ica", "fecha_inicial": "2019-01-01"}
    r = resolver(exp, _fake_lista(obras), base=None)
    assert r["estado"] == "revision" and r["cui"] is None, r
    assert "homónimos" in r["decision"], r["decision"]
    assert len(r["candidatos"]) >= 2, r          # ambos visibles para la cola humana


def test_empate_roto_por_numero_de_institucion_resuelve():
    """El mismo empate PERO una obra trae el N° de I.E. del certificado y la otra no:
    la señal dura rompe el empate → resuelve al candidato corroborado (no abstiene)."""
    obras = [_obra("2000020", 1, "MEJORAMIENTO DE LA I.E. N 555 SANTA ROSA DE ICA", "ICA"),
             _obra("2000021", 2, "MEJORAMIENTO DE LA I.E. N 999 SANTA ROSA DE ICA", "ICA")]
    exp = {"proyecto": "Mejoramiento de la I.E. N° 555 Santa Rosa de Ica",
           "fecha_inicial": "2019-01-01"}
    r = resolver(exp, _fake_lista(obras), base=None)
    assert r["estado"] == "resuelto" and r["cui"] == "2000020", r
