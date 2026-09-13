"""La descarga de documentos del MEF verifica TLS salvo en los hosts del SEACE,
cuyo servidor antiguo (servlet de contratos) entrega una cadena de certificados
incompleta (13-sep-2026: 14 de 27 contratos de una propuesta quedaban sin
descargar por «unable to get local issuer certificate»)."""
from scraping import mef


def test_hosts_del_seace_no_verifican_tls():
    assert mef._verificar_tls(
        "https://prodapp2.seace.gob.pe/portalseace-uiwd-pub/DownloadContratosFileServlet?fileName=x.pdf") is False
    assert mef._verificar_tls("https://prod3.seace.gob.pe/algo.pdf") is False
    assert mef._verificar_tls("https://seace.gob.pe/x") is False


def test_el_mef_y_el_almacenamiento_nuevo_siguen_verificando():
    assert mef._verificar_tls(
        "https://ofi5.mef.gob.pe/invierte/general/downloadArchivoPublico?idArchivo=a.pdf") is True
    assert mef._verificar_tls(
        "https://objectstorage.us-ashburn-1.oraclecloud.com/n/x/b/BUCKET_PROD_SEACE/o/c.pdf") is True
    # un host que solo CONTIENE la cadena no cuenta como del SEACE
    assert mef._verificar_tls("https://noseace.gob.pe.example.com/x") is True


def test_descarga_pasa_verify_segun_el_host(tmp_path):
    llamadas = []

    class _Resp:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, n):
            yield b"%PDF-1.4 contenido"

    class _Session:
        def get(self, url, **kw):
            llamadas.append(kw.get("verify"))
            return _Resp()

    assert mef.descargar_pdf(_Session(), "https://prodapp2.seace.gob.pe/x.pdf", tmp_path / "a.pdf")
    assert mef.descargar_pdf(_Session(), "https://ofi5.mef.gob.pe/y.pdf", tmp_path / "b.pdf")
    assert llamadas == [False, True]
