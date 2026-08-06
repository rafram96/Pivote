"""
Etapas REALES del pipeline — las que la demo corre de verdad.

Cada etapa envuelve un módulo ya probado offline (validacion/, resolucion/,
scraping/, reglas/, entregables/) y respeta el contrato de etapa: no lanza por
item, acumula observaciones/ItemRevision, idempotente, respeta `solo_items`.

Las dependencias de red (InfoObras, SUNAT, RENIPRESS) son INYECTABLES: los
tests pasan fakes; en producción se usan los clientes en vivo con throttling.

El `ctx.enriquecimiento` (persistido por el motor) acumula por experiencia:
  "n:m" → {cui, via, obra, paralizaciones[(iso,iso)], codigo_infoobras,
            sunat{}, renipress{}}
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
from validacion import (a_observaciones, anotar_cargo_nucleo,
                        evaluar_confiabilidad, observaciones_recalculo,
                        recalcular_espejo, revisar_certificados,
                        verificar_espejo)
from resolucion import (ConsultaInfoObras, resolver_con_dedup, resolver_obras,
                        rubros_mixtos)
from resolucion.cui import establecimiento, rubros_de
from reglas import anios, dias_efectivos_profesional, periodo_fechas
from entregables import desempaquetar_enriquecimiento, generar_excel_final, mapear_certificados
from .etapas import Contexto, EtapaIngesta, EtapaStub
from .repositorio import carpeta_job

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


def _recorte(texto, n: int = 40) -> str:
    """Recorta un nombre largo para la línea de progreso, sin romper la barra."""
    t = (texto or "").strip()
    return (t[: n - 1] + "…") if len(t) > n else t


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


def _cobertura_cert(avances, cert_ini: Optional[date], cert_fin: Optional[date],
                    fecha_inicio_obra: Optional[date] = None) -> Optional[float]:
    """Fracción [0..1] del periodo del certificado cubierta por el rango de
    valorizaciones de la obra. None si faltan datos para decidir."""
    if not (cert_ini and cert_fin) or cert_fin <= cert_ini:
        return None
    meses = [date(a.anio, a.mes, 1) for a in (avances or [])
             if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
    if not meses:
        return 0.0
    vi, vf = min(meses), max(meses)
    if fecha_inicio_obra:
        vi = max(vi, fecha_inicio_obra)
    # fin-de-mes de la última valoriz: misma ventana que el clamp (_fuera_de_ventana)
    solape = (min(cert_fin, _fin_de_mes(vf)) - max(cert_ini, vi)).days
    return max(0, solape) / (cert_fin - cert_ini).days


def _fuera_de_ventana(avances, cert_ini: Optional[date], cert_fin: Optional[date],
                      fecha_inicio_obra: Optional[date] = None,
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
    # Una valorización mensual acredita únicamente días en los que la obra ya
    # existía. El lado final NO usa fecha_fin: ampliaciones pueden valorizar
    # legítimamente después de esa ficha (#64, regresión Cajabamba).
    if fecha_inicio_obra:
        vi = max(vi, fecha_inicio_obra)
    vf_fin = _fin_de_mes(vf)  # la valoriz del último mes cubre todo el mes
    fuera: list[tuple[date, date]] = []
    if vi > cert_ini:
        fuera.append((cert_ini, vi - timedelta(days=1)))
    if vf_fin < cert_fin:
        fuera.append((vf_fin + timedelta(days=1), cert_fin))
    return fuera


def _motivo_cobertura(avances, cert_ini, cert_fin, cod, pct: int,
                      fecha_inicio_obra: Optional[date] = None) -> str:
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
    if fecha_inicio_obra and cert_ini and cert_ini < fecha_inicio_obra:
        return (f"la obra {cod} empezó el {fecha_inicio_obra.strftime('%d/%m/%Y')}; "
                f"los días anteriores no están respaldados por una obra existente")
    if cert_ini and _fin_de_mes(vf) < cert_ini:  # mismo borde de mes que el clamp
        return (f"la obra {cod} valorizó hasta {vf.strftime('%m/%Y')}, antes de que "
                f"empiece el certificado ({cert_ini.strftime('%m/%Y')}) — periodo no respaldado")
    if cert_fin and vi > cert_fin:
        return (f"la obra {cod} empezó a valorizar en {vi.strftime('%m/%Y')}, después de "
                f"que termina el certificado ({cert_fin.strftime('%m/%Y')}) — periodo no respaldado")
    return (f"el periodo del certificado solo solapa {pct}% con las valorizaciones de "
            f"la obra {cod} — posible obra complementaria o periodo en un hueco")


def _fx_de_obra(obra, cui) -> dict:
    """Dict-ficha que consume el Excel (render_obra) a partir de un WorkInfo:
    código, CUI, estado, monto, fechas, TODAS las valorizaciones y las
    modificaciones de plazo. Compartido por la ficha de una experiencia normal
    (_procesar) y la de cada sub-obra de un cert multi-obra (_enriquecer_subobra),
    para que ambas se rendericen con el MISMO formato."""
    fi, ff = getattr(obra, "fecha_inicio", None), getattr(obra, "fecha_fin", None)
    return {
        "codigo_infoobras": getattr(obra, "codigo_infoobras", None),
        "cui": cui,
        "estado": getattr(obra, "estado", None),
        "monto": getattr(obra, "monto_ejecutado_acumulado", None)
                 or getattr(obra, "monto_contrato", None),
        "fecha_inicio": fi.isoformat() if fi else None,
        "fecha_fin": ff.isoformat() if ff else None,
        "valorizaciones": [
            {"anio": a.anio, "mes": a.mes, "estado": getattr(a, "estado", None),
             "fisico_real": getattr(a, "avance_fisico_real", None),
             "valorizado_real": getattr(a, "valorizado_real", None),
             "docs": getattr(a, "num_documentos", 0)}
            for a in (getattr(obra, "avances", []) or [])
            if getattr(a, "anio", 0) and getattr(a, "mes", 0)
        ],
        "modificaciones_plazo": [
            {"tipo": m.tipo, "causal": m.causal, "dias": m.dias_aprobados,
             "fecha_aprobacion": m.fecha_aprobacion.isoformat() if m.fecha_aprobacion else None,
             "fecha_fin": m.fecha_fin.isoformat() if m.fecha_fin else None}
            for m in (getattr(obra, "modificaciones_plazo", []) or [])
        ],
    }


# ── 1 · Revisión de consistencia (las notas puras del validador) ─────────────

class EtapaValidacionReal:
    nombre = E.VALIDACION

    def __init__(self, dir_datos=None):
        # La carpeta de datos solo hace falta para leer los recortes de los
        # certificados (#47). Opcional: sin ella la etapa corre igual y la
        # verificación de folio se salta — así los tests que la construyen sin
        # argumentos siguen valiendo.
        self.dir_datos = Path(dir_datos) if dir_datos else None

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ctx.reportar(self.nombre, 0, 0, "Revisando la consistencia de la propuesta")
        # ESCUDO DE INTEGRIDAD (#45 · L1) — lo PRIMERO de la etapa, sobre el espejo
        # tal como llegó. No re-evalúa la propuesta: comprueba que lo que entregó
        # `agent-evaluador` corresponda a los profesionales y experiencias del
        # análisis (que no falten veredictos, que ningún sustento sea de otro).
        #
        # ⚠ TRAMPA (resuelta en dos capas, ambas necesarias):
        # `recalcular_espejo` rellena días/colegiatura y `anotar_cargo_nucleo`
        # reescribe `cargo_bases_valido`. Si el escudo corriera después, vería
        # esas celdas llenas POR EL BACKEND y daría por entregado lo que nunca
        # llegó. Medido: con el orden invertido, el job 12b7cb15ab1e —que llegó
        # sin UNA sola celda del evaluador— pasaba de «no confiable» a «revisar».
        #   1ª capa · el escudo va primero, antes de que nada se toque.
        #   2ª capa · el escudo NO usa como señal ninguna celda que el backend
        #     sepa escribir (`integridad.CAMPOS_EXP` y `_entregado`). Hace falta
        #     porque el espejo se PERSISTE ya recalculado: en un re-disparo, ir
        #     primero no basta — las celdas del backend ya vienen en el archivo.
        confiabilidad = evaluar_confiabilidad(ctx.espejo)
        observaciones = a_observaciones(confiabilidad.hallazgos)
        # Persistir el resultado agregado y su evidencia crítica. El estado de la
        # etapa (`ok_con_revision`) no expresa si el job es solo revisable o si el
        # entregable completo no es confiable.
        if ctx.job is not None:
            ctx.job.confiabilidad = confiabilidad.veredicto
            ctx.job.hallazgos_criticos = [
                o for o in observaciones if o.severidad == pipeline.Severidad.CRITICA
            ]
        # ANTES de verificar: días/meses/años, ¿anterior a colegiatura? y ¿COVID?
        # son ARITMÉTICA, no juicio — el backend los calcula y deja de depender de
        # que el LLM los mande (#45 · L2). Con el defecto `sobrescribir=False` solo
        # rellena huecos, así que `notas` ve el espejo ya completo y sus totales
        # cuadran. Si algún día se activa `sobrescribir=True`, este bloque debe ir
        # DESPUÉS de `verificar_espejo`: las NOTAS 9 y 10 comparan contra lo que
        # escribió Claude y ya no lo encontrarían.
        observaciones += verificar_espejo(ctx.espejo)
        # La verificación conserva primero la cifra original para poder señalar
        # discrepancias; después el entregable adopta SIEMPRE la aritmética
        # inclusiva determinística. Así Base de Datos, CLAUDE y las hojas P usan
        # la misma convención (incluidos los años bisiestos).
        recalculo = recalcular_espejo(ctx.espejo, sobrescribir=True)
        observaciones += observaciones_recalculo(recalculo, origen=E.VALIDACION)
        # DESPUÉS de verificar (que lee el veredicto original de Claude para
        # detectar la contradicción): marca en rojo, dentro del espejo que va al
        # Excel, las experiencias que no acreditan ni cargo ni funciones (#31).
        anotar_cargo_nucleo(ctx.espejo)
        # FOLIO ↔ CERTIFICADO (#47): ¿la página que se embebe como sustento es la
        # del emisor declarado? Solo LEE los recortes; no muta el espejo.
        #
        # Únicamente se reporta el SOSPECHOSO (`ok is False`): confirmar un folio
        # no es un hallazgo y llenaría el Excel de ruido verde, y `ok is None` es
        # ausencia de evidencia, no una alarma. Eso último no es un detalle
        # menor: 727 de los 729 recortes del corpus son escaneos SIN capa de
        # texto, así que hoy la verificación solo puede pronunciarse sobre el
        # 0.3% — abstenerse en el resto es la única respuesta honesta (decisión
        # del desarrollador, 2026-07-26).
        certs = (carpeta_job(self.dir_datos, ctx.job.job_id) / "certs"
                 if self.dir_datos else None)
        for v in (revisar_certificados(certs, ctx.espejo) if certs else []):
            if not v.sospechoso:
                continue
            observaciones.append(pipeline.Observacion(
                codigo="FOLIO", severidad=pipeline.Severidad.ALERTA,
                mensaje=v.motivo, origen=self.nombre,
                referencia=f"prof={v.n_prof} exp={v.n_exp} folio={v.folio}"))
        n_exp = sum(len(p.get("experiencias", [])) for p in ctx.espejo.get("profesionales", []))
        # El escudo NO bloquea el job. Abortar dejaría al evaluador SIN Excel, y
        # el contrato del pipeline es entregar lo que se tenga + la lista de lo
        # que hay que mirar (ver `ItemRevision`): un análisis con una alerta
        # enorme le sirve; ninguno, no. Pero un archivo que PARECE válido y no lo
        # es sí es peor que ninguno, así que una corrida no confiable jamás puede
        # terminar en verde: la etapa queda `ok_con_revision` (el panel la pinta
        # distinto) y los hallazgos viajan como observaciones CRÍTICAS del job,
        # con el texto redactado para que lo lea el evaluador.
        estado = EE.OK if confiabilidad.confiable else EE.OK_CON_REVISION
        return _res(self.nombre, estado, _met(n_exp, n_exp), observaciones)


# ── 2 · Identificación de obras (CUI) ────────────────────────────────────────

class EtapaResolucionCuiReal:
    nombre = E.RESOLUCION_CUI

    def __init__(self, consulta=None):
        self._consulta = consulta  # perezoso: la red solo si la etapa corre

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        consulta = self._consulta or ConsultaInfoObras()
        # base local del MEF (F3): se construye UNA vez por etapa. Import perezoso
        # para no pagar la carga al importar el módulo; `instancia()` es perezosa
        # (no lee el índice hasta la primera consulta). Si algo falla al construirla,
        # se sigue con base=None — el análisis JAMÁS debe caerse por la base.
        try:
            from resolucion import base_mef
            base = base_mef.instancia()
        except Exception:  # noqa: BLE001 — la base MEF es opcional
            base = None
        ok = rev = 0
        obs: list[pipeline.Observacion] = []

        # Frescura de la base (issue #24): si la resolución corrió contra datos
        # de hace semanas, el evaluador tiene que verlo en SU informe. Una obra
        # registrada después de la última actualización buena no está en la base,
        # y su ausencia se lee exactamente igual que un «no existe». Solo se
        # anota cuando hay algo que decir: con la base al día no molesta. Con la
        # base ausente tampoco: eso ya lo cuenta la degradación normal a
        # InfoObras en vivo, y no es un dato envejecido sin avisar.
        if base is not None:
            try:
                fr = base.frescura()
                if fr["estado"] in ("stale", "invalid", "refresco_fallido") and fr["mensaje"]:
                    obs.append(pipeline.Observacion(
                        codigo="BASE_MEF_DESACTUALIZADA",
                        severidad=pipeline.Severidad.ADVERTENCIA,
                        mensaje=fr["mensaje"], origen=self.nombre))
            except Exception:  # noqa: BLE001 — avisar jamás puede tumbar el análisis
                pass

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
            elif e.get("obras"):
                # Cert MULTI-OBRA: un vínculo continuo con VARIAS obras, cada una con
                # su CUI. El "identificador" de la experiencia es su portafolio, no un
                # CUI único → NO va a "Por confirmar". Se verifica cada sub-obra por
                # código (determinístico) y se guarda la lista para el Excel/panel.
                sub = resolver_obras(e.get("obras"), consulta, base=base, exp_madre=e)
                n_res = sum(1 for s in sub if s.get("estado") == "resuelto")
                enr_mo = {"cui": None, "via": "MULTI_OBRA", "obra": None,
                          "sub_obras": sub}
                # CANDADO MULTI-RUBRO (ADR-011 · P1): sub-obras de especialidades
                # distintas y NINGÚN desglose de tiempo por obra → cuánto tiempo
                # corresponde a cada especialidad es genuinamente indecidible sin
                # anexo. Se SEÑALA para que lo confirme un humano; NO se bloquea el
                # cómputo: los días son del vínculo y viven en la experiencia madre
                # (el ADR es explícito). Si el cert declaró las sub-fechas de TODAS
                # las obras (Escenario B), el desglose existe y no hay nada que
                # confirmar; con solo algunas, sigue siendo ambiguo.
                mix = rubros_mixtos(e.get("obras") or [])
                con_sub_fechas = all(o.get("fecha_inicial") and o.get("fecha_final")
                                     for o in (e.get("obras") or []))
                if mix and not con_sub_fechas:
                    enr_mo["multi_rubro"] = sorted(mix)
                    obs.append(pipeline.Observacion(
                        codigo="MULTI_RUBRO", severidad=pipeline.Severidad.ADVERTENCIA,
                        mensaje="Por confirmar — el certificado agrupa obras de "
                                f"especialidades distintas ({', '.join(sorted(mix))}) "
                                "y no declara el tiempo de cada una: para repartir la "
                                "experiencia por especialidad se necesita el anexo de "
                                "desglose. El tiempo total del vínculo no cambia.",
                        origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
                ctx.enriquecimiento[_clave(np_, ne)] = enr_mo
                ok += 1
                # PARCIAL (1 de N): la experiencia cuenta igual —su respaldo es el
                # certificado— pero el conteo deja la brecha a la vista (ADR-011).
                sev = (pipeline.Severidad.INFO if n_res == len(sub)
                       else pipeline.Severidad.ADVERTENCIA)
                obs.append(pipeline.Observacion(
                    codigo="MULTI_OBRA", severidad=sev,
                    mensaje=f"experiencia multi-obra ({len(sub)} sub-proyectos): "
                            f"{n_res} de {len(sub)} identificada(s) en InfoObras",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            else:
                pendientes.append((e, (np_, ne)))

        n_pend = len(pendientes)
        for i, ((np_, ne), r) in enumerate(resolver_con_dedup(pendientes, consulta, base=base), 1):
            ctx.reportar(self.nombre, i, n_pend,
                         f"Ubicando la obra {i} de {n_pend} en el registro público")
            k = _clave(np_, ne)
            if r["estado"] == "resuelto":
                # se persisten candidatos + decision también en los RESUELTOS (no
                # solo en revisión): un PROBABLE auto-elegido (caso obra homónima
                # vieja) necesita mostrar las alternativas para que el evaluador
                # pueda corregir sin re-correr.
                ctx.enriquecimiento[k] = {"cui": r["cui"], "via": r["via"], "obra": r["obra"],
                                          "candidatos": r.get("candidatos") or [],
                                          "decision": r.get("decision"),
                                          # #63: el CUI tiene N registros de obra
                                          # (contingencia/principal/saldo…) — la
                                          # ficha del Excel lo declara
                                          **({"registros_cui": r["registros_cui"]}
                                             if r.get("registros_cui") else {})}
                ok += 1
                if r["via"] == "PROBABLE":
                    obs.append(pipeline.Observacion(
                        codigo="CUI", severidad=pipeline.Severidad.ADVERTENCIA,
                        mensaje=f"obra identificada como probable — {r['decision']}",
                        origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            elif r["estado"] == "na":
                # Cliente/obra PRIVADA: InfoObras no aplica (solo registra obra
                # pública). NO va a "Por confirmar" — no hay acción humana pendiente:
                # el respaldo de una experiencia privada es su certificado. Se deja
                # señalado (via PRIVADA + observación) para el Excel/panel/ZIP.
                ctx.enriquecimiento[k] = {"cui": None, "via": r.get("via") or "NA"}
                obs.append(pipeline.Observacion(
                    codigo="PRIVADA", severidad=pipeline.Severidad.INFO,
                    mensaje=f"experiencia con cliente/obra privada — sin cruce "
                            f"InfoObras (no registra obra privada); el respaldo es "
                            f"el certificado presentado",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            else:  # 'revision': NADA se descarta en silencio — todo CUI no
                   # resuelto surge en "Por confirmar" (elegir candidato, pegar el
                   # CUI a mano, o descartar la experiencia).
                rev += 1
                # Persistir también la abstención. Sin esta marca, REGLAS veía
                # una experiencia con fechas válidas pero sin ficha y la trataba
                # como tiempo verificado. No se promueve ningún candidato: el
                # resolver conserva exactamente su decisión de revisión.
                ctx.enriquecimiento[k] = {
                    **(ctx.enriquecimiento.get(k) or {}),
                    "cui": None, "via": "REVISION", "sin_verificar": True,
                    "decision": r.get("decision"),
                    "candidatos": r.get("candidatos") or [],
                }
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
        # `obs` SÍ viaja: MULTI_OBRA / PROBABLE / PRIVADA se acumulaban y se perdían
        # en el return (quedaban solo en el enriquecimiento, invisibles en el job).
        return _res(self.nombre, estado, _met(total, ok, rev), obs)


# ── 3a · Consulta a InfoObras (paralizaciones + descargas) ───────────────────

class EtapaInfoObrasReal:
    nombre = E.INFOOBRAS

    def __init__(self, fetcher: Optional[Callable] = None,
                 dir_descargas: Optional[Path] = None,
                 descargar: Optional[Callable] = None,
                 verificador_mef: Optional[Callable] = None,
                 consulta_ocds: Optional[Callable] = None):
        self._fetcher = fetcher
        self.dir_descargas = dir_descargas
        self._descargar = descargar
        # Verificación de expedientes contra el MEF (módulo T-003). Inyectable en
        # tests; en producción usa scraping.mef.verificar_cui (best-effort, red).
        self._verificar_mef = verificador_mef
        # T-004: procesos y documentos SEACE por CUI. Inyectable para que la
        # suite sea offline; en producción se usa el cliente OCDS best-effort.
        self._consulta_ocds = consulta_ocds
        # Sin definir → SIN LÍMITE (descarga TODOS los documentos necesarios).
        # 0 = ninguna (solo transporte). N>0 = tope (solo para acotar pruebas).
        _raw = os.getenv("PIVOTE_MAX_DESCARGAS")
        self.max_descargas = None if _raw is None or not _raw.strip() else int(_raw)
        # MODO EXPEDIENTES (camino A): el concurso completo es de elaboración de
        # expedientes técnicos/estudios → TODA experiencia se trata como expediente
        # (verificación MEF/contrato + hito de aprobación; sin clamp por
        # valorizaciones de la construcción posterior). Caso San Isidro: el cert
        # dice "Elaboración del ET: «X»" pero la skill guardó solo «X» y el
        # clasificador por nombre enrutaba 51/68 como obra. La detección por texto
        # (es_expediente_exp) sigue siendo el default cuando el modo no está.
        self.forzar_expedientes = (os.getenv("PIVOTE_FORZAR_EXPEDIENTES") or "") \
            .strip() in ("1", "true", "si", "sí")

    def _fetch(self, cui: str, cert_ini=None, cert_fin=None, obra_id=None):
        if self._fetcher:
            try:
                return self._fetcher(cui, cert_ini, cert_fin, obra_id)
            except TypeError:
                return self._fetcher(cui)
        from scraping.infoobras import fetch_by_cui
        return fetch_by_cui(cui, cert_ini, cert_fin, obra_id)

    def _verificar_expediente_mef(self, exp: dict, cui, codsnip="") -> Optional[dict]:
        """Verifica un expediente contra el MEF (contrato/contratista/resolución).
        SOLO corre si hay un verificador cableado (`verificador_mef`): la app en
        modo real pasa `scraping.mef.verificar_cui`; los tests inyectan un fake; si
        no está, se OMITE (así los tests offline no tocan red). El `codsnip` (de la
        obra de InfoObras) mejora la cobertura del endpoint de contratos. Best-effort:
        si el módulo falla o el portal no responde, devuelve None y el análisis sigue."""
        if self._verificar_mef is None:
            return None
        try:
            return self._verificar_mef(exp, cui, codsnip)
        except Exception as e:  # noqa: BLE001
            from scraping.errores_red import corto
            logger.debug("verificación MEF CUI %s: %s", cui, corto(e))
            return None

    def _procesos_seace(self, cui: str):
        if self._consulta_ocds is not None:
            return self._consulta_ocds(cui)
        from scraping.seace_abierto import procesos_por_cui
        return procesos_por_cui(cui)

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
            # ¿Experiencia de EXPEDIENTE técnico aceptada por su aprobación? Sin
            # valorizaciones + nombre de expediente + el hito "Aprobación del proyecto"
            # trajo el documento. Solo entonces cuenta por el periodo del certificado
            # (no se le aplica el clamp fuera_de_ventana ni se manda a revisión).
            from resolucion.cui import es_expediente_exp
            _avances = getattr(obra, "avances", []) or []
            _aprob_exp = getattr(obra, "aprobacion_expediente", None)
            _es_exped = self.forzar_expedientes or es_expediente_exp(_e)
            es_exp_aprobado = (not _avances and _aprob_exp is not None and _es_exped)
            periodos = periodos_inactividad(getattr(obra, "avances", []) or [])
            enr["paralizaciones"] = [
                {"inicio": p["inicio"].isoformat(), "fin": p["fin"].isoformat(),
                 "tipo": p["tipo"]} for p in periodos
            ]
            # CLAMP (Paso 5): el tramo del certificado fuera de la ventana de
            # valorizaciones no cuenta como experiencia (sin valoriz que lo
            # respalde). Se inyecta como descuento para que reglas/ lo reste sin
            # tocar su firma. Disjunto de los huecos internos → sin doble conteo.
            # A un EXPEDIENTE no se le aplica: el estudio precede a la construcción
            # y sus fechas jamás caen dentro de las valorizaciones de la obra.
            if not (es_exp_aprobado or _es_exped):
                _inicio_obra = getattr(obra, "fecha_inicio", None)
                for a, b in _fuera_de_ventana(
                        getattr(obra, "avances", []) or [], cert_ini, cert_fin,
                        _inicio_obra):
                    _tipo = ("antes_inicio_obra" if _inicio_obra and b < _inicio_obra
                             else "fuera_de_ventana")
                    enr["paralizaciones"].append({
                        "inicio": a.isoformat(), "fin": b.isoformat(), "tipo": _tipo,
                        **({"fecha_inicio_obra": _inicio_obra.isoformat()}
                           if _tipo == "antes_inicio_obra" else {}),
                    })
            enr.pop("sin_verificar", None)  # se trajo OK: ya no es incierta
            enr["codigo_infoobras"] = getattr(obra, "codigo_infoobras", None)
            enr["obra_nombre"] = getattr(obra, "nombre", None)
            # ficha de la obra + todas las valorizaciones + modificaciones de plazo,
            # con el helper compartido (misma forma que la ficha de cada sub-obra).
            _fx = _fx_de_obra(obra, cui)
            enr["obra_ficha"] = {k: _fx[k] for k in
                                 ("cui", "codigo_infoobras", "estado", "monto",
                                  "fecha_inicio", "fecha_fin")}
            enr["valorizaciones"] = _fx["valorizaciones"]
            enr["modificaciones_plazo"] = _fx["modificaciones_plazo"]
            if es_exp_aprobado:
                enr["aprobacion_expediente"] = _aprob_exp   # {url,filename,nombre,extension,fecha}
                _f = _aprob_exp.get("fecha")                # ISO "AAAA-MM-DD" | None
                _fm = f"{_f[8:10]}/{_f[5:7]}/{_f[0:4]}" if _f and len(_f) == 10 else None
                obs.append(pipeline.Observacion(
                    codigo="RESPALDO", severidad=pipeline.Severidad.INFO,
                    mensaje=f"experiencia de expediente técnico (sin valorizaciones) — "
                            f"respaldada por la Aprobación del proyecto"
                            f"{f' del {_fm}' if _fm else ''} registrada en InfoObras; "
                            f"cuenta por el periodo del certificado",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            # Verificación de EXPEDIENTES contra el MEF (T-003): si la experiencia es
            # de expediente y hay CUI resuelto, cruzar contra el Banco de Inversiones
            # (contrato/contratista/resolución). Best-effort, no bloquea.
            if cui and _es_exped:
                # el SNIP de la obra de InfoObras mejora la cobertura de contratos del MEF
                _snip = str((getattr(obra, "raw_busqueda", {}) or {}).get("codSnip") or "").strip()
                _vmef = self._verificar_expediente_mef(_e, cui, _snip)
                if _vmef and _vmef.get("verificado_en_mef"):
                    _vmef.setdefault("cod_snip", _snip or None)   # para re-usar en la descarga
                    enr["verificacion_expediente"] = _vmef
                    _ct = (_vmef.get("contrato") or {}).get("numero")
                    obs.append(pipeline.Observacion(
                        codigo="VERIF_MEF", severidad=pipeline.Severidad.INFO,
                        mensaje=f"expediente verificado contra el MEF (CUI {cui}"
                                f"{f' · contrato {_ct}' if _ct else ''})",
                        origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
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
            _inicio_obra = getattr(obra, "fecha_inicio", None)
            cob = _cobertura_cert(
                getattr(obra, "avances", []) or [], cert_ini, cert_fin, _inicio_obra)
            if not es_exp_aprobado and cob is not None and cob < _COBERTURA_MIN:
                pct = round(cob * 100)
                # La etapa REGLAS necesita saberlo: si el clamp deja al profesional
                # bajo el mínimo POR una cobertura casi nula, el NO CUMPLE no puede
                # ser duro — la causa más probable es una obra mal emparejada
                # (error nuestro), no una experiencia inexistente. Ver la «Regla
                # legal» de EtapaReglasReal.
                k_cob = _clave(np_, ne)
                enr_cob = ctx.enriquecimiento.get(k_cob) or {}
                enr_cob["cobertura_baja"] = pct
                ctx.enriquecimiento[k_cob] = enr_cob
                cod = getattr(obra, "codigo_infoobras", None)
                motivo = _motivo_cobertura(getattr(obra, "avances", []) or [],
                                           cert_ini, cert_fin, cod, pct, _inicio_obra)
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

        def _enriquecer_subobra(s: dict) -> dict:
            """Cert MULTI-OBRA: para una sub-obra YA resuelta por código, baja su
            ficha real de InfoObras (periodo de valorizaciones, estado, monto) para
            mostrar info+verificación en el Excel. Si el cert consignó el rango de
            tiempo POR esta obra (fecha_inicial/fecha_final de la sub-obra), computa
            la cobertura; si no, solo trae la ficha (no hay tiempo por-obra que cruzar)."""
            if s.get("estado") != "resuelto":
                return s
            cui = s.get("cui")
            obra_id = (s.get("obra") or {}).get("obra_id")
            si, sf = _fecha_iso(s.get("fecha_inicial")), _fecha_iso(s.get("fecha_final"))
            obra = _fetch_obra(cui, si, sf, obra_id)
            if obra is None:
                s["sin_verificar"] = True   # portal flaky → ficha desconocida (no invalida)
                return s
            s.pop("sin_verificar", None)     # se trajo OK (quizá en la 2ª pasada)
            avances = getattr(obra, "avances", []) or []
            meses = [date(a.anio, a.mes, 1) for a in avances
                     if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
            vi = min(meses) if meses else None
            vf = _fin_de_mes(max(meses)) if meses else None
            # ficha COMPLETA (con TODAS las valorizaciones + modificaciones): el Excel
            # renderiza cada sub-obra como un ítem full con render_obra, igual que una
            # experiencia normal. obra_nombre/periodo_valoriz son extras para el encabezado.
            s["ficha"] = {
                **_fx_de_obra(obra, cui),
                "obra_nombre": getattr(obra, "nombre", None),
                "periodo_valoriz": [vi.isoformat() if vi else None,
                                    vf.isoformat() if vf else None],
            }
            # cruce de tiempo SOLO si el cert dio el rango POR esta obra (la regla
            # del cliente: verificar el tiempo por obra únicamente si es explícito)
            if si and sf:
                if not meses:
                    # obra sin valorizaciones → no hay contra qué cruzar el tiempo
                    s["cobertura"] = {"pct": None, "cubierto": None,
                                      "cert_ini": si.isoformat(), "cert_fin": sf.isoformat(),
                                      "nota": "obra sin valorizaciones"}
                else:
                    cob = _cobertura_cert(
                        avances, si, sf, getattr(obra, "fecha_inicio", None))
                    s["cobertura"] = {
                        "pct": round(cob * 100) if cob is not None else None,
                        "cert_ini": si.isoformat(), "cert_fin": sf.isoformat(),
                        "cubierto": bool(cob is not None and cob >= _COBERTURA_MIN),
                    }
            return s

        # cert MULTI-OBRA: enriquece cada sub-obra resuelta con su ficha real (la
        # etapa de resolución solo verificó existencia por código). Se hace ANTES del
        # loop de cui único (esas experiencias tienen cui=None y se saltarían).
        for _e, (np_, ne) in ctx.items_experiencia():
            enr = ctx.enriquecimiento.get(_clave(np_, ne)) or {}
            if enr.get("via") == "MULTI_OBRA" and enr.get("sub_obras"):
                enr["sub_obras"] = [_enriquecer_subobra(s) for s in enr["sub_obras"]]
                ctx.enriquecimiento[_clave(np_, ne)] = enr

        # 1ª pasada: procesar lo que responda; lo que cae por flakiness se aparta
        # (todavía NO se marca error) para reintentarlo al final.
        n_fetch = sum(1 for _e, (np_, ne) in ctx.items_experiencia()
                      if (ctx.enriquecimiento.get(_clave(np_, ne)) or {}).get("cui"))
        i_fetch = 0
        fallidos: list[tuple] = []
        for _e, (np_, ne) in ctx.items_experiencia():
            enr = ctx.enriquecimiento.get(_clave(np_, ne)) or {}
            cui = enr.get("cui")
            if not cui:
                continue  # sin obra identificada: nada que consultar
            i_fetch += 1
            _proy = _recorte(_e.get("proyecto"))
            ctx.reportar(self.nombre, i_fetch, n_fetch,
                         f"Verificando la obra {i_fetch} de {n_fetch}"
                         + (f" — {_proy}" if _proy else ""))
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
            n_fall = len(fallidos)
            for j, (_e, np_, ne, cui, cert_ini, cert_fin, obra_id) in enumerate(fallidos, 1):
                ctx.reportar(self.nombre, j, n_fall,
                             f"Reintentando la obra {j} de {n_fall} (el portal estaba inestable)")
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

        # 2ª pasada para las sub-obras MULTI-OBRA cuya ficha cayó por flakiness en el
        # pre-loop: mismo criterio que el loop de cui único (ya pasaron minutos → el
        # bache del portal suele haberse disipado). Solo reintenta las sin_verificar.
        for _e, (np_, ne) in ctx.items_experiencia():
            enr = ctx.enriquecimiento.get(_clave(np_, ne)) or {}
            if enr.get("via") != "MULTI_OBRA" or not enr.get("sub_obras"):
                continue
            if not any(s.get("sin_verificar") for s in enr["sub_obras"]):
                continue
            enr["sub_obras"] = [_enriquecer_subobra(s) if s.get("sin_verificar") else s
                                for s in enr["sub_obras"]]
            ctx.enriquecimiento[_clave(np_, ne)] = enr

        # T-004 F2: localizar las Bases Integradas y el contrato del proceso que
        # corresponde a CADA experiencia. Esto es independiente de que InfoObras
        # haya devuelto obra_id: SEACE se consulta por CUI y jamás cruza de tipo.
        from resolucion.cui import es_expediente_exp
        from scraping.seace_abierto import (
            clasificar_proceso, codigo_convocatoria, doc_bases_integradas,
            doc_contrato_firmado, seleccionar_proceso, tipo_esperado,
        )
        from validacion.candado_seace import (
            CONTRADICE, evaluar_candado, resumen_proceso)
        cache_seace: dict[str, object] = {}
        for _e, (np_, ne) in ctx.items_experiencia():
            k = _clave(np_, ne)
            enr = ctx.enriquecimiento.get(k) or {}
            cui = str(enr.get("cui") or "").strip()
            if not cui or str(enr.get("via") or "").upper() == "PRIVADA":
                continue
            if cui not in cache_seace:
                try:
                    cache_seace[cui] = self._procesos_seace(cui)
                except Exception as ex:  # noqa: BLE001 — fuente estatal best-effort
                    logger.warning("SEACE abierto CUI %s: %r", cui, ex)
                    cache_seace[cui] = None
            procesos = cache_seace[cui]
            if procesos is None:
                enr["seace"] = {
                    "estado": "fuente_no_disponible", "cui": cui,
                    "motivo": "la fuente de datos abiertos no respondió; reintentar",
                }
                obs.append(pipeline.Observacion(
                    codigo="SEACE", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"datos abiertos del proceso CUI {cui} no disponibles "
                            f"temporalmente — el análisis continúa",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
                ctx.enriquecimiento[k] = enr
                continue
            if not procesos:
                enr["seace"] = {
                    "estado": "sin_procesos", "cui": cui,
                    "motivo": "el CUI no figura en los datos abiertos disponibles (cobertura 2018+)",
                }
                ctx.enriquecimiento[k] = enr
                continue

            texto = " ".join(str(_e.get(c) or "") for c in
                             ("proyecto", "objeto", "cargo_ocupado", "descripcion"))
            es_exped = self.forzar_expedientes or es_expediente_exp(_e)
            tipo = tipo_esperado(es_exped, texto)
            ini, fin = _fecha_iso(_e.get("fecha_inicial")), _fecha_iso(_e.get("fecha_final"))
            seleccion = seleccionar_proceso(
                procesos, tipo, periodo=(ini, fin) if ini and fin else None)
            elegido = seleccion.get("elegido")
            if elegido is None:
                enr["seace"] = {
                    "estado": "sin_tipo", "cui": cui, "proceso_objeto": tipo,
                    "seleccion": None, "motivo": seleccion.get("motivo"),
                    "candidatos": seleccion.get("candidatos") or [],
                }
                ctx.enriquecimiento[k] = enr
                continue

            # F5: la identidad del proceso sale de `resumen_proceso`, que abarca
            # TODOS sus contratos. `contracts[0]` es arbitrario y puede ser una
            # adenda de dos días (caso real CUI 2343407) — de ahí salían la
            # «fecha de firma» y la vigencia que se muestran en el Excel.
            resumen = resumen_proceso(elegido)
            resumen["tipo"] = clasificar_proceso(elegido)[0]
            bases, firmado = doc_bases_integradas(elegido), doc_contrato_firmado(elegido)
            seace = {
                "estado": "seleccionado",
                "cui": cui,
                "codigoconvocatoria": codigo_convocatoria(elegido),
                "ocid": elegido.get("ocid"),
                "proceso_objeto": tipo,
                "seleccion": seleccion.get("seleccion"),
                "ambiguo": bool(seleccion.get("ambiguo")),
                "motivo": seleccion.get("motivo"),
                "fecha_suscripcion": resumen.get("fecha_firma"),
                "vigencia": [resumen.get("vigencia_inicio"),
                             resumen.get("vigencia_fin")],
                "docs": {
                    "bases": {
                        "estado": "disponible" if bases else "no_disponible",
                        "url": (bases or {}).get("url"),
                        "titulo": (bases or {}).get("title"),
                        "formato": (bases or {}).get("format"),
                    },
                    "contrato": {
                        "estado": "disponible" if firmado else "no_disponible",
                        "url": (firmado or {}).get("url"),
                        "titulo": (firmado or {}).get("title"),
                        "formato": (firmado or {}).get("format"),
                    },
                },
            }
            # T-004 F5 — candado de identidad: elegir el proceso por CUI+tipo NO
            # prueba que sea el del certificado. El resumen del proceso se
            # PERSISTE (identidad estructurada, sin PDFs) para poder re-evaluar
            # el candado sin volver a la fuente.
            seace["proceso"] = resumen
            candado = evaluar_candado(resumen, {
                "entidad_contratante": _e.get("entidad_contratante"),
                "entidad_emisora": _e.get("entidad_emisora"),
                "ruc_emisor": _e.get("ruc_emisor"),
                "tipo_experiencia": tipo,
                "fecha_inicial": _e.get("fecha_inicial"),
                "fecha_final": _e.get("fecha_final"),
                "monto_contrato_soles": _e.get("monto_contrato_soles"),
            })
            seace["candado"] = candado.como_dict()
            enr["seace"] = seace
            if candado.resultado == CONTRADICE:
                # Una contradicción se SEÑALA, no se esconde ni bloquea: los PDF
                # siguen yendo al ZIP como sustento, con el rótulo que
                # corresponde.
                obs.append(pipeline.Observacion(
                    codigo="SEACE", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"los documentos del proceso encontrado para el CUI {cui} "
                            f"no coinciden con el certificado: {candado.motivo}",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            if seace["ambiguo"]:
                obs.append(pipeline.Observacion(
                    codigo="SEACE", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"hay varios procesos de {tipo} para el CUI {cui}; "
                            f"se eligió el más reciente y debe confirmarse en el ZIP",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))
            ctx.enriquecimiento[k] = enr

        total = sum(1 for _ in ctx.items_experiencia())
        # Las métricas de descarga (archivos/bytes/reintentos) las RELLENA la
        # descarga diferida (post-pipeline) sobre esta misma etapa — aquí van en 0.
        estado = (EE.ERROR_PARCIAL if cont["err"]
                  else (EE.OK_CON_REVISION if cont["rev"] else EE.OK))
        return _res(self.nombre, estado, _met(total, cont["ok"], cont["rev"], cont["err"]), obs)


_NOTAS_DESCARGA = ("_ERROR.TXT", "_NO_DISPONIBLE.TXT", "SIN_DOCUMENTOS.TXT")


def _es_documento_descargado(path: Path) -> bool:
    """Distingue documentos reales de marcas, temporales y notas de diagnóstico."""
    nombre = path.name.upper()
    return (path.is_file() and path.suffix.lower() not in (".part", ".ok")
            and not any(nombre.endswith(s) for s in _NOTAS_DESCARGA))


def _inventario_real_descarga(destino: Path) -> tuple[int, dict[str, int]]:
    """Cuenta archivos reales totales y por hito YYYY-MM dentro de Valorizaciones."""
    if not destino.is_dir():
        return 0, {}
    archivos = [p for p in destino.rglob("*") if _es_documento_descargado(p)]
    por_hito: dict[str, int] = {}
    raiz = destino / "Valorizaciones"
    if raiz.is_dir():
        for carpeta in raiz.iterdir():
            if not carpeta.is_dir():
                continue
            clave = carpeta.name[:7] if re.match(r"^\d{4}-\d{2}", carpeta.name) else carpeta.name
            por_hito[clave] = sum(
                1 for p in carpeta.rglob("*") if _es_documento_descargado(p)
            )
    return len(archivos), por_hito


def _estado_seccion(secciones: dict, avisos: list[str], nombre: str,
                    esperados: int, descargados: int) -> None:
    if esperados <= 0:
        estado = "sin_documentos"
    elif descargados >= esperados:
        estado = "completa"
    elif descargados:
        estado = "parcial"
        avisos.append(f"{nombre}: {descargados} de {esperados} documentos descargados.")
    else:
        estado = "error"
        avisos.append(f"{nombre}: no se descargó ninguno de los {esperados} documentos disponibles.")
    secciones[nombre] = {
        "estado": estado, "esperados": esperados, "descargados": descargados,
    }


def descargar_documentos_job(espejo, enriquecimiento, job_id, dir_descargas,
                             max_descargas=None, descargar=None, reportar=None,
                             descargar_seace=None, dir_cache_seace=None):
    """Descarga DIFERIDA de InfoObras y SEACE a {job}.descargas/P{n}_E{m}.
    Cada fuente tiene su propia marca idempotente: una experiencia puede traer
    documentos SEACE aunque no tenga `obra_id`, y completar una fuente no salta
    la otra.
    Devuelve {descargas, bytes, reintentos} medidos del folder + el scraper.

    `reportar(procesadas, total, nombre_obra)` (opcional): avance para la barra del
    panel — se llama al empezar cada experiencia descargable. Un reintento NO
    reinicia el contador."""
    from entregables.zip_infoobras import (
        descargar_documentos_obra_por_hito, descargar_informes_control,
        descargar_datos_cierre, descargar_aprobacion_expediente,
        reset_descargas_stats, descargas_stats, resumen_descargas)
    from scraping.errores_red import corto
    base = carpeta_job(Path(dir_descargas), job_id) / "descargas"
    from orquestador.descargas_infoobras import (
        CacheDescargasInfoObras, secciones_en_error)
    from orquestador.descargas_seace import (
        DOCUMENTOS_SEACE, CacheDescargasSeace, etiqueta_documento_seace,
        NOTA_SEACE_DESCARGA_FALLIDA, nota_seace_ausencia)
    cache_infoobras = CacheDescargasInfoObras(
        carpeta_job(Path(dir_descargas), job_id) / "cache_obras"
    )
    # Un corte duro (kill/reinicio) deja `.{obra}.{uuid}.part` que nadie recoge:
    # se limpian al arrancar la descarga del job (issue #81, R4).
    huerfanos = cache_infoobras.recolectar_temporales()
    if huerfanos:
        logger.info("descargas job %s: %d carpeta(s) temporal(es) recolectada(s)",
                    job_id, huerfanos)
    cache_seace = CacheDescargasSeace(
        Path(dir_cache_seace)
        if dir_cache_seace is not None
        else Path(dir_descargas) / "referencia" / "seace"
    )
    reset_descargas_stats()
    bajadas = saltados = 0

    requisitos_obra: dict[str, dict] = {}
    for profesional in espejo.get("profesionales", []):
        np_requisito = profesional.get("n_prof")
        for experiencia in profesional.get("experiencias", []) or []:
            enr_requisito = enriquecimiento.get(
                _clave(np_requisito, experiencia.get("n"))) or {}
            obra_requisito = (enr_requisito.get("obra")
                              if isinstance(enr_requisito.get("obra"), dict) else {})
            oid = obra_requisito.get("obra_id")
            if not oid:
                continue
            requisito = requisitos_obra.setdefault(str(oid), {})
            if enr_requisito.get("aprobacion_expediente") and not requisito.get("aprobacion"):
                requisito["aprobacion"] = enr_requisito["aprobacion_expediente"]
            verificacion = enr_requisito.get("verificacion_expediente")
            if (isinstance(verificacion, dict) and verificacion.get("cui_confirmado")
                    and not requisito.get("verificacion")):
                requisito["verificacion"] = verificacion

    def _obra_id(np_, ne):
        enr = enriquecimiento.get(_clave(np_, ne)) or {}
        o = enr.get("obra") if isinstance(enr.get("obra"), dict) else None
        return (o or {}).get("obra_id")

    def _seace(np_, ne):
        enr = enriquecimiento.get(_clave(np_, ne)) or {}
        return enr.get("seace") if isinstance(enr.get("seace"), dict) else None

    def _nota_atomica(ruta: Path, texto: str) -> None:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = ruta.with_name(ruta.name + ".part")
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, ruta)

    def _bajar_seace(datos: dict, destino: Path) -> None:
        docs = datos.get("docs") or {}
        estado_general = datos.get("estado")
        for clave_doc, nombre, _etiqueta in DOCUMENTOS_SEACE:
            doc = docs.get(clave_doc) or {}
            from scraping.seace_abierto import extension_documento
            archivo = destino / f"{nombre}{extension_documento(doc)}"
            nota_no = destino / f"{nombre}_NO_DISPONIBLE.txt"
            nota_err = destino / f"{nombre}_ERROR.txt"
            if estado_general != "seleccionado" or not doc.get("url"):
                # Al cambiar de estado se borra la nota CONTRARIA: si quedaran
                # las dos, el índice avisaría a la vez "no publicado" y "error".
                ruta, contraria = ((nota_err, nota_no)
                                   if estado_general == "fuente_no_disponible"
                                   else (nota_no, nota_err))
                contraria.unlink(missing_ok=True)
                _nota_atomica(ruta, nota_seace_ausencia(estado_general) + "\n")
                continue
            nota_no.unlink(missing_ok=True)
            nota_err.unlink(missing_ok=True)
            if descargar_seace is None:
                from scraping.seace_abierto import descargar_archivo
                descargador = descargar_archivo
            else:
                descargador = descargar_seace
            ok_archivo = cache_seace.materializar(
                doc["url"], archivo, descargar=descargador
            ).ok
            if not ok_archivo:
                _nota_atomica(nota_err, NOTA_SEACE_DESCARGA_FALLIDA + "\n")

    def _descargar_corpus_obra(obra_id, destino_cache: Path,
                               pendientes: frozenset[str] | None = None) -> dict:
        """Baja el corpus de una obra a la caché. `pendientes` = reintento
        selectivo (issue #81): se rehacen SOLO esas secciones y el estado
        devuelto habla solo de ellas; la caché lo fusiona con lo sano."""
        def _toca(seccion: str) -> bool:
            return pendientes is None or seccion in pendientes

        if descargar is not None:
            descargar(obra_id, destino_cache)
            archivos, _ = _inventario_real_descarga(destino_cache)
            return {
                "secciones": {"InfoObras": {
                    "esperados": archivos, "descargados": archivos,
                }},
                "informes_anios": [],
            }

        estado: dict = {"secciones": {}, "avisos": [], "informes_anios": []}
        if _toca("InfoObras"):
            # Que la sección principal reviente ya no tira TODO el corpus: se
            # publica lo demás y esta sección queda marcada para reintento.
            try:
                principal = descargar_documentos_obra_por_hito(obra_id, destino_cache)
                inventario = principal.get("inventario") or {}
                esperados = sum(
                    len(avance.get("documentos") or [])
                    for avance in inventario.get("avances", [])
                ) + len((inventario.get("obra") or {}).get("documentos") or [])
                estado["secciones"]["InfoObras"] = {
                    "esperados": esperados,
                    "descargados": principal.get("descargados") or 0,
                }
            except Exception as ex:  # noqa: BLE001
                logger.warning("documentos de la obra %s: %s", obra_id, corto(ex))
                estado["secciones"]["InfoObras"] = {"error": True}
                estado["avisos"].append(
                    "InfoObras: la consulta de documentos de la obra no pudo "
                    "completarse.")
        if _toca("Informes de control"):
            try:
                control = descargar_informes_control(obra_id, destino_cache)
                estado["informes_anios"] = control.get("anios") or []
                estado["secciones"]["Informes de control"] = {
                    "esperados": control.get("encontrados") or 0,
                    "descargados": control.get("descargados") or 0,
                }
            except Exception as ex:  # noqa: BLE001
                logger.debug("informes control obra %s: %s", obra_id, corto(ex))
                estado["secciones"]["Informes de control"] = {"error": True}
                estado["avisos"].append(
                    "Informes de control: la consulta no pudo completarse.")
        if _toca("Datos de cierre"):
            try:
                cierre = descargar_datos_cierre(obra_id, destino_cache)
                estado["secciones"]["Datos de cierre"] = {
                    "esperados": cierre.get("encontrados") or 0,
                    "descargados": cierre.get("descargados") or 0,
                }
            except Exception as ex:  # noqa: BLE001
                logger.debug("datos de cierre obra %s: %s", obra_id, corto(ex))
                estado["secciones"]["Datos de cierre"] = {"error": True}
                estado["avisos"].append(
                    "Datos de cierre: la consulta no pudo completarse.")

        requisito = requisitos_obra.get(str(obra_id), {})
        aprobacion = requisito.get("aprobacion")
        if aprobacion and _toca("Aprobación del expediente"):
            try:
                aprob_ok = descargar_aprobacion_expediente(aprobacion, destino_cache)
                estado["secciones"]["Aprobación del expediente"] = {
                    "esperados": 1, "descargados": int(bool(aprob_ok)),
                }
            except Exception as ex:  # noqa: BLE001
                logger.debug("aprobación expediente obra %s: %s", obra_id, corto(ex))
                estado["secciones"]["Aprobación del expediente"] = {"error": True}
                estado["avisos"].append(
                    "Aprobación del expediente: la descarga falló.")
        verificacion = requisito.get("verificacion")
        if verificacion and _toca("Verificación MEF"):
            try:
                from scraping.mef import descargar_documentos_expediente
                mef = descargar_documentos_expediente(
                    verificacion["cui_confirmado"],
                    destino_cache / "Verificación MEF",
                    codsnip=verificacion.get("cod_snip") or "",
                )
                descargados_mef = sum(int(valor or 0) for valor in mef.values())
                contrato_mef = verificacion.get("contrato") or {}
                resolucion_mef = verificacion.get("resolucion") or {}
                esperados_mef = (
                    int(bool(contrato_mef.get("numero")))
                    + int(bool(resolucion_mef.get("numero")
                               or resolucion_mef.get("documento")))
                )
                estado["secciones"]["Verificación MEF"] = {
                    "esperados": max(1, esperados_mef),
                    "descargados": descargados_mef,
                }
            except Exception as ex:  # noqa: BLE001
                logger.debug("verificación MEF obra %s: %s", obra_id, corto(ex))
                estado["secciones"]["Verificación MEF"] = {"error": True}
                estado["avisos"].append(
                    "Verificación MEF: la consulta de documentos falló.")
        return estado

    # total descargable = unión de InfoObras y SEACE (una cuenta por experiencia)
    total_desc = sum(1 for prof in espejo.get("profesionales", [])
                     for e in (prof.get("experiencias", []) or [])
                     if (_obra_id(prof.get("n_prof"), e.get("n"))
                         or _seace(prof.get("n_prof"), e.get("n"))))
    procesadas = 0
    for prof in espejo.get("profesionales", []):
        np_ = prof.get("n_prof")
        for e in prof.get("experiencias", []) or []:
            ne = e.get("n")
            enr = enriquecimiento.get(_clave(np_, ne)) or {}
            obra = enr.get("obra") if isinstance(enr.get("obra"), dict) else None
            obra_id = (obra or {}).get("obra_id")
            seace = _seace(np_, ne)
            if not obra_id and not seace:
                saltados += 1
                continue
            if max_descargas is not None and bajadas >= max_descargas:
                break
            procesadas += 1
            if reportar is not None:
                nombre_obra = (enr.get("obra_nombre") or (obra or {}).get("nombre")
                               or e.get("proyecto") or f"obra {obra_id}")
                reportar(procesadas, total_desc, _recorte(nombre_obra))
            destino = base / f"P{np_}_E{ne}"
            ok = base / f"P{np_}_E{ne}.ok"
            ok_seace = base / f"P{np_}_E{ne}.seace.ok"
            hizo_trabajo = False
            previo = (enr.get("descargas_reales")
                      if isinstance(enr.get("descargas_reales"), dict) else {})
            avisos = list(previo.get("avisos") or [])
            secciones = dict(previo.get("secciones") or {})
            fallos_antes = len(descargas_stats().get("fallidos") or [])
            try:
                if obra_id and not ok.exists():
                    hizo_trabajo = True
                    avisos, secciones = [], {}
                    resultado_cache = cache_infoobras.obtener(
                        obra_id,
                        descargar=lambda ruta, pend, oid=obra_id: (
                            _descargar_corpus_obra(oid, ruta, pend)),
                    )
                    cert_ini = _fecha_iso(e.get("fecha_inicial"))
                    cert_fin = _fecha_iso(e.get("fecha_final"))
                    materializados = cache_infoobras.materializar(
                        resultado_cache, destino,
                        fecha_ini=cert_ini, fecha_fin=cert_fin,
                    )
                    estado_cache = resultado_cache.estado
                    avisos.extend(estado_cache.get("avisos") or [])
                    for nombre, datos_seccion in (
                            estado_cache.get("secciones") or {}).items():
                        if datos_seccion.get("error"):
                            secciones[nombre] = {"estado": "error"}
                            continue
                        esperados = datos_seccion.get("esperados") or 0
                        descargados = datos_seccion.get("descargados") or 0
                        publicados = None
                        if nombre == "Informes de control":
                            anios = estado_cache.get("informes_anios") or []
                            publicados = len(anios)
                            if cert_ini is not None and cert_fin is not None:
                                inferior, superior = sorted((cert_ini.year, cert_fin.year))
                                esperados = sum(
                                    1 for anio in anios
                                    if anio is None or inferior <= anio <= superior
                                )
                            else:
                                esperados = len(anios)
                            descargados = materializados.informes
                        _estado_seccion(
                            secciones, avisos, nombre, esperados, descargados)
                        if publicados:
                            # El inventario COMPLETO de la obra distingue «no hay
                            # informes» de «los hay, pero de otros años» (issue #81).
                            secciones[nombre]["publicados"] = publicados
                    base.mkdir(parents=True, exist_ok=True)
                    if resultado_cache.completa:
                        ok.write_text("ok", encoding="utf-8")
                    else:
                        # Corpus con secciones caídas: NO se marca la experiencia
                        # como terminada, para que la siguiente pasada reintente
                        # (la caché solo re-descarga lo fallido).
                        logger.info(
                            "descargas job %s P%sE%s: obra %s con secciones "
                            "pendientes de reintento (%s)", job_id, np_, ne, obra_id,
                            ", ".join(secciones_en_error(estado_cache)))
                if seace and not ok_seace.exists():
                    hizo_trabajo = True
                    _bajar_seace(seace, destino)
                    base.mkdir(parents=True, exist_ok=True)
                    ok_seace.write_text("ok", encoding="utf-8")
                if hizo_trabajo:
                    bajadas += 1
            except Exception as ex:  # noqa: BLE001
                logger.warning("Descargas ✗ P%sE%s: %s", np_, ne, corto(ex))
                avisos.append("Descarga general: no se pudo completar esta experiencia.")

            # El manifiesto se reconstruye incluso al reanudar: no confía en el
            # inventario del portal ni en la mera existencia de una carpeta.
            archivos_reales, por_hito = _inventario_real_descarga(destino)
            fallos = (descargas_stats().get("fallidos") or [])[fallos_antes:]
            for etiqueta, categoria, _mensaje in fallos:
                aviso = f"Archivo «{etiqueta}»: no descargado ({categoria})."
                if aviso not in avisos:
                    avisos.append(aviso)
            if destino.is_dir():
                # El rótulo del aviso es legible ("Bases Integradas (SEACE)"), no
                # el nombre del archivo: el índice lo lee un evaluador.
                for nota in destino.rglob("*_ERROR.txt"):
                    etiqueta = etiqueta_documento_seace(
                        nota.stem.removesuffix("_ERROR"))
                    aviso = f"{etiqueta}: la fuente devolvió un error."
                    if aviso not in avisos:
                        avisos.append(aviso)
                for nota in destino.rglob("*_NO_DISPONIBLE.txt"):
                    etiqueta = etiqueta_documento_seace(
                        nota.stem.removesuffix("_NO_DISPONIBLE"))
                    aviso = f"{etiqueta}: no publicado por la fuente."
                    if aviso not in avisos:
                        avisos.append(aviso)
            enr["descargas_reales"] = {
                "completada": bool((not obra_id or ok.exists())
                                    and (not seace or ok_seace.exists())),
                "archivos": archivos_reales,
                "por_hito": por_hito,
                "secciones": secciones,
                "avisos": avisos,
            }
            enriquecimiento[_clave(np_, ne)] = enr
    if saltados:
        logger.info("descargas job %s: %d experiencia(s) sin fuentes descargables",
                    job_id, saltados)
    logger.info("Documentos del job %s — %s", job_id, resumen_descargas())
    n_files = n_bytes = 0
    if base.is_dir():
        for p in base.rglob("*"):
            if _es_documento_descargado(p):
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
    consorcio) ni la cola 'RUC …'.

    El prelimpiado vive en `scraping/nombres_empresa.py` desde T-REFACTOR-002:
    el candado SEACE y la verificación de expedientes del MEF necesitaban
    exactamente esta limpieza y la tenían escondida acá."""
    from scraping.nombres_empresa import limpiar_nombre_entidad
    return limpiar_nombre_entidad(entidad)


def _elegir_match_exacto(nombre: str, matches: list) -> Optional[dict]:
    """De varias coincidencias SUNAT para un nombre, elige la que tiene la MISMA
    razón social que la buscada.

    La búsqueda de SUNAT es por prefijo, así que un nombre como "ACRUTA & TAPIA
    INGENIEROS S.A.C." trae también empresas parecidas pero distintas (la del
    consorcio, una homónima dada de baja, etc.). Comparando con el nombre
    normalizado (sin sufijos legales/puntuación/acentos) se puede desempatar
    cuando solo UNA fila es idéntica. Si hay varias idénticas, prefiere la
    ACTIVA; si sigue habiendo ambigüedad, devuelve None (revisión humana).

    `nombre` llega ya prelimpiado por `_nombre_emisor_limpio` (el compartido de
    `scraping/nombres_empresa.py`). Aquí NO se limpia la razón social que
    devuelve SUNAT: son denominaciones registrales, no membretes, y limpiarlas
    solo podría crear empates nuevos — o sea convertir un desempate exitoso en
    una revisión humana. La monotonía manda (T-REFACTOR-002)."""
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


def _evaluar_habido_emisor(hist, emp, e: dict, ini) -> Optional[dict]:
    """¿El emisor estaba HABIDO el día que emitió el certificado y durante la
    obra que certifica? (issue #30, punto 4).

    Cruza el histórico de condición con la fecha de emisión y con el periodo de
    la experiencia. Devuelve None si no hay histórico que cruzar; dentro, cada
    respuesta puede quedar en `ok=None` cuando el dato no alcanza.
    """
    if hist is None:
        return None
    from scraping.sunat import evaluar_habido
    return evaluar_habido(
        hist.condiciones,
        fecha_emision=_fecha_iso(e.get("fecha_emision")),
        ini=ini, fin=_fecha_iso(e.get("fecha_final")),
        condicion_actual=getattr(emp, "condicion", None),
    )


class EtapaSunatReal:
    nombre = E.SUNAT

    def __init__(self, consultor: Optional[Callable] = None,
                 buscador: Optional[Callable] = None,
                 extras: Optional[Callable] = None):
        self._consultor = consultor
        self._buscador = buscador
        self._extras = extras

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

    def _consultar_extras(self, ruc: str) -> tuple[list, object]:
        """Las dos consultas informativas del emisor (issue #30): representantes
        legales e información histórica. Devuelve (representantes, historico)."""
        if self._extras:
            return self._extras(ruc)
        from scraping.sunat import consultar_historico, consultar_representantes
        return consultar_representantes(ruc), consultar_historico(ruc)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ok = err = rev = 0
        obs: list[pipeline.Observacion] = []
        cache: dict[str, object] = {}
        cache_extra: dict[str, tuple] = {}   # ruc → (representantes, historico)
        total = 0
        postor_rucs = _rucs_postor(ctx.espejo)

        n_tot = sum(1 for _ in ctx.items_experiencia())
        for idx, (e, (np_, ne)) in enumerate(ctx.items_experiencia(), 1):
            entidad = str(e.get("entidad_emisora") or "")
            ctx.reportar(self.nombre, idx, n_tot,
                         f"Consultando el emisor {idx} de {n_tot}"
                         + (f" — {_recorte(entidad)}" if entidad.strip() else ""))
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
            # Consultas informativas del emisor (una vez por RUC, no por
            # experiencia): representantes legales + información histórica.
            try:
                reps, hist = (cache_extra[ruc] if ruc in cache_extra
                              else cache_extra.setdefault(ruc, self._consultar_extras(ruc)))
            except Exception as ex:  # noqa: BLE001 — informativo, no debe tumbar la etapa
                logger.warning("SUNAT extras %s: %r", ruc, ex)
                reps, hist = [], None

            enr = ctx.enriquecimiento.get(k) or {}
            fins = getattr(emp, "fecha_inscripcion", None)
            ini_act = getattr(emp, "fecha_inicio_actividades", None)
            habido = _evaluar_habido_emisor(hist, emp, e, ini)
            # Una inscripción actual posterior no demuestra que la empresa no
            # existiera antes: SUNAT la reemplaza tras ciertas bajas de oficio y
            # reinscripciones. Si el propio histórico acredita actividad en el
            # periodo certificado, ALT04 queda reconciliada como reinscripción,
            # nunca como una imposibilidad roja.
            evidencia_previa = bool(
                habido and any(
                    (habido.get(k) or {}).get("ok") is True
                    for k in ("emision", "periodo")
                )
            )
            alt04 = None
            if fins and ini and fins > ini:
                alt04 = {
                    "estado": "REINSCRIPCION" if evidencia_previa else "ALERTA",
                    "fecha_referencia": fins.isoformat(),
                    "mensaje": (
                        "La fecha vigente de inscripción es posterior, pero el histórico "
                        "SUNAT acredita actividad en el periodo: probable reinscripción "
                        "tras una baja; no se trata como creación de la empresa."
                        if evidencia_previa else
                        "La inscripción SUNAT vigente es posterior al inicio de la "
                        "experiencia; confirmar la inscripción original en el histórico."
                    ),
                }
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
                # informativo (issue #30): representantes legales del emisor.
                # SIN veredicto de firmante — ADR-008 descartó ALT-12.
                "representantes": [r.to_dict() for r in (reps or [])],
                # información histórica + la pregunta que le importa al evaluador:
                # ¿estaba HABIDO al emitir el certificado y durante la obra?
                "historico": hist.to_dict() if hist else None,
                "habido": habido,
                "alt04": alt04,
            }
            ctx.enriquecimiento[k] = enr
            if fins and ini and fins > ini and not evidencia_previa:
                obs.append(pipeline.Observacion(
                    codigo="ALT04", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"la inscripción SUNAT vigente del emisor (RUC {ruc}) figura el "
                            f"{fins.strftime('%d/%m/%y')}, después del inicio de la experiencia; "
                            "confirmar la inscripción original en el histórico antes de concluir",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

        return _res(self.nombre, EE.OK if err == 0 else EE.ERROR_PARCIAL,
                    _met(total, ok, rev, err), obs)


# ── 3c · RENIPRESS (existencia auxiliar de establecimientos de salud) ───────

class EtapaRenipressReal:
    """Consulta RENIPRESS sin convertir el resultado en un veredicto.

    Solo procesa experiencias cuyo proyecto declara rubro salud. Tanto una
    respuesta vacía como una coincidencia ambigua se conservan para el
    evaluador; una caída del portal jamás se interpreta como inexistencia.
    """

    nombre = E.RENIPRESS

    def __init__(self, consultor: Optional[Callable] = None):
        self._consultor = consultor

    def _consultar(self, termino: str):
        if self._consultor:
            return self._consultor(termino)
        from scraping.renipress import buscar_renipress
        return buscar_renipress(termino)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        experiencias = [
            (e, clave)
            for e, clave in ctx.items_experiencia()
            if "salud" in rubros_de(str(e.get("proyecto") or ""))
        ]
        cache: dict[str, dict] = {}
        ok = err = 0
        obs: list[pipeline.Observacion] = []

        for idx, (e, (np_, ne)) in enumerate(experiencias, 1):
            proyecto = str(e.get("proyecto") or "").strip()
            termino = establecimiento(proyecto).strip() or proyecto
            ctx.reportar(
                self.nombre,
                idx,
                len(experiencias),
                f"Consultando el establecimiento {idx} de {len(experiencias)}"
                + (f" — {_recorte(termino)}" if termino else ""),
            )
            if len(termino) < 2:
                continue

            clave_cache = termino.casefold()
            if clave_cache not in cache:
                try:
                    resultado = self._consultar(termino)
                    cache[clave_cache] = resultado.to_dict()
                except Exception as ex:  # noqa: BLE001 — fuente auxiliar best-effort
                    logger.warning("RENIPRESS %r: %r", termino, ex)
                    cache[clave_cache] = {
                        "estado": "portal_no_disponible",
                        "termino": termino,
                        "tipo_consulta": "texto",
                        "solo_activos": True,
                        "establecimientos": [],
                        "total": 0,
                        "intentos": 1,
                        "detalle_error": "la consulta RENIPRESS falló",
                        "ambiguo": False,
                    }

            datos = cache[clave_cache]
            enr = ctx.enriquecimiento.setdefault(_clave(np_, ne), {})
            enr["renipress"] = datos
            if datos.get("estado") == "portal_no_disponible":
                err += 1
                obs.append(pipeline.Observacion(
                    codigo="RENIPRESS",
                    severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=(
                        f"RENIPRESS no respondió al consultar «{termino}»; "
                        "la existencia del establecimiento queda sin verificar"
                    ),
                    origen=self.nombre,
                    referencia=f"prof={np_} exp={ne}",
                ))
            else:
                ok += 1

        estado = EE.ERROR_PARCIAL if err else EE.OK
        return _res(
            self.nombre,
            estado,
            _met(len(experiencias), ok, err=err),
            obs,
        )


# ── 4 · Cálculo de días efectivos (Paso 5 + mínimo de las bases) ─────────────

# El mínimo exigido se escribe en AÑOS, MESES o DÍAS según las bases; el regex
# anterior solo entendía "años" y por eso `cumple_backend` casi nunca se calculaba:
# en el concurso de Lircay (CP-02-2025) los 17 cargos dicen "Experiencia mínima:
# 24/36 meses" → 0 de 17 mínimos captados, y los 5 falsos CUMPLE del análisis
# quedaron sin contraveredicto (#51).
#
# `m[ií]nim[ao]` cubre "mínimo de 3 años" y "Experiencia mínima: 24 meses"; el
# hueco intermedio es corto y no-codicioso para no saltar a otra cifra de la frase.
_RE_MINIMO = re.compile(
    r"m[ií]nim[ao][^0-9]{0,20}?(\d+)\s*(a[ñn]os?|meses|mes|d[ií]as?)", re.I)

# Conversión a días: la MISMA convención que `reglas.anios` (365) y `reglas.meses`
# (30). Usar otra haría que el umbral contradiga la cifra que se muestra al lado.
_DIAS_POR_UNIDAD = {"a": 365, "m": 30, "d": 1}


def _minimo_exigido(requisitos) -> Optional[tuple[int, str]]:
    """Mínimo de las bases normalizado a `(días, texto_literal)`.

    Se compara en DÍAS y no en años porque es la unidad que el Paso 5 calcula sin
    pérdida: convertir los efectivos a años y redondear puede volcar un caso de
    borde (2.996 años redondea a 3.0 y un mínimo de "3 años" pasaría a cumplir)."""
    for v in (requisitos or {}).values():
        m = _RE_MINIMO.search(str(v))
        if m:
            n, unidad = int(m.group(1)), m.group(2).lower()[0]
            return n * _DIAS_POR_UNIDAD[unidad], f"{n} {m.group(2)}"
    return None


def _participantes_factor_a(espejo: dict) -> set[int]:
    """Cargos que participan según las bases; legado: recupera la lista que
    quedó escrita en el detalle del factor, sin confiar en sus resultados."""
    estructurados = {
        p.get("n_prof") for p in espejo.get("profesionales", [])
        if (p.get("requisitos") or {}).get("factor_a_aplica") is True
    }
    if estructurados:
        return estructurados
    factor = next((f for f in (espejo.get("resumen_evaluacion") or {}).get("factores", [])
                   if str(f.get("factor") or "").strip().upper() == "A"), None)
    texto = str((factor or {}).get("detalle") or "")
    # Formato histórico real: "Factor A (nº 2 ..., 3 ..., 4 ..., 6 ...)".
    # El paréntesis termina antes de las cifras de años/porcentaje del resultado.
    parentesis = re.search(r"factor\s*a\s*\(([^)]+)\)", texto, flags=re.I)
    if parentesis:
        numeros = {int(x) for x in re.findall(r"\b\d+\b", parentesis.group(1))}
        existentes = {p.get("n_prof") for p in espejo.get("profesionales", [])}
        if numeros & existentes:
            return numeros & existentes
    m = re.search(r"participan[^:]*:\s*([^.;]+)", texto, flags=re.I)
    return {int(x) for x in re.findall(r"\d+", m.group(1))} if m else set()


def _recalcular_factor_a(espejo: dict, enriquecimiento: dict) -> None:
    """El Factor A solo existe sobre tiempo efectivo que excede el mínimo.

    La rúbrica histórica no viaja estructurada, por lo que no se inventa un
    tramo: se retira el puntaje anterior y se deja pendiente. Cuando la skill ya
    traiga ``factor_a_aplica``, el detalle y la elegibilidad sí son plenamente
    determinísticos.
    """
    resumen = espejo.get("resumen_evaluacion") or {}
    factor = next((f for f in resumen.get("factores", [])
                   if str(f.get("factor") or "").strip().upper() == "A"), None)
    if not factor:
        return
    participantes = _participantes_factor_a(espejo)
    if not participantes:
        return
    califican: list[int] = []
    pendientes: list[int] = []
    for p in espejo.get("profesionales", []):
        np_ = p.get("n_prof")
        if np_ not in participantes:
            continue
        d = enriquecimiento.get(f"prof:{np_}") or {}
        minimo, efectivos = d.get("minimo_dias"), d.get("dias_efectivos")
        provisional = bool(d.get("veredicto_provisional"))
        if minimo is None or efectivos is None or provisional:
            pendientes.append(np_)
            p["anios_adicionales"] = "POR VERIFICAR — el tiempo efectivo no es definitivo"
            continue
        exceso = max(0, efectivos - minimo)
        p["anios_adicionales"] = f"{round(exceso / 365, 2)} años efectivos adicionales"
        if exceso >= 365:
            califican.append(np_)
    puntaje_anterior = factor.get("puntaje")
    factor["puntaje"] = None
    factor["detalle"] = (
        f"{len(califican)} de {len(participantes)} cargos acreditan al menos un año "
        f"efectivo adicional (profesionales {', '.join(map(str, califican)) or 'ninguno'}). "
        + (f"Pendientes de verificación: {', '.join(map(str, pendientes))}. " if pendientes else "")
        + "Puntaje por confirmar con el cuadro del Factor A de las bases."
    )
    if isinstance(puntaje_anterior, (int, float)) and isinstance(resumen.get("puntaje_total"), (int, float)):
        resumen["puntaje_total"] = max(0, resumen["puntaje_total"] - puntaje_anterior)
    resumen["nota"] = ((resumen.get("nota") or "") +
                       " · Factor A recalculado con tiempo efectivo; su tramo queda por confirmar.").strip(" ·")


class EtapaReglasReal:
    nombre = E.REGLAS

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ctx.reportar(self.nombre, 0, 0, "Calculando los días efectivos de experiencia")
        obs: list[pipeline.Observacion] = []
        total = ok = 0
        for p in ctx.espejo.get("profesionales", []):
            np_ = p.get("n_prof")
            total += 1
            periodos: list[tuple[date, date]] = []
            paral_por_idx: dict[int, list[tuple[date, date]]] = {}
            sin_verificar: list[int] = []   # experiencias sin ventana conocida
            cobertura_baja: list[int] = []  # obra verificada pero casi sin solape
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
                # Distinta de `sin_verificar`: acá el portal SÍ respondió, pero sus
                # valorizaciones casi no solapan el periodo certificado, así que el
                # clamp del Paso 5 recortó casi todo. La causa más probable es una obra
                # mal emparejada (error nuestro), no una experiencia inexistente → no
                # puede sostener un NO CUMPLE duro. Su ítem de revisión ya lo creó la
                # etapa de InfoObras; acá solo ablanda el veredicto.
                elif enr.get("cobertura_baja") is not None:
                    cobertura_baja.append(e.get("n"))
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
            exigido = _minimo_exigido(p.get("requisitos"))
            if exigido is not None:
                min_dias, min_texto = exigido
                datos["minimo_dias"] = min_dias
                datos["minimo_texto"] = min_texto
                # `minimo_anios` se conserva (lo leen panel y tests); es informativo
                # y queda entero cuando el requisito venía en años.
                datos["minimo_anios"] = (min_dias // 365 if min_dias % 365 == 0
                                         else round(min_dias / 365, 2))
                if res.dias_efectivos < min_dias:
                    datos["cumple_backend"] = (
                        f"NO CUMPLE — {res.dias_efectivos} días efectivos "
                        f"({anios_ef} años) contra un mínimo de {min_texto}")
                    obs.append(pipeline.Observacion(
                        codigo="PASO5", severidad=pipeline.Severidad.ALERTA,
                        mensaje=f"profesional {np_}: {res.dias_efectivos} días efectivos tras "
                                f"descontar paralizaciones y traslapes — por debajo del mínimo "
                                f"de {min_texto}",
                        origen=self.nombre, referencia=f"prof={np_}"))
            # veredicto provisional: alguna experiencia no se pudo verificar en
            # InfoObras (fetch fallido → ventana desconocida, no se clampó, el número
            # puede estar inflado) o la obra emparejada casi no cubre el periodo
            # certificado (clamp casi total → el número puede estar hundido). Las dos
            # son incertidumbre nuestra sobre la obra: van a revisión humana.
            if cobertura_baja:
                datos["cobertura_baja"] = cobertura_baja
                datos["veredicto_provisional"] = (
                    datos.get("veredicto_provisional", []) + cobertura_baja)
            if sin_verificar:
                datos["veredicto_provisional"] = (
                    datos.get("veredicto_provisional", []) + sin_verificar)
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
            if prov:
                exps = ", ".join(map(str, sorted(set(prov))))
                # El motivo se nombra tal cual es: «no respondió» y «casi no cubre el
                # periodo» mandan al evaluador a revisar cosas distintas.
                causas = []
                if sin_verificar:
                    causas.append("no se pudo consultar la obra en InfoObras")
                if cobertura_baja:
                    causas.append("la obra encontrada casi no cubre el periodo del "
                                  "certificado (puede ser la obra equivocada)")
                if fechas_invalidas:
                    causas.append("hay una fecha del certificado sin leer")
                datos["cumple_backend"] = (
                    f"POR VERIFICAR — {res.dias_efectivos} días efectivos PROVISIONALES "
                    f"({datos['anios_efectivos']} años) contra un mínimo de "
                    f"{datos.get('minimo_texto', datos.get('minimo_anios'))}: en la(s) "
                    f"experiencia(s) {exps}, {'; '.join(causas)}. La ausencia de datos NO "
                    f"invalida la experiencia — confirmar a mano antes de concluir; el "
                    f"cómputo puede estar incompleto.")
            ctx.enriquecimiento[f"prof:{np_}"] = datos
            # #57 · las dos cifras viajan juntas y estructuradas. `total` en el
            # espejo es la suma declarada de filas; este bloque explica exactamente
            # cómo se llega desde ella al efectivo que sostiene el veredicto.
            p["total_backend"] = {
                "dias_declarados": res.dias_brutos,
                "dias_paralizados": res.dias_paralizados,
                "dias_traslape": res.dias_traslape,
                "dias_efectivos": res.dias_efectivos,
                "anios_efectivos": anios_ef,
                "incompleto": bool(fechas_invalidas),
            }
            p["dias_efectivos_backend"] = res.dias_efectivos
            # El veredicto del backend viaja TAMBIÉN en el espejo: la hoja resumen del
            # Excel (`construir_hoja_evaluacion`) solo recibe el espejo, y hasta ahora
            # `cumple_backend` moría en el enriquecimiento — se calculaba, se guardaba
            # y el evaluador nunca lo veía (#51). El campo es aditivo: `Profesional`
            # es passthrough/lax en las dos copias del contrato.
            if datos.get("cumple_backend"):
                p["cumple_backend"] = datos["cumple_backend"]
                p["minimo_exigido_backend"] = datos.get("minimo_texto")
            ok += 1

        # T-011 · cruces de fechas contrato/expediente ↔ certificado. Van aquí y
        # no en la etapa SEACE porque necesitan que TODAS las fuentes hayan
        # corrido (proceso + candado de identidad de F5, verificación MEF del
        # expediente y su documento de aprobación). Nunca convierten una ausencia
        # de datos en incumplimiento: sin fuente confirmada el cruce se abstiene
        # con su razón escrita, y solo el resultado `dispara` levanta alerta.
        from reglas.cruces_fechas import DISPARA, TITULO_REGLA, cruces_de_experiencia
        for _e, (np_, ne) in ctx.items_experiencia():
            k = _clave(np_, ne)
            enr = ctx.enriquecimiento.get(k) or {}
            cruces = cruces_de_experiencia(enr, _e)
            enr["cruces_fechas"] = [c.como_dict() for c in cruces]
            ctx.enriquecimiento[k] = enr
            for c in cruces:
                if c.resultado != DISPARA:
                    continue
                obs.append(pipeline.Observacion(
                    codigo=c.regla, severidad=pipeline.Severidad.ALERTA,
                    mensaje=f"{TITULO_REGLA.get(c.regla, c.regla)}: {c.motivo}",
                    origen=self.nombre, referencia=f"prof={np_} exp={ne}"))

        _recalcular_factor_a(ctx.espejo, ctx.enriquecimiento)
        # B2 — resumen de incertidumbre InfoObras: "X de Y no encontrados". Solo en
        # corrida COMPLETA (en re-disparo de un item no se recalcula → evita duplicar,
        # porque el re-disparo EXTIENDE las observaciones en vez de reemplazarlas).
        if not ctx.solo_items:
            tot_exp = no_verif = na = 0
            for p in ctx.espejo.get("profesionales", []):
                for e in p.get("experiencias", []):
                    tot_exp += 1
                    enr = ctx.enriquecimiento.get(_clave(p.get("n_prof"), e.get("n"))) or {}
                    if str(enr.get("via") or "").upper() in ("NA", "PRIVADA"):
                        na += 1                     # no aplica (privada / sin cruce)
                        continue
                    obra = enr.get("obra") if isinstance(enr.get("obra"), dict) else None
                    if not (obra or {}).get("obra_id") or enr.get("sin_verificar"):
                        no_verif += 1
            if no_verif:
                extra = f" ({na} no aplican)" if na else ""
                obs.append(pipeline.Observacion(
                    codigo="RESUMEN_INFOOBRAS", severidad=pipeline.Severidad.ADVERTENCIA,
                    mensaje=f"{no_verif} de {tot_exp} experiencias no se ubicaron/verificaron "
                            f"en InfoObras{extra} → revisión manual. La ausencia de datos NO "
                            f"invalida la experiencia.",
                    origen=self.nombre))
        return _res(self.nombre, EE.OK, _met(total, ok), obs)


# ── 5 · Excel final ──────────────────────────────────────────────────────────

class EtapaExcelReal:
    nombre = E.EXCEL

    def __init__(self, dir_salida: Path):
        self.dir_salida = Path(dir_salida)

    def correr(self, ctx: Contexto) -> pipeline.ResultadoEtapa:
        ctx.reportar(self.nombre, 0, 0, "Armando el Excel de evaluación")
        # pasa los periodos CON su tipo (paralizado / sin valorización) para que
        # el Excel los muestre diferenciados; el generador normaliza las fechas.
        paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(ctx.enriquecimiento)
        # experiencias en revisión → su motivo Y su acción sugerida, para que la hoja
        # del profesional muestre "EN REVISIÓN" + la razón en vez de una columna
        # vacía. La acción viaja junto al motivo porque los ItemRevision los crean 4
        # etapas distintas y cada una pide algo diferente (pegar un CUI, verificar
        # una fecha, reintentar el portal): si el Excel inventa una acción fija de
        # "pegar el CUI", la pide también sobre obras bien identificadas.
        revisiones: dict[tuple[int, int], tuple[str, Optional[str]]] = {}
        for it in ctx.job.items_revision:
            if not it.resuelto and it.n_exp is not None:
                revisiones.setdefault((it.n_prof, it.n_exp),
                                      (it.motivo, it.accion_sugerida))
        # experiencias PRIVADAS → bloque propio en el Excel (no es "revisión": el
        # respaldo es el certificado; InfoObras no registra obra privada).
        for k, e in ctx.enriquecimiento.items():
            if isinstance(e, dict) and str(e.get("via") or "").upper() == "PRIVADA" \
                    and ":" in k and not k.startswith("prof:"):
                np_, ne = (int(x) for x in k.split(":"))
                revisiones.setdefault((np_, ne), "[PRIVADA]")
        ruta = carpeta_job(self.dir_salida, ctx.job.job_id) / "final.xlsx"
        if ruta.exists():
            ruta.unlink()  # regenerar (re-disparo tras revisión humana)
        # certificados de las experiencias (imágenes) que subió la skill, si los hay
        certs = mapear_certificados(self.dir_salida, ctx.job.job_id)
        generar_excel_final(
            ctx.espejo, ruta, paral, cuis, fichas, revisiones, sunat, certs,
            confiabilidad={
                "veredicto": ctx.job.confiabilidad,
                "hallazgos_criticos": [
                    o.model_dump(mode="json") for o in ctx.job.hallazgos_criticos
                ],
            },
        )
        ctx.job.excel_final = f"/api/pivote/jobs/{ctx.job.job_id}/excel"
        ctx.job.zip_infoobras = f"/api/pivote/jobs/{ctx.job.job_id}/zip"
        zip_previo = carpeta_job(self.dir_salida, ctx.job.job_id) / "infoobras.zip"
        if zip_previo.exists():
            zip_previo.unlink()  # que el endpoint lo reconstruya con lo nuevo
        n_exp = sum(len(p.get("experiencias", [])) for p in ctx.espejo.get("profesionales", []))
        return _res(self.nombre, EE.OK, _met(n_exp, n_exp))


# ── juego completo ───────────────────────────────────────────────────────────

def etapas_reales(dir_datos: Path, *, consulta_cui=None, fetcher_infoobras=None,
                  consultor_sunat=None, buscador_sunat=None, extras_sunat=None,
                  consultor_renipress=None, descargar=None, verificador_mef=None,
                  consulta_ocds=None):
    """Las 9 etapas de la demo. Los parámetros inyectables son para tests;
    en producción quedan los clientes en vivo."""
    return [
        EtapaIngesta(),
        EtapaValidacionReal(Path(dir_datos)),
        EtapaResolucionCuiReal(consulta=consulta_cui),
        EtapaInfoObrasReal(fetcher=fetcher_infoobras, dir_descargas=Path(dir_datos),
                           descargar=descargar, verificador_mef=verificador_mef,
                           consulta_ocds=consulta_ocds),
        EtapaSunatReal(consultor=consultor_sunat, buscador=buscador_sunat,
                       extras=extras_sunat),
        EtapaRenipressReal(consultor=consultor_renipress),
        EtapaReglasReal(),
        EtapaExcelReal(Path(dir_datos)),
        EtapaStub(E.PERSISTENCIA),
    ]
