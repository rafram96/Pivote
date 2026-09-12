"""
Cruces de fechas CONTRATO / EXPEDIENTE ↔ CERTIFICADO (T-011, «T-005» comercial).

Qué pregunta responde
─────────────────────
El certificado dice «el profesional trabajó del A al B». Las fuentes oficiales
dicen cuándo NACIÓ y cuándo MURIÓ documentalmente ese encargo:

  Regla A · «nadie supervisa antes de que el contrato exista»
            inicio declarado ≥ fecha de firma del contrato del proceso (SEACE),
            o —cuando SEACE no identificó el proceso— del contrato del
            expediente publicado por el MEF, si ese contrato es del emisor de la
            constancia. Un contrato de otra empresa no sirve de vara: se dice y
            se calla.

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

3. **Abstención por defecto.** Sin fuente (consulta sin procesos devueltos,
   expediente sin verificar en el MEF, fecha ilegible) el resultado
   es `POR_CONFIRMAR` con la razón escrita en lenguaje de evaluador. Nunca una
   alerta «porque falta el dato», nunca un NO CUMPLE. Misma regla legal que el
   clamp del Paso 5: la falta de información es a favor del que declara.

Por qué la Regla A NO es la señal `temporal` del candado F5
───────────────────────────────────────────────────────────
`validacion/candado_seace.py` conserva firma vs inicio como señal débil; no
decide identidad con esa fecha. Aquí se presenta el contraste fecha declarada
vs contrato solo cuando la identidad está sostenida por señales independientes
(entidad, adjudicatario, objeto). Identidad confirmada puede coexistir con
discrepancia temporal: no significa que las fechas coincidan ni que el
profesional incumpla. Los jobs antiguos que persistieron temporal como fuerte
se tratan por sus señales no temporales, no por su rótulo global.

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
    TOLERANCIA_DIAS_FIRMA, candado_tiene_adjudicatario_favorable,
    hay_varios_contratos_distintos,
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

# Fecha de la FIRMA con la que juega la Regla A: de dónde salió.
FUENTE_FIRMA_SEACE = "proceso de contratación publicado (SEACE)"
FUENTE_FIRMA_CONTRATO_MEF = "contrato del expediente (MEF)"

# Constante heredada para compatibilidad; no establece por qué una consulta
# concreta no devolvió procesos y ya no se usa para construir ese motivo.
COBERTURA_SEACE_DESDE = 2018

# Veredictos de `verificacion_expediente.contrato` que significan «este contrato
# es del emisor de la constancia». `scraping.mef` rotula hoy `ok`; el rótulo
# `coincide` y el campo `elegido_por` son la nomenclatura nueva. Se aceptan los
# tres para no depender del orden en que aterricen los cambios.
VEREDICTOS_CONTRATO_DEL_EMISOR = ("coincide", "ok")

# Frase de cierre de la Regla A cuando dispara. Una experiencia de expediente NO
# se «supervisa» ni «presta un servicio»: se elabora, y lo que falta es la firma.
FRASE_SIN_CONTRATO_OBRA = (
    "No se puede prestar el servicio de un contrato que todavía no existe.")
FRASE_SIN_CONTRATO_EXPEDIENTE = (
    "No se puede elaborar un expediente cuyo contrato aún no se ha firmado.")


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
    # Algunos jobs persisten el resumen bajo `proceso`; aceptar ambas formas
    # mantiene la guarda también para candados históricos enriquecidos.
    if candado.get("contratos_multiples") is True:
        return False, ("el proceso publica varios contratos distintos; las "
                       "coincidencias de metadatos no identifican cuál encargo "
                       "corresponde al certificado")
    if (hay_varios_contratos_distintos(candado)
            or hay_varios_contratos_distintos(candado.get("proceso"))):
        return False, ("el proceso publica varios contratos distintos; las "
                       "coincidencias de metadatos no identifican cuál encargo "
                       "corresponde al certificado")
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
    if {s.get("nombre") for s in favor} <= {"entidad", "objeto"}:
        return False, ("la identidad solo coincide por entidad y objeto; sin "
                       "una evidencia independiente adicional no se cruzan "
                       "fechas contra este proceso")
    if not candado_tiene_adjudicatario_favorable(candado):
        return False, ("no hay una señal fuerte a favor del adjudicatario; no se "
                       "cruzan fechas contra un proceso sin adjudicatario cotejado")
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
    if verificacion.get("estado") == "no_recontrastado":
        return False, "el cruce MEF no se ha actualizado tras corregir la identidad; no se reutiliza el del proyecto anterior"
    if verificacion.get("estado") == "recontrastado" and not verificacion.get("verificado_en_mef"):
        return False, str(verificacion.get("motivo") or "la nueva consulta MEF no permitió asociar el contrato exacto")
    if verificacion.get("estado") == "recontrastado" and verificacion.get("aprobacion_identificada") is not True:
        return False, "el contrato fue recontrastado, pero la aprobación de este encargo aún no se identificó por contenido; no se usa la fecha de un enlace candidato"
    if not verificacion.get("verificado_en_mef"):
        return False, ("este análisis no dispone de contratos ni Formato 08-A para este "
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

def es_experiencia_de_expediente(enr: Optional[dict], cert: Optional[dict]) -> bool:
    """¿La experiencia es de ELABORACIÓN DE EXPEDIENTE?

    Solo se usa para REDACTAR (elegir entre «prestar el servicio» y «elaborar el
    expediente»); jamás para decidir si una regla se pronuncia. Por eso puede
    mirar también lo que declara el certificado, que no es una fuente oficial.
    """
    enr, cert = enr or {}, cert or {}
    seace = enr.get("seace") if isinstance(enr.get("seace"), dict) else {}
    tipo = str(cert.get("tipo_experiencia") or "").strip().lower()
    return bool("expediente" in tipo
                or enr.get("verificacion_expediente")
                or enr.get("aprobacion_expediente")
                or seace.get("proceso_objeto") == "expediente")


def motivo_sin_proceso_seace(cert: Optional[dict], es_expediente: bool) -> str:
    """Por qué la Regla A no tiene contrato del proceso con el que comparar.

    La fecha del certificado no demuestra la causa de una búsqueda sin
    resultados. Se mantiene ``cert`` por compatibilidad, sin usarlo para
    atribuir la ausencia a la cobertura del portal. Termina en punto porque
    el Excel concatena este motivo con el de la Regla B.
    """
    sujeto = "de este expediente" if es_expediente else "de esta experiencia"
    return (f"no se halló el proceso de contratación {sujeto} en los datos "
            "abiertos de SEACE en esta consulta; esto no demuestra que no "
            "exista ni establece la causa. No se obtuvo un contrato con el "
            "que comparar el inicio declarado.")


def firma_de_contrato_mef(enr: Optional[dict]) -> tuple[Optional[date], Optional[str]]:
    """Firma del contrato del expediente publicado por el MEF, para la Regla A.

    Devuelve `(firma, motivo_de_abstención)`:
      · `(fecha, None)`  → hay contrato CON fecha y es del emisor de la
        constancia: sirve de firma aunque SEACE no haya identificado el proceso.
      · `(None, motivo)` → el MEF publica un contrato para el CUI, pero de otro
        contratista: compararlo mediría el inicio declarado contra el encargo de
        otra empresa (el mismo gate anti-circularidad de siempre).
      · `(None, None)`   → no hay contrato publicado, o no trae fecha.

    Precedencia: `contrato_emisor` (el contrato que RESOLVIÓ la vía CONTRATO —
    ya ató emisor y expediente, así que su identidad no está en discusión) manda
    sobre el contrato que la ficha del MEF eligió por su cuenta, que con varios
    contratos por CUI puede no ser el mismo.
    """
    enr = enr or {}
    ce = enr.get("contrato_emisor")
    if isinstance(ce, dict):
        f = _fecha(ce.get("fecha"))
        if f:
            return f, None
    ct = (enr.get("verificacion_expediente") or {}).get("contrato")
    if not isinstance(ct, dict):
        return None, None
    f = _fecha(ct.get("fecha_suscripcion") or ct.get("fecha"))
    if not f:
        return None, None
    # `veredicto == "ok"` = el contratista del contrato es el emisor;
    # `elegido_por == "emisor"` = así se eligió entre los del expediente. Los
    # otros `elegido_por` (`unico`, `mas_barato`) son heurísticas de selección,
    # no evidencia de identidad — y contra ellas no se cruza nada.
    del_emisor = (ct.get("veredicto") in VEREDICTOS_CONTRATO_DEL_EMISOR
                  or ct.get("elegido_por") == "emisor")
    if not del_emisor:
        return None, ("el único contrato publicado por el MEF es de otro "
                      "contratista; no se compara")
    return f, None


def _veredicto_inicio(inicio: date, firma: date, fuente: str, sujeto: str,
                      es_expediente: bool) -> Cruce:
    """Aritmética y redacción compartidas por las dos fuentes de firma."""
    dias = (firma - inicio).days          # > 0 → se firmó DESPUÉS del inicio
    comun = dict(fecha_declarada=inicio.isoformat(), fecha_fuente=firma.isoformat(),
                 dias=dias, fuente=fuente)
    if dias > TOLERANCIA_DIAS_INICIO:
        return Cruce(
            REGLA_INICIO, DISPARA,
            f"El profesional declara haber iniciado el {_dmy(inicio)}, pero "
            f"{sujeto} se firmó el {_dmy(firma)}: {dias} días después. "
            f"{FRASE_SIN_CONTRATO_EXPEDIENTE if es_expediente else FRASE_SIN_CONTRATO_OBRA} "
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
        f"{sujeto[0].upper()}{sujeto[1:]} se firmó el {_dmy(firma)} y el "
        f"profesional declara haber iniciado el {_dmy(inicio)}, después de esa "
        f"firma.", **comun)


def evaluar_inicio_vs_contrato(seace: Optional[dict], cert: Optional[dict],
                               enr: Optional[dict] = None) -> Cruce:
    """«Nadie supervisa antes de que el contrato exista.»

    `seace`: bloque `enriquecimiento[…]["seace"]`. `cert`: la experiencia del
    espejo (se usa `fecha_inicial`). `enr`: el enriquecimiento COMPLETO de la
    experiencia — opcional, y solo para la segunda fuente de firma: cuando SEACE
    no identificó el proceso pero el MEF publica el contrato del expediente y
    ese contrato es del emisor de la constancia, esa firma es tan oficial como
    la del proceso y la regla puede pronunciarse igual.
    """
    cert = cert or {}
    enr = enr or {}
    inicio = _fecha(cert.get("fecha_inicial"))
    es_exp = es_experiencia_de_expediente(enr, cert)

    def abstener(motivo: str) -> Cruce:
        return Cruce(REGLA_INICIO, POR_CONFIRMAR, motivo,
                     fecha_declarada=inicio.isoformat() if inicio else None)

    if not isinstance(seace, dict) or seace.get("estado") != "seleccionado":
        firma_mef, porque_mef = firma_de_contrato_mef(enr)
        if firma_mef:
            if not inicio:
                return abstener("el certificado no declara una fecha de inicio "
                                "legible.")
            return _veredicto_inicio(
                inicio, firma_mef, FUENTE_FIRMA_CONTRATO_MEF,
                "el contrato del expediente publicado por el MEF", es_exp)
        base = motivo_sin_proceso_seace(cert, es_exp)
        if porque_mef:
            return abstener(f"{base} Además, {porque_mef}.")
        return abstener(base)
    if not inicio:
        return abstener("el certificado no declara una fecha de inicio legible.")

    firma = _fecha((seace.get("proceso") or {}).get("fecha_firma")
                   or seace.get("fecha_suscripcion"))
    if not firma:
        return abstener("este análisis no dispone de la fecha en que se "
                        "firmó el contrato.")

    pasa, porque = identidad_sostenida_sin_temporal(seace.get("candado"))
    if not pasa:
        return Cruce(REGLA_INICIO, POR_CONFIRMAR,
                     f"No se compara el inicio declarado ({_dmy(inicio)}) contra la "
                     f"firma del contrato ({_dmy(firma)}): {porque}.",
                     fecha_declarada=inicio.isoformat(),
                     fecha_fuente=firma.isoformat(),
                     fuente=FUENTE_FIRMA_SEACE)

    return _veredicto_inicio(inicio, firma, FUENTE_FIRMA_SEACE,
                             "el contrato del proceso", es_exp)


# ── Regla B · término declarado vs aprobación del expediente ─────────────────

def _referencia_termino(fin: date, aprob: date) -> str:
    """Frase informativa que acompaña a una abstención con las DOS fechas ya en
    la mano. No es un veredicto: nombra la distancia y se calla."""
    dias = (fin - aprob).days
    if dias == 0:
        return (f"Referencia: el término declarado ({_dmy(fin)}) es el mismo día "
                f"de la aprobación publicada ({_dmy(aprob)}).")
    rel = "posterior" if dias > 0 else "anterior"
    return (f"Referencia: el término declarado ({_dmy(fin)}) es {abs(dias)} días "
            f"{rel} a la aprobación publicada ({_dmy(aprob)}).")


def _motivo_sin_fecha_de_aprobacion(enr: dict) -> str:
    """Por qué no hay fecha de aprobación con la que comparar el término.

    Tres situaciones DISTINTAS que antes se contaban con la misma frase, y esa
    frase («figura solo con su número») mentía en dos de ellas — el Excel llegó
    a decir «figura solo con su número» con la celda de resolución en «—»:

      1. el MEF no publica resolución alguna (`resolucion` sin número ni fecha);
      2. la publica, pero solo con su número (la de siempre);
      3. la fecha se LEYÓ y se descartó por implausible
         (`resolucion_aprobacion.fecha_descartada` / `fecha_motivo`).
    """
    res = ((enr.get("verificacion_expediente") or {}).get("resolucion")) or {}
    res = res if isinstance(res, dict) else {}
    lectura = enr.get("resolucion_aprobacion")
    lectura = lectura if isinstance(lectura, dict) else {}

    descartada = _fecha(lectura.get("fecha_descartada"))
    if descartada:
        porque = str(lectura.get("fecha_motivo")
                     or "no es coherente con el número ni con el contrato")
        return (f"La fecha leída en la resolución ({_dmy(descartada)}) no es "
                f"plausible: {porque.strip().rstrip('.')}; se omite el cruce.")
    if not (res.get("numero") or res.get("documento") or res.get("fecha")):
        return ("Este análisis no dispone de una resolución de aprobación "
                "utilizable; no se puede comparar el término.")
    return ("El expediente está verificado en el MEF, pero la resolución que lo "
            "aprobó figura solo con su número, sin fecha; no se puede comparar "
            "contra el término declarado sin inventar el día.")

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
        return abstener("el certificado no declara una fecha de término legible.")

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
        motivo = (f"No se compara el término declarado ({_dmy(fin)}) contra "
                  f"la aprobación del expediente: {porque}.")
        # La resolución NO nombra a nadie: la abstención se mantiene (no se sabe
        # si esa aprobación es de este encargo), pero el evaluador merece ver el
        # número que está dejando de usarse — es la diferencia entre «no se pudo
        # comprobar» y «no se pudo comprobar, y por 80 días».
        if lectura.get("coincide_emisor") == "no_nombra" and aprob:
            motivo += " " + _referencia_termino(fin, aprob)
        return abstener(motivo)
    if not aprob:
        return abstener(_motivo_sin_fecha_de_aprobacion(enr))

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
    if enr.get("servicio_fase_incompatible"):
        motivo = ("El certificado declara un servicio de otra fase. No se contrastan "
                  "sus fechas con documentos de la ruta del concurso como si fueran "
                  "el mismo servicio; confirmar el sustento correspondiente.")
        reglas = [REGLA_INICIO]
        if enr.get("camino") == "expediente":
            reglas.append(REGLA_TERMINO)
        return [Cruce(regla, POR_CONFIRMAR, motivo) for regla in reglas]
    salida = [evaluar_inicio_vs_contrato(enr.get("seace"), cert, enr)]
    b = evaluar_termino_vs_aprobacion(enr, cert)
    if b is not None:
        salida.append(b)
    return salida
