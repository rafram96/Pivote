"""Cronómetro de etapa: tiempo de pared por experiencia, por fuente y por fase.

Nace de la corrida Muraria del 6-sep-2026 (job c9751ee5d3d5): la etapa
infoobras tardó 51,8 min y los artefactos no permitían saber dónde. Las
descargas fueron instantáneas, las cachés de OCR y MEF ahorran ~2 min, y 38 min
quedaron en dos huecos sin ninguna escritura en disco (medido por las marcas
NTFS de creación/escritura de cada archivo). Sin medición por experiencia y por
fuente, cualquier optimización se evalúa a ciegas.

Puro y sin red: la etapa lo alimenta con `experiencia()`, `medir()` y `fase()`,
lo persiste en el enriquecimiento (`tiempos_s`) y lo resume en una observación
TIEMPOS del job. El reloj es inyectable para las pruebas.
"""
from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Callable, Iterator, Optional


def _fmt(segundos: float) -> str:
    return f"{segundos:.1f} s" if segundos < 90 else f"{segundos / 60:.1f} min"


def _legible(clave: str) -> str:
    """`"2:7"` → `"P2 E7"`; cualquier otra clave se devuelve tal cual."""
    if ":" in clave:
        a, _, b = clave.partition(":")
        if a.isdigit() and b.isdigit():
            return f"P{a} E{b}"
    return clave


class Cronometro:
    """Acumula segundos por experiencia (`experiencia`), por fuente (`medir`) y
    por fase (`fase`). Una medición de fuente dentro de una experiencia se
    apunta a ambas; fuera de toda experiencia, solo a la fuente."""

    def __init__(self, reloj: Callable[[], float] = perf_counter) -> None:
        self._reloj = reloj
        self.actual: Optional[str] = None
        self.por_experiencia: dict[str, dict[str, float]] = {}
        self.por_fuente: dict[str, list[float]] = {}     # fuente → [segundos, llamadas]
        self.fases: dict[str, float] = {}

    @contextmanager
    def experiencia(self, clave: str) -> Iterator[None]:
        previa, self.actual = self.actual, clave
        t0 = self._reloj()
        try:
            yield
        finally:
            d = self._reloj() - t0
            e = self.por_experiencia.setdefault(clave, {})
            e["total"] = e.get("total", 0.0) + d
            self.actual = previa

    @contextmanager
    def medir(self, fuente: str) -> Iterator[None]:
        t0 = self._reloj()
        try:
            yield
        finally:
            d = self._reloj() - t0
            f = self.por_fuente.setdefault(fuente, [0.0, 0])
            f[0] += d
            f[1] += 1
            if self.actual is not None:
                e = self.por_experiencia.setdefault(self.actual, {})
                e[fuente] = e.get(fuente, 0.0) + d

    @contextmanager
    def fase(self, nombre: str) -> Iterator[None]:
        t0 = self._reloj()
        try:
            yield
        finally:
            self.fases[nombre] = self.fases.get(nombre, 0.0) + (self._reloj() - t0)

    def tiempos_de(self, clave: str) -> dict[str, float]:
        return {k: round(v, 2) for k, v in (self.por_experiencia.get(clave) or {}).items()}

    def mas_lentas(self, n: int = 5) -> list[tuple[str, float]]:
        pares = ((k, v.get("total", 0.0)) for k, v in self.por_experiencia.items())
        return sorted(pares, key=lambda x: -x[1])[:n]

    def linea_experiencia(self, clave: str) -> str:
        """`P2 E7: 1740.3 s (mef 1700.0 s · resolucion 30.2 s)` — para el log."""
        t = self.por_experiencia.get(clave) or {}
        detalle = " · ".join(f"{k} {_fmt(v)}" for k, v in t.items() if k != "total")
        return f"{_legible(clave)}: {_fmt(t.get('total', 0.0))}" + (f" ({detalle})" if detalle else "")

    def resumen(self, top: int = 5) -> str:
        partes = []
        if self.fases:
            partes.append("fases: " + " · ".join(f"{k} {_fmt(v)}" for k, v in self.fases.items()))
        if self.por_fuente:
            orden = sorted(self.por_fuente.items(), key=lambda x: -x[1][0])
            partes.append("fuentes: " + " · ".join(
                f"{k} {_fmt(s)} ({int(n)} llamadas)" for k, (s, n) in orden))
        lentas = [(k, s) for k, s in self.mas_lentas(top) if s >= 1.0]
        if lentas:
            partes.append("experiencias más lentas: " + ", ".join(
                f"{_legible(k)} {_fmt(s)}" for k, s in lentas))
        return "; ".join(partes) or "sin mediciones"
