from __future__ import annotations

import json

from orquestador.adjuntos_seace import MaterializadorAdjuntosSeace


def _doc(url: str, categoria: str = "bases", estado: str = "seleccionado"):
    return {"categoria": categoria, "id_documento": "d1",
            "id_contrato": "c1", "ocid": "o1", "url": url,
            "titulo": "Mismo título", "formato": "pdf",
            "rol_documental": "contrato", "correspondencia": "confirmado"}


def test_adjuntos_separan_titulos_duplicados_y_no_confian_metadatos(tmp_path):
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.write_bytes(b"%PDF-1.4 contenido")
        return True

    materializador = MaterializadorAdjuntosSeace(
        tmp_path, tmp_path / "cache", lambda _clave: True, descargar
    )
    docs = [_doc("https://seace/a?fileCode=A"),
            {**_doc("https://seace/b?fileCode=B", "contrato"), "id_documento": "d2"}]
    resultado = materializador.materializar({"estado": "seleccionado", "documentos": docs}, tmp_path / "descargas" / "PE")
    carpeta = tmp_path / "descargas" / "PE" / "Documentos SEACE"
    nombres = [r["archivo_entregado"] for r in resultado["documentos"]]
    assert len(set(nombres)) == 2
    assert nombres[0].startswith("BASES_") and nombres[1].startswith("ADJUNTO_CONTRATO_")
    manifiesto = json.loads((carpeta / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))
    assert all(d["rol_documental"] == "por_identificar" and d["correspondencia"] == "por_confirmar"
               for d in manifiesto["documentos"])
    assert len(llamadas) == 2


def test_falla_una_fuente_y_lista_vacia_retira_de_forma_recuperable(tmp_path):
    def descargar(url, destino):
        if url.endswith("bad"):
            return False
        destino.write_bytes(b"%PDF-1.4 ok")
        return True

    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    destino = tmp_path / "descargas" / "PE"
    r = m.materializar({"estado": "seleccionado", "documentos": [_doc("https://x/good"), _doc("https://x/bad")]}, destino)
    assert r["descargados"] == 1
    m.materializar({"documentos": []}, destino)
    assert (destino / "Documentos SEACE" / "DOCUMENTOS_SEACE.json").is_file()
    assert list((tmp_path / "descargas_previas").iterdir())


def test_hermanos_mismo_titulo_y_url_distinta_no_colisionan(tmp_path):
    llamadas = []
    def descargar(url, destino):
        llamadas.append(url); destino.write_bytes(b"%PDF-1.4 ok"); return True
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    docs = [_doc("https://x/uno"), {**_doc("https://x/dos"), "id_documento": "d2"}]
    r = m.materializar({"estado": "seleccionado", "documentos": docs}, tmp_path / "descargas" / "P")
    assert len(set(x["archivo_entregado"] for x in r["documentos"])) == 2
    assert len(llamadas) == 2


def test_mismo_url_ids_distintos_comparte_cache(tmp_path):
    llamadas = []
    def descargar(url, destino):
        llamadas.append(url); destino.write_bytes(b"%PDF-1.4 ok"); return True
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    docs = [_doc("https://x/uno"), {**_doc("https://x/uno"), "id_documento": "d2"}]
    r = m.materializar({"estado": "seleccionado", "documentos": docs}, tmp_path / "descargas" / "P")
    assert r["descargados"] == 2 and len(llamadas) == 1


def test_sin_url_es_sin_enlace_y_falla_una_no_detiene_otra(tmp_path):
    def descargar(url, destino):
        if url.endswith("bad"): return False
        destino.write_bytes(b"%PDF-1.4 ok"); return True
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    docs = [_doc("https://x/bad"), {**_doc(""), "id_documento": "d2"},
            {**_doc("https://x/good"), "id_documento": "d3"}]
    r = m.materializar({"estado": "seleccionado", "documentos": docs}, tmp_path / "descargas" / "P")
    assert [x["estado"] for x in r["documentos"]] == ["descarga_fallida", "sin_enlace", "descargado"]


def test_reanudacion_no_reintenta_red(tmp_path):
    intentos = []
    def intentar(k):
        intentos.append(k); return len(intentos) == 1
    def descargar(_url, _destino):
        raise AssertionError("no debe completar una descarga fallida")
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", intentar, descargar)
    d = {"estado": "seleccionado", "documentos": [_doc("https://x/falla")]}
    assert m.materializar(d, tmp_path / "descargas" / "P")["descargados"] == 0
    assert m.materializar(d, tmp_path / "descargas" / "P")["descargados"] == 0
    assert len(intentos) == 1


def test_estado_no_seleccionado_retira_sin_red_y_huella_estable(tmp_path):
    llamadas = []
    def descargar(url, destino):
        llamadas.append(url); destino.write_bytes(b"%PDF-1.4 ok"); return True
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    destino = tmp_path / "descargas" / "P"
    m.materializar({"estado": "seleccionado", "documentos": [_doc("https://x/a")]}, destino)
    d = {"estado": "fuente_no_disponible", "motivo": "portal caído", "documentos": [_doc("https://x/a")]}
    m.materializar(d, destino)
    n = len(list((tmp_path / "descargas_previas").iterdir()))
    m.materializar(d, destino)
    assert len(llamadas) == 1 and len(list((tmp_path / "descargas_previas").iterdir())) == n
    assert "portal caído" in (destino / "Documentos SEACE" / "DOCUMENTOS_SEACE.txt").read_text(encoding="utf-8")


def test_cambio_url_respalda_hash_y_destino_inseguro_rechaza(tmp_path):
    def descargar(_url, destino): destino.write_bytes(b"%PDF-1.4 ok"); return True
    m = MaterializadorAdjuntosSeace(tmp_path, tmp_path / "cache", lambda _k: True, descargar)
    destino = tmp_path / "descargas" / "P"
    m.materializar({"estado": "seleccionado", "documentos": [_doc("https://x/a")]}, destino)
    viejo = next((destino / "Documentos SEACE").glob("BASES_*.pdf"))
    sha = __import__("hashlib").sha256(viejo.read_bytes()).hexdigest()
    m.materializar({"estado": "seleccionado", "documentos": [_doc("https://x/b")]}, destino)
    assert any(__import__("hashlib").sha256(p.read_bytes()).hexdigest() == sha
               for p in (tmp_path / "descargas_previas").rglob("*.pdf"))
    try:
        m.materializar({"estado": "seleccionado", "documentos": []}, tmp_path / "otra")
    except ValueError:
        pass
    else:
        raise AssertionError("destino fuera del job aceptado")


def test_retirar_legado_no_toca_mef(tmp_path):
    destino = tmp_path / "descargas" / "P"
    destino.mkdir(parents=True)
    (destino / "BASES_INTEGRADAS.pdf").write_bytes(b"legacy")
    (destino / "CONTRATO_FIRMADO_NO_DISPONIBLE.txt").write_text("x")
    (destino / "otro.txt").write_text("keep")
    (destino / "Verificación MEF").mkdir()
    m = MaterializadorAdjuntosSeace(tmp_path)
    assert m.retirar_legado(destino) == 2
    assert (destino / "otro.txt").exists() and (destino / "Verificación MEF").exists()
