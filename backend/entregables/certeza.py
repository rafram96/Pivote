"""
Certeza de identificación de una experiencia (concursos de EXPEDIENTES).

Qué problema resuelve
─────────────────────
La PARTE 5 de las hojas por profesional sumaba días como si todos valieran lo
mismo. En un concurso de ELABORACIÓN DE EXPEDIENTES TÉCNICOS eso engaña: un
periodo cuyo CUI viene **citado en el certificado** y confirmado por el contrato
del MEF no tiene el mismo respaldo que otro cuyo CUI el backend **infirió por el
parecido del nombre del proyecto**. El evaluador necesita ver, en la misma
tabla, cuántos de los días que sostienen el veredicto están realmente
identificados.

Este módulo es PURO: sin red, sin disco, sin openpyxl. Recibe la experiencia del
espejo y su enriquecimiento (o la proyección que `desempaquetar_enriquecimiento`
deja en `fichas`, que conserva los mismos campos) y devuelve qué se pinta.

Vocabulario real del enriquecimiento (verificado sobre corridas reales)
───────────────────────────────────────────────────────────────────────
· `via`: CUI_TEXTO · CODIGO · MANUAL · CONTRATO · RESOLUCION · NOMBRE · NUMERO ·
  MEF · PROBABLE · MULTI_OBRA · REVISION · PRIVADA · NA.
· `verificacion_expediente.contrato.veredicto` y `.contratista.veredicto`:
  **`ok` | `no_verificable` | `discrepancia`** (NO «coincide» / «no coincide»:
  ese vocabulario no existe en los datos; se aceptan ambos por tolerancia).
· `verificacion_expediente.contrato.elegido_por`: `emisor` | `unico` |
  `mas_barato` — CÓMO se eligió el contrato entre los del expediente. Solo
  `emisor` confirma identidad: `unico`/`mas_barato` son heurísticas de
  selección, no evidencia de que ese contrato sea el del emisor.
· `verificacion_expediente.contrato.otros_contratos_expediente`: hasta 5
  «numero — contratista» del mismo expediente; se muestran cuando el contrato
  NO se eligió por el emisor, para que se vea entre qué se escogió.
· `contrato_emisor` (vía CONTRATO): `{numero, contratista, fecha}` — el
  contrato que ATA al emisor con el expediente; manda sobre el anterior.
· `resolucion_aprobacion.coincide_emisor`: `confirma` | `nombra_otro` |
  `no_nombra`; `fecha` puede ser None con `fecha_descartada` + `fecha_motivo`
  cuando la fecha leída no era plausible.
· `identificacion_incompleta`: True en un certificado multi-obra al que le
  faltan sub-obras por ubicar.
· `cruces_fechas[].resultado`: `coincide` | `dispara` | `por_confirmar`
  (`dispara` es lo que el Excel imprime como «NO»).

Colores
───────
Se devuelven como HEX y son EXACTAMENTE los de la paleta ya vigente del
entregable, para que la leyenda siga siendo verdad:
verde `D9EAD3` (FILL_OK) · violeta `E4D7F5` (FILL_SUPUESTO) ·
amarillo suave `FFF2CC` (FILL_PEND) · gris `D9D9D9` (FILL_PARTE).
"""
from __future__ import annotations

from typing import Optional
from entregables.estado_fuentes import consultas_de, nota_ausencia_mef

# ── Paleta (misma que las constantes de `excel_final`, por HEX) ──────────────
COLOR_VERIFICADO = "D9EAD3"   # verde  → identificación sostenida por documento
COLOR_INFERIDO = "E4D7F5"     # violeta → el backend dedujo la identidad
COLOR_SIN_IDENTIFICAR = "FFF2CC"  # amarillo suave → por verificar
COLOR_PRIVADA = "D9D9D9"      # gris → fuera del registro público

# ── Niveles (vocabulario cerrado) ───────────────────────────────────────────
CITADO = "citado"
CONFIRMADO_MEF = "confirmado_mef"
INFERIDO = "inferido"
MULTI_OBRA = "multi_obra"
SIN_IDENTIFICAR = "sin_identificar"
PRIVADA = "privada"

# A qué fila de totales suman los días NO se decide por el nivel sino por el
# color (ver `bucket_certeza`): un multi-obra parcial es MULTI_OBRA y sin embargo
# se pinta y se suma como inferido. Tener las dos cosas separadas fue justo el
# origen del defecto que se corrige aquí.
#: Niveles cuyos días se presentan como PROVISIONALES.
NIVELES_PROVISIONALES = frozenset({SIN_IDENTIFICAR})

