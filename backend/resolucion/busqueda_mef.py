"""
Buscador de inversiones sobre la base local del MEF — núcleo compartido.

Lo consumen DOS bocas, que no deben divergir nunca:

  · el endpoint HTTP  `GET /api/pivote/mef/buscar`   (api/app.py)
  · el CLI de soporte `python -m scripts.buscar_mef`  (scripts/buscar_mef.py)

Qué hace: recibe un texto (nombre de la obra, o directamente un CUI/SNIP) y
devuelve los mejores candidatos de la base local (`resolucion/base_mef.py`),
con filtros geográficos y por entidad. Todo ocurre en esta máquina: cero red,
cero captchas.

Reglas del contrato (deliberadas, no accidentes):

1. **Un código exacto gana.** Si el texto es sólo dígitos y coincide con un CUI
   o un SNIP de la base, se devuelve ESA ficha (`coincidencia: "codigo"`). Si el
   número no existe como código, se sigue buscando por nombre — hay obras cuyo
   nombre contiene números ("I.E. N° 1452").
2. **Los filtros se aplican siempre**, también sobre el acierto por código. Un
   CUI de Huánuco con `--dpto lima` devuelve cero resultados, y eso es la
   respuesta correcta, no un error.
3bis. **Si la base está vencida, se dice en la respuesta.** `base_desactualizada`
   + `aviso_frescura` (issue #24): quien consulta tiene derecho a saber que la
   lista que está mirando se armó con datos de hace semanas, porque una obra
   registrada después no va a aparecer y la ausencia se lee igual que un «no
   existe». Van en campos aparte de `aviso`, que es para lo que el usuario
   escribió mal.

3. **La base ausente no es un error del que pregunta.** Si los artefactos no
   están instalados se responde 200 con `base_mef_no_disponible: true` y un
   aviso en castellano; jamás un traceback ni un 500. Un integrador distingue
   "no hay base" de "no hay resultados" mirando esa bandera, no adivinando por
   la lista vacía.
4. **NO toca el resolver de CUI** (`resolucion/cui.py`): esto es una consulta de
   consulta, no una resolución de identidad. Quien decide qué obra corresponde a
   un certificado sigue siendo el resolver, con InfoObras de decisor.

Rendimiento (medido sobre la base real, 620.985 filas / 579.481 CUIs, laptop de
dev): un código exacto responde en ~15 ms; un nombre acotado, en decenas de ms;
un nombre amplio como «hospital abancay» une decenas de miles de candidatos y
tarda ~0,25-0,6 s. La respuesta incluye `ms` —lo que tardó ESA llamada— para que
esto sea comprobable en vez de prometido. Ojo: la PRIMERA consulta de un proceso
paga además la carga perezosa del índice (~65-90 s) y su `ms` lo refleja; a
partir de ahí el índice queda en RAM. En el servidor eso lo absorbe el primer
análisis del día.
"""
from __future__ import annotations

import time
from typing import Optional

from resolucion.texto import norm

LIMITE_DEFECTO = 10
LIMITE_MAX = 50
Q_MIN = 2
Q_MAX = 200

# Sobre-pedido al índice: se traen más candidatos de los pedidos para que los
# filtros tengan de dónde descartar. El scoring ya se hizo sobre todo el
# subconjunto, así que pedir de más sólo cambia dónde se corta la lista.
_FACTOR_SOBRE_PEDIDO = 10
_TOPN_MAX = 500

AVISO_SIN_BASE = (
    "La base local de inversiones del MEF no está instalada en este equipo, "
    "así que no hay dónde buscar. Instálala con "
    "«python scripts/actualizar_base_mef.py» y vuelve a consultar."
)

AVISO_TEXTO_GENERICO = (
    "El texto es demasiado genérico: todas sus palabras («salud», «mejoramiento», "
    "«servicios»…) aparecen en decenas de miles de inversiones. Agrega el nombre "
    "propio del establecimiento o de la localidad."
)


class ConsultaInvalida(ValueError):
    """Lo que pidió el usuario no se puede buscar (texto muy corto, límite fuera
    de rango). Quien llama la traduce a 400 (HTTP) o a un mensaje del CLI."""


def _base_por_defecto():
    """Indirecto a propósito: los tests lo sustituyen por una base de fixtures
    para no cargar el medio millón de filas reales."""
    from resolucion.base_mef import instancia
    return instancia()


def _ubicacion(ficha: dict) -> str:
    partes = [str(ficha.get(k) or "").strip() for k in ("dist", "prov", "dpto")]
    return ", ".join(p for p in partes if p)


