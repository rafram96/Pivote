"""
Tests OFFLINE de scraping/seace_abierto.py (T-004, F1).

El corazón es el requisito N°1 del cliente (reunión 29-jul): un mismo CUI tiene
hasta 4 juegos de bases (preinversión / expediente / supervisión / ejecución) y
la selección JAMÁS cruza de tipo. Los títulos de los fixtures son la taxonomía
que él mismo dictó («preinversión del hospital X, expediente técnico X,
supervisión del hospital X, construcción del hospital X»).
"""
from datetime import date

import pytest

from scraping.seace_abierto import (
    TIPO_EJECUCION, TIPO_EXPEDIENTE, TIPO_OTRO, TIPO_PREINVERSION, TIPO_SUPERVISION,
    CacheConosce, clasificar_proceso, codigo_convocatoria,
    crear_session, descargar_archivo, doc_bases_integradas, doc_contrato_firmado,
    archivo_valido, cabecera_valida, extension_documento, procesos_por_cui,
    seleccionar_proceso,
    tipo_esperado,
)


def _proc(ocid, titulo, contratos=None, categoria=None):
    comp = {"ocid": ocid, "tender": {"title": titulo}}
    if categoria:
        comp["tender"]["mainProcurementCategory"] = categoria
    if contratos:
        comp["contracts"] = contratos
    return comp


# los 4 procesos del MISMO hospital (mismo CUI), como los describió el cliente
HOSPITAL = [
    _proc("ocds-dgv273-seacev3-101", "Elaboración del estudio de preinversión del Hospital de Andahuaylas"),
    _proc("ocds-dgv273-seacev3-102", "Contratación del servicio de consultoría para la elaboración del expediente técnico del Hospital de Andahuaylas"),
    _proc("ocds-dgv273-seacev3-103", "Contratación del servicio de supervisión de la ejecución de la obra: Hospital de Andahuaylas"),
    _proc("ocds-dgv273-seacev3-104", "Ejecución de la obra: mejoramiento de los servicios de salud del Hospital de Andahuaylas", categoria="works"),
]


# ── clasificación ────────────────────────────────────────────────────────────

def test_clasificar_la_taxonomia_del_cliente():
    tipos = [clasificar_proceso(p)[0] for p in HOSPITAL]
    assert tipos == [TIPO_PREINVERSION, TIPO_EXPEDIENTE, TIPO_SUPERVISION, TIPO_EJECUCION]


def test_supervision_gana_sobre_expediente():
    # "supervisión de la elaboración del expediente" usa bases DE SUPERVISIÓN
    p = _proc("x", "Supervisión de la elaboración del expediente técnico del Hospital X")
    assert clasificar_proceso(p)[0] == TIPO_SUPERVISION


def test_bienes_no_se_clasifican_por_el_proyecto_mencionado():
    """La categoría goods identifica adquisición, aunque la descripción
    nombre ejecución, expediente o supervisión del proyecto destinatario."""
    for palabra in ("ejecución de obra", "expediente técnico", "supervisión"):
        p = _proc("x", f"Adquisición de bienes para la {palabra} del hospital",
                  categoria="  GOODS  ")
        assert clasificar_proceso(p)[0] == TIPO_OTRO


def test_works_con_equipamiento_conserva_ejecucion():
    p = _proc("x", "Ejecución de obra con equipamiento del hospital",
              categoria=" WORKS ")
    assert clasificar_proceso(p)[0] == TIPO_EJECUCION


def test_saldo_se_marca_sin_cambiar_el_tipo():
    p = _proc("x", "Supervisión del saldo de obra: Hospital de Challhuahuacho")
    tipo, es_saldo = clasificar_proceso(p)
    assert tipo == TIPO_SUPERVISION and es_saldo is True