_VIA_CITADA = frozenset({"CUI_TEXTO", "CODIGO", "MANUAL"})
_VIA_MEF = frozenset({"CONTRATO", "RESOLUCION"})
_VIA_INFERIDA = frozenset({"NOMBRE", "NUMERO", "MEF", "PROBABLE"})
_VIA_PRIVADA = frozenset({"PRIVADA", "NA"})

# Veredictos del bloque MEF. El dato real dice «ok»; se acepta «coincide» por si
# el vocabulario cambia aguas arriba (nunca al revés: un `no_verificable` jamás
# se lee como confirmación).
_VEREDICTO_OK = frozenset({"ok", "coincide"})
_VEREDICTO_CONTRA = frozenset({"discrepancia", "no_coincide", "no coincide",
                               "contradice"})

REGLA_TERMINO = "FECHA_APROBACION_ET"   # regla B de `reglas.cruces_fechas`


def _texto(v) -> str:
    return str(v or "").strip()


def _dic(v) -> dict:
    return v if isinstance(v, dict) else {}


def normalizar_motivo_fuente(texto) -> str:
    """Neutraliza solo afirmaciones históricas que la evidencia no prueba."""
    salida = str(texto or "")
    reemplazos = (
        ("no publicado por la fuente.",
         "no obtenido en esta corrida; la ausencia no prueba que no esté publicado."),
        ("El MEF no publica la resolución de aprobación de este expediente",
         "Este análisis no dispone de una resolución de aprobación utilizable"),
        ("el MEF no publica contratos ni Formato 08-A para este",
         "este análisis no dispone de contratos ni Formato 08-A para este"),
        ("el proceso identificado no publica la fecha en que se",
         "este análisis no dispone de la fecha en que se"),
    )
    for anterior, nuevo in reemplazos:
        salida = salida.replace(anterior, nuevo)
    return salida


def via_de(enr: Optional[dict], exp: Optional[dict] = None) -> str:
    """La vía con que el backend identificó la obra, en MAYÚSCULAS ('' si no hay)."""
    return _texto(_dic(enr).get("via") or _dic(exp).get("via")).upper()


def _cui_de(enr: Optional[dict], exp: Optional[dict]) -> str:
    enr, exp = _dic(enr), _dic(exp)
    return _texto(enr.get("cui")
                  or _dic(enr.get("verificacion_expediente")).get("cui_confirmado")
                  or exp.get("cui"))


def _sub_obras(enr: dict) -> tuple[int, int]:
    """(resueltas, totales) de un certificado multi-obra."""
    sub = enr.get("sub_obras")
    if not isinstance(sub, list):
        return 0, 0
    total = len(sub)
    resueltas = sum(1 for s in sub
                    if isinstance(s, dict) and _texto(s.get("estado")) == "resuelto")
    return resueltas, total


def confirmado_por_mef(enr: Optional[dict]) -> bool:
    """¿El MEF publica un documento que ata este expediente al emisor?

    Basta con UNA de estas evidencias documentales:
      · el contrato del expediente coincide con lo declarado (`veredicto == "ok"`),
      · el contrato se eligió PORQUE su contratista es el emisor
        (`elegido_por == "emisor"`) — `unico`/`mas_barato` NO confirman nada:
        son heurísticas para escoger entre varios contratos del expediente,
      · existe `contrato_emisor` (la vía CONTRATO ya ató emisor y expediente),
      · la resolución de aprobación nombra al emisor (`confirma`).
    """
    enr = _dic(enr)
    if _dic(enr.get("contrato_emisor")):
        return True
    ver = _dic(enr.get("verificacion_expediente"))
    contrato = _dic(ver.get("contrato"))
    contratista = _dic(ver.get("contratista"))
    if _texto(contrato.get("elegido_por")) == "emisor":
        return True
    if _texto(contrato.get("veredicto")).lower() in _VEREDICTO_OK:
        return True
    if _texto(contratista.get("veredicto")).lower() in _VEREDICTO_OK:
        return True
    return _texto(_dic(enr.get("resolucion_aprobacion")).get("coincide_emisor")) == "confirma"


