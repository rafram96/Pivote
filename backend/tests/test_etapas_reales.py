"""
Tests de las etapas REALES con dependencias inyectadas (cero red):
identificación de obras, InfoObras (paralizaciones), SUNAT (ALT04), días
efectivos con mínimo de bases, Excel final con paralizaciones, y el flujo
integrado motor + revisión humana.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import openpyxl
import pytest

from orquestador import Motor, RepositorioMemoria
from orquestador.etapas_reales import etapas_reales
from schemas.pipeline import Etapa, EstadoEtapa, JobEstado

# ── espejo sintético: 2 profesionales, 3 experiencias ────────────────────────
# prof 1 exp 1: CUI en el campo → determinístico
# prof 1 exp 2: sin pista → REVISIÓN (candidatos del fake)
# prof 2 exp 1: nombre resoluble por el fake + RUC emisor (SUNAT ALT04)
ESPEJO = {
    "_meta": {"analisis_id": "demo-real-001", "concurso": "CP-REAL/2026",
              "postor": "POSTOR REAL DEMO"},
    "postor": {},
    "profesionales": [
        {"n_prof": 1, "cargo": "JEFE DE SUPERVISIÓN", "nombre": "Prof Uno",
         "requisitos": {"tipo_experiencia": "supervisión — mínimo 3 años desde la colegiatura"},
         "total": {"dias": 1448, "anios": 3.97},
         "experiencias": [
             {"n": 1, "proyecto": "Supervisión del Centro de Salud Pillco Marca, Huanuco",
              "cui": "2418877", "fecha_inicial": "2021-05-13", "fecha_final": "2023-05-06",
              "dias": 724, "folio": "100"},
             {"n": 2, "proyecto": "Mejoramiento del Puesto de Salud Quisqui",
              "fecha_inicial": "2023-11-22", "fecha_final": "2025-07-22",
              "dias": 609, "folio": "120"},
         ]},
        {"n_prof": 2, "cargo": "ESP. ESTRUCTURAS", "nombre": "Prof Dos",
         "requisitos": {"tipo_experiencia": "mínimo 2 años"},
         "total": {"dias": 1244, "anios": 3.41},
         "experiencias": [
             {"n": 1, "proyecto": "Supervisión del Hospital Materno de Ambo, Huanuco",
              "entidad_emisora": "Consorcio X (RUC 20512345678)",
              "fecha_inicial": "2019-11-04", "fecha_final": "2023-03-31",
              "dias": 1244, "folio": "200"},
         ]},
    ],
    "resumen_evaluacion": {"factores": [], "puntaje_total": None},
}


# ── fakes inyectables ────────────────────────────────────────────────────────

class ConsultaFake:
    """InfoObras-búsqueda falsa: conoce 2 obras."""
    def por_codigo(self, codigo):
        if codigo == "2418877":
            return [{"nombrObra": "MEJORAMIENTO DEL CENTRO DE SALUD PILLCO MARCA",
                     "nombrDepartamento": "HUANUCO", "codSnip": "2418877", "codigoObra": 111}]
        return []

    def buscar(self, nombre):
        if "AMBO" in nombre.upper() or "MATERNO" in nombre.upper():
            return [{"nombrObra": "MEJORAMIENTO DEL HOSPITAL MATERNO DE AMBO",
                     "nombrDepartamento": "HUANUCO", "codSnip": "395001",
                     "codigoObra": 222, "rucEjecutor": "", "rucSupervisor": "20512345678"}]
        return []  # Quisqui: sin candidatos → REVISIÓN


@dataclass
class AvanceFake:
    anio: int
    mes: int
    estado: str
    fecha_paralizacion: object = None


@dataclass
class ObraFake:
    obra_id: int
    nombre: str
    codigo_infoobras: str = "INF-001"
    avances: list = field(default_factory=list)
    aprobacion_expediente: object = None


def _meses(desde, hasta, paralizados=()):
    """AvanceFake mensual continuo [desde, hasta] inclusive (anio, mes)."""
    out, (y, m) = [], desde
    while (y, m) <= hasta:
        estado = "Paralizado" if (y, m) in paralizados else "En ejecución"
        out.append(AvanceFake(y, m, estado))
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
    return out


def fetcher_fake(cui):
    if cui == "2418877":
        # valorizaciones que CUBREN el periodo certificado (2021-05 → 2023-05),
        # con feb-abr 2022 paralizado (1 paralización, sin huecos)
        avances = _meses((2021, 5), (2023, 5),
                         paralizados={(2022, 2), (2022, 3), (2022, 4)})
        return ObraFake(111, "C.S. PILLCO MARCA", avances=avances)
    if cui == "395001":
        # cubre el periodo certificado (2019-11 → 2023-03), sin paralización
        return ObraFake(222, "HOSPITAL MATERNO AMBO", avances=_meses((2019, 11), (2023, 3)))
    if cui == "777999":
        # CUI pegado a mano por el humano → resuelve a una obra que cubre su cert
        # (Quisqui: 2023-11-22 → 2025-07-22)
        return ObraFake(333, "PUESTO DE SALUD QUISQUI", avances=_meses((2023, 11), (2025, 7)))
    return None


@dataclass
class EmpresaFake:
    ruc: str
    razon_social: str
    fecha_inscripcion: date
    estado: str = "ACTIVO"


def consultor_fake(ruc):
    # constituida DESPUÉS del inicio de la experiencia (2019-11-04) → ALT04
    return EmpresaFake(ruc, "CONSORCIO X SAC", date(2020, 6, 1))


def hacer_motor(tmp_path):
    repo = RepositorioMemoria()
    etapas = etapas_reales(
        tmp_path, consulta_cui=ConsultaFake(), fetcher_infoobras=fetcher_fake,
        consultor_sunat=consultor_fake, buscador_sunat=lambda n: [],
        descargar=lambda *a, **k: None)
    return Motor(etapas, repo), repo


# ── el flujo integrado ────────────────────────────────────────────────────────

def test_flujo_real_completo_con_revision_humana(tmp_path):
    motor, repo = hacer_motor(tmp_path)
    job = motor.crear_job(ESPEJO)
    job = motor.correr(job.job_id)

    # exp (1,2) sin candidato → REQUIERE_REVISION con su ItemRevision contextual
    assert job.estado == JobEstado.REQUIERE_REVISION
    items = [it for it in job.items_revision if not it.resuelto]
    assert len(items) == 1
    assert (items[0].n_prof, items[0].n_exp) == (1, 2)
    assert items[0].proyecto and "Quisqui" in items[0].proyecto

    enr = repo.cargar_enriquecimiento(job.job_id)
    # (1,1): CUI del campo, verificado
    assert enr["1:1"]["cui"] == "2418877" and enr["1:1"]["via"] == "CUI_TEXTO"
    # (2,1): resuelto por RUC supervisor
    assert enr["2:1"]["cui"] == "395001" and enr["2:1"]["via"] == "RUC"
    # paralizaciones de la obra 2418877 (feb-abr 2022) — ahora dicts con tipo
    assert len(enr["1:1"]["paralizaciones"]) == 1
    assert enr["1:1"]["paralizaciones"][0]["inicio"] == "2022-02-01"
    assert enr["1:1"]["paralizaciones"][0]["tipo"] == "paralizado"
    # SUNAT en (2,1) con ALT04
    assert enr["2:1"]["sunat"]["razon_social"] == "CONSORCIO X SAC"
    obs_alt04 = [o for e in job.etapas for o in e.observaciones if o.codigo == "ALT04"]
    assert len(obs_alt04) == 1

    # reglas: prof 1 con paralizaciones descontadas (mínimo 3 → sigue cumpliendo)
    p1 = enr["prof:1"]
    assert p1["dias_brutos"] == 1333  # 724 + 609
    # feb+mar+abr; el scraper aproxima el fin de mes como el día 1 del mes
    # siguiente (convención existente de _extraer_periodos_suspension) → 90
    assert p1["dias_paralizados"] == 90
    assert p1["minimo_anios"] == 3
    assert "cumple_backend" not in p1  # 3.4 años efectivos ≥ 3

    # el humano resuelve la pendiente pegando un CUI → job completa
    job = motor.resolver_revision(job.job_id, 1, 2, {"cui": "777999"})
    assert job.estado == JobEstado.COMPLETADO
    enr = repo.cargar_enriquecimiento(job.job_id)
    assert enr["1:2"]["via"] == "MANUAL" and enr["1:2"]["cui"] == "777999"

    # Excel final regenerado CON las paralizaciones en la hoja de hitos
    ruta = tmp_path / f"{job.job_id}.final.xlsx"
    assert ruta.exists()
    ws = openpyxl.load_workbook(ruta)["P1 JEFE DE SUPERVISIÓN"]
    texto = "\n".join(str(c.value) for f in ws.iter_rows() for c in f if c.value)
    assert "Paralización 1 de la obra (InfoObras)" in texto
    assert job.excel_final and job.zip_infoobras


def test_paso5_marca_no_cumple_cuando_cae_bajo_el_minimo(tmp_path):
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Largo, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2023-06-30", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    def fetcher_paraliza_todo(cui):
        # 24 meses paralizados de 30 → efectivos muy por debajo de 2 años
        avances = [AvanceFake(a, m, "Paralizado")
                   for a in (2021, 2022) for m in range(1, 13)]
        return ObraFake(1, "OBRA", avances=avances)

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_paraliza_todo,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    enr = repo.cargar_enriquecimiento(job.job_id)
    p = enr["prof:1"]
    assert p["anios_efectivos"] < 2
    assert "NO CUMPLE" in p["cumple_backend"]


def test_cobertura_baja_marca_revision(tmp_path):
    """Caso 133630/Valdizán: el periodo certificado cae casi fuera del rango de
    valorizaciones de la obra elegida → debe ir a revisión humana."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 # el nombre coincide con la obra del fake → el CUI resuelve limpio
                 # (CUI_TEXTO) y el flujo llega a InfoObras, donde la cobertura falla
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2016-06-10", "fecha_final": "2017-05-15", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    def fetcher_no_cubre(cui):
        # valorizaciones 2015-01 → 2016-07: apenas tocan el inicio del certificado
        return ObraFake(111, "OBRA", avances=_meses((2015, 1), (2016, 7)))

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_no_cubre,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    assert job.estado == JobEstado.REQUIERE_REVISION
    items = [it for it in job.items_revision if it.n_exp == 1 and not it.resuelto]
    assert len(items) == 1 and items[0].etapa == Etapa.INFOOBRAS
    obs_cob = [o for e in job.etapas for o in e.observaciones if o.codigo == "COBERTURA"]
    assert len(obs_cob) == 1


