"""Cómo se reintenta una fuente y cómo se dice que no respondió — para TODO el
backend (ADR-014).

Dos piezas, ambas sin red y testeables offline:

1. `clasificar()` / `corto()` — convierten una excepción de red/portal en
   (categoría, mensaje corto en español), para que los logs de scraping dejen de
   escupir la excepción cruda (IncompleteRead con bytes, tracebacks SSL, URLs
   larguísimas).

   Categorías:
     red    → problema del lado del usuario: DNS, SSL/intercepción, sin salida.
     portal → problema del servidor: cortó la descarga, 5xx, timeout.
     otro   → no clasificado (se devuelve un extracto corto).

2. `con_reintentos()` + `Politica` + `Resultado` — el ÚNICO bucle de reintentos
   del backend. Antes había 15 artesanales con 4 fórmulas de backoff y 6 formas
   distintas de decir «el portal no respondió»; cada llamador tenía que conocer
   el dialecto de su fuente.

   La regla que sostiene todo lo demás:

       «la fuente respondió vacío»  ≠  «la fuente no respondió»
        └ dato: no hay                └ incógnita: reintentar o abstenerse

   Confundirlas ya costó un caso real (6:1): una microcaída del portal agotaba
   los intentos en milisegundos, el `[]` resultante se leyó como «no hay obra» y
   el resolver degradó al fragmento genérico. Por eso `Resultado` NO es booleano:
   `if res:` lanza TypeError. La distinción es mecánica, no de disciplina.
"""
from __future__ import annotations

import contextlib
import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

RED = "red"
PORTAL = "portal"
OTRO = "otro"

logger = logging.getLogger(__name__)


def clasificar(e) -> tuple[str, str]:
    """Devuelve (categoria, mensaje_corto en español) para una excepción o cadena."""
    s = str(e)
    low = s.lower()

    # --- RED: tu conexión (DNS / SSL / sin salida) ---
    if "getaddrinfo failed" in low or "failed to resolve" in low or "nameresolution" in low:
        return RED, "sin DNS — no se pudo resolver el dominio (revisa tu internet)"
    if ("certificate_verify_failed" in low or "hostname mismatch" in low
            or "certificateerror" in low or "sslcertverification" in low):
        return RED, "SSL inválido — posible red/proxy interceptando"
    if "sslerror" in low or "[ssl:" in low:
        return RED, "error SSL en la conexión"

    # --- PORTAL: el servidor de InfoObras ---
    m = re.search(r"incompleteread\((\d+) bytes read, (\d+) more expected\)", low)
    if m:
        leido, falta = int(m.group(1)), int(m.group(2))
        tot = (leido + falta) / 1e6
        return PORTAL, f"el portal cortó la transferencia ({leido / 1e6:.1f}/{tot:.1f} MB)"
    if "descarga incompleta" in low:
        return PORTAL, "el portal cortó la descarga antes de terminar"
    if "remotedisconnected" in low or "connection aborted" in low or "connectionreset" in low:
        return PORTAL, "el portal cerró la conexión"
    if "connection broken" in low or "chunkedencoding" in low:
        return PORTAL, "transferencia interrumpida por el portal"
    if "timed out" in low or "timeout" in low:
        return PORTAL, "timeout — el portal no respondió a tiempo"
    m = re.search(r"http (\d{3})", low)
    if m:
        return PORTAL, f"el portal respondió HTTP {m.group(1)}"
    if "max retries exceeded" in low:
        return RED, "no se pudo conectar al portal (sin salida a internet)"

    # --- fallback: extracto corto de una línea ---
    base = s.splitlines()[0].strip() if s.strip() else type(e).__name__
    return OTRO, (base[:88] + "…") if len(base) > 88 else base


def corto(e) -> str:
    """'[categoria] mensaje corto' — para meter directo en un log."""
    cat, msg = clasificar(e)
    return f"[{cat}] {msg}"


