"""Resultados profesionales sin dependencias del generador ni de la orquestación."""
from __future__ import annotations

from datetime import date
from typing import Optional

from reglas import anios, dias_efectivos_profesional, periodo_fechas
from reglas.requisitos import minimo_exigido


def reconciliar_resultados_profesionales(espejo: dict,
                                         enriquecimiento: Optional[dict]) -> dict[int, dict]:
    """Reconstruye el resultado efectivo que comparten API y Excel.

    Los jobs anteriores a la separación de rutas pueden conservar en
    ``prof:N`` paralizaciones o avisos de InfoObras que ya no aplican a una
    experiencia de expediente o privada. El entregable nuevo ya presentaba
    esas rutas correctamente por experiencia, pero el resumen seguía leyendo
    el agregado histórico. Se recalcula solo con datos persistidos, sin red y
    sin modificar el resolver.
    """
    from resolucion.cui import (TIPO_EXPEDIENTES, es_expediente_exp,
                                tipo_evaluacion_del_espejo)
    from validacion.recalculo import fechas_calculo, regla_periodos_de

    enriquecimiento = enriquecimiento or {}
    tipo_evaluacion = tipo_evaluacion_del_espejo(espejo)   # ADR-010
    # La correccion historica se activa solo cuando la convocatoria declaro su
    # tipo. Un espejo antiguo sin tipo no se reclasifica por texto ni por CUI.
    if tipo_evaluacion == TIPO_EXPEDIENTES:
        from reglas.expedientes import reconciliar_expedientes
        return reconciliar_expedientes(espejo, enriquecimiento)
    regla_periodos = regla_periodos_de(espejo)             # #93 · mes completo si lo dicen las bases
    salida: dict[int, dict] = {}
    for prof in (espejo or {}).get("profesionales", []):
        np_ = prof.get("n_prof")
        periodos: list[tuple[date, date]] = []
        paral_por_idx: dict[int, list[tuple[date, date]]] = {}
        sin_verificar: list[int] = []
        cobertura_baja: list[int] = []
        privadas_pendientes: list[int] = []
        fechas_invalidas: list[int] = []

        for exp in prof.get("experiencias", []):
            ne = exp.get("n")
            # Mismas fechas que usa el pipeline: cierta, o borde mensual si las
            # bases lo autorizan. Leer solo el ISO completo descartaba en silencio
            # los certificados con mes y año (dos profesionales bajo el mínimo).
            ini, fin, _deducida = fechas_calculo(exp, regla_periodos)
            if not (ini and fin) or fin < ini:
                if exp.get("fecha_inicial") or exp.get("fecha_final"):
                    fechas_invalidas.append(ne)
                continue

            idx = len(periodos)
            periodos.append((ini, fin))
            datos_exp = enriquecimiento.get(f"{np_}:{ne}") or {}
            privada = str(datos_exp.get("via") or "").upper() == "PRIVADA"
            expediente = es_expediente_exp(exp, tipo_evaluacion)

            # La ejecución física no descuenta tiempo de un expediente y las
            # fuentes públicas no aplican a una obra privada.
            if not (privada or expediente):
                paral_crudo = [periodo_fechas(x)
                               for x in datos_exp.get("paralizaciones", [])]
                paral = [(a, b) for a, b in paral_crudo if b >= a]
                if paral:
                    paral_por_idx[idx] = paral

            if privada:
                if not (datos_exp.get("sunat") or {}).get("ruc"):
                    privadas_pendientes.append(ne)
                continue
            if datos_exp.get("sin_verificar"):
                sin_verificar.append(ne)
            if not expediente and datos_exp.get("cobertura_baja") is not None:
                cobertura_baja.append(ne)

        anterior = dict(enriquecimiento.get(f"prof:{np_}") or {})
        for campo in ("cumple_backend", "veredicto_provisional", "cobertura_baja"):
            anterior.pop(campo, None)
        if not periodos:
            salida[np_] = anterior
            continue

        res = dias_efectivos_profesional(periodos, paral_por_idx)
        anios_ef = round(anios(res.dias_efectivos), 2)
        datos = {
            **anterior,
            "dias_brutos": res.dias_brutos,
            "dias_paralizados": res.dias_paralizados,
            "dias_traslape": res.dias_traslape,
            "dias_efectivos": res.dias_efectivos,
            "anios_efectivos": anios_ef,
        }
        exigido = minimo_exigido(prof.get("requisitos"))
        if exigido:
            minimo_dias, minimo_texto = exigido
            datos.update(
                minimo_dias=minimo_dias,
                minimo_texto=minimo_texto,
                minimo_anios=(minimo_dias // 365 if minimo_dias % 365 == 0
                               else round(minimo_dias / 365, 2)),
            )
            if res.dias_efectivos < minimo_dias:
                datos["cumple_backend"] = (
                    f"NO CUMPLE — {res.dias_efectivos} días efectivos "
                    f"({anios_ef} años) contra un mínimo de {minimo_texto}")

        provisionales = sorted(set(sin_verificar + cobertura_baja
                                   + privadas_pendientes + fechas_invalidas))
        if provisionales:
            datos["veredicto_provisional"] = provisionales
            if cobertura_baja:
                datos["cobertura_baja"] = cobertura_baja
            causas = []
            if sin_verificar:
                causas.append("no se pudo consultar la obra en InfoObras")
            if cobertura_baja:
                causas.append("la obra encontrada casi no cubre el periodo del certificado "
                              "(puede ser la obra equivocada)")
            if privadas_pendientes:
                causas.append("SUNAT no identificó inequívocamente al emisor privado")
            if fechas_invalidas:
                causas.append("hay una fecha del certificado sin leer")
            exps = ", ".join(map(str, provisionales))
            minimo = datos.get("minimo_texto", datos.get("minimo_anios", "sin dato"))
            datos["cumple_backend"] = (
                f"POR VERIFICAR — {res.dias_efectivos} días efectivos PROVISIONALES "
                f"({anios_ef} años) contra un mínimo de {minimo}: en la(s) "
                f"experiencia(s) {exps}, {'; '.join(causas)}. La ausencia de datos NO "
                "invalida la experiencia; confirmar la evidencia antes de concluir.")
        salida[np_] = datos
    return salida


