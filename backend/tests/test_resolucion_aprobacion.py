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
    leer_resolucion, limpiar_razon_social, normalizar,
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