def test_tipo_esperado_por_camino_y_texto():
    assert tipo_esperado(True) == TIPO_EXPEDIENTE
    assert tipo_esperado(False, "JEFE DE SUPERVISIÓN en la supervisión de la obra") == TIPO_SUPERVISION
    assert tipo_esperado(False, "Residente de obra en la construcción") == TIPO_EJECUCION
    assert tipo_esperado(False, "") == TIPO_SUPERVISION  # default: concursos de supervisión


# ── selección: el requisito N°1 — nunca cruzar de tipo ───────────────────────

@pytest.mark.parametrize("tipo,ocid_ok", [
    (TIPO_EXPEDIENTE, "ocds-dgv273-seacev3-102"),
    (TIPO_SUPERVISION, "ocds-dgv273-seacev3-103"),
    (TIPO_EJECUCION, "ocds-dgv273-seacev3-104"),
])
def test_cada_tipo_elige_su_proceso_y_solo_el_suyo(tipo, ocid_ok):
    r = seleccionar_proceso(HOSPITAL, tipo)
    assert r["elegido"]["ocid"] == ocid_ok
    assert r["seleccion"] == "objeto"


def test_sin_proceso_del_tipo_devuelve_none_jamas_otro_tipo():
    solo_obra = [HOSPITAL[3]]
    r = seleccionar_proceso(solo_obra, TIPO_EXPEDIENTE)
    assert r["elegido"] is None, "antes de cruzar de tipo, se devuelve nada"
    assert "no tiene proceso de expediente" in r["motivo"]
    assert "ejecucion" in r["motivo"]  # y dice qué SÍ había


def test_desempate_por_vigencia_solo_dentro_del_mismo_tipo():
    madre = _proc("m", "Supervisión de la obra: Hospital X",
                  contratos=[{"period": {"startDate": "2019-01-01", "endDate": "2021-06-30"}}])
    saldo = _proc("s", "Supervisión del saldo de obra: Hospital X",
                  contratos=[{"period": {"startDate": "2022-01-01", "endDate": "2023-06-30"}}])
    r = seleccionar_proceso([madre, saldo], TIPO_SUPERVISION,
                            periodo=(date(2022, 3, 1), date(2023, 1, 31)))
    assert r["elegido"]["ocid"] == "s"
    assert r["seleccion"] == "objeto+vigencia"
    assert "solapa" in r["motivo"]


def test_sin_periodo_prefiere_el_proceso_madre():
    madre = _proc("m", "Supervisión de la obra: Hospital X")
    saldo = _proc("s", "Supervisión del saldo de obra: Hospital X")
    r = seleccionar_proceso([saldo, madre], TIPO_SUPERVISION)
    assert r["elegido"]["ocid"] == "m"


# ── documentos ───────────────────────────────────────────────────────────────

def test_bases_integradas_no_administrativas():
    comp = {"ocid": "x", "tender": {"documents": [
        {"documentType": "biddingDocuments", "title": "Bases Administrativas", "url": "u1"},
        {"documentType": "biddingDocuments", "title": "Bases Integradas", "url": "u2"},
        {"documentType": "clarifications", "title": "Pliego absolutorio", "url": "u3"},
    ]}, "contracts": [{"documents": [
        {"documentType": "contractSigned", "title": "Contrato", "url": "u4"},
    ]}]}
    assert doc_bases_integradas(comp)["url"] == "u2"
    assert doc_contrato_firmado(comp)["url"] == "u4"


def test_sin_integradas_devuelve_none_no_las_administrativas():
    comp = {"ocid": "x", "tender": {"documents": [
        {"documentType": "biddingDocuments", "title": "Bases Administrativas", "url": "u1"},
    ]}}
    assert doc_bases_integradas(comp) is None


def test_codigo_convocatoria_sale_del_ocid():
    assert codigo_convocatoria({"ocid": "ocds-dgv273-seacev3-1207427"}) == "1207427"
    assert codigo_convocatoria({"ocid": ""}) is None


