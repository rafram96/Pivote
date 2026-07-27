"""
Armado de casos de la línea base golden (`scripts/golden_cui.py`).

La golden armaba cada caso con solo `{proyecto, cui}` y fechas en None: toda
regla del resolver que lea ubicación, entidad contratante o RUC del emisor
quedaba INERTE, así que la red de seguridad principal del proyecto no validaba
la mitad de sus candados. Estos tests fijan el ENSANCHE: el caso se reconstruye
con la experiencia real del espejo del job, y cuando no se puede el caso degrada
y se CUENTA (un golden que miente sobre su cobertura es peor que uno pobre).

Todo offline: se fabrica un `datos_pivote` sintético en tmp_path.
"""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "scripts"))

import golden_cui as g  # noqa: E402


def _espejo(base: Path, job: str, experiencias: dict) -> None:
    """Escribe `<base>/<job>/espejo.json` con {(n_prof, n_exp): campos}."""
    profs: dict[int, list] = {}
    for (n_prof, n_exp), campos in experiencias.items():
        profs.setdefault(n_prof, []).append({"n": n_exp, **campos})
    d = {"profesionales": [{"n_prof": np_, "experiencias": exps}
                           for np_, exps in profs.items()]}
    (base / job).mkdir(parents=True, exist_ok=True)
    (base / job / "espejo.json").write_text(json.dumps(d, ensure_ascii=False),
                                            encoding="utf-8")


@pytest.fixture
def base_tmp(tmp_path, monkeypatch):
    """Apunta el módulo a un `datos_pivote` sintético y limpia su caché de espejos."""
    monkeypatch.setattr(g, "BASE", tmp_path)
    monkeypatch.setattr(g, "_ESPEJOS", {})
    return tmp_path


def _caso(**kw) -> dict:
    return {"proyecto": "OBRA X", "cui_verdad": "1234567", "cui_en_cert": "",
            "riesgo": "BAJO", "job": "job1", "prof_exp": "2:1",
            "ruc_auditoria": "", **kw}


# ── camino feliz ─────────────────────────────────────────────────────────────

def test_enriquece_con_la_experiencia_real_del_espejo(base_tmp):
    _espejo(base_tmp, "job1", {
        (2, 1): {"ubicacion": "Huancayo, Junín",
                 "entidad_contratante": "Municipalidad Distrital de San Agustín",
                 "entidad_emisora": "KG S.A.C.", "ruc_emisor": "20568720432",
                 "fecha_inicial": "2020-01-31", "fecha_final": "2020-12-10"},
        (2, 2): {"ubicacion": "OTRA QUE NO DEBE ENTRAR"},
    })
    caso = _caso()
    g._enriquecer(caso)
    assert caso["enriquecido"] is True
    assert caso["motivo_degradado"] is None
    assert caso["campos"]["ubicacion"] == "Huancayo, Junín"
    assert caso["campos"]["entidad_contratante"] == "Municipalidad Distrital de San Agustín"
    assert caso["campos"]["ruc_emisor"] == "20568720432"
    # las fechas reales entran: iban SIEMPRE en None y eso volvía inerte
    # `_elegir_obra` (desempate entre obras del mismo CUI)
    assert caso["campos"]["fecha_inicial"] == "2020-01-31"
    assert caso["campos"]["fecha_final"] == "2020-12-10"


def test_los_campos_vacios_no_entran(base_tmp):
    """Un campo vacío/None no debe entrar: `resolver` distingue ausente de "" en
    algunos candados, y meter "" sería inventar un dato que el cert no dio."""
    _espejo(base_tmp, "job1", {(2, 1): {"ubicacion": "Ica", "entidad_contratante": None,
                                        "entidad_emisora": "", "ruc_emisor": None}})
    caso = _caso()
    g._enriquecer(caso)
    assert caso["campos"] == {"ubicacion": "Ica"}


# ── degradación honesta ──────────────────────────────────────────────────────

def test_degrada_sin_espejo_en_disco(base_tmp):
    caso = _caso(job="job_inexistente")
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert caso["campos"] == {}
    assert "sin espejo legible" in caso["motivo_degradado"]


def test_degrada_con_espejo_corrupto(base_tmp):
    (base_tmp / "job1").mkdir()
    (base_tmp / "job1" / "espejo.json").write_text("{no es json", encoding="utf-8")
    caso = _caso()
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert "sin espejo legible" in caso["motivo_degradado"]


def test_degrada_con_prof_exp_ilegible(base_tmp):
    _espejo(base_tmp, "job1", {(2, 1): {"ubicacion": "Ica"}})
    caso = _caso(prof_exp="2:1 (multi)")
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert "prof:exp ilegible" in caso["motivo_degradado"]
    assert caso["campos"] == {}


def test_degrada_cuando_el_par_no_calza(base_tmp):
    _espejo(base_tmp, "job1", {(2, 1): {"ubicacion": "Ica"}})
    caso = _caso(prof_exp="9:9")
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert "no tiene la experiencia 9:9" in caso["motivo_degradado"]


