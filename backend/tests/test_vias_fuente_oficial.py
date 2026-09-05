"""
Tres vías nuevas de resolución automática, decididas por el desarrollador el
5-sep-2026 («no hay golden ni habrá; que baje mucho más de 21 a 15»):

  NUMERO     — el N° de la institución educativa del certificado coincide con la
               obra y ninguna otra obra hallada lo comparte (resolver).
  CONTRATO   — el contrato DE EXPEDIENTE del MEF está a nombre del emisor (etapa).
  RESOLUCION — la resolución de aprobación nombra al emisor (etapa).

Las dos últimas solo promueven si EXACTAMENTE un candidato recibe señal.
"""
from __future__ import annotations

from orquestador import Motor, RepositorioMemoria, etapas_esqueleto
from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaInfoObrasReal
from resolucion.cui import resolver
from schemas import pipeline


class _Fake:
    def __init__(self, obras, por_codigo=()):
        self.obras, self.pc = obras, list(por_codigo)

    def por_codigo(self, codigo):
        return list(self.pc)

    def buscar(self, nombre):
        return list(self.obras)


def _obra(cui, obra_id, nombre, depto="ICA"):
    return {"codUniqInv": cui, "codSnip": "", "codigoObra": obra_id, "nombrObra": nombre,
            "nombrDepartamento": depto, "fechaIniObra": None, "rucEjecutor": "", "rucSupervisor": ""}


# ── vía NUMERO ───────────────────────────────────────────────────────────────

EXP_IE = {"proyecto": 'Elaboración del Expediente Técnico denominado "MEJORAMIENTO DEL SERVICIO '
                      'EDUCATIVO EN LA I.E. N° 22489 DEL DISTRITO DE PARACAS"',
          "ubicacion": "Distrito de Paracas - Provincia de Pisco - Ica",
          "fecha_inicial": "2021-01-01", "fecha_final": "2021-12-31"}


def test_numero_de_institucion_unico_resuelve():
    obras = [_obra("2425571", 1, "MEJORAMIENTO DEL SERVICIO EDUCATIVO EN LA I.E. N° 22489 DEL DISTRITO DE PARACAS"),
             _obra("2610575", 2, "MEJORAMIENTO DEL SERVICIO DE EDUCACION INICIAL EN I.E. 205 DISTRITO DE PARACAS")]
    r = resolver(EXP_IE, _Fake(obras))
    assert r["estado"] == "resuelto", r
    assert r["via"] == "NUMERO" and r["cui"] == "2425571"


def test_numero_compartido_por_dos_obras_no_resuelve():
    # mejoramiento y ampliación de la MISMA escuela: el número no distingue
    obras = [_obra("2425571", 1, "MEJORAMIENTO DEL SERVICIO EDUCATIVO EN LA I.E. N° 22489 DEL DISTRITO DE PARACAS"),
             _obra("2999999", 2, "AMPLIACION DEL SERVICIO EDUCATIVO EN LA I.E. N° 22489 DEL DISTRITO DE PARACAS")]
    r = resolver(EXP_IE, _Fake(obras))
    assert r["via"] != "NUMERO"
    assert r["estado"] == "revision", r


def test_numero_con_otro_rubro_no_resuelve():
    # misma escuela, otra intervención: red de alcantarillado vs construcción del colegio
    exp = {"proyecto": "Expediente Técnico Definitivo: CONSTRUCCION Y EQUIPAMIENTO DE LA "
                       "INSTITUCION EDUCATIVA N° 14325 NIVEL PRIMARIA - FRIAS",
           "ubicacion": "Frías, Ayabaca, Piura", "fecha_inicial": "2021-01-01", "fecha_final": "2021-12-31"}
    obras = [_obra("2556981", 9, "RENOVACION DE RED DE ALCANTARILLADO; EN EL(LA) IE 14325 - FRIAS", depto="PIURA")]
    r = resolver(exp, _Fake(obras))
    assert r["via"] != "NUMERO"
    assert r["estado"] == "revision", r


def test_numero_con_ubicacion_contradictoria_no_resuelve():
    obras = [_obra("2425571", 1, "MEJORAMIENTO DEL SERVICIO EDUCATIVO EN LA I.E. N° 22489 DEL DISTRITO DE PARACAS",
                   depto="LORETO")]
    r = resolver(EXP_IE, _Fake(obras))
    assert r["via"] != "NUMERO"


# ── vías CONTRATO y RESOLUCION (etapa) ───────────────────────────────────────

def _ctx(enr_inicial: dict, exp: dict, tipo="expedientes"):
    espejo = {"_meta": {"analisis_id": "v-001", "concurso": "c", "postor": "p", "tipo_evaluacion": tipo},
              "postor": {},
              "profesionales": [{"n_prof": 1, "cargo": "ESP", "nombre": "N",
                                 "experiencias": [{"n": 1, "folio": "1", **exp}]}],
              "resumen_evaluacion": {"factores": []}}
    motor = Motor(etapas_esqueleto(), RepositorioMemoria())
    job = motor.crear_job(espejo)
    job.items_revision.append(pipeline.ItemRevision(
        n_prof=1, n_exp=1, etapa=pipeline.Etapa.RESOLUCION_CUI, motivo="sin candidato fiable",
        candidatos=enr_inicial.get("candidatos") or []))
    return Contexto(job=job, espejo=espejo, enriquecimiento={"1:1": dict(enr_inicial)})


