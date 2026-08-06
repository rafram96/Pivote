"""
Bitácora del refresco de la base local del MEF — para que un fallo deje de ser
silencioso (issue #24).

El problema que resuelve: la base MEF se refresca sola (tarea semanal). Si el
refresco falla, **por diseño se conserva la versión anterior** — correcto — pero
hasta ahora nadie se enteraba: los artefactos seguían ahí, `BaseMef` los cargaba
sin protestar y el resolver contestaba con datos viejos con exactamente la misma
cara que si estuvieran frescos. Una obra registrada en el MEF después de la
última corrida buena simplemente NO existe para el sistema, y eso no sale como
error: sale como «no resuelto» o, peor, como un candidato antiguo equivocado.

Dos piezas, ambas sin red:

1. **Escritura** (`registrar_exito` / `registrar_fallo`) — la usa
   `scripts/actualizar_base_mef.py` al terminar cada corrida, con éxito o sin él.
   Escribe `bitacora.json` en la raíz de la carpeta de la base (junto a
   `manifest.json`, NO dentro de `cargas/`: la purga de cargas viejas no debe
   llevarse la memoria de lo que pasó). Escritura atómica (tmp + replace).

2. **Lectura** (`ultima_corrida`, `leer`, `aviso`) — la usan `BaseMef.frescura()`
   y, a través de ella, las tres superficies donde el aviso se ve: el endpoint de
   salud, el buscador de la base (HTTP y consola) y una observación en el
   análisis cuando la resolución corrió con una base vencida.

Regla de oro: **la bitácora nunca rompe nada**. Si no se puede escribir, el ETL
sigue (avisa por consola); si no se puede leer, se responde «no se sabe» en vez
de lanzar. Un problema al anotar no puede ser peor que el problema anotado.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

ARCHIVO = "bitacora.json"

# Cuántas corridas se conservan. Con una tarea semanal, 20 son ~5 meses: alcanza
# para ver si un fallo es un tropiezo aislado o una racha, y el archivo sigue
# cabiendo en una pantalla.
MAX_HISTORIAL = 20

SCHEMA_VERSION = 1


def ruta(dir_base) -> Path:
    return Path(dir_base) / ARCHIVO


# ── escritura ────────────────────────────────────────────────────────────────

def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _corrida_base(inicio: Optional[str], duracion_s: Optional[float]) -> dict:
    return {
        "inicio": inicio or _ahora(),
        "fin": _ahora(),
        "duracion_s": round(float(duracion_s), 1) if duracion_s is not None else None,
    }


def _escribir(dir_base, corrida: dict, *, aviso: Callable[[str], None] = print) -> dict:
    """Fusiona `corrida` en la bitácora y la deja escrita de forma atómica.

    Devuelve la bitácora resultante aunque no se haya podido guardar: quien llama
    ya tiene el dato en la mano y el archivo es el respaldo, no la verdad."""
    datos = leer(dir_base) or {"schema_version": SCHEMA_VERSION, "historial": []}
    datos["schema_version"] = SCHEMA_VERSION
    datos["ultima"] = corrida
    if corrida.get("ok"):
        datos["ultimo_exito"] = corrida
    datos.setdefault("historial", [])
    datos["historial"] = ([corrida] + list(datos["historial"]))[:MAX_HISTORIAL]

    destino = ruta(dir_base)
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, destino)
    except OSError as exc:  # anotar no puede ser más grave que lo anotado
        aviso(f"AVISO: no se pudo escribir la bitácora del MEF ({exc}); "
              f"la corrida sí terminó como dice arriba.")
    return datos


def registrar_exito(dir_base, *, meta: dict, inicio: Optional[str] = None,
                    duracion_s: Optional[float] = None,
                    aviso: Callable[[str], None] = print) -> dict:
    """Anota una actualización que terminó bien, con lo que dejó publicado."""
    corrida = _corrida_base(inicio, duracion_s)
    corrida.update({
        "ok": True,
        "load_id": (meta or {}).get("load_id"),
        "filas_total": (meta or {}).get("filas_total"),
        "cuis_distintos": (meta or {}).get("cuis_distintos"),
        "entidades": (meta or {}).get("entidades"),
        "categoria": None,
        "causa": None,
    })
    return _escribir(dir_base, corrida, aviso=aviso)


def registrar_fallo(dir_base, *, error, inicio: Optional[str] = None,
                    duracion_s: Optional[float] = None,
                    aviso: Callable[[str], None] = print) -> dict:
    """Anota una actualización que NO terminó, con la causa ya clasificada.

    La clasificación reutiliza `scraping/errores_red.clasificar()` (ADR-014), el
    mismo vocabulario con el que el resto del backend explica por qué una fuente
    no contestó: `red` (esta máquina no sale), `portal` (el servidor del MEF), o
    `otro` (validación, disco, PostgreSQL…). Así el operador lee la misma frase
    aquí y en los logs de scraping, en vez de un traceback."""
    from scraping.errores_red import clasificar

    categoria, causa = clasificar(error)
    corrida = _corrida_base(inicio, duracion_s)
    corrida.update({
        "ok": False,
        "load_id": None,
        "filas_total": None,
        "cuis_distintos": None,
        "entidades": None,
        "categoria": categoria,
        "causa": causa,
        "excepcion": type(error).__name__ if isinstance(error, BaseException) else None,
    })
    return _escribir(dir_base, corrida, aviso=aviso)


# ── lectura ──────────────────────────────────────────────────────────────────

def leer(dir_base) -> Optional[dict]:
    """Bitácora completa, o None si no hay (o está ilegible). Nunca lanza."""
    try:
        datos = json.loads(ruta(dir_base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def ultima_corrida(dir_base) -> Optional[dict]:
    """La última actualización intentada, con o sin éxito. None si nunca hubo."""
    datos = leer(dir_base) or {}
    ultima = datos.get("ultima")
    return ultima if isinstance(ultima, dict) else None


# ── redacción del aviso (lenguaje de evaluador, sin jerga) ───────────────────

def _fecha_legible(iso: Optional[str]) -> str:
    texto = str(iso or "")[:10]
    try:
        d = datetime.fromisoformat(texto).date()
    except ValueError:
        return "fecha desconocida"
    return d.strftime("%d/%m/%Y")


def _cola_refresco(refresco: Optional[dict]) -> str:
    if not refresco or refresco.get("ok"):
        return ""
    return (f" El último intento de actualización, del "
            f"{_fecha_legible(refresco.get('fin') or refresco.get('inicio'))}, "
            f"no llegó a completarse: {refresco.get('causa') or 'causa no registrada'}.")


def aviso(estado: str, *, edad_dias: Optional[int], umbral_dias: int,
          refresco: Optional[dict] = None) -> Optional[str]:
    """Frase para mostrarle a una persona, o None si la base está al día.

    Se escribe en palabras de evaluador: qué le falta a la información que está
    viendo y a quién avisar. Nada de «ETL», «artefactos» ni «stale»."""
    if estado == "missing":
        return ("La base de inversiones del MEF no está instalada en este equipo: "
                "no hay contra qué contrastar los proyectos. Avisa al responsable "
                "del servidor.")
    if estado == "invalid":
        return ("No se puede saber de cuándo es la base de inversiones del MEF "
                "(le falta la fecha de su última actualización), así que tampoco "
                "si le faltan obras. Avisa al responsable del servidor." +
                _cola_refresco(refresco))
    if estado == "stale":
        dias = "?" if edad_dias is None else str(edad_dias)
        return (f"La base de inversiones del MEF se actualizó por última vez hace "
                f"{dias} día(s), y lo previsto es como máximo {umbral_dias}. Las "
                f"obras registradas después de esa fecha todavía no aparecen, así "
                f"que una experiencia puede quedar «por confirmar» solo por eso. "
                f"Avisa al responsable del servidor." + _cola_refresco(refresco))
    if estado == "refresco_fallido":
        dias = "?" if edad_dias is None else str(edad_dias)
        return (f"La base de inversiones del MEF todavía está al día ({dias} día(s)), "
                f"pero la actualización automática dejó de funcionar." +
                _cola_refresco(refresco) +
                " Si no se corrige, en pocos días empezará a faltarle obras.")
    return None