def clasificar_identificacion(exp: Optional[dict], enr: Optional[dict]) -> dict:
    """Con cuánta certeza se sabe QUÉ obra es la de esta experiencia.

    Devuelve ``{"nivel", "etiqueta", "color"}``. `exp` es la experiencia del
    espejo; `enr` su enriquecimiento (o la proyección que viaja en `fichas`).

    El orden de las preguntas importa y es deliberado:
      1. Obra privada → no hay registro público que consultar; no es un fallo.
      2. CUI citado en el papel → la identidad la puso el emisor, no el backend.
      3. Certificado multi-obra → su certeza es «cuántas de las M se ubicaron».
      4. Documento del MEF (contrato o resolución) → identidad confirmada aunque
         la vía de llegada haya sido el nombre.
      5. Vías por parecido → inferido.
      6. Todo lo demás (REVISION, sin vía, sin CUI) → sin identificar.
    """
    exp, enr = _dic(exp), _dic(enr)
    via = via_de(enr, exp)
    cui = _cui_de(enr, exp)

    if via in _VIA_PRIVADA:
        return {"nivel": PRIVADA,
                "etiqueta": "Obra privada (sin registro público)",
                "color": COLOR_PRIVADA}

    if via in _VIA_CITADA and cui:
        return {"nivel": CITADO,
                "etiqueta": "CUI citado en el certificado",
                "color": COLOR_VERIFICADO}

    if via == "MULTI_OBRA" or enr.get("sub_obras"):
        resueltas, total = _sub_obras(enr)
        incompleta = bool(enr.get("identificacion_incompleta")) or resueltas < total
        if resueltas == 0:
            return {"nivel": SIN_IDENTIFICAR,
                    "etiqueta": "Sin identificar",
                    "color": COLOR_SIN_IDENTIFICAR}
        # Con obras ubicadas pero no TODAS, la identificación es parcial: el
        # violeta dice «hay una parte deducida» sin negar lo que sí se probó.
        return {"nivel": MULTI_OBRA,
                "etiqueta": f"{resueltas} de {total} obras identificadas",
                "color": COLOR_INFERIDO if incompleta else COLOR_VERIFICADO}

    if via in _VIA_MEF or confirmado_por_mef(enr):
        return {"nivel": CONFIRMADO_MEF,
                "etiqueta": ("CUI confirmado por el MEF (contrato o resolución "
                             "a nombre del emisor)"),
                "color": COLOR_VERIFICADO}

    if via in _VIA_CITADA:       # vía citada pero sin CUI legible
        return {"nivel": SIN_IDENTIFICAR,
                "etiqueta": "Sin identificar",
                "color": COLOR_SIN_IDENTIFICAR}

    if via in _VIA_INFERIDA and cui:
        return {"nivel": INFERIDO,
                "etiqueta": "CUI inferido por el nombre del proyecto",
                "color": COLOR_INFERIDO}

    return {"nivel": SIN_IDENTIFICAR,
            "etiqueta": "Sin identificar",
            "color": COLOR_SIN_IDENTIFICAR}


def es_provisional(nivel: str) -> bool:
    """¿Los días de esta experiencia se presentan como PROVISIONALES?"""
    return nivel in NIVELES_PROVISIONALES


# Cubetas de los TOTALES de la PARTE 5. Se derivan del COLOR y no del nivel a
# propósito: así la fila de totales y el relleno de la celda «Efectivo (días)»
# no pueden contradecirse nunca (un multi-obra parcial se pinta violeta, luego
# sus días suman en «CUI inferido», no en «confirmado»).
BUCKET_CONFIRMADO = "confirmado"
BUCKET_INFERIDO = "inferido"
BUCKET_SIN_IDENTIFICAR = "sin_identificar"
BUCKET_PRIVADA = "privada"

_BUCKET_POR_COLOR = {
    COLOR_VERIFICADO: BUCKET_CONFIRMADO,
    COLOR_INFERIDO: BUCKET_INFERIDO,
    COLOR_SIN_IDENTIFICAR: BUCKET_SIN_IDENTIFICAR,
    COLOR_PRIVADA: BUCKET_PRIVADA,
}


def bucket_certeza(certeza: dict) -> str:
    """A qué fila de TOTALES suman los días de esta experiencia."""
    return _BUCKET_POR_COLOR.get(_dic(certeza).get("color"),
                                 BUCKET_SIN_IDENTIFICAR)


