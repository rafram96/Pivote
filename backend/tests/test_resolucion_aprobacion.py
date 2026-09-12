"""
Lectura de la resolución que aprobó el expediente técnico (08-A del MEF).

Textos sintéticos que reproducen los patrones vistos en la medición del 5-sep:
  · consorcio con nombre de topónimo («Consorcio Santiago» vs «distrito de
    Santiago») → NO confirma;
  · nombre antes del rol («MENDOZA & TAPIA S.A.C. - ENTIDAD PRIVADA SUPERVISORA»)
    con ruido de OCR («&» → «8») → confirma;
  · «EL CONSULTOR CONSORCIO ESPERANZA» → confirma;
  · resolución que nombra a OTRO consultor → nombra_otro;
  · la fecha del encabezado gana a las fechas «DE FECHA …» de los considerandos.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reglas.cruces_fechas import fecha_aprobacion_expediente
from validacion.resolucion_aprobacion import (
    coincide_emisor, consultores_nombrados, fecha_emision, interpretar_resolucion,
    leer_resolucion, limpiar_razon_social, normalizar, plausibilidad_fecha,
)

CABECERA = ("RESOLUCION GERENCIAL REGIONAL N° 274-2019-GRH/GR. Huaraz, 18 de junio de 2019. "
            "VISTO: el Informe N° 120-2019 de fecha 03 de junio de 2019 y el Oficio N° 88 "
            "de fecha 10 de junio de 2019; CONSIDERANDO: ")


def test_normaliza_ruido_ocr_y_sufijos():
    assert normalizar("Mendoza $: Tapia S.A.C.") == "MENDOZA TAPIA S.A.C."
    assert limpiar_razon_social("MENDOZA & TAPIA S.A.C.") == "MENDOZA TAPIA"
    assert limpiar_razon_social("AYEP Contratistas Generales E.I.R.L.") == "AYEP CONTRATISTAS GENERALES"
    assert limpiar_razon_social("Consorcio Santiago") == "CONSORCIO SANTIAGO"


def test_fecha_emision_prefiere_la_del_encabezado_no_las_citadas():
    assert fecha_emision(normalizar(CABECERA)) == date(2019, 6, 18)
    # sin encabezado legible, cae a la primera fecha que haya
    assert fecha_emision(normalizar("…, de fecha 05 de setiembre del 2025, …")) == date(2025, 9, 5)
    assert fecha_emision(normalizar("sin fechas aquí")) is None


def test_consorcio_con_nombre_de_toponimo_no_confirma():
    T = normalizar(CABECERA + "QUE, mediante el Contrato N° 82-2016-JUS a favor del contratista "
                   "JORGE YARLAQUE MONTALVO, para la elaboración del expediente técnico de la "
                   "obra en el distrito de Santiago, provincia de Ica, departamento de Ica; …")
    veredicto, detalle = coincide_emisor(T, "CONSORCIO SANTIAGO")
    assert veredicto == "nombra_otro", (veredicto, detalle)
    assert "YARLAQUE" in detalle


def test_nombre_antes_del_rol_con_ruido_ocr_confirma():
    T = normalizar(CABECERA + "QUE, mediante Carta N° 01-2025 MENDOZA $: TAPIA S.A.C. - ENTIDAD "
                   "PRIVADA SUPERVISORA remite a la Universidad el expediente técnico …")
    assert coincide_emisor(T, "MENDOZA & TAPIA S.A.C.")[0] == "confirma"


def test_consultor_tras_el_rol_confirma():
    T = normalizar(CABECERA + "QUE, mediante Contrato N° 045-2023-UNMSM entre la Universidad "
                   "Nacional Mayor de San Marcos y el consultor CONSORCIO ESPERANZA; que la "
                   "Oficina de Estudios …")
    assert coincide_emisor(T, "Consorcio Esperanza")[0] == "confirma"
    assert any("CONSORCIO ESPERANZA" in c for c in consultores_nombrados(T))


def test_resolucion_que_no_nombra_a_nadie():
    T = normalizar(CABECERA + "SE RESUELVE: APROBAR el expediente técnico del proyecto con "
                   "código único de inversiones 2513467 por un monto de S/ 1,000.00.")
    assert coincide_emisor(T, "NKP CONTRATISTAS GENERALES E.I.R.L.")[0] == "no_nombra"


def test_interpretar_arma_el_bloque_completo():
    texto = (CABECERA + "QUE, mediante Contrato N° 045-2023-UNMSM entre la Universidad y el "
             "consultor CONSORCIO ESPERANZA se elaboró el expediente técnico del proyecto "
             "con CUI 2234021; SE RESUELVE: APROBAR el expediente técnico …")
    r = interpretar_resolucion(texto, "Consorcio Esperanza", cui="2234021",
                               numero_citado="274-2019-GRH/GR")
    assert r["legible"] is True
    assert r["fecha"] == "2019-06-18"
    assert r["coincide_emisor"] == "confirma"
    assert r["cita_cui"] is True
    assert r["numero_citado_coincide"] is True
    assert "18/06/2019" in r["resumen"] and "Nombra al emisor" in r["resumen"]
    # número citado que NO está en el documento
    r2 = interpretar_resolucion(texto, "Consorcio Esperanza", numero_citado="999-2020-XYZ")
    assert r2["numero_citado_coincide"] is False


def test_texto_ilegible_no_inventa_nada():
    r = interpretar_resolucion("   ", "Consorcio Esperanza", cui="1")
    assert r["legible"] is False and r["fecha"] is None
    assert r["coincide_emisor"] == "sin_texto"


def test_leer_resolucion_con_descarga_y_lectura_inyectadas(tmp_path):
    def descargar(url, ruta: Path) -> bool:
        ruta.write_bytes(b"%PDF-1.4 fake")
        return True

    def extraer(ruta: Path):
        return (CABECERA + "y el consultor CONSORCIO ESPERANZA; …", "ocr", 2)

    out = leer_resolucion("https://mef/x.pdf", tmp_path / "res", emisor="Consorcio Esperanza",
                          cui="2234021", numero="274-2019-GRH/GR",
                          descargar=descargar, extraer_texto=extraer)
    assert out and out["fecha"] == "2019-06-18" and out["coincide_emisor"] == "confirma"
    assert out["texto_fuente"] == "ocr" and out["paginas"] == 2
    assert (tmp_path / "res" / out["archivo"]).exists()
    # el archivo ya existe → no vuelve a descargar (segunda llamada sin descargador real)
    out2 = leer_resolucion("https://mef/x.pdf", tmp_path / "res", emisor="Consorcio Esperanza",
                           cui="2234021", numero="274-2019-GRH/GR",
                           descargar=lambda u, r: False, extraer_texto=extraer)
    assert out2 and out2["fecha"] == "2019-06-18"


def test_leer_resolucion_falla_en_silencio(tmp_path):
    assert leer_resolucion("https://mef/x.pdf", tmp_path, emisor="X", cui="1",
                           descargar=lambda u, r: False) is None


def _enr_regla_b(coincide: str, fecha_res: str = "2019-06-18"):
    return {"cui": "2450843",
            "verificacion_expediente": {"verificado_en_mef": True,
                                        "contratista": {"valor": "OTRO", "veredicto": "no_verificable"},
                                        "resolucion": {"numero": "274-2019-GRH/GR",
                                                       "fecha": fecha_res, "veredicto": "ok"}},
            "resolucion_aprobacion": {"legible": True, "fecha": fecha_res,
                                      "coincide_emisor": coincide,
                                      "detalle_emisor": "JORGE YARLAQUE MONTALVO" if coincide == "nombra_otro" else None}}


def test_regla_b_compara_cuando_la_resolucion_nombra_al_emisor():
    from reglas.cruces_fechas import COINCIDE, DISPARA, evaluar_termino_vs_aprobacion
    # término declarado 5 meses DESPUÉS de la aprobación → dispara
    c = evaluar_termino_vs_aprobacion(_enr_regla_b("confirma"), {"fecha_final": "2019-11-30"})
    assert c.resultado == DISPARA and c.fecha_fuente == "2019-06-18"
    # término antes de la aprobación → coincide
    c = evaluar_termino_vs_aprobacion(_enr_regla_b("confirma"), {"fecha_final": "2019-05-30"})
    assert c.resultado == COINCIDE


def test_regla_b_se_abstiene_si_la_resolucion_nombra_a_otro():
    from reglas.cruces_fechas import POR_CONFIRMAR, evaluar_termino_vs_aprobacion
    c = evaluar_termino_vs_aprobacion(_enr_regla_b("nombra_otro"), {"fecha_final": "2019-11-30"})
    assert c.resultado == POR_CONFIRMAR
    assert "YARLAQUE" in c.motivo and "no a quien emitió" in c.motivo


def test_regla_b_sin_nombre_en_la_resolucion_sigue_exigiendo_el_contrato():
    from reglas.cruces_fechas import POR_CONFIRMAR, evaluar_termino_vs_aprobacion
    c = evaluar_termino_vs_aprobacion(_enr_regla_b("no_nombra"), {"fecha_final": "2019-11-30"})
    assert c.resultado == POR_CONFIRMAR   # el contratista MEF no coincide → gate como antes


def test_regla_b_prefiere_la_fecha_leida_de_la_resolucion():
    enr = {"verificacion_expediente": {"verificado_en_mef": True,
                                       "resolucion": {"numero": "274-2019-GRH/GR",
                                                      "fecha": "2019-06-18", "veredicto": "ok"}},
           # la fecha del hito InfoObras es deducida del nombre del archivo y posterior
           "aprobacion_expediente": {"fecha": "2019-09-01", "nombre": "RGR 274-2019"}}
    f, fuente, inferida = fecha_aprobacion_expediente(enr)
    assert f == date(2019, 6, 18)
    assert inferida is False
    assert "MEF" in fuente.upper() or "resoluci" in fuente.lower()


# ── Plausibilidad de la fecha (fechas imposibles vistas en corrida real) ──────
# Reproducen, con datos ficticios, los dos casos que dispararon una alerta roja
# falsa: una resolución «…-2025» leída con fecha de 2011 (fecha citada en el
# cuerpo) y una «…-2026» leída con fecha del año anterior.

CABECERA_2025 = ("RESOLUCION RECTORAL N° 004321-2025-R/UNIV. Lima, 22 de marzo de 2011. "
                 "VISTO: el expediente administrativo; Lima, 14 de agosto de 2025; "
                 "CONSIDERANDO: que la Oficina General de Infraestructura ")


def test_plausibilidad_acepta_fecha_coherente_con_el_numero():
    ok, motivo = plausibilidad_fecha(date(2025, 8, 14), numero="004321-2025-R/UNIV")
    assert ok is True and motivo is None
    # ±1 año: una resolución de enero puede numerarse con el año anterior
    assert plausibilidad_fecha(date(2026, 1, 5), numero="004321-2025-R/UNIV")[0] is True
    # número con año de dos cifras («-25» → 2025)
    assert plausibilidad_fecha(date(2025, 8, 14), numero="N° 123-25-GM-MDT")[0] is True


def test_plausibilidad_descarta_fecha_de_otro_ano_que_el_numero():
    ok, motivo = plausibilidad_fecha(date(2011, 3, 22), numero="004321-2025-R/UNIV")
    assert ok is False
    assert motivo == ("el año de la fecha no corresponde al año del número de "
                      "la resolución (2025)")
    # el segundo caso real: resolución 2026 leída con fecha de 2025 pasa (±1),
    # pero una de 2019 no
    assert plausibilidad_fecha(date(2019, 4, 29), numero="002-2026-GM-MDX")[0] is False
    # numeración anual: «002-2026» no puede ser de abril de 2025 (caso real, OCR 5/6)
    assert plausibilidad_fecha(date(2025, 4, 29), numero="002-2026-GM-MDX")[0] is False
    assert plausibilidad_fecha(date(2025, 12, 30), numero="002-2026-GM-MDX")[0] is True


def test_plausibilidad_descarta_fecha_anterior_al_contrato_futura_o_prehistorica():
    ok, motivo = plausibilidad_fecha(date(2024, 1, 10), fecha_contrato="2024-05-03")
    assert ok is False
    assert motivo == ("la fecha es anterior a la firma del contrato del "
                      "expediente (03/05/2024)")
    # el contrato también se acepta como `date`
    assert plausibilidad_fecha(date(2024, 1, 10), fecha_contrato=date(2024, 5, 3))[0] is False
    assert plausibilidad_fecha(date(2024, 6, 1), fecha_contrato="2024-05-03")[0] is True
    # futura respecto de «hoy» (inyectable para que el test no envejezca)
    assert plausibilidad_fecha(date(2030, 1, 1), hoy=date(2026, 9, 5)) == (
        False, "la fecha es posterior a hoy")
    assert plausibilidad_fecha(date(1998, 7, 1)) == (
        False, "fecha fuera del rango de Invierte.pe")


def test_fecha_emision_sin_numero_ni_contrato_se_comporta_como_antes():
    T = normalizar(CABECERA_2025)
    assert fecha_emision(T) == date(2011, 3, 22)     # primera del encabezado
    assert fecha_emision(normalizar(CABECERA)) == date(2019, 6, 18)


def test_fecha_emision_salta_la_implausible_y_toma_la_siguiente():
    T = normalizar(CABECERA_2025)
    assert fecha_emision(T, numero="004321-2025-R/UNIV") == date(2025, 8, 14)
    # si la única fecha del encabezado es implausible, no inventa ninguna
    solo_mala = normalizar("RESOLUCION N° 004321-2025-R/UNIV. Lima, 22 de marzo de 2011. "
                           "CONSIDERANDO: que la Oficina General de Infraestructura evaluó "
                           "el expediente técnico y emitió opinión favorable; SE RESUELVE: ")
    assert fecha_emision(solo_mala, numero="004321-2025-R/UNIV") is None
    # el contrato también descarta: ambas fechas son previas a la firma
    assert fecha_emision(T, fecha_contrato="2026-01-15") is None


def test_interpretar_publica_la_fecha_descartada_y_el_motivo():
    texto = (CABECERA_2025 + "QUE, mediante Contrato N° 088-2025-UNIV la Universidad y el "
             "consultor CONSORCIO ESPERANZA suscribieron la elaboración del expediente "
             "técnico del proyecto con CUI 2234021; SE RESUELVE: APROBAR el expediente …")
    r = interpretar_resolucion(texto, "Consorcio Esperanza", "2234021", "004321-2025")
    assert r["fecha"] == "2025-08-14"                      # la segunda, plausible
    assert r["fecha_descartada"] == "2011-03-22"           # trazabilidad
    assert "no corresponde al año del número" in r["fecha_motivo"]
    assert ("La fecha leída (22/03/2011) no es plausible para la resolución "
            "004321-2025 y se omitió") in r["resumen"]
    assert "Documento MEF del 14/08/2025; tipo de acto por confirmar." in r["resumen"]


def test_interpretar_sin_ninguna_fecha_plausible_deja_fecha_en_none():
    texto = ("RESOLUCION RECTORAL N° 004321-2025-R/UNIV. Lima, 22 de marzo de 2011. "
             "CONSIDERANDO: QUE, mediante Contrato N° 088-2025-UNIV la Universidad y el "
             "consultor CONSORCIO ESPERANZA suscribieron la elaboración del expediente "
             "técnico del proyecto con CUI 2234021; SE RESUELVE: APROBAR el expediente …")
    r = interpretar_resolucion(texto, "Consorcio Esperanza", "2234021", "004321-2025")
    assert r["legible"] is True and r["fecha"] is None
    assert r["fecha_descartada"] == "2011-03-22"
    assert r["fecha_motivo"] and "2025" in r["fecha_motivo"]
    assert "no es plausible" in r["resumen"]
    assert "no muestra una fecha legible" not in r["resumen"]
    assert r["coincide_emisor"] == "confirma"      # el resto de la lectura sigue igual
    # sin número ni contrato la fecha de 2011 se publica como antes
    r2 = interpretar_resolucion(texto, "Consorcio Esperanza", "2234021")
    assert r2["fecha"] == "2011-03-22" and r2["fecha_descartada"] is None


def test_texto_ilegible_trae_los_campos_de_traza_vacios():
    r = interpretar_resolucion("   ", "Consorcio Esperanza", cui="1")
    assert r["fecha_descartada"] is None and r["fecha_motivo"] is None


def test_leer_resolucion_descarta_la_fecha_implausible_del_encabezado(tmp_path):
    def descargar(url, ruta: Path) -> bool:
        ruta.write_bytes(b"%PDF-1.4 fake")
        return True

    def extraer(ruta: Path):
        return (CABECERA_2025 + "y el consultor CONSORCIO ESPERANZA elaboró el expediente "
                "técnico; SE RESUELVE: APROBAR …", "ocr", 3)

    out = leer_resolucion("https://mef/x.pdf", tmp_path / "res", emisor="Consorcio Esperanza",
                          cui="2234021", numero="004321-2025-R/UNIV",
                          descargar=descargar, extraer_texto=extraer)
    assert out and out["fecha"] == "2025-08-14"
    assert out["fecha_descartada"] == "2011-03-22"
    assert "no corresponde al año del número" in out["fecha_motivo"]
    assert "no es plausible" in out["resumen"]


def test_leer_resolucion_usa_la_fecha_del_contrato_del_expediente(tmp_path):
    def descargar(url, ruta: Path) -> bool:
        ruta.write_bytes(b"%PDF-1.4 fake")
        return True

    def extraer(ruta: Path):
        return (CABECERA_2025 + "y el consultor CONSORCIO ESPERANZA elaboró el expediente "
                "técnico; SE RESUELVE: APROBAR …", "capa", 1)

    out = leer_resolucion("https://mef/y.pdf", tmp_path / "res2", emisor="Consorcio Esperanza",
                          cui="2234021", numero="004321-2025-R/UNIV",
                          fecha_contrato="2025-10-01",
                          descargar=descargar, extraer_texto=extraer)
    # 22/03/2011 cae por el año del número y 14/08/2025 por ser previa al contrato
    assert out and out["fecha"] is None
    assert out["fecha_descartada"] == "2011-03-22"


def test_leer_resolucion_reutiliza_el_texto_guardado_junto_al_pdf(tmp_path):
    """El OCR es lo caro: la segunda lectura del mismo PDF (otra experiencia con el
    mismo CUI) no vuelve a extraer texto. Un «sin_texto» no se reutiliza."""
    extracciones = []

    def descargar(url, ruta: Path) -> bool:
        ruta.write_bytes(b"%PDF-1.4 fake")
        return True

    def extraer(ruta: Path):
        extracciones.append(ruta.name)
        return (CABECERA + "y el consultor CONSORCIO ESPERANZA; …", "ocr", 2)

    args = dict(emisor="Consorcio Esperanza", cui="2234021", numero="274-2019-GRH/GR",
                descargar=descargar, extraer_texto=extraer)
    out = leer_resolucion("https://mef/x.pdf", tmp_path / "res", **args)
    assert out["fecha"] == "2019-06-18" and out["texto_reutilizado"] is False
    sidecar = tmp_path / "res" / (out["archivo"] + ".texto.json")
    assert sidecar.exists()

    out2 = leer_resolucion("https://mef/x.pdf", tmp_path / "res", **args)
    assert out2["fecha"] == "2019-06-18" and out2["coincide_emisor"] == "confirma"
    assert out2["texto_reutilizado"] is True and out2["paginas"] == 2
    assert extracciones == [out["archivo"]]          # una sola extracción

    # otro tope de páginas → el texto guardado no vale
    leer_resolucion("https://mef/x.pdf", tmp_path / "res", max_pag=8, **args)
    assert len(extracciones) == 2

    # sin Tesseract la lectura queda «sin_texto» y NO se recuerda
    def sin_texto(ruta: Path):
        extracciones.append("sin")
        return ("", "sin_texto", 2)

    args2 = {**args, "extraer_texto": sin_texto}
    leer_resolucion("https://mef/y.pdf", tmp_path / "res2", **args2)
    leer_resolucion("https://mef/y.pdf", tmp_path / "res2", **args2)
    assert extracciones[-2:] == ["sin", "sin"]


def test_texto_guardado_se_invalida_si_cambia_el_pdf_aunque_pese_igual(tmp_path):
    """Revisión de Codex (7-sep): sustituir el PDF por otro del mismo tamaño
    reutilizaba la fecha del anterior."""
    extracciones = []

    def descargar_a(url, ruta: Path) -> bool:
        ruta.write_bytes(b"%PDF-1.4 version A")
        return True

    def extraer(ruta: Path):
        cuerpo = ruta.read_bytes()
        extracciones.append(cuerpo)
        cabecera = CABECERA if b"version A" in cuerpo else CABECERA.replace("18 de junio", "19 de junio")
        return (cabecera + "y el consultor CONSORCIO ESPERANZA; …", "ocr", 1)

    args = dict(emisor="Consorcio Esperanza", cui="2234021", numero="274-2019-GRH/GR",
                extraer_texto=extraer)
    out = leer_resolucion("https://mef/x.pdf", tmp_path / "res", descargar=descargar_a, **args)
    assert out["fecha"] == "2019-06-18"
    # se reemplaza el PDF por otro del MISMO tamaño y distinto contenido
    (tmp_path / "res" / out["archivo"]).write_bytes(b"%PDF-1.4 version B")
    out2 = leer_resolucion("https://mef/x.pdf", tmp_path / "res", descargar=lambda u, r: False, **args)
    assert out2["fecha"] == "2019-06-19" and out2["texto_reutilizado"] is False
    assert len(extracciones) == 2
