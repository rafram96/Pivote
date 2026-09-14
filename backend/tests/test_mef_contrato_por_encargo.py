"""El contrato del expediente se elige por ENCARGO: un certificado de supervisión
del expediente lleva el contrato de supervisión, no el del proyectista; y un
contrato suscrito después del fin del certificado no puede sustentarlo
(auditoría documental 13-sep-2026: 4:2, 5:2, 6:1, 10:6 y 15:3). Datos sintéticos."""
from datetime import date

from scraping import mef


def _c(numero, objeto, contratista, monto, fecha):
    return {"numero": numero, "objeto": objeto, "contratista": contratista, "monto": monto,
            "fecha_suscripcion": fecha, "nomenclatura": "", "valor_referencial": None,
            "url_pdf": f"https://x/{numero}.pdf"}


ELAB = _c("001-2017", "CONTRATACIÓN DEL SERVICIO DE ELABORACIÓN DE EXPEDIENTE TÉCNICO DEL PROYECTO H",
          "CONSORCIO PROYECTISTA FICTICIO", 500000.0, date(2017, 3, 1))
SUP = _c("019-2017", "CONSULTORÍA DE OBRA PARA LA SUPERVISIÓN DE LA ELABORACIÓN DEL EXPEDIENTE TÉCNICO DEL PROYECTO H",
         "CONSORCIO SUPERVISOR FICTICIO", 120000.0, date(2017, 8, 1))
SUP_OBRA = _c("050-2019", "SUPERVISIÓN DE LA OBRA DEL PROYECTO H", "CONSORCIO OBRA FICTICIA", 900000.0, date(2019, 1, 1))
TARDIO = _c("053-2026", "CONSULTORÍA DE OBRA PARA EL SALDO DEL EXPEDIENTE TÉCNICO DEL PROYECTO H",
            "CONSORCIO ACTUAL FICTICIO", 300000.0, date(2026, 5, 1))


def _exp(tipo, emisora="CONSORCIO SUPERVISOR FICTICIO", proyecto="Supervisión de la elaboración del expediente técnico del proyecto H",
         fin="2018-10-11"):
    return {"cui": "2999301", "proyecto": proyecto, "entidad_emisora": emisora,
            "fecha_inicial": "2017-08-19", "fecha_final": fin,
            "servicio_declarado": {"tipo": tipo, "texto": proyecto}}


def test_certificado_de_supervision_lleva_el_contrato_de_supervision():
    b = mef.verificar_expediente(_exp("supervision_expediente"), {}, [ELAB, SUP, SUP_OBRA])
    assert b["contrato"]["numero"] == "019-2017"
    assert b["contrato"]["encargo_certificado"] == "supervision"
    assert b["contrato"]["encargo_contrato"] == "supervision"
    assert b["contrato"]["veredicto"] == "ok" and b["contratista"]["veredicto"] == "ok"
    assert "nota_encargo" not in b["contrato"]


def test_supervision_de_obra_no_cuenta_como_supervision_del_expediente():
    b = mef.verificar_expediente(_exp("supervision_expediente", emisora="OTRA S.A."), {}, [ELAB, SUP_OBRA])
    # sin contrato de supervisión del ET cae al de elaboración, rotulado
    assert b["contrato"]["numero"] == "001-2017"
    assert b["contrato"]["encargo_contrato"] == "elaboracion"
    assert b["contrato"]["veredicto"] == "no_verificable"
    assert "supervisión del expediente" in b["contrato"]["nota_encargo"]


def test_certificado_de_elaboracion_conserva_el_contrato_de_siempre():
    b = mef.verificar_expediente(_exp("elaboracion_expediente", emisora="CONSORCIO PROYECTISTA FICTICIO",
                                      proyecto="Elaboración del expediente técnico del proyecto H"),
                                 {}, [ELAB, SUP])
    assert b["contrato"]["numero"] == "001-2017" and b["contrato"]["elegido_por"] == "emisor"
    assert b["contrato"]["encargo_certificado"] == "elaboracion"
    assert "nota_encargo" not in b["contrato"]


def test_sin_tipo_estructurado_el_texto_del_proyecto_decide():
    assert mef.encargo_declarado({"proyecto": "Supervisión del Estudio del Expediente Técnico del proyecto H"}) == "supervision"
    assert mef.encargo_declarado({"proyecto": "Elaboración del expediente técnico del proyecto H"}) == "elaboracion"
    assert mef.encargo_declarado({"proyecto": "Supervisión de la obra del proyecto H"}) == "elaboracion"


