"""Lectura para investigar identidades, sin elegir obra ni crear descargas/jobs."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from scraping import infoobras

_LIMITE_TEXTO = 60000


class ConsultaIdentidadInvalida(ValueError):
    pass


def _codigo(valor) -> str:
    codigo = str(valor or "").strip()
    if not re.fullmatch(r"[0-9]{1,10}", codigo):
        raise ConsultaIdentidadInvalida("CUI/SNIP debe contener de 1 a 10 dígitos.")
    return codigo


def _id_obra(valor) -> int:
    if isinstance(valor, bool) or not re.fullmatch(r"[0-9]{1,10}", str(valor or "")):
        raise ConsultaIdentidadInvalida("obra_id debe ser un entero positivo.")
    numero = int(valor)
    if not 0 < numero <= 2147483647:
        raise ConsultaIdentidadInvalida("obra_id está fuera de rango.")
    return numero


def _base(codigo: str) -> dict:
    return {
        "cui_consultado": codigo,
        "consultado_en": datetime.now(timezone.utc).isoformat(),
        "fuente": "InfoObras / Contraloría",
        "alcance": "Lectura de registros; no confirma que correspondan al certificado ni evalúa al profesional.",
    }


def _fallo(exc: Exception) -> dict:
    respuesta = getattr(exc, "response", None)
    status = getattr(respuesta, "status_code", None)
    if status is not None:
        return {"estado": "error_http", "http_status": status,
                "motivo": f"La fuente respondió HTTP {status}; no demuestra ausencia de obra o documento."}
    if isinstance(exc, requests.RequestException):
        return {"estado": "fuente_no_respondio", "motivo": "No se completó la consulta a la fuente.",
                "tipo_error": type(exc).__name__}
    return {"estado": "formato_no_reconocido", "motivo": "No se pudo interpretar la respuesta de la fuente.",
            "tipo_error": type(exc).__name__}


def _candidatos(session, codigo: str) -> dict:
    obras = infoobras._buscar_por_cui(session, codigo)
    if not isinstance(obras, list) or any(not isinstance(o, dict) for o in obras):
        raise ValueError("Respuesta de búsqueda no es una lista de registros")
    candidatos = []
    for obra in obras:
        oid = None
        for clave_id in ("codigoObra", "obraId"):
            try:
                oid = _id_obra(obra.get(clave_id))
                break
            except ConsultaIdentidadInvalida:
                continue
        candidatos.append({
            "obra_id": oid,
            "cui": obra.get("codUniqInv"),
            "snip": obra.get("codSnip"),
            "nombre": obra.get("nombreObra") or obra.get("nombrObra"),
            "url_ficha": f"{infoobras.BASE_WEB}/Mapa/DatosEjecucion?ObraId={oid}" if oid else None,
            "datos_fuente": dict(obra),
        })
    return {
        "estado": "disponible" if candidatos else "sin_resultados",
        "candidatos": candidatos,
        "total_devuelto": len(candidatos),
        "url_consulta": f"{infoobras.BASE_MAPA}/Mapa/busqueda/obrasBasic",
        "limite_consulta_fuente": 20,
        "listado_completo_verificado": False,
        "motivo": "Se muestran los registros devueltos por la consulta; no se certifica exhaustividad del portal.",
    }


def listar_fichas(cui: str) -> dict:
    codigo = _codigo(cui)
    session = None
    try:
        session = infoobras._crear_session()
        return {**_base(codigo), **_candidatos(session, codigo)}
    except Exception as exc:  # fuente externa: estado explícito, sin convertir fallo en lista vacía
        return {**_base(codigo), **_fallo(exc), "candidatos": None}
    finally:
        if session is not None:
            session.close()


class _TextoPagina(HTMLParser):
    """Conserva texto de tablas y enlaces; no ejecuta scripts ni interpreta sus órdenes."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.enlaces = []
        self.omitir = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.omitir += 1
        if self.omitir:
            return
        if tag in {"tr", "p", "div", "br", "h1", "h2", "h3", "h4", "li"}:
            self.partes.append("\n")
        elif tag in {"td", "th"}:
            self.partes.append(" | ")
        atributos = dict(attrs)
        enlace = atributos.get("data-download-url")
        if enlace:
            self.enlaces.append({"url": urljoin(infoobras.BASE_WEB + "/", enlace),
                                 "nombre_fuente": atributos.get("data-nombre"),
                                 "clasificacion": "sin_identificar"})

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.omitir:
            self.omitir -= 1

    def handle_data(self, data):
        if not self.omitir:
            self.partes.append(re.sub(r"\s+", " ", data))


def _leer_pagina(session, oid: int, seccion: str) -> dict:
    url = f"{infoobras.BASE_WEB}/Mapa/{seccion}?ObraId={oid}"
    try:
        respuesta = session.get(url, headers={"Accept": "text/html,*/*"}, timeout=(5, 20))
        respuesta.raise_for_status()
        html = respuesta.text
        lector = _TextoPagina()
        lector.feed(html)
        texto = "\n".join(linea.strip() for linea in "".join(lector.partes).splitlines() if linea.strip())
        # Un HTTP 200 puede ser login, error o una ficha distinta: no llamarlo lectura válida.
        # El portal incluye dos <title>: el genérico del layout y otro interno
        # con el ID. No basta el primero ni un ID incidental en un enlace.
        titulos = re.findall(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        ids_titulo = set()
        for titulo in titulos:
            identidad = re.search(r"\bFICHA\b.*?-\s*([0-9]+)\s*$", titulo, re.I | re.S)
            if identidad:
                ids_titulo.add(int(identidad.group(1)))
        reconocida = ids_titulo == {oid}
        return {"url": url, "estado": "disponible" if reconocida else "formato_no_reconocido",
                "http_status": respuesta.status_code, "obra_id_solicitado": oid,
                "obra_ids_en_titulos": sorted(ids_titulo),
                "texto_visible": texto[:_LIMITE_TEXTO], "caracteres_totales": len(texto),
                "texto_truncado": len(texto) > _LIMITE_TEXTO,
                "documentos_enlazados": lector.enlaces,
                "alcance": "Texto visible y enlaces de esta sección; no incluye contenido de PDFs ni acredita pertinencia documental."}
    except Exception as exc:
        return {"url": url, "obra_id_solicitado": oid, **_fallo(exc)}


def consultar_ficha(cui: str, obra_id: int) -> dict:
    codigo, oid = _codigo(cui), _id_obra(obra_id)
    base = {**_base(codigo), "obra_id_solicitado": oid}
    session = None
    try:
        session = infoobras._crear_session()
        busqueda = _candidatos(session, codigo)
        elegida = next((o for o in busqueda["candidatos"] if o["obra_id"] == oid), None)
        if elegida is None:
            return {**base, "estado": "ficha_no_encontrada_en_consulta", "ficha": None,
                    "busqueda": busqueda, "motivo": "La consulta no incluyó la ficha solicitada; no se sustituyó por otra ni se afirma que no exista."}
        fuentes = [_leer_pagina(session, oid, seccion)
                   for seccion in ("DatosEjecucion", "DatosPreparacion")]
        disponibles = sum(f["estado"] == "disponible" for f in fuentes)
        return {**base, "estado": "disponible" if disponibles == 2 else "parcial" if disponibles else "sin_lectura_de_ficha",
                "ficha": elegida, "fuentes": fuentes,
                "motivo": "Se leyó únicamente el ID solicitado. Las discrepancias se conservan para revisión humana."}
    except Exception as exc:
        return {**base, **_fallo(exc), "ficha": None}
    finally:
        if session is not None:
            session.close()
