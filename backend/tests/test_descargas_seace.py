"""Caché secuencial de documentos SEACE."""
from __future__ import annotations

def _zip_real(**archivos) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, cuerpo in (archivos or {"contenido.txt": "x"}).items():
            z.writestr(nombre, cuerpo)
    return buf.getvalue()


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
        destino.write_bytes(_zip_real())
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


def test_archivo_seace_valido_reconoce_word(tmp_path):
    docx = tmp_path / "bases.docx"
    docx.write_bytes(_zip_real(**{"[Content_Types].xml": "<Types/>", "word/document.xml": "<w/>"}))
    doc = tmp_path / "bases.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)
    malo = tmp_path / "bases2.docx"
    malo.write_bytes(b"%PDF-1.4")
    cualquier_zip = tmp_path / "bases3.docx"
    cualquier_zip.write_bytes(_zip_real(**{"aviso.txt": "no es Word"}))
    truncado = tmp_path / "bases4.docx"
    truncado.write_bytes(b"PK\x03\x04")
    assert archivo_seace_valido(docx) and archivo_seace_valido(doc)
    assert not archivo_seace_valido(malo)
    assert not archivo_seace_valido(cualquier_zip)
    assert not archivo_seace_valido(truncado)