def test_contrato_suscrito_despues_del_certificado_queda_fuera():
    b = mef.verificar_expediente(_exp("elaboracion_expediente", emisora="CONSORCIO ACTUAL FICTICIO",
                                      proyecto="Elaboración del expediente técnico del proyecto H"),
                                 {}, [TARDIO, ELAB])
    assert b["contrato"]["numero"] == "001-2017"
    assert b["contratos_posteriores_al_certificado"] == [
        "053-2026 — CONSORCIO ACTUAL FICTICIO (2026-05-01)"]


def test_sin_fecha_final_no_se_descarta_ningun_contrato():
    b = mef.verificar_expediente(_exp("elaboracion_expediente", emisora="CONSORCIO ACTUAL FICTICIO",
                                      proyecto="Elaboración del expediente técnico del proyecto H", fin=None),
                                 {}, [TARDIO, ELAB])
    assert b["contrato"]["numero"] == "053-2026"
    assert "contratos_posteriores_al_certificado" not in b


def test_sin_fecha_final_legible_la_emision_del_certificado_es_la_cota():
    exp = _exp("elaboracion_expediente", emisora="CONSORCIO ACTUAL FICTICIO",
               proyecto="Elaboración del expediente técnico del proyecto H",
               fin="POR VERIFICAR (solo consta el plazo del expediente)")
    exp["fecha_emision"] = "2018-01 (Enero del 2018)"
    b = mef.verificar_expediente(exp, {}, [TARDIO, ELAB])
    assert b["contrato"]["numero"] == "001-2017"
    assert b["contratos_posteriores_al_certificado"] == [
        "053-2026 — CONSORCIO ACTUAL FICTICIO (2026-05-01)"]


def test_fecha_flexible_de_mes_toma_el_ultimo_dia():
    assert mef._fecha_iso_a_date("2018-01 (Enero del 2018)").isoformat() == "2018-01-31"
    assert mef._fecha_iso_a_date("2019-12").isoformat() == "2019-12-31"
    assert mef._fecha_iso_a_date("2019-06-11").isoformat() == "2019-06-11"
    assert mef._fecha_iso_a_date("POR VERIFICAR") is None


def test_filas_repetidas_del_dwh_completan_el_enlace_del_contrato():
    crudo = [
        {"NUM_CONTRATO": "16-2018", "MTO_TOTAL": "1000", "NOM_CONTRATISTA": "X", "DES_PROCESO": "ELABORACION DE EXPEDIENTE", "URL_CONTRATO": ""},
        {"NUM_CONTRATO": "16-2018", "MTO_TOTAL": "1000", "NOM_CONTRATISTA": "X", "DES_PROCESO": "ELABORACION DE EXPEDIENTE", "URL_CONTRATO": "https://x/16.pdf"},
        {"NUM_CONTRATO": "16-2018", "MTO_TOTAL": "1000", "NOM_CONTRATISTA": "X", "DES_PROCESO": "ELABORACION DE EXPEDIENTE", "URL_CONTRATO": "https://x/otro.pdf"},
    ]
    cs = mef.normalizar_contratos(crudo)
    assert len(cs) == 1 and cs[0]["url_pdf"] == "https://x/16.pdf"


def test_el_enlace_del_contrato_se_conserva_haya_o_no_contratos_posteriores():
    # regresión 13-sep-2026: el enlace quedó anidado bajo «posteriores» y el
    # contrato salía sin PDF salvo cuando había contratos tardíos
    b = mef.verificar_expediente(_exp("elaboracion_expediente", emisora="CONSORCIO PROYECTISTA FICTICIO",
                                      proyecto="Elaboración del expediente técnico del proyecto H"),
                                 {}, [ELAB])
    assert b["contrato"]["pdf"] == "https://x/001-2017.pdf"
    assert "contratos_posteriores_al_certificado" not in b


def test_contratos_posteriores_sin_contrato_elegido_no_revienta():
    # regresión 13-sep-2026: 15 de 50 verificaciones cayeron con
    # «'NoneType' object has no attribute 'get'» cuando solo había tardíos
    b = mef.verificar_expediente(_exp("elaboracion_expediente", emisora="OTRA S.A.",
                                      proyecto="Elaboración del expediente técnico del proyecto H"),
                                 {}, [TARDIO])
    assert "contrato" not in b
    assert b["contratos_posteriores_al_certificado"] == [
        "053-2026 — CONSORCIO ACTUAL FICTICIO (2026-05-01)"]
