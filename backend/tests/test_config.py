"""
Tests de backend/config.py — resolución de la carpeta de datos (PIVOTE_DATA_DIR).
"""
from __future__ import annotations

from pathlib import Path

import config


def test_default_es_datos_pivote_anclado_a_backend(monkeypatch):
    monkeypatch.delenv("PIVOTE_DATA_DIR", raising=False)
    d = config.data_dir()
    assert d.name == "datos_pivote"
    assert d.parent == Path(config.__file__).resolve().parent   # backend/


def test_relativa_se_ancla_a_backend_no_al_cwd(tmp_path, monkeypatch):
    """Correr un script desde otra carpeta NO cambia dónde caen los datos."""
    monkeypatch.setenv("PIVOTE_DATA_DIR", "otra_carpeta/datos")
    monkeypatch.chdir(tmp_path)                                  # CWD ajeno al repo
    d = config.data_dir()
    assert d.is_absolute()
    assert d == Path(config.__file__).resolve().parent / "otra_carpeta" / "datos"


def test_absoluta_se_respeta_tal_cual(tmp_path, monkeypatch):
    monkeypatch.setenv("PIVOTE_DATA_DIR", str(tmp_path / "datos"))
    assert config.data_dir() == tmp_path / "datos"
