"""
Etapas REALES del pipeline — las que la demo corre de verdad.

Cada etapa envuelve un módulo ya probado offline (validacion/, resolucion/,
scraping/, reglas/, entregables/) y respeta el contrato de etapa: no lanza por
item, acumula observaciones/ItemRevision, idempotente, respeta `solo_items`.

Las dependencias de red (InfoObras, SUNAT) son INYECTABLES: los tests pasan
fakes; en producción se usan los clientes en vivo con throttling.

El `ctx.enriquecimiento` (persistido por el motor) acumula por experiencia:
  "n:m" → {cui, via, obra, paralizaciones[(iso,iso)], codigo_infobras, sunat{}}
y por profesional: "prof:n" → {dias_brutos, dias_paralizados, dias_traslape,
  dias_efectivos, anios_efectivos, minimo_anios?, cumple_backend?}
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from schemas import pipeline
from validacion import verificar_espejo
from resolucion import ConsultaInfoObras, resolver_con_dedup
from reglas import anios, dias_efectivos_profesional, periodo_fechas
from entregables import generar_excel_final
from .etapas import Contexto, EtapaIngesta, EtapaStub

logger = logging.getLogger(__name__)

E = pipeline.Etapa
EE = pipeline.EstadoEtapa


def _met(total=0, ok=0, rev=0, err=0) -> pipeline.MetricaEtapa:
    return pipeline.MetricaEtapa(items_total=total, items_ok=ok,
                                 items_revision=rev, items_error=err)


def _res(etapa, estado, met, obs=None) -> pipeline.ResultadoEtapa:
    return pipeline.ResultadoEtapa(etapa=etapa, estado=estado, metrica=met,
                                   observaciones=obs or [])


def _clave(np_: int, ne: int) -> str:
    return f"{np_}:{ne}"


def _fecha_iso(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) == 10:
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


# ── 1 · Revisión de consistencia (las notas puras del validador) ─────────────

class EtapaValidacionReal:
    nombre = E.VALIDACION

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        observaciones = verificar_espejo(ctx.espejo)
        n_exp = sum(len(p.get("experiencias", [])) for p in ctx.espejo.get("profesionales", []))
        return _res(self.nombre, EE.OK, _met(n_exp, n_exp), observaciones)


# ── 2 · Identificación de obras (CUI) ────────────────────────────────────────

class EtapaResolucionCuiReal:
    nombre = E.RESOLUCION_CUI

    def __init__(self, consulta=None):
        self._consulta = consulta  # perezoso: la red solo si la etapa corre

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        consulta = self._consulta or ConsultaInfoObras()
        ok = rev = na = 0
        obs: list[pipeline.Observacion] = []

        pares = list(ctx.items_experiencia())

        # dato humano primero (re-disparo): CUI pegado a mano = resuelto MANUAL
        pendientes = []
        for e, (np_, ne) in pares:
            humano = ctx.datos_humano.get((np_, ne)) or {}
            if humano.get("cui"):
                ctx.enriquecimiento[_clave(np_, ne)] = {
                    "cui": re.sub(r"\D", "", str(humano["cui"])), "via": "MANUAL",
                    "obra": None,
                }
                ok += 1
            elif humano.get("accion") == "no_existe":
                ctx.enriquecimiento[_clave(np_, ne)] = {"cui": None, "via": "NO_EXISTE"}
                ok += 1
            else:
                pendientes.append((e, (np_, ne)))

        for (np_, ne), r in resolver_con_dedup(pendientes, consulta):
            k = _clave(np_, ne)
            if r["estado"] == "resuelto":
                ctx.enriquecimiento[k] = {"cui": r["cui"], "via": r["via"], "obra": r["obra"]}
                ok += 1
                if r["via"] == "PROBABLE":
                    obs.append(pipeline.Observacion(
                        codigo="CUI", severidad=pipeline.Severidad.ADVERTENCIA,
                        mensaje=f"obra identificada como probable — {r['decision']}",
                        origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            elif r["estado"] == "na":
                ctx.enriquecimiento[k] = {"cui": None, "via": "NA"}
                na += 1
            else:
                rev += 1
                ya = any(it.n_prof == np_ and it.n_exp == ne and not it.resuelto
                         for it in ctx.job.items_revision)
                if not ya:
                    prof = next((p for p in ctx.espejo.get("profesionales", [])
                                 if p.get("n_prof") == np_), {})
                    exp = next((x for x in prof.get("experiencias", [])
                                if x.get("n") == ne), {})
                    ctx.job.items_revision.append(pipeline.ItemRevision(
                        n_prof=np_, n_exp=ne, etapa=self.nombre,
                        motivo=r["decision"], accion_sugerida="elegir candidato o pegar CUI",
                        candidatos=r["candidatos"],
                        profesional=prof.get("nombre"), cargo=prof.get("cargo"),
                        proyecto=exp.get("proyecto"),
                        fechas=f"{exp.get('fecha_inicial')} → {exp.get('fecha_final')}",
                    ))

        total = len(pares)
        estado = EE.OK_CON_REVISION if rev else EE.OK
        return _res(self.nombre, estado, _met(total, ok + na, rev))


# ── 3a · Consulta a InfoObras (paralizaciones + descargas) ───────────────────

class EtapaInfoObrasReal:
    nombre = E.INFOOBRAS

    def __init__(self, fetcher: Optional[Callable] = None,
                 dir_descargas: Optional[Path] = None,
                 descargar: Optional[Callable] = None):
        self._fetcher = fetcher
        self.dir_descargas = dir_descargas
        self._descargar = descargar
        self.max_descargas = int(os.getenv("PIVOTE_MAX_DESCARGAS", "0"))

    def _fetch(self, cui: str, cert_ini=None, cert_fin=None):
        if self._fetcher:
            return self._fetcher(cui)
        from scraping.infoobras import fetch_by_cui
        return fetch_by_cui(cui, cert_ini, cert_fin)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ok = err = 0
        obs: list[pipeline.Observacion] = []
        descargadas = 0
        cache: dict[str, object] = {}

        for _e, (np_, ne) in ctx.items_experiencia():
            k = _clave(np_, ne)
            enr = ctx.enriquecimiento.get(k) or {}
            cui = enr.get("cui")
            if not cui:
                continue  # sin obra identificada: nada que consultar
            # ventana del certificado: cuando un CUI tiene varias obras, sirve
            # para elegir la que cubre el periodo que el profesional supervisó
            cert_ini, cert_fin = _fecha_iso(_e.get("fecha_inicial")), _fecha_iso(_e.get("fecha_final"))
            ckey = (cui, cert_ini, cert_fin)
            try:
                obra = (cache[ckey] if ckey in cache
                        else cache.setdefault(ckey, self._fetch(cui, cert_ini, cert_fin)))
            except Exception as ex:  # noqa: BLE001 — portal intermitente
                logger.warning("InfoObras CUI %s: %r", cui, ex)
                obra = None
            if obra is None:
                err += 1
                obs.append(pipeline.Observacion(
                    codigo="INFOOBRAS", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"la obra CUI {cui} no respondió en InfoObras — sin paralizaciones que descontar",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
                continue

            from scraping.infoobras import periodos_inactividad
            periodos = periodos_inactividad(getattr(obra, "avances", []) or [])
            enr["paralizaciones"] = [
                {"inicio": p["inicio"].isoformat(), "fin": p["fin"].isoformat(),
                 "tipo": p["tipo"]} for p in periodos
            ]
            enr["codigo_infobras"] = getattr(obra, "codigo_infobras", None)
            enr["obra_nombre"] = getattr(obra, "nombre", None)
            # ficha de la obra + todas las valorizaciones (para la hoja Excel)
            fi, ff = getattr(obra, "fecha_inicio", None), getattr(obra, "fecha_fin", None)
            enr["obra_ficha"] = {
                "cui": cui,
                "codigo_infobras": getattr(obra, "codigo_infobras", None),
                "estado": getattr(obra, "estado", None),
                "monto": getattr(obra, "monto_ejecutado_acumulado", None)
                         or getattr(obra, "monto_contrato", None),
                "fecha_inicio": fi.isoformat() if fi else None,
                "fecha_fin": ff.isoformat() if ff else None,
            }
            enr["valorizaciones"] = [
                {"anio": a.anio, "mes": a.mes, "estado": getattr(a, "estado", None),
                 "fisico_real": getattr(a, "avance_fisico_real", None),
                 "valorizado_real": getattr(a, "valorizado_real", None)}
                for a in (getattr(obra, "avances", []) or [])
                if getattr(a, "anio", 0) and getattr(a, "mes", 0)
            ]
            ctx.enriquecimiento[k] = enr
            ok += 1
            if periodos:
                dias_p = sum((p["fin"] - p["inicio"]).days + 1 for p in periodos)
                n_par = sum(1 for p in periodos if p["tipo"] == "paralizado")
                n_gap = sum(1 for p in periodos if p["tipo"] == "sin_valorizacion")
                partes = []
                if n_par:
                    partes.append(f"{n_par} paralización(es)")
                if n_gap:
                    partes.append(f"{n_gap} periodo(s) sin valorización (obra parada)")
                obs.append(pipeline.Observacion(
                    codigo="PARALIZACION", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"la obra CUI {cui} tiene {' y '.join(partes)} ({dias_p} días) "
                            f"— no cuentan como experiencia",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

            # descarga de documentos (acotada para la demo)
            if (self.dir_descargas and descargadas < self.max_descargas
                    and getattr(obra, "obra_id", None)):
                destino = self.dir_descargas / f"{ctx.job.job_id}.descargas" / f"P{np_}_E{ne}"
                try:
                    descargar = self._descargar
                    if descargar is None:
                        from entregables.zip_infoobras import descargar_documentos_obra
                        descargar = descargar_documentos_obra
                    descargar(obra.obra_id, destino)
                    descargadas += 1
                except Exception as ex:  # noqa: BLE001
                    logger.warning("descarga obra %s: %r", cui, ex)

        total = sum(1 for _ in ctx.items_experiencia())
        return _res(self.nombre, EE.OK if err == 0 else EE.ERROR_PARCIAL,
                    _met(total, ok, 0, err), obs)


# ── 3b · Consulta a SUNAT (ALT04) ────────────────────────────────────────────

class EtapaSunatReal:
    nombre = E.SUNAT

    def __init__(self, consultor: Optional[Callable] = None):
        self._consultor = consultor

    def _consultar(self, ruc: str):
        if self._consultor:
            return self._consultor(ruc)
        from scraping.sunat import consultar_ruc
        return consultar_ruc(ruc)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ok = err = 0
        obs: list[pipeline.Observacion] = []
        cache: dict[str, object] = {}
        total = 0

        for e, (np_, ne) in ctx.items_experiencia():
            texto = f"{e.get('ruc_emisor') or ''} {e.get('entidad_emisora') or ''}"
            m = re.search(r"\b(\d{11})\b", texto)
            if not m:
                continue
            total += 1
            ruc = m.group(1)
            try:
                emp = cache[ruc] if ruc in cache else cache.setdefault(ruc, self._consultar(ruc))
            except Exception as ex:  # noqa: BLE001
                logger.warning("SUNAT %s: %r", ruc, ex)
                emp = None
            if emp is None:
                err += 1
                continue
            ok += 1
            k = _clave(np_, ne)
            enr = ctx.enriquecimiento.get(k) or {}
            fins = getattr(emp, "fecha_inscripcion", None)
            enr["sunat"] = {
                "ruc": ruc,
                "razon_social": getattr(emp, "razon_social", None),
                "fecha_inscripcion": fins.isoformat() if fins else None,
                "estado": getattr(emp, "estado", None),
            }
            ctx.enriquecimiento[k] = enr
            ini = _fecha_iso(e.get("fecha_inicial"))
            if fins and ini and fins > ini:
                obs.append(pipeline.Observacion(
                    codigo="ALT04", severidad=pipeline.Severidad.ALERTA,
                    mensaje=f"el emisor (RUC {ruc}) se constituyó el {fins.strftime('%d/%m/%y')}, "
                            f"DESPUÉS del inicio de la experiencia que certifica",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

        return _res(self.nombre, EE.OK if err == 0 else EE.ERROR_PARCIAL,
                    _met(total, ok, 0, err), obs)


# ── 4 · Cálculo de días efectivos (Paso 5 + mínimo de las bases) ─────────────

_RE_MINIMO = re.compile(r"m[ií]nimo\s+(?:de\s+)?(\d+)\s+a[ñn]os?", re.I)


class EtapaReglasReal:
    nombre = E.REGLAS

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        obs: list[pipeline.Observacion] = []
        total = ok = 0
        for p in ctx.espejo.get("profesionales", []):
            np_ = p.get("n_prof")
            total += 1
            periodos: list[tuple[date, date]] = []
            paral_por_idx: dict[int, list[tuple[date, date]]] = {}
            for e in p.get("experiencias", []):
                ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
                if not (ini and fin) or fin < ini:
                    continue
                idx = len(periodos)
                periodos.append((ini, fin))
                enr = ctx.enriquecimiento.get(_clave(np_, e.get("n"))) or {}
                paral = [periodo_fechas(p) for p in enr.get("paralizaciones", [])]
                if paral:
                    paral_por_idx[idx] = paral
            if not periodos:
                continue
            res = dias_efectivos_profesional(periodos, paral_por_idx)
            anios_ef = round(anios(res.dias_efectivos), 2)
            datos = {
                "dias_brutos": res.dias_brutos,
                "dias_paralizados": res.dias_paralizados,
                "dias_traslape": res.dias_traslape,
                "dias_efectivos": res.dias_efectivos,
                "anios_efectivos": anios_ef,
            }
            # mínimo exigido: de los requisitos del cargo (texto de las bases)
            minimo = None
            for v in (p.get("requisitos") or {}).values():
                m = _RE_MINIMO.search(str(v))
                if m:
                    minimo = int(m.group(1))
                    break
            if minimo is not None:
                datos["minimo_anios"] = minimo
                if anios_ef < minimo:
                    datos["cumple_backend"] = (
                        f"NO CUMPLE — {anios_ef} años efectivos (mínimo: {minimo})")
                    obs.append(pipeline.Observacion(
                        codigo="PASO5", severidad=pipeline.Severidad.ALERTA,
                        mensaje=f"profesional {np_}: {anios_ef} años efectivos tras descontar "
                                f"paralizaciones y traslapes — por debajo del mínimo de {minimo} años",
                        origen=self.nombre, referencia=f"prof={np_}"))
            ctx.enriquecimiento[f"prof:{np_}"] = datos
            ok += 1
        return _res(self.nombre, EE.OK, _met(total, ok), obs)


# ── 5 · Excel final ──────────────────────────────────────────────────────────

class EtapaExcelReal:
    nombre = E.EXCEL

    def __init__(self, dir_salida: Path):
        self.dir_salida = Path(dir_salida)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        # pasa los periodos CON su tipo (paralizado / sin valorización) para que
        # el Excel los muestre diferenciados; el generador normaliza las fechas.
        paral: dict[tuple[int, int], list] = {}
        cuis: dict[tuple[int, int], str] = {}
        fichas: dict[tuple[int, int], dict] = {}
        for k, enr in ctx.enriquecimiento.items():
            if ":" not in k or k.startswith("prof:"):
                continue
            np_, ne = (int(x) for x in k.split(":"))
            if enr.get("paralizaciones"):
                paral[(np_, ne)] = enr["paralizaciones"]
            if enr.get("cui"):
                cuis[(np_, ne)] = enr["cui"]
            if enr.get("obra_ficha") or enr.get("valorizaciones"):
                fichas[(np_, ne)] = {**(enr.get("obra_ficha") or {}),
                                     "valorizaciones": enr.get("valorizaciones") or []}
        ruta = self.dir_salida / f"{ctx.job.job_id}.final.xlsx"
        if ruta.exists():
            ruta.unlink()  # regenerar (re-disparo tras revisión humana)
        generar_excel_final(ctx.espejo, ruta, paral, cuis, fichas)
        ctx.job.excel_final = f"/api/pivote/jobs/{ctx.job.job_id}/excel"
        ctx.job.zip_infoobras = f"/api/pivote/jobs/{ctx.job.job_id}/zip"
        zip_previo = self.dir_salida / f"{ctx.job.job_id}.infoobras.zip"
        if zip_previo.exists():
            zip_previo.unlink()  # que el endpoint lo reconstruya con lo nuevo
        n_exp = sum(len(p.get("experiencias", [])) for p in ctx.espejo.get("profesionales", []))
        return _res(self.nombre, EE.OK, _met(n_exp, n_exp))


# ── juego completo ───────────────────────────────────────────────────────────

def etapas_reales(dir_datos: Path, *, consulta_cui=None, fetcher_infoobras=None,
                  consultor_sunat=None, descargar=None):
    """Las 8 etapas de la demo. Los parámetros inyectables son para tests;
    en producción quedan los clientes en vivo."""
    return [
        EtapaIngesta(),
        EtapaValidacionReal(),
        EtapaResolucionCuiReal(consulta=consulta_cui),
        EtapaInfoObrasReal(fetcher=fetcher_infoobras, dir_descargas=Path(dir_datos),
                           descargar=descargar),
        EtapaSunatReal(consultor=consultor_sunat),
        EtapaReglasReal(),
        EtapaExcelReal(Path(dir_datos)),
        EtapaStub(E.PERSISTENCIA),
    ]