def alertas_experiencia(exp: Optional[dict], enr: Optional[dict]) -> list[str]:
    """Hallazgos que CONTRADICEN lo declarado y merecen la celda roja.

    No incluye las abstenciones: «no verificable» no es una alerta, es falta de
    fuente (mismo principio que el resto del entregable — la ausencia de datos
    nunca se convierte en un cargo contra el postor).
    """
    exp, enr = _dic(exp), _dic(enr)
    avisos: list[str] = []

    resol = _dic(enr.get("resolucion_aprobacion"))
    if _texto(resol.get("coincide_emisor")) == "nombra_otro":
        consultores = [c for c in (resol.get("consultores") or []) if _texto(c)]
        quien = f" ({'; '.join(str(c) for c in consultores)})" if consultores else ""
        avisos.append("La resolución de aprobación del MEF nombra a OTRO "
                      f"consultor{quien}, no al emisor del certificado")

    ver = _dic(enr.get("verificacion_expediente"))
    for campo, texto in (("contrato", "El contrato publicado por el MEF no "
                                      "coincide con lo declarado"),
                         ("contratista", "El contratista del expediente en el MEF "
                                         "no coincide con el emisor del certificado")):
        if _texto(_dic(ver.get(campo)).get("veredicto")).lower() in _VEREDICTO_CONTRA:
            avisos.append(texto)

    for cruce in (enr.get("cruces_fechas") or []):
        if not isinstance(cruce, dict):
            continue
        if cruce.get("regla") == REGLA_TERMINO and cruce.get("resultado") == "dispara":
            avisos.append("El término declarado es POSTERIOR a la aprobación del "
                          "expediente (regla B: NO)")

    sunat = _dic(enr.get("sunat"))
    if _texto(sunat.get("condicion")).upper().startswith("NO HABIDO"):
        avisos.append("El emisor figura como NO HABIDO en SUNAT")
    if _texto(sunat.get("estado")).upper().startswith("BAJA"):
        avisos.append("El emisor figura de BAJA en SUNAT")

    resueltas, total = _sub_obras(enr)
    if total and resueltas == 0:
        avisos.append(f"Certificado con {total} obras y ninguna ubicada en el "
                      "registro público")
    return avisos


def _fecha(v) -> str:
    """`2019-08-08` → `08/08/2019`; cualquier otra cosa se devuelve tal cual."""
    t = _texto(v)
    if len(t) == 10 and t[4] == "-" and t[7] == "-":
        return f"{t[8:10]}/{t[5:7]}/{t[0:4]}"
    return t


#: Lo que se lee cuando la evidencia conservada no permite explicar la ausencia.
SIN_DOCUMENTOS_MEF = ("Este análisis no dispone de contrato/resolución "
                      "utilizable para el contraste")

FUENTE_MEF_PRIVADA = ("No aplica consulta MEF/InfoObras a esta experiencia "
                      "privada")
FUENTE_MEF_SIN_IDENTIFICAR = ("Identificación del expediente pendiente; no hay "
                              "respaldo MEF vinculado de forma verificable")

_CONSULTOR = {
    "confirma": "Consultor según resolución: confirma al emisor del certificado",
    "nombra_otro": "Consultor según resolución: nombra a OTRO",
    "no_nombra": "Consultor según resolución: la resolución no nombra al consultor",
}