EXP_CONS = {"proyecto": "Elaboración del Expediente Técnico: MEJORAMIENTO DEL C.S. X",
            "entidad_emisora": "CONSORCIO CONSULTOR PARACAS", "fecha_inicial": "2021-01-01",
            "fecha_final": "2021-12-31"}
ENR_REV = {"via": "REVISION", "cui": None, "candidatos": [
    {"cui": "2425571", "nombre_obra": "MEJORAMIENTO DEL C.S. X", "departamento": "ICA", "score": 90},
    {"cui": "2610575", "nombre_obra": "MEJORAMIENTO DEL C.S. Y", "departamento": "ICA", "score": 80}]}


def _contratos(por_cui):
    return lambda cui: por_cui.get(cui, [])


def _contrato(numero, contratista, objeto="ELABORACION DEL EXPEDIENTE TECNICO"):
    return {"numero": numero, "contratista": contratista, "monto": 100.0, "objeto": objeto,
            "nomenclatura": "", "fecha_suscripcion": None, "valor_referencial": None, "url_pdf": None}


def test_contrato_de_expediente_a_nombre_del_emisor_promueve():
    etapa = EtapaInfoObrasReal(contratos_mef=_contratos(
        {"2425571": [_contrato("082-2021", "CONSORCIO CONSULTOR PARACAS")]}),
        ficha_08a=lambda cui: None)
    ctx = _ctx(ENR_REV, EXP_CONS)
    obs = etapa._promover_expedientes_por_fuente_oficial(ctx)
    enr = ctx.enriquecimiento["1:1"]
    assert enr["cui"] == "2425571" and enr["via"] == "CONTRATO", enr
    assert "082-2021" in enr["decision"]
    assert ctx.job.items_revision[0].resuelto is True
    assert "RESUELTO AUTOMÁTICAMENTE" in ctx.job.items_revision[0].motivo
    assert obs and obs[0].codigo == "VIA_CONTRATO"


def test_contrato_de_otra_empresa_no_promueve():
    etapa = EtapaInfoObrasReal(contratos_mef=_contratos(
        {"2425571": [_contrato("082-2021", "TECOV INGENIEROS SAC")]}), ficha_08a=lambda cui: None)
    ctx = _ctx(ENR_REV, EXP_CONS)
    etapa._promover_expedientes_por_fuente_oficial(ctx)
    assert ctx.enriquecimiento["1:1"].get("cui") is None
    assert ctx.job.items_revision[0].resuelto is False


def test_contrato_de_obra_no_cuenta_como_expediente():
    # el contrato de EJECUCIÓN a nombre del emisor no identifica un expediente
    etapa = EtapaInfoObrasReal(contratos_mef=_contratos(
        {"2425571": [_contrato("099-2022", "CONSORCIO CONSULTOR PARACAS",
                               objeto="EJECUCION DE LA OBRA MEJORAMIENTO")]}), ficha_08a=lambda cui: None)
    ctx = _ctx(ENR_REV, EXP_CONS)
    etapa._promover_expedientes_por_fuente_oficial(ctx)
    assert ctx.enriquecimiento["1:1"].get("cui") is None


def test_dos_candidatos_con_senal_es_ambiguo_y_no_promueve():
    etapa = EtapaInfoObrasReal(contratos_mef=_contratos(
        {"2425571": [_contrato("082-2021", "CONSORCIO CONSULTOR PARACAS")],
         "2610575": [_contrato("083-2021", "CONSORCIO CONSULTOR PARACAS")]}), ficha_08a=lambda cui: None)
    ctx = _ctx(ENR_REV, EXP_CONS)
    etapa._promover_expedientes_por_fuente_oficial(ctx)
    assert ctx.enriquecimiento["1:1"].get("cui") is None


def test_resolucion_que_nombra_al_emisor_promueve(tmp_path):
    def lector(url, destino, **kw):
        return {"legible": True, "fecha": "2021-06-18", "coincide_emisor": "confirma",
                "consultores": ["CONSORCIO CONSULTOR PARACAS"], "resumen": "…"}
    etapa = EtapaInfoObrasReal(dir_descargas=tmp_path, contratos_mef=_contratos({}),
                               ficha_08a=lambda cui: ({"url": "https://mef/r.pdf", "numero": "274-2021"}
                                                      if cui == "2425571" else None),
                               lector_resolucion=lector)
    ctx = _ctx(ENR_REV, EXP_CONS)
    etapa._promover_expedientes_por_fuente_oficial(ctx)
    enr = ctx.enriquecimiento["1:1"]
    assert enr["cui"] == "2425571" and enr["via"] == "RESOLUCION", enr


def test_experiencia_de_obra_no_entra_a_la_promocion():
    etapa = EtapaInfoObrasReal(contratos_mef=_contratos(
        {"2425571": [_contrato("082-2021", "CONSORCIO CONSULTOR PARACAS")]}), ficha_08a=lambda cui: None)
    exp = {**EXP_CONS, "proyecto": "Supervisión de la obra MEJORAMIENTO DEL C.S. X"}
    ctx = _ctx(ENR_REV, exp, tipo="obras")
    etapa._promover_expedientes_por_fuente_oficial(ctx)
    assert ctx.enriquecimiento["1:1"].get("cui") is None
