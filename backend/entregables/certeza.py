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


#: Lo que se lee cuando el MEF no publicó documentos del expediente.
SIN_DOCUMENTOS_MEF = ("El MEF no publica contrato ni resolución de este "
                      "expediente — cuenta por el certificado")

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
    if enr.get("sin_documentos_mef") or not (ver or resol_leida or contrato_emisor):
        return {"sin_documentos": True, "contrato": SIN_DOCUMENTOS_MEF,
                "resolucion": "—", "consultor": "—"}

    contrato = _dic(ver.get("contrato"))
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
        texto_contrato = "El MEF no publica el contrato de este expediente"

    numero_res = _texto(_dic(ver.get("resolucion")).get("numero")
                        or resol_leida.get("numero"))
    fecha_res = _fecha(resol_leida.get("fecha")
                       or _dic(ver.get("resolucion")).get("fecha"))
    descartada = _fecha(resol_leida.get("fecha_descartada"))
    if numero_res or fecha_res or descartada:
        texto_resol = "Resolución de aprobación N° " + (numero_res or "s/n")
        if fecha_res:
            texto_resol += f" del {fecha_res}"
        elif descartada:
            # La fecha se leyó pero no era plausible: se dice cuál se descartó y
            # por qué, en vez de callar (una fecha inventada es peor que ninguna).
            motivo = _texto(resol_leida.get("fecha_motivo"))
            texto_resol += (f" — fecha no legible con certeza (se descartó "
                            f"{descartada}{': ' + motivo if motivo else ''})")
    else:
        texto_resol = "El MEF no publica la resolución que aprobó el expediente"

    consultor = _CONSULTOR.get(_texto(resol_leida.get("coincide_emisor")),
                               "Consultor según resolución: sin resolución leída")
    return {"sin_documentos": False, "contrato": texto_contrato,
            "resolucion": texto_resol, "consultor": consultor}
