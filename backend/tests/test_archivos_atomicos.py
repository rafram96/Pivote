"""Regresiones de escritura atómica ante bloqueos breves de Windows."""
from __future__ import annotations

import json
import threading
import time

import pytest

from infraestructura import archivos_atomicos
from orquestador import repositorio


def test_reemplazo_reintenta_dos_permission_error_y_tiene_exito(
    tmp_path, monkeypatch
):
    origen = tmp_path / "origen.json"
    destino = tmp_path / "destino.json"
    origen.write_text("nuevo", encoding="utf-8")
    destino.write_text("anterior", encoding="utf-8")
    reemplazo_real = archivos_atomicos.os.replace
    llamadas = 0

    def reemplazo_intermitente(ruta_origen, ruta_destino):
        nonlocal llamadas
        llamadas += 1
        if llamadas <= 2:
            raise PermissionError("lector concurrente")
        reemplazo_real(ruta_origen, ruta_destino)

    monkeypatch.setattr(archivos_atomicos.os, "replace", reemplazo_intermitente)

    archivos_atomicos.reemplazar_atomico(
        origen, destino, intentos=3, espera_segundos=0
    )

    assert llamadas == 3
    assert destino.read_text(encoding="utf-8") == "nuevo"
    assert not origen.exists()


def test_reemplazo_agota_intentos_y_propaga_permission_error(
    tmp_path, monkeypatch
):
    origen = tmp_path / "origen.json"
    destino = tmp_path / "destino.json"
    origen.write_text("nuevo", encoding="utf-8")
    destino.write_text("anterior", encoding="utf-8")
    llamadas = 0

    def reemplazo_bloqueado(_ruta_origen, _ruta_destino):
        nonlocal llamadas
        llamadas += 1
        raise PermissionError("destino bloqueado")

    monkeypatch.setattr(archivos_atomicos.os, "replace", reemplazo_bloqueado)

    with pytest.raises(PermissionError, match="destino bloqueado"):
        archivos_atomicos.reemplazar_atomico(
            origen, destino, intentos=3, espera_segundos=0
        )

    assert llamadas == 3
    assert destino.read_text(encoding="utf-8") == "anterior"
    assert origen.read_text(encoding="utf-8") == "nuevo"


def test_escritura_fallida_conserva_anterior_y_limpia_temporal(
    tmp_path, monkeypatch
):
    ruta = tmp_path / "estado.json"
    ruta.write_text('{"version": "anterior"}', encoding="utf-8")

    def reemplazo_bloqueado(_origen, _destino, **_kwargs):
        raise PermissionError("destino bloqueado")

    monkeypatch.setattr(repositorio, "reemplazar_atomico", reemplazo_bloqueado)

    with pytest.raises(PermissionError, match="destino bloqueado"):
        repositorio._escribir_atomico(ruta, '{"version": "nueva"}')

    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "version": "anterior"
    }
    assert list(tmp_path.glob("estado.json.*.tmp")) == []


def test_lectura_concurrente_nunca_observa_json_parcial(tmp_path):
    ruta = tmp_path / "estado.json"
    ruta.write_text('{"version": -1}', encoding="utf-8")
    detener = threading.Event()
    iniciado = threading.Event()
    errores_de_contenido: list[Exception] = []
    versiones: list[int] = []

    def leer_repetidamente():
        iniciado.set()
        while not detener.is_set():
            try:
                dato = json.loads(ruta.read_text(encoding="utf-8"))
                versiones.append(dato["version"])
                time.sleep(0.001)
            except PermissionError:
                # NTFS puede negar transitoriamente la apertura mientras ocurre
                # el reemplazo; eso no equivale a exponer contenido parcial.
                time.sleep(0.001)
                continue
            except Exception as exc:  # pragma: no cover - solo se llena al fallar
                errores_de_contenido.append(exc)

    lector = threading.Thread(target=leer_repetidamente)
    lector.start()
    iniciado.wait(timeout=1)
    try:
        for version in range(100):
            repositorio._escribir_atomico(
                ruta, json.dumps({"version": version, "relleno": "x" * 4096})
            )
    finally:
        detener.set()
        lector.join(timeout=1)

    assert not lector.is_alive()
    assert not errores_de_contenido
    assert versiones
    assert json.loads(ruta.read_text(encoding="utf-8"))["version"] == 99
