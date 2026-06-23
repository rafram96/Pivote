"""
Etapas REALES del pipeline — las que la demo corre de verdad.

Cada etapa envuelve un módulo ya probado offline (validacion/, resolucion/,
scraping/, reglas/, entregables/) y respeta el contrato de etapa: no lanza por
item, acumula observaciones/ItemRevision, idempotente, respeta `solo_items`.

Las dependencias de red (InfoObras, SUNAT) son INYECTABLES: los tests pasan
fakes; en producción se usan los clientes en vivo con throttling.

El `ctx.enriquecimiento` (persistido por el motor) acumula por experiencia:
  "n:m" → {cui, via, obra, paralizaciones[(iso,iso)], codigo_infoobras, sunat{}}
y por profesional: "prof:n" → {dias_brutos, dias_paralizados, dias_traslape,
  dias_efectivos, anios_efectivos, minimo_anios?, cumple_backend?}
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from schemas import pipeline
from validacion import verificar_espejo
from resolucion import ConsultaInfoObras, resolver_con_dedup
from reglas import anios, dias_efectivos_profesional, periodo_fechas
from entregables import desempaquetar_enriquecimiento, generar_excel_final, mapear_certificados
from .etapas import Contexto, EtapaIngesta, EtapaStub

logger = logging.getLogger(__name__)

E = pipeline.Etapa
EE = pipeline.EstadoEtapa


def _met(total=0, ok=0, rev=0, err=0, reintentos=0, descargas=0, bytes_=0) -> pipeline.MetricaEtapa:
    return pipeline.MetricaEtapa(items_total=total, items_ok=ok,
                                 items_revision=rev, items_error=err,
                                 reintentos=reintentos, descargas=descargas,
                                 bytes_descargados=bytes_)


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


# Umbral de cobertura para mandar a revisión. Con el clamp del Paso 5 ya en
# sitio, la cobertura parcial se PRORRATEA de forma justa (los días fuera de la
# ventana no cuentan), así que solo se manda a revisión la cobertura MUY baja —
# síntoma de obra equivocada o sin valorizaciones reales (recomendación del
# cliente: <20%). Una obra a 46% que igual CUMPLE no necesita revisión.
_COBERTURA_MIN = 0.2


def _fin_de_mes(d: date) -> date:
    """Último día del mes de `d`. La valorización de un mes cubre TODO el mes —
    convención única para cobertura, clamp y mensajes (evita desfase de bordes)."""
    return date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)


def _cobertura_cert(avances, cert_ini: Optional[date], cert_fin: Optional[date]) -> Optional[float]:
    """Fracción [0..1] del periodo del certificado cubierta por el rango de
    valorizaciones de la obra. None si faltan datos para decidir."""
    if not (cert_ini and cert_fin) or cert_fin <= cert_ini:
        return None
    meses = [date(a.anio, a.mes, 1) for a in (avances or [])
             if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
    if not meses:
        return 0.0
    vi, vf = min(meses), max(meses)
    # fin-de-mes de la última valoriz: misma ventana que el clamp (_fuera_de_ventana)
    solape = (min(cert_fin, _fin_de_mes(vf)) - max(cert_ini, vi)).days
    return max(0, solape) / (cert_fin - cert_ini).days


def _fuera_de_ventana(avances, cert_ini: Optional[date], cert_fin: Optional[date]
                      ) -> list[tuple[date, date]]:
    """Tramos del certificado que caen FUERA de la ventana de valorizaciones de
    la obra (antes de la 1ª / después de la última). Son días sin valorización
    que los respalde → no cuentan como experiencia (clamp del Paso 5).

    Si la obra no tiene avances, TODO el certificado queda fuera. Estos tramos
    son disjuntos de los huecos internos (que viven DENTRO de [1ª, última]), así
    que no hay doble descuento. Solo aplica a obras traídas con éxito; un fetch
    fallido NO se clampa (ventana desconocida) — eso se marca sin_verificar."""
    if not (cert_ini and cert_fin):
        return []
    meses = [date(a.anio, a.mes, 1) for a in (avances or [])
             if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
    if not meses:
        return [(cert_ini, cert_fin)]  # obra sin valorizaciones → todo fuera
    vi, vf = min(meses), max(meses)
    vf_fin = _fin_de_mes(vf)  # la valoriz del último mes cubre todo el mes
    fuera: list[tuple[date, date]] = []
    if vi > cert_ini:
        fuera.append((cert_ini, vi - timedelta(days=1)))
    if vf_fin < cert_fin:
        fuera.append((vf_fin + timedelta(days=1), cert_fin))
    return fuera


def _motivo_cobertura(avances, cert_ini, cert_fin, cod, pct: int) -> str:
    """Mensaje específico —legible para un evaluador NO técnico— de por qué la
    obra no cubre el periodo certificado. Distingue las causas en vez de un
    genérico '% de solape'."""
    cod = cod or "?"
    meses = [date(a.anio, a.mes, 1) for a in (avances or [])
             if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
    if not meses:
        return (f"la obra {cod} está registrada SIN valorizaciones ejecutadas "
                f"— no es verificable en InfoObras")
    vi, vf = min(meses), max(meses)
    if cert_ini and _fin_de_mes(vf) < cert_ini:  # mismo borde de mes que el clamp
        return (f"la obra {cod} valorizó hasta {vf.strftime('%m/%Y')}, antes de que "
                f"empiece el certificado ({cert_ini.strftime('%m/%Y')}) — periodo no respaldado")
    if cert_fin and vi > cert_fin:
        return (f"la obra {cod} empezó a valorizar en {vi.strftime('%m/%Y')}, después de "
                f"que termina el certificado ({cert_fin.strftime('%m/%Y')}) — periodo no respaldado")
    return (f"el periodo del certificado solo solapa {pct}% con las valorizaciones de "
            f"la obra {cod} — posible obra complementaria o periodo en un hueco")


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
        ok = rev = 0
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
            else:  # 'revision' o 'na': NADA se descarta en silencio — todo CUI no
                   # resuelto surge en "Por confirmar" (elegir candidato, pegar el
                   # CUI a mano, o descartar la experiencia).
                rev += 1
                if r["estado"] == "na":                       # tipo fuera del alcance
                    ctx.enriquecimiento[k] = {"cui": None, "via": "NA"}
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
        return _res(self.nombre, estado, _met(total, ok, rev))


# ── 3a · Consulta a InfoObras (paralizaciones + descargas) ───────────────────

class EtapaInfoObrasReal:
    nombre = E.INFOOBRAS

    def __init__(self, fetcher: Optional[Callable] = None,
                 dir_descargas: Optional[Path] = None,
                 descargar: Optional[Callable] = None):
        self._fetcher = fetcher
        self.dir_descargas = dir_descargas
        self._descargar = descargar
        # Sin definir → SIN LÍMITE (descarga TODOS los documentos necesarios).
        # 0 = ninguna (solo transporte). N>0 = tope (solo para acotar pruebas).
        _raw = os.getenv("PIVOTE_MAX_DESCARGAS")
        self.max_descargas = None if _raw is None or not _raw.strip() else int(_raw)

    def _fetch(self, cui: str, cert_ini=None, cert_fin=None, obra_id=None):
        if self._fetcher:
            try:
                return self._fetcher(cui, cert_ini, cert_fin, obra_id)
            except TypeError:
                return self._fetcher(cui)
        from scraping.infoobras import fetch_by_cui
        return fetch_by_cui(cui, cert_ini, cert_fin, obra_id)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        obs: list[pipeline.Observacion] = []
        cache: dict[tuple, object] = {}
        cont = {"ok": 0, "rev": 0, "err": 0}

        def _fetch_obra(cui, cert_ini, cert_fin, obra_id=None):
            # Cachea SOLO éxitos: si la obra cae por flakiness no se memoriza el
            # None, para que la 2da pasada (o un hermano con el mismo CUI) pueda
            # reintentar. La ventana del certificado desambigua si el CUI trae
            # varias obras.
            if obra_id is not None:
                ckey_lookup = (cui, None, None, obra_id)
                if ckey_lookup in cache:
                    return cache[ckey_lookup]

            ckey = (cui, cert_ini, cert_fin, obra_id)
            if ckey in cache:
                return cache[ckey]
            try:
                obra = self._fetch(cui, cert_ini, cert_fin, obra_id)
            except Exception as ex:  # noqa: BLE001 — portal intermitente
                logger.warning("InfoObras CUI %s: %r", cui, ex)
                return None
            if obra is not None:
                cache[ckey] = obra
                if getattr(obra, "obra_id", None) is not None:
                    cache[(cui, None, None, obra.obra_id)] = obra
            return obra

        def _procesar(_e, np_, ne, cui, cert_ini, cert_fin, obra):
            from scraping.infoobras import periodos_inactividad
            k = _clave(np_, ne)
            enr = ctx.enriquecimiento.get(k) or {}
            periodos = periodos_inactividad(getattr(obra, "avances", []) or [])
            enr["paralizaciones"] = [
                {"inicio": p["inicio"].isoformat(), "fin": p["fin"].isoformat(),
                 "tipo": p["tipo"]} for p in periodos
            ]
            # CLAMP (Paso 5): el tramo del certificado fuera de la ventana de
            # valorizaciones no cuenta como experiencia (sin valoriz que lo
            # respalde). Se inyecta como descuento para que reglas/ lo reste sin
            # tocar su firma. Disjunto de los huecos internos → sin doble conteo.
            enr["paralizaciones"] += [
                {"inicio": a.isoformat(), "fin": b.isoformat(), "tipo": "fuera_de_ventana"}
                for a, b in _fuera_de_ventana(getattr(obra, "avances", []) or [], cert_ini, cert_fin)
            ]
            enr.pop("sin_verificar", None)  # se trajo OK: ya no es incierta
            enr["codigo_infoobras"] = getattr(obra, "codigo_infoobras", None)
            enr["obra_nombre"] = getattr(obra, "nombre", None)
            # ficha de la obra + todas las valorizaciones (para la hoja Excel)
            fi, ff = getattr(obra, "fecha_inicio", None), getattr(obra, "fecha_fin", None)
            enr["obra_ficha"] = {
                "cui": cui,
                "codigo_infoobras": getattr(obra, "codigo_infoobras", None),
                "estado": getattr(obra, "estado", None),
                "monto": getattr(obra, "monto_ejecutado_acumulado", None)
                         or getattr(obra, "monto_contrato", None),
                "fecha_inicio": fi.isoformat() if fi else None,
                "fecha_fin": ff.isoformat() if ff else None,
            }
            enr["valorizaciones"] = [
                {"anio": a.anio, "mes": a.mes, "estado": getattr(a, "estado", None),
                 "fisico_real": getattr(a, "avance_fisico_real", None),
                 "valorizado_real": getattr(a, "valorizado_real", None),
                 "docs": getattr(a, "num_documentos", 0)}
                for a in (getattr(obra, "avances", []) or [])
                if getattr(a, "anio", 0) and getattr(a, "mes", 0)
            ]
            # modificaciones de plazo (ampliaciones/suspensiones): explican el
            # hueco entre valorizaciones y la vida oficial de la obra. Solo para
            # mostrar al evaluador — NO cuentan como experiencia (sin valorización).
            enr["modificaciones_plazo"] = [
                {"tipo": m.tipo, "causal": m.causal, "dias": m.dias_aprobados,
                 "fecha_aprobacion": m.fecha_aprobacion.isoformat() if m.fecha_aprobacion else None,
                 "fecha_fin": m.fecha_fin.isoformat() if m.fecha_fin else None}
                for m in (getattr(obra, "modificaciones_plazo", []) or [])
            ]
            ctx.enriquecimiento[k] = enr
            cont["ok"] += 1
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

            # cobertura: ¿las valorizaciones de la obra elegida cubren el periodo
            # certificado? Si casi no solapan, el emparejamiento es dudoso (obra
            # equivocada o periodo en un hueco) → revisión humana.
            cob = _cobertura_cert(getattr(obra, "avances", []) or [], cert_ini, cert_fin)
            if cob is not None and cob < _COBERTURA_MIN:
                pct = round(cob * 100)
                cod = getattr(obra, "codigo_infoobras", None)
                motivo = _motivo_cobertura(getattr(obra, "avances", []) or [],
                                           cert_ini, cert_fin, cod, pct)
                obs.append(pipeline.Observacion(
                    codigo="COBERTURA", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"{motivo} (CUI {cui})",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
                ya = any(it.n_prof == np_ and it.n_exp == ne and not it.resuelto
                         for it in ctx.job.items_revision)
                if not ya:
                    prof = next((p for p in ctx.espejo.get("profesionales", [])
                                 if p.get("n_prof") == np_), {})
                    ctx.job.items_revision.append(pipeline.ItemRevision(
                        n_prof=np_, n_exp=ne, etapa=self.nombre,
                        motivo=motivo,
                        accion_sugerida="confirmar la obra o pegar el CUI correcto",
                        candidatos=[],
                        profesional=prof.get("nombre"), cargo=prof.get("cargo"),
                        proyecto=_e.get("proyecto"),
                        fechas=f"{_e.get('fecha_inicial')} → {_e.get('fecha_final')}",
                    ))
                    cont["rev"] += 1

            # La DESCARGA de documentos ya NO ocurre aquí: se DIFIERE a después del
            # pipeline (descargar_documentos_job, disparada por la API) usando el
            # obra_id ya persistido en el enriquecimiento. Así el veredicto/Excel
            # quedan listos en ~1 min sin esperar ~1 GB de PDFs (que solo sirven al ZIP).

        # 1ª pasada: procesar lo que responda; lo que cae por flakiness se aparta
        # (todavía NO se marca error) para reintentarlo al final.
        fallidos: list[tuple] = []
        for _e, (np_, ne) in ctx.items_experiencia():
            enr = ctx.enriquecimiento.get(_clave(np_, ne)) or {}
            cui = enr.get("cui")
            if not cui:
                continue  # sin obra identificada: nada que consultar
            cert_ini, cert_fin = _fecha_iso(_e.get("fecha_inicial")), _fecha_iso(_e.get("fecha_final"))
            obra_id = enr.get("obra", {}).get("obra_id") if isinstance(enr.get("obra"), dict) else None
            obra = _fetch_obra(cui, cert_ini, cert_fin, obra_id)
            if obra is None:
                fallidos.append((_e, np_, ne, cui, cert_ini, cert_fin, obra_id))
            else:
                _procesar(_e, np_, ne, cui, cert_ini, cert_fin, obra)

        # 2ª pasada: reintentar las caídas. Ya pasaron minutos procesando el
        # resto → el bache transitorio del portal suele haberse disipado. Solo
        # las que SIGUEN sin responder se marcan como error honesto.
        if fallidos:
            logger.info("InfoObras: 2da pasada para %d obra(s) caídas por flakiness", len(fallidos))
            for _e, np_, ne, cui, cert_ini, cert_fin, obra_id in fallidos:
                obra = _fetch_obra(cui, cert_ini, cert_fin, obra_id)
                if obra is None:
                    cont["err"] += 1
                    # ventana DESCONOCIDA: no se clampa (sería NO CUMPLE falso).
                    # Se marca provisional Y se limpian las paralizaciones de una
                    # corrida exitosa previa (re-disparo): reglas no debe descontar
                    # tramos de una obra que ya no se pudo verificar.
                    k = _clave(np_, ne)
                    enr = ctx.enriquecimiento.get(k) or {}
                    enr["sin_verificar"] = True
                    enr.pop("paralizaciones", None)
                    ctx.enriquecimiento[k] = enr
                    obs.append(pipeline.Observacion(
                        codigo="INFOOBRAS", severidad=pipeline.Severidad.ADVERTENCIA,
                        mensaje=f"la obra CUI {cui} no respondió en InfoObras (tras 2 pasadas) "
                                f"— experiencia sin verificar, veredicto provisional",
                        origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
                else:
                    _procesar(_e, np_, ne, cui, cert_ini, cert_fin, obra)

        total = sum(1 for _ in ctx.items_experiencia())
        # Las métricas de descarga (archivos/bytes/reintentos) las RELLENA la
        # descarga diferida (post-pipeline) sobre esta misma etapa — aquí van en 0.
        estado = (EE.ERROR_PARCIAL if cont["err"]
                  else (EE.OK_CON_REVISION if cont["rev"] else EE.OK))
        return _res(self.nombre, estado, _met(total, cont["ok"], cont["rev"], cont["err"]), obs)


def descargar_documentos_job(espejo, enriquecimiento, job_id, dir_descargas,
                             max_descargas=None, descargar=None):
    """Descarga DIFERIDA de los documentos InfoObras de TODAS las experiencias del
    job a {job}.descargas/P{n}_E{m}, usando el `obra_id` YA persistido en el
    enriquecimiento (sin re-fetch al portal). Idempotente: salta las carpetas que
    ya tienen archivos (skip-existing → re-runs rápidos y reentrada segura).
    Devuelve {descargas, bytes, reintentos} medidos del folder + el scraper."""
    from entregables.zip_infoobras import (
        descargar_documentos_obra_por_hito, descargar_informes_control,
        reset_descargas_stats, descargas_stats)
    base = Path(dir_descargas) / f"{job_id}.descargas"
    reset_descargas_stats()
    bajadas = saltados = 0
    for prof in espejo.get("profesionales", []):
        np_ = prof.get("n_prof")
        for e in prof.get("experiencias", []) or []:
            ne = e.get("n")
            enr = enriquecimiento.get(_clave(np_, ne)) or {}
            obra = enr.get("obra") if isinstance(enr.get("obra"), dict) else None
            obra_id = (obra or {}).get("obra_id")
            if not obra_id:
                saltados += 1            # NA / sin CUI resuelto → no descargable
                continue
            if max_descargas is not None and bajadas >= max_descargas:
                break
            destino = base / f"P{np_}_E{ne}"
            ok = base / f"P{np_}_E{ne}.ok"          # marca de descarga COMPLETA (no .part)
            if ok.exists():
                continue  # ya descargado COMPLETO → idempotencia / re-runs rápidos.
                # (una carpeta a medio bajar NO tiene .ok → se vuelve a intentar)
            try:
                if descargar is not None:           # inyección de tests
                    descargar(obra_id, destino)
                else:
                    descargar_documentos_obra_por_hito(obra_id, destino)
                    cert_ini = _fecha_iso(e.get("fecha_inicial"))
                    cert_fin = _fecha_iso(e.get("fecha_final"))
                    try:
                        descargar_informes_control(obra_id, destino,
                                                   fecha_ini=cert_ini, fecha_fin=cert_fin)
                    except Exception as ex:  # noqa: BLE001
                        logger.warning("informes control obra %s: %r", obra_id, ex)
                base.mkdir(parents=True, exist_ok=True)
                ok.write_text("ok", encoding="utf-8")   # recién aquí: descarga COMPLETA
                bajadas += 1
            except Exception as ex:  # noqa: BLE001
                logger.warning("descarga obra %s (P%sE%s): %r", obra_id, np_, ne, ex)
    if saltados:
        logger.info("descargas job %s: %d experiencia(s) sin obra_id (no descargables)",
                    job_id, saltados)
    n_files = n_bytes = 0
    if base.is_dir():
        for p in base.rglob("*"):
            if p.is_file() and p.suffix != ".ok":   # no contar las marcas
                n_files += 1
                try:
                    n_bytes += p.stat().st_size
                except OSError:
                    pass
    return {"descargas": n_files, "bytes": n_bytes,
            "reintentos": descargas_stats().get("reintentos", 0)}


# ── 3b · Consulta a SUNAT (ALT04) + vinculación postor↔emisor ────────────────

_RE_RUC = re.compile(r"\b(\d{11})\b")


def _rucs_postor(espejo: dict) -> set[str]:
    """RUCs de IDENTIDAD del postor/consorcio: de los formularios/anexos
    declarados, la composición del consorcio (`consorciados`, NOTA 14) y la meta.

    **No** mira `experiencia_postor`: esos RUCs son de los clientes/entidades
    contratantes del postor (terceros) → incluirlos daría falsos positivos de
    auto-certificación.
    """
    meta = espejo.get("_meta") or {}
    postor = espejo.get("postor") or {}
    fuentes = [
        meta.get("postor"), meta.get("representante_comun"),
        postor.get("detalle"), postor.get("consorciados"),
        postor.get("formularios"),
    ]
    return set(_RE_RUC.findall(str(fuentes)))


# Entidades públicas: tienen RUC pero NO se cruzan (ALT04 no aplica — existen
# desde siempre; el emisor relevante a verificar son las empresas/consorcios).
_PUBLICO_RE = re.compile(
    r"\b(gobierno\s+regional|gobierno\s+local|municipal|ministerio|essalud|"
    r"es\s?salud|seguro\s+social|gerencia\s+regional|direcci[oó]n\s+regional|"
    r"proyecto\s+especial|unidad\s+ejecutora|instituto\s+nacional)\b", re.I)


def _es_publica(entidad: str) -> bool:
    return bool(_PUBLICO_RE.search(entidad or ""))


def _nombre_emisor_limpio(entidad: str) -> str:
    """Nombre del emisor para buscar en SUNAT: sin paréntesis (miembros del
    consorcio) ni la cola 'RUC …'."""
    s = re.sub(r"\(.*?\)", " ", entidad or "")
    s = re.sub(r"\bRUC\b.*$", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def _elegir_match_exacto(nombre: str, matches: list) -> Optional[dict]:
    """De varias coincidencias SUNAT para un nombre, elige la que tiene la MISMA
    razón social que la buscada.

    La búsqueda de SUNAT es por prefijo, así que un nombre como "ACRUTA & TAPIA
    INGENIEROS S.A.C." trae también empresas parecidas pero distintas (la del
    consorcio, una homónima dada de baja, etc.). Comparando con el nombre
    normalizado (sin sufijos legales/puntuación/acentos) se puede desempatar
    cuando solo UNA fila es idéntica. Si hay varias idénticas, prefiere la
    ACTIVA; si sigue habiendo ambigüedad, devuelve None (revisión humana)."""
    from scraping.sunat import normalizar_nombre_empresa
    objetivo = normalizar_nombre_empresa(nombre)
    if not objetivo:
        return None
    exactas = [m for m in matches
               if normalizar_nombre_empresa(m.get("razon_social") or "") == objetivo]
    if len(exactas) == 1:
        return exactas[0]
    if len(exactas) > 1:
        activas = [m for m in exactas if "ACTIVO" in str(m.get("estado") or "").upper()]
        if len(activas) == 1:
            return activas[0]
    return None


class EtapaSunatReal:
    nombre = E.SUNAT

    def __init__(self, consultor: Optional[Callable] = None,
                 buscador: Optional[Callable] = None):
        self._consultor = consultor
        self._buscador = buscador

    def _consultar(self, ruc: str):
        if self._consultor:
            return self._consultor(ruc)
        from scraping.sunat import consultar_ruc
        return consultar_ruc(ruc)

    def _buscar(self, nombre: str):
        if self._buscador:
            return self._buscador(nombre)
        from scraping.sunat import buscar_por_razon_social
        return buscar_por_razon_social(nombre)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ok = err = rev = 0
        obs: list[pipeline.Observacion] = []
        cache: dict[str, object] = {}
        total = 0
        postor_rucs = _rucs_postor(ctx.espejo)

        for e, (np_, ne) in ctx.items_experiencia():
            entidad = str(e.get("entidad_emisora") or "")
            rucs_e = _RE_RUC.findall(f"{e.get('ruc_emisor') or ''} {entidad}")
            k = _clave(np_, ne)
            ini = _fecha_iso(e.get("fecha_inicial"))

            # ¿hay un emisor verificable? Sin RUC y (sin nombre o entidad pública)
            # → no se cruza (las públicas tienen RUC pero ALT04 no aplica).
            if not rucs_e and (not entidad.strip() or _es_publica(entidad)):
                continue
            total += 1

            # Resolver el RUC del emisor: 1) del certificado · 2) por nombre en SUNAT
            # (la mayoría de certs traen solo el nombre de la empresa/consorcio).
            ruc = via = None
            if rucs_e:
                ruc, via = rucs_e[0], "cert"
            else:
                nombre = _nombre_emisor_limpio(entidad)
                try:
                    matches = self._buscar(nombre) if nombre else []
                except Exception as ex:  # noqa: BLE001
                    logger.warning("SUNAT buscar %r: %r", nombre, ex)
                    matches = []
                if len(matches) == 1:
                    ruc, via = matches[0].get("ruc"), "nombre"
                elif (elegido := _elegir_match_exacto(nombre, matches)):
                    # varias filas, pero solo una idéntica → desempate por nombre
                    ruc, via = elegido.get("ruc"), "nombre_exacto"
                else:
                    rev += 1
                    enr = ctx.enriquecimiento.get(k) or {}
                    if len(matches) > 1:
                        enr["sunat"] = {"nombre": nombre, "ambiguo": len(matches),
                                        "candidatos": [{"ruc": m.get("ruc"),
                                                        "razon_social": m.get("razon_social")}
                                                       for m in matches[:5]]}
                    else:
                        enr["sunat"] = {"nombre": nombre, "no_encontrado": True}
                    ctx.enriquecimiento[k] = enr
                    continue

            # Vinculación postor↔emisor — RUC del cert o el resuelto por nombre.
            vinc = sorted((set(rucs_e) | {ruc}) & postor_rucs)
            if vinc:
                enr = ctx.enriquecimiento.get(k) or {}
                enr["vinculacion_postor_emisor"] = True
                ctx.enriquecimiento[k] = enr
                obs.append(pipeline.Observacion(
                    codigo="VINCULACION", severidad=pipeline.Severidad.ALERTA,
                    mensaje=f"el emisor del certificado (RUC {vinc[0]}) es el propio "
                            f"postor o un consorciado — posible auto-certificación de la experiencia",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

            try:
                emp = cache[ruc] if ruc in cache else cache.setdefault(ruc, self._consultar(ruc))
            except Exception as ex:  # noqa: BLE001
                logger.warning("SUNAT %s: %r", ruc, ex)
                emp = None
            if emp is None:
                err += 1
                continue
            ok += 1
            enr = ctx.enriquecimiento.get(k) or {}
            fins = getattr(emp, "fecha_inscripcion", None)
            ini_act = getattr(emp, "fecha_inicio_actividades", None)
            enr["sunat"] = {
                "ruc": ruc, "via": via,
                "razon_social": getattr(emp, "razon_social", None),
                "fecha_inscripcion": fins.isoformat() if fins else None,
                "estado": getattr(emp, "estado", None),
                "condicion": getattr(emp, "condicion", None),
                "tipo_contribuyente": getattr(emp, "tipo_contribuyente", None),
                "nombre_comercial": getattr(emp, "nombre_comercial", None),
                "domicilio_fiscal": getattr(emp, "domicilio_fiscal", None),
                "fecha_inicio_actividades": ini_act.isoformat() if ini_act else None,
                "actividades_economicas": getattr(emp, "actividades_economicas", None) or [],
            }
            ctx.enriquecimiento[k] = enr
            if fins and ini and fins > ini:
                obs.append(pipeline.Observacion(
                    codigo="ALT04", severidad=pipeline.Severidad.ALERTA,
                    mensaje=f"el emisor (RUC {ruc}) se constituyó el {fins.strftime('%d/%m/%y')}, "
                            f"DESPUÉS del inicio de la experiencia que certifica",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

        return _res(self.nombre, EE.OK if err == 0 else EE.ERROR_PARCIAL,
                    _met(total, ok, rev, err), obs)


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
            sin_verificar: list[int] = []   # experiencias sin ventana conocida
            fechas_invalidas: list[int] = []  # fecha sin leer (ej. "POR VERIFICAR")
            for e in p.get("experiencias", []):
                ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
                if not (ini and fin) or fin < ini:
                    # no se puede contar; si tenía algún dato de fecha, marcarla
                    # (Claude no la leyó) para que el humano la confirme.
                    if e.get("fecha_inicial") or e.get("fecha_final"):
                        fechas_invalidas.append(e.get("n"))
                    continue
                idx = len(periodos)
                periodos.append((ini, fin))
                enr = ctx.enriquecimiento.get(_clave(np_, e.get("n"))) or {}
                if enr.get("sin_verificar"):
                    sin_verificar.append(e.get("n"))
                paral_crudo = [periodo_fechas(x) for x in enr.get("paralizaciones", [])]
                paral = [(a, b) for (a, b) in paral_crudo if b >= a]
                invertidas = len(paral_crudo) - len(paral)
                if invertidas:
                    obs.append(pipeline.Observacion(
                        codigo="PARAL_INVALIDA", severidad=pipeline.Severidad.ALERTA,
                        mensaje=f"{invertidas} paralización(es) de InfoObras con fechas "
                                f"invertidas (inicio posterior al fin) — se ignoran en el "
                                f"cálculo; verificar la obra a mano",
                        origen=self.nombre, referencia=f"prof={np_} exp={e.get('n')}"))
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
            # veredicto provisional: alguna experiencia no se pudo verificar en
            # InfoObras (fetch fallido) → la ventana es desconocida, no se clampó,
            # así que el número puede estar inflado. Va a revisión humana.
            if sin_verificar:
                datos["veredicto_provisional"] = sin_verificar
                exp0 = next((x for x in p.get("experiencias", [])
                             if x.get("n") == sin_verificar[0]), {})
                ya = any(it.n_prof == np_ and it.n_exp == sin_verificar[0] and not it.resuelto
                         for it in ctx.job.items_revision)
                if not ya:
                    ctx.job.items_revision.append(pipeline.ItemRevision(
                        n_prof=np_, n_exp=sin_verificar[0], etapa=self.nombre,
                        motivo=f"no se pudo verificar en InfoObras la(s) experiencia(s) "
                               f"{', '.join(map(str, sin_verificar))} — veredicto provisional",
                        accion_sugerida="reintentar la consulta o verificar la obra a mano",
                        candidatos=[], profesional=p.get("nombre"), cargo=p.get("cargo"),
                        proyecto=exp0.get("proyecto"),
                        fechas=f"{exp0.get('fecha_inicial')} → {exp0.get('fecha_final')}"))
            # NO CUMPLE con una experiencia descartada por fecha sin leer: al
            # confirmar la fecha el veredicto podría cambiar a CUMPLE → revisión.
            if fechas_invalidas and datos.get("cumple_backend"):
                datos["veredicto_provisional"] = (
                    datos.get("veredicto_provisional", []) + fechas_invalidas)
                ne0 = fechas_invalidas[0]
                exp0 = next((x for x in p.get("experiencias", []) if x.get("n") == ne0), {})
                ya = any(it.n_prof == np_ and it.n_exp == ne0 and not it.resuelto
                         for it in ctx.job.items_revision)
                if not ya:
                    ctx.job.items_revision.append(pipeline.ItemRevision(
                        n_prof=np_, n_exp=ne0, etapa=self.nombre,
                        motivo=f"NO CUMPLE pero la(s) experiencia(s) {', '.join(map(str, fechas_invalidas))} "
                               f"no se contó por una fecha sin verificar — confirmarla puede cambiar el veredicto",
                        accion_sugerida="verificar la fecha de fin del certificado",
                        candidatos=[], profesional=p.get("nombre"), cargo=p.get("cargo"),
                        proyecto=exp0.get("proyecto"),
                        fechas=f"{exp0.get('fecha_inicial')} → {exp0.get('fecha_final')}"))
            # ⚖ Regla legal — la AUSENCIA no invalida ("la falta de información es a
            # favor del que declara"). Si el NO CUMPLE depende de una experiencia sin
            # verificar en InfoObras o de una fecha sin leer, NO es un fallo definitivo:
            # se reformula como INCERTIDUMBRE (texto "POR VERIFICAR" → amarillo en el
            # Excel), nunca como NO CUMPLE duro. El NO CUMPLE se reserva para cuando los
            # días caen bajo el mínimo con datos EFECTIVAMENTE verificados.
            prov = datos.get("veredicto_provisional")
            if prov and str(datos.get("cumple_backend", "")).startswith("NO CUMPLE"):
                exps = ", ".join(map(str, sorted(set(prov))))
                datos["cumple_backend"] = (
                    f"POR VERIFICAR — {datos['anios_efectivos']} años efectivos PROVISIONALES "
                    f"(mínimo {datos.get('minimo_anios')}): la(s) experiencia(s) {exps} no se "
                    f"pudo verificar en InfoObras. La ausencia de datos NO invalida la "
                    f"experiencia — confirmar a mano antes de concluir; el cómputo puede estar incompleto.")
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
        paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(ctx.enriquecimiento)
        # experiencias en revisión → su motivo, para que la hoja del profesional
        # muestre "EN REVISIÓN" + la razón en vez de una columna vacía.
        revisiones: dict[tuple[int, int], str] = {}
        for it in ctx.job.items_revision:
            if not it.resuelto and it.n_exp is not None:
                revisiones.setdefault((it.n_prof, it.n_exp), it.motivo)
        ruta = self.dir_salida / f"{ctx.job.job_id}.final.xlsx"
        if ruta.exists():
            ruta.unlink()  # regenerar (re-disparo tras revisión humana)
        # certificados de las experiencias (imágenes) que subió la skill, si los hay
        certs = mapear_certificados(self.dir_salida, ctx.job.job_id)
        generar_excel_final(ctx.espejo, ruta, paral, cuis, fichas, revisiones, sunat, certs)
        ctx.job.excel_final = f"/api/pivote/jobs/{ctx.job.job_id}/excel"
        ctx.job.zip_infoobras = f"/api/pivote/jobs/{ctx.job.job_id}/zip"
        zip_previo = self.dir_salida / f"{ctx.job.job_id}.infoobras.zip"
        if zip_previo.exists():
            zip_previo.unlink()  # que el endpoint lo reconstruya con lo nuevo
        n_exp = sum(len(p.get("experiencias", [])) for p in ctx.espejo.get("profesionales", []))
        return _res(self.nombre, EE.OK, _met(n_exp, n_exp))


# ── juego completo ───────────────────────────────────────────────────────────

def etapas_reales(dir_datos: Path, *, consulta_cui=None, fetcher_infoobras=None,
                  consultor_sunat=None, buscador_sunat=None, descargar=None):
    """Las 8 etapas de la demo. Los parámetros inyectables son para tests;
    en producción quedan los clientes en vivo."""
    return [
        EtapaIngesta(),
        EtapaValidacionReal(),
        EtapaResolucionCuiReal(consulta=consulta_cui),
        EtapaInfoObrasReal(fetcher=fetcher_infoobras, dir_descargas=Path(dir_datos),
                           descargar=descargar),
        EtapaSunatReal(consultor=consultor_sunat, buscador=buscador_sunat),
        EtapaReglasReal(),
        EtapaExcelReal(Path(dir_datos)),
        EtapaStub(E.PERSISTENCIA),
    ]
