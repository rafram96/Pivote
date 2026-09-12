"""Cadena offline: colección SEACE, caché, manifiesto y retiro seguro."""

import json
import zipfile

import pytest

from entregables import construir_zip_infoobras
from orquestador.etapas_reales import descargar_documentos_job
from orquestador.repositorio import carpeta_job


def _espejo(cantidad=3):
    return {"_meta": {"tipo_evaluacion": "obras"}, "profesionales": [{
        "n_prof": 1, "experiencias": [
            {"n": n, "proyecto": f"Hospital {n}"} for n in range(1, cantidad + 1)
        ],
    }]}


def _seace():
    docs = [
        {"categoria": "bases", "id_documento": "b1", "id_contrato": None,
         "ocid": "ocid-1", "url": "https://fuente/bases", "titulo": "Bases integradas",
         "formato": "pdf", "tipo_publicado": "biddingDocuments",
         "rol_documental": "por_identificar", "correspondencia": "por_confirmar"},
        {"categoria": "contrato", "id_documento": "f1", "id_contrato": "c1",
         "ocid": "ocid-1", "url": "https://fuente/firma", "titulo": "Firma 1",
         "formato": "pdf", "tipo_publicado": "contractSigned",
         "rol_documental": "por_identificar", "correspondencia": "por_confirmar"},
        {"categoria": "contrato", "id_documento": "a1", "id_contrato": "c1",
         "ocid": "ocid-1", "url": "https://fuente/anexo", "titulo": "Anexo 1",
         "formato": "pdf", "tipo_publicado": "contractAnnexe",
         "rol_documental": "por_identificar", "correspondencia": "por_confirmar"},
    ]
    return {"estado": "seleccionado", "documentos": docs}


def _enriquecimiento(cantidad=3, estado="seleccionado"):
    return {f"1:{n}": {"seace": _seace() if estado == "seleccionado"
                         else {"estado": estado, "motivo": "selección retirada"}}
            for n in range(1, cantidad + 1)}


def test_coleccion_materializa_manifiesto_zip_y_comparte_cache(tmp_path):
    espejo = _espejo()
    enr = _enriquecimiento()
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-1.4 documento")
        return True

    base = carpeta_job(tmp_path, "cadena") / "descargas"
    base.mkdir(parents=True, exist_ok=True)
    (base / "P1_E1.seace.ok").write_text("ok", encoding="utf-8")
    descargar_documentos_job(espejo, enr, "cadena", tmp_path, descargar_seace=descargar)
    assert sorted(llamadas) == ["https://fuente/anexo", "https://fuente/bases", "https://fuente/firma"]
    for n in range(1, 4):
        destino = base / f"P1_E{n}" / "Documentos SEACE"
        manifiesto = json.loads((destino / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))
        assert len(manifiesto["documentos"]) == 3
        assert all(d["estado"] == "descargado" for d in manifiesto["documentos"])
        assert enr[f"1:{n}"]["descargas_reales"]["archivos"] == 3
    salida = construir_zip_infoobras(espejo,
                                     {(1, n): base / f"P1_E{n}" for n in range(1, 4)},
                                     tmp_path / "cadena.zip", enriquecimiento=enr)
    with zipfile.ZipFile(salida) as zf:
        assert sum(n.endswith("DOCUMENTOS_SEACE.json") for n in zf.namelist()) == 3


def test_marca_legacy_no_omite_hermanos_y_retiro_no_reintenta_red(tmp_path):
    espejo = _espejo(2)
    enr = _enriquecimiento(2)
    base = carpeta_job(tmp_path, "retiro") / "descargas"
    (base / "P1_E1.seace.ok").parent.mkdir(parents=True, exist_ok=True)
    (base / "P1_E1.seace.ok").write_text("ok", encoding="utf-8")
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-1.4 documento")
        return True

    descargar_documentos_job(espejo, enr, "retiro", tmp_path, descargar_seace=descargar)
    assert len(llamadas) == 3
    enr_retirado = _enriquecimiento(2, estado="identidad_pendiente")
    descargar_documentos_job(espejo, enr_retirado, "retiro", tmp_path,
                              descargar_seace=lambda *_: (_ for _ in ()).throw(
                                  AssertionError("no debe tocar red")))
    for n in range(1, 3):
        carpeta = base / f"P1_E{n}" / "Documentos SEACE"
        manifiesto = json.loads((carpeta / "DOCUMENTOS_SEACE.json").read_text(encoding="utf-8"))
        assert manifiesto["documentos"] == []
        assert not list(carpeta.glob("*.pdf"))
    assert list((carpeta_job(tmp_path, "retiro") / "descargas_previas").rglob("*.pdf"))