# ═══════════════════════════════════════════════════════════════════════════
#  Reintentos: UN solo mecanismo para todas las fuentes (ADR-014)
# ═══════════════════════════════════════════════════════════════════════════

LINEAL = "lineal"
EXPONENCIAL = "exponencial"


class RespuestaTransitoria(OSError):
    """La fuente contestó, pero con algo que NO es una respuesta: 5xx, cuerpo
    vacío, transferencia cortada. Cuenta como caída — se reintenta y, si se
    agotan los intentos, el resultado es «no respondió», nunca «no hay dato».

    Hereda de OSError para que los `except (requests.RequestException, OSError)`
    que ya existían en los bucles migrados la sigan atrapando."""


class Permanente(Exception):
    """Envoltorio: lo de adentro NO se reintenta (un 4xx, una entrada inválida).
    `con_reintentos` relanza de inmediato la excepción original, con su tipo
    intacto. Se usa con el context manager `permanente()`."""

    def __init__(self, original: BaseException) -> None:
        super().__init__(str(original))
        self.original = original


@contextlib.contextmanager
def permanente():
    """`with permanente(): r.raise_for_status()` → un 4xx no se reintenta.

    Envuelve lo que salga del bloque en `Permanente`; el helper lo desenvuelve y
    lo relanza tal cual, sin gastar intentos."""
    try:
        yield
    except Permanente:
        raise
    except BaseException as e:  # noqa: BLE001 — se relanza intacta
        raise Permanente(e) from e


@dataclass(frozen=True)
class Politica:
    """Cuántas veces y cada cuánto se reintenta.

    `modo` LINEAL      → base·(i+1)   (1.5s, 3.0s, 4.5s…)
    `modo` EXPONENCIAL → base·2ⁱ      (1.0s, 2.0s, 4.0s…)
    `jitter` suma `jitter·azar()` — equivale exacto a `random.uniform(0, jitter)`,
    que es como estaba escrito en los bucles artesanales.
    """

    intentos: int = 3
    base: float = 1.5
    modo: str = LINEAL
    jitter: float = 0.0
    tope: Optional[float] = None

    def __post_init__(self) -> None:
        if self.intentos < 1:
            raise ValueError("una política necesita al menos 1 intento")
        if self.base < 0 or self.jitter < 0:
            raise ValueError("base y jitter no pueden ser negativos")
        if self.modo not in (LINEAL, EXPONENCIAL):
            raise ValueError(f"modo desconocido: {self.modo!r}")

    def espera(self, intento: int, azar: Callable[[], float] = random.random) -> float:
        """Segundos a dormir DESPUÉS del intento `intento` (0-based)."""
        d = (self.base * (intento + 1) if self.modo == LINEAL
             else self.base * (2 ** intento))
        if self.tope is not None:
            d = min(d, self.tope)
        return d + (self.jitter * azar() if self.jitter else 0.0)


PREDETERMINADA = Politica()


class _Reintentar:
    """Marca interna: la operación contestó, pero la respuesta no sirve."""

    __slots__ = ("valor_final",)

    def __init__(self, valor_final: Any) -> None:
        self.valor_final = valor_final


def reintentar(valor_final: Any = None) -> _Reintentar:
    """Devuélvelo desde la operación cuando la fuente contestó pero la respuesta
    huele a hipo del portal (el 200-con-lista-vacía de InfoObras).

    Se reintenta; si se agotan los intentos el resultado es **RESPONDIÓ** con
    `valor_final`, porque contestar vacío tres veces seguidas SÍ es un dato."""
    return _Reintentar(valor_final)


