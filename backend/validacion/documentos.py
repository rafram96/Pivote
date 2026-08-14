"""Inventario documental puro, independiente de las descargas (#100)."""
from __future__ import annotations

import hashlib


def _id(prefijo: str, valor) -> str:
    huella = hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:20]
    return f"{prefijo}:{huella}"


def construir_inventario_documental(espejo: dict, enriquecimiento: dict) -> int:
    """Persiste lo encontrado en metadatos ya disponibles; nunca toca red/disco."""
    total_ids: set[str] = set()
    for prof in espejo.get("profesionales", []) or []:
        np_ = prof.get("n_prof")
        for exp in prof.get("experiencias", []) or []:
            ne = exp.get("n")
            clave = f"{np_}:{ne}"
            enr = enriquecimiento.get(clave)
            if not isinstance(enr, dict):
                continue
            docs: dict[str, dict] = {}
            obra = enr.get("obra") if isinstance(enr.get("obra"), dict) else {}
            obra_id = obra.get("obra_id") or enr.get("cui") or clave
            for val in enr.get("valorizaciones", []) or []:
                if not isinstance(val, dict):
                    continue
                cantidad = int(val.get("docs") or 0)
                hito = f"{val.get('anio')}-{val.get('mes')}"
                for i in range(cantidad):
                    did = _id("infoobras", f"{obra_id}:{hito}:{i}")
                    docs[did] = {"id": did, "fuente": "InfoObras", "tipo": "valorizacion"}
            seace = enr.get("seace") if isinstance(enr.get("seace"), dict) else {}
            for tipo, doc in (seace.get("docs") or {}).items():
                if not isinstance(doc, dict) or not (doc.get("url") or doc.get("estado") == "disponible"):
                    continue
                did = _id("seace", doc.get("url") or f"{obra_id}:{tipo}")
                docs[did] = {"id": did, "fuente": "SEACE", "tipo": tipo}
            aprobacion = enr.get("aprobacion_expediente")
            if isinstance(aprobacion, dict) and (aprobacion.get("url") or aprobacion.get("documento")):
                did = _id("aprobacion", aprobacion.get("url") or aprobacion.get("documento"))
                docs[did] = {"id": did, "fuente": "fuente existente", "tipo": "aprobacion"}
            inventario = {"documentos": list(docs.values()), "total": len(docs)}
            enr["inventario_documental"] = inventario
            enr["documentos_encontrados"] = len(docs)
            total_ids.update(docs)
            enriquecimiento[clave] = enr
    return len(total_ids)
