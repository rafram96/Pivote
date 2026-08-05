"""Caché documental InfoObras por obra y por job (issues #80 y #81)."""
from __future__ import annotations

import os
from datetime import date

from orquestador.descargas_infoobras import (
    CacheDescargasInfoObras,
    informe_en_periodo,
    purgar_secciones_en_error,
    secciones_en_error,
)
from orquestador.descargas_seace import materializar_archivo


def _corpus(destino, _pendientes=None):
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

    def descargar(destino, _pendientes=None):
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

    def descargar(destino, _pendientes=None):
        llamadas.append(destino)
        return _corpus(destino)

    cache = CacheDescargasInfoObras(raiz)
    nuevo = cache.obtener(99, descargar=descargar)
    assert not nuevo.cache_hit
    assert len(llamadas) == 1
    assert not (parcial / "archivo_incompleto.pdf").exists()

    reutilizado = cache.obtener(
        99,
        descargar=lambda _destino, _pend=None: (_ for _ in ()).throw(
            AssertionError("una caché completa no debe tocar la red")
        ),
    )
    assert reutilizado.cache_hit
    cache.materializar(
        reutilizado, tmp_path / "offline",
        fecha_ini=None, fecha_fin=None,
    )
    assert (tmp_path / "offline/Valorizaciones/2025-01 ENERO/val.pdf").is_file()


def _corpus_con_informes_caidos(destino, pendientes=None):
    """Descarga donde SOLO los informes de control revientan."""
    estado = {"secciones": {}, "avisos": [], "informes_anios": []}
    if pendientes is None or "InfoObras" in pendientes:
        (destino / "Valorizaciones" / "2025-01 ENERO").mkdir(parents=True)
        (destino / "Valorizaciones" / "2025-01 ENERO" / "val.pdf").write_bytes(b"%PDF v")
        estado["secciones"]["InfoObras"] = {"esperados": 1, "descargados": 1}
    if pendientes is None or "Informes de control" in pendientes:
        estado["secciones"]["Informes de control"] = {"error": True}
        estado["avisos"].append("Informes de control: la consulta no pudo completarse.")
    return estado


def test_seccion_en_error_no_se_congela_como_completa(tmp_path):
    """Issue #81 R1: una sección caída publica caché PARCIAL y el siguiente
    pedido reintenta SOLO esa sección, sin volver a bajar las sanas."""
    cache = CacheDescargasInfoObras(tmp_path / "job" / "cache_obras")
    primero = cache.obtener(72056, descargar=_corpus_con_informes_caidos)
    entrada = tmp_path / "job" / "cache_obras" / "72056"

    assert not primero.completa
    assert not (entrada / ".completa").exists()
    assert (entrada / ".parcial").is_file()
    assert secciones_en_error(primero.estado) == ("Informes de control",)
    assert (entrada / "Valorizaciones/2025-01 ENERO/val.pdf").is_file()

    pedidas = []

    def reintento(destino, pendientes=None):
        pedidas.append(pendientes)
        (destino / "Informes de control").mkdir(parents=True)
        (destino / "Informes de control" / "2025 - I-01.pdf").write_bytes(b"%PDF i")
        return {"secciones": {"Informes de control": {"esperados": 1, "descargados": 1}},
                "informes_anios": [2025]}

    segundo = cache.obtener(72056, descargar=reintento)
    assert pedidas == [frozenset({"Informes de control"})]
    assert segundo.completa and segundo.reintentadas == ("Informes de control",)
    assert (entrada / ".completa").is_file() and not (entrada / ".parcial").exists()
    # la sección sana sobrevivió al reintento sin volver a descargarse
    assert (entrada / "Valorizaciones/2025-01 ENERO/val.pdf").is_file()
    assert segundo.estado["secciones"]["InfoObras"] == {"esperados": 1, "descargados": 1}
    assert segundo.estado["informes_anios"] == [2025]
    assert segundo.estado["avisos"] == []      # el aviso caducó con el error

    tercero = cache.obtener(
        72056,
        descargar=lambda _d, _p=None: (_ for _ in ()).throw(
            AssertionError("una caché ya completa no vuelve a la fuente")))
    assert tercero.cache_hit


def test_reintento_fallido_conserva_el_corpus_publicado(tmp_path):
    cache = CacheDescargasInfoObras(tmp_path / "cache_obras")
    cache.obtener(72056, descargar=_corpus_con_informes_caidos)

    def revienta(_destino, _pendientes=None):
        raise ConnectionError("portal caído")

    try:
        cache.obtener(72056, descargar=revienta)
    except ConnectionError:
        pass
    entrada = tmp_path / "cache_obras" / "72056"
    assert (entrada / "Valorizaciones/2025-01 ENERO/val.pdf").is_file()
    assert (entrada / ".parcial").is_file()
    assert not list((tmp_path / "cache_obras").glob(".*.part"))


