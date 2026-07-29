"""Cliente reutilizable del buscador público RENIPRESS de SUSALUD.

La fuente usa una sesión HTTP y una grilla DataTables. Este módulo conserva la
distinción crítica entre una búsqueda válida sin filas y un portal que no
respondió; ningún consumidor debe convertir una caída en «no existe».
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

import requests

logger = logging.getLogger(__name__)

_BASE_PREDETERMINADA = (
    "http://app20.susalud.gob.pe:8080/registro-renipress-webapp/"
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)
_FORM_BASE = {
    "cmb_departamento": "0",
    "cmb_provincia": "0",
    "cmb_distrito": "0",
    "cmb_institucion": "0",
    "cmb_tipo_establecimiento": "0",
    "cmb_clasificacion": "0",
    "cmb_categoria": "0",
    "cmb_unidadEjecutora": "0",
    "cmb_servicio": "0",
    "cmb_autoridadSanitaria": "0",
    "cmb_red": "0",
    "cmb_microRed": "0",
    "cmb_clas": "0",
    "cmb_colegio": "0",
    "cmb_especialidad": "0",
    "cmb_quintil": "0",
    "cmb_telesalud": "0",
}

EstadoConsulta = Literal["encontrado", "sin_resultados", "portal_no_disponible"]
TipoConsulta = Literal["codigo", "ruc", "texto"]


@dataclass(frozen=True)
class EstablecimientoRENIPRESS:
    """Registro estable que se expone a los consumidores del scraper."""

    codigo_unico: str
    nombre_razon_social: str
    ruc: str | None = None
    estado: str | None = None
    condicion: str | None = None
    departamento: str | None = None
    provincia: str | None = None
    distrito: str | None = None
    institucion: str | None = None
    categoria: str | None = None
    coincidencia_exacta: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResultadoRENIPRESS:
    """Resultado explícito; `sin_resultados` nunca representa una caída."""

    estado: EstadoConsulta
    termino: str
    tipo_consulta: TipoConsulta
    solo_activos: bool
    establecimientos: list[EstablecimientoRENIPRESS] = field(default_factory=list)
    total: int = 0
    intentos: int = 1
    detalle_error: str | None = None

    @property
    def ambiguo(self) -> bool:
        exactos = sum(e.coincidencia_exacta for e in self.establecimientos)
        return self.estado == "encontrado" and exactos != 1

    def to_dict(self) -> dict[str, Any]:
        salida = asdict(self)
        salida["ambiguo"] = self.ambiguo
        return salida


def _tipo_consulta(termino: str) -> TipoConsulta:
    digitos = re.sub(r"\D", "", termino)
    if termino.strip().isdigit() and len(digitos) == 11:
        return "ruc"
    if termino.strip().isdigit() and 6 <= len(digitos) <= 10:
        return "codigo"
    return "texto"


def _texto(valor: Any) -> str | None:
    limpio = re.sub(r"\s+", " ", str(valor or "")).strip()
    return limpio or None


def _entero(valor: Any, predeterminado: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return predeterminado


def _config_entero(nombre: str, predeterminado: int) -> int:
    try:
        valor = int((os.getenv(nombre) or "").strip() or predeterminado)
    except ValueError:
        return predeterminado
    return valor if valor > 0 else predeterminado


def _config_float(nombre: str, predeterminado: float) -> float:
    try:
        valor = float((os.getenv(nombre) or "").strip() or predeterminado)
    except ValueError:
        return predeterminado
    return valor if valor > 0 else predeterminado


def _crear_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers.update(
        {"User-Agent": _USER_AGENT, "X-Requested-With": "XMLHttpRequest"}
    )
    return sesion


class ClienteRENIPRESS:
    """Cliente HTTP inyectable y sin estado compartido para RENIPRESS."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        crear_sesion: Callable[[], requests.Session] = _crear_sesion,
        dormir: Callable[[float], None] = time.sleep,
        reintentos: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self._base = (
            base_url
            or os.getenv("PIVOTE_RENIPRESS_URL")
            or _BASE_PREDETERMINADA
        ).rstrip("/") + "/"
        self._crear_sesion = crear_sesion
        self._dormir = dormir
        self._reintentos = max(
            1,
            reintentos
            if reintentos is not None
            else _config_entero("PIVOTE_RENIPRESS_REINTENTOS", 3),
        )
        self._timeout = (
            timeout
            if timeout is not None
            else _config_float("PIVOTE_RENIPRESS_TIMEOUT", 40.0)
        )

    def buscar(
        self,
        termino: str,
        *,
        solo_activos: bool = True,
        max_filas: int = 50,
    ) -> ResultadoRENIPRESS:
        termino = re.sub(r"\s+", " ", str(termino or "")).strip()
        if not termino:
            raise ValueError("El término de búsqueda RENIPRESS no puede estar vacío")
        if not 1 <= max_filas <= 500:
            raise ValueError("max_filas debe estar entre 1 y 500")

        tipo = _tipo_consulta(termino)
        for intento in range(1, self._reintentos + 1):
            try:
                return self._buscar_una_vez(
                    termino, tipo, solo_activos, max_filas, intento
                )
            except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
                logger.warning(
                    "RENIPRESS intento %d/%d falló: %s",
                    intento,
                    self._reintentos,
                    exc,
                )
                if intento < self._reintentos:
                    self._dormir(1.5 * intento)

        return ResultadoRENIPRESS(
            estado="portal_no_disponible",
            termino=termino,
            tipo_consulta=tipo,
            solo_activos=solo_activos,
            intentos=self._reintentos,
            detalle_error=(
                f"RENIPRESS no respondió tras {self._reintentos} intento(s)"
            ),
        )

    def _buscar_una_vez(
        self,
        termino: str,
        tipo: TipoConsulta,
        solo_activos: bool,
        max_filas: int,
        intento: int,
    ) -> ResultadoRENIPRESS:
        sesion = self._crear_sesion()
        form = dict(_FORM_BASE)
        form.update(
            {
                "txt_filtrar": termino,
                "cmb_estado": "1" if solo_activos else "0",
            }
        )
        pagina = self._base + "listadoEstablecimientosRegistrados.htm?action=mostrarBuscar"
        buscar = self._base + "listadoEstablecimientosRegistrados.htm?action=buscarEstablecimientos"
        cargar = self._base + "listadoEstablecimientosRegistrados.htm?action=cargarEstablecimientos"

        respuesta = sesion.get(pagina, timeout=self._timeout)
        respuesta.raise_for_status()
        respuesta = sesion.post(buscar, data=form, timeout=self._timeout)
        respuesta.raise_for_status()
        consulta = {
            **form,
            "draw": "1",
            "start": "0",
            "length": str(max_filas),
        }
        respuesta = sesion.get(cargar, params=consulta, timeout=self._timeout)
        respuesta.raise_for_status()
        cuerpo = re.sub(r'"draw":\s*,', '"draw":1,', respuesta.text)
        datos = json.loads(cuerpo)
        if not isinstance(datos, dict) or not isinstance(datos.get("data"), list):
            raise ValueError("RENIPRESS devolvió una estructura JSON inesperada")

        establecimientos = [
            self._normalizar_fila(fila, termino, tipo)
            for fila in datos["data"]
            if isinstance(fila, dict)
        ]
        total = _entero(
            datos.get("recordsFiltered"),
            _entero(datos.get("recordsTotal"), len(establecimientos)),
        )
        return ResultadoRENIPRESS(
            estado="encontrado" if establecimientos else "sin_resultados",
            termino=termino,
            tipo_consulta=tipo,
            solo_activos=solo_activos,
            establecimientos=establecimientos,
            total=total,
            intentos=intento,
        )

    @staticmethod
    def _normalizar_fila(
        fila: dict[str, Any], termino: str, tipo: TipoConsulta
    ) -> EstablecimientoRENIPRESS:
        codigo = _texto(fila.get("codigounico")) or ""
        ruc = _texto(fila.get("ruc"))
        nombre = _texto(fila.get("nombrerazonsocial")) or ""
        objetivo = {
            "codigo": codigo,
            "ruc": ruc or "",
            "texto": nombre,
        }[tipo]
        return EstablecimientoRENIPRESS(
            codigo_unico=codigo,
            nombre_razon_social=nombre,
            ruc=ruc,
            estado=_texto(fila.get("estado")),
            condicion=_texto(fila.get("condicion")),
            departamento=_texto(fila.get("departamento")),
            provincia=_texto(fila.get("provincia")),
            distrito=_texto(fila.get("distrito")),
            institucion=_texto(fila.get("institucion")),
            categoria=_texto(fila.get("categoria")),
            coincidencia_exacta=objetivo.casefold() == termino.casefold(),
        )


def buscar_renipress(
    termino: str, *, solo_activos: bool = True, max_filas: int = 50
) -> ResultadoRENIPRESS:
    """Atajo para consumidores que no necesitan inyectar transporte."""

    return ClienteRENIPRESS().buscar(
        termino, solo_activos=solo_activos, max_filas=max_filas
    )
