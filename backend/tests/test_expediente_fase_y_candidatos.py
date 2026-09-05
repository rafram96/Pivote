"""
Dos hallazgos de la corrida real de expedientes (5-sep):

1. Un certificado de ELABORACIÓN DEL EXPEDIENTE que cita el CUI exacto —y el MEF
   lo confirma con el mismo nombre— caía a revisión porque InfoObras solo tenía
   un registro de «obra de contingencia» y ningún registro de expediente. La fase
   de expediente casi nunca se registra en InfoObras: se verifica en el MEF. La
   identidad del proyecto se conserva y se deja escrito qué registra InfoObras.

2. Las experiencias de expediente que quedan en revisión ahora llevan lo que dice
   la resolución de aprobación de cada candidato (evidencia oficial), en el ítem
   de revisión y en la hoja P. No resuelven: informan.
"""
from __future__ import annotations

import openpyxl

from entregables.excel_final import generar_excel_final
from orquestador.etapas_reales import frases_resoluciones_candidatos
from resolucion.cui import resolver
from schemas.cargo import etiqueta_hoja


class _PorCodigo:
    def __init__(self, obras):
        self.obras = obras

    def por_codigo(self, codigo):
        return list(self.obras)

    def buscar(self, nombre):
        return []


def _obra(cui, obra_id, nombre, depto="PIURA"):
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None, "rucEjecutor": "", "rucSupervisor": ""}


def test_expediente_con_cui_citado_no_cae_por_falta_de_registro_de_expediente():
    exp = {"cui": "2266200",
           "proyecto": "Elaboración del Expediente Técnico del PIP: MEJORAMIENTO DE LOS SERVICIOS "
                       "DE SALUD DEL ESTABLECIMIENTO DE SALUD DE AYABACA, PROVINCIA Y DISTRITO DE "
                       "AYABACA, DEPARTAMENTO DE PIURA",
           "ubicacion": "Ayabaca, Ayabaca, Piura",
           "fecha_inicial": "2019-03-01", "fecha_final": "2019-12-31"}
    # InfoObras solo registra la OBRA DE CONTINGENCIA del mismo CUI
    obra = _obra("2266200", 501, "OBRA DE CONTINGENCIA PARA EL PROYECTO MEJORAMIENTO DE LOS "
                 "SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD DE AYABACA")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "resuelto", r
    assert r["cui"] == "2266200"
    assert "solo en su fase de contingencia" in r["decision"]
    assert "MEF" in r["decision"]


def test_obra_con_fase_contradictoria_sigue_yendo_a_revision():
    # el caso que #63 protege: certificado de OBRA PRINCIPAL y registro de contingencia
    exp = {"cui": "2266200", "proyecto": "Supervisión de la OBRA PRINCIPAL: MEJORAMIENTO DEL "
                                         "ESTABLECIMIENTO DE SALUD DE AYABACA",
           "fecha_inicial": "2021-03-01", "fecha_final": "2021-12-31"}
    obra = _obra("2266200", 501, "OBRA DE CONTINGENCIA PARA EL PROYECTO MEJORAMIENTO DEL "
                 "ESTABLECIMIENTO DE SALUD DE AYABACA")
    r = resolver(exp, _PorCodigo([obra]))
    assert r["estado"] == "revision", r
    assert "elegir el registro correcto" in r["decision"]


def test_frases_de_candidatos_en_palabras_del_evaluador():
    frases = frases_resoluciones_candidatos([
        {"cui": "2412695", "legible": True, "fecha": "2023-11-27", "coincide_emisor": "nombra_otro",
         "detalle_emisor": "TECOV INGENIEROS"},
        {"cui": "2234021", "legible": True, "fecha": "2025-03-10", "coincide_emisor": "confirma"},
        {"cui": "2331884", "legible": True, "fecha": "2023-04-02", "coincide_emisor": "no_nombra"},
        {"cui": "2450843", "legible": False},
    ])
    assert "nombra a TECOV INGENIEROS, no al emisor" in frases[0] and "27/11/2023" in frases[0]
    assert "nombra al emisor del certificado" in frases[1]
    assert "no nombra a quien elaboró" in frases[2]
    assert "sin texto reconocible" in frases[3]


def _espejo_pendiente():
    return {
        "_meta": {"analisis_id": "exp-002", "concurso": "CP-EXP", "postor": "P",
                  "tipo_evaluacion": "expedientes"},
        "postor": {},
        "profesionales": [{
            "n_prof": 6, "cargo": "EQUIPAMIENTO", "nombre": "Profesional Seis",
            "colegiatura": "CIP 6", "cumple": "CUMPLE — x", "total": {"dias": 400, "anios": 1.1},
            "experiencias": [{
                "n": 2, "proyecto": "Elaboración del Expediente Técnico: MEJORAMIENTO Y AMPLIACIÓN "
                                    "DE LOS SERVICIOS REGISTRALES",
                "entidad_emisora": "AYEP CONTRATISTAS GENERALES EIRL", "ruc_emisor": "20493929403",
                "fecha_inicial": "2022-01-10", "fecha_final": "2022-12-20", "dias": 345, "folio": "20"}],
        }],
        "resumen_evaluacion": {"factores": []},
    }


def test_hoja_p_muestra_lo_que_dice_la_resolucion_de_cada_candidato(tmp_path):
    ficha = {"via": "REVISION", "camino": "expediente", "camino_fuente": "declarado",
             "resoluciones_candidatos": [
                 {"cui": "2412695", "nombre_obra": "MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS REGISTRALES",
                  "legible": True, "fecha": "2023-11-27", "coincide_emisor": "nombra_otro",
                  "detalle_emisor": "TECOV INGENIEROS"},
                 {"cui": "2331884", "nombre_obra": "MEJORAMIENTO DE LOS SERVICIOS REGISTRALES DE ICA",
                  "legible": True, "fecha": "2023-04-02", "coincide_emisor": "no_nombra"}]}
    revisiones = {(6, 2): ("los candidatos hallados contradicen la ubicación del certificado",
                           "elegir candidato o pegar CUI")}
    salida = generar_excel_final(_espejo_pendiente(), tmp_path / "c.xlsx", {},
                                 fichas={(6, 2): ficha}, revisiones=revisiones)
    ws = openpyxl.load_workbook(salida)[etiqueta_hoja(6, "EQUIPAMIENTO")]
    texto = " || ".join(str(c.value) for fila in ws.iter_rows() for c in fila if c.value not in (None, ""))
    assert "EXPERIENCIA EN REVISIÓN" in texto
    assert "Candidato CUI 2412695" in texto and "nombra a TECOV INGENIEROS, no al emisor" in texto
    assert "Candidato CUI 2331884" in texto and "no nombra a quien elaboró" in texto