def test_purga_de_revision_desatasca_una_cache_completa_con_error(tmp_path):
    """Compatibilidad: un job viejo pudo publicar `.completa` con una sección en
    error. Resolver la revisión debe poder forzar el reintento de esa sección."""
    raiz = tmp_path / "cache_obras"
    cache = CacheDescargasInfoObras(raiz)
    cache.obtener(72056, descargar=_corpus_con_informes_caidos)
    entrada = raiz / "72056"
    (entrada / "Informes de control").mkdir()
    (entrada / "Informes de control" / "resto.pdf").write_bytes(b"%PDF resto")
    (entrada / ".completa").write_text("ok\n", encoding="utf-8")   # marca heredada
    (entrada / ".parcial").unlink()

    assert cache.obtener(
        72056,
        descargar=lambda _d, _p=None: (_ for _ in ()).throw(
            AssertionError("una caché heredada sigue siendo válida tal cual"))
    ).cache_hit

    assert purgar_secciones_en_error(raiz, 72056) == ("Informes de control",)
    assert not (entrada / "Informes de control").exists()
    assert (entrada / "Valorizaciones/2025-01 ENERO/val.pdf").is_file()

    pedidas = []
    cache.obtener(72056, descargar=lambda d, p=None: (
        pedidas.append(p) or {"secciones": {"Informes de control": {
            "esperados": 0, "descargados": 0}}}))
    assert pedidas == [frozenset({"Informes de control"})]
    assert (entrada / ".completa").is_file()
    # una caché sana no se purga: la revisión la reutiliza sin tocar el portal
    assert purgar_secciones_en_error(raiz, 72056) == ()
    assert purgar_secciones_en_error(raiz, 999999) == ()


def test_recoleccion_de_carpetas_part_huerfanas(tmp_path):
    """Issue #81 R4: un kill duro deja `.{obra}.{uuid}.part`; nadie los recogía."""
    raiz = tmp_path / "cache_obras"
    cache = CacheDescargasInfoObras(raiz)
    cache.obtener(72056, descargar=_corpus)
    huerfano = raiz / f".72056.{'a1b2c3d4' * 4}.part"
    (huerfano / "Valorizaciones").mkdir(parents=True)
    (huerfano / "Valorizaciones" / "a medias.pdf").write_bytes(b"%PDF")

    assert cache.recolectar_temporales() == 1
    assert not huerfano.exists()
    assert (raiz / "72056" / ".completa").is_file()
    assert (raiz / "72056/Valorizaciones/2025-01 ENERO/val.pdf").is_file()
    assert cache.recolectar_temporales() == 0
    assert CacheDescargasInfoObras(tmp_path / "no-existe").recolectar_temporales() == 0


_ESPEJO_UNA_EXPERIENCIA = {
    "_meta": {"analisis_id": "r1", "concurso": "CP-TEST", "postor": "P"},
    "profesionales": [{
        "n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "N",
        "experiencias": [{
            "n": 1, "proyecto": "Supervisión del Hospital",
            "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31",
        }],
    }],
}


