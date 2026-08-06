"""
Prelimpiado compartido de nombres de entidad/empresa. Puro, sin red.

Por qué existe
──────────────
Tres sitios del backend preguntan «¿estos dos nombres son la misma empresa?» y
lo hacen con DOS comparadores distintos:

    scraping/sunat.py::score_match_empresa   → cruce SUNAT, candado SEACE, #58
    scraping/mef.py::_nombres_coinciden      → bloque de verificación de expedientes

Antes de decidir cuál sobrevive (T-REFACTOR-002) hay una mejora que no cambia
ningún criterio y que los beneficia a los dos por igual: **limpiar la entrada**.
El nombre que llega del certificado no es una razón social, es lo que el emisor
tipeó en el membrete, y suele arrastrar la composición del consorcio entre
paréntesis:

    «CONSORCIO HOSPITAL ABANCAY (COLESI Contratistas Generales S.A. & JOCA
     Ingenieria y Construccion S.A.)»   vs   «CONSORCIO HOSPITAL ABANCAY»

Ese paréntesis vale 46/100 en el comparador de SUNAT — el candado SEACE lo lee
como señal FUERTE **en contra** («son entidades distintas») sobre dos nombres
que son el MISMO consorcio con el mismo RUC. Quitándolo: 100/100. Medido sobre
los espejos de `datos_pivote/`, 7 de las 25 divergencias reales entre ambos
comparadores son exactamente esto: basura de entrada, no desacuerdo de criterio.

Por qué en `scraping/` y no dentro de `sunat.py`
────────────────────────────────────────────────
Lo consumen `scraping/sunat.py` (vía sus llamadores), `scraping/mef.py`,
`validacion/candado_seace.py` y `orquestador/etapas_reales.py`. Meterlo en
`sunat.py` obligaría a `mef.py` a importar del scraper de SUNAT para limpiar un
nombre que nada tiene que ver con SUNAT. Este módulo no importa nada del
proyecto (solo `re`), así que ninguna de esas cuatro zonas gana una dependencia
ni se abre un ciclo — el mismo trato que `errores_red.py`.

Es además el sitio donde vivirá el comparador único cuando se ejecute la doble
corrida de T-REFACTOR-002; hoy solo hospeda el prelimpiado.
"""
from __future__ import annotations

import re

# Paréntesis: composición del consorcio, glosa del cargo, alias. Nunca aportan a
# la identidad de la razón social y sí hunden cualquier similitud por longitud.
_RE_PARENTESIS = re.compile(r"\(.*?\)")
# Cola «RUC 20…»: el número se extrae aparte (`_RE_RUC`), en el nombre estorba.
_RE_COLA_RUC = re.compile(r"\bRUC\b.*$", re.I)
_RE_WS = re.compile(r"\s+")


def limpiar_nombre_entidad(nombre: str) -> str:
    """Nombre de entidad listo para comparar: sin paréntesis ni cola «RUC …».

    NO normaliza (no toca tildes, sufijos legales ni mayúsculas) — de eso se
    encarga cada comparador con su propio criterio, que este helper no cambia.

    Guardarraíl: si limpiar dejaría el nombre VACÍO (un valor que es solo el
    paréntesis, p. ej. «(sin datos)»), devuelve el original colapsado. Vaciar un
    nombre no es limpiarlo: los dos comparadores responden `0`/`False` ante un
    string vacío, y eso convertiría un dato pobre en una respuesta falsa.
    """
    original = _RE_WS.sub(" ", str(nombre or "")).strip()
    if not original:
        return ""
    s = _RE_PARENTESIS.sub(" ", original)
    s = _RE_COLA_RUC.sub(" ", s)
    s = _RE_WS.sub(" ", s).strip()
    return s or original


def variantes(nombre: str) -> tuple[str, ...]:
    """El nombre tal cual **y** su versión prelimpiada, sin repetir.

    Por qué las dos y no solo la limpia: el paréntesis no siempre es ruido. En
    los espejos hay las dos formas y son opuestas —

        «CONSORCIO HOSPITAL ABANCAY (COLESI … & JOCA …)»
            el paréntesis ESTORBA: son los miembros, no la identidad. 46 → 100.
        «DIESA S.R.L. (Promotora, Constructora e Inmobiliaria Diaz Espinoza
         Asociados S.R.L.)»   vs   la razón social SUNAT del mismo RUC
            el paréntesis ES la identidad: afuera quedó solo la sigla. 93 → 15.

    Distinguir un caso del otro exige criterio nuevo, y esta tarea no toca
    ningún criterio. Así que se prueban las dos formas y el consumidor se queda
    con la MEJOR. La consecuencia importante es que el cambio es **monótono**:
    un veredicto solo puede mejorar (`no_verificable` → `ok`), nunca al revés.
    """
    crudo = _RE_WS.sub(" ", str(nombre or "")).strip()
    limpio = limpiar_nombre_entidad(crudo)
    return (crudo,) if limpio == crudo else (crudo, limpio)