def fuente_mef(enr: Optional[dict]) -> dict:
    """Lo que el MEF publica del expediente, ya redactado para la PARTE 5.

    Devuelve ``{"sin_documentos", "contrato", "resolucion", "consultor"}``. Los
    tres textos son la fila «Fuente: MEF» que sustituye a la vieja fila
    «Fuente: InfoObras» — que hablaba de la EJECUCIÓN de la obra, algo que no
    prueba nada sobre quién elaboró el expediente.
    """
    enr = _dic(enr)
    ver = _dic(enr.get("verificacion_expediente"))
    resol_leida = _dic(enr.get("resolucion_aprobacion"))
    contrato_emisor = _dic(enr.get("contrato_emisor"))
    contrato = _dic(ver.get("contrato"))
    resol_ver = _dic(ver.get("resolucion"))

    # La vía privada se resuelve antes que cualquier expectativa de fuente
    # pública. `NA` es un alias histórico admitido por el clasificador.
    if via_de(enr) in _VIA_PRIVADA:
        return {"sin_documentos": True, "contrato": FUENTE_MEF_PRIVADA,
                "resolucion": "—", "consultor": "—"}

    hay_contrato = bool(
        contrato_emisor
        or contrato.get("numero")
        or contrato.get("fecha")
        or contrato.get("fecha_suscripcion")
    )
    hay_resolucion = bool(
        resol_ver.get("numero")
        or resol_ver.get("fecha")
        or resol_ver.get("documento")
        or resol_leida.get("numero")
        or resol_leida.get("fecha")
        or resol_leida.get("fecha_descartada")
    )

    # Una marca antigua describe una decisión del pipeline, no la evidencia
    # disponible hoy. Si después se conservó un documento, este debe mostrarse.
    if not (hay_contrato or hay_resolucion):
        nivel = clasificar_identificacion({}, enr)["nivel"]
        texto = (FUENTE_MEF_SIN_IDENTIFICAR
                 if nivel == SIN_IDENTIFICAR else SIN_DOCUMENTOS_MEF)
        if any(k.startswith("mef_") for k in consultas_de(enr)):
            texto = nota_ausencia_mef(enr)
        return {"sin_documentos": True, "contrato": texto,
                "resolucion": "—", "consultor": "—"}

    contratista = _dic(ver.get("contratista"))
    if contrato_emisor:
        # Vía CONTRATO: este es EL contrato que ata al emisor con el expediente.
        # Manda sobre el que la verificación haya elegido por heurística.
        partes = [f"Contrato N° {_texto(contrato_emisor.get('numero')) or 's/n'}"]
        if _texto(contrato_emisor.get("contratista")):
            partes.append(_texto(contrato_emisor.get("contratista")))
        if _fecha(contrato_emisor.get("fecha")):
            partes.append(f"suscrito {_fecha(contrato_emisor.get('fecha'))}")
        partes.append("a nombre del emisor del certificado")
        texto_contrato = " · ".join(partes)
    elif contrato.get("numero") or contrato.get("fecha") or contrato.get("fecha_suscripcion"):
        nombre = _texto(contratista.get("valor") or contratista.get("declarado")
                        or _dic(ver.get("emisor_certificado")).get("empresa"))
        fecha = _fecha(contrato.get("fecha_suscripcion") or contrato.get("fecha"))
        partes = [f"Contrato N° {_texto(contrato.get('numero')) or 's/n'}"]
        if nombre:
            partes.append(nombre)
        if fecha:
            partes.append(f"suscrito {fecha}")
        veredicto = _texto(contrato.get("veredicto")).lower()
        if veredicto in _VEREDICTO_OK:
            partes.append("coincide con lo declarado")
        elif veredicto in _VEREDICTO_CONTRA:
            partes.append("NO coincide con lo declarado")
        elif veredicto:
            partes.append("por confirmar")
        # Cómo se escogió: solo `emisor` es evidencia; decirlo evita que un
        # contrato elegido «por ser el único» se lea como confirmación.
        elegido = _texto(contrato.get("elegido_por"))
        if elegido and elegido != "emisor":
            otros = [str(x) for x in (contrato.get("otros_contratos_expediente") or [])
                     if _texto(x)]
            nota = ("elegido por ser el único del expediente" if elegido == "unico"
                    else "elegido por ser el de menor monto del expediente"
                    if elegido == "mas_barato" else f"elegido por «{elegido}»")
            if otros:
                nota += f" — otros contratos del expediente: {'; '.join(otros)}"
            partes.append(nota)
        texto_contrato = " · ".join(partes)
    else:
        texto_contrato = "Este análisis no dispone de contrato utilizable"

    numero_res = _texto(_dic(ver.get("resolucion")).get("numero")
                        or resol_leida.get("numero"))
    fecha_res = _fecha(resol_leida.get("fecha")
                       or _dic(ver.get("resolucion")).get("fecha"))
    documento_res = _texto(_dic(ver.get("resolucion")).get("documento"))
    descartada = _fecha(resol_leida.get("fecha_descartada"))
    if numero_res or fecha_res or documento_res or descartada:
        texto_resol = ("Resolución de aprobación N° " + (numero_res or "s/n")
                       if numero_res or fecha_res or descartada
                       else "Resolución de aprobación: documento disponible")
        if fecha_res:
            texto_resol += f" del {fecha_res}"
        elif descartada:
            # La fecha se leyó pero no era plausible: se dice cuál se descartó y
            # por qué, en vez de callar (una fecha inventada es peor que ninguna).
            motivo = _texto(resol_leida.get("fecha_motivo"))
            texto_resol += (f" — fecha no legible con certeza (se descartó "
                            f"{descartada}{': ' + motivo if motivo else ''})")
    else:
        texto_resol = "Este análisis no dispone de resolución utilizable"

    consultor = _CONSULTOR.get(_texto(resol_leida.get("coincide_emisor")),
                               "Consultor según resolución: sin resolución leída")
    return {"sin_documentos": False, "contrato": texto_contrato,
            "resolucion": texto_resol, "consultor": consultor}


# ─────────────────────────────────────────────────────────────────────────────
# Proyección para el PANEL
# ─────────────────────────────────────────────────────────────────────────────
# El Excel pinta HEX; el Panel quiere un nombre de color estable. Ambos leen la
# MISMA clasificación (`clasificar_identificacion`), así que la leyenda del
# entregable y la del panel no pueden divergir.

VERDE = "verde"
VIOLETA = "violeta"
AMARILLO = "amarillo"
GRIS = "gris"

