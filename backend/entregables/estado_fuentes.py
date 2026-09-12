"""Presentación de consultas y descargas, sin decidir identidad ni cumplimiento.

Un resultado vacío describe una consulta, no la inexistencia de un proyecto.
Un archivo descargado describe adquisición, no correspondencia documental.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter


_NOMBRES = {
    "mef_ficha": "MEF · ficha 08-A", "mef_contratos": "MEF · contratos",
    "sunat_nombre": "SUNAT · búsqueda por nombre", "sunat_ruc": "SUNAT · ficha RUC",
    "infoobras_busqueda": "InfoObras · búsqueda",
    "infoobras_ejecucion": "InfoObras · ejecución",
    "infoobras_preparacion": "InfoObras · preparación",
    "infoobras_sumario": "InfoObras · sumario",
    "infoobras_seleccion": "InfoObras · selección de ficha",
}
_ESTADOS = {
    "con_resultados": "respuesta con datos",
    "sin_resultados": "consulta completada sin resultados; no demuestra inexistencia",
    "fuente_no_disponible": "fuente no disponible; no se pudo completar la consulta",
    "respuesta_no_reconocida": "respuesta no interpretable; no permite afirmar ausencia",
    "no_registrado": "estado de consulta no registrado",
    "no_consultado": "no consultado",
    "identidad_pendiente": "identidad pendiente; no se seleccionó otra ficha",
    "no_seleccionado": "sin ficha seleccionada; no equivale a búsqueda vacía",
}
_DESCARGAS = {
    "descargado": "descargado; tipo y correspondencia por confirmar",
    "descarga_fallida": "descarga fallida; no se pudo obtener una copia utilizable",
    "sin_enlace": "sin enlace descargable conservado",
    "no_descargado": "no descargado; revisar motivo registrado",
    "no_intentado": "descarga no intentada",
    "enlace_sin_descarga_registrada": "enlace identificado; descarga no registrada",
}


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _contexto(enriquecimiento) -> dict:
    enr = _dict(enriquecimiento)
    return _dict(enr.get("_enriquecimiento_identidad")) or enr


def consultas_de(enriquecimiento) -> dict:
    enr = _contexto(enriquecimiento)
    consultas = deepcopy(_dict(_dict(enr.get("verificacion_expediente")).get("consultas_fuentes")))
    consultas.update(deepcopy(_dict(enr.get("consultas_fuentes"))))
    return {k: v for k, v in consultas.items() if isinstance(v, dict)}


def linea_consulta(recurso: str, consulta: dict) -> str:
    estado = _ESTADOS.get(consulta.get("estado"), "estado de consulta no reconocido")
    motivo = str(consulta.get("motivo") or "").strip()
    return f"{_NOMBRES.get(recurso, recurso)}: {estado}" + (f". {motivo}" if motivo else "")


def nota_ausencia_mef(enriquecimiento) -> str:
    """Ausencia en este análisis, nunca afirmación de lo que el MEF no publica."""
    consultas = {k: v for k, v in consultas_de(enriquecimiento).items() if k.startswith("mef_")}
    if consultas:
        return " · ".join(linea_consulta(k, v) for k, v in sorted(consultas.items())) + ". No se dispone de contrato ni aprobación utilizable en este análisis."
    return ("Este análisis no dispone de contrato ni aprobación utilizable; "
            "el estado de la consulta MEF no quedó registrado. No demuestra que no existan documentos.")


def proyectar_estado_fuentes(enriquecimiento) -> dict:
    """Contrato de salida redactado: no expone rutas locales, tokens ni URLs.

    Lee el manifiesto persistido, no el inventario anunciado por los portales.
    No cambia los contadores históricos de archivos ni el esquema de ingesta.
    """
    enr = _contexto(enriquecimiento)
    consultas = consultas_de(enr)
    consultas = {k: {"estado": v.get("estado") or "no_registrado",
                     "motivo": v.get("motivo") or ""} for k, v in consultas.items()}
    notas = [linea_consulta(k, v) for k, v in sorted(consultas.items())]
    sunat = _dict(enr.get("sunat"))
    if sunat.get("ambiguo"):
        notas.append(f"SUNAT · selección: {sunat['ambiguo']} coincidencias; emisor pendiente de identificación.")
    if enr.get("seleccion_obra_pendiente"):
        notas.append("InfoObras · selección: ficha pendiente de identificación; no equivale a fuente sin resultados.")
    seace = _dict(enr.get("seace"))
    if seace.get("estado"):
        from orquestador.descargas_seace import nota_seace_ausencia
        estado = seace["estado"]
        if estado == "seleccionado":
            notas.append("SEACE: proceso seleccionado; no acredita descarga ni correspondencia de sus documentos.")
        else:
            notas.append("SEACE: " + nota_seace_ausencia(estado))
    documentos = []
    secciones = _dict(_dict(enr.get("descargas_reales")).get("secciones"))
    for seccion, datos in secciones.items():
        datos = _dict(datos)
        for doc in datos.get("documentos") or []:
            if not isinstance(doc, dict):
                continue
            estado = doc.get("estado") or "no_registrado"
            titulo = str(doc.get("titulo") or doc.get("tipo") or doc.get("categoria") or "adjunto")
            texto = _DESCARGAS.get(estado, "estado de descarga no registrado")
            registro = {"fuente": seccion, "documento": titulo, "estado": estado,
                        "lectura": "texto_leido" if doc.get("leida") else "no_acreditada",
                        "correspondencia": "por_confirmar", "texto": texto,
                        "motivo": doc.get("motivo") or ""}
            documentos.append(registro)
            lectura = " Texto leído; tipo de acto y correspondencia siguen por confirmar." if doc.get("leida") else ""
            notas.append(f"{seccion} · {titulo}: {texto}.{lectura}")
    # Antes de materializar, tener el enlace no permite afirmar que la copia
    # existe. Tampoco inventar un fallo o intento a partir de su ausencia.
    if seace.get("estado") == "seleccionado" and "Documentos SEACE" not in secciones:
        candidatos = seace.get("documentos")
        if candidatos is None:
            candidatos = list(_dict(seace.get("docs")).values())
        for doc in candidatos or []:
            if not isinstance(doc, dict) or not doc.get("url"):
                continue
            titulo = str(doc.get("titulo") or doc.get("categoria") or "Adjunto SEACE")
            estado = "enlace_sin_descarga_registrada"
            documentos.append({"fuente": "Documentos SEACE", "documento": titulo,
                "estado": estado, "lectura": "no_acreditada", "correspondencia": "por_confirmar",
                "texto": _DESCARGAS[estado], "motivo": "No hay manifiesto de descarga para este enlace."})
            notas.append(f"Documentos SEACE · {titulo}: {_DESCARGAS[estado]}.")
    if not notas:
        notas.append("Estados de consulta y descarga no registrados en este análisis; no permiten deducir la causa de una ausencia.")
    return {"consultas": consultas, "documentos": documentos, "notas": notas}


def lineas_estado_fuentes(enriquecimiento) -> list[str]:
    return proyectar_estado_fuentes(enriquecimiento)["notas"]


def resumen_estado_fuentes(enriquecimiento) -> str:
    """Una fila legible en Excel; documentos repetidos se agrupan por estado."""
    proyeccion = proyectar_estado_fuentes(enriquecimiento)
    lineas = [linea_consulta(k, v) for k, v in sorted(proyeccion["consultas"].items())]
    lineas.extend(n for n in proyeccion["notas"] if n.startswith("SEACE:"))
    lineas.extend(n for n in proyeccion["notas"] if " · selección:" in n)
    grupos = Counter((d["fuente"], d["estado"]) for d in proyeccion["documentos"])
    lineas.extend(f"{fuente}: {n} archivo(s) — {_DESCARGAS.get(estado, 'estado no registrado')}."
                  for (fuente, estado), n in sorted(grupos.items()))
    return "\n".join(lineas or proyeccion["notas"])