def test_degrada_sin_job(base_tmp):
    caso = _caso(job="")
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert "no trae job" in caso["motivo_degradado"]


# ── respaldo del RUC (la auditoría lo trae en su col 9) ──────────────────────

def test_ruc_de_la_auditoria_rellena_cuando_el_espejo_no_lo_dio(base_tmp):
    _espejo(base_tmp, "job1", {(2, 1): {"ubicacion": "Ica"}})
    caso = _caso(ruc_auditoria="20100000001")
    g._enriquecer(caso)
    assert caso["campos"]["ruc_emisor"] == "20100000001"
    assert caso["enriquecido"] is True


def test_el_ruc_del_espejo_manda_sobre_el_de_la_auditoria(base_tmp):
    _espejo(base_tmp, "job1", {(2, 1): {"ruc_emisor": "20111111111"}})
    caso = _caso(ruc_auditoria="20999999999")
    g._enriquecer(caso)
    assert caso["campos"]["ruc_emisor"] == "20111111111"


def test_el_caso_degradado_conserva_el_ruc_de_la_auditoria(base_tmp):
    """Degradar no debe tirar el único dato que la auditoría sí tenía."""
    caso = _caso(job="no_existe", ruc_auditoria="20100000001")
    g._enriquecer(caso)
    assert caso["enriquecido"] is False
    assert caso["campos"] == {"ruc_emisor": "20100000001"}


# ── la exp que recibe el resolver ────────────────────────────────────────────

def test_proyecto_y_cui_mandan_sobre_lo_que_traiga_el_espejo(base_tmp, monkeypatch):
    """`proyecto` y `cui` son la IDENTIDAD del caso (anclan el emparejamiento con
    la baseline en `--comparar`): el ensanche no puede pisarlos."""
    from resolucion import cui as mod_cui
    vistas: list[dict] = []

    def _fake(exp, consulta, base=None):
        vistas.append(dict(exp))
        return {"estado": "revision", "cui": None, "via": "NOMBRE"}

    monkeypatch.setattr(mod_cui, "resolver", _fake)
    caso = _caso(cui_en_cert="2222222",
                 campos={"proyecto": "NOMBRE DEL ESPEJO", "cui": "9999999",
                         "ubicacion": "Ica"})
    g.resolver_caso(caso, consulta=SimpleNamespace())
    assert vistas[0]["proyecto"] == "OBRA X"
    assert vistas[0]["cui"] == "2222222"
    assert vistas[0]["ubicacion"] == "Ica"


def test_caso_degradado_conserva_las_fechas_en_none(base_tmp, monkeypatch):
    from resolucion import cui as mod_cui
    vistas: list[dict] = []
    monkeypatch.setattr(mod_cui, "resolver",
                        lambda exp, consulta, base=None: (vistas.append(dict(exp)),
                        {"estado": "revision", "cui": None, "via": "NOMBRE"})[1])
    caso = _caso(campos={})
    g.resolver_caso(caso, consulta=SimpleNamespace())
    assert vistas[0]["fecha_inicial"] is None
    assert vistas[0]["fecha_final"] is None


def test_cada_reintento_parte_de_una_exp_limpia(base_tmp, monkeypatch):
    """`resolver` escribe en la exp que recibe (`_ficha_mef_citado`, `_fichas_mef`):
    un reintento por portal caído no puede arrastrar el estado del intento previo."""
    from resolucion import cui as mod_cui
    vistas: list[dict] = []

    def _fake(exp, consulta, base=None):
        vistas.append(dict(exp))
        exp["_ficha_mef_citado"] = {"nombre": "sucio"}
        return {"estado": "revision", "cui": None, "via": "PORTAL"}

    monkeypatch.setattr(mod_cui, "resolver", _fake)
    monkeypatch.setattr(g.time, "sleep", lambda _s: None)
    caso = _caso(campos={"ubicacion": "Ica"})
    r = g.resolver_caso(caso, consulta=SimpleNamespace())
    assert r["estado"] == "portal_caido"
    assert len(vistas) == g.REINTENTOS_CASO + 1
    assert all("_ficha_mef_citado" not in v for v in vistas)


# ── el reporte declara su propia cobertura ───────────────────────────────────

def test_resumen_cobertura_cuenta_enriquecidos_y_degradados(base_tmp):
    _espejo(base_tmp, "job1", {(2, 1): {"ubicacion": "Ica", "ruc_emisor": "20100000001"}})
    casos = [_caso(), _caso(job="no_existe"), _caso(prof_exp="9:9")]
    for c in casos:
        g._enriquecer(c)
    cob = g.resumen_cobertura(casos)
    assert cob["total"] == 3
    assert cob["enriquecidos"] == 1
    assert cob["degradados"] == 2
    assert cob["campos_no_vacios"]["ubicacion"] == 1
    assert cob["campos_no_vacios"]["entidad_contratante"] == 0
    assert sum(cob["motivos_degradado"].values()) == 2
