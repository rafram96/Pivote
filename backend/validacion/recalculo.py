"""
Recálculo determinístico de la Parte 4 (issue #45) — lo que NO necesita un LLM.

Hoy DÍAS / MESES / AÑOS / ¿ANT. COLEGIAT.? / ¿INCLUYE COVID? los calcula el LLM,
y cuando falla salen vacíos: en el job `95af90f1578e` las 63 experiencias vinieron
con `dias: null`. El Excel los lee directo del espejo (`e.get("dias")`), así que
sin este recálculo no hay recuperación posible y la columna sale en blanco.

Son aritmética de fechas y dos comparaciones: el backend los calcula.

**Frontera con el Paso 5 (no confundirlos).** Aquí se calcula el valor **BRUTO**
por experiencia — el periodo tal como lo declara el certificado — que es lo que
muestran las columnas DÍAS/MESES/AÑOS de la Parte 4. Los días **EFECTIVOS**
(recortados a la ventana de valorizaciones, menos paralizaciones de InfoObras,
menos traslapes ALT11) los calcula `orquestador/etapas_reales.py` con
`reglas.dias_efectivos_profesional` y viven en otro sitio del entregable. Un
bruto NUNCA es un efectivo: el bruto es lo declarado, el efectivo es lo probado.

Toda la aritmética se delega a `reglas/` (`dias_inclusivos`, `meses`, `anios`,
`periodo_fechas`): la convención de bordes es **INCLUSIVA** (días = fin − inicio
+ 1), verificada contra las hojas manuales del ingeniero. Ver `reglas/calculo.py`.

Abstención (es un detector de mentiras — un falso CUMPLE es el peor fallo):
- Fecha centinela ("POR VERIFICAR…") o parcial ("2019-03 (sin día)") → NO se
  calcula. Elegir un día dentro del mes es adivinar, y ese día inventado se
  propaga a DÍAS, a los años acumulados y al veredicto.
- Periodo invertido (fin < inicio) → no se sabe cuál de las dos fechas está mal:
  se abstiene de las tres columnas, no se "arregla" dando vuelta el par.
- Sin `fecha_colegiatura` → `anterior_colegiatura` queda vacío, NO "NO":
  no saber no es lo mismo que saber que no.
- **DÍAS en discrepancia** → no se derivan MESES/AÑOS de él, y esa experiencia
  no entra en la fila TOTAL: un número que el backend acaba de declarar no
  confiable no puede propagarse a la columna que lee el Factor A ni al
  acumulado que el evaluador lee como «años de experiencia» (ver `_confiable`).
- **Fila TOTAL** → solo si TODAS las experiencias tienen periodo legible y DÍAS
  no discrepante, y además **ninguna se traslapa** con otra. Ver
  `_total_del_profesional`: un total incompleto se lee como la experiencia
  completa del profesional, y con solape la suma bruta la exagera.

**DÍAS es el dato; MESES y AÑOS son su conversión de unidad.** Se calculan igual,
pero no se comparan contra el espejo: eso alertaría del divisor que usó el LLM
(365/12, 360…) y no de la experiencia del profesional — 33 de 34 casos en los 37
espejos reales. Ver `_SIN_DISCREPANCIA`.

Por defecto **solo rellena lo vacío** (`sobrescribir=False`): el valor del LLM
puede traer matices ("NO — el título es posterior pero el cert…") que no se
borran a ciegas. Lo que ya venía y no cuadra se reporta como `Discrepancia`;
quién manda sigue siendo el Comité.

Funciones puras + una mutación explícita del espejo (`recalcular_espejo`, misma
convención que `anotar_cargo_nucleo`). Sin I/O, sin red.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from reglas import anios, dias_inclusivos, fusionar_traslapes, meses, periodo_fechas
from schemas import pipeline
from schemas.espejo import SENTINEL_POR_VERIFICAR

# COVID y la normalización de flags se importan del validador para que las dos
# capas no puedan divergir: si la ventana cambia, cambia en un solo sitio.
from .notas import COVID_FIN, COVID_INICIO, _es_si

# Vocabulario del espejo real (ffbda008a346 y el resto de corridas sanas). Ojo:
# lleva tilde — `_clasificar_veredicto` del Excel acepta ambas, pero se escribe
# como lo escribe la skill para que el diff contra un espejo sano sea vacío.
SI = "SÍ"
NO = "NO"

CAMPOS = ("dias", "meses", "anios", "anterior_colegiatura", "incluye_covid")

# MESES y AÑOS se guardan redondeados a 2 decimales: es lo que traen los espejos
# sanos y lo que ya hace la etapa REGLAS (`round(anios(...), 2)`).
DECIMALES = 2

# Campos que NO se reportan como discrepancia (se calculan igual; lo que no se
# hace es alertar cuando el espejo trae otra cosa):
#
# - `incluye_covid`: recalcular lo que Claude marcó y contradecirlo ya es trabajo
#   de la NOTA 10 (`notas.nota10_covid`). Duplicarlo llenaría el panel dos veces.
# - `meses` y `anios`: NO son datos, son la conversión de unidad de `dias`. El
#   dato vigilado es DÍAS, que tiene una sola convención (inclusiva) y sí se
#   compara. Medido sobre los 37 espejos reales: de 34 "discrepancias" de
#   meses/años, 33 eran solo otro divisor (Claude usa 365/12 = 30.4167 en la fila
#   TOTAL y 360 en un caso, el proyecto usa 30 y 365) y una sola era un error
#   real. Un candado con 33 falsos positivos por cada acierto no se lee: el
#   evaluador aprende a ignorarlo, y de paso se lleva puestas las alertas buenas.
#   Si los DÍAS no cuadran, la alerta de DÍAS ya lo dice.
_SIN_DISCREPANCIA = frozenset({"incluye_covid", "meses", "anios"})

# Códigos de abstención (para agrupar; el texto largo va aparte).
MOTIVO_SIN_FECHA = "SIN_FECHA"
MOTIVO_CENTINELA = "FECHA_CENTINELA"
MOTIVO_PARCIAL = "FECHA_PARCIAL"
MOTIVO_INVERTIDO = "PERIODO_INVERTIDO"
MOTIVO_SIN_COLEGIATURA = "SIN_COLEGIATURA"
MOTIVO_SIN_DIAS = "SIN_DIAS"
MOTIVO_DIAS_DISCREPANTE = "DIAS_DISCREPANTE"
MOTIVO_TOTAL_INCOMPLETO = "TOTAL_INCOMPLETO"
MOTIVO_TOTAL_TRASLAPE = "TOTAL_TRASLAPE"

_RE_ISO_COMPLETA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Lectura defensiva de fechas ──────────────────────────────────────────────

def fecha_dura(v) -> Optional[date]:
    """`date` SOLO si la fecha es cierta al día; todo lo demás → None.

    El espejo admite tres formas (`schemas/espejo.py`): ISO completa, parcial
    ("2019-03 (sin día)") y centinela ("POR VERIFICAR…"). Con las dos últimas no
    hay día que restar. Acepta `date`/`datetime` porque el mismo espejo llega ya
    coercionado por Pydantic o crudo del JSON según por dónde entre al pipeline.
    """
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and _RE_ISO_COMPLETA.match(v.strip()):
        try:
            # La conversión la hace `periodo_fechas` (reglas/): un solo parser de
            # fechas en el backend, no dos que puedan divergir.
            return periodo_fechas((v.strip(), v.strip()))[0]
        except ValueError:
            return None      # "2019-02-30": ISO en la forma, imposible en el calendario
    return None


def _vacio(v) -> bool:
    """Vacío = None o cadena en blanco. El 0 NO es vacío (0.0 años es un dato)."""
    return v is None or (isinstance(v, str) and not v.strip())


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def _motivo_fecha(valor, etiqueta: str) -> tuple[str, str]:
    if _vacio(valor):
        return MOTIVO_SIN_FECHA, f"{etiqueta} vacía en el espejo"
    texto = str(valor).strip()
    if texto.upper().startswith(SENTINEL_POR_VERIFICAR):
        return (MOTIVO_CENTINELA,
                f"{etiqueta}={texto!r}: el certificado no consigna la fecha")
    return (MOTIVO_PARCIAL,
            f"{etiqueta}={texto!r} no es una fecha completa; elegir un día dentro "
            f"del mes sería adivinar")


def _motivo_colegiatura(valor) -> tuple[str, str]:
    if _vacio(valor):
        return (MOTIVO_SIN_COLEGIATURA,
                "el profesional no trae fecha_colegiatura: no se puede saber si la "
                "experiencia es anterior (no saber ≠ no serlo)")
    return _motivo_fecha(valor, "fecha_colegiatura")


# ── Cálculo por experiencia (puro: no toca el espejo) ────────────────────────

def solapa_covid(inicio: date, fin: date) -> bool:
    """¿El periodo pisa la ventana COVID? Bordes INCLUSIVOS: un periodo que
    termina el 16/03/2020 o que empieza el 30/06/2020 sí la incluye."""
    return inicio <= COVID_FIN and fin >= COVID_INICIO


def derivar_de_dias(dias) -> dict:
    """MESES y AÑOS a partir de los DÍAS que quedarán en la fila.

    Se derivan del valor VIGENTE, no del recalculado: si el LLM ya puso un DÍAS y
    no lo estamos pisando, derivar del nuestro dejaría la fila internamente
    incoherente (163 días / 5.47 meses) en el Excel que lee el evaluador.
    """
    return {"meses": round(meses(dias), DECIMALES),
            "anios": round(anios(dias), DECIMALES)}


def calcular_campos(exp: dict, fecha_colegiatura=None) -> tuple[dict, dict]:
    """Calcula `dias`, `anterior_colegiatura` e `incluye_covid` de UNA experiencia.

    No muta `exp` ni mira lo que ya trae. Devuelve
    `({campo: valor}, {campo: (codigo, motivo)})`: lo que se pudo calcular y por
    qué no se pudo el resto. MESES/AÑOS no salen de aquí — dependen del DÍAS que
    termine vigente en la fila (ver `derivar_de_dias`).
    """
    valores: dict = {}
    motivos: dict = {}

    crudo_ini, crudo_fin = exp.get("fecha_inicial"), exp.get("fecha_final")
    ini, fin = fecha_dura(crudo_ini), fecha_dura(crudo_fin)

    if ini is None:
        motivo_periodo = _motivo_fecha(crudo_ini, "fecha_inicial")
    elif fin is None:
        motivo_periodo = _motivo_fecha(crudo_fin, "fecha_final")
    elif fin < ini:
        motivo_periodo = (MOTIVO_INVERTIDO,
                          f"periodo invertido ({ini} → {fin}): no se sabe cuál de "
                          f"las dos fechas está mal, no se da vuelta el par")
    else:
        motivo_periodo = None

    if motivo_periodo is None:
        periodo = periodo_fechas((ini, fin))
        valores["dias"] = dias_inclusivos(*periodo)
        valores["incluye_covid"] = SI if solapa_covid(*periodo) else NO
    else:
        motivos["dias"] = motivo_periodo
        motivos["incluye_covid"] = motivo_periodo

    # `anterior_colegiatura` solo mira fecha_inicial: si únicamente falta
    # fecha_final, el dato sigue siendo calculable. Con el periodo invertido no,
    # porque la sospechosa puede ser precisamente la inicial.
    invertido = motivo_periodo is not None and motivo_periodo[0] == MOTIVO_INVERTIDO
    colegiatura = fecha_dura(fecha_colegiatura)
    if ini is None or invertido:
        motivos["anterior_colegiatura"] = motivo_periodo
    elif colegiatura is None:
        motivos["anterior_colegiatura"] = _motivo_colegiatura(fecha_colegiatura)
    else:
        # Estricto: empezar el MISMO día de la colegiatura no es "anterior".
        valores["anterior_colegiatura"] = SI if ini < colegiatura else NO

    return valores, motivos


# ── Reporte de lo que pasó ───────────────────────────────────────────────────

@dataclass(frozen=True)
class Relleno:
    """Celda que el backend escribió.

    `previo` distingue los dos casos que NO son lo mismo: hueco rellenado
    (`previo` vacío, el 99% de las veces) vs valor de la propuesta reemplazado
    (solo posible con `sobrescribir=True` — ahí `sobrescrito` es True y el texto
    original ya no está en el espejo). Antes se contaban juntos y el log decía
    "rellenado" de algo que en realidad se había borrado.
    """
    n_prof: object
    n_exp: object
    campo: str
    valor: object
    previo: object = None

    @property
    def sobrescrito(self) -> bool:
        return not _vacio(self.previo)


@dataclass(frozen=True)
class Abstencion:
    """Campo que quedó vacío a propósito, con el porqué."""
    n_prof: object
    n_exp: object
    campo: str
    codigo: str
    motivo: str


@dataclass(frozen=True)
class Discrepancia:
    """El espejo ya traía un valor y no coincide con el recalculado.

    No se corrige solo (salvo `sobrescribir=True`): se señala. Ojo con `dias` —
    ver `TOLERANCIA_DIAS`.
    """
    n_prof: object
    n_exp: object
    campo: str
    valor_espejo: object
    valor_calculado: object


# El LLM cuenta los días EXCLUSIVOS (fin − inicio) y el proyecto los cuenta
# INCLUSIVOS (+1, convención verificada contra las hojas del ingeniero). Esa
# diferencia sistemática de 1 día no es un error del extractor y llenaría el
# panel de ruido, así que no se reporta. Mismo criterio que `notas.totales_cuadran`
# (tolera ±1 día por experiencia).
#
# Es la ÚNICA tolerancia del módulo: ya no hay un epsilon aparte para los
# decimales de MESES/AÑOS que perdonara más o menos que este (1 día son 0.033
# meses, así que el viejo 0.02 alertaba en MESES por la misma diferencia de
# convención que en DÍAS se declaraba correcta). Al dejar de comparar las
# columnas derivadas —ver `_SIN_DISCREPANCIA`— queda un solo número que calibrar.
# Para la fila TOTAL se escala a N días (N = experiencias sumadas): el off-by-one
# se acumula al sumar, igual que en `notas.totales_cuadran`.
TOLERANCIA_DIAS = 1


@dataclass(frozen=True)
class ResultadoRecalculo:
    rellenos: tuple[Relleno, ...] = ()
    abstenciones: tuple[Abstencion, ...] = ()
    discrepancias: tuple[Discrepancia, ...] = ()

    @property
    def tocadas(self) -> int:
        """Celdas escritas (huecos rellenados + valores sobrescritos)."""
        return len(self.rellenos)

    @property
    def sobrescritos(self) -> tuple[Relleno, ...]:
        """Los que pisaron un valor de la propuesta (solo con `sobrescribir=True`)."""
        return tuple(r for r in self.rellenos if r.sobrescrito)

    @staticmethod
    def _cuenta(items) -> dict[str, int]:
        out: dict[str, int] = {}
        for i in items:
            out[i.campo] = out.get(i.campo, 0) + 1
        return out

    def por_campo(self) -> dict[str, int]:
        """Celdas escritas de cada campo (huecos + sobrescrituras)."""
        return self._cuenta(self.rellenos)

    def huecos_por_campo(self) -> dict[str, int]:
        """Solo las celdas que estaban VACÍAS y el backend calculó."""
        return self._cuenta(r for r in self.rellenos if not r.sobrescrito)

    def sobrescritos_por_campo(self) -> dict[str, int]:
        return self._cuenta(self.sobrescritos)

    def vacios_por_campo(self) -> dict[str, int]:
        return self._cuenta(self.abstenciones)

    def resumen(self) -> str:
        """Una línea para el log de la etapa."""
        rel = ", ".join(f"{k}={v}" for k, v in sorted(self.huecos_por_campo().items())) or "nada"
        vac = ", ".join(f"{k}={v}" for k, v in sorted(self.vacios_por_campo().items()))
        sob = ", ".join(f"{k}={v}" for k, v in sorted(self.sobrescritos_por_campo().items()))
        txt = f"recálculo Parte 4 · rellenado: {rel}"
        if vac:
            txt += f" · sin calcular: {vac}"
        if sob:
            txt += f" · SOBRESCRITO (se perdió lo de la propuesta): {sob}"
        if self.discrepancias:
            txt += f" · discrepancias: {len(self.discrepancias)}"
        return txt


# ── Aplicación sobre el espejo ───────────────────────────────────────────────

def _discrepa(campo: str, previo, calculado,
              dias_tolerados: int = TOLERANCIA_DIAS) -> bool:
    """¿El valor del espejo contradice al recalculado? (con las tolerancias)."""
    if campo in _SIN_DISCREPANCIA:
        return False
    if campo == "dias":
        if not _numero(previo):
            return True          # texto donde debería haber un número
        return abs(previo - calculado) > dias_tolerados
    # Flags: se comparan normalizados («SÍ» == «SI» == «SÍ, porque…»). Un texto
    # que no empieza por SÍ/NO no es comparable → no se declara discrepancia.
    previo_flag, calc_flag = _es_si(previo), _es_si(calculado)
    return previo_flag is not None and previo_flag != calc_flag


def _confiable(dias_vigente, dias_calculado, dias_tolerados: int = TOLERANCIA_DIAS) -> bool:
    """¿El DÍAS que queda en la fila sirve para derivar MESES/AÑOS y sumar al TOTAL?

    Sí cuando es un número y (a) es el nuestro / coincide con el nuestro dentro de
    tolerancia, o (b) no teníamos con qué contrastarlo (fechas no computables: es
    el único número disponible y la fila tiene que ser internamente coherente).
    NO cuando el backend ya lo declaró en discrepancia: derivar de él escribiría
    AÑOS —la columna del Factor A— desde un número que el backend no cree, y
    encima lo anunciaría como "calculado por el backend".
    """
    if not _numero(dias_vigente):
        return False
    if dias_calculado is None:
        return True
    return not _discrepa("dias", dias_vigente, dias_calculado, dias_tolerados)


def recalcular_espejo(
    espejo: dict,
    *,
    sobrescribir: bool = False,
) -> ResultadoRecalculo:
    """Rellena en el espejo los campos calculables de la Parte 4. **Idempotente.**

    `sobrescribir=False` (defecto): solo escribe donde está vacío; lo que ya venía
    se conserva tal cual y, si no cuadra, se reporta en `discrepancias`.
    `sobrescribir=True`: impone el valor del backend. Ojo con el orden — con esta
    opción hay que correrlo **después** de `verificar_espejo`, porque las NOTAS 9
    y 10 comparan contra lo que escribió Claude y ya no lo encontrarían.
    Con el defecto puede correr antes (y conviene: así `totales_cuadran` ve los
    días rellenados).

    Cubre las 5 columnas por experiencia **y la fila TOTAL** del profesional
    (ver `_total_del_profesional`).
    """
    rellenos: list[Relleno] = []
    abstenciones: list[Abstencion] = []
    discrepancias: list[Discrepancia] = []

    def aplicar(destino: dict, n_prof, n_exp, campo: str, valor, motivo,
                *, prefijo: str = "", dias_tolerados: int = TOLERANCIA_DIAS) -> object:
        """Escribe (o no) el campo; devuelve el valor VIGENTE en la celda.

        `prefijo` es solo etiqueta de reporte ("total.dias"); la clave escrita en
        `destino` sigue siendo `campo`.
        """
        etiqueta = prefijo + campo
        previo = destino.get(campo)
        if valor is None:
            if _vacio(previo):
                # `calcular_campos` garantiza el motivo; el respaldo evita que un
                # campo nuevo sin motivo tumbe TODO el recálculo.
                codigo, texto = motivo or (
                    MOTIVO_SIN_FECHA, "sin datos para calcular el campo")
                abstenciones.append(
                    Abstencion(n_prof, n_exp, etiqueta, codigo, texto))
            return previo
        if not _vacio(previo):
            if previo == valor:
                return previo                    # nada que hacer (re-corrida)
            if _discrepa(campo, previo, valor, dias_tolerados):
                discrepancias.append(
                    Discrepancia(n_prof, n_exp, etiqueta, previo, valor))
            if not sobrescribir:
                return previo
        destino[campo] = valor
        rellenos.append(Relleno(n_prof, n_exp, etiqueta, valor, previo))
        return valor

    def derivar(destino: dict, n_prof, n_exp, dias_vigente, dias_calculado,
                motivo_periodo, *, prefijo: str = "",
                dias_tolerados: int = TOLERANCIA_DIAS) -> None:
        """MESES/AÑOS de una celda de DÍAS — o la abstención con su porqué."""
        if _confiable(dias_vigente, dias_calculado, dias_tolerados):
            derivados = derivar_de_dias(dias_vigente)
            for campo in ("meses", "anios"):
                aplicar(destino, n_prof, n_exp, campo, derivados[campo], None,
                        prefijo=prefijo, dias_tolerados=dias_tolerados)
            return
        if _numero(dias_vigente):
            motivo = (MOTIVO_DIAS_DISCREPANTE,
                      f"dias={dias_vigente!r} no coincide con el recalculado "
                      f"({dias_calculado}): no se derivan meses ni años de un "
                      f"número que el backend no da por bueno")
        else:
            # Sin DÍAS no hay de dónde sacar MESES/AÑOS: se hereda el motivo del
            # periodo, o se dice que el DÍAS del espejo no es un número.
            motivo = motivo_periodo or (
                MOTIVO_SIN_DIAS,
                f"dias={dias_vigente!r} no es un número: no se derivan meses ni años")
        for campo in ("meses", "anios"):
            aplicar(destino, n_prof, n_exp, campo, None, motivo,
                    prefijo=prefijo, dias_tolerados=dias_tolerados)

    for prof in espejo.get("profesionales", []) or []:
        n_prof = prof.get("n_prof")
        colegiatura = prof.get("fecha_colegiatura")
        sumables: list[Optional[int]] = []
        periodos: list[tuple[date, date]] = []

        for exp in prof.get("experiencias", []) or []:
            n_exp = exp.get("n")
            valores, motivos = calcular_campos(exp, colegiatura)
            dias_calculado = valores.get("dias")

            dias_vigente = aplicar(exp, n_prof, n_exp, "dias",
                                   dias_calculado, motivos.get("dias"))
            derivar(exp, n_prof, n_exp, dias_vigente, dias_calculado,
                    motivos.get("dias"))
            for campo in ("anterior_colegiatura", "incluye_covid"):
                aplicar(exp, n_prof, n_exp, campo,
                        valores.get(campo), motivos.get(campo))

            # Para el TOTAL solo cuentan las experiencias cuyo periodo el backend
            # pudo LEER (no basta con que Claude haya puesto un número): así el
            # total es enteramente derivado de fechas y se puede cruzar traslapes.
            if dias_calculado is not None and _confiable(dias_vigente, dias_calculado):
                sumables.append(dias_vigente)
                periodos.append(periodo_fechas(
                    (fecha_dura(exp.get("fecha_inicial")),
                     fecha_dura(exp.get("fecha_final")))))
            else:
                sumables.append(None)

        _total_del_profesional(prof, n_prof, sumables, periodos, aplicar, derivar)

    return ResultadoRecalculo(
        tuple(rellenos), tuple(abstenciones), tuple(discrepancias))


def _total_del_profesional(prof: dict, n_prof, sumables: list,
                           periodos: list, aplicar, derivar) -> None:
    """Fila TOTAL de la Parte 4 (`prof["total"]` → DÍAS/MESES/AÑOS del Excel).

    Es el número que el evaluador lee como «años de experiencia del profesional»
    (`scripts/generar_excel.py`, fila TOTAL): si las filas se recalculan y el
    total no, el Excel se autocontradice — la columna suma una cosa y el total
    dice otra, o queda en blanco (91 de los 342 profesionales del corpus, los 10
    de `95af90f1578e` entre ellos; 29 se recuperan aquí).

    Se llena la SUMA BRUTA de la columna —misma convención que
    `notas.totales_cuadran`, que compara `total.dias` contra la suma pelada— y
    **solo cuando esa suma no puede exagerar la experiencia**. Dos candados:

    1. **Todas** las experiencias con periodo legible y DÍAS no discrepante. Un
       total al que le faltan periodos no se lee como "faltan datos": se lee como
       la experiencia completa del profesional.
    2. **Sin traslapes** (ALT11 / NOTA 9). Medido en los 37 espejos reales:
       cuando hay solape, Claude a veces pone en `total` la cifra YA de-solapada
       (`013721553f0a` prof 4: total 5 años, columna 8.38, y su veredicto dice
       "de-solapando 2022-2026"). Escribir ahí la suma bruta inflaría 3.4 años la
       celda que decide el Factor A — la dirección peligrosa. Con solape el
       backend se abstiene y el número lo pone quien descuenta: los días
       EFECTIVOS del Paso 5 (`reglas.dias_efectivos_profesional`).

    Por lo mismo un `total` que ya viene NO se pisa (`sobrescribir=False`): puede
    ser bruto o de-solapado y el backend no puede saber cuál.
    """
    if not sumables:                           # profesional sin experiencias
        return

    n = len(sumables)
    faltan = sum(1 for d in sumables if not _numero(d))
    traslape = fusionar_traslapes(periodos)[1] if not faltan else 0
    if faltan:
        total_dias = None
        motivo = (MOTIVO_TOTAL_INCOMPLETO,
                  f"{faltan} de {n} experiencias sin periodo legible o con DÍAS "
                  f"en discrepancia: un total parcial se leería como la "
                  f"experiencia completa del profesional")
    elif traslape:
        total_dias = None
        motivo = (MOTIVO_TOTAL_TRASLAPE,
                  f"los periodos se traslapan ({traslape} días en común): la suma "
                  f"bruta exageraría la experiencia y no se sabe si el total "
                  f"debe ir bruto o de-solapado — lo resuelve el Paso 5")
    else:
        total_dias = sum(sumables)
        motivo = None

    # El off-by-one de convención se acumula al sumar: ±1 día por experiencia.
    tol = TOLERANCIA_DIAS * n
    destino = prof.get("total")
    if not isinstance(destino, dict):
        destino = {}                           # se engancha solo si se escribe

    vigente = aplicar(destino, n_prof, None, "dias", total_dias, motivo,
                      prefijo="total.", dias_tolerados=tol)
    derivar(destino, n_prof, None, vigente, total_dias, motivo,
            prefijo="total.", dias_tolerados=tol)

    if destino and prof.get("total") is not destino:
        prof["total"] = destino


# ── Traducción a observaciones del pipeline (opcional; el que cablea decide) ──

def observaciones_recalculo(
    resultado: ResultadoRecalculo,
    *,
    origen: pipeline.Etapa = pipeline.Etapa.REGLAS,
) -> list[pipeline.Observacion]:
    """`ResultadoRecalculo` → observaciones para el job.

    Agrupadas por experiencia: una fila con 3 columnas vacías es UN problema, no
    tres. `origen` es parámetro porque el recálculo puede colgarse de VALIDACION
    o de REGLAS según dónde lo cablee el orquestador.
    """
    out: list[pipeline.Observacion] = []

    # INFO: solo los huecos. Lo sobrescrito NO es "calculado por el backend" a
    # secas — es un dato de la propuesta que se perdió, y va aparte.
    huecos = resultado.huecos_por_campo()
    if huecos:
        detalle = ", ".join(f"{k}={v}" for k, v in sorted(huecos.items()))
        out.append(pipeline.Observacion(
            codigo="RECALCULO", severidad=pipeline.Severidad.INFO,
            mensaje=f"campos de la Parte 4 calculados por el backend: {detalle}",
            origen=origen))

    sobrescritos = resultado.sobrescritos_por_campo()
    if sobrescritos:
        detalle = ", ".join(f"{k}={v}" for k, v in sorted(sobrescritos.items()))
        out.append(pipeline.Observacion(
            codigo="RECALCULO", severidad=pipeline.Severidad.ADVERTENCIA,
            mensaje=(f"sobrescribir=True: el backend reemplazó valores que traía la "
                     f"propuesta ({detalle}); el texto original ya no está en el espejo"),
            origen=origen))

    # Abstenciones: agrupadas por (profesional, experiencia, motivo).
    agrupadas: dict[tuple, list[str]] = {}
    for a in resultado.abstenciones:
        agrupadas.setdefault((a.n_prof, a.n_exp, a.codigo, a.motivo), []).append(a.campo)
    for (n_prof, n_exp, _codigo, motivo), campos in agrupadas.items():
        out.append(pipeline.Observacion(
            codigo="RECALCULO", severidad=pipeline.Severidad.ADVERTENCIA,
            mensaje=f"sin calcular ({', '.join(campos)}): {motivo}",
            origen=origen, referencia=_referencia(n_prof, n_exp)))

    for d in resultado.discrepancias:
        out.append(pipeline.Observacion(
            codigo="RECALCULO", severidad=pipeline.Severidad.ALERTA,
            mensaje=(f"{d.campo}={d.valor_espejo!r} en el espejo, pero el recálculo "
                     f"determinístico da {d.valor_calculado!r} — a ratificación del Comité"),
            origen=origen, referencia=_referencia(d.n_prof, d.n_exp)))

    return out


def _referencia(n_prof, n_exp) -> str:
    """La fila TOTAL no tiene número de experiencia: no se escribe 'exp=None'."""
    return f"prof={n_prof}" if n_exp is None else f"prof={n_prof} exp={n_exp}"
