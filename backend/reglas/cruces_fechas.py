"""
Cruces de fechas CONTRATO / EXPEDIENTE ↔ CERTIFICADO (T-011, «T-005» comercial).

Qué pregunta responde
─────────────────────
El certificado dice «el profesional trabajó del A al B». Las fuentes oficiales
dicen cuándo NACIÓ y cuándo MURIÓ documentalmente ese encargo:

  Regla A · «nadie supervisa antes de que el contrato exista»
            inicio declarado ≥ fecha de firma del contrato del proceso (SEACE).

  Regla B · «nadie sigue elaborando lo que ya está aprobado» (solo expedientes)
            término declarado ≤ fecha de la resolución que aprobó el expediente.

Las dos son SEÑALES, no veredictos: se suman al motor de alertas existente
(`pipeline.Observacion`, mismo esquema de las ALT) y al Excel. Ninguna de las
dos convierte una ausencia de datos en un incumplimiento.

Los tres principios que gobiernan el módulo
───────────────────────────────────────────
1. **Aritmética día-exacta, jamás truncada a mes.** Un inicio declarado el
   05/01 contra una firma del 30/01 «coincide» si solo se comparan meses, y son
   25 días que ninguna fuente respalda. Todas las comparaciones son entre
   `date` completos y las tolerancias se expresan en DÍAS.

2. **Gate anti-circularidad.** Cruzar fechas contra un proceso que no es el del
   certificado produce alertas contra el concurso equivocado — el peor fallo
   posible. Antes de pronunciarse, cada regla exige que la IDENTIDAD de su
   fuente esté confirmada **por señales independientes de la fecha que se va a
   cruzar**. Es el mismo criterio del CASO 0 de la tarea del RUC del
   adjudicatario y la lección del selector por solape (familia ADR-005): *lo que
   se verifica no puede elegir su propia identidad*.

3. **Abstención por defecto.** Sin fuente (proceso pre-2018, CUI sin procesos
   publicados, expediente sin verificar en el MEF, fecha ilegible) el resultado
   es `POR_CONFIRMAR` con la razón escrita en lenguaje de evaluador. Nunca una
   alerta «porque falta el dato», nunca un NO CUMPLE. Misma regla legal que el
   clamp del Paso 5: la falta de información es a favor del que declara.

Por qué la Regla A NO es la señal `temporal` del candado F5
───────────────────────────────────────────────────────────
`validacion/candado_seace.py` ya compara firma vs inicio, pero para decidir
**si el proceso es el del certificado** (identidad). Aquí la misma aritmética
decide otra cosa: **si lo que el certificado declara cabe dentro de lo que el
contrato permite** (sustancia). De ahí el gate: la Regla A solo habla cuando la
identidad del proceso está sostenida por las OTRAS señales fuertes (entidad,
adjudicatario, objeto). En esa configuración el candado global queda en
`contradice` — y el motivo de esa contradicción es exactamente lo que esta
regla nombra en lenguaje de evaluador, en vez de dejarlo dicho como «los
documentos no coinciden».

Consecuencia práctica, dicha sin adornos:
  · candado `confirmado`  → la Regla A concluye COINCIDE (las fechas cuadran).
  · candado `contradice` SOLO por la señal temporal, con ≥2 señales fuertes no
    temporales a favor → la Regla A DISPARA.
  · cualquier otro caso (`por_confirmar`, contradicción de entidad/objeto, job
    anterior a F5, sin proceso) → ABSTENCIÓN con nota.

Módulo PURO: sin red, sin disco, sin openpyxl. Recibe el enriquecimiento de una
experiencia (lo que ya persisten las etapas SEACE/InfoObras/MEF) y los campos
del certificado que trae el espejo.

⚠ Este módulo NO se re-exporta desde `reglas/__init__.py` a propósito: importa
`validacion.candado_seace`, y `validacion/__init__` importa `recalculo`, que a
su vez importa `reglas`. Colgarlo del `__init__` crearía un ciclo de imports
que solo se sostiene por el orden de las líneas. Se importa siempre explícito:
`from reglas.cruces_fechas import …`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from validacion.candado_seace import (
    A_FAVOR, CONFIRMADO, EN_CONTRA, FUERTE, MINIMO_SENALES_CONFIRMAR,
    TOLERANCIA_DIAS_FIRMA,
)

# ── Identificadores de las reglas (mismo esquema de código que las ALT) ───────

REGLA_INICIO = "FECHA_CONTRATO"
REGLA_TERMINO = "FECHA_APROBACION_ET"

TITULO_REGLA = {
    REGLA_INICIO: "El inicio declarado no puede ser anterior al contrato",
    REGLA_TERMINO: "El término declarado no puede ser posterior a la aprobación "
                   "del expediente",
}

# Preguntas tal como se leen en la tabla comparativa del Excel.
PREGUNTA_REGLA = {
    REGLA_INICIO: "¿EMPEZÓ DESPUÉS DE FIRMADO EL CONTRATO?",
    REGLA_TERMINO: "¿TERMINÓ ANTES DE APROBARSE EL EXPEDIENTE?",
}

# ── Resultados posibles (vocabulario cerrado, traducido en el Excel) ─────────

COINCIDE = "coincide"            # la fecha declarada cabe dentro de la oficial
DISPARA = "dispara"              # incoherencia real, con fuente confirmada
POR_CONFIRMAR = "por_confirmar"  # abstención: no hay con qué pronunciarse

# Cómo se lee cada resultado en la celda (cero enums crudos en el entregable).
RESPUESTA = {
    COINCIDE: "SÍ",
    DISPARA: "NO",
    POR_CONFIRMAR: "POR VERIFICAR",
}

# ── Tolerancias, en DÍAS COMPLETOS y cada una con su porqué ──────────────────

# Regla A. Se reutiliza LA MISMA vara del candado (15 días) a propósito: es el
# desfase habitual entre suscribir el contrato y el arranque efectivo del
# servicio (entrega de terreno, orden de inicio) que las constancias suelen
# redondear. Tener dos varas distintas para la misma comparación de fechas
# haría que el Excel dijera una cosa en el bloque del proceso y otra en la
# cronología — la inconsistencia visible que ya costó cara en los comparadores
# de nombres de empresa. Cambiar el valor aquí es cambiarlo en los dos sitios.
TOLERANCIA_DIAS_INICIO = TOLERANCIA_DIAS_FIRMA

# Regla B. Vara PROPIA porque mide otra cosa: no un arranque, sino el cierre
# administrativo del servicio. Entre la resolución que aprueba el expediente y
# la conformidad/liquidación que cierra el contrato del proyectista pasan días
# o semanas, y una constancia legítima puede certificar hasta ese cierre. Un
# mes cubre ese trámite; seguir «elaborando» meses o años después de aprobado
# el expediente es justamente lo que la regla existe para señalar.
TOLERANCIA_DIAS_APROBACION = 30

# Fecha de la aprobación: de dónde salió (se rotula en el Excel; la inferida a
# partir del nombre del archivo va en violeta, por convención de supuestos).
FUENTE_APROBACION_INFOOBRAS = (
    "documento del hito «Aprobación del proyecto» registrado en InfoObras")
FUENTE_APROBACION_MEF = (
    "resolución de aprobación publicada en el Formato 08-A del MEF")


@dataclass(frozen=True)
class Cruce:
    """Resultado de una regla sobre UNA experiencia, con su frase ya redactada.

    `fecha_declarada` / `fecha_fuente` viajan en ISO para que el Excel y el
    espejo puedan mostrarlas sin volver a calcular nada.
    """
    regla: str
    resultado: str                       # COINCIDE | DISPARA | POR_CONFIRMAR
    motivo: str
    fecha_declarada: Optional[str] = None
    fecha_fuente: Optional[str] = None
    dias: Optional[int] = None           # diferencia día-exacta (>0 = incoherente)
    fuente: Optional[str] = None         # de dónde salió `fecha_fuente`
    inferida: bool = False               # True → violeta (dato deducido)

    @property
    def respuesta(self) -> str:
        return RESPUESTA.get(self.resultado, "POR VERIFICAR")

    def como_dict(self) -> dict:
        """Forma persistida en `enriquecimiento[…]["cruces_fechas"]`."""
        d = {"regla": self.regla, "resultado": self.resultado, "motivo": self.motivo}
        for k in ("fecha_declarada", "fecha_fuente", "dias", "fuente"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        if self.inferida:
            d["inferida"] = True
        return d


# ── Utilidades de fecha (día completo SIEMPRE) ───────────────────────────────

def _fecha(v: Any) -> Optional[date]:
    """Fecha completa de un valor ISO/`date`/`datetime`. `None` si no parsea.

    No existe (ni debe existir) una variante «solo año-mes»: media fecha no es
    una fecha con la que se pueda concluir nada.
    """
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


_RE_DDMMAAAA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def fecha_en_texto(texto: Any) -> Optional[date]:
    """Fecha DD/MM/AAAA embebida en un texto libre (p. ej. el rótulo de una
    resolución: «R.G.R. N° 262-2023-GRH/GRI DE FECHA 14/08/2023»).

    Deliberadamente NO reconoce «2023» ni «08/2023»: un año o un mes sueltos
    invitarían a truncar, que es exactamente lo prohibido. Sin día no hay fecha.
    """
    m = _RE_DDMMAAAA.search(str(texto or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _dmy(f: Optional[date]) -> str:
    return f.strftime("%d/%m/%Y") if f else "—"


# ── Gate anti-circularidad de la Regla A ─────────────────────────────────────

def identidad_sostenida_sin_temporal(candado: Optional[dict]) -> tuple[bool, str]:
    """¿La identidad del proceso se sostiene SIN usar la señal de fechas?

    Devuelve `(pasa, motivo_si_no_pasa)`. Exige lo mismo que el candado para
    promover, pero ciego a `temporal`:
      · ≥ `MINIMO_SENALES_CONFIRMAR` señales FUERTES a favor que no sean
        temporales (entidad, adjudicatario, objeto);
      · CERO señales fuertes en contra que no sean temporales.

    Un job anterior a F5 (sin bloque `candado`) no pasa: no hay con qué
    sostener la identidad, y suponerla es exactamente lo que el gate impide.
    """
    if not isinstance(candado, dict) or not candado.get("senales"):
        return False, ("el sistema todavía no había verificado a qué proceso "
                       "corresponde este certificado")
    fuertes = [s for s in candado["senales"]
               if isinstance(s, dict) and s.get("fuerza") == FUERTE
               and s.get("nombre") != "temporal"]
    contra = [s for s in fuertes if s.get("sentido") == EN_CONTRA]
    favor = [s for s in fuertes if s.get("sentido") == A_FAVOR]
    if contra:
        return False, ("el proceso encontrado no corresponde al certificado por "
                       "razones ajenas a las fechas, así que compararlas diría "
                       "poco: " + " ".join(str(s.get("detalle") or "") for s in contra))
    if len(favor) < MINIMO_SENALES_CONFIRMAR:
        return False, (f"solo {len(favor)} de {MINIMO_SENALES_CONFIRMAR} señales "
                       f"independientes de la fecha confirman que el proceso sea "
                       f"el del certificado; cruzar fechas contra un proceso sin "
                       f"confirmar puede señalar el concurso equivocado")
    return True, ""


# ── Gate anti-circularidad de la Regla B ─────────────────────────────────────

def expediente_verificado(verificacion: Optional[dict]) -> tuple[bool, str]:
    """¿La verificación MEF confirma que ESTE expediente es el del certificado?

    Equivalente de la Regla B al gate de la A: exige que el MEF haya respondido
    (`verificado_en_mef`) **y** que el contratista del expediente coincida con
    el emisor de la constancia (`contratista.veredicto == "ok"`). Sin esa
    coincidencia se estaría midiendo el término declarado contra la aprobación
    del expediente de OTRA empresa.
    """
    if not isinstance(verificacion, dict):
        return False, ("esta experiencia no tiene verificación del expediente "
                       "contra el Banco de Inversiones del MEF")
    if not verificacion.get("verificado_en_mef"):
        return False, ("el MEF no publica contratos ni Formato 08-A para este "
                       "proyecto, así que no hay expediente que cotejar")
    veredicto = ((verificacion.get("contratista") or {}).get("veredicto"))
    if veredicto != "ok":
        return False, ("el MEF no confirma que quien emitió la constancia sea "
                       "el proyectista del expediente; comparar contra esa "
                       "aprobación sería comparar con otro encargo")
    return True, ""


# ── Fecha de aprobación del expediente ───────────────────────────────────────

def fecha_aprobacion_expediente(enr: Optional[dict]) -> tuple[Optional[date], str, bool]:
    """Fecha de la resolución que aprobó el expediente: `(fecha, fuente, inferida)`.

    Orden de preferencia, y el porqué de cada uno:

    0. `verificacion_expediente.resolucion.fecha` — la fecha escrita en la propia
       resolución del MEF, leída del PDF (capa de texto u OCR local). Es la
       fecha oficial de aprobación; no es deducida.
    1. `aprobacion_expediente.fecha` — el documento del hito «Aprobación del
       proyecto» de InfoObras. Trae día completo, pero se deduce del nombre del
       archivo (`…AAAAMMDD…`), que es la fecha de REGISTRO del documento y puede
       ser posterior a la de la resolución. Se marca `inferida=True` → violeta
       en el Excel. Que sea posterior juega a favor del que declara, así que
       usarla nunca inventa una incoherencia: solo puede callar una.
    2. Una fecha DD/MM/AAAA dentro del rótulo de la resolución del MEF. Muchas
       entidades escriben el número sin fecha («N° 262-2023-GRH/GRI»); en ese
       caso NO hay fecha y la regla se abstiene, en vez de deducir el año.

    Sin ninguna de las dos → `(None, "", False)`.
    """
    enr = enr or {}
    res = ((enr.get("verificacion_expediente") or {}).get("resolucion")) or {}
    if isinstance(res, dict):
        # 0. La fecha LEÍDA del propio documento (OCR/capa de texto de la
        #    resolución, `validacion.resolucion_aprobacion`): es la fecha oficial
        #    escrita en el acto que aprobó el expediente, no una deducción. Gana
        #    a la del hito de InfoObras, que sale del nombre del archivo.
        f = _fecha(res.get("fecha"))
        if f:
            return f, FUENTE_APROBACION_MEF, False
    aprob = enr.get("aprobacion_expediente")
    if isinstance(aprob, dict):
        f = _fecha(aprob.get("fecha"))
        if f:
            return f, FUENTE_APROBACION_INFOOBRAS, True
    if isinstance(res, dict):
        f = fecha_en_texto(res.get("documento")) or fecha_en_texto(res.get("numero"))
        if f:
            return f, FUENTE_APROBACION_MEF, False
    return None, "", False


# ── Regla A · inicio declarado vs firma del contrato ─────────────────────────

def evaluar_inicio_vs_contrato(seace: Optional[dict], cert: Optional[dict]) -> Cruce:
    """«Nadie supervisa antes de que el contrato exista.»

    `seace`: bloque `enriquecimiento[…]["seace"]`. `cert`: la experiencia del
    espejo (se usa `fecha_inicial`).
    """
    cert = cert or {}
    inicio = _fecha(cert.get("fecha_inicial"))

    def abstener(motivo: str) -> Cruce:
        return Cruce(REGLA_INICIO, POR_CONFIRMAR, motivo,
                     fecha_declarada=inicio.isoformat() if inicio else None)

    if not isinstance(seace, dict) or seace.get("estado") != "seleccionado":
        return abstener("no se identificó el proceso de contratación de esta "
                        "experiencia en los datos abiertos del Estado "
                        "(la cobertura empieza en 2018), así que no hay contrato "
                        "con el que comparar el inicio declarado")
    if not inicio:
        return abstener("el certificado no declara una fecha de inicio legible")

    firma = _fecha((seace.get("proceso") or {}).get("fecha_firma")
                   or seace.get("fecha_suscripcion"))
    if not firma:
        return abstener("el proceso identificado no publica la fecha en que se "
                        "firmó el contrato")

    pasa, porque = identidad_sostenida_sin_temporal(seace.get("candado"))
    if not pasa:
        return Cruce(REGLA_INICIO, POR_CONFIRMAR,
                     f"No se compara el inicio declarado ({_dmy(inicio)}) contra la "
                     f"firma del contrato ({_dmy(firma)}): {porque}.",
                     fecha_declarada=inicio.isoformat(),
                     fecha_fuente=firma.isoformat(),
                     fuente="proceso de contratación publicado (SEACE)")

    dias = (firma - inicio).days          # > 0 → se firmó DESPUÉS del inicio
    comun = dict(fecha_declarada=inicio.isoformat(), fecha_fuente=firma.isoformat(),
                 dias=dias, fuente="proceso de contratación publicado (SEACE)")
    if dias > TOLERANCIA_DIAS_INICIO:
        return Cruce(
            REGLA_INICIO, DISPARA,
            f"El profesional declara haber iniciado el {_dmy(inicio)}, pero el "
            f"contrato del proceso se firmó el {_dmy(firma)}: {dias} días después. "
            f"No se puede prestar el servicio de un contrato que todavía no existe. "
            f"(Se admite un desfase de hasta {TOLERANCIA_DIAS_INICIO} días por la "
            f"entrega de terreno u orden de inicio.)", **comun)
    if dias > 0:
        return Cruce(
            REGLA_INICIO, COINCIDE,
            f"El inicio declarado ({_dmy(inicio)}) antecede en {dias} día(s) a la "
            f"firma del contrato ({_dmy(firma)}), dentro del margen admitido de "
            f"{TOLERANCIA_DIAS_INICIO} días por la entrega de terreno u orden de "
            f"inicio.", **comun)
    return Cruce(
        REGLA_INICIO, COINCIDE,
        f"El contrato del proceso se firmó el {_dmy(firma)} y el profesional "
        f"declara haber iniciado el {_dmy(inicio)}, después de esa firma.", **comun)


# ── Regla B · término declarado vs aprobación del expediente ─────────────────

def evaluar_termino_vs_aprobacion(enr: Optional[dict], cert: Optional[dict]) -> Optional[Cruce]:
    """«Nadie sigue elaborando lo que ya está aprobado.»

    Solo aplica a experiencias de EXPEDIENTE técnico. Devuelve `None` cuando la
    experiencia no lo es — una experiencia de supervisión o de ejecución de obra
    no tiene por qué aparecer con una pregunta que no le toca.

    Se considera experiencia de expediente si el pipeline dejó alguna huella de
    expediente: la verificación MEF, el documento de aprobación de InfoObras, o
    un proceso SEACE clasificado como expediente.
    """
    enr, cert = enr or {}, cert or {}
    seace = enr.get("seace") if isinstance(enr.get("seace"), dict) else {}
    es_expediente = bool(
        enr.get("verificacion_expediente") or enr.get("aprobacion_expediente")
        or seace.get("proceso_objeto") == "expediente")
    if not es_expediente:
        return None

    fin = _fecha(cert.get("fecha_final"))
    aprob, fuente, inferida = fecha_aprobacion_expediente(enr)

    def abstener(motivo: str) -> Cruce:
        return Cruce(REGLA_TERMINO, POR_CONFIRMAR, motivo,
                     fecha_declarada=fin.isoformat() if fin else None,
                     fecha_fuente=aprob.isoformat() if aprob else None,
                     fuente=fuente or None, inferida=inferida)

    if not fin:
        return abstener("el certificado no declara una fecha de término legible")

    # La RESOLUCIÓN LEÍDA (validacion.resolucion_aprobacion) es la identidad más
    # directa que existe: el acto que aprobó el expediente dice quién lo elaboró.
    #   · nombra al emisor → identidad confirmada por documento oficial: se compara;
    #   · nombra a OTRO   → comparar sería medir contra el encargo de otra empresa:
    #                        abstención con la razón escrita;
    #   · no nombra a nadie → decide el gate del contrato (como antes).
    lectura = enr.get("resolucion_aprobacion")
    lectura = lectura if isinstance(lectura, dict) else {}
    if lectura.get("coincide_emisor") == "nombra_otro":
        return abstener(
            f"No se compara el término declarado ({_dmy(fin)}) contra la aprobación: "
            "la resolución que aprobó el expediente nombra como consultor a "
            f"{str(lectura.get('detalle_emisor') or 'otra empresa')[:90]}, no a quien "
            "emitió la constancia; confirmar quién elaboró este expediente.")
    if lectura.get("coincide_emisor") == "confirma":
        pasa, porque = True, ""
    else:
        pasa, porque = expediente_verificado(enr.get("verificacion_expediente"))
    if not pasa:
        return abstener(f"No se compara el término declarado ({_dmy(fin)}) contra "
                        f"la aprobación del expediente: {porque}.")
    if not aprob:
        return abstener(
            "El expediente está verificado en el MEF, pero la resolución que lo "
            "aprobó figura solo con su número, sin fecha; no se puede comparar "
            "contra el término declarado sin inventar el día.")

    dias = (fin - aprob).days             # > 0 → siguió DESPUÉS de la aprobación
    comun = dict(fecha_declarada=fin.isoformat(), fecha_fuente=aprob.isoformat(),
                 dias=dias, fuente=fuente, inferida=inferida)
    if dias > TOLERANCIA_DIAS_APROBACION:
        return Cruce(
            REGLA_TERMINO, DISPARA,
            f"El profesional declara haber elaborado el expediente hasta el "
            f"{_dmy(fin)}, pero el expediente ya estaba aprobado el {_dmy(aprob)}: "
            f"{dias} días antes. No se sigue elaborando un expediente ya aprobado. "
            f"(Se admiten hasta {TOLERANCIA_DIAS_APROBACION} días por el cierre "
            f"administrativo del servicio.) Fuente de la aprobación: {fuente}.",
            **comun)
    if dias > 0:
        return Cruce(
            REGLA_TERMINO, COINCIDE,
            f"El término declarado ({_dmy(fin)}) excede en {dias} día(s) la "
            f"aprobación del expediente ({_dmy(aprob)}), dentro del margen "
            f"admitido de {TOLERANCIA_DIAS_APROBACION} días por el cierre "
            f"administrativo. Fuente de la aprobación: {fuente}.", **comun)
    return Cruce(
        REGLA_TERMINO, COINCIDE,
        f"El profesional declara haber terminado el {_dmy(fin)} y el expediente "
        f"se aprobó el {_dmy(aprob)}, después de ese término. Fuente de la "
        f"aprobación: {fuente}.", **comun)


# ── Punto de entrada del motor ───────────────────────────────────────────────

def cruces_de_experiencia(enr: Optional[dict], cert: Optional[dict]) -> list[Cruce]:
    """Los cruces de fechas que corresponden a UNA experiencia.

    La Regla A siempre se pronuncia (aunque sea abstiniéndose: el evaluador
    tiene que saber que no se pudo comprobar). La Regla B solo aparece cuando la
    experiencia es de expediente técnico.
    """
    enr = enr or {}
    salida = [evaluar_inicio_vs_contrato(enr.get("seace"), cert)]
    b = evaluar_termino_vs_aprobacion(enr, cert)
    if b is not None:
        salida.append(b)
    return salida
