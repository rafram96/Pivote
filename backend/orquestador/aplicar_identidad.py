"""Aplicación explícita de investigación; fuentes exactas y retiro recuperable."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import uuid

from entregables.investigacion_identidad import preparar_contexto
from orquestador.repositorio import _escribir_atomico
from scraping.consulta_infoobras import consultar_ficha
from scraping.seace_abierto import (
    procesos_por_cui, clasificar_proceso, doc_bases_integradas, doc_contrato_firmado,
)
from validacion.candado_seace import resumen_proceso


def _reemplazar_unidad(enriquecimiento, caso, valor):
    clave = f"{caso['n_prof']}:{caso['n_exp']}"
    padre = enriquecimiento.setdefault(clave, {})
    if caso["subobra"]:
        subs = padre.setdefault("sub_obras", [])
        while len(subs) < caso["subobra"]:
            subs.append({})
        previo = subs[caso["subobra"] - 1]
        subs[caso["subobra"] - 1] = valor(previo)
        padre.pop("descargas_reales", None)
    else:
        enriquecimiento[clave] = valor(padre)


def _proceso_exacto(cui, propuesto, consultar):
    if not propuesto or not (propuesto.get("ocid") or propuesto.get("nomenclatura")):
        return {"estado": "identidad_pendiente", "docs": {},
                "motivo": "No se identificó un proceso exacto; no se reutiliza el contrato anterior."}
    procesos = consultar(cui)
    if procesos is None:
        raise ValueError("SEACE no respondió; no se aplicó la asociación")
    coincidencias = [p for p in procesos if
        (not propuesto.get("ocid") or p.get("ocid") == propuesto["ocid"]) and
        (not propuesto.get("nomenclatura") or
         propuesto["nomenclatura"] in ((p.get("tender") or {}).get("title"),
                                      (p.get("tender") or {}).get("id")))]
    if len(coincidencias) != 1:
        raise ValueError("El proceso exacto no es único en la consulta; no se eligió otro")
    proceso = coincidencias[0]
    if not propuesto.get("rol") or clasificar_proceso(proceso)[0] != propuesto["rol"]:
        raise ValueError("El rol contractual propuesto no coincide con el proceso oficial")
    numero = propuesto.get("contrato_numero")
    contratos = proceso.get("contracts") or []
    if numero:
        contratos = [c for c in contratos if numero in (c.get("id"), c.get("title"))]
        if len(contratos) != 1:
            raise ValueError("Contrato exacto no comprobado; no se sustituye por el primero")
    # Sin número, varios contratos no permiten elegir un contrato firmado.
    contrato = doc_contrato_firmado({"contracts": contratos}) if len(contratos) == 1 else None
    fuente = deepcopy(proceso)
    fuente["contracts"] = deepcopy(contratos) if len(contratos) == 1 else []
    # Los proveedores de otros contratos del mismo proceso no acreditan este.
    premios = {c.get("awardID") for c in fuente["contracts"] if c.get("awardID")}
    fuente["awards"] = [a for a in fuente.get("awards", []) if a.get("id") in premios]
    fuente["parties"] = []
    resumen = resumen_proceso(fuente)
    if not fuente["contracts"] or (fuente["contracts"][0].get("value") or {}).get("amount") is None:
        resumen["monto"] = None  # valor referencial no es monto del contrato
    elif (fuente["contracts"][0].get("value") or {}).get("amount") == 0:
        resumen["monto"] = 0
    resumen["tipo"] = propuesto["rol"]
    return {"estado": "seleccionado", "proceso": resumen, "proceso_fuente": fuente,
            "cui": cui, "ocid": proceso.get("ocid"), "proceso_objeto": propuesto["rol"],
            "fecha_suscripcion": resumen.get("fecha_firma"),
            "vigencia": [resumen.get("vigencia_inicio"), resumen.get("vigencia_fin")],
            "tipo": propuesto["rol"], "motivo": "Proceso exacto de investigación; no seleccionado por fechas",
            "docs": {"bases": doc_bases_integradas(proceso), "contrato": contrato}}


def proyectar_asociaciones(job_id, espejo, enriquecimiento, tipo, resultados,
                          *, leer_ficha=consultar_ficha, leer_procesos=procesos_por_cui):
    """Prepara todo en memoria. Cualquier error deja el estado original intacto."""
    paquete = preparar_contexto(job_id, espejo, enriquecimiento, tipo)
    casos = {c["caso_id"]: c for c in paquete["casos"]}
    nuevo = deepcopy(enriquecimiento)
    afectados, vistos = [], set()
    fichas_leidas, procesos_leidos = {}, {}

    def procesos_del_lote(cui):
        if cui not in procesos_leidos:
            procesos_leidos[cui] = leer_procesos(cui)
        return procesos_leidos[cui]
    if not isinstance(resultados, list) or not resultados or len(resultados) > len(casos):
        raise ValueError("Lote de resultados vacío o inválido")
    for r in resultados:
        permitidos = {"version", "job_id", "huella_contexto", "caso_id", "estado",
                      "seleccion_propuesta", "candidatos", "evidencias", "discrepancias",
                      "faltantes", "consultas", "motivo", "limites"}
        if not isinstance(r, dict) or set(r) - permitidos:
            raise ValueError("Resultado contiene campos ajenos al contrato de investigación")
        cid = r.get("caso_id")
        if cid not in casos or cid in vistos or type(r.get("version")) is not int or r["version"] != 1:
            raise ValueError("Caso inválido o duplicado")
        vistos.add(cid)
        if r.get("job_id") != job_id or r.get("huella_contexto") != paquete["huella_contexto"]:
            raise ValueError("Contexto obsoleto o de otro job")
        if r.get("estado") in {"ambiguo", "sin_candidato"}:
            if r.get("seleccion_propuesta") is not None or not r.get("motivo") or not r.get("consultas"):
                raise ValueError("Abstención sin motivo/consultas o con selección activa")
            caso = casos[cid]
            def pendiente(previo):
                return {**{k: deepcopy(previo[k]) for k in
                    ("proyecto", "fecha_inicial", "fecha_final", "camino") if k in previo},
                    "estado": "revision", "cui": None, "obra": None, "sin_verificar": True,
                    "revision_identidad": uuid.uuid4().hex, "decision": r["motivo"],
                    "seace": {"estado": "identidad_pendiente", "docs": {}},
                    "asociacion_investigada": {"resultado": deepcopy(r), "anterior": deepcopy(previo),
                                              "contraste_derivado": "pendiente"}}
            _reemplazar_unidad(nuevo, caso, pendiente)
            afectados.append(caso)
            continue
        if r.get("estado") != "asociacion_propuesta":
            raise ValueError("Estado no aplicable: un fallo de fuente no prueba ausencia ni naturaleza privada")
        candidatos = r.get("candidatos") or []
        seleccion = (r.get("seleccion_propuesta") or {}).get("candidato_id")
        elegidos = [c for c in candidatos if c.get("id") == seleccion]
        if len(elegidos) != 1:
            raise ValueError("Selección inexistente o duplicada")
        candidato = elegidos[0]
        if set(candidato) - {"id", "cui", "obra_id", "intervencion", "procedimiento", "evidencias", "motivo"}:
            raise ValueError("Candidato contiene campos ajenos al contrato")
        cui, oid = candidato.get("cui"), candidato.get("obra_id")
        if not isinstance(cui, str) or not re.fullmatch(r"[0-9]{1,10}", cui):
            raise ValueError("CUI inválido")
        if oid is not None and (type(oid) is not int or not 0 < oid <= 2147483647):
            raise ValueError("Ficha inválida")
        evidencia = r.get("evidencias") or []
        ids = [e.get("id") for e in evidencia]
        if len(ids) != len(set(ids)) or any(i not in ids for i in candidato.get("evidencias", [])):
            raise ValueError("Evidencias duplicadas o inexistentes")
        soporte = [e for e in evidencia if e.get("id") in candidato.get("evidencias", [])
                   and e.get("acceso") == "leido" and isinstance(e.get("cita"), str)
                   and len(e["cita"].strip()) >= 3]
        oficiales = {e.get("campo") for e in soporte if e.get("tipo_fuente") == "oficial"
                     and re.match(r"^https?://[^/]+", str(e.get("url") or ""))}
        necesarios = {"cui"} | ({"obra_id"} if oid else set())
        if candidato.get("procedimiento"):
            necesarios.add("contrato")
        if not necesarios <= oficiales or not any(e.get("campo") == "intervencion"
                and e.get("tipo_fuente") in {"oficial", "propuesta"} for e in soporte):
            raise ValueError("Falta evidencia leída de la intervención o de sus identificadores oficiales")
        ficha = None
        if oid:
            if (cui, oid) not in fichas_leidas:
                fichas_leidas[cui, oid] = leer_ficha(cui, oid)
            lectura = fichas_leidas[cui, oid]
            ficha = lectura.get("ficha") or {}
            if (lectura.get("estado") not in {"disponible", "parcial"}
                    or str(ficha.get("cui")) != cui or ficha.get("obra_id") != oid
                    or not any(f.get("estado") == "disponible" for f in lectura.get("fuentes", []))):
                raise ValueError("No se pudo comprobar la ficha exacta; no se sustituyó por otra")
        seace = _proceso_exacto(cui, candidato.get("procedimiento"), procesos_del_lote)
        if not ficha and seace.get("estado") != "seleccionado":
            raise ValueError("Sin ficha ni proceso exacto comprobado; asociación pendiente")
        caso = casos[cid]
        clave = f"{caso['n_prof']}:{caso['n_exp']}"
        padre = nuevo.setdefault(clave, {})
        if caso["subobra"]:
            posicion = caso["subobra"] - 1
            subs = padre.setdefault("sub_obras", [])
            while len(subs) <= posicion:
                subs.append({})
            previo = subs[posicion]
        else:
            previo = padre
        # No trasladar valorizaciones, contratos, SUNAT cruzado, días o veredictos
        # de otra identidad. El espejo declarado jamás se modifica.
        actualizado = {k: deepcopy(previo[k]) for k in
                       ("proyecto", "fecha_inicial", "fecha_final", "camino") if k in previo}
        actualizado.update({"estado": "resuelto", "cui": cui,
            "revision_identidad": uuid.uuid4().hex,
            "camino": "expediente" if tipo == "expedientes" else "obra",
            "obra": {"obra_id": oid, "cui": cui, "nombre": ficha.get("nombre")} if ficha else None,
            "seace": seace, "sin_verificar": True,
            "decision": "Asociación investigada aplicada; contraste y cálculo derivados pendientes",
            "asociacion_investigada": {"resultado": deepcopy(r), "anterior": deepcopy(previo),
                                      "contraste_derivado": "pendiente"}})
        if caso["subobra"]:
            padre["sub_obras"][posicion] = actualizado
            padre.pop("descargas_reales", None)
        else:
            nuevo[clave] = actualizado
        afectados.append(caso)
    return nuevo, afectados


def publicar_asociaciones(repo, directorio: Path, job_id, anterior, nuevo, afectados):
    """Diario primero; si hay interrupción, lectores bloqueados y respaldo completo."""
    directorio = Path(directorio).resolve()
    pendiente = directorio / "identidad_pendiente.json"
    if pendiente.exists():
        raise ValueError("Hay una aplicación interrumpida; revisar su respaldo antes de continuar")
    revision = uuid.uuid4().hex
    respaldo = directorio / "identidades_previas" / revision
    respaldo.mkdir(parents=True)
    _escribir_atomico(respaldo / "enriquecimiento.json", json.dumps(anterior, ensure_ascii=False))
    _escribir_atomico(respaldo / "enriquecimiento_nuevo.json", json.dumps(nuevo, ensure_ascii=False))
    job = repo.cargar(job_id) if hasattr(repo, "cargar") else None
    if job:
        _escribir_atomico(respaldo / "job.json", job.model_dump_json())
    _escribir_atomico(pendiente, json.dumps({"revision": revision, "estado": "publicando"}))
    for caso in afectados:
        nombre = f"P{caso['n_prof']}_E{caso['n_exp']}"
        marca = nombre + (f"_S{caso['subobra']}" if caso["subobra"] else "")
        destino = directorio / "descargas" / nombre
        if caso["subobra"]:
            destino /= f"Subobra {caso['subobra']:02d}"
        rutas = [destino, directorio / "descargas" / f"{marca}.ok",
                 directorio / "descargas" / f"{marca}.seace.ok",
                 directorio / "fuentes_descarga" / f"{marca}.json"]
        for ruta in rutas:
            if not ruta.resolve().is_relative_to(directorio):
                raise ValueError("Ruta documental fuera del job")
            if ruta.exists():
                copia = respaldo / ruta.relative_to(directorio)
                copia.parent.mkdir(parents=True, exist_ok=True)
                os.replace(ruta, copia)
    for nombre in ("final.xlsx", "infoobras.zip"):
        ruta = directorio / nombre
        if ruta.exists():
            os.replace(ruta, respaldo / nombre)
    repo.guardar_enriquecimiento(job_id, nuevo)
    _escribir_atomico(directorio / "identidad_contraste_pendiente.json", json.dumps({
        "revision": revision, "casos": [c["caso_id"] for c in afectados],
        "motivo": "Identidades actualizadas; no reutilizar cálculos de las fuentes anteriores"}))
    return revision
