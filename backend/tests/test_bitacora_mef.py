"""
Tests offline del aviso de frescura de la base MEF (issue #24).

Lo que se comprueba, en el orden en que importa:

  1. cada corrida del refresco deja rastro — la buena y la que falló, esta con
     su causa ya clasificada;
  2. con la base al día NADIE es molestado (ni salud, ni el buscador, ni el
     análisis): un aviso que sale siempre deja de leerse;
  3. con la base vencida —o con el refresco caído— el aviso aparece en las TRES
     superficies existentes;
  4. sin base, o con una base sin fecha, nada revienta.

Cero red y cero PostgreSQL: la bitácora son dos funciones sobre un JSON y
`frescura()` mira dos archivos.
"""
from __future__ import annotations

import gzip
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from resolucion import bitacora_mef
from resolucion.base_mef import BaseMef

FIX = Path(__file__).parent / "fixtures" / "mef"


def _instalar_base(dir_base: Path, *, dias: int | None = 0) -> BaseMef:
    """Base mínima usable, con la fecha de metadata movida `dias` al pasado.
    `dias=None` deja la metadata SIN fecha (base de la que no se sabe la edad)."""
    dir_base.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIX / "mef_mini.csv.gz", dir_base / "inversiones.csv.gz")
    shutil.copy(FIX / "entidades_mini.csv", dir_base / "entidades_publicas.csv")
    meta = {"cuis_distintos": 23}
    if dias is not None:
        meta["fecha"] = (date.today() - timedelta(days=dias)).isoformat()
    (dir_base / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    return BaseMef(dir_base)


# ── 1 · la corrida deja rastro ───────────────────────────────────────────────

def test_exito_queda_registrado_con_fecha_y_filas(tmp_path):
    bitacora_mef.registrar_exito(
        tmp_path,
        meta={"load_id": "20260803T030000Z-abc", "filas_total": 620_985,
              "cuis_distintos": 579_481, "entidades": 11_011},
        duracion_s=612.4)

    ultima = bitacora_mef.ultima_corrida(tmp_path)
    assert ultima["ok"] is True
    assert ultima["load_id"] == "20260803T030000Z-abc"
    assert ultima["filas_total"] == 620_985
    assert ultima["duracion_s"] == 612.4
    assert ultima["causa"] is None
    assert ultima["fin"][:4] == str(date.today().year)


def test_fallo_queda_registrado_con_causa_clasificada(tmp_path):
    bitacora_mef.registrar_fallo(
        tmp_path,
        error=RuntimeError("HTTPSConnectionPool: Max retries exceeded "
                           "(getaddrinfo failed)"))

    ultima = bitacora_mef.ultima_corrida(tmp_path)
    assert ultima["ok"] is False
    assert ultima["categoria"] == "red"          # vocabulario de errores_red
    assert "DNS" in ultima["causa"]
    assert ultima["excepcion"] == "RuntimeError"
    assert ultima["load_id"] is None


def test_un_fallo_no_borra_la_ultima_corrida_buena(tmp_path):
    bitacora_mef.registrar_exito(tmp_path, meta={"load_id": "bueno",
                                                 "filas_total": 620_000})
    bitacora_mef.registrar_fallo(tmp_path, error=ValueError("validación FALLIDA"))

    datos = bitacora_mef.leer(tmp_path)
    assert datos["ultima"]["ok"] is False
    assert datos["ultimo_exito"]["load_id"] == "bueno"   # la buena sigue ahí
    assert len(datos["historial"]) == 2


def test_historial_acotado(tmp_path):
    for i in range(bitacora_mef.MAX_HISTORIAL + 5):
        bitacora_mef.registrar_exito(tmp_path, meta={"load_id": f"c{i}"})
    datos = bitacora_mef.leer(tmp_path)
    assert len(datos["historial"]) == bitacora_mef.MAX_HISTORIAL
    assert datos["historial"][0]["load_id"] == "c24"     # el más reciente primero


def test_bitacora_ilegible_no_lanza(tmp_path):
    bitacora_mef.ruta(tmp_path).write_text("{esto no es json", encoding="utf-8")
    assert bitacora_mef.leer(tmp_path) is None
    assert bitacora_mef.ultima_corrida(tmp_path) is None
    # y una escritura nueva la reemplaza en vez de arrastrar la basura
    bitacora_mef.registrar_exito(tmp_path, meta={"load_id": "x"})
    assert bitacora_mef.ultima_corrida(tmp_path)["load_id"] == "x"


def test_no_poder_escribir_no_tumba_la_corrida(tmp_path, monkeypatch):
    def explota(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(bitacora_mef.os, "replace", explota)
    dichos: list[str] = []
    datos = bitacora_mef.registrar_exito(tmp_path, meta={"load_id": "x"},
                                         aviso=dichos.append)
    assert datos["ultima"]["load_id"] == "x"    # el dato se devuelve igual
    assert dichos and "bitácora" in dichos[0]


# ── el script del ETL anota su propio resultado ──────────────────────────────

def test_el_etl_anota_exito_y_fallo(tmp_path):
    from scripts.actualizar_base_mef import ActualizacionEnCurso, _con_bitacora

    meta = _con_bitacora(tmp_path, lambda: {"load_id": "L1", "filas_total": 500_000})
    assert meta["load_id"] == "L1"
    assert bitacora_mef.ultima_corrida(tmp_path)["ok"] is True

    def cae():
        raise ConnectionError("Connection aborted, RemoteDisconnected")

    with pytest.raises(ConnectionError):
        _con_bitacora(tmp_path, cae)
    ultima = bitacora_mef.ultima_corrida(tmp_path)
    assert ultima["ok"] is False and ultima["categoria"] == "portal"

    # el choque de lock NO es un fallo del refresco: no debe pisar el registro
    def ocupada():
        raise ActualizacionEnCurso("ya existe una actualización MEF en ejecución")

    with pytest.raises(ActualizacionEnCurso):
        _con_bitacora(tmp_path, ocupada)
    assert bitacora_mef.ultima_corrida(tmp_path) == ultima


# ── 2 · base al día: silencio ────────────────────────────────────────────────

def test_base_al_dia_no_avisa_en_ninguna_superficie(tmp_path):
    from orquestador.etapas_reales import EtapaResolucionCuiReal
    from resolucion.busqueda_mef import buscar

    base = _instalar_base(tmp_path, dias=3)
    bitacora_mef.registrar_exito(tmp_path, meta={"load_id": "L1"})

    fr = base.frescura()
    assert fr == {"estado": "ok", "edad_dias": 3, "umbral_dias": 10,
                  "ultimo_refresco": bitacora_mef.ultima_corrida(tmp_path),
                  "mensaje": None}

    r = buscar("hospital", base=base)
    assert r["base_desactualizada"] is False
    assert r["aviso_frescura"] is None

    assert _observaciones_frescura(EtapaResolucionCuiReal, base) == []


# ── 3 · base vencida / refresco caído: se nota ───────────────────────────────

def test_base_vencida_es_stale_y_lo_explica(tmp_path):
    base = _instalar_base(tmp_path, dias=21)
    fr = base.frescura()
    assert fr["estado"] == "stale"
    assert fr["edad_dias"] == 21 and fr["umbral_dias"] == 10
    assert "21 día(s)" in fr["mensaje"]
    assert "MEF" in fr["mensaje"] and "responsable del servidor" in fr["mensaje"]
    # sin jerga: el mensaje lo lee un evaluador, no un operador de sistemas
    for palabra in ("ETL", "stale", "artefacto", "backend", "cron"):
        assert palabra not in fr["mensaje"]


def test_umbral_configurable_por_entorno(tmp_path, monkeypatch):
    base = _instalar_base(tmp_path, dias=9)
    assert base.frescura()["estado"] == "ok"          # default 10

    monkeypatch.setenv("PIVOTE_MEF_DIAS_FRESCURA", "7")
    assert base.frescura()["estado"] == "stale"
    assert base.frescura()["umbral_dias"] == 7

    # un valor absurdo NO apaga el aviso: cae al default
    monkeypatch.setenv("PIVOTE_MEF_DIAS_FRESCURA", "cada tanto")
    assert base.frescura()["umbral_dias"] == 10
    monkeypatch.setenv("PIVOTE_MEF_DIAS_FRESCURA", "0")
    assert base.frescura()["umbral_dias"] == 10


def test_base_fresca_pero_refresco_caido_avisa_temprano(tmp_path):
    base = _instalar_base(tmp_path, dias=2)
    bitacora_mef.registrar_fallo(tmp_path, error=TimeoutError("read timed out"))

    fr = base.frescura()
    assert fr["estado"] == "refresco_fallido"
    assert "todavía está al día" in fr["mensaje"]
    assert "timeout" in fr["mensaje"]                 # la causa concreta viaja
    assert fr["ultimo_refresco"]["categoria"] == "portal"


def test_vencida_con_refresco_caido_dice_las_dos_cosas(tmp_path):
    base = _instalar_base(tmp_path, dias=30)
    bitacora_mef.registrar_fallo(tmp_path, error=ValueError("caída de volumen"))
    mensaje = base.frescura()["mensaje"]
    assert "30 día(s)" in mensaje
    assert "no llegó a completarse" in mensaje


def test_superficie_buscador(tmp_path):
    from resolucion.busqueda_mef import buscar

    base = _instalar_base(tmp_path, dias=40)
    r = buscar("hospital", base=base)
    assert r["base_desactualizada"] is True
    assert "40 día(s)" in r["aviso_frescura"]
    assert r["aviso"] is None            # no pisa el aviso de la consulta
    assert r["edad_dias"] == 40


def test_superficie_salud(tmp_path, monkeypatch):
    import resolucion.base_mef as bm
    from fastapi.testclient import TestClient

    from api.app import app

    base = _instalar_base(tmp_path, dias=40)
    monkeypatch.setattr(bm, "instancia", lambda dir_base=None: base)

    with TestClient(app) as cliente:
        cuerpo = cliente.get("/api/pivote/salud").json()
    mef = next(p for p in cuerpo if p["portal"] == "base_mef")
    assert mef["ok"] is False
    assert mef["diagnostico"] == "stale"
    assert mef["edad_dias"] == 40 and mef["umbral_dias"] == 10
    assert "40 día(s)" in mef["mensaje"]


def test_superficie_analisis(tmp_path):
    from orquestador.etapas_reales import EtapaResolucionCuiReal

    base = _instalar_base(tmp_path, dias=40)
    obs = _observaciones_frescura(EtapaResolucionCuiReal, base)
    assert len(obs) == 1
    assert obs[0].codigo == "BASE_MEF_DESACTUALIZADA"
    assert obs[0].severidad.value == "advertencia"
    assert "40 día(s)" in obs[0].mensaje


# ── 4 · nada revienta sin base ───────────────────────────────────────────────

def test_sin_base_instalada(tmp_path):
    base = BaseMef(tmp_path / "no-existe")
    fr = base.frescura()
    assert fr["estado"] == "missing"
    assert fr["edad_dias"] is None
    assert "no está instalada" in fr["mensaje"]


def test_base_sin_fecha_no_se_da_por_fresca(tmp_path):
    """Peor que una base vieja es una de la que no se sabe la edad: si `invalid`
    se tratara como `ok`, un metadata corrupto apagaría el aviso para siempre."""
    base = _instalar_base(tmp_path, dias=None)
    fr = base.frescura()
    assert fr["estado"] == "invalid"
    assert fr["edad_dias"] is None
    assert "no se puede saber de cuándo es" in fr["mensaje"].lower()


def test_base_nunca_actualizada_no_crashea(tmp_path):
    """Base recién instalada a mano: hay artefactos y no hay bitácora."""
    base = _instalar_base(tmp_path, dias=1)
    assert bitacora_mef.ultima_corrida(tmp_path) is None
    fr = base.frescura()
    assert fr["estado"] == "ok" and fr["ultimo_refresco"] is None


# ── helper ───────────────────────────────────────────────────────────────────

def _observaciones_frescura(clase, base) -> list:
    """Corre SOLO el bloque de frescura de la etapa de resolución: un contexto
    sin experiencias hace que la etapa no toque red ni el resolver."""
    from schemas import pipeline

    class _CtxVacio:
        espejo: dict = {"profesionales": []}
        datos_humano: dict = {}
        enriquecimiento: dict = {}
        job = pipeline  # solo se toca si hay items; aquí no hay

        def items_experiencia(self):
            return []

        def reportar(self, *a, **k):
            return None

    etapa = clase(consulta=object())
    import resolucion.base_mef as bm
    original = bm.instancia
    bm.instancia = lambda dir_base=None: base
    try:
        res = etapa.correr(_CtxVacio())
    finally:
        bm.instancia = original
    return [o for o in res.observaciones if o.codigo == "BASE_MEF_DESACTUALIZADA"]