_NOMBRE_POR_COLOR = {
    COLOR_VERIFICADO: VERDE,
    COLOR_INFERIDO: VIOLETA,
    COLOR_SIN_IDENTIFICAR: AMARILLO,
    COLOR_PRIVADA: GRIS,
}


def color_nombre(color: Optional[str]) -> str:
    """HEX de la paleta → nombre de color del Panel (`verde`/`violeta`/
    `amarillo`/`gris`). Lo desconocido cae en `amarillo`, igual que
    `bucket_certeza` cae en «sin identificar»: nunca se inventa un verde."""
    return _NOMBRE_POR_COLOR.get(_texto(color).upper(), AMARILLO)


_VIA_CITADA_TEXTO = {
    "CUI_TEXTO": "citado en el texto del certificado",
    "CODIGO": "citado como código de obra en el certificado",
    "MANUAL": "confirmado a mano por el evaluador",
}
_VIA_INFERIDA_TEXTO = {
    "NOMBRE": "inferido por el nombre del proyecto",
    "NUMERO": "inferido por el número que cita el certificado",
    "MEF": "inferido por búsqueda en el banco de inversiones del MEF",
    "PROBABLE": "inferido por coincidencia probable",
}
_VIA_MEF_TEXTO = {
    "CONTRATO": "confirmado por el contrato que publica el MEF",
    "RESOLUCION": "confirmado por la resolución de aprobación que publica el MEF",
}


def _respaldo_mef(enr: dict) -> str:
    """Una frase llana con lo que el MEF publica (o no) de este expediente."""
    panel = fuente_mef_panel(enr)
    if panel["estado"] == MEF_SIN_DOCUMENTOS:
        return panel["texto"]
    partes: list[str] = []
    contrato = panel["contrato"]
    if contrato:
        if contrato["del_emisor"]:
            partes.append("el MEF publica un contrato a nombre del emisor "
                          "del certificado")
        elif contrato["contratista"]:
            partes.append("el MEF publica contrato a nombre de otro contratista "
                          f"({contrato['contratista']})")
        else:
            partes.append("el MEF publica un contrato del expediente, sin "
                          "confirmar que sea del emisor")
    resol = panel["resolucion"]
    if resol:
        partes.append({
            "confirma": "la resolución de aprobación nombra al emisor",
            "nombra_otro": "la resolución de aprobación nombra a OTRO consultor",
            "no_nombra": "la resolución de aprobación no nombra al consultor",
        }.get(_texto(resol.get("coincide_emisor")),
              "el MEF publica la resolución que aprobó el expediente"))
    return "; ".join(partes)


def detalle_identificacion(exp: Optional[dict], enr: Optional[dict]) -> str:
    """POR QUÉ esta experiencia tiene esa certeza, en llano: la vía con que se
    llegó al CUI y el respaldo documental del MEF.

    Ej.: «CUI 2412686 inferido por el nombre del proyecto; el MEF publica
    contrato a nombre de otro contratista»."""
    exp, enr = _dic(exp), _dic(enr)
    nivel = clasificar_identificacion(exp, enr)["nivel"]
    via = via_de(enr, exp)
    cui = _cui_de(enr, exp)
    resueltas, total = _sub_obras(enr)

    if nivel == PRIVADA:
        return ("Obra privada: no aplica consulta MEF/InfoObras; la experiencia "
                "se contrasta con el certificado y SUNAT no acredita por sí sola "
                "el tiempo ni el cargo")
    if nivel == CITADO:
        return (f"CUI {cui} " + _VIA_CITADA_TEXTO.get(via, "citado en el certificado")
                + "; " + _respaldo_mef(enr))
    if nivel == CONFIRMADO_MEF:
        base = (f"CUI {cui} " if cui else "Expediente ") + _VIA_MEF_TEXTO.get(
            via, "confirmado por un documento que el MEF publica a nombre del emisor")
        return base + "; " + _respaldo_mef(enr)
    if nivel == MULTI_OBRA:
        base = (f"Certificado de {total} obras: {resueltas} identificadas en el "
                "registro público")
        if total - resueltas > 0:
            base += f", {total - resueltas} sin ubicar"
        return base + "; " + _respaldo_mef(enr)
    if nivel == INFERIDO:
        return (f"CUI {cui} " + _VIA_INFERIDA_TEXTO.get(via, "inferido por el backend")
                + "; " + _respaldo_mef(enr))
    # sin_identificar: se dice QUÉ faltó, no solo que faltó.
    if total and resueltas == 0:
        return (f"Certificado de {total} obras y ninguna ubicada en el registro "
                "público; los días se cuentan como provisionales")
    if via == "REVISION":
        return ("La identificación quedó pendiente de revisión manual; "
                "los días se cuentan como provisionales")
    if via in _VIA_CITADA:
        return ("El certificado cita un código pero no se leyó un CUI válido; "
                "los días se cuentan como provisionales")
    if cui:
        return (f"CUI {cui} registrado sin un método de identificación verificable; "
                "los días se cuentan como provisionales")
    return ("Sin identificación verificable registrada; los días se "
            "cuentan como provisionales")