def test_bases_conservan_formato_real():
    assert extension_documento({"format": "rar"}) == ".rar"
    assert extension_documento({"format": "application/zip"}) == ".zip"
    assert extension_documento({"format": "application/pdf"}) == ".pdf"


class _RespArchivo:
    status_code = 200

    def __init__(self, contenido):
        self.contenido = contenido

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, _tam):
        yield self.contenido


class _SessionArchivo:
    def __init__(self, contenido):
        self.contenido = contenido
        self.headers = {}
        self.llamadas = []

    def get(self, *args, **kwargs):
        self.llamadas.append((args, kwargs))
        return _RespArchivo(self.contenido)


def test_crear_session_reemplaza_solo_user_agent_de_requests():
    default = _SessionArchivo(b"")
    default.headers["User-Agent"] = "python-requests/2.32.0"
    crear_session(default)
    assert default.headers["User-Agent"].startswith("Mozilla/5.0")
    assert default.headers["Referer"] == "https://bi.seace.gob.pe/"

    personalizado = _SessionArchivo(b"")
    personalizado.headers["User-Agent"] = "Cliente-Controlado/1.0"
    crear_session(personalizado)
    assert personalizado.headers["User-Agent"] == "Cliente-Controlado/1.0"


def test_descarga_prod_omite_referer_y_usa_timeout_de_primer_byte(tmp_path):
    sesion = _SessionArchivo(b"%PDF-1.7")
    destino = tmp_path / "bases.pdf"
    assert descargar_archivo(
        "https://prod1.seace.gob.pe/x?fileCode=abc", destino, session=sesion
    )
    _, parametros = sesion.llamadas[0]
    assert parametros["headers"] == {"Referer": None}
    assert parametros["timeout"] == (30.0, 480.0)


def test_descarga_fuera_de_prod_conserva_referer_de_la_sesion(tmp_path):
    sesion = _SessionArchivo(b"%PDF-1.7")
    destino = tmp_path / "contrato.pdf"
    assert descargar_archivo(
        "https://contratacionesabiertas.oece.gob.pe/contrato",
        destino,
        session=sesion,
    )
    _, parametros = sesion.llamadas[0]
    assert parametros["headers"] == {}
    assert sesion.headers["Referer"] == "https://bi.seace.gob.pe/"


def test_descarga_invalida_elimina_archivo_parcial(tmp_path):
    destino = tmp_path / "bases.pdf"
    assert not descargar_archivo(
        "https://estado/doc", destino, session=_SessionArchivo(b"<html>error")
    )
    assert not destino.exists()
    assert not destino.with_name("bases.pdf.part").exists()


def _zip_bytes(**archivos) -> bytes:
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nombre, cuerpo in archivos.items():
            z.writestr(nombre, cuerpo)
    return buf.getvalue()


def _docx_bytes() -> bytes:
    return _zip_bytes(**{"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"})


@pytest.mark.parametrize(("nombre", "magia"), [
    ("bases.pdf", b"%PDF-1.4"),
    ("bases.zip", _zip_bytes(**{"bases.pdf": "x"})),
    ("bases.rar", b"Rar!\x1a\x07\x01demo"),
])
def test_descarga_archivo_valida_pdf_zip_y_rar(tmp_path, nombre, magia):
    destino = tmp_path / nombre
    assert descargar_archivo("https://estado/doc", destino,
                             session=_SessionArchivo(magia)) is True
    assert destino.read_bytes() == magia


# ── OCDS por red: fakes (nunca red real en tests) ────────────────────────────

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _SessionFake:
    """Firma mínima que usa _get: .get(url, ...) y .headers."""
    def __init__(self, resp):
        self._resp = resp
        self.headers = {}

    def get(self, url, **kw):
        if isinstance(self._resp, Exception):
            raise self._resp
        return self._resp


