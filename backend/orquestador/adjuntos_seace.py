"""Materialización segura de adjuntos SEACE seleccionados."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from orquestador.descargas_seace import (
    CacheDescargasSeace,
    archivo_seace_valido,
    clave_archivo_seace,
    nota_seace_ausencia,
)
from orquestador.repositorio import _escribir_atomico
from scraping.seace_abierto import extension_documento


SECCION_SEACE = "Documentos SEACE"
ALCANCE = "Contenido y vínculo al encargo por confirmar; descarga no es verificación"


class ErrorIntegridadAdjuntos(RuntimeError):
    """No publicar un ZIP si no se pudo retirar/persistir la selección exacta."""


class MaterializadorAdjuntosSeace:
    """Copia únicamente la selección explícita, conservando trazabilidad."""

    def __init__(self, job_dir: Path, cache=None, intentar=None, descargar=None):
        self.job_dir = Path(job_dir).resolve()
        self.cache = cache if hasattr(cache, "materializar") else CacheDescargasSeace(
            Path(cache) if cache is not None else self.job_dir / "cache_seace"
        )
        self.intentar = intentar or (lambda _clave: True)
        self._intentadas: set[str] = set()
        if descargar is None:
            from scraping.seace_abierto import descargar_archivo
            descargar = descargar_archivo
        self.descargar = descargar

    def _puede_intentar(self, clave: str) -> bool:
        if clave in self._intentadas:
            return False
        self._intentadas.add(clave)
        return bool(self.intentar(clave))

    def _carpeta_segura(self, destino: Path) -> Path:
        raiz = (self.job_dir / "descargas").resolve()
        destino_real = Path(destino).resolve()
        carpeta = (destino_real / SECCION_SEACE).resolve()
        if destino_real == raiz or not carpeta.is_relative_to(raiz):
            raise ValueError("Destino SEACE fuera de descargas del job")
        return carpeta

    @staticmethod
    def _identidad(doc: dict) -> str:
        return json.dumps(tuple(str(doc.get(k) or "") for k in
                                ("categoria", "id_contrato", "id_documento", "ocid", "url")),
                          ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def _huella_seleccion(cls, docs: list[dict]) -> str:
        cuerpo = [dict(sorted(d.items())) for d in docs]
        return hashlib.sha256(json.dumps(cuerpo, ensure_ascii=False,
                                         sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def _huella_estado(cls, datos: dict, docs: list[dict]) -> str:
        return cls._huella_seleccion([{"estado": datos.get("estado"),
                                       "motivo": datos.get("motivo"),
                                       "documentos": docs}])

    def _respaldar(self, carpeta: Path) -> None:
        raiz = self.job_dir.resolve()
        respaldo = (self.job_dir / "descargas_previas" / uuid.uuid4().hex).resolve()
        if not carpeta.resolve().is_relative_to(raiz) or not respaldo.is_relative_to(raiz):
            raise ValueError("Ruta de respaldo fuera del job")
        respaldo.parent.mkdir(parents=True, exist_ok=True)
        os.replace(carpeta, respaldo)

    def retirar_legado(self, destino: Path) -> int:
        """Mueve archivos SEACE históricos de la raíz de una experiencia."""
        destino = Path(destino).resolve()
        raiz = (self.job_dir / "descargas").resolve()
        if destino == raiz or not destino.is_relative_to(raiz):
            raise ValueError("Destino SEACE fuera de descargas del job")
        nombres = ("BASES_INTEGRADAS", "CONTRATO_FIRMADO", "SEACE_")
        archivos = [p for p in destino.iterdir() if p.is_file() and
                    any(p.name.upper().startswith(n) for n in nombres)] if destino.is_dir() else []
        if not archivos:
            return 0
        respaldo = (self.job_dir / "descargas_previas" / uuid.uuid4().hex).resolve()
        if not respaldo.is_relative_to(self.job_dir):
            raise ValueError("Ruta de respaldo fuera del job")
        if any(not archivo.resolve().is_relative_to(destino) for archivo in archivos):
            raise ValueError("Archivo legado fuera de la experiencia")
        respaldo.mkdir(parents=True, exist_ok=True)
        for archivo in archivos:
            os.replace(archivo, respaldo / archivo.name)
        return len(archivos)

    def materializar(self, datos_seace: dict, destino: Path) -> dict:
        carpeta = self._carpeta_segura(Path(destino))
        entradas = datos_seace.get("documentos") or []
        entradas = [d for d in entradas if isinstance(d, dict)]
        seleccion = ([dict(d) for d in entradas]
                     if datos_seace.get("estado") == "seleccionado" else [])
        huella = (self._huella_seleccion(seleccion) if datos_seace.get("estado") == "seleccionado"
                  else self._huella_estado(datos_seace, entradas))
        manifiesto = carpeta / "DOCUMENTOS_SEACE.json"
        anterior_huella = None
        if manifiesto.is_file():
            try:
                anterior_huella = json.loads(manifiesto.read_text(encoding="utf-8")).get("seleccion_sha256")
            except (OSError, ValueError, TypeError):
                pass

        # Todo estado distinto de seleccionado, incluida una consulta vacía,
        # retira la selección previa: no debe quedar un adjunto viejo disponible.
        retirados = False
        if carpeta.exists() and anterior_huella != huella:
            self._respaldar(carpeta)
            retirados = True
        retirados = bool(self.retirar_legado(Path(destino))) or retirados

        registros = []
        for original in seleccion:
            doc = dict(original)
            doc["rol_documental"] = "por_identificar"
            doc["correspondencia"] = "por_confirmar"
            registro = dict(doc, estado="sin_enlace")
            url = str(doc.get("url") or "")
            if not url:
                registro["motivo"] = "El registro seleccionado no conserva enlace descargable"
                registros.append(registro)
                continue
            ext = extension_documento(doc)
            prefijo = "BASES" if str(doc.get("categoria")) == "bases" else "ADJUNTO_CONTRATO"
            nombre = f"{prefijo}_{hashlib.sha256(self._identidad(doc).encode()).hexdigest()[:12]}{ext}"
            archivo = carpeta / nombre
            try:
                clave = clave_archivo_seace(url)
                if self._puede_intentar(f"seace:{clave}"):
                    resultado = self.cache.materializar(url, archivo, descargar=self.descargar)
                else:
                    resultado = self.cache.materializar_existente(url, archivo)
                if not resultado.ok or not archivo_seace_valido(archivo):
                    raise ValueError("No se pudo obtener un archivo SEACE utilizable")
                registro.update(estado="descargado", archivo_entregado=nombre,
                                sha256_entregado=hashlib.sha256(archivo.read_bytes()).hexdigest())
            except Exception as exc:
                archivo.unlink(missing_ok=True)
                registro.update(estado="descarga_fallida", motivo=str(exc))
            registros.append(registro)

        carpeta.mkdir(parents=True, exist_ok=True)
        contenido = {"seleccion_sha256": huella, "documentos": registros, "alcance": ALCANCE,
                     "estado_fuente": datos_seace.get("estado"), "motivo": datos_seace.get("motivo")}
        _escribir_atomico(carpeta / "DOCUMENTOS_SEACE.json", json.dumps(contenido, ensure_ascii=False, indent=2))
        lineas = ["Documentos SEACE seleccionados.", ALCANCE, ""]
        if datos_seace.get("estado") != "seleccionado":
            lineas = ["No se seleccionaron documentos SEACE en esta corrida."]
            lineas.append(nota_seace_ausencia(datos_seace.get("estado")))
            if retirados:
                lineas.append("Los adjuntos anteriores fueron retirados a un respaldo recuperable.")
            if datos_seace.get("motivo"):
                lineas.append(f"Motivo: {datos_seace['motivo']}")
            lineas.extend([f"Estado de fuente: {datos_seace.get('estado') or 'no indicado'}", ALCANCE, ""])
        elif not registros:
            lineas.append(nota_seace_ausencia("seleccionado"))
        for r in registros:
            lineas.extend([
                f"Proceso/OCID: {r.get('ocid') or 'no indicado'} | Contrato: {r.get('id_contrato') or 'no indicado'}",
                f"Categoría: {r.get('categoria') or 'no indicada'} | ID documento: {r.get('id_documento') or 'no indicado'}",
                f"Título: {r.get('titulo') or 'no indicado'}",
                f"URL: {r.get('url') or 'sin enlace'}",
                f"Hash: {r.get('sha256_entregado') or 'no disponible'}",
                f"Estado: {r['estado']}",
            ])
            if r.get("archivo_entregado"):
                lineas.append(f"Archivo entregado: {r['archivo_entregado']}")
            if r.get("motivo"):
                lineas.append(f"Motivo: {r['motivo']}")
            lineas.append("")
        _escribir_atomico(carpeta / "DOCUMENTOS_SEACE.txt", "\n".join(lineas))
        return {"esperados": len(seleccion),
                "descargados": sum(r["estado"] == "descargado" for r in registros),
                "documentos": registros}