def test_job_no_congela_la_seccion_caida_y_la_reintenta_en_la_pasada_siguiente(
        tmp_path, monkeypatch):
    """Recorrido completo de R1 sobre `descargar_documentos_job` + índice del ZIP:
    primera pasada con los informes caídos (error visible, resto sano), segunda
    pasada que reintenta SOLO esa sección y promueve la caché a completa."""
    import zipfile

    from entregables import construir_zip_infoobras, zip_infoobras
    from orquestador.etapas_reales import descargar_documentos_job
    from orquestador.repositorio import carpeta_job

    llamadas: list[str] = []

    def hito(obra_id, destino, **_k):
        llamadas.append("hito")
        (destino / "Valorizaciones" / "2020-01 ENERO").mkdir(parents=True)
        (destino / "Valorizaciones" / "2020-01 ENERO" / "val.pdf").write_bytes(b"%PDF v")
        return {"descargados": 1, "fallidos": 0,
                "inventario": {"avances": [{"documentos": [{"x": 1}]}], "obra": {}}}

    def cierre(obra_id, destino, **_k):
        llamadas.append("cierre")
        return {"encontrados": 0, "descargados": 0}

    def informes_caidos(*_a, **_k):
        llamadas.append("informes-error")
        raise ConnectionError("portal caído")

    monkeypatch.setattr(zip_infoobras, "descargar_documentos_obra_por_hito", hito)
    monkeypatch.setattr(zip_infoobras, "descargar_datos_cierre", cierre)
    monkeypatch.setattr(zip_infoobras, "descargar_informes_control", informes_caidos)

    enr = {"1:1": {"cui": "1", "obra": {"obra_id": 72056}}}
    descargar_documentos_job(_ESPEJO_UNA_EXPERIENCIA, enr, "job-r1", tmp_path)

    base = carpeta_job(tmp_path, "job-r1") / "descargas"
    destino = base / "P1_E1"
    manifiesto = enr["1:1"]["descargas_reales"]
    assert manifiesto["secciones"]["Informes de control"] == {"estado": "error"}
    assert manifiesto["secciones"]["InfoObras"]["estado"] == "completa"
    assert (destino / "Valorizaciones/2020-01 ENERO/val.pdf").is_file()
    # el corpus quedó incompleto → la experiencia NO se da por terminada
    assert not (base / "P1_E1.ok").exists()
    assert not manifiesto["completada"]

    indice = _indice_del_zip(construir_zip_infoobras(
        _ESPEJO_UNA_EXPERIENCIA, {(1, 1): destino}, tmp_path / "r1-a.zip",
        enriquecimiento=enr))
    assert ("SECCIÓN Informes de control: la fuente no respondió en esta corrida "
            "(se puede reintentar)") in indice
    assert "ADVERTENCIA: Informes de control: la consulta no pudo completarse." in indice

    # ── segunda pasada: la fuente vuelve, con 3 informes de OTROS años ──────
    def informes_ok(obra_id, destino_cache, **_k):
        llamadas.append("informes-ok")
        carpeta = destino_cache / "Informes de control"
        carpeta.mkdir(parents=True, exist_ok=True)
        for n in (1, 2, 3):
            (carpeta / f"2018 - I-0{n}.pdf").write_bytes(b"%PDF informe")
        return {"encontrados": 3, "descargados": 3, "anios": [2018, 2018, 2018]}

    monkeypatch.setattr(zip_infoobras, "descargar_informes_control", informes_ok)
    descargar_documentos_job(_ESPEJO_UNA_EXPERIENCIA, enr, "job-r1", tmp_path)

    assert llamadas == ["hito", "informes-error", "cierre", "informes-ok"], (
        "el reintento solo vuelve por la sección caída")
    entrada = carpeta_job(tmp_path, "job-r1") / "cache_obras" / "72056"
    assert (entrada / ".completa").is_file() and not (entrada / ".parcial").exists()
    assert (base / "P1_E1.ok").is_file()
    manifiesto = enr["1:1"]["descargas_reales"]
    assert manifiesto["completada"]
    assert manifiesto["secciones"]["Informes de control"] == {
        "estado": "sin_documentos", "esperados": 0, "descargados": 0, "publicados": 3}
    # los informes existen pero son de 2018: no se materializan en una
    # experiencia de 2020 (y el índice ya no los llama "0 disponibles")
    assert not (destino / "Informes de control").exists()

    indice = _indice_del_zip(construir_zip_infoobras(
        _ESPEJO_UNA_EXPERIENCIA, {(1, 1): destino}, tmp_path / "r1-b.zip",
        enriquecimiento=enr))
    assert ("SECCIÓN Informes de control: los informes de control publicados no "
            "corresponden al periodo de este certificado (3 publicados, todos de "
            "otros años)") in indice
    assert "Informes de control: sin documentos publicados" not in indice
    # la ausencia REAL conserva su texto: la obra no publicó datos de cierre
    assert "SECCIÓN Datos de cierre: sin documentos publicados (0 disponibles)" in indice
    assert "ADVERTENCIA" not in indice


def _indice_del_zip(ruta) -> str:
    import zipfile
    with zipfile.ZipFile(ruta) as zf:
        return zf.read("indice.txt").decode("utf-8")


def test_job_recolecta_los_part_huerfanos_de_la_cache(tmp_path):
    """R4 dentro del job: un `.part` plantado desaparece en la corrida siguiente
    y las entradas publicadas quedan intactas."""
    from orquestador.etapas_reales import descargar_documentos_job
    from orquestador.repositorio import carpeta_job

    def descargar(_obra_id, destino):
        (destino / "Valorizaciones").mkdir(parents=True, exist_ok=True)
        (destino / "Valorizaciones" / "val.pdf").write_bytes(b"%PDF v")

    enr = {"1:1": {"cui": "1", "obra": {"obra_id": 72056}}}
    descargar_documentos_job(_ESPEJO_UNA_EXPERIENCIA, enr, "job-part", tmp_path,
                             descargar=descargar)
    raiz = carpeta_job(tmp_path, "job-part") / "cache_obras"
    huerfano = raiz / f".72056.{'0f1e2d3c' * 4}.part"
    (huerfano / "Valorizaciones").mkdir(parents=True)
    (huerfano / "Valorizaciones" / "a medias.pdf").write_bytes(b"%PDF")

    descargar_documentos_job(_ESPEJO_UNA_EXPERIENCIA, enr, "job-part", tmp_path,
                             descargar=descargar)
    assert not huerfano.exists()
    assert (raiz / "72056" / ".completa").is_file()


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