def identificacion_panel(exp: Optional[dict], enr: Optional[dict]) -> dict:
    """`{"nivel", "etiqueta", "color", "detalle"}` — lo mismo que pinta el Excel,
    con el color por nombre y el porqué ya redactado."""
    certeza = clasificar_identificacion(exp, enr)
    return {"nivel": certeza["nivel"], "etiqueta": certeza["etiqueta"],
            "color": color_nombre(certeza["color"]),
            "detalle": detalle_identificacion(exp, enr)}


#: Valores posibles de `fuente_mef_panel()["estado"]`.
MEF_SIN_DOCUMENTOS = "sin_documentos"
MEF_CONTRATO = "contrato"
MEF_RESOLUCION = "resolucion"
MEF_AMBOS = "ambos"


def fuente_mef_panel(enr: Optional[dict]) -> dict:
    """Lo que el MEF publica del expediente, estructurado para el Panel.

    ``{"estado", "contrato": {...}|None, "resolucion": {...}|None, "texto"}``.
    `texto` es exactamente lo que imprime la PARTE 5 del Excel (`fuente_mef`),
    para que panel y entregable no puedan contar historias distintas.
    """
    enr = _dic(enr)
    textos = fuente_mef(enr)
    texto = " · ".join(t for t in (textos["contrato"], textos["resolucion"],
                                  textos["consultor"]) if _texto(t) and t != "—")

    if textos["sin_documentos"]:
        return {"estado": MEF_SIN_DOCUMENTOS, "contrato": None,
                "resolucion": None, "texto": texto}

    ver = _dic(enr.get("verificacion_expediente"))
    contrato_ver = _dic(ver.get("contrato"))
    contratista = _dic(ver.get("contratista"))
    contrato_emisor = _dic(enr.get("contrato_emisor"))
    resol_leida = _dic(enr.get("resolucion_aprobacion"))
    resol_ver = _dic(ver.get("resolucion"))

    contrato = None
    if contrato_emisor:
        # Vía CONTRATO: este contrato ATA al emisor con el expediente.
        contrato = {"numero": contrato_emisor.get("numero"),
                    "contratista": contrato_emisor.get("contratista"),
                    "fecha": contrato_emisor.get("fecha"),
                    "del_emisor": True, "otros": []}
    elif (contrato_ver.get("numero") or contrato_ver.get("fecha")
          or contrato_ver.get("fecha_suscripcion")):
        # El contratista del MEF vive en `contratista.valor`; `declarado` es lo
        # que dice el certificado y `emisor_certificado.empresa` el último recurso.
        nombre = _texto(contratista.get("valor") or contratista.get("declarado")
                        or _dic(ver.get("emisor_certificado")).get("empresa")) or None
        # Solo `elegido_por == "emisor"` (o un veredicto `ok`) ata el contrato al
        # emisor: `unico`/`mas_barato` son heurísticas de selección, no evidencia.
        del_emisor = (_texto(contrato_ver.get("elegido_por")) == "emisor"
                      or _texto(contrato_ver.get("veredicto")).lower() in _VEREDICTO_OK
                      or _texto(contratista.get("veredicto")).lower() in _VEREDICTO_OK)
        contrato = {"numero": contrato_ver.get("numero"),
                    "contratista": nombre,
                    "fecha": (contrato_ver.get("fecha_suscripcion")
                              or contrato_ver.get("fecha")),
                    "del_emisor": bool(del_emisor),
                    "otros": [str(x) for x in
                              (contrato_ver.get("otros_contratos_expediente") or [])
                              if _texto(x)]}

    resolucion = None
    numero_res = _texto(resol_ver.get("numero") or resol_leida.get("numero")) or None
    fecha_res = resol_leida.get("fecha") or resol_ver.get("fecha")
    if (numero_res or fecha_res or resol_ver.get("documento")
            or resol_leida.get("fecha_descartada")):
        resolucion = {"numero": numero_res, "fecha": fecha_res,
                      "coincide_emisor": resol_leida.get("coincide_emisor"),
                      "fecha_descartada": resol_leida.get("fecha_descartada"),
                      "fecha_motivo": resol_leida.get("fecha_motivo")}

    if contrato and resolucion:
        estado = MEF_AMBOS
    elif contrato:
        estado = MEF_CONTRATO
    elif resolucion:
        estado = MEF_RESOLUCION
    else:
        # No vino marcado `sin_documentos_mef` pero tampoco hay documento legible:
        # se declara la ausencia, nunca un respaldo que no existe.
        estado = MEF_SIN_DOCUMENTOS
    return {"estado": estado, "contrato": contrato, "resolucion": resolucion,
            "texto": texto}


