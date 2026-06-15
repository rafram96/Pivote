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
    codigo_infobras: str = "INF-001"
    avances: list = field(default_factory=list)


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
        consultor_sunat=consultor_fake, descargar=lambda *a, **k: None)
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
    assert enr["1:1"]["codigo_infobras"] == "INF-001"
    # no quedó error de InfoObras (la 2da pasada la rescató)
    assert not [o for e in job.etapas for o in e.observaciones if o.codigo == "INFOOBRAS"]
    obs = [o for e in job.etapas for o in e.observaciones if o.codigo == "PASO5"]
    assert len(obs) == 1 and "por debajo del mínimo" in obs[0].mensaje


def test_obra_privada_no_va_a_revision(tmp_path):
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
    assert job.estado == JobEstado.COMPLETADO  # N/A no pide revisión humana
    enr = repo.cargar_enriquecimiento(job.job_id)
    assert enr["1:1"]["via"] == "NA"


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