def test_procesos_por_cui_distingue_vacio_de_caido():
    ok = _SessionFake(_Resp(200, {"records": [
        {"compiledRelease": {"ocid": "ocds-dgv273-seacev3-9", "tender": {"title": "Supervisión X"}}},
    ]}))
    assert len(procesos_por_cui("2418877", session=ok)) == 1

    sin = _SessionFake(_Resp(404))
    assert procesos_por_cui("2418877", session=sin) == []      # dato: no hay

    caido = _SessionFake(ConnectionError("timeout"))
    assert procesos_por_cui("2418877", session=caido) is None  # incertidumbre


# ── cache CONOSCE (disco, sin red) ───────────────────────────────────────────

def _xlsx_contratos(ruta, filas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["CODIGOCONVOCATORIA", "NUM_CONTRATO", "RUC_CONTRATISTA",
               "MONTO_CONTRATADO_TOTAL", "FECHA_SUSCRIPCION_CONTRATO",
               "FECHA_VIGENCIA_INICIAL", "FECHA_VIGENCIA_FINAL", "URLCONTRATO"])
    for f in filas:
        ws.append(f)
    wb.save(ruta)


def test_cache_lee_contratos_de_todos_los_anios(tmp_path):
    _xlsx_contratos(tmp_path / "contratos_2019.xlsx",
                    [["111", "C-1", "20100000001", 5_000_000, "2019-05-02",
                      "2019-05-10", "2021-02-01", "http://pdf/1"]])
    _xlsx_contratos(tmp_path / "contratos_2023.xlsx",
                    [["222", "C-2", "20100000002", 8_000_000, "2023-03-15",
                      "2023-04-01", "2024-12-31", "http://pdf/2"],
                     ["222", "C-2b", "20100000002", 100, "2023-06-01",
                      "2023-06-01", "2023-12-31", "http://pdf/2b"]])
    cache = CacheConosce(tmp_path)
    assert cache.contrato("111")[0]["fecha_suscripcion"] == "2019-05-02"
    assert len(cache.contrato("222")) == 2, "un proceso puede tener varios contratos"
    assert cache.contrato("999") == []


def test_cache_tolera_un_xlsx_corrupto(tmp_path):
    _xlsx_contratos(tmp_path / "contratos_2020.xlsx",
                    [["333", "C-3", "20100000003", 1, "2020-01-01", None, None, None]])
    (tmp_path / "contratos_2021.xlsx").write_bytes(b"esto no es un xlsx")
    cache = CacheConosce(tmp_path)
    assert cache.contrato("333"), "el archivo corrupto no impide leer los sanos"


def test_actualizar_es_atomico_y_tolera_fallos(tmp_path):
    pedidos = []

    class _S:
        headers = {}

        def get(self, url, **kw):
            pedidos.append(url)
            if "2019" in url:
                raise ConnectionError("host caído")
            return type("R", (), {"status_code": 200, "content": b"PK-fake-xlsx"})()

    cache = CacheConosce(tmp_path)
    r = cache.actualizar(datasets=("contratos",), anios=range(2018, 2020), session=_S())
    assert "contratos_2018.xlsx" in r["descargados"]
    assert "contratos_2019.xlsx" in r["fallidos"]
    assert (tmp_path / "contratos_2018.xlsx").read_bytes() == b"PK-fake-xlsx"
    assert not list(tmp_path.glob("*.part")), "nunca queda un archivo a medias"
    meta = (tmp_path / "metadata.json").read_text(encoding="utf-8")
    assert "contratos_2018.xlsx" in meta

    # segunda corrida: el año cerrado ya no se pide de nuevo
    pedidos.clear()
    r2 = cache.actualizar(datasets=("contratos",), anios=range(2018, 2019), session=_S())
    assert r2["vigentes"] == ["contratos_2018.xlsx"] and not pedidos