def test_infoobras_segunda_pasada_recupera_obra_transitoria(tmp_path):
    """Una obra cae por flakiness en la 1ra pasada y responde en la 2da → debe
    quedar OK con sus valorizaciones, sin marcarse como error de InfoObras."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2022-01-01", "fecha_final": "2022-12-31", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    estado = {"n": 0}

    def fetcher_flaky(cui):
        estado["n"] += 1
        if estado["n"] == 1:
            raise ConnectionError("caída transitoria del portal")
        return ObraFake(111, "C.S. PILLCO MARCA", avances=_meses((2022, 1), (2022, 12)))

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_flaky,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    enr = repo.cargar_enriquecimiento(job.job_id)
    assert estado["n"] == 2  # cayó en la 1ra pasada, recuperó en la 2da
    assert len(enr["1:1"]["valorizaciones"]) == 12
    assert enr["1:1"]["codigo_infoobras"] == "INF-001"
    # no quedó error de InfoObras (la 2da pasada la rescató)
    assert not [o for e in job.etapas for o in e.observaciones if o.codigo == "INFOOBRAS"]
    obs = [o for e in job.etapas for o in e.observaciones if o.codigo == "PASO5"]
    assert len(obs) == 1 and "por debajo del mínimo" in obs[0].mensaje


def test_obra_sin_match_surge_a_revision(tmp_path):
    """Requisito del cliente: NADA se descarta en silencio. Ya NO hay 'gate de alcance'
    (se resuelve cualquier rubro/tipo). Una experiencia que no resuelve —sin CUI y sin
    candidato fiable por nombre— surge igual en "Por confirmar" para que el humano
    pegue el CUI o la descarte; no se marca y se olvida."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "experiencias": [
                 {"n": 1, "proyecto": "Construcción de edificio de oficinas corporativas Lima",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2022-01-01", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    motor, repo = hacer_motor(tmp_path)
    job = motor.correr(motor.crear_job(espejo).job_id)
    assert job.estado == JobEstado.REQUIERE_REVISION  # surge para resolución humana
    item = next(it for it in job.items_revision if it.n_prof == 1 and it.n_exp == 1)
    assert not item.resuelto                           # esperando decisión del humano


def test_experiencia_de_expediente_se_acepta_por_su_aprobacion(tmp_path):
    """Experiencia de EXPEDIENTE técnico: no tiene valorizaciones, su respaldo es el
    hito 'Aprobación del proyecto'. Con el nombre de expediente + la aprobación traída
    de InfoObras, NO va a revisión y cuenta por el periodo del certificado."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 1 año"},
             "experiencias": [
                 {"n": 1, "cui": "2418877",
                  "proyecto": "Elaboración del Expediente Técnico: Mejoramiento del "
                              "Centro de Salud Pillco Marca, Huanuco",
                  "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    aprob = {"url": "https://infobras.contraloria.gob.pe/InfobrasWeb/Mapa/DownloadFile?x",
             "filename": "expediente/documento20200917114618.pdf",
             "nombre": "Res. Gerencia Municipal N° 072-2020-GM MDS",
             "extension": "pdf", "fecha": "2020-09-17"}

    def fetcher_expediente(cui):
        # obra sin valorizaciones, pero con la aprobación del expediente
        return ObraFake(111, "C.S. PILLCO MARCA", avances=[], aprobacion_expediente=aprob)

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_expediente,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    # NO cae en revisión por cobertura (la aprobación la respalda)
    assert not [it for it in job.items_revision
                if it.n_exp == 1 and not it.resuelto and it.etapa == Etapa.INFOOBRAS]
    # observación RESPALDO con la fecha de aprobación
    resp = [o for e in job.etapas for o in e.observaciones if o.codigo == "RESPALDO"]
    assert len(resp) == 1 and "17/09/2020" in resp[0].mensaje
    # se persiste la aprobación en el enriquecimiento (para Excel + descarga)
    enr = repo.cargar_enriquecimiento(job.job_id)
    assert enr["1:1"]["aprobacion_expediente"]["fecha"] == "2020-09-17"
    # sin clamp fuera_de_ventana (no se anuló el periodo del certificado)
    assert not any(p.get("tipo") == "fuera_de_ventana"
                   for p in enr["1:1"].get("paralizaciones", []))


def test_obra_de_construccion_sin_valorizaciones_no_usa_aprobacion(tmp_path):
    """El respaldo por aprobación es SOLO para expedientes (por nombre). Una obra de
    construcción sin valorizaciones NO se acepta por la aprobación → sigue a revisión."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 1 año"},
             "experiencias": [
                 {"n": 1, "cui": "2418877",
                  "proyecto": "Mejoramiento del Centro de Salud Pillco Marca, Huanuco",
                  "fecha_inicial": "2020-01-01", "fecha_final": "2020-12-31", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    aprob = {"url": "u", "filename": "expediente/doc20200917.pdf",
             "nombre": "Res", "extension": "pdf", "fecha": "2020-09-17"}

    def fetcher(cui):
        return ObraFake(111, "C.S. PILLCO MARCA", avances=[], aprobacion_expediente=aprob)

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)
    # NO hay RESPALDO (no es expediente) y sí surge a revisión
    assert not [o for e in job.etapas for o in e.observaciones if o.codigo == "RESPALDO"]
    assert job.estado == JobEstado.REQUIERE_REVISION


def test_infoobras_cache_por_obra_id(tmp_path):
    """Dos experiencias con el mismo CUI y obra_id pero diferentes fechas
    certificado solo hacen 1 llamada al fetcher (gracias al caché por obra_id)."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca 1", "cui": "2418877",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2021-06-30", "folio": "1"},
                 {"n": 2, "proyecto": "Centro de Salud Pillco Marca 2", "cui": "2418877",
                  "fecha_inicial": "2022-01-01", "fecha_final": "2022-06-30", "folio": "2"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    estado = {"llamadas": 0}

    def fetcher_con_conteo(cui, cert_ini=None, cert_fin=None, obra_id=None):
        estado["llamadas"] += 1
        return ObraFake(111, "C.S. PILLCO MARCA", avances=_meses((2021, 1), (2022, 12)))

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_con_conteo,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    # Ambas experiencias deben haberse procesado exitosamente
    enr = repo.cargar_enriquecimiento(job.job_id)
    assert len(enr["1:1"]["valorizaciones"]) == 24
    assert len(enr["1:2"]["valorizaciones"]) == 24
    # La consulta real al fetcher de InfoObras debió ocurrir SOLO UNA VEZ
    assert estado["llamadas"] == 1


def test_clamp_descuenta_cert_fuera_de_la_ventana(tmp_path):
    # cert 2016-01 → 2017-12 (731 días) pero la obra valoriza solo ene-jun 2016.
    # Lo que cae fuera de la ventana de valorizaciones no cuenta (clamp Paso 5).
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2016-01-01", "fecha_final": "2017-12-31", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    def fetcher_parcial(cui, *a, **k):
        return ObraFake(111, "C.S. PILLCO MARCA", avances=_meses((2016, 1), (2016, 6)))

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_parcial,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    enr = repo.cargar_enriquecimiento(job.job_id)
    assert "fuera_de_ventana" in {p["tipo"] for p in enr["1:1"]["paralizaciones"]}
    p1 = enr["prof:1"]
    assert p1["dias_brutos"] == 731        # cert completo (2016 bisiesto + 2017)
    assert p1["dias_efectivos"] == 182     # solo ene-jun 2016 (lo valorizado)


def test_rucs_postor_excluye_experiencia_postor():
    """_rucs_postor toma RUCs de formularios/consorciados/meta, NO de
    experiencia_postor (esos son clientes terceros → falsos positivos)."""
    from orquestador.etapas_reales import _rucs_postor
    espejo = {
        "_meta": {"postor": "CONSORCIO (RUC 20111111111)"},
        "postor": {
            "formularios": [{"documento": "Promesa de consorcio — miembro RUC 20222222222"}],
            "consorciados": [{"ruc": "20333333333"}],
            "experiencia_postor": [{"cliente": "GORE Huánuco (RUC 20999999999)"}],  # NO entra
        },
    }
    rucs = _rucs_postor(espejo)
    assert rucs == {"20111111111", "20222222222", "20333333333"}
    assert "20999999999" not in rucs


def test_vinculacion_postor_emisor_dispara_alerta(tmp_path):
    """Auto-certificación: el RUC que emitió el certificado es el del propio
    postor / un consorciado (declarado en los formularios) → alerta VINCULACION.
    El otro emisor (RUC ajeno) no dispara. Determinístico, no usa SUNAT."""
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "CONSORCIO X + Y"},
        "postor": {"formularios": [
            {"anexo": "Anexo 2",
             "documento": "Promesa de consorcio — JOGAMA (RUC 20512345678) + Bisbal"}]},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "experiencias": [
                 {"n": 1, "proyecto": "Edificio corporativo Lima",
                  "entidad_emisora": "JOGAMA Consultorías E.I.R.L. (RUC 20512345678)",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2022-01-01", "folio": "1"},
                 {"n": 2, "proyecto": "Edificio corporativo Trujillo",
                  "entidad_emisora": "Entidad Ajena S.A. (RUC 20999999999)",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2022-01-01", "folio": "2"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }
    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_fake,
                                consultor_sunat=lambda r: EmpresaFake(r, "EMP", date(2000, 1, 1)),
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    vinc = [o for e in job.etapas for o in e.observaciones if o.codigo == "VINCULACION"]
    assert len(vinc) == 1 and vinc[0].referencia == "prof=1 exp=1"
    enr = repo.cargar_enriquecimiento(job.job_id)
    assert enr["1:1"].get("vinculacion_postor_emisor") is True
    assert not enr["1:2"].get("vinculacion_postor_emisor")
    # los emisores se inscribieron en 2000 (antes del inicio) → ningún ALT04
    assert not [o for e in job.etapas for o in e.observaciones if o.codigo == "ALT04"]


def test_fetch_fallido_no_se_clampa_y_marca_veredicto_provisional(tmp_path):
    # el portal cae en ambas pasadas → ventana DESCONOCIDA: no clampar a 0 (sería
    # NO CUMPLE falso). El profesional queda con veredicto provisional + revisión.
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2021-01-01", "fecha_final": "2023-06-30", "folio": "1"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    def fetcher_siempre_cae(cui, *a, **k):
        raise ConnectionError("portal caído todo el run")

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_siempre_cae,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    enr = repo.cargar_enriquecimiento(job.job_id)
    assert enr["1:1"].get("sin_verificar") is True
    assert not enr["1:1"].get("valorizaciones")          # no se inventó tabla
    assert enr["prof:1"].get("veredicto_provisional") == [1]
    assert job.estado == JobEstado.REQUIERE_REVISION
    assert any(it.n_prof == 1 and not it.resuelto and "provisional" in it.motivo
               for it in job.items_revision)


def test_fecha_por_verificar_en_no_cumple_va_a_revision(tmp_path):
    # prof con 2 experiencias; la 2da resuelve pero su fecha_final no se leyó
    # ("POR VERIFICAR") → se excluye del cálculo. Solo con la 1ra el cómputo cae bajo el
    # mínimo, PERO como depende de una fecha sin leer NO es un NO CUMPLE definitivo: se
    # reformula a INCERTIDUMBRE ("POR VERIFICAR", la ausencia no invalida) y va a revisión.
    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N",
             "requisitos": {"tipo_experiencia": "mínimo 2 años"},
             "experiencias": [
                 {"n": 1, "proyecto": "Centro de Salud Pillco Marca, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2022-01-01", "fecha_final": "2022-12-31", "folio": "1"},
                 {"n": 2, "proyecto": "Centro de Salud Pillco Marca II, Huanuco", "cui": "2418877",
                  "fecha_inicial": "2023-01-01", "fecha_final": "POR VERIFICAR", "folio": "2"},
             ]},
        ],
        "resumen_evaluacion": {"factores": []},
    }

    repo = RepositorioMemoria()
    motor = Motor(etapas_reales(tmp_path, consulta_cui=ConsultaFake(),
                                fetcher_infoobras=fetcher_fake,
                                consultor_sunat=lambda r: None,
                                descargar=lambda *a, **k: None), repo)
    job = motor.correr(motor.crear_job(espejo).job_id)

    enr = repo.cargar_enriquecimiento(job.job_id)
    veredicto = enr["prof:1"]["cumple_backend"]
    assert "POR VERIFICAR" in veredicto and "NO invalida" in veredicto  # incertidumbre, no fallo duro
    assert not veredicto.startswith("NO CUMPLE")
    assert enr["prof:1"].get("veredicto_provisional") == [2]
    assert any(it.n_prof == 1 and it.n_exp == 2 and not it.resuelto
               and "fecha sin verificar" in it.motivo for it in job.items_revision)


def test_cobertura_y_clamp_coinciden_en_borde_de_mes():
    # la valoriz de un mes cubre TODO el mes: cobertura y clamp deben usar el
    # mismo límite (fin-de-mes). Borde: última valoriz marzo, cert empieza 15/03.
    from orquestador.etapas_reales import _cobertura_cert, _fuera_de_ventana
    avs = [AvanceFake(2020, m, "En ejecución") for m in (1, 2, 3)]
    ci, cf = date(2020, 3, 15), date(2020, 6, 30)
    # el clamp acredita 15-31 de marzo → la cobertura NO debe caer a 0
    assert _cobertura_cert(avs, ci, cf) > 0
    fuera = _fuera_de_ventana(avs, ci, cf)
    assert fuera and fuera[0][0] == date(2020, 4, 1)  # fuera empieza 01/04, no 16/03


def test_motivo_cobertura_distingue_la_causa():
    from orquestador.etapas_reales import _motivo_cobertura
    ci, cf = date(2020, 1, 1), date(2021, 1, 1)
    # obra sin valorizaciones
    assert "valorizaciones ejecutadas" in _motivo_cobertura([], ci, cf, "10056", 0)
    # certificado posterior a la última valorización
    avs_viejos = [AvanceFake(2017, m, "En ejecución") for m in (1, 2, 3)]
    m1 = _motivo_cobertura(avs_viejos, ci, cf, "71173", 0)
    assert "valorizó hasta" in m1 and "no respaldado" in m1
    # certificado anterior a la primera valorización
    avs_nuevos = [AvanceFake(2024, m, "En ejecución") for m in (1, 2, 3)]
    m2 = _motivo_cobertura(avs_nuevos, ci, cf, "99999", 0)
    assert "empezó a valorizar" in m2 and "no respaldado" in m2


def test_excel_muestra_bloque_en_revision(tmp_path):
    # una experiencia sin obra (en revisión) debe mostrar "EN REVISIÓN" + el
    # motivo en su hoja, no una columna de obra vacía.
    from entregables.excel_final import generar_excel_final
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
                {"n": 1, "proyecto": "Hospital X", "fecha_inicial": "2020-01-01",
                 "fecha_final": "2020-12-31", "folio": "1"}]}],
    }
    ruta = tmp_path / "rev.xlsx"
    generar_excel_final(espejo, ruta, {}, {}, {},
                        revisiones={(1, 1): "sin candidato fiable en InfoObras"})
    wb = openpyxl.load_workbook(ruta)
    hoja = next(s for s in wb.sheetnames if s.startswith("P1"))
    texto = "\n".join(str(c.value) for row in wb[hoja].iter_rows()
                      for c in row if c.value)
    assert "EN REVISIÓN" in texto and "sin candidato" in texto.lower()


def test_excel_muestra_modificaciones_de_plazo(tmp_path):
    from entregables.excel_final import generar_excel_final
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
                {"n": 1, "proyecto": "Hospital X", "fecha_inicial": "2015-01-01",
                 "fecha_final": "2015-12-31", "folio": "1"}]}],
    }
    fichas = {(1, 1): {
        "cui": "123", "codigo_infoobras": "33900", "estado": "Finalizado",
        "valorizaciones": [{"anio": 2015, "mes": 6, "estado": "En ejecución",
                            "fisico_real": 50, "valorizado_real": 100}],
        "modificaciones_plazo": [
            {"tipo": "Ampliación del plazo", "causal": "mayores metrados", "dias": 88,
             "fecha_aprobacion": "2015-03-05", "fecha_fin": "2015-05-26"}],
    }}
    ruta = tmp_path / "mods.xlsx"
    generar_excel_final(espejo, ruta, {}, {(1, 1): "123"}, fichas)
    wb = openpyxl.load_workbook(ruta)
    hoja = next(s for s in wb.sheetnames if s.startswith("P1"))
    texto = "\n".join(str(c.value) for row in wb[hoja].iter_rows()
                      for c in row if c.value)
    assert "MODIFICACIONES DE PLAZO" in texto and "Ampliación del plazo" in texto


def test_excel_marca_valorizaciones_con_archivos(tmp_path):
    from entregables.excel_final import generar_excel_final
    espejo = {
        "_meta": {}, "postor": {},
        "profesionales": [
            {"n_prof": 1, "cargo": "ESP", "nombre": "N", "experiencias": [
                {"n": 1, "proyecto": "Hospital X", "fecha_inicial": "2015-01-01",
                 "fecha_final": "2015-12-31", "folio": "1"}]}],
    }
    fichas = {(1, 1): {
        "cui": "123", "codigo_infoobras": "33900", "estado": "Finalizado",
        "valorizaciones": [
            {"anio": 2015, "mes": 6, "estado": "En ejecución", "fisico_real": 50,
             "valorizado_real": 100, "docs": 2},
            {"anio": 2015, "mes": 5, "estado": "En ejecución", "fisico_real": 40,
             "valorizado_real": 80, "docs": 0}],
    }}
    ruta = tmp_path / "valdocs.xlsx"
    generar_excel_final(espejo, ruta, {}, {(1, 1): "123"}, fichas)
    wb = openpyxl.load_workbook(ruta)
    hoja = next(s for s in wb.sheetnames if s.startswith("P1"))
    texto = "\n".join(str(c.value) for row in wb[hoja].iter_rows()
                      for c in row if c.value)
    assert "ARCHIVOS (ZIP)" in texto   # nueva columna
    assert "Sí (2)" in texto           # valorización con 2 documentos
    assert "—" in texto                # valorización sin documentos


def test_sunat_por_nombre_cuando_no_hay_ruc():
    """Sin RUC en el cert: nombre distintivo → 1 match → se cruza (via nombre);
    nombre genérico → varios → 'ambiguo'; entidad pública → se salta."""
    from orquestador.etapas import Contexto
    from orquestador.etapas_reales import EtapaSunatReal

    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "ESP", "experiencias": [
            {"n": 1, "entidad_emisora": "Consorcio Hospital Tacna",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"},
            {"n": 2, "entidad_emisora": "Consorcio Supervisor (Bisbal, Estela)",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"},
            {"n": 3, "entidad_emisora": "Gobierno Regional de Huánuco",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"},
        ]}],
        "resumen_evaluacion": {"factores": []},
    }

    def buscador(nombre):
        u = nombre.upper()
        if "TACNA" in u:
            return [{"ruc": "20600789911", "razon_social": "CONSORCIO HOSPITAL TACNA"}]
        if "SUPERVISOR" in u:  # genérico → varios
            return [{"ruc": "1" * 11, "razon_social": "A"}, {"ruc": "2" * 11, "razon_social": "B"}]
        return []

    consultor = lambda r: EmpresaFake(r, "CONSORCIO HOSPITAL TACNA", date(2015, 11, 6))
    ctx = Contexto(job=None, espejo=espejo, enriquecimiento={})
    EtapaSunatReal(consultor=consultor, buscador=buscador).correr(ctx)

    # exp 1: nombre distintivo → 1 match → cruzado por nombre
    assert ctx.enriquecimiento["1:1"]["sunat"]["ruc"] == "20600789911"
    assert ctx.enriquecimiento["1:1"]["sunat"]["via"] == "nombre"
    # exp 2: genérico → varios → ambiguo (no se cruza; deja candidatos)
    assert ctx.enriquecimiento["1:2"]["sunat"]["ambiguo"] == 2
    assert "ruc" not in ctx.enriquecimiento["1:2"]["sunat"]
    # exp 3: entidad pública → se salta (sin bloque sunat)
    assert "sunat" not in ctx.enriquecimiento.get("1:3", {})


def test_sunat_desempate_por_nombre_exacto():
    """Varias filas en SUNAT (búsqueda por prefijo) pero solo UNA idéntica al
    nombre buscado → se cruza esa (via nombre_exacto), no va a ambiguo.
    Caso real ACRUTA & TAPIA INGENIEROS S.A.C. (3 filas, 1 idéntica ACTIVA)."""
    from orquestador.etapas import Contexto
    from orquestador.etapas_reales import EtapaSunatReal

    espejo = {
        "_meta": {"analisis_id": "x", "concurso": "c", "postor": "p"},
        "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "ESP", "experiencias": [
            {"n": 1, "entidad_emisora": "ACRUTA & TAPIA INGENIEROS S.A.C.",
             "fecha_inicial": "2020-01-01", "fecha_final": "2021-01-01"},
        ]}],
        "resumen_evaluacion": {"factores": []},
    }

    def buscador(nombre):  # SUNAT por prefijo devuelve 3, solo 1 idéntica
        return [
            {"ruc": "20339231983", "razon_social": "ACRUTA-TAPIA ING. SA Y SAG. ING. CON. SA",
             "estado": "BAJA DEFINITIVA"},
            {"ruc": "20262241441", "razon_social": "ACRUTA & TAPIA INGENIEROS S.A.C.",
             "estado": "ACTIVO"},
            {"ruc": "20433090480", "razon_social": "C.ACRUTA & TAPIA ING.SAC-J.SILVA ING.SRL",
             "estado": "BAJA DEFINITIVA"},
        ]

    consultor = lambda r: EmpresaFake(r, "ACRUTA & TAPIA INGENIEROS S.A.C.", date(2010, 1, 1))
    ctx = Contexto(job=None, espejo=espejo, enriquecimiento={})
    EtapaSunatReal(consultor=consultor, buscador=buscador).correr(ctx)

    assert ctx.enriquecimiento["1:1"]["sunat"]["ruc"] == "20262241441"
    assert ctx.enriquecimiento["1:1"]["sunat"]["via"] == "nombre_exacto"
    assert "ambiguo" not in ctx.enriquecimiento["1:1"]["sunat"]