def test_retiro_de_legado_sin_fuente_no_deja_adjuntos_en_zip(tmp_path):
    base = carpeta_job(tmp_path, "sin-fuente") / "descargas"
    destino = base / "P1_E1"
    destino.mkdir(parents=True)
    (destino / "CONTRATO_FIRMADO.pdf").write_bytes(b"%PDF anterior")
    (base / "P1_E1.seace.ok").write_text("ok")
    enr = {"1:1": {}}
    descargar_documentos_job(_espejo(1), enr, "sin-fuente", tmp_path)
    assert not list(destino.rglob("*.pdf"))
    assert enr["1:1"]["descargas_reales"]["archivos"] == 0
    assert list((base.parent / "descargas_previas").rglob("CONTRATO_FIRMADO.pdf"))


def test_fallo_de_retiro_aborta_en_vez_de_publicar_mezcla(tmp_path, monkeypatch):
    from orquestador.adjuntos_seace import MaterializadorAdjuntosSeace, ErrorIntegridadAdjuntos
    def fallo(*_):
        raise PermissionError("No se puede retirar el árbol anterior")
    monkeypatch.setattr(MaterializadorAdjuntosSeace, "materializar", fallo)
    with pytest.raises(ErrorIntegridadAdjuntos):
        descargar_documentos_job(_espejo(1), _enriquecimiento(1), "seguridad", tmp_path)


def test_cambio_infoobras_y_cache_no_tocan_seleccion_seace(tmp_path):
    from orquestador.descargas_infoobras import (
        preparar_destino_infoobras, guardar_marca_infoobras, CacheDescargasInfoObras)
    base = tmp_path / "job/descargas"
    destino = base / "P1_E1"
    carpeta = destino / "Documentos SEACE"
    carpeta.mkdir(parents=True)
    adjunto = carpeta / "ADJUNTO_CONTRATO_actual.pdf"
    adjunto.write_bytes(b"%PDF seace actual")
    (carpeta / "DOCUMENTOS_SEACE.json").write_text('{"documentos":[]}')
    marca = base / "P1_E1.ok"
    guardar_marca_infoobras(marca, 1)
    assert not preparar_destino_infoobras(destino, marca, 2)
    assert adjunto.read_bytes() == b"%PDF seace actual"
    cache = CacheDescargasInfoObras(tmp_path / "job/cache_obras")
    def descargar(ruta, _pendientes=None):
        ruta.mkdir(parents=True, exist_ok=True)
        (ruta / "obra.pdf").write_bytes(b"%PDF obra")
        return {"secciones": {}}
    cache.materializar(cache.obtener(2, descargar=descargar), destino, fecha_ini=None, fecha_fin=None)
    assert adjunto.read_bytes() == b"%PDF seace actual"
    assert (carpeta / "DOCUMENTOS_SEACE.json").is_file()


def test_fallo_infoobras_no_impide_adjuntos_seace_ni_retiro(tmp_path):
    espejo = _espejo(1)
    enr = _enriquecimiento(1)
    enr["1:1"]["obra"] = {"obra_id": 1}
    def falla_infoobras(*_):
        raise ConnectionError("InfoObras no respondió")
    def descargar(_url, destino):
        destino.write_bytes(b"%PDF-1.4 adjunto")
        return True
    descargar_documentos_job(espejo, enr, "fuentes", tmp_path,
                             descargar=falla_infoobras, descargar_seace=descargar)
    assert enr["1:1"]["descargas_reales"]["archivos"] == 3
    assert not enr["1:1"]["descargas_reales"]["completada"]
    enr["1:1"]["seace"] = {"estado": "identidad_pendiente", "documentos": []}
    enr["1:1"]["obra"] = {"obra_id": 2}
    descargar_documentos_job(espejo, enr, "fuentes", tmp_path, descargar=falla_infoobras)
    destino = carpeta_job(tmp_path, "fuentes") / "descargas/P1_E1"
    assert not list((destino / "Documentos SEACE").glob("*.pdf"))
