"""Contexto de investigación de solo lectura; no resuelve ni promueve identidades."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from reglas.cruces_fechas import identidad_sostenida_sin_temporal


CAMPOS_DECLARADOS = (
    "n", "proyecto", "objeto", "descripcion", "tipo_experiencia", "cui", "snip",
    "entidad_contratante", "entidad_emisora", "ruc_emisor", "ubicacion",
    "cargo_ocupado", "fecha_inicial", "fecha_final", "folio", "paginas_pdf",
    "tipo_documento", "contrato_numero", "numero_contrato", "obras",
)


def _dic(valor):
    return valor if isinstance(valor, dict) else {}


def _tomar(valor, campos):
    dato = _dic(valor)
    return {k: deepcopy(dato[k]) for k in campos if k in dato}


def _id(valor):
    return str(valor).strip() if valor is not None else None


def _contexto(ev: dict) -> dict:
    seace = _dic(ev.get("seace"))
    return {
        **_tomar(ev, ("estado", "via", "cui", "decision", "obra", "obra_inicial",
                      "candidatos", "camino", "sin_verificar", "sin_registro_infoobras", "revision_identidad")),
        "ficha": _tomar(ev.get("obra_ficha") or ev.get("ficha"),
                         ("obra_id", "codigo_infoobras", "cui", "obra_nombre",
                          "fecha_inicio", "fecha_fin", "estado")),
        "seace": _tomar(seace, ("estado", "ambiguo", "motivo", "candado", "proceso",
                                 "candidatos", "proceso_objeto", "codigoconvocatoria")),
    }


def _disparadores(ev: dict, tipo: str, multi: bool) -> list[str]:
    motivos = []
    via = str(ev.get("via") or "").upper()
    if via == "RUC":
        motivos.append("contratista_no_demuestra_intervencion")
    if not ev.get("cui") or via in {"REVISION", "PROBABLE", "PORTAL", "NO_EXISTE"} \
            or ev.get("estado") == "revision":
        motivos.append("identificacion_pendiente")
    if ev.get("sin_verificar"):
        motivos.append("consulta_no_completada")
    obra = _dic(ev.get("obra"))
    ficha = _dic(ev.get("obra_ficha") or ev.get("ficha"))
    oid = obra.get("obra_id")
    fid = ficha.get("obra_id") or ficha.get("codigo_infoobras")
    if oid and fid and _id(oid) != _id(fid):
        motivos.append("ficha_y_seleccion_difieren")
    if tipo == "obras" and ev.get("cui") and not (oid or fid):
        motivos.append("intervencion_sin_ficha")
    seace = _dic(ev.get("seace"))
    if seace.get("estado") == "seleccionado":
        motivos.append("contrato_requiere_contraste_de_rol_y_emisor")
    if seace.get("ambiguo"):
        motivos.append("varios_procedimientos")
    if seace.get("estado") == "seleccionado" and not identidad_sostenida_sin_temporal(
            _dic(seace.get("candado")))[0]:
        motivos.append("proceso_sin_identidad_independiente")
    if multi:
        motivos.append("certificado_multiobra")
    candidatos = ev.get("candidatos") or []
    ids = {_id(c.get("obra_id")) for c in candidatos if isinstance(c, dict)
           and c.get("obra_id") and _id(c.get("cui")) == _id(ev.get("cui"))}
    if len(ids) > 1:
        motivos.append("varias_fichas_registradas")
    return motivos


def preparar_contexto(job_id: str, espejo: dict, enriquecimiento: dict, tipo: str) -> dict:
    """Exporta unidades P/E (o P/E/subobra), sin red ni modificación del job.

    Los positivos sin señal se revisan primero por listado de fichas, una vez
    por CUI. No exigir señales de riesgo equivale a no auditar falsos positivos.
    Tampoco se usa el ranking de nombres como verdad o nuevo umbral de confianza.
    """
    casos, omitidos, referencias = [], [], set()
    for prof in espejo.get("profesionales") or []:
        np = prof["n_prof"]
        for exp in prof.get("experiencias") or []:
            ne = exp["n"]
            clave = f"{np}:{ne}"
            if clave in referencias:
                raise ValueError("Experiencia duplicada: no se puede vincular la investigación")
            referencias.add(clave)
            ev = _dic(enriquecimiento.get(clave))
            subs = ev.get("sub_obras") or []
            declaradas = exp.get("obras") or []
            cantidad = max(len(subs), len(declaradas))
            unidades = [(i + 1, subs[i] if i < len(subs) else {})
                        for i in range(cantidad)] if cantidad else [(None, ev)]
            for pos, unidad in unidades:
                unidad = _dic(unidad)
                caso_id = f"{clave}:s{pos}" if pos else clave
                if str(unidad.get("via") or "").upper() == "PRIVADA" \
                        or unidad.get("estado") == "privada":
                    omitidos.append({"caso_id": caso_id, "motivo": "ruta_privada_vigente_no_auditada"})
                    continue
                motivos = _disparadores(unidad, tipo, bool(pos or declaradas))
                sub = _dic(declaradas[pos - 1]) if pos and pos <= len(declaradas) else None
                casos.append({
                    "caso_id": caso_id, "n_prof": np, "n_exp": ne, "subobra": pos,
                    "cargo": prof.get("cargo"),
                    "declarado": _tomar(exp, CAMPOS_DECLARADOS),
                    "declarado_subobra": deepcopy(sub),
                    "contexto_backend": _contexto(unidad),
                    "certificado_nombre": f"P{np}_E{ne}.pdf",
                    "disparadores": motivos,
                    "accion": "investigar" if motivos else "comprobar_fichas",
                    "nota": ("Subobra por posición: cotejar con el certificado; no heredar "
                             "fechas globales ni afirmar que esta posición prueba asociación."
                             if pos else "La selección vigente es una pista, no una respuesta correcta."),
                })
    paquete = {"version": 1, "job_id": job_id, "tipo_evaluacion": tipo,
               "casos": casos, "omitidos": omitidos,
               "alcance": "Investigación de identidad; no dictamen ni aplicación a descargas."}
    paquete["huella_contexto"] = hashlib.sha256(json.dumps(
        paquete, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return paquete
