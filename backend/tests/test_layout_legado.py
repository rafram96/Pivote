"""El candado de los scripts operativos que quedaron en el layout PLANO.

`avance_descargas.py` y `redescargar_documentos.py` leen (y escriben) los
artefactos sueltos en la raíz de `datos_pivote/`. Corridos sobre un job del
formato vigente —una carpeta por job— trabajarían en un sitio que ni el Excel ni
el Panel miran, y el operador no tendría cómo notarlo. El candado los detiene
antes de tocar nada.
"""
from __future__ import annotations

import pytest

from scripts.layout_legado import (
    exigir_layout_plano, extraer_forzar, layout_por_carpeta, mensaje,
)


def _job_por_carpeta(base, job_id, marca="job.json"):
    d = base / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / marca).write_text("{}", encoding="utf-8")
    return d


def _job_plano(base, job_id):
    (base / f"{job_id}.espejo.json").write_text("{}", encoding="utf-8")
    (base / f"{job_id}.descargas").mkdir(exist_ok=True)


def test_detecta_el_layout_vigente_por_cualquiera_de_sus_marcas(tmp_path):
    """Un job a medio correr puede no tener todavía `espejo.json`."""
    for marca in ("job.json", "espejo.json", "enriquecimiento.json"):
        _job_por_carpeta(tmp_path, f"job-{marca}", marca)
        assert layout_por_carpeta(tmp_path, f"job-{marca}") is True


def test_una_carpeta_vacia_no_es_el_layout_vigente(tmp_path):
    """Sin ningún artefacto dentro no hay job que proteger: no se estorba."""
    (tmp_path / "abc123").mkdir()
    assert layout_por_carpeta(tmp_path, "abc123") is False
    exigir_layout_plano(tmp_path, "abc123")          # no levanta


def test_un_job_del_layout_plano_pasa_sin_ruido(tmp_path):
    _job_plano(tmp_path, "viejo1")
    assert layout_por_carpeta(tmp_path, "viejo1") is False
    exigir_layout_plano(tmp_path, "viejo1")          # no levanta


def test_un_job_del_layout_vigente_aborta_con_un_mensaje_legible(tmp_path):
    _job_por_carpeta(tmp_path, "7e9306a321ac")
    with pytest.raises(SystemExit) as exc:
        exigir_layout_plano(tmp_path, "7e9306a321ac")
    texto = str(exc.value)
    assert "7e9306a321ac" in texto
    assert "formato de datos anterior" in texto      # por qué se detiene
    assert "Excel" in texto and "Panel" in texto     # qué se rompería
    assert "--forzar" in texto                       # cómo seguir a sabiendas


def test_forzar_deja_pasar_a_quien_sabe_lo_que_hace(tmp_path):
    _job_por_carpeta(tmp_path, "7e9306a321ac")
    exigir_layout_plano(tmp_path, "7e9306a321ac", forzar=True)   # no levanta


def test_extraer_forzar_lo_saca_de_la_linea_de_comandos():
    assert extraer_forzar(["abc"]) == (["abc"], False)
    assert extraer_forzar(["abc", "--forzar"]) == (["abc"], True)
    assert extraer_forzar(["--forzar", "abc"]) == (["abc"], True)


def test_el_mensaje_no_habla_de_rutas_ni_de_codigo():
    """Lo lee quien opera el servidor, no quien escribió el script."""
    txt = mensaje("abc123")
    assert "datos_pivote" not in txt and "json" not in txt.lower()


@pytest.mark.parametrize("modulo", ["scripts.avance_descargas",
                                    "scripts.redescargar_documentos"])
def test_los_dos_scripts_avisan_en_su_docstring(modulo):
    """El aviso tiene que verse al abrir el archivo, no solo al correrlo."""
    import importlib
    doc = importlib.import_module(modulo).__doc__ or ""
    assert "FORMATO DE DATOS ANTERIOR" in doc
    assert "--forzar" in doc
