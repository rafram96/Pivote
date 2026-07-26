"""
Candado determinístico de correspondencia CARGO ↔ BASES (issue #31).

El problema: `cargo_bases_valido` lo juzga SOLO el LLM (`agent-evaluador`), que
matchea por **tokens compartidos** y da falsos CUMPLE. Caso real (Comité,
2026-07-25, huachocolpa P4 «Especialista en Planeamiento y Costos»):
«Especialista en Costos, Metrados y Valorizaciones» comparte COSTOS con el cargo
exigido → el LLM escribió "SÍ" y el sistema pintó verde, cuando el Comité lo
declaró NO CUMPLE por no reunir el núcleo completo.

La regla del Comité (`.ai/context/business_rules.md`, «Cargo declarado vs cargo
exigido»): la lista de cargos válidos varía solo en el **sustantivo inicial**
(especialista / responsable / encargado / ingeniero / inspector…); el **núcleo de
especialidad es obligatorio y compuesto** — «planeamiento **y** costos» exige
AMBOS términos. Segunda puerta: si el título no acredita, solo salva un documento
que liste FUNCIONES; un certificado que únicamente dice «desempeñando el cargo de
X, del … al …, en la obra Y» NO las acredita.

Semántica de `cargos_similares_validos` (verificada en 35 espejos reales, 322
profesionales): la lista son **cargos ALTERNATIVOS aceptables**, no reformulaciones
del mismo. Por eso:

    OR entre alternativas  ·  AND dentro de cada alternativa

El cargo declarado acredita si reúne el núcleo COMPLETO de **alguna** de las
alternativas que listan las bases. Los sustantivos intercambiables y el ruido
("cargos similares:", "de obra") se descartan antes; una alternativa que solo
traía sustantivo queda sin términos y se ignora (no vacía el requisito).

Principio del sistema — **señalar, no juzgar**: el candado NUNCA calla una
contradicción, pero tampoco marca NO por ausencia de datos (si no puede derivar
el requisito, se abstiene). No toca el cómputo de días. El veredicto duro sigue
siendo del Comité.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# ── Sustantivos iniciales: NUNCA forman parte del núcleo ─────────────────────
# Son los que las bases intercambian libremente ("especialista / responsable /
# encargado / ingeniero / inspector de X"). Exigir uno de ellos daría falsos NO.
# OJO: SUPERVISOR/SUPERVISION, RESIDENTE y GERENTE **no** están aquí — en cargos
# como "Jefe de Supervisión" o "Gerente de Contrato" son el núcleo real.
_SUSTANTIVOS = {
    "ESPECIALISTA", "RESPONSABLE", "ENCARGADO", "ENCARGADA", "INGENIERO",
    "INGENIERA", "INSPECTOR", "INSPECTORA", "COORDINADOR", "COORDINADORA",
    "JEFE", "ARQUITECTO", "ARQUITECTA", "PROFESIONAL", "TECNICO", "LICENCIADO",
}

# Ruido que aparece en casi todos los cargos y no identifica especialidad.
# «CARGO/SIMILAR/VALIDO/EQUIVALENTE» vienen del preámbulo con que agent-bases
# copia la columna ("Cargos similares: especialista en arquitectura") — sin
# ellos aquí, el candado exigía literalmente «CARGOS» y «SIMILARES» (5 falsos
# NO en el replay).
_RUIDO = {
    "DEL", "LOS", "LAS", "OBRA", "OBRAS", "PARA", "CON", "POR", "CLAVE",
    "PERSONAL", "PROYECTO", "PROYECTOS", "CARGO", "AREA", "SR", "SRA",
    "SIMILAR", "VALIDO", "VALIDA", "EQUIVALENTE", "AFIN", "ACEPTADO",
    "ACEPTADA", "MINIMO", "MINIMA", "OTRO", "OTRA", "ESPECIALIDAD",
    "SUBESPECIALIDAD",
}

# Cualificadores que no identifican especialidad por sí solos: son la cola de un
# nombre compuesto ("medio ambiente", "seguridad y salud en el trabajo").
# Exigirlos produce falsos NO puramente sintácticos ("Especialista en Mitigación
# Ambiental" ≠ acredita «MEDIO»; SSOMA ≠ acredita «TRABAJO») — ambos vistos en
# el replay. Los términos con carga de especialidad (AMBIENTE, SEGURIDAD, SALUD)
# se conservan.
_CUALIFICADORES = {"MEDIO", "TRABAJO", "GENERAL", "INTEGRAL", "NIVEL", "TIPO"}

# Sustantivos de ACTIVIDAD o CONTENEDOR: dicen qué se hace o sobre qué documento,
# no en qué se es especialista. Las bases los usan para describir la alternativa
# ("Encargado del diseño/elaboración del expediente técnico del estudio
# definitivo de instalaciones sanitarias") y exigirlos genera falsos NO en masa:
# en el replay eran los faltantes MÁS reclamados —DESARROLLO 48×, ELABORACION
# 25×, INSTALACIONES 22×, DISEÑO 20×, EXPEDIENTES 10×— contra especialidades
# reales de 2-3× (PLANEAMIENTO, COSTOS, GEOTECNIA). Quitarlos deja el núcleo en
# el término que sí discrimina: «ESPECIALISTA EN MECÁNICA» acredita
# «Instalaciones Mecánicas», pero «Especialista en Instalaciones» a secas NO
# acredita «Instalaciones Sanitarias» (le falta SANITARIAS).
_ACTIVIDAD = {
    "DESARROLLO", "ELABORACION", "DISENO", "CALCULO", "ESTUDIO", "DEFINITIVO",
    "EXPEDIENTE", "INSTALACION", "EJECUCION", "FORMULACION", "IMPLEMENTACION",
    "COMBINACION", "DENOMINACION", "ESTA", "TECNICO", "TECNICA",
}

_STOP_BRUTO = _SUSTANTIVOS | _RUIDO | _CUALIFICADORES | _ACTIVIDAD

# ── Equivalencias léxicas — MÍNIMA Y CONSERVADORA ────────────────────────────
# Cada entrada nueva es una puerta al falso CUMPLE: solo se amplía con aval
# explícito del Comité (ver ADR-012). Hoy la única avalada es la del caso
# 2026-07-25: el Comité trató «Especialista en Planificación» como el mismo
# núcleo «planeamiento» (y lo rechazó por faltarle costos, no por el sinónimo).
# NO están —y no deben estar sin aval— costos≈presupuestos≈valorizaciones:
# esa equivalencia reabre exactamente el falso CUMPLE que este candado ataja.
_SINONIMOS = {
    "PLANIFICACION": "PLANEAMIENTO",
    "PLANEACION": "PLANEAMIENTO",
}

# Variación derivativa (supervisión↔supervisor, ambiente↔ambiental): dos
# términos largos con prefijo común suficiente son el mismo núcleo. Sin esto,
# «Supervisor de Obra» contra bases «… de Supervisión de Obra» daría falso NO.
# Los pares de la trampa (PLANEAMIENTO/PRESUPUESTO, COSTO/…) comparten ≤1 letra
# inicial, así que la trampa sigue atajada.
_PREFIJO_MIN = 6
_LARGO_MIN_PREFIJO = 7

_SEPARADORES = re.compile(r"[;/|\n·•]+")


def _norm(s) -> str:
    """Mayúsculas, sin tildes ni puntuación (mismo criterio que match_cargo.js)."""
    t = unicodedata.normalize("NFKD", str(s if s is not None else ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.upper()
    t = re.sub(r"[^A-Z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _stem(tok: str) -> str:
    """Plural → singular, conservador (COSTOS→COSTO, VALORIZACIONES→VALORIZACION)."""
    if len(tok) > 5 and tok.endswith("ES"):
        return tok[:-2]
    if len(tok) > 4 and tok.endswith("S"):
        return tok[:-1]
    return tok


def _canon(tok: str) -> str:
    s = _stem(tok)
    return _SINONIMOS.get(s, s)


_STOP = _STOP_BRUTO | {_canon(w) for w in _STOP_BRUTO}
# Las palabras ESTRUCTURALES se descartan además por familia derivativa: el
# plural español es ambiguo para un stemmer simple («valorizaciones»→VALORIZACION
# pero «expedientes»→EXPEDIENTE), y sin esto «EXPEDIENTES» se exigía como si
# fuera especialidad (39 falsos NO en el replay).
# Los SUSTANTIVOS quedan fuera de la comparación por prefijo a propósito:
# ARQUITECTO comparte 9 letras con ARQUITECTURA, que sí es una especialidad real
# — incluirlos borraba el núcleo de todos los cargos de arquitectura.
_STOP_FAMILIA = tuple(
    s for s in (_RUIDO | _CUALIFICADORES | _ACTIVIDAD) if len(s) >= _LARGO_MIN_PREFIJO)


def _es_ruido(tok: str) -> bool:
    """Descarta por forma cruda, canónica y familia derivativa del ruido."""
    if len(tok) < 3 or tok.isdigit() or tok in _STOP:
        return True
    c = _canon(tok)
    return c in _STOP or any(equivalentes(c, s) for s in _STOP_FAMILIA)


def _tokens(texto) -> list[str]:
    """Términos canónicos de un cargo, sin sustantivos genéricos ni ruido."""
    out: list[str] = []
    for t in _norm(texto).split(" "):
        if _es_ruido(t):
            continue
        c = _canon(t)
        if c not in out:
            out.append(c)
    return out


def equivalentes(a: str, b: str) -> bool:
    """¿Dos términos canónicos son el mismo núcleo? (exacto o familia derivativa)."""
    if a == b:
        return True
    if len(a) < _LARGO_MIN_PREFIJO or len(b) < _LARGO_MIN_PREFIJO:
        return False
    comun = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        comun += 1
    return comun >= _PREFIJO_MIN


def _hay_equivalente(term: str, tokens) -> bool:
    return any(equivalentes(term, t) for t in tokens)


@dataclass(frozen=True)
class Alternativa:
    """UN cargo aceptable de las bases: su núcleo se exige COMPLETO (AND)."""
    terminos: tuple[str, ...]
    etiquetas: dict          # término canónico → como lo escriben las bases
    texto: str               # la variante literal, para citarla en la observación

    def etiqueta(self, term: str) -> str:
        return self.etiquetas.get(term, term)

    def describir(self) -> str:
        return " + ".join(f"«{self.etiqueta(t)}»" for t in self.terminos)


@dataclass(frozen=True)
class Requisito:
    """Las alternativas aceptables (OR): basta reunir el núcleo de UNA."""
    alternativas: tuple[Alternativa, ...]

    def describir(self) -> str:
        return " ó ".join(a.describir() for a in self.alternativas)


def _variantes(cargos_validos) -> list[str]:
    """La lista de las bases llega como string unido con '; ' (o como array)."""
    if cargos_validos is None:
        return []
    crudo = cargos_validos if isinstance(cargos_validos, list) else [cargos_validos]
    fuera: list[str] = []
    for item in crudo:
        if item is None:
            continue
        for parte in _SEPARADORES.split(str(item)):
            if parte.strip():
                fuera.append(parte.strip())
    return fuera


def derivar_requisito(cargos_validos, cargo_bases_nombre=None) -> Optional[Requisito]:
    """Alternativas aceptables según las bases (OR), cada una con su núcleo (AND).

    Devuelve None si no hay señal suficiente (lista vacía, o ninguna alternativa
    con términos de especialidad) → el candado se abstiene. Nunca inventa núcleo.
    """
    variantes = _variantes(cargos_validos)
    if cargo_bases_nombre:
        variantes.append(str(cargo_bases_nombre))   # el nombre del Cuadro también vale

    alts: list[Alternativa] = []
    vistos: set = set()
    for var in variantes:
        terminos, etiquetas = [], {}
        for bruto in _norm(var).split(" "):
            if _es_ruido(bruto):
                continue
            c = _canon(bruto)
            if c not in terminos:
                terminos.append(c)
                etiquetas[c] = bruto
        if not terminos:
            continue                       # solo traía el sustantivo: se ignora
        clave = frozenset(terminos)
        if clave in vistos:
            continue                       # misma exigencia escrita distinto
        vistos.add(clave)
        alts.append(Alternativa(tuple(terminos), etiquetas, var.strip()))

    return Requisito(tuple(alts)) if alts else None


def evaluar_cargo(cargo_ocupado, requisito: Requisito) -> tuple[list[str], Optional[Alternativa]]:
    """→ (términos faltantes, alternativa de referencia).

    Faltantes vacío = el cargo acredita (reunió el núcleo de alguna alternativa).
    Si no acredita, devuelve los faltantes de la alternativa MÁS CERCANA, que es
    la que se le cita al Comité. Si `cargo_ocupado` viene vacío no se puede
    afirmar nada → acredita por abstención (nunca un falso NO).
    """
    toks = _tokens(cargo_ocupado)
    if not toks or not requisito.alternativas:
        return [], None

    mejor, mejor_falt, mejor_clave = None, None, None
    for alt in requisito.alternativas:
        falt = [t for t in alt.terminos if not _hay_equivalente(t, toks)]
        if not falt:
            return [], alt                                   # acredita por esta
        # más cercana = menos faltantes y, a igualdad, más términos SÍ acreditados
        # («Planeamiento y Costos» con costos acreditado gana a «Arquitectura»,
        #  que no comparte nada: es la que el Comité querría ver citada).
        clave = (len(falt), -(len(alt.terminos) - len(falt)))
        if mejor_clave is None or clave < mejor_clave:
            mejor, mejor_falt, mejor_clave = alt, falt, clave
    return [mejor.etiqueta(t) for t in mejor_falt], mejor


def faltantes(cargo_ocupado, requisito: Requisito) -> list[str]:
    """Atajo legible: solo los términos faltantes (ver `evaluar_cargo`)."""
    return evaluar_cargo(cargo_ocupado, requisito)[0]


def funciones_acreditadas(exp: dict) -> bool:
    """Segunda puerta: ¿el documento LISTA funciones/actividades?

    `funciones_similares` en null/vacío = el certificado solo consigna cargo,
    fechas y obra → NO acredita funciones (criterio literal del Comité).
    """
    v = exp.get("funciones_similares")
    if not isinstance(v, str) or not v.strip():
        return False
    t = _norm(v)
    if not t or t.startswith("NO") or "POR VERIFICAR" in t or t in ("N A", "NA"):
        return False
    return True


def veredicto_llm(exp: dict) -> Optional[str]:
    """Cómo quedó `cargo_bases_valido` según el LLM: 'si' | 'no' | None."""
    v = exp.get("cargo_bases_valido")
    if not isinstance(v, str) or not v.strip():
        return None
    t = _norm(v)
    if t.startswith("NO"):
        return "no"
    if t.startswith(("SI", "CUMPLE", "ACREDITA", "VALIDO")):
        return "si"
    return None


@dataclass(frozen=True)
class Hallazgo:
    """Lo que el candado concluyó sobre UNA experiencia."""
    n_exp: object
    cargo_ocupado: object
    faltantes: tuple[str, ...]
    referencia: Optional[Alternativa]     # la alternativa de las bases más cercana
    funciones: bool
    llm: Optional[str]

    @property
    def acredita(self) -> bool:
        return not self.faltantes

    @property
    def contradice(self) -> bool:
        """El candado dice que no acredita y el LLM había dicho que sí."""
        return bool(self.faltantes) and self.llm == "si"

    @property
    def duro(self) -> bool:
        """Ni cargo ni funciones: el caso que el Comité declara NO CUMPLE."""
        return bool(self.faltantes) and not self.funciones


def revisar_profesional(prof: dict) -> tuple[Optional[Requisito], list[Hallazgo]]:
    """Corre el candado sobre las experiencias de un profesional."""
    req = prof.get("requisitos") or {}
    requisito = derivar_requisito(req.get("cargos_validos"), prof.get("cargo_bases_nombre"))
    if requisito is None:
        return None, []
    out = []
    for e in prof.get("experiencias", []) or []:
        falt, alt = evaluar_cargo(e.get("cargo_ocupado"), requisito)
        out.append(Hallazgo(
            n_exp=e.get("n"), cargo_ocupado=e.get("cargo_ocupado"),
            faltantes=tuple(falt), referencia=alt,
            funciones=funciones_acreditadas(e), llm=veredicto_llm(e)))
    return requisito, out


# ── Marca en el espejo (lo que hace visible el hallazgo en el Excel) ─────────
# Reescribe `cargo_bases_valido` en el caso duro (ni cargo ni funciones), en DOS
# niveles — calibrados con el replay sobre 35 espejos reales (1421 experiencias):
#
#   ROJO      "NO (candado: …)"            → el LLM había escrito un SÍ explícito.
#             Es la contradicción del issue #31: había un verde que corregir.
#   AMARILLO  "POR VERIFICAR (candado: …)" → el LLM no dejó veredicto legible.
#             No hay verde que desmentir y ahí la precisión del candado es menor
#             (los cargos vienen redactados de mil formas), así que se pide
#             confirmación en vez de afirmar el NO.
#
# Ambos textos los pinta `_fill_veredicto` por su prefijo, sin tocar el formato
# congelado del Excel. El texto de Claude se conserva entre ⟦⟧ (traza, mismo
# criterio que el consolidador). NO se toca el cómputo de días: se señala, no se
# juzga — el veredicto duro es del Comité.
_MARCA_NO = "NO (candado:"
_MARCA_PEND = "POR VERIFICAR (candado:"


def _texto_marca(h: Hallazgo, previo, prefijo: str) -> str:
    falta = ", ".join(f"«{t}»" for t in h.faltantes)
    ref = f" del cargo exigido «{h.referencia.texto}»" if h.referencia else ""
    txt = (f"{prefijo} el cargo declarado no acredita {falta}{ref}; el documento "
           f"tampoco acredita funciones) — a ratificación del Comité")
    if isinstance(previo, str) and previo.strip():
        txt += f" ⟦Claude: {previo.strip()}⟧"
    return txt


def anotar_cargo_nucleo(espejo: dict) -> int:
    """Marca en el espejo las experiencias que el candado rechaza. Idempotente.

    Devuelve cuántas celdas reescribió. Debe correr DESPUÉS de `verificar_espejo`
    (que lee el veredicto original del LLM para detectar la contradicción).
    """
    tocadas = 0
    for prof in espejo.get("profesionales", []) or []:
        _, hallazgos = revisar_profesional(prof)
        por_n = {h.n_exp: h for h in hallazgos}
        for e in prof.get("experiencias", []) or []:
            h = por_n.get(e.get("n"))
            if h is None or not h.duro:
                continue
            if h.llm == "no":
                continue                      # el LLM ya la marcó: no hay qué corregir
            previo = e.get("cargo_bases_valido")
            if isinstance(previo, str) and previo.lstrip().startswith((_MARCA_NO, _MARCA_PEND)):
                continue                      # ya marcada (re-corrida)
            e["cargo_bases_valido"] = _texto_marca(
                h, previo, _MARCA_NO if h.llm == "si" else _MARCA_PEND)
            tocadas += 1
    return tocadas