def test_dos_procesos_del_tipo_sin_solape_elige_el_mas_reciente_y_lo_marca():
    """Caso real (CUI 2279396, prueba de humo 29-jul): supervisiones de 2017 y
    2022 sin vigencias en la fuente. Ni silencio ni azar: el más reciente, con
    la ambigüedad marcada para que aguas abajo se pida verificación."""
    viejo = _proc("v", "Supervisión de la obra: Hospital X")
    viejo["date"] = "2017-06-01T00:00:00Z"
    nuevo = _proc("n", "Supervisión de la obra: Hospital X")
    nuevo["date"] = "2022-09-01T00:00:00Z"
    r = seleccionar_proceso([viejo, nuevo], TIPO_SUPERVISION)
    assert r["elegido"]["ocid"] == "n"
    assert r["ambiguo"] is True
    assert "VERIFICAR" in r["motivo"]
    # y con uno solo del tipo, nada de ambigüedad
    r1 = seleccionar_proceso([nuevo], TIPO_SUPERVISION)
    assert r1.get("ambiguo") in (None, False)


# ── DOC/DOCX (Bases de la Universidad Nacional de Música, Muraria 6-sep-2026) ─

@pytest.mark.parametrize(("doc", "esperada"), [
    ({"format": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "url": "https://x/doc?fileCode=1"}, ".docx"),
    ({"formato": "docx", "url": "https://x/d"}, ".docx"),
    ({"format": "", "url": "https://x/BASES.docx"}, ".docx"),
    ({"format": "application/msword", "url": "https://x/d"}, ".doc"),
    ({"formato": "doc", "url": "https://x/d"}, ".doc"),
    ({"format": "application/zip", "url": "https://x/d"}, ".zip"),
    ({"format": "application/pdf", "url": "https://x/d"}, ".pdf"),
])
def test_extension_documento_reconoce_word(doc, esperada):
    assert extension_documento(doc) == esperada


@pytest.mark.parametrize(("nombre", "magia"), [
    ("bases.docx", _docx_bytes()),
    ("bases.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600),
])
def test_descarga_archivo_acepta_word(tmp_path, nombre, magia):
    destino = tmp_path / nombre
    assert descargar_archivo("https://estado/doc", destino,
                             session=_SessionArchivo(magia)) is True
    assert destino.read_bytes() == magia


def test_cabecera_valida_rechaza_vacio_y_extension_desconocida():
    assert cabecera_valida(".docx", b"PK\x03\x04")
    assert not cabecera_valida(".pdf", b"")            # HTTP 200 sin cuerpo
    assert not cabecera_valida(".xlsx", b"PK\x03\x04")
    assert not cabecera_valida(".docx", b"%PDF-1.4")


@pytest.mark.parametrize(("nombre", "cuerpo"), [
    ("bases.docx", b"PK\x03\x04"),                             # cuatro bytes truncados
    ("bases.docx", _zip_bytes(**{"aviso.txt": "no es Word"})),   # ZIP cualquiera
    ("bases.zip", b"PK\x03\x04demo"),                          # firma sin contenedor
    ("bases.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),          # sin sector OLE
])
def test_descarga_rechaza_contenedores_incompletos(tmp_path, nombre, cuerpo):
    """Revisión de Codex (7-sep): la firma sola aceptaba cualquier ZIP o un
    archivo truncado como Word válido."""
    destino = tmp_path / nombre
    assert descargar_archivo("https://estado/doc", destino,
                             session=_SessionArchivo(cuerpo)) is False
    assert not destino.exists() and not destino.with_name(nombre + ".part").exists()


def test_archivo_valido_admite_extension_final_sobre_temporal(tmp_path):
    tmp = tmp_path / "bases.docx.part"
    tmp.write_bytes(_docx_bytes())
    assert archivo_valido(tmp, extension=".docx")
    assert not archivo_valido(tmp)                      # «.part» no es una extensión conocida


def test_descarga_vacia_no_deja_archivo(tmp_path):
    destino = tmp_path / "contrato.pdf"
    assert descargar_archivo("https://estado/doc", destino,
                             session=_SessionArchivo(b"")) is False
    assert not destino.exists()
