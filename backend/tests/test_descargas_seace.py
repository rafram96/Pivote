"""Caché secuencial de documentos SEACE."""
from __future__ import annotations

from orquestador.descargas_seace import (
    CacheDescargasSeace,
    archivo_seace_valido,
    clave_archivo_seace,
)


def test_clave_prefiere_filecode_y_hash_si_no_existe():
    assert clave_archivo_seace(
        "https://prod1.seace.gob.pe/x?foo=1&fileCode=ABC-123"
    ) == "ABC-123"
    una = clave_archivo_seace("https://estado/documento/1")
    otra = clave_archivo_seace("https://estado/documento/2")
    assert len(una) == 64
    assert una != otra


def test_respuesta_invalida_no_contamina_cache_destino_ni_temporales(tmp_path):
    cache = CacheDescargasSeace(tmp_path / "cache")

    def descargar(_url, destino):
        destino.write_bytes(b"<html>WAF</html>")
        return True

    resultado = cache.materializar(
        "https://estado/x?fileCode=MALO",
        tmp_path / "destino.pdf",
        descargar=descargar,
    )

    assert not resultado.ok
    assert not (tmp_path / "destino.pdf").exists()
    assert not list((tmp_path / "cache").glob("*"))


def test_cache_valida_magia_y_publica_copias_atomicas(tmp_path):
    cache = CacheDescargasSeace(tmp_path / "cache")
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.write_bytes(b"PK\x03\x04contenido")
        return True

    url = "https://prod1.seace.gob.pe/x?fileCode=ZIP-UNO"
    primero = cache.materializar(
        url, tmp_path / "primero.zip", descargar=descargar
    )
    segundo = cache.materializar(
        url, tmp_path / "segundo.zip", descargar=descargar
    )

    assert primero.ok and not primero.cache_hit
    assert segundo.ok and segundo.cache_hit
    assert len(llamadas) == 1
    assert archivo_seace_valido(tmp_path / "primero.zip")
    assert (tmp_path / "primero.zip").read_bytes() == (
        tmp_path / "segundo.zip"
    ).read_bytes()
    assert not list(tmp_path.rglob("*.part"))
