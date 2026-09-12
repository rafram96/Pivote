"""
Candado determinístico de identidad CERTIFICADO ↔ PROCESO SEACE (T-004 F5).

El problema que resuelve
────────────────────────
Hasta F2 el proceso SEACE se elegía por **CUI + tipo** (`seleccionar_proceso`).
Eso evita cruzar de tipo, pero NADA confirmaba que el proceso elegido fuera de
verdad el que respalda el certificado que se está evaluando: un CUI puede tener
varios procesos del mismo tipo, y un CUI mal resuelto arrastra al proceso
equivocado. Promover las Bases/Contrato de otro concurso como evidencia
verificada es el peor fallo posible del sistema — el mismo patrón que el veto de
rubro del resolver (ADR-013).

Confirmación ASIMÉTRICA
───────────────────────
Promover exige señales; degradar es el default. El candado NUNCA bloquea la
descarga (los PDF igual van al ZIP como sustento): lo único que decide es el
**rótulo de confianza** del Excel y del índice.

    confirmado    ≥2 señales FUERTES a favor y CERO en contra
    contradice    ≥1 señal FUERTE en contra (se muestra como «Por confirmar»
                  + alerta: una contradicción se señala, no se esconde)
    por_confirmar todo lo demás — incluida la falta de datos

La zona gris de similitud jamás decide: produce `sin_dato`, no una señal.

Las señales
───────────
FUERTES

  entidad        Entidad convocante del proceso vs entidad CONTRATANTE que
                 declara el certificado. Comparador: `score_match_empresa` de
                 `scraping/sunat.py`.
                 ⚠ Se reutiliza EL DE SUNAT a propósito. `scraping/mef.py` tiene
                 otro comparador de nombres (`_similitud`/tokens de proyecto),
                 pero está afinado para NOMBRES DE OBRA («mejoramiento de los
                 servicios de salud de…»), no para razones sociales: no quita
                 sufijos legales (S.A., E.I.R.L.) ni normaliza la puntuación de
                 una denominación. El de SUNAT sí, que es exactamente el
                 problema aquí («GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL» vs
                 «GOB. REG. JUNÍN»).

  adjudicatario  RUC del EMISOR del certificado == RUC de un adjudicatario del
                 proceso. Es la pata «entidad emisora» de la señal de entidad y
                 en la práctica la más contundente, porque es una igualdad de
                 RUC, no un parecido de texto: en una constancia de terceros el
                 emisor es la supervisora que ganó ese proceso (caso real Pedro
                 Sánchez Meza: INSTITUTO DE CONSULTORIA S.A., RUC 20263373058,
                 figura como `supplier` del proceso AS-SM-28-2021-GRJ-CS-1).
                 SOLO puede sumar a favor: que el RUC del emisor no figure NO es
                 contradicción — una constancia legítima puede emitirla un
                 consorciado con RUC propio o la entidad contratante misma.

  objeto         Tipo de proceso esperado por la experiencia vs tipo real del
                 proceso elegido. La segmentación estricta ya vive en
                 `seleccionar_proceso`; aquí se vuelve a verificar de forma
                 INDEPENDIENTE (defensa en profundidad: si alguna vez se toca el
                 selector, el candado sigue siendo el que responde).

DÉBIL

  temporal       Coherencia de fechas, en DÍAS COMPLETOS (ver abajo). Conserva
                 la evidencia exacta, pero nunca confirma ni contradice por sí
                 sola la identidad del proceso.

  monto          Monto del proceso vs monto del contrato que declara el
                 certificado, si AMBOS lados lo publican. Nunca veta y nunca
                 alcanza para promover por sí sola: el certificado suele
                 declarar el monto de la OBRA supervisada y el proceso el de la
                 SUPERVISIÓN — dos cifras legítimamente distintas.

Aritmética temporal: DÍAS COMPLETOS, jamás meses
────────────────────────────────────────────────
Truncar a mes valida días que ninguna fuente respalda: un profesional que
declara desde el 05/01 con respaldo real desde el 30/01 «coincide» si solo se
compara enero, y son 25 días inventados. `dateSigned` y las fechas de
convocatoria traen día completo, así que se comparan como fechas completas.
La tolerancia se expresa en DÍAS (`TOLERANCIA_DIAS_FIRMA`).

Este módulo es PURO: no toca red ni disco. Recibe un resumen del proceso
(`resumen_proceso`, que sí sabe de la forma OCDS) y los campos del certificado
que ya extrae el espejo.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from validacion.servicio_experiencia import evidencia_tipo_servicio

# ── Umbrales, todos con su porqué ────────────────────────────────────────────

# Parecido de razón social suficiente para dar la entidad por la misma. Es el
# mismo umbral que `scraping/sunat.py` documenta como «match fuerte» y el que
# usa el resolver de CUI (`cui.py::_mismo_nombre_empresa`) — no se inventa uno
# nuevo para esta señal.
UMBRAL_ENTIDAD_A_FAVOR = 85

# Por debajo de esto los nombres no se parecen en nada y la contradicción es
# real («GOBIERNO REGIONAL DE JUNIN» vs «MUNICIPALIDAD DISTRITAL DE PUNO»). El
# tramo 60–84 es ZONA GRIS: ni confirma ni contradice — `sin_dato`.
UMBRAL_ENTIDAD_EN_CONTRA = 60

# Tolerancia de la señal temporal, EN DÍAS COMPLETOS.
# 15 días = media quincena. Cubre el desfase habitual entre la suscripción del
# contrato y el inicio de servicio que registra la constancia (entrega de
# terreno, orden de inicio), sin llegar a un mes: un mes entero es justamente
# el error que se quiere evitar — con 30 días, «firma 30/01 vs inicio declarado
# 05/01» pasaría, que es el caso borde que el truncado a mes daba por bueno.
TOLERANCIA_DIAS_FIRMA = 15

# Diferencia relativa que se considera «el mismo orden de magnitud» para la
# señal débil de monto. Amplia a propósito: adicionales, reajustes y el IGV
# mueven la cifra sin que sea otro contrato.
TOLERANCIA_MONTO = 0.20

CONFIRMADO = "confirmado"
POR_CONFIRMAR = "por_confirmar"
CONTRADICE = "contradice"

A_FAVOR = "a_favor"
EN_CONTRA = "en_contra"
SIN_DATO = "sin_dato"

FUERTE = "fuerte"
DEBIL = "debil"

# Señales fuertes a favor necesarias para promover. Dos, nunca una: cualquiera
# de ellas por separado se cumple por casualidad con demasiada facilidad (todo
# proceso de un CUI de salud es de salud; casi todo proceso de supervisión de
# una obra larga solapa el periodo declarado).
MINIMO_SENALES_CONFIRMAR = 2


@dataclass(frozen=True)
class Senal:
    """Una señal evaluada, con su frase para el evaluador ya redactada."""
    nombre: str
    fuerza: str          # FUERTE | DEBIL
    sentido: str         # A_FAVOR | EN_CONTRA | SIN_DATO
    detalle: str

    def como_dict(self) -> dict:
        return {"nombre": self.nombre, "fuerza": self.fuerza,
                "sentido": self.sentido, "detalle": self.detalle}


@dataclass(frozen=True)
class Candado:
    resultado: str
    motivo: str
    senales: list[Senal] = field(default_factory=list)
    contratos_multiples: bool = False

    @property
    def a_favor(self) -> list[Senal]:
        return [s for s in self.senales
                if s.fuerza == FUERTE and s.sentido == A_FAVOR]

    @property
    def en_contra(self) -> list[Senal]:
        return [s for s in self.senales
                if s.fuerza == FUERTE and s.sentido == EN_CONTRA]

    def como_dict(self) -> dict:
        """Forma persistida en `enriquecimiento[…]["seace"]["candado"]`."""
        salida = {"resultado": self.resultado, "motivo": self.motivo,
                  "senales": [s.como_dict() for s in self.senales]}
        if self.contratos_multiples:
            salida["contratos_multiples"] = True
        return salida


# ── Extracción del resumen del proceso (conoce la forma OCDS) ────────────────

def _texto(v: Any) -> str:
    return str(v or "").strip()


def _fecha(v: Any) -> Optional[date]:
    """Fecha de un valor OCDS/ISO/`date`. Día completo — nunca se trunca a mes."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _texto(v)[:10]
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _numero(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _solo_digitos(v: Any) -> str:
    return "".join(c for c in _texto(v) if c.isdigit())


def _ruc(v: Any) -> Optional[str]:
    """RUC peruano normalizado (11 dígitos). Los identificadores OCDS vienen
    como `PE-RUC-20263373058`, pero también como `PE-RUC-466064` — códigos de
    consorcio de 6 dígitos que NO son RUC y no deben compararse como tales."""
    d = _solo_digitos(v)
    return d if len(d) == 11 else None


def resumen_proceso(comp: dict) -> dict:
    """Identidad estructurada del proceso OCDS elegido, para persistir junto al
    bloque `seace` y poder re-evaluar el candado sin volver a la red.

    F5 NO lee PDFs: todo sale de la metadata que la fuente ya publica.

    ⚠ La ventana del proceso abarca TODOS sus contratos, no `contracts[0]`.
    El orden que devuelve la fuente es arbitrario y un proceso suele traer más
    de un contrato (el original y su liquidación/adenda). Caso real medido el
    2026-08-05 (CUI 2343407, proceso CP-SM-9-2017-PRONIS-1): `contracts[0]` es
    un registro de DOS DÍAS de 2024 y `contracts[1]` el contrato de verdad
    (18/04/2018 – 01/05/2020). Quedarse con el primero convertía dos
    experiencias legítimas en «NO COINCIDE». Es el mismo criterio que ya usa
    `seace_abierto._periodo_proceso` para desempatar en el selector.
    La FIRMA es la más TEMPRANA: la referencia de «nadie supervisa antes de que
    el contrato exista» es el contrato original, no una adenda posterior.
    """
    comp = comp or {}
    tender = comp.get("tender") or {}
    contratos = [c for c in (comp.get("contracts") or []) if isinstance(c, dict)]
    contrato = contratos[0] if contratos else {}

    firmas = [f for f in (_fecha(c.get("dateSigned")) for c in contratos) if f]
    inicios = [f for f in (_fecha((c.get("period") or {}).get("startDate"))
                           for c in contratos) if f]
    fines = [f for f in (_fecha((c.get("period") or {}).get("endDate"))
                         for c in contratos) if f]
    periodo = {"startDate": min(inicios) if inicios else None,
               "endDate": max(fines) if fines else None}
    contrato = {**contrato, "dateSigned": min(firmas) if firmas else None}

    adjudicatarios: list[dict[str, str]] = []

    def agregar_adjudicatario(proveedor: dict, origen: str) -> None:
        proveedor = proveedor or {}
        identificador = proveedor.get("identifier") or {}
        r = _ruc(identificador.get("id") or proveedor.get("id"))
        if not r:
            return
        nombre = (_texto(proveedor.get("name"))
                  or _texto(identificador.get("legalName")))
        existente = next((x for x in adjudicatarios if x["ruc"] == r), None)
        if existente:
            # Awards/contracts suelen traer el nombre cuando `parties` no lo
            # hace. Completar es aditivo; jamás sustituir un nombre ya leído.
            if not existente.get("nombre") and nombre:
                existente["nombre"] = nombre
            return
        adjudicatarios.append({"ruc": r, "nombre": nombre, "origen": origen})

    for parte in comp.get("parties") or []:
        roles = [str(r).lower() for r in (parte.get("roles") or [])]
        if "supplier" in roles:
            agregar_adjudicatario(parte, "parties")
    for premio in comp.get("awards") or []:
        for prov in premio.get("suppliers") or []:
            agregar_adjudicatario(prov, "awards")
    for c in contratos:
        for prov in c.get("suppliers") or []:
            agregar_adjudicatario(prov, "contracts")

    # Suma de todos los contratos (mismo motivo que la ventana: `contracts[0]`
    # es arbitrario). Sin contratos, el valor referencial del tender.
    montos = [m for m in (_numero((c.get("value") or {}).get("amount"))
                          for c in contratos) if m]
    monto = sum(montos) if montos else _numero((tender.get("value") or {}).get("amount"))

    # Estos metadatos se conservan para investigación y para no perder la
    # relación entre el resumen y el contrato elegido. No se usan para
    # clasificar el objeto ni para escoger un contrato por heurística.
    contratos_resumen = [
        {"id": _texto(c.get("id")) or None,
         "titulo": _texto(c.get("title")) or None,
         "award_id": (_texto(c.get("awardID"))
                      or _texto(c.get("award_id")) or None)}
        for c in contratos
    ]
    items_tender = comp.get("items")
    if items_tender is None:
        items_tender = tender.get("items")

    return {
        "entidad_convocante": _texto((comp.get("buyer") or {}).get("name")) or None,
        "rucs_adjudicatarios": [x["ruc"] for x in adjudicatarios],
        # Issue #83: SUNAT necesita nombre + RUC para confrontar el emisor. La
        # lista histórica de RUC se conserva para compatibilidad.
        "adjudicatarios": adjudicatarios,
        "fecha_firma": (lambda f: f.isoformat() if f else None)(
            _fecha(contrato.get("dateSigned"))),
        "fecha_convocatoria": (lambda f: f.isoformat() if f else None)(
            _fecha((tender.get("tenderPeriod") or {}).get("startDate"))),
        "vigencia_inicio": (lambda f: f.isoformat() if f else None)(
            _fecha(periodo.get("startDate"))),
        "vigencia_fin": (lambda f: f.isoformat() if f else None)(
            _fecha(periodo.get("endDate"))),
        "monto": monto,
        "nomenclatura": _texto(tender.get("title")) or None,
        "descripcion": _texto(tender.get("description")) or None,
        "items": items_tender if isinstance(items_tender, list) else [],
        "contratos": contratos_resumen,
    }


# ── Señales ──────────────────────────────────────────────────────────────────

def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFD", _texto(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper()


def _senal_entidad(proceso: dict, cert: dict) -> Senal:
    """(a) Entidad convocante del proceso vs entidad CONTRATANTE del certificado."""
    convocante = _texto(proceso.get("entidad_convocante"))
    contratante = _texto(cert.get("entidad_contratante"))
    if not convocante:
        return Senal("entidad", FUERTE, SIN_DATO,
                     "El proceso no publica la entidad convocante.")
    if not contratante:
        return Senal("entidad", FUERTE, SIN_DATO,
                     f"El certificado no declara la entidad contratante; el proceso "
                     f"fue convocado por «{convocante}». No se puede comparar.")
    # Reutiliza el comparador de razones sociales de SUNAT (ver docstring), pero
    # puntuando también la forma PRELIMPIADA del nombre (T-REFACTOR-002): el
    # membrete del certificado suele traer la composición del consorcio entre
    # paréntesis, y esa cola hundía el parecido hasta 46/100 — una señal FUERTE
    # «en contra» sobre dos nombres que son el mismo consorcio. Se toma el mejor
    # de los dos, así que el candado solo puede dejar de contradecir, nunca
    # empezar a hacerlo. La frase sigue citando lo que el documento dice
    # literalmente; lo que se limpia es lo que se puntúa.
    from scraping.nombres_empresa import variantes
    from scraping.sunat import score_match_empresa
    score = max(score_match_empresa(x, y)
                for x in variantes(contratante) for y in variantes(convocante))
    frase = (f"Entidad: «{contratante}» (certificado) vs «{convocante}» "
             f"(proceso) → ")
    if score >= UMBRAL_ENTIDAD_A_FAVOR:
        return Senal("entidad", FUERTE, A_FAVOR,
                     f"{frase}coincide ({score}/100).")
    if score < UMBRAL_ENTIDAD_EN_CONTRA:
        return Senal("entidad", FUERTE, EN_CONTRA,
                     f"{frase}son entidades distintas ({score}/100).")
    return Senal("entidad", FUERTE, SIN_DATO,
                 f"{frase}parecido insuficiente para decidir ({score}/100, "
                 f"zona gris {UMBRAL_ENTIDAD_EN_CONTRA}-"
                 f"{UMBRAL_ENTIDAD_A_FAVOR - 1}).")


def _senal_adjudicatario(proceso: dict, cert: dict) -> Senal:
    """(a-bis) RUC del emisor del certificado entre los adjudicatarios del proceso.

    Solo suma; su ausencia NUNCA contradice (ver docstring del módulo).
    """
    rucs = [r for r in (proceso.get("rucs_adjudicatarios") or []) if _ruc(r)]
    emisor = _ruc(cert.get("ruc_emisor"))
    nombre = _texto(cert.get("entidad_emisora")) or "el emisor"
    if not emisor:
        return Senal("adjudicatario", FUERTE, SIN_DATO,
                     "El certificado no trae un RUC de emisor válido para cruzar "
                     "con los adjudicatarios del proceso.")
    if not rucs:
        return Senal("adjudicatario", FUERTE, SIN_DATO,
                     "El proceso no publica el RUC de su adjudicatario.")
    if emisor in rucs:
        return Senal("adjudicatario", FUERTE, A_FAVOR,
                     f"Emisor: «{nombre}» (RUC {emisor}) es el adjudicatario del "
                     f"proceso → es la empresa que prestó el servicio.")
    return Senal("adjudicatario", FUERTE, SIN_DATO,
                 f"Emisor: «{nombre}» (RUC {emisor}) no figura entre los "
                 f"adjudicatarios ({', '.join(rucs)}). No es contradicción: una "
                 f"constancia puede emitirla un consorciado o la propia entidad.")


def _senal_objeto(proceso: dict, cert: dict) -> Senal:
    """(b) Objeto del proceso vs tipo de la experiencia."""
    declarado = evidencia_tipo_servicio(cert)
    esperado = (declarado.get("tipo") or "").lower()
    real = _texto(proceso.get("tipo")).lower()
    etiquetas = {"expediente": "expediente técnico", "supervision": "supervisión",
                 "ejecucion": "ejecución de obra", "preinversion": "preinversión"}
    leg = lambda t: etiquetas.get(t, t or "—")  # noqa: E731
    if not esperado:
        return Senal("objeto", FUERTE, SIN_DATO,
                     "Objeto: el servicio del certificado no aporta evidencia independiente. "
                     + declarado["motivo"])
    if not esperado or not real or real == "otro":
        return Senal("objeto", FUERTE, SIN_DATO,
                     f"Objeto: no se pudo clasificar ({leg(esperado)} buscado vs "
                     f"{leg(real)} del proceso).")
    if esperado == real:
        return Senal("objeto", FUERTE, A_FAVOR,
                     f"Objeto: la experiencia es de {leg(esperado)} y el proceso "
                     f"también → coincide.")
    return Senal("objeto", FUERTE, EN_CONTRA,
                 f"Objeto: la experiencia es de {leg(esperado)} pero el proceso es "
                 f"de {leg(real)} → no corresponde.")


def _senal_temporal(proceso: dict, cert: dict) -> Senal:
    """(c) Ventana temporal, en DÍAS COMPLETOS; siempre señal DÉBIL.

    Dos condiciones, ambas necesarias para sumar a favor:
      1. la firma del contrato no puede ser posterior al inicio declarado por
         más de `TOLERANCIA_DIAS_FIRMA` días — nadie supervisa un contrato que
         todavía no existe;
      2. el periodo del certificado tiene que solapar la vigencia del proceso al
         menos un día.
    """
    ini = _fecha(cert.get("fecha_inicial"))
    fin = _fecha(cert.get("fecha_final"))
    firma = _fecha(proceso.get("fecha_firma")) or _fecha(proceso.get("fecha_convocatoria"))
    vig_ini = _fecha(proceso.get("vigencia_inicio"))
    vig_fin = _fecha(proceso.get("vigencia_fin"))
    if not ini:
        return Senal("temporal", DEBIL, SIN_DATO,
                     "El certificado no declara fecha de inicio; no hay nada que "
                     "comparar contra las fechas del proceso.")
    if not firma and not (vig_ini and vig_fin):
        return Senal("temporal", DEBIL, SIN_DATO,
                     "El proceso no publica fecha de firma ni vigencia.")

    if firma:
        holgura = (firma - ini).days      # >0 = el contrato se firmó DESPUÉS
        if holgura > TOLERANCIA_DIAS_FIRMA:
            return Senal("temporal", DEBIL, EN_CONTRA,
                         f"Fechas: el profesional declara inicio el "
                         f"{ini.strftime('%d/%m/%Y')} pero el contrato del proceso "
                         f"se firmó el {firma.strftime('%d/%m/%Y')} — {holgura} días "
                         f"después (tolerancia: {TOLERANCIA_DIAS_FIRMA} días). "
                         f"No se puede prestar el servicio de un contrato que aún no se ha firmado.")

    if vig_ini and vig_fin and fin:
        solape = (min(fin, vig_fin) - max(ini, vig_ini)).days + 1
        if solape <= 0:
            return Senal("temporal", DEBIL, EN_CONTRA,
                         f"Fechas: el periodo del certificado "
                         f"({ini.strftime('%d/%m/%Y')}–{fin.strftime('%d/%m/%Y')}) no "
                         f"toca ni un día la vigencia del proceso "
                         f"({vig_ini.strftime('%d/%m/%Y')}–"
                         f"{vig_fin.strftime('%d/%m/%Y')}).")
        return Senal("temporal", DEBIL, A_FAVOR,
                     f"Fechas: el periodo del certificado "
                     f"({ini.strftime('%d/%m/%Y')}–{fin.strftime('%d/%m/%Y')}) cae "
                     f"dentro de la vigencia del proceso "
                     f"({vig_ini.strftime('%d/%m/%Y')}–{vig_fin.strftime('%d/%m/%Y')}"
                     f"), con {solape} días en común.")

    if firma:
        return Senal("temporal", DEBIL, A_FAVOR,
                     f"Fechas: el contrato se firmó el "
                     f"{firma.strftime('%d/%m/%Y')}, antes del inicio declarado "
                     f"({ini.strftime('%d/%m/%Y')}) → coherente.")
    return Senal("temporal", DEBIL, SIN_DATO,
                 "El proceso no publica una vigencia completa que comparar.")


def _senal_monto(proceso: dict, cert: dict) -> Senal:
    """(d) Monto — señal DÉBIL. Nunca veta, nunca promueve por sí sola."""
    a = _numero(proceso.get("monto"))
    b = _numero(cert.get("monto_contrato_soles"))
    if a is None or b is None:
        return Senal("monto", DEBIL, SIN_DATO,
                     "Monto: uno de los dos lados no lo publica — no se evalúa.")
    dif = abs(a - b) / max(a, b)
    if dif <= TOLERANCIA_MONTO:
        return Senal("monto", DEBIL, A_FAVOR,
                     f"Monto: S/ {b:,.2f} (certificado) vs S/ {a:,.2f} (proceso) → "
                     f"mismo orden ({dif * 100:.0f}% de diferencia). Suma, no decide.")
    return Senal("monto", DEBIL, SIN_DATO,
                 f"Monto: S/ {b:,.2f} (certificado) vs S/ {a:,.2f} (proceso) → "
                 f"difieren {dif * 100:.0f}%. No es contradicción: el certificado "
                 f"suele declarar el monto de la obra y el proceso el del servicio.")


# ── Veredicto ────────────────────────────────────────────────────────────────

def hay_varios_contratos_distintos(proceso: Optional[dict]) -> bool:
    """Indica pluralidad solo cuando la metadata trae IDs de contrato distintos.

    Un resumen histórico sin la lista/IDs de contratos no permite inferir
    pluralidad: la ausencia de metadata es desconocimiento, no evidencia.
    """
    contratos = (proceso or {}).get("contratos")
    if not isinstance(contratos, list):
        return False
    ids = {_texto(c.get("id")) for c in contratos
           if isinstance(c, dict) and _texto(c.get("id"))}
    return len(ids) > 1


def candado_tiene_adjudicatario_favorable(candado: Optional[dict]) -> bool:
    """Comprueba la señal persistida exacta del adjudicatario, sin inferirla."""
    return any(
        isinstance(s, dict) and s.get("nombre") == "adjudicatario"
        and s.get("fuerza") == FUERTE and s.get("sentido") == A_FAVOR
        for s in (candado or {}).get("senales", [])
    ) if isinstance(candado, dict) else False

def evaluar_candado(proceso: dict, cert: dict) -> Candado:
    """Cruza el resumen del proceso contra los datos del certificado.

    `proceso`: salida de `resumen_proceso` + la clave `tipo` (el tipo clasificado
    del proceso elegido). `cert`: campos del espejo — `entidad_contratante`,
    `entidad_emisora`, `ruc_emisor`, `tipo_experiencia`, `fecha_inicial`,
    `fecha_final`, `monto_contrato_soles`.
    """
    proceso, cert = proceso or {}, cert or {}
    senales = [
        _senal_entidad(proceso, cert),
        _senal_adjudicatario(proceso, cert),
        _senal_objeto(proceso, cert),
        _senal_temporal(proceso, cert),
        _senal_monto(proceso, cert),
    ]
    contra = [s for s in senales if s.fuerza == FUERTE and s.sentido == EN_CONTRA]
    favor = [s for s in senales if s.fuerza == FUERTE and s.sentido == A_FAVOR]

    if contra:
        return Candado(
            CONTRADICE,
            "El proceso encontrado CONTRADICE al certificado: "
            + " ".join(s.detalle for s in contra),
            senales)
    adjudicatario_favorable = any(
        s.nombre == "adjudicatario" and s.sentido == A_FAVOR
        and s.fuerza == FUERTE for s in favor)
    if hay_varios_contratos_distintos(proceso):
        return Candado(
            POR_CONFIRMAR,
            "El proceso publica varios contratos distintos; las coincidencias "
            "de metadatos no permiten confirmar cuál encargo corresponde al "
            "certificado. Se conservan los candidatos para investigación.",
            senales, contratos_multiples=True)
    if len(favor) >= MINIMO_SENALES_CONFIRMAR and adjudicatario_favorable:
        observaciones = observaciones_temporales(Candado(CONFIRMADO, "", senales))
        motivo = (f"{len(favor)} señales independientes muestran coincidencias "
                  "de metadatos entre el proceso y el certificado, y ninguna señal "
                  "fuerte de identidad lo contradice; esto no verifica por sí solo "
                  "el documento ni el encargo íntegro.")
        if observaciones:
            motivo += " Observación de fechas: " + " ".join(observaciones)
        return Candado(
            CONFIRMADO,
            motivo,
            senales)
    return Candado(
        POR_CONFIRMAR,
        f"Identidad pendiente. Señales fuertes a favor: {len(favor)}; se requieren "
        f"al menos {MINIMO_SENALES_CONFIRMAR}, incluyendo al adjudicatario."
        + (" Falta cotejar el RUC del emisor con el adjudicatario."
           if not adjudicatario_favorable else ""),
        senales)


def observaciones_temporales(candado: Candado | dict) -> list[str]:
    """Detalles literales de señales temporales en contra, incluso heredadas.

    La observación conserva una discrepancia de fechas para el evaluador, pero
    no altera el resultado del candado ni su tratamiento como señal débil.
    """
    if isinstance(candado, Candado):
        senales = candado.senales
    else:
        senales = (candado or {}).get("senales") or []
    observaciones = []
    for senal in senales:
        nombre = senal.get("nombre") if isinstance(senal, dict) else getattr(senal, "nombre", None)
        sentido = senal.get("sentido") if isinstance(senal, dict) else getattr(senal, "sentido", None)
        detalle = senal.get("detalle") if isinstance(senal, dict) else getattr(senal, "detalle", None)
        if nombre == "temporal" and sentido == EN_CONTRA and detalle:
            observaciones.append(str(detalle))
    return observaciones


def confirmado_sin_adjudicatario(candado: Candado | dict) -> bool:
    """Gate anticircular de #83; actualmente no habilita rescate de RUC.

    Sin adjudicatario solo quedan entidad y tipo genérico: no identifican el
    encargo. Usar el mismo RUC que se intenta recuperar sería circular. Se
    conserva la interfaz viva/histórica, pero no se habilitan señales hipotéticas
    sin productor ni validación. La consulta SUNAT ordinaria sigue funcionando.
    """
    return False


# ── Rótulos para los entregables (una sola fuente de verdad) ─────────────────

ROTULOS = {
    CONFIRMADO: "Coincidencias de metadatos del proceso con el certificado; "
                "no verifica por sí solo el documento ni el encargo íntegro",
    POR_CONFIRMAR: "Por confirmar — no se pudo verificar contra el certificado",
    CONTRADICE: "Por confirmar — los datos del proceso NO coinciden con el certificado",
}


def rotulo(resultado: Optional[str]) -> Optional[str]:
    """Rótulo de confianza del candado. `None` si el job no lo trae (jobs
    anteriores a F5: el entregable se genera exactamente como antes)."""
    return ROTULOS.get(str(resultado or "")) or None
