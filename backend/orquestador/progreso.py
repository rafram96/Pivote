"""
Progreso FINO del pipeline — en memoria, volátil a propósito.

El checkpoint por etapa (persistente, en el `Job`) da el avance GRUESO: 1/8 por
etapa. Pero una etapa larga (RESOLUCION_CUI, INFOOBRAS, SUNAT) itera por
experiencia — 49+ en Lircay — y puede pasar minutos sin señal. Este registro da
el avance DENTRO de la etapa ("obra 12 de 49") sin tocar disco: las etapas
reportan por ítem y la API lo lee para pintar la barra.

Volátil por diseño: si el proceso muere, el job reanuda por checkpoints y este
progreso se reconstruye solo cuando la etapa vuelve a correr. NUNCA es la fuente
de verdad (esa es el checkpoint) — solo un espejo de "qué está pasando ahora".

Concurrencia: INFOOBRAS ∥ SUNAT corren a la vez, así que el registro es
`{job_id: {etapa: EtapaViva}}` — dos entradas simultáneas por job, nunca una
sola. Thread-safe con un lock (igual patrón de proceso único que `_SALUD_CACHE`
en la API).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class EtapaViva:
    """Snapshot del avance de UNA etapa en curso para UN job."""
    etapa: str            # valor del enum Etapa (str) — o pseudo-etapa "descargas"
    item_actual: int      # 1-based; 0 = etapa sin ítems discretos (validacion/reglas)
    items_total: int
    descripcion: str      # texto SIN jerga, ya listo para el panel
    actualizado_en: float # time.monotonic() — para el TTL de purga


class RegistroProgreso:
    """Singleton de proceso. `reportar()` desde las etapas; `etapas()` desde la API."""

    _TTL_S = 3600.0   # un job terminado se purga tras 1 h por si el panel llega tarde

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, EtapaViva]] = {}

    def reportar(self, job_id: str, etapa: str, item_actual: int,
                 items_total: int, descripcion: str) -> None:
        """La llaman las etapas al iniciar cada ítem. Barata: solo escribe memoria."""
        with self._lock:
            self._jobs.setdefault(job_id, {})[etapa] = EtapaViva(
                etapa=etapa, item_actual=item_actual, items_total=items_total,
                descripcion=descripcion, actualizado_en=time.monotonic())

    def etapas(self, job_id: str) -> dict[str, dict]:
        """`{etapa: {item_actual, items_total, descripcion}}` — lo que consume la API.
        Copia defensiva: el consumidor no ve el `EtapaViva` mutable interno."""
        with self._lock:
            return {
                k: {"item_actual": v.item_actual, "items_total": v.items_total,
                    "descripcion": v.descripcion}
                for k, v in self._jobs.get(job_id, {}).items()
            }

    def limpiar(self, job_id: str) -> None:
        """Olvida un job (al terminar el pipeline + descargas). Idempotente."""
        with self._lock:
            self._jobs.pop(job_id, None)

    def purgar_viejos(self) -> None:
        """Descarta jobs cuyas etapas no se tocan hace > TTL (red de seguridad: un
        crash sin `limpiar()` no deja memoria colgada para siempre)."""
        ahora = time.monotonic()
        with self._lock:
            for jid in list(self._jobs):
                etapas = self._jobs[jid]
                if etapas and all(ahora - v.actualizado_en > self._TTL_S
                                  for v in etapas.values()):
                    self._jobs.pop(jid, None)


# Instancia única de proceso (como el motor y el repo en api/app.py).
REGISTRO = RegistroProgreso()
