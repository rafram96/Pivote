"""Descarga diferida por sub-obra sin mezclar identidad, periodos ni fuentes."""
from copy import deepcopy
import zipfile

from entregables.zip_infoobras import construir_zip_infoobras
from orquestador.etapas_reales import (
    _experiencias_documentales, descargar_documentos_job,
)


def _caso():
    espejo = {"_meta": {"tipo_evaluacion": "obras"}, "profesionales": [{
        "n_prof": 1, "cargo": "ESPECIALISTA", "experiencias": [{
            "n": 1, "proyecto": "Certificado de varios hospitales",
            "fecha_inicial": "2020-01-01", "fecha_final": "2024-12-31",
        }],
    }]}
    sub = {"estado": "resuelto", "cui": "2000001", "proyecto": "Hospital A",
           "obra": {"obra_id": 101}}
    info = {"1:1": {"via": "MULTI_OBRA", "cui": None, "obra": None,
                    "sub_obras": [sub, {**deepcopy(sub), "proyecto": "Hospital A otro periodo"},
                                  {"estado": "revision", "proyecto": "Hospital B",
                                   "obra": {"obra_id": 999}, "cui": None}]}}
    return espejo, info


def test_multiobra_descarga_comparte_cache_y_conserva_nota_en_zip(tmp_path):
    espejo, info = _caso()
    llamadas = []

    def descargar(oid, destino):
        llamadas.append(oid)
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "respaldo.pdf").write_bytes(b"%PDF-1.4 respaldo")

    for _ in range(2):
        resultado = descargar_documentos_job(
            espejo, info, "multi", tmp_path, descargar=descargar)
    assert llamadas == [101]
    assert resultado["descargas"] == 2
    padre = tmp_path / "multi/descargas/P1_E1"
    assert (padre / "Subobra 01/respaldo.pdf").exists()
    assert (padre / "Subobra 02/respaldo.pdf").exists()
    assert not (padre / "Subobra 03/respaldo.pdf").exists()
    assert info["1:1"]["cui"] is None and info["1:1"]["obra"] is None
    assert info["1:1"]["descargas_reales"]["archivos"] == 2
    assert not info["1:1"]["descargas_reales"]["completada"]
    salida = construir_zip_infoobras(espejo, {(1, 1): padre}, tmp_path / "entrega.zip", info)
    with zipfile.ZipFile(salida) as z:
        assert sum(n.endswith("respaldo.pdf") for n in z.namelist()) == 2
        nota = next(n for n in z.namelist() if n.endswith("Subobra 03/SIN_DOCUMENTOS.txt"))
        texto = z.read(nota).decode("utf-8")
        assert "Hospital B" in texto and "Identificación pendiente" in texto
        assert not any(n.endswith(".ok") for n in z.namelist())


def test_multiobra_no_hereda_fechas_y_respeta_ruta_expediente():
    espejo, info = _caso()
    subs = info["1:1"]["sub_obras"]
    subs[1].update(fecha_inicial="2022-02-01", fecha_final="2022-03-01")
    trabajos = list(_experiencias_documentales(espejo["profesionales"][0], info, "expedientes"))
    assert trabajos[0][0]["fecha_inicial"] is None
    assert trabajos[0][0]["fecha_final"] is None
    assert trabajos[1][0]["fecha_inicial"] == "2022-02-01"
    assert all(t[1]["camino"] == "expediente" for t in trabajos)
    assert espejo["profesionales"][0]["experiencias"][0]["fecha_inicial"] == "2020-01-01"


def test_multiobra_fallo_parcial_no_borra_documentos_hermanos(tmp_path):
    espejo, info = _caso()
    info["1:1"]["sub_obras"][1]["obra"]["obra_id"] = 102

    def descargar(oid, destino):
        if oid == 102:
            raise RuntimeError("fuente no respondió")
        destino.mkdir(parents=True, exist_ok=True)
        (destino / "respaldo.pdf").write_bytes(b"%PDF-1.4 respaldo")

    descargar_documentos_job(espejo, info, "parcial", tmp_path, descargar=descargar)
    subs = info["1:1"]["sub_obras"]
    assert subs[0]["descargas_reales"]["archivos"] == 1
    assert subs[1]["descargas_reales"]["archivos"] == 0
    assert not subs[1]["descargas_reales"]["completada"]
    assert (tmp_path / "parcial/descargas/P1_E1/Subobra 01/respaldo.pdf").exists()


def test_multiobra_seace_sin_obra_id_y_no_aplica_privada(tmp_path):
    espejo, info = _caso()
    subs = info["1:1"]["sub_obras"]
    subs[0]["obra"] = None
    subs[0]["seace"] = {"estado": "seleccionado", "docs": {
        "bases": {"url": "https://fuente/bases.pdf"}}}
    subs[1].update(estado="privada", via="PRIVADA", obra=None)
    llamadas = []

    def descargar(url, destino):
        llamadas.append(url)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-1.4 base")
        return True

    descargar_documentos_job(espejo, info, "seace-multi", tmp_path, descargar_seace=descargar)
    assert llamadas == ["https://fuente/bases.pdf"]
    padre = tmp_path / "seace-multi/descargas/P1_E1"
    assert (padre / "Subobra 01/BASES_INTEGRADAS.pdf").exists()
    assert "privada" in (padre / "Subobra 02/SIN_DOCUMENTOS.txt").read_text(encoding="utf-8")
