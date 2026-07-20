"""
traza.py — Tracing estructurado del pipeline, on-prem y sin dependencias.

Cada evento es UNA LÍNEA JSONL en el archivo de traza del job (carpeta por job,
igual que el espejo). El visor `visor_traza.html` (autocontenido, arrastrar y
soltar) lo pinta como línea de tiempo. El módulo es GENÉRICO: no sabe nada de
InfoObras — reutilizable en cualquier proyecto Python.

Esquema de evento (campos base + atributos libres):
    {"ts": "...", "trace": "<job>", "ev": "<nombre>", "en": "<span/padre>",
     "ms": 12.3, ...atributos}
  · "ev":"span"  = un bloque medido (with traza.span(...)) con su duración
  · "ev":"error" = excepción dentro de un span (se re-lanza; la traza no traga)
  · cualquier otro "ev" = evento puntual

Uso:
    from observabilidad.traza import Traza, usar, actual

    t = Traza(carpeta_job / "traza.jsonl", trace_id=job_id)
    token = usar(t)                      # activa para este contexto/tarea
    ...
    tr = actual()                        # en cualquier módulo instrumentado
    with tr.span("resolver_cui", clave="11:1"):
        tr.ev("busqueda", fuente="infoobras", hits=7, ms=840)
    ...
    restaurar(token)                     # (opcional) desactiva

Sin tracer activo, `actual()` devuelve un no-op: la instrumentación cuesta
nanosegundos y jamás rompe el pipeline (escribir la traza nunca lanza).
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional

_actual: ContextVar[Optional["Traza"]] = ContextVar("traza_actual", default=None)
_pila: ContextVar[tuple] = ContextVar("traza_pila", default=())


class Traza:
    """Tracer JSONL append-only, thread-safe. Un archivo por trace (job)."""

    def __init__(self, destino: Path | str, trace_id: str = ""):
        self._path = Path(destino)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.trace_id = trace_id

    # ── evento puntual ───────────────────────────────────────────────────────
    def ev(self, evento: str, **attrs) -> None:
        self._write({"ev": evento, **attrs})

    # ── bloque medido (con duración y jerarquía) ─────────────────────────────
    @contextmanager
    def span(self, nombre: str, **attrs):
        t0 = time.perf_counter()
        pila = _pila.get()
        token = _pila.set(pila + (nombre,))
        try:
            yield self
        except Exception as e:  # noqa: BLE001 — se registra y SE RE-LANZA
            self._write({"ev": "error", "span": "/".join(pila + (nombre,)),
                         "error": f"{type(e).__name__}: {e}"[:200], **attrs,
                         "ms": round((time.perf_counter() - t0) * 1000, 1)})
            raise
        else:
            self._write({"ev": "span", "span": "/".join(pila + (nombre,)),
                         **attrs, "ms": round((time.perf_counter() - t0) * 1000, 1)})
        finally:
            _pila.reset(token)

    # ── interno ──────────────────────────────────────────────────────────────
    def _write(self, d: dict) -> None:
        try:
            base: dict = {"ts": datetime.now().isoformat(timespec="milliseconds")}
            if self.trace_id:
                base["trace"] = self.trace_id
            pila = _pila.get()
            if pila and "span" not in d:
                d.setdefault("en", "/".join(pila))
            linea = json.dumps({**base, **d}, ensure_ascii=False, default=str)
            with self._lock, open(self._path, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
        except Exception:  # noqa: BLE001 — la traza JAMÁS rompe el pipeline
            pass


class _TrazaNula:
    """No-op: instrumentar es gratis cuando no hay tracer activo."""

    def ev(self, *a, **k) -> None:  # noqa: D102
        pass

    @contextmanager
    def span(self, *a, **k):  # noqa: D102
        yield self


NULA = _TrazaNula()


def usar(t: Traza):
    """Activa `t` como tracer del contexto actual. Devuelve token para restaurar."""
    return _actual.set(t)


def restaurar(token) -> None:
    _actual.reset(token)


def actual() -> "Traza | _TrazaNula":
    return _actual.get() or NULA
