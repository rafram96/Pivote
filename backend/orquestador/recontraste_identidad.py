"""Refresca fuentes exactas tras una corrección, sin volver a resolver identidad."""
from copy import deepcopy

from entregables.investigacion_identidad import preparar_contexto
from reglas.resultados_profesionales import reconciliar_resultados_profesionales
from orquestador.etapas_reales import (
    _fx_de_obra, _cobertura_cert, _fuera_de_ventana, _COBERTURA_MIN,
)
from reglas.cruces_fechas import cruces_de_experiencia
from resolucion.cui import tipo_evaluacion_del_espejo
from scraping.infoobras import fetch_by_cui, periodos_inactividad
from scraping.seace_abierto import tipo_por_experiencia
from validacion.candado_seace import evaluar_candado
from validacion.servicio_experiencia import contrastar_servicio, fase_servicio_incompatible
from validacion.recalculo import fechas_calculo, regla_periodos_de
from orquestador.recontraste_fuentes import FuentesRecontraste


def recontrastar_asociaciones(espejo, enriquecimiento, casos_ids, *, leer_obra=None, fuentes=None):
    """Solo unidades afectadas. Ausencia de lectura nunca recupera la ficha vieja.

    MEF/SUNAT se releen sin heredar cruces ni sustituir el contrato seleccionado.
    No se convierte una investigación en dictamen.
    """
    leer_obra = leer_obra or fetch_by_cui
    fuentes = fuentes or FuentesRecontraste()
    nuevo = deepcopy(enriquecimiento)
    tipo = tipo_evaluacion_del_espejo(espejo)
    casos = {c["caso_id"]: c for c in preparar_contexto("recontraste", espejo, nuevo, tipo)["casos"]}
    experiencias = {(p["n_prof"], e["n"]): e for p in espejo.get("profesionales", [])
                    for e in p.get("experiencias", [])}
    if not casos_ids or len(set(casos_ids)) != len(casos_ids) or any(c not in casos for c in casos_ids):
        raise ValueError("Unidades de recontraste inexistentes o duplicadas")
    cache, profesionales = {}, set()
    for cid in casos_ids:
        caso = casos[cid]
        clave = f"{caso['n_prof']}:{caso['n_exp']}"
        padre = nuevo[clave]
        sub = caso["subobra"]
        unidad = padre["sub_obras"][sub - 1] if sub else padre
        asociacion = unidad.get("asociacion_investigada")
        if not asociacion:
            raise ValueError("Unidad sin aplicación investigada")
        cert = deepcopy(experiencias[caso["n_prof"], caso["n_exp"]])
        if sub:
            # Contexto del certificado sí; fechas globales para una subobra NO.
            cert.pop("fecha_inicial", None)
            cert.pop("fecha_final", None)
            cert.update(caso.get("declarado_subobra") or {})
            for campo in ("fecha_inicial", "fecha_final"):
                if unidad.get(campo):
                    cert[campo] = unidad[campo]
        ini, fin, _ = fechas_calculo(cert, regla_periodos_de(espejo))
        expediente = unidad.get("camino") == "expediente"
        unidad["contraste_servicio"] = contrastar_servicio(espejo, cert)
        otra_fase = fase_servicio_incompatible(espejo, cert, expediente)
        unidad["servicio_fase_incompatible"] = otra_fase
        for campo in ("obra_ficha", "ficha", "valorizaciones", "modificaciones_plazo",
                      "codigo_infoobras", "obra_nombre", "paralizaciones", "cobertura_baja",
                      "cobertura", "cruces_fechas", "aprobacion_expediente",
                      "verificacion_expediente", "resolucion_aprobacion", "sunat"):
            unidad.pop(campo, None)
        unidad["sin_verificar"] = True
        cui, oid = unidad.get("cui"), (unidad.get("obra") or {}).get("obra_id")
        fuente = {"estado": "sin_identidad", "motivo": "No hay ficha exacta seleccionada; no se eligió otra."}
        obra = None
        if cui and oid:
            llave = (str(cui), int(oid))
            if llave not in cache:
                try:
                    cache[llave] = (leer_obra(str(cui), obra_id=int(oid)), None)
                except Exception as exc:
                    cache[llave] = (None, type(exc).__name__)
            obra, error = cache[llave]
            fuente = {"estado": "no_disponible", "cui": cui, "obra_id": oid,
                      "motivo": "No se obtuvo la ficha exacta; no prueba que la obra no exista."}
            if error:
                fuente.update(estado="fuente_no_respondio", error=error)
            if obra is not None and (str(obra.cui) != str(cui) or int(obra.obra_id) != int(oid)):
                obra = None
                fuente.update(estado="identidad_discrepante", motivo="La fuente devolvió otra identidad; datos descartados.")
        if obra is not None:
            fuente.update(estado="disponible", motivo="Lectura de la ficha seleccionada, sin desempate por fechas.")
            fx = _fx_de_obra(obra, cui)
            unidad.update(obra_nombre=obra.nombre, codigo_infoobras=obra.codigo_infoobras,
                          obra_ficha={k: v for k, v in fx.items() if k not in {"valorizaciones", "modificaciones_plazo"}},
                          valorizaciones=fx["valorizaciones"], modificaciones_plazo=fx["modificaciones_plazo"],
                          sin_verificar=otra_fase)
            unidad["obra"]["nombre_obra"] = obra.nombre
            if sub:
                unidad["ficha"] = {**fx, "obra_nombre": obra.nombre}
            if not expediente and not otra_fase:
                unidad["paralizaciones"] = [
                    {"inicio": p["inicio"].isoformat(), "fin": p["fin"].isoformat(), "tipo": p["tipo"]}
                    for p in periodos_inactividad(obra.avances)]
                for a, b in _fuera_de_ventana(obra.avances, ini, fin, obra.fecha_inicio):
                    antes = bool(obra.fecha_inicio and b < obra.fecha_inicio)
                    unidad["paralizaciones"].append({"inicio": a.isoformat(), "fin": b.isoformat(),
                        "tipo": "antes_inicio_obra" if antes else "fuera_de_ventana",
                        **({"fecha_inicio_obra": obra.fecha_inicio.isoformat()} if antes else {})})
                cobertura = _cobertura_cert(obra.avances, ini, fin, obra.fecha_inicio)
                if cobertura is not None and cobertura < _COBERTURA_MIN:
                    unidad["cobertura_baja"] = cobertura
            if expediente and not otra_fase and obra.aprobacion_expediente:
                unidad["aprobacion_expediente"] = deepcopy(obra.aprobacion_expediente)
        seace = unidad.get("seace") or {}
        if seace.get("estado") == "seleccionado":
            seace["candado"] = evaluar_candado(seace["proceso"], {
                **cert, "tipo_experiencia": tipo_por_experiencia(expediente, cert)["tipo"],
            }).como_dict()
        estados_fuentes, faltantes_fuentes = {}, []
        if expediente and cui and not otra_fase:
            bloque, estado, motivos = fuentes.contrastar_mef(cert, str(cui), seace)
            unidad["verificacion_expediente"] = bloque
            estados_fuentes["mef"] = estado
            faltantes_fuentes.extend(motivos)
        elif expediente and not otra_fase:
            unidad["verificacion_expediente"] = {
                "verificado_en_mef": False, "estado": "no_recontrastado",
                "motivo": "Sin CUI inequívoco para consultar MEF; aprobación por verificar."}
            faltantes_fuentes.append(unidad["verificacion_expediente"]["motivo"])
        bloque, estado, motivos = fuentes.contrastar_sunat(cert, unidad, espejo)
        unidad["sunat"] = bloque
        estados_fuentes["sunat"] = estado
        faltantes_fuentes.extend(motivos)
        unidad["cruces_fechas"] = [c.como_dict() for c in cruces_de_experiencia(unidad, cert)]
        faltantes = []
        if otra_fase:
            faltantes.append("El certificado declara otra fase; los datos de la ruta del concurso no respaldan su periodo.")
        if fuente["estado"] != "disponible":
            faltantes.append(fuente["motivo"])
        if not seace.get("fecha_suscripcion"):
            faltantes.append("Sin fecha del contrato exacto seleccionado.")
        faltantes.extend(faltantes_fuentes)
        asociacion.update(contraste_derivado="actualizado_con_faltantes" if faltantes else "actualizado",
                          fuentes={"infoobras": fuente, **estados_fuentes}, faltantes=faltantes)
        unidad["decision"] = "Fuentes corregidas y contraste actualizado. " + " ".join(faltantes)
        if sub:
            # El total global de un certificado multiobra no se atribuye a un hijo.
            padre.pop("paralizaciones", None)
            padre["sin_verificar"] = True
            padre["decision"] = "Subobras actualizadas por separado; periodo global no atribuible a una sola obra."
        profesionales.add(caso["n_prof"])
    for np in profesionales:
        nuevo.pop(f"prof:{np}", None)
    recalculados = reconciliar_resultados_profesionales(espejo, nuevo)
    for np in profesionales:
        nuevo[f"prof:{np}"] = recalculados.get(np, {})
    return nuevo
