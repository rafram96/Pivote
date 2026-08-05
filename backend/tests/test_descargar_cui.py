"""
Tests offline de la descarga por un solo CUI (endpoint suelto): orquestación
(resolver CUI → bajar las 4 secciones → agregar) y el ZIP plano. Sin red: se
inyecta `fetch` y se monkepatchean las descargas de InfoObras.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from entregables import zip_infoobras
from entregables.zip_infoobras import _zip_carpeta, descargar_cui


class _Obra:
    """WorkInfo mínimo para el test (lo que descargar_cui lee por getattr)."""
    def __init__(self, obra_id, nombre, aprob=None):
        self.obra_id = obra_id
        self.nombre = nombre
        self.aprobacion_expediente = aprob


def test_zip_carpeta_empaqueta_el_arbol(tmp_path):
    base = tmp_path / "docs"
    (base / "Valorizaciones" / "2020-09").mkdir(parents=True)
    (base / "Valorizaciones" / "2020-09" / "a.pdf").write_bytes(b"%PDF a")
    (base / "Datos de cierre").mkdir(parents=True)
    (base / "Datos de cierre" / "b.pdf").write_bytes(b"%PDF b")
    (base / "Datos de cierre" / "incompleto.pdf.part").write_bytes(b"parcial")
    salida = tmp_path / "out.zip"
    _zip_carpeta(base, salida, "titulo demo")
    nombres = zipfile.ZipFile(salida).namelist()
    assert "indice.txt" in nombres
    assert any(n.endswith("a.pdf") for n in nombres)
    assert any(n.endswith("b.pdf") for n in nombres)
    assert not any(n.endswith(".part") for n in nombres)
    # conserva el árbol relativo (no aplana todo a la raíz)
    assert any("Valorizaciones/" in n for n in nombres)


def _stub_descargas(monkeypatch, registro):
    def hito(obra_id, destino, **k):
        Path(destino).mkdir(parents=True, exist_ok=True)
        registro.append(("hito", obra_id))
        return {"descargados": 3, "fallidos": 1, "inventario": {}}
    monkeypatch.setattr(zip_infoobras, "descargar_documentos_obra_por_hito", hito)
    monkeypatch.setattr(zip_infoobras, "descargar_informes_control",
                        lambda *a, **k: registro.append(("informes", a[0])) or {})
    monkeypatch.setattr(zip_infoobras, "descargar_datos_cierre",
                        lambda *a, **k: registro.append(("cierre", a[0])) or {})
    monkeypatch.setattr(zip_infoobras, "descargar_aprobacion_expediente",
                        lambda *a, **k: registro.append(("aprob",)) or True)


def test_descargar_cui_resuelve_y_baja_las_4_secciones(tmp_path, monkeypatch):
    reg = []
    _stub_descargas(monkeypatch, reg)
    aprob = {"filename": "expediente/doc.pdf", "nombre": "Res", "extension": "pdf",
             "fecha": "2020-09-17", "url": "u"}
    r = descargar_cui("2418877", tmp_path / "d",
                      fetch=lambda cui, fi, ff, oid: _Obra(111, "OBRA X", aprob))
    assert r["obra_id"] == 111 and r["nombre"] == "OBRA X"
    # el conteo cubre TODAS las secciones: 3 del hito + 1 de la aprobación
    assert r["descargados"] == 4 and r["fallidos"] == 1 and r["error"] is None
    assert {c[0] for c in reg} == {"hito", "informes", "cierre", "aprob"}
    # la caché de la descarga es HERMANA del árbol entregable, nunca su hija:
    # si viviera dentro, el ZIP por CUI empaquetaría cada documento dos veces.
    assert not any(p.name.endswith(".cache") for p in (tmp_path / "d").rglob("*"))
    assert (tmp_path / "d.cache").is_dir()


def test_descargar_cui_sin_aprobacion_no_intenta_esa_descarga(tmp_path, monkeypatch):
    reg = []
    _stub_descargas(monkeypatch, reg)
    r = descargar_cui("2418877", tmp_path / "d",
                      fetch=lambda cui, fi, ff, oid: _Obra(111, "OBRA X", None))
    assert r["obra_id"] == 111
    assert ("aprob",) not in reg     # obra sin expediente → no se llama a la aprobación


def test_descargar_cui_no_resuelto_devuelve_error(tmp_path):
    r = descargar_cui("0000000", tmp_path / "d", fetch=lambda *a, **k: None)
    assert r["obra_id"] is None and r["descargados"] == 0
    assert "no resolvió" in (r["error"] or "")


def test_descargar_cui_seccion_caida_no_tumba_el_resto(tmp_path, monkeypatch):
    # si una sección (informes) revienta, la descarga sigue y devuelve lo del hito
    reg = []
    _stub_descargas(monkeypatch, reg)
    def informes_rompe(*a, **k):
        raise ConnectionError("portal caído")
    monkeypatch.setattr(zip_infoobras, "descargar_informes_control", informes_rompe)
    r = descargar_cui("2418877", tmp_path / "d",
                      fetch=lambda cui, fi, ff, oid: _Obra(111, "OBRA X", None))
    assert r["obra_id"] == 111 and r["descargados"] == 3 and r["error"] is None
    # …pero el reporte YA NO la esconde: la sección caída se declara y cuenta
    # como fallo (issue #81, R5 — antes quedaba solo en un logger.debug).
    assert r["secciones"]["Informes de control"] == {"error": True}
    assert r["fallidos"] == 2          # 1 documento del hito + 1 sección caída
    assert any("Informes de control" in a for a in r["avisos"])


def test_descargar_cui_reintenta_solo_la_seccion_caida(tmp_path, monkeypatch):
    """La caché de la descarga no congela el error: un segundo pedido con el
    mismo `dir_cache` rehace solo los informes y no vuelve a bajar el hito."""
    reg = []
    _stub_descargas(monkeypatch, reg)
    monkeypatch.setattr(zip_infoobras, "descargar_informes_control",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("caído")))
    obra = lambda cui, fi, ff, oid: _Obra(111, "OBRA X", None)  # noqa: E731
    primero = descargar_cui("2418877", tmp_path / "d", fetch=obra,
                            dir_cache=tmp_path / "cache")
    assert primero["secciones"]["Informes de control"] == {"error": True}

    def informes_ok(obra_id, destino, **k):
        reg.append(("informes-ok", obra_id))
        carpeta = Path(destino) / "Informes de control"
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "2020 - I-01.pdf").write_bytes(b"%PDF informe")
        return {"encontrados": 1, "descargados": 1, "anios": [2020]}

    monkeypatch.setattr(zip_infoobras, "descargar_informes_control", informes_ok)
    segundo = descargar_cui("2418877", tmp_path / "d", fetch=obra,
                            dir_cache=tmp_path / "cache")
    assert segundo["secciones"]["Informes de control"]["descargados"] == 1
    assert segundo["fallidos"] == 1          # solo el documento del hito
    assert [c for c in reg if c[0] == "hito"] == [("hito", 111)], (
        "la sección sana no se vuelve a descargar")
    assert (tmp_path / "d" / "Informes de control" / "2020 - I-01.pdf").is_file()