@dataclass(frozen=True)
class Resultado:
    """Lo que devuelve `con_reintentos`. Una sola pregunta, sin dialectos:

    - `respondio=True`  → la fuente contestó. `valor` puede venir vacío
      (`[]`, `None`, `False`): eso ES un dato y el llamador puede concluir.
    - `respondio=False` → la fuente no contestó tras agotar los intentos. Es una
      INCÓGNITA: reintentar más tarde o abstenerse. Jamás «no hay».
    """

    respondio: bool
    valor: Any = None
    error: Optional[BaseException] = None
    intentos: int = 0

    def __bool__(self):  # noqa: D105
        raise TypeError(
            "Resultado no es un booleano: «respondió vacío» no es «no respondió». "
            "Usa .respondio (¿contestó la fuente?) o mira .valor (el dato, que "
            "puede venir vacío). Ver ADR-014."
        )

    def valor_o(self, defecto: Any) -> Any:
        """El dato si la fuente contestó; `defecto` si no contestó."""
        return self.valor if self.respondio else defecto

    def relanzar(self, defecto: Optional[BaseException] = None) -> None:
        """No-op si la fuente contestó; si no, relanza el último error (o
        `defecto` si nunca hubo excepción concreta)."""
        if self.respondio:
            return
        err = self.error or defecto or RespuestaTransitoria("la fuente no respondió")
        raise err


def con_reintentos(
    operacion: Callable[[], Any],
    *,
    politica: Politica = PREDETERMINADA,
    etiqueta: str = "",
    excepciones: tuple = (Exception,),
    dormir: Optional[Callable[[float], None]] = None,
    azar: Optional[Callable[[], float]] = None,
    al_reintentar: Optional[Callable[[int, Optional[BaseException]], None]] = None,
    log: Optional[logging.Logger] = None,
    nivel: int = logging.DEBUG,
) -> Resultado:
    """Ejecuta `operacion()` hasta `politica.intentos` veces y clasifica el fallo.

    Reglas (las tres, y no hay más):

    1. **Cualquier valor devuelto es una respuesta definitiva** — incluidos
       `None`, `[]` y `False`. No se reintenta y el `Resultado` dice `respondio`.
    2. Una excepción de `excepciones` **se reintenta**; agotados los intentos el
       `Resultado` dice `respondio=False` (incógnita) con `.error`. Una excepción
       fuera de esa tupla, o envuelta en `Permanente`, **sube de inmediato**.
    3. `reintentar(valor_final)` reintenta; si se agota, el `Resultado` dice
       `respondio=True` con `valor_final` (la fuente sí contestó, aunque vacío).

    `dormir` y `azar` se resuelven en tiempo de llamada, así que un
    `monkeypatch.setattr(modulo.time, "sleep", …)` de los tests sigue valiendo.
    """
    reg = log or logger
    n = politica.intentos
    ultimo_err: Optional[BaseException] = None
    respondio_vacio = False
    valor_vacio: Any = None

    for intento in range(n):
        try:
            salida = operacion()
        except Permanente as envuelta:
            raise envuelta.original      # nunca se reintenta
        except excepciones as e:         # noqa: B902 — la tupla la fija el llamador
            ultimo_err = e
        else:
            if not isinstance(salida, _Reintentar):
                return Resultado(True, salida, None, intento + 1)
            # contestó, pero la respuesta no sirve: se reintenta sin perder que
            # la fuente SÍ estaba viva.
            respondio_vacio = True
            valor_vacio = salida.valor_final
            ultimo_err = None

        if intento < n - 1:
            espera = politica.espera(intento, azar or random.random)
            if al_reintentar is not None:
                al_reintentar(intento + 1, ultimo_err)
            reg.log(
                nivel,
                "%s intento %d/%d: %s — reintento en %.1fs",
                etiqueta or "fuente", intento + 1, n,
                corto(ultimo_err) if ultimo_err is not None
                else "respondió sin dato utilizable",
                espera,
            )
            (dormir if dormir is not None else time.sleep)(espera)

    if respondio_vacio:                  # contestó al menos una vez → es dato
        return Resultado(True, valor_vacio, None, n)
    return Resultado(False, None, ultimo_err, n)
