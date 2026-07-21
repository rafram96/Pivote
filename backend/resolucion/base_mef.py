"""
Base local de inversiones del MEF — consulta en memoria para el resolver de CUI.

Carga los artefactos que produce `scripts/actualizar_base_mef.py`
(`inversiones.csv.gz`, `entidades_publicas.csv`, `metadata.json`) y ofrece:

  buscar_candidatos(nombre)  → CUIs cuyo nombre de inversión se parece al dado
  existe_cui(codigo)         → ficha de un CUI o SNIP exacto
  es_entidad_publica(nombre) → ¿el nombre corresponde a una entidad del Estado?

Diseño de memoria: columnas en listas paralelas + `sys.intern` en los campos de
baja cardinalidad (dpto/prov/dist/situacion/estado/entidad/ubigeo) + `array('i')`
en las listas de posteo del índice invertido. Objetivo < 500 MB para ~490k filas.

La búsqueda por nombre usa un índice invertido token→filas (sin stopwords ni
tokens cortos): se une el posteo de los ~6 tokens más RAROS de la consulta y se
puntúa ese subconjunto con `rapidfuzz.token_set_ratio`. Así una consulta toca
decenas de miles de nombres, no el medio millón completo.

Si los artefactos no existen, `disponible()` es False y todos los métodos
devuelven vacío/None sin lanzar (el resolver sigue con InfoObras en vivo).
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import sys
import threading
from array import array
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from resolucion.texto import norm

csv.field_size_limit(10_000_000)


# Tokens que NO discriminan una inversión (aparecen en decenas de miles de nombres).
# Excluirlos del índice y de la consulta evita unir posteos gigantes y ruido. Set
# validado empíricamente contra las 1042 experiencias reales (scratchpad F1).
_STOP = frozenset("""
DE DEL LA LAS EL LOS Y EN A CON PARA POR DISTRITO PROVINCIA DEPARTAMENTO REGION
LOCALIDAD CENTRO POBLADO SALUD PUESTO EDUCATIVA INSTITUCION IE I E N NO S SERVICIO
SERVICIOS MEJORAMIENTO AMPLIACION CONSTRUCCION CREACION RECUPERACION INSTALACION
""".split())

_RE_ALNUM = re.compile(r"[A-Z0-9]+")

# Tope de posteo por token: un token con más apariciones que esto es demasiado
# común para acotar la búsqueda; se salta al elegir los tokens raros de la consulta.
_MAX_POSTEO_TOKEN = 20_000
# Corte de candidatos acumulados: más allá, la unión ya no ayuda a la precisión y
# sí encarece el scoring.
_MAX_CANDIDATOS = 60_000
_SCORE_MIN = 60


def _limpiar(s: str) -> str:
    """Normaliza (norm) y colapsa la puntuación de los nombres MEF a espacios.

    Los nombres del Banco de Inversiones traen comas, guiones y paréntesis que,
    pegados a un token ('SALUD,', '(CHINCHINGA'), rompen el match exacto del índice
    invertido. Se limpian aquí; norm() de `texto.py` no toca puntuación a propósito
    (lo comparte con el resolver de certificados), así que la limpieza vive donde
    hace falta. Reproduce el normalizador con el que se validó la base (score ~100
    en el caso Chinchinga)."""
    return " ".join(_RE_ALNUM.findall(norm(s)))


def _tokens(nombre_norm: str) -> list[str]:
    return [t for t in nombre_norm.split() if len(t) > 2 and t not in _STOP]


class BaseMef:
    """Base de inversiones cargada en memoria (carga perezosa)."""

    def __init__(self, dir_base: Path):
        self._dir = Path(dir_base)
        self._cargada = False
        self._lock = threading.Lock()
        # columnas paralelas
        self._cui: list[str] = []
        self._snip: list[str] = []
        self._nombre: list[str] = []
        self._nombre_norm: list[str] = []
        self._estado: list[str] = []
        self._situacion: list[str] = []
        self._ubigeo: list[str] = []
        self._dpto: list[str] = []
        self._prov: list[str] = []
        self._dist: list[str] = []
        self._entidad: list[str] = []
        # índices
        self._por_cui: dict[str, int] = {}
        self._por_snip: dict[str, int] = {}
        self._tok_index: dict[str, array] = {}
        # entidades públicas
        self._entidades: list[str] = []
        self._siglas: set[str] = set()
        self._meta: dict = {}

    # ── archivos ─────────────────────────────────────────────────────────────

    @property
    def _f_inv(self) -> Path:
        return self._dir / "inversiones.csv.gz"

    @property
    def _f_ent(self) -> Path:
        return self._dir / "entidades_publicas.csv"

    @property
    def _f_meta(self) -> Path:
        return self._dir / "metadata.json"

    def disponible(self) -> bool:
        """True si los 3 artefactos existen y son legibles."""
        try:
            return (self._f_inv.is_file() and self._f_ent.is_file()
                    and self._f_meta.is_file())
        except OSError:
            return False

    def edad_dias(self) -> Optional[int]:
        """Días desde la fecha registrada en metadata.json (None si no hay base)."""
        if not self._f_meta.is_file():
            return None
        try:
            from datetime import date
            meta = json.loads(self._f_meta.read_text(encoding="utf-8"))
            f = date.fromisoformat(str(meta.get("fecha"))[:10])
            return (date.today() - f).days
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    # ── carga ────────────────────────────────────────────────────────────────

    def _asegurar_cargada(self) -> bool:
        if self._cargada:
            return True
        if not self.disponible():
            return False
        with self._lock:
            if self._cargada:
                return True
            self._cargar()
            self._cargada = True
        return True

    def _cargar(self) -> None:
        intern = sys.intern
        tok_tmp: dict[str, array] = {}
        with gzip.open(self._f_inv, "rt", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for fila in r:
                i = len(self._cui)
                cui = (fila.get("cui") or "").strip()
                snip = (fila.get("snip") or "").strip()
                nombre = fila.get("nombre") or ""
                nnorm = _limpiar(nombre)
                self._cui.append(cui)
                self._snip.append(snip)
                self._nombre.append(nombre)
                self._nombre_norm.append(nnorm)
                self._estado.append(intern(fila.get("estado_dataset") or ""))
                self._situacion.append(intern(fila.get("situacion") or ""))
                self._ubigeo.append(intern(fila.get("ubigeo") or ""))
                self._dpto.append(intern(fila.get("dpto") or ""))
                self._prov.append(intern(fila.get("prov") or ""))
                self._dist.append(intern(fila.get("dist") or ""))
                self._entidad.append(intern(fila.get("entidad") or ""))
                if cui and cui not in self._por_cui:
                    self._por_cui[cui] = i
                if snip and snip not in self._por_snip:
                    self._por_snip[snip] = i
                for t in set(_tokens(nnorm)):
                    post = tok_tmp.get(t)
                    if post is None:
                        post = tok_tmp[t] = array("i")
                    post.append(i)
        self._tok_index = tok_tmp
        self._cargar_entidades()

    def _cargar_entidades(self) -> None:
        with open(self._f_ent, encoding="utf-8", newline="") as f:
            for fila in csv.DictReader(f):
                ent = (fila.get("entidad") or "").strip()
                sig = (fila.get("sigla") or "").strip()
                if ent:
                    self._entidades.append(ent)
                if sig:
                    self._siglas.add(sig)

    # ── consultas ────────────────────────────────────────────────────────────

    def buscar_candidatos(self, nombre: str, topn: int = 10) -> list[dict]:
        if not self._asegurar_cargada():
            return []
        q = _limpiar(nombre)
        if not q:
            return []
        # tokens de la consulta ordenados por RAREZA (posteo más corto primero)
        toks = sorted(set(_tokens(q)),
                      key=lambda t: len(self._tok_index.get(t, ())) or 10 ** 9)
        cand: set[int] = set()
        for t in toks[:6]:
            post = self._tok_index.get(t)
            if not post or len(post) > _MAX_POSTEO_TOKEN:
                continue
            cand.update(post)
            if len(cand) > _MAX_CANDIDATOS:
                break
        if not cand:
            return []
        scored = []
        for i in cand:
            sc = fuzz.token_set_ratio(q, self._nombre_norm[i])
            if sc >= _SCORE_MIN:
                scored.append((sc, i))
        # orden determinístico: score desc, desempate por CUI (y por índice)
        scored.sort(key=lambda x: (-x[0], self._cui[x[1]] or "~", x[1]))
        return [self._ficha(i, round(float(sc), 1)) for sc, i in scored[:topn]]

    def existe_cui(self, codigo: str) -> Optional[dict]:
        if not self._asegurar_cargada():
            return None
        c = str(codigo or "").strip()
        if not c:
            return None
        i = self._por_cui.get(c)
        if i is None:
            i = self._por_snip.get(c)
        return self._ficha(i) if i is not None else None

    def es_entidad_publica(self, nombre: str) -> tuple[bool, float]:
        if not self._asegurar_cargada():
            return (False, 0.0)
        q = norm(nombre)
        if not q:
            return (False, 0.0)
        if q in self._siglas:
            return (True, 100.0)
        mejor = 0.0
        for ent in self._entidades:
            s = fuzz.token_set_ratio(q, ent)
            if s > mejor:
                mejor = s
                if mejor >= 100:
                    break
        # 90 es umbral DURO: "ORDEN DE SAN AGUSTIN" matchea ~82 con municipalidades
        # de San Agustín y NO debe pasar como entidad pública.
        return (mejor >= 90, round(float(mejor), 1))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _ficha(self, i: int, score: Optional[float] = None) -> dict:
        d = {
            "cui": self._cui[i],
            "snip": self._snip[i],
            "nombre": self._nombre[i],
            "ubigeo": self._ubigeo[i],
            "dpto": self._dpto[i],
            "prov": self._prov[i],
            "dist": self._dist[i],
            "entidad": self._entidad[i],
            "estado_dataset": self._estado[i],
            "situacion": self._situacion[i],
        }
        if score is not None:
            d["score"] = score
        return d

    def memoria_mb(self) -> float:
        """Estimación (MB) de la RAM de las estructuras cargadas. O(n); es un helper
        de diagnóstico, no de la ruta caliente."""
        total = 0
        listas_str = (self._cui, self._snip, self._nombre, self._nombre_norm,
                      self._estado, self._situacion, self._ubigeo, self._dpto,
                      self._prov, self._dist, self._entidad, self._entidades)
        vistos: set[int] = set()
        for lst in listas_str:
            total += sys.getsizeof(lst)
            for s in lst:
                oid = id(s)
                if oid not in vistos:      # no doble-contar strings interned/repetidos
                    vistos.add(oid)
                    total += sys.getsizeof(s)
        total += sys.getsizeof(self._por_cui) + sys.getsizeof(self._por_snip)
        total += sys.getsizeof(self._tok_index)
        for t, post in self._tok_index.items():
            total += sys.getsizeof(t) + post.buffer_info()[1] * post.itemsize + sys.getsizeof(post)
        return round(total / (1024 * 1024), 1)


# ── singleton ────────────────────────────────────────────────────────────────

_instancia: Optional[BaseMef] = None
_lock_singleton = threading.Lock()


def _dir_por_defecto() -> Path:
    from config import data_dir
    return data_dir() / "referencia" / "mef"


def instancia(dir_base: Optional[Path] = None) -> BaseMef:
    """Devuelve la BaseMef compartida (carga perezosa en el primer uso). Con
    `dir_base` explícito crea/retorna una instancia apuntando a esa carpeta —
    pensado para tests con fixtures."""
    global _instancia
    if dir_base is not None:
        return BaseMef(dir_base)
    if _instancia is None:
        with _lock_singleton:
            if _instancia is None:
                _instancia = BaseMef(_dir_por_defecto())
    return _instancia
