"""El 08-A tiene secciones: la aprobación del expediente vive en la B («Expediente
técnico o documento equivalente», con fecha entre paréntesis) y las
modificaciones durante la ejecución física en la C. Elegir la resolución por
etiqueta, ignorando la sección, tomaba el acto más reciente (auditoría
documental del 13-sep-2026: 7 de 10 documentos «de otra fase»). HTML sintético
con la misma estructura que la ficha real."""
from scraping import mef

_ENLACE = ('<a class="blue" href="/invierte/general/downloadArchivoPublico?idArchivo={id}.pdf'
           '&amp;token=T"><i class="fa fa-paperclip"></i> {texto}</a>')


def _fila(concepto, id_, texto):
    return (f"<tr><td>{concepto}</td><td>INFRAESTRUCTURA</td><td>1,000.00</td>"
            f"<td>{_ENLACE.format(id=id_, texto=texto)}</td></tr>")


def _html():
    return (
        '<html><body>'
        '<div class="opaco"><h4>A. Datos de la fase de Formulación y Evaluación, modificados en la fase de Ejecución</h4></div>'
        '<table><tr><td>Costo de control concurrente (CCC): S/.</td><td>' + _ENLACE.format(id="ccc", texto="Informe CCC (01/01/2020)") + '</td></tr></table>'
        '<div class="opaco"><h4>B. Datos de la fase de Ejecución: Expediente técnico o documento equivalente </h4></div>'
        '<strong>1 Resultado de la elaboración del expediente técnico o documentos equivalentes</strong>'
        '<table><caption>1.1 Estructura del proyecto</caption>'
        + _fila("Construccion de hospital : INFRAESTRUCTURA", "aprob", "N°024-GCPI-FICTICIA-2022 (11/02/2022)")
        + _fila("Otras acciones de equipamiento", "aprob", "N°024-GCPI-FICTICIA-2022 (11/02/2022)")
        + _fila("EXPEDIENTE TÉCNICO: S/. (UEI: FICTICIA)", "contrato", "N°4600099999 (10/06/2019)")
        + _fila("SUPERVISIÓN: S/. (UEI: FICTICIA)", "contrato", "N°4600099999 (10/06/2019)")
        + '</table>'
        '<div class="opaco"><h4>C. Datos de la fase de Ejecución durante la ejecución física </h4></div>'
        '<strong>1 Modificaciones durante la ejecución física</strong>'
        '<table>'
        + _fila("CONSTRUCCION DE HOSPITAL : INFRAESTRUCTURA", "modif", "RESOLUCION 0063-GCPI-FICTICIA-2024 (16/10/2024)")
        + _fila("LIQUIDACIÓN: S/", "modif", "RESOLUCION 0063-GCPI-FICTICIA-2024 - APROBACIÓN DEL (16/10/2024)")
        + '</table></body></html>'
    )


def test_la_aprobacion_sale_de_la_seccion_b_con_su_fecha():
    ficha = mef.parsear_ficha_08a(_html())
    res = ficha["resolucion"]
    assert res["numero"] == "024-GCPI-FICTICIA-2022"
    assert res["fecha"] == "2022-02-11" and res["origen"] == "seccion_b"
    assert res["url"].endswith("idArchivo=aprob.pdf&token=T")


def test_la_modificacion_de_la_seccion_c_no_gana_aunque_sea_mas_reciente_y_se_llame_resolucion():
    ficha = mef.parsear_ficha_08a(_html())
    assert "0063" not in (ficha["resolucion"]["documento"] or "")
    mods = ficha["modificaciones_08a"]
    assert [m["fecha"] for m in mods] == ["2024-10-16"]
    assert "0063-GCPI-FICTICIA-2024" in mods[0]["documento"]


def test_el_contrato_del_expediente_sale_de_la_fila_de_costo():
    ficha = mef.parsear_ficha_08a(_html())
    assert ficha["contrato_et_08a"]["fecha"] == "2019-06-10"
    assert "4600099999" in ficha["contrato_et_08a"]["documento"]


def test_cada_documento_lleva_seccion_concepto_y_fecha():
    docs = {d["url"].split("idArchivo=")[1].split(".pdf")[0]: d for d in mef._documentos_08a(_html())}
    assert docs["ccc"]["seccion"] == "A" and docs["ccc"]["fecha"] == "2020-01-01"
    assert docs["aprob"]["seccion"] == "B" and docs["aprob"]["concepto"].startswith("Construccion")
    assert docs["modif"]["seccion"] == "C"


def test_sin_secciones_cae_a_la_eleccion_por_etiqueta_de_siempre():
    html = ('<html><body>' + _ENLACE.format(id="x", texto="Resolución de aprobación N° 7-2020")
            + _ENLACE.format(id="y", texto="Carta notarial") + '</body></html>')
    ficha = mef.parsear_ficha_08a(html)
    assert ficha["resolucion"]["numero"] == "7-2020" and ficha["resolucion"]["origen"] == "etiqueta"
    assert ficha["resolucion"]["fecha"] is None
    assert ficha["contrato_et_08a"] is None and ficha["modificaciones_08a"] == []


def test_verificar_expediente_propaga_fecha_y_origen():
    ficha = mef.parsear_ficha_08a(_html())
    bloque = mef.verificar_expediente({"cui": "2999999"}, ficha, [])
    assert bloque["resolucion"]["fecha_08a"] == "2022-02-11"
    assert bloque["resolucion"]["origen"] == "seccion_b"
    assert bloque["contrato_et_08a"]["fecha"] == "2019-06-10"
    assert len(bloque["modificaciones_08a"]) == 1
