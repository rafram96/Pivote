"""Caché documental InfoObras por obra y por job (issue #80)."""
from __future__ import annotations

import os
from datetime import date

from orquestador.descargas_infoobras import (
    CacheDescargasInfoObras,
    informe_en_periodo,
)
from orquestador.descargas_seace import materializar_archivo


def _corpus(destino):
    (destino / "Valorizaciones" / "2025-01 ENERO").mkdir(parents=True)
    (destino / "Valorizaciones" / "2025-01 ENERO" / "val.pdf").write_bytes(
        b"%PDF valorizacion"
    )
    (destino / "Informes de control").mkdir()
    (destino / "Informes de control" / "2018 - I-18.pdf").write_bytes(b"%PDF 18")
    (destino / "Informes de control" / "2022 - I-22.pdf").write_bytes(b"%PDF 22")
    return {"secciones": {}, "informes_anios": [2018, 2022]}


def test_filtro_de_informes_conserva_semantica_anual_inclusiva():
    assert informe_en_periodo(
        "2018 - I-18.pdf", date(2018, 12, 31), date(2018, 12, 31)
    )
    assert not informe_en_periodo(
        "2019 - I-19.pdf", date(2018, 1, 1), date(2018, 12, 31)
    )
    assert informe_en_periodo(
        "s-f - sin fecha.pdf", date(2018, 1, 1), date(2018, 12, 31)
    )


def test_infoobras_cache_por_obra_id(tmp_path):
    """Una sola descarga por obra_id, dos árboles materializados con filtro local distinto."""
    cache = CacheDescargasInfoObras(tmp_path / "job" / "cache_obras")
    llamadas = []

    def descargar(destino):
        llamadas.append(destino)
        return _corpus(destino)

    primero = cache.obtener(72056, descargar=descargar)
    segundo = cache.obtener(72056, descargar=descargar)
    destino_uno = tmp_path / "P1_E1"
    destino_uno.mkdir()
    (destino_uno / "BASES_INTEGRADAS.pdf").write_bytes(b"%PDF seace")
    (destino_uno / "Informes de control").mkdir()
    (destino_uno / "Informes de control/2017 - obsoleto.pdf").write_bytes(b"%PDF")
    uno = cache.materializar(
        primero, destino_uno,
        fecha_ini=date(2018, 1, 1), fecha_fin=date(2018, 12, 31),
    )
    dos = cache.materializar(
        segundo, tmp_path / "P2_E1",
        fecha_ini=date(2022, 1, 1), fecha_fin=date(2022, 12, 31),
    )

    assert len(llamadas) == 1
    assert uno.informes == dos.informes == 1
    assert (tmp_path / "P1_E1/Valorizaciones/2025-01 ENERO/val.pdf").is_file()
    assert (tmp_path / "P2_E1/Valorizaciones/2025-01 ENERO/val.pdf").is_file()
    assert (tmp_path / "P1_E1/Informes de control/2018 - I-18.pdf").is_file()
    assert (tmp_path / "P1_E1/BASES_INTEGRADAS.pdf").is_file()
    assert not (tmp_path / "P1_E1/Informes de control/2017 - obsoleto.pdf").exists()
    assert not (tmp_path / "P1_E1/Informes de control/2022 - I-22.pdf").exists()
    assert (tmp_path / "P2_E1/Informes de control/2022 - I-22.pdf").is_file()


def test_materializar_preserva_los_seace_con_nombres_viejos(tmp_path):
    """La caché de obra NO gestiona SEACE: al rematerializar InfoObras no puede
    borrar los documentos SEACE de la experiencia. Hay jobs en disco con los
    nombres históricos `SEACE_01_…`, así que se preservan ambos formatos."""
    cache = CacheDescargasInfoObras(tmp_path / "job" / "cache_obras")
    resultado = cache.obtener(72056, descargar=_corpus)
    destino = tmp_path / "P1_E1"
    destino.mkdir()
    (destino / "SEACE_01_BASES_INTEGRADAS.pdf").write_bytes(b"%PDF viejo")
    (destino / "SEACE_02_CONTRATO_FIRMADO_ERROR.txt").write_text("x", encoding="utf-8")
    (destino / "CONTRATO_FIRMADO.pdf").write_bytes(b"%PDF nuevo")
    (destino / "BASES_INTEGRADAS_NO_DISPONIBLE.txt").write_text("x", encoding="utf-8")
    (destino / "resto-de-un-corpus-anterior.pdf").write_bytes(b"%PDF viejo corpus")

    cache.materializar(resultado, destino, fecha_ini=None, fecha_fin=None)

    for nombre in ("SEACE_01_BASES_INTEGRADAS.pdf",
                   "SEACE_02_CONTRATO_FIRMADO_ERROR.txt",
                   "CONTRATO_FIRMADO.pdf",
                   "BASES_INTEGRADAS_NO_DISPONIBLE.txt"):
        assert (destino / nombre).is_file(), nombre
    # lo que no es SEACE sí se limpia antes de rematerializar
    assert not (destino / "resto-de-un-corpus-anterior.pdf").exists()
    assert (destino / "Valorizaciones/2025-01 ENERO/val.pdf").is_file()


def test_cache_parcial_se_descarta_y_cache_completa_funciona_offline(tmp_path):
    raiz = tmp_path / "job" / "cache_obras"
    parcial = raiz / "99"
    parcial.mkdir(parents=True)
    (parcial / "archivo_incompleto.pdf").write_bytes(b"%PDF parcial")
    llamadas = []

    def descargar(destino):
        llamadas.append(destino)
        return _corpus(destino)

    cache = CacheDescargasInfoObras(raiz)
    nuevo = cache.obtener(99, descargar=descargar)
    assert not nuevo.cache_hit
    assert len(llamadas) == 1
    assert not (parcial / "archivo_incompleto.pdf").exists()

    reutilizado = cache.obtener(
        99,
        descargar=lambda _destino: (_ for _ in ()).throw(
            AssertionError("una caché completa no debe tocar la red")
        ),
    )
    assert reutilizado.cache_hit
    cache.materializar(
        reutilizado, tmp_path / "offline",
        fecha_ini=None, fecha_fin=None,
    )
    assert (tmp_path / "offline/Valorizaciones/2025-01 ENERO/val.pdf").is_file()


def test_materializacion_hardlink_y_fallback_a_copia(tmp_path, monkeypatch):
    origen = tmp_path / "origen.pdf"
    origen.write_bytes(b"%PDF evidencia")
    por_link = tmp_path / "link.pdf"
    materializar_archivo(origen, por_link)
    assert por_link.read_bytes() == origen.read_bytes()
    if os.name == "nt":
        assert origen.stat().st_ino == por_link.stat().st_ino

    def link_falla(*_args, **_kwargs):
        raise OSError("volúmenes distintos")

    monkeypatch.setattr("orquestador.descargas_seace.os.link", link_falla)
    por_copia = tmp_path / "copia.pdf"
    materializar_archivo(origen, por_copia)
    assert por_copia.read_bytes() == origen.read_bytes()
    assert not list(tmp_path.rglob("*.part"))
