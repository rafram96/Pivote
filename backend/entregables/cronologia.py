"""
Lógica PURA de la «Línea de tiempo por profesional» (sección 2 de la hoja
«Cronología de expedientes»).

Aquí no se toca openpyxl ni se decide nada del negocio: solo se calcula DÓNDE
va cada cosa en la rejilla — el eje temporal, qué celdas pinta cada periodo, en
qué celda cae un hito y qué rótulo lleva la fila. Las decisiones (qué días
cuentan, con cuánta certeza se identificó la obra, qué dice cada regla) siguen
viviendo en `validacion.recalculo`, `entregables.certeza` y
`reglas.cruces_fechas`; este módulo solo las coloca.

Se separa del render para poder probar el layout sin construir un libro: un
error de una celda (una barra corrida un mes, una «C» en el trimestre
equivocado) es indetectable a ojo en un Excel de cincuenta columnas y es
justamente lo que el Comité mira primero.

Granularidad adaptativa
───────────────────────
El mismo dibujo tiene que servir para un profesional con dos experiencias de
tres meses y para otro con veinte años de trayectoria:

  · hasta  60 meses de rango → una columna por MES      (letra del mes)
  · hasta 240 meses de rango → una columna por TRIMESTRE («T1»…«T4»)
  · más                      → una columna por AÑO      (sin sub-rótulo)
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import NamedTuple, Optional, Sequence

# ── Vocabulario de granularidad ─────────────────────────────────────────────
GRANO_MES = "mes"
GRANO_TRIMESTRE = "trimestre"
GRANO_ANIO = "anio"

#: Umbrales (en MESES de rango, bordes inclusivos) que eligen la granularidad.
MAX_MESES_GRANO_MES = 60
MAX_MESES_GRANO_TRIMESTRE = 240

#: Inicial del mes en español; la «S» de setiembre se escribe S, no SET.
LETRA_MES = "EFMAMJJASOND"

#: Un hito documental (firma o resolución) que cae fuera del periodo declarado
#: pero CERCA se muestra igual: es la información que explica el desfase. Más
#: allá de esta distancia estirar el eje solo aplasta las barras.
MARGEN_HITO_MESES = 6

# ── Medidas de la rejilla ───────────────────────────────────────────────────
ANCHO_ROTULO = 46          # columna A: «N° · proyecto · CUI»
ANCHO_UNIDAD = 2.4         # cada mes / trimestre / año
#: Mínimo de columnas de la hoja. La sección 1 (fichas por proyecto) escribe su
#: valor combinando D hasta la última columna: con un eje corto ese ancho se
#: quedaría en veinte caracteres y la ficha se rompería. Se rellena con columnas
#: vacías del mismo ancho hasta reponer los ~185 caracteres que la ficha tenía
#: con la rejilla anterior (el campo más largo de un job real mide 139).
MIN_COLUMNAS = 80
#: Recorte del nombre del proyecto en el rótulo.
LARGO_PROYECTO = 45

# ── Marcas que se escriben ENCIMA de la barra ───────────────────────────────
MARCA_FIRMA = "C"          # firma del contrato
MARCA_RESOLUCION = "R"     # resolución que aprobó el expediente
MARCA_MES = "≈"            # el periodo viene con mes y año: se asume mes completo

NOTA_MES_COMPLETO = "(fechas de mes; se asume mes completo)"
NOTA_SIN_FECHAS = "sin fechas computables"
SIN_CUI = "sin CUI"


class Unidad(NamedTuple):
    """Una columna del eje: el intervalo de fechas que representa."""
    inicio: date
    fin: date
    anio: int
    etiqueta: str


# ── Fechas ──────────────────────────────────────────────────────────────────

def fecha(v) -> Optional[date]:
    """`date` a partir de un ISO completo, un `date` o un `datetime`; si no, None.

    Deliberadamente estricto: en el eje una fecha a medias no se puede colocar
    en ninguna columna, y adivinar el día sería inventar el hito.
    """
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        t = v.strip()[:10]
        try:
            return date.fromisoformat(t)
        except ValueError:
            return None
    return None


def desplazar_meses(f: date, n: int) -> date:
    """`f` movida `n` meses, recortando el día al último del mes destino."""
    total = (f.year * 12 + (f.month - 1)) + n
    anio, mes = divmod(total, 12)
    mes += 1
    return date(anio, mes, min(f.day, monthrange(anio, mes)[1]))


def meses_entre(a: date, b: date) -> int:
    """Cuántos MESES de calendario abarca `[a, b]`, bordes inclusivos (≥ 1)."""
    if b < a:
        a, b = b, a
    return (b.year - a.year) * 12 + (b.month - a.month) + 1


def dias_inclusivos(a: date, b: date) -> int:
    return (b - a).days + 1 if b >= a else 0


# ── Eje ─────────────────────────────────────────────────────────────────────

def rango_eje(periodos: Sequence[tuple[date, date]],
              hitos: Sequence[Optional[date]] = (),
              margen_meses: int = MARGEN_HITO_MESES
              ) -> Optional[tuple[date, date]]:
    """Del primer inicio al último fin de los periodos computables, estirado
    para que quepan los hitos que caigan a menos de `margen_meses`.

    Devuelve None si el profesional no tiene ningún periodo computable: sin
    periodos no hay línea de tiempo que dibujar (y un hito suelto no la crea).
    """
    validos = [(a, b) for a, b in periodos if a and b and b >= a]
    if not validos:
        return None
    ini = min(a for a, _ in validos)
    fin = max(b for _, b in validos)
    for h in hitos:
        if not h:
            continue
        if h < ini and h >= desplazar_meses(ini, -margen_meses):
            ini = h
        elif h > fin and h <= desplazar_meses(fin, margen_meses):
            fin = h
    return ini, fin


def granularidad(inicio: date, fin: date) -> str:
    n = meses_entre(inicio, fin)
    if n <= MAX_MESES_GRANO_MES:
        return GRANO_MES
    if n <= MAX_MESES_GRANO_TRIMESTRE:
        return GRANO_TRIMESTRE
    return GRANO_ANIO


def construir_eje(inicio: date, fin: date,
                  grano: Optional[str] = None) -> list[Unidad]:
    """Las columnas del eje, de `inicio` a `fin`, con la granularidad elegida."""
    if fin < inicio:
        inicio, fin = fin, inicio
    grano = grano or granularidad(inicio, fin)
    eje: list[Unidad] = []

    if grano == GRANO_MES:
        anio, mes = inicio.year, inicio.month
        while (anio, mes) <= (fin.year, fin.month):
            eje.append(Unidad(date(anio, mes, 1),
                              date(anio, mes, monthrange(anio, mes)[1]),
                              anio, LETRA_MES[mes - 1]))
            anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        return eje

    if grano == GRANO_TRIMESTRE:
        anio, tri = inicio.year, (inicio.month - 1) // 3 + 1
        fin_anio, fin_tri = fin.year, (fin.month - 1) // 3 + 1
        while (anio, tri) <= (fin_anio, fin_tri):
            m0 = (tri - 1) * 3 + 1
            eje.append(Unidad(date(anio, m0, 1),
                              date(anio, m0 + 2, monthrange(anio, m0 + 2)[1]),
                              anio, f"T{tri}"))
            anio, tri = (anio + 1, 1) if tri == 4 else (anio, tri + 1)
        return eje

    for anio in range(inicio.year, fin.year + 1):
        eje.append(Unidad(date(anio, 1, 1), date(anio, 12, 31), anio, ""))
    return eje


def indice_unidad(eje: Sequence[Unidad], f: Optional[date]) -> Optional[int]:
    """En qué columna cae una fecha suelta (un hito); None si queda fuera."""
    if not f:
        return None
    for i, u in enumerate(eje):
        if u.inicio <= f <= u.fin:
            return i
    return None


def indices_periodo(eje: Sequence[Unidad], ini: Optional[date],
                    fin: Optional[date]) -> list[int]:
    """Columnas que TOCA el periodo `[ini, fin]` (basta un día dentro)."""
    if not (ini and fin):
        return []
    if fin < ini:
        ini, fin = fin, ini
    return [i for i, u in enumerate(eje) if u.inicio <= fin and u.fin >= ini]


def tramos_de_anio(eje: Sequence[Unidad]) -> list[tuple[int, int, int]]:
    """`(índice_inicial, índice_final, año)` de la fila de años del encabezado."""
    tramos: list[tuple[int, int, int]] = []
    for i, u in enumerate(eje):
        if tramos and tramos[-1][2] == u.anio:
            ini, _f, anio = tramos[-1]
            tramos[-1] = (ini, i, anio)
        else:
            tramos.append((i, i, u.anio))
    return tramos


def unidades_con_traslape(eje: Sequence[Unidad],
                          periodos: Sequence[tuple[date, date]]) -> set[int]:
    """Columnas donde DOS o más periodos se pisan por más de cero días.

    Se mira dentro de la columna, no en el conjunto del eje: un traslape de
    marzo no debe teñir el trimestre entero si la columna es mensual, y en una
    columna trimestral se tiñe porque ahí sí conviven.
    """
    validos = [(a, b) for a, b in periodos if a and b and b >= a]
    marcadas: set[int] = set()
    for i, u in enumerate(eje):
        recortes = [(max(a, u.inicio), min(b, u.fin)) for a, b in validos]
        recortes = [(a, b) for a, b in recortes if b >= a]
        for j in range(len(recortes)):
            for k in range(j + 1, len(recortes)):
                a = max(recortes[j][0], recortes[k][0])
                b = min(recortes[j][1], recortes[k][1])
                if dias_inclusivos(a, b) > 0:
                    marcadas.add(i)
                    break
            if i in marcadas:
                break
    return marcadas


# ── Hitos documentales (MEF / SEACE) ────────────────────────────────────────

def hito_firma(fx: Optional[dict]) -> Optional[date]:
    """Fecha de firma del contrato del expediente, en orden de autoridad:

      1. `contrato_emisor.fecha` — la vía CONTRATO ya ató emisor y expediente.
      2. `verificacion_expediente.contrato.fecha`, SOLO si ese contrato es del
         emisor (`veredicto == "ok"` o `elegido_por == "emisor"`): los contratos
         elegidos por heurística (`unico`, `mas_barato`) pueden ser de otro
         consultor del mismo expediente y pintarían una «C» que no es suya.
      3. La firma del proceso SEACE, si el proceso se localizó.
    """
    fx = fx if isinstance(fx, dict) else {}
    ce = fx.get("contrato_emisor")
    if isinstance(ce, dict) and fecha(ce.get("fecha")):
        return fecha(ce.get("fecha"))

    ver = fx.get("verificacion_expediente")
    contrato = (ver or {}).get("contrato") if isinstance(ver, dict) else None
    if isinstance(contrato, dict):
        del_emisor = (str(contrato.get("veredicto") or "").lower() == "ok"
                      or str(contrato.get("elegido_por") or "") == "emisor")
        if del_emisor and fecha(contrato.get("fecha")):
            return fecha(contrato.get("fecha"))

    seace = fx.get("seace") if isinstance(fx.get("seace"), dict) else {}
    proceso = seace.get("proceso") if isinstance(seace.get("proceso"), dict) else {}
    return fecha(proceso.get("fecha_firma") or seace.get("fecha_suscripcion"))


def hito_resolucion(fx: Optional[dict]) -> Optional[date]:
    """Fecha de la resolución que aprobó el expediente (leída o verificada)."""
    fx = fx if isinstance(fx, dict) else {}
    lect = fx.get("resolucion_aprobacion")
    if isinstance(lect, dict) and fecha(lect.get("fecha")):
        return fecha(lect.get("fecha"))
    ver = fx.get("verificacion_expediente")
    res = (ver or {}).get("resolucion") if isinstance(ver, dict) else None
    if isinstance(res, dict):
        return fecha(res.get("fecha"))
    return None


# ── Rótulos ─────────────────────────────────────────────────────────────────

def recortar(texto, largo: int = LARGO_PROYECTO) -> str:
    t = " ".join(str(texto or "").split())
    if not t:
        return "Proyecto sin nombre"
    return t if len(t) <= largo else t[:largo - 1].rstrip() + "…"


def ddmmaaaa(f: Optional[date]) -> str:
    return f.strftime("%d/%m/%Y") if f else "—"


def rotulo_experiencia(n_exp, proyecto, cui, notas: Sequence[str] = ()) -> str:
    """«N° · proyecto recortado · CUI 2418877 · nota · nota»."""
    partes = [str(n_exp if n_exp is not None else "?"),
              recortar(proyecto),
              f"CUI {cui}" if str(cui or "").strip() else SIN_CUI]
    partes.extend(n for n in notas if n)
    return " · ".join(partes)


def nota_hito_fuera(marca: str, f: Optional[date]) -> str:
    """«R 18/06/2025 fuera de rango» — el hito existe, pero no cabe en el eje."""
    return f"{marca} {ddmmaaaa(f)} fuera de rango"


def marcas_de_columna(marcas: dict[int, list[str]]) -> dict[int, str]:
    """Ordena las marcas de cada columna: primero «≈», luego «C», luego «R»."""
    orden = {MARCA_MES: 0, MARCA_FIRMA: 1, MARCA_RESOLUCION: 2}
    return {col: "".join(sorted(set(ms), key=lambda m: orden.get(m, 9)))
            for col, ms in marcas.items() if ms}