def inyectar_veredicto_backend(espejo: dict, enriquecimiento: Optional[dict]) -> None:
    """Copia veredicto y desglose de totales del enriquecimiento al espejo.

    El espejo se persiste UNA vez (al crear el job) y no se vuelve a guardar; el
    enriquecimiento sí se persiste tras cada etapa. En la corrida en vivo la etapa
    REGLAS ya deja el veredicto en el espejo en memoria, pero al REGENERAR el Excel
    desde disco ese espejo viene sin él — y la hoja resumen volvería a mostrar solo
    el veredicto del LLM, que es justo el defecto de #51. Modifica `espejo` in situ.
    """
    resultados = reconciliar_resultados_profesionales(espejo, enriquecimiento)
    for p in (espejo or {}).get("profesionales", []):
        np_ = p.get("n_prof")
        d = resultados.get(np_) or {}
        if isinstance(enriquecimiento, dict) and d:
            # La copia cargada para el Excel queda alineada con lo que se
            # presenta. El repositorio no se escribe desde este helper.
            enriquecimiento[f"prof:{np_}"] = d
        if d:
            p["total_backend"] = {
                "dias_declarados": d.get("dias_brutos"),
                "dias_paralizados": d.get("dias_paralizados"),
                "dias_traslape": d.get("dias_traslape"),
                "dias_efectivos": d.get("dias_efectivos"),
                "anios_efectivos": d.get("anios_efectivos"),
                "incompleto": bool(d.get("veredicto_provisional")),
            }
            p["dias_efectivos_backend"] = d.get("dias_efectivos")
        p.pop("cumple_backend", None)
        p.pop("minimo_exigido_backend", None)
        if d.get("cumple_backend"):
            p["cumple_backend"] = d["cumple_backend"]
            p["minimo_exigido_backend"] = d.get("minimo_texto")
    # También al regenerar desde disco: el puntaje heredado de Factor A no puede
    # sobrevivir si los efectivos actuales no sostienen sus excedentes.
    from reglas.factor_a import recalcular_factor_a
    recalcular_factor_a(espejo, enriquecimiento or {})