# ── Cubetas de días por certeza (misma aritmética que la PARTE 5) ────────────
#: Cubeta de `bucket_certeza` → clave del resumen que consume el Panel.
CLAVE_RESUMEN = {
    BUCKET_CONFIRMADO: "citado_confirmado",
    BUCKET_INFERIDO: "inferido",
    BUCKET_SIN_IDENTIFICAR: "sin_identificar",
    BUCKET_PRIVADA: "privada",
}


def resumen_certeza_profesional(prof: Optional[dict],
                                enr_todo: Optional[dict],
                                regla_periodos: str,
                                tipo_evaluacion: Optional[str] = None) -> dict:
    """Días del profesional repartidos por certeza de identificación.

    Reproduce la aritmética de la PARTE 5 de expedientes (`excel_final._p5_exp`
    / `_p5_tot_exp`): una sola fuente de fechas (`fechas_calculo` con la regla
    de las bases), paralizaciones recortadas al periodo — y nunca en un
    expediente ni en una obra privada —, y ALT11 (`dias_efectivos_profesional`)
    para el total y el traslape. El Excel NO se refactoriza: hay un test que
    compara ambas salidas para que no se separen.

    `enr_todo` es el enriquecimiento completo del job (`{"N:M": {...}}`), tal
    como lo persiste el orquestador. Devuelve::

        {"citado_confirmado": {"experiencias": n, "dias": d}, "inferido": {...},
         "sin_identificar": {...}, "privada": {...},
         "dias_efectivos": d, "dias_traslape": d}

    `experiencias` cuenta TODAS las de esa cubeta (también las de fechas
    ilegibles, que no aportan días): el Panel debe poder decir «1 experiencia,
    0 días» sin que la fila desaparezca.
    """
    from reglas.calculo import (dias_efectivos_profesional, dias_inclusivos,
                                periodo_fechas, restar_paralizaciones)
    from resolucion.cui import es_expediente_exp
    from validacion.recalculo import fechas_calculo

    prof = _dic(prof)
    enr_todo = enr_todo if isinstance(enr_todo, dict) else {}
    np_ = prof.get("n_prof")

    periodos: list = []
    paral_por_idx: dict = {}
    dias = {clave: 0 for clave in CLAVE_RESUMEN.values()}
    conteo = {clave: 0 for clave in CLAVE_RESUMEN.values()}

    for exp in prof.get("experiencias") or []:
        exp = _dic(exp)
        enr = _dic(enr_todo.get(f"{np_}:{exp.get('n')}"))
        cubeta = CLAVE_RESUMEN[bucket_certeza(clasificar_identificacion(exp, enr))]
        conteo[cubeta] += 1

        ini, fin, _deducida = fechas_calculo(exp, regla_periodos)
        if not (ini and fin) or fin < ini:
            continue
        idx = len(periodos)
        periodos.append((ini, fin))

        # La ejecución física no descuenta tiempo de un expediente, y a una obra
        # privada no le aplican las fuentes públicas.
        clamp: list = []
        privada = _texto(enr.get("via")).upper() == "PRIVADA"
        if not (privada or es_expediente_exp(exp, tipo_evaluacion)):
            for p in enr.get("paralizaciones") or []:
                try:
                    p_i, p_f = periodo_fechas(p)
                except (ValueError, TypeError, KeyError, IndexError):
                    continue        # dato corrupto del portal: no tumba el panel
                c_i, c_f = max(p_i, ini), min(p_f, fin)
                if c_f >= c_i:
                    clamp.append((c_i, c_f))
        if clamp:
            paral_por_idx[idx] = clamp
        dias[cubeta] += sum(dias_inclusivos(a, b) for a, b
                            in restar_paralizaciones((ini, fin), clamp))

    res = dias_efectivos_profesional(periodos, paral_por_idx) if periodos else None
    salida = {clave: {"experiencias": conteo[clave], "dias": dias[clave]}
              for clave in CLAVE_RESUMEN.values()}
    salida["dias_efectivos"] = res.dias_efectivos if res else 0
    salida["dias_traslape"] = res.dias_traslape if res else 0
    return salida