def _resultado(ficha: dict, score: Optional[float]) -> dict:
    """Proyección estable de la ficha: lo que el evaluador necesita ver, con los
    nombres de campo del contrato. Se ignoran las columnas internas de la base."""
    return {
        "cui": ficha.get("cui") or None,
        "snip": ficha.get("snip") or None,
        "nombre": ficha.get("nombre") or None,
        "dpto": ficha.get("dpto") or None,
        "prov": ficha.get("prov") or None,
        "dist": ficha.get("dist") or None,
        "ubigeo": ficha.get("ubigeo") or None,
        "ubicacion": _ubicacion(ficha) or None,
        "entidad": ficha.get("entidad") or None,
        "estado": ficha.get("estado_dataset") or None,
        "situacion": ficha.get("situacion") or None,
        "score": score,
    }


def _filtros_normalizados(dpto, prov, dist, entidad) -> dict:
    crudos = {"dpto": dpto, "prov": prov, "dist": dist, "entidad": entidad}
    return {k: str(v).strip() for k, v in crudos.items() if str(v or "").strip()}


def _coincide(ficha: dict, filtros: dict) -> bool:
    """Un filtro pasa si su texto normalizado está CONTENIDO en el campo: así
    «huanuco» encuentra HUANUCO y «gobierno regional» encuentra GOBIERNO
    REGIONAL DE HUANUCO, sin obligar a escribir el nombre exacto."""
    for campo, valor in filtros.items():
        if norm(valor) not in norm(str(ficha.get(campo) or "")):
            return False
    return True


def _validar(q: str, limite: int) -> tuple[str, int]:
    texto = str(q or "").strip()
    if not Q_MIN <= len(texto) <= Q_MAX:
        raise ConsultaInvalida(
            f"q debe tener entre {Q_MIN} y {Q_MAX} caracteres")
    try:
        n = int(limite)
    except (TypeError, ValueError):
        raise ConsultaInvalida(
            f"limite debe ser un número entre 1 y {LIMITE_MAX}") from None
    if not 1 <= n <= LIMITE_MAX:
        raise ConsultaInvalida(f"limite debe estar entre 1 y {LIMITE_MAX}")
    return texto, n


def buscar(
    q: str,
    *,
    dpto: str = "",
    prov: str = "",
    dist: str = "",
    entidad: str = "",
    limite: int = LIMITE_DEFECTO,
    base=None,
) -> dict:
    """Busca inversiones en la base local del MEF. Ver el encabezado del módulo
    para las cuatro reglas del contrato.

    Devuelve siempre un dict con la misma forma:
        {q, filtros, limite, coincidencia, base_mef_no_disponible, aviso,
         edad_dias, base_desactualizada, aviso_frescura, ms, total, resultados[]}
    Lanza `ConsultaInvalida` sólo por lo que el usuario escribió mal.
    """
    t0 = time.perf_counter()
    r = _buscar(q, dpto=dpto, prov=prov, dist=dist, entidad=entidad,
                limite=limite, base=base)
    r["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return r


def _buscar(q, *, dpto, prov, dist, entidad, limite, base) -> dict:
    texto, n = _validar(q, limite)
    filtros = _filtros_normalizados(dpto, prov, dist, entidad)
    base = base if base is not None else _base_por_defecto()

    respuesta = {
        "q": texto,
        "filtros": filtros,
        "limite": n,
        "coincidencia": None,
        "base_mef_no_disponible": False,
        "aviso": None,
        "edad_dias": None,
        "base_desactualizada": False,
        "aviso_frescura": None,
        "ms": None,
        "total": 0,
        "resultados": [],
    }

    if not base.disponible():
        respuesta["base_mef_no_disponible"] = True
        respuesta["aviso"] = AVISO_SIN_BASE
        return respuesta

    # Frescura (issue #24). Va en campos PROPIOS, no en `aviso`: «tu consulta no
    # se puede resolver» y «lo que estás consultando puede estar incompleto» son
    # cosas distintas y una no debe tapar a la otra. `frescura()` no toca
    # PostgreSQL ni el índice, así que se puede pagar en cada búsqueda.
    fr = base.frescura()
    respuesta["edad_dias"] = fr["edad_dias"]
    respuesta["base_desactualizada"] = fr["estado"] != "ok"
    respuesta["aviso_frescura"] = fr["mensaje"]

    # 1 · código exacto (CUI o SNIP)
    if texto.isdigit():
        ficha = base.existe_cui(texto)
        if ficha:
            elegidos = [_resultado(ficha, 100.0)] if _coincide(ficha, filtros) else []
            respuesta.update(coincidencia="codigo", total=len(elegidos),
                             resultados=elegidos)
            return respuesta

    # 2 · nombre (difuso)
    from resolucion.base_mef import tokens_discriminantes

    respuesta["coincidencia"] = "nombre"
    if not tokens_discriminantes(texto):
        respuesta["aviso"] = AVISO_TEXTO_GENERICO
        return respuesta
    topn = min(_TOPN_MAX, max(n * _FACTOR_SOBRE_PEDIDO, 50))
    candidatos = base.buscar_candidatos(texto, topn=topn)
    elegidos = [_resultado(f, f.get("score")) for f in candidatos
                if _coincide(f, filtros)][:n]
    respuesta.update(total=len(elegidos), resultados=elegidos)
    return respuesta
