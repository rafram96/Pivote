"""Materializa la selección MEF por experiencia; nunca vuelve a elegirla."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from orquestador.repositorio import _escribir_atomico
from orquestador.descargas_seace import (
    CacheDescargasSeace, archivo_seace_valido, materializar_archivo,
)

SECCION_MEF = "Verificación MEF"


def documentos_por_experiencia(exp: dict, info: dict, tipo_evaluacion, sub_pos=None) -> list[dict]:
    from resolucion.cui import es_expediente_exp
    if str(info.get("via") or "").upper() == "PRIVADA":
        return []
    if sub_pos is not None and info.get("estado") != "resuelto":
        return []
    camino = info.get("camino")
    if camino != "expediente" and (camino or not es_expediente_exp(exp, tipo_evaluacion)):
        return []
    return documentos_seleccionados(info)


def documentos_seleccionados(info: dict) -> list[dict]:
    verificacion = info.get("verificacion_expediente") or {}
    contrato = verificacion.get("contrato") or {}
    lectura = info.get("resolucion_aprobacion") or {}
    # La lectura retenida puede corresponder a otro adjunto que el candidato 08-A.
    resolucion = lectura or verificacion.get("resolucion") or {}
    salida = []
    if contrato.get("numero") or contrato.get("pdf"):
        salida.append({"tipo": "contrato", "numero": contrato.get("numero"),
                       "url": contrato.get("pdf"), "cui": info.get("cui"),
                       "elegido_por": contrato.get("elegido_por")})
    if any(resolucion.get(k) for k in ("numero", "documento", "url", "archivo")):
        salida.append({"tipo": "resolucion", "numero": resolucion.get("numero"),
                       "url": resolucion.get("url"), "cui": info.get("cui"),
                       "archivo": lectura.get("archivo"), "sha256": lectura.get("sha256"),
                       "leida": bool(lectura)})
    urls = {d.get("url") for d in salida}
    for doc in verificacion.get("documentos_contractuales") or []:
        if doc.get("url") and doc["url"] not in urls:
            salida.append({"tipo": "acto_contractual", "url": doc["url"],
                           "etiqueta": doc.get("label"), "cui": info.get("cui"),
                           "clasificacion": "Indicado por etiqueta; contenido por confirmar"})
            urls.add(doc["url"])
    return salida


class DescargasMefSeleccionadas:
    def __init__(self, job_dir: Path, *, intentar, descargar=None):
        self.job_dir = Path(job_dir).resolve()
        self.cache = CacheDescargasSeace(self.job_dir / "cache_mef_documentos")
        self.intentar = intentar
        if descargar is None:
            from scraping.mef import crear_session, descargar_pdf
            sesion = crear_session()
            descargar = lambda url, ruta: descargar_pdf(sesion, url, ruta)
        self.descargar = descargar

    def materializar(self, docs: list[dict], destino: Path) -> dict:
        carpeta = Path(destino) / SECCION_MEF
        if not carpeta.resolve().is_relative_to(self.job_dir / "descargas"):
            raise ValueError("Destino MEF fuera del job")
        huella = hashlib.sha256(json.dumps(docs, sort_keys=True).encode()).hexdigest()
        manifiesto = carpeta / "DOCUMENTOS_MEF.json"
        anterior = {}
        if manifiesto.is_file():
            try:
                anterior = json.loads(manifiesto.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                pass
        # También retira carpetas legadas: el corpus por obra no acredita selección P/E.
        if carpeta.exists() and anterior.get("seleccion_sha256") != huella:
            respaldo = self.job_dir / "descargas_previas" / f"mef-{uuid.uuid4().hex}"
            respaldo.parent.mkdir(parents=True, exist_ok=True)
            os.replace(carpeta, respaldo)
        registros = []
        for doc in docs:
            registro = {**doc, "estado": "no_descargado",
                        "rol_documental": "por_identificar", "correspondencia": "por_confirmar"}
            destino_pdf = carpeta / ("CONTRATO_SELECCIONADO.pdf" if doc["tipo"] == "contrato"
                                     else "RESOLUCION_SELECCIONADA.pdf")
            if doc["tipo"] == "acto_contractual":
                sufijo = hashlib.sha256(doc["url"].encode()).hexdigest()[:12]
                destino_pdf = carpeta / f"ACTO_CONTRACTUAL_{sufijo}.pdf"
            try:
                if doc.get("leida"):
                    self._copiar_lectura(doc, destino_pdf)
                else:
                    url = doc.get("url")
                    if not url:
                        raise ValueError("La selección no conserva enlace descargable")
                    clave = hashlib.sha256(url.encode()).hexdigest()
                    if self.intentar(f"mef_documento:{clave}"):
                        resultado = self.cache.materializar(url, destino_pdf, descargar=self.descargar)
                    else:
                        resultado = self.cache.materializar_existente(url, destino_pdf)
                    if not resultado.ok:
                        raise ValueError("No se pudo obtener el enlace seleccionado; no se eligió otro documento")
                registro.update(estado="descargado", archivo_entregado=destino_pdf.name,
                                sha256_entregado=hashlib.sha256(destino_pdf.read_bytes()).hexdigest())
            except Exception as exc:  # una fuente fallida no impide descargar la otra
                registro["estado"] = ("descarga_fallida" if doc.get("url") or doc.get("leida")
                                      else "sin_enlace")
                # Si la copia deja de ser verificable, no conservar un PDF previo como vigente.
                if destino_pdf.exists():
                    respaldo = self.job_dir / "descargas_previas" / f"mef-{uuid.uuid4().hex}"
                    respaldo.mkdir(parents=True)
                    os.replace(destino_pdf, respaldo / destino_pdf.name)
                registro["motivo"] = str(exc) if isinstance(exc, ValueError) else "No se pudo materializar el documento seleccionado"
            registros.append(registro)
        if docs:
            carpeta.mkdir(parents=True, exist_ok=True)
            _escribir_atomico(manifiesto, json.dumps({
                "seleccion_sha256": huella, "documentos": registros,
                "alcance": "Copias de la selección del análisis. No acredita tipo de acto, autenticidad ni correspondencia con el encargo.",
            }, ensure_ascii=False))
            lineas = ["Documentos MEF seleccionados para esta experiencia.",
                      "Se conserva la selección del análisis; no se certifica su correspondencia ni el tipo del acto.", ""]
            for r in registros:
                lineas.append(f"{r['tipo'].capitalize()} {r.get('numero') or 'sin número'}: "
                              + ("descargado" if r["estado"] == "descargado" else "no descargado"))
                if r.get("archivo_entregado"):
                    lineas.append(f"Archivo: {r['archivo_entregado']}")
                if r.get("motivo"):
                    lineas.append(r["motivo"])
                if r.get("etiqueta"):
                    lineas.append(f"Etiqueta del portal: {r['etiqueta']} (contenido por confirmar)")
                lineas.append("")
            _escribir_atomico(carpeta / "DOCUMENTOS_MEF.txt", "\n".join(lineas))
        return {"esperados": len(docs),
                "descargados": sum(r["estado"] == "descargado" for r in registros),
                "documentos": registros}

    def _copiar_lectura(self, doc: dict, destino: Path) -> None:
        nombre = str(doc.get("archivo") or "")
        raiz = self.job_dir / "resoluciones"
        origen = (raiz / nombre).resolve()
        if not nombre or Path(nombre).name != nombre or not origen.is_relative_to(raiz):
            raise ValueError("La lectura no conserva una ruta local segura; requiere nueva lectura explícita")
        if not archivo_seace_valido(origen):
            raise ValueError("El PDF leído no está disponible; no se sustituye por otro")
        huella = hashlib.sha256(origen.read_bytes()).hexdigest()
        if doc.get("sha256") and doc["sha256"] != huella:
            raise ValueError("El PDF cambió desde la lectura; requiere nueva lectura explícita")
        if not doc.get("sha256"):
            raise ValueError("Lectura histórica sin huella del PDF; requiere nueva lectura explícita")
        materializar_archivo(origen, destino)
