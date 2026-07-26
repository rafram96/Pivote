"""
Escudo de integridad de la evaluación (issue #45, capa L1).

`agent-evaluador` es un LLM y el consolidador de la skill acepta lo que devuelve
sin verificar nada: `(ev.profesionales_eval || {})[String(i)] || {}`. Si la fila
falta, los campos quedan `null`, el espejo valida igual (son opcionales) y el
formato sale con columnas en blanco sin que nadie se entere. Si las filas vienen
CORRIDAS, cada profesional recibe el veredicto del siguiente: un falso NO CUMPLE
y un falso CUMPLE a la vez, ambos con razones literales que suenan convincentes.

Este módulo NO re-evalúa la propuesta (el backend no juzga: esa decisión es de
Claude y del Comité). Solo comprueba que lo entregado CORRESPONDA a lo pedido:
que las columnas del evaluador no vengan vacías y que el sustento de cada
profesional hable de SU especialidad y de SUS experiencias.

Tres principios que fijan la calibración:

  1. **La falla es POR PROFESIONAL, no por corrida.** El consolidador pierde la
     fila `[String(i)]`, así que la ausencia le pasa a UN profesional aunque los
     demás vengan bien. Por eso la cobertura se mide y se reporta profesional
     por profesional: si se promediara, nueve sin evaluar se esconderían detrás
     de uno completo.
  2. **Invalidar la corrida exige PATRÓN, no dos coincidencias.** Dos sustentos
     que nombren de pasada la especialidad vecina son ruido de redacción, no un
     corrimiento. Para decir «repítalo todo» hace falta el mismo desplazamiento
     en la mayoría de los profesionales, o evidencia independiente que lo
     corrobore (los avisos `cargo_corregido`, o los requisitos también corridos).
  3. **Falla CERRADO.** Si el espejo no tiene la forma esperada, el veredicto es
     `no_revisable` — nunca «confiable». Un escudo que llama sano a lo que no
     pudo mirar es peor que no tener escudo.

Todas las funciones son puras: reciben el espejo como dict y devuelven
`Hallazgo`. El cableado al pipeline lo hace el integrador; `a_observaciones()`
convierte a `pipeline.Observacion` en una línea.

Dos fallas reales medidas (26-jul) que fijan la calibración:
  A · corrimiento +1  (job 36d710f27694) — 10 profesionales con el veredicto del
      siguiente; el nº10 sin veredicto; 7 avisos `cargo_corregido`.
  B · ausencia total  (job 95af90f1578e) — 0/63 experiencias y 0/10
      profesionales con campos del evaluador.
  Referencia sana (no debe disparar NI UN hallazgo): ffbda008a346.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

# ── Vocabulario de severidades ───────────────────────────────────────────────
# Strings iguales a los valores de `schemas.pipeline.Severidad`, para que el
# integrador convierta sin traducir. Se usan strings (y no el Enum) para que el
# módulo se pueda probar y reusar sin arrastrar el schema del pipeline.
INFO = "info"
ADVERTENCIA = "advertencia"
ALERTA = "alerta"
CRITICA = "critica"

_ORDEN_SEV = {CRITICA: 0, ALERTA: 1, ADVERTENCIA: 2, INFO: 3}

# Inventario de todo lo que este módulo puede decir. Está aquí —y no solo
# repartido por el código— para que el test de lenguaje pueda exigir que NINGÚN
# mensaje visible se le escape: los lee el Ing. Manuel, no un programador.
CODIGOS = (
    "SIN_EVALUACION",           # nadie tiene nada del evaluador
    "EVALUACION_INCOMPLETA",    # falta buena parte del equipo
    "PROFESIONAL_SIN_EVALUAR",  # a ESE profesional no le llegó nada
    "EXPERIENCIA_SIN_EVALUAR",  # a ESA fila no le llegó nada
    "COBERTURA_NULA",           # una columna del formato sale en blanco
    "VEREDICTO_AJENO",          # el sustento habla de otra especialidad
    "CORRIMIENTO",              # patrón: los sustentos se corrieron
    "POSIBLE_CORRIMIENTO",      # dos coincidencias, sin patrón que las respalde
    "VEREDICTO_COLA",           # el último se quedó sin veredicto
    "EXPERIENCIA_INEXISTENTE",  # el sustento cita una experiencia que no existe
    "CONTEO_DESCUADRA",         # cita más/menos documentos de los registrados
    "REQUISITO_AJENO",          # medido con la vara de otro cargo (con dueño)
    "REQUISITO_DUDOSO",         # el nombre no calza, pero nadie reclama ese cargo
    "CORRIMIENTO_REQUISITOS",   # patrón: los requisitos se aplicaron corridos
    "CARGO_CORREGIDO",          # la propia skill tuvo que corregir cargos
    "NO_REVISABLE",             # no se pudo mirar (falla cerrado)
)

# ── Vocabulario de veredictos de confiabilidad ───────────────────────────────
CONFIABLE = "confiable"
REVISAR = "revisar"
NO_CONFIABLE = "no_confiable"
NO_REVISABLE = "no_revisable"      # no se pudo mirar: nunca es luz verde


@dataclass(frozen=True)
class Hallazgo:
    """Un problema de integridad. `mensaje` lo lee un evaluador, no un programador."""
    codigo: str
    severidad: str
    mensaje: str
    n_prof: Optional[int] = None
    n_exp: Optional[int] = None

    @property
    def referencia(self) -> Optional[str]:
        """Formato `prof=7 exp=2` — el mismo que usa el resto del validador."""
        partes = []
        if self.n_prof is not None:
            partes.append(f"prof={self.n_prof}")
        if self.n_exp is not None:
            partes.append(f"exp={self.n_exp}")
        return " ".join(partes) or None


@dataclass(frozen=True)
class Confiabilidad:
    """Veredicto agregado de la corrida, para marcar el job."""
    veredicto: str          # confiable | revisar | no_confiable | no_revisable
    motivo: str             # una línea, redactada para el evaluador
    hallazgos: list = field(default_factory=list)

    @property
    def confiable(self) -> bool:
        return self.veredicto == CONFIABLE


# ── Campos que produce EXCLUSIVAMENTE agent-evaluador ────────────────────────
# Verificado en skill/scripts/consolidar_espejo.js: estos cuatro salen solo de
# `j` (la fila de experiencias_eval). Los que tienen respaldo del extractor
# (`cert_antes_culminar`, `cargo_valido_emitir`, `funciones_similares`) NO van
# aquí: aparecen llenos aunque el evaluador no haya entregado nada, así que no
# dicen nada sobre su cobertura.
CAMPOS_EXP = {
    "dias": "los días de experiencia",
    "cargo_bases_valido": "si el cargo certificado vale para las bases",
    "tipo_obra_valido": "si el tipo de obra vale para las bases",
    "anterior_colegiatura": "si la experiencia es anterior a la colegiatura",
}
CAMPOS_PROF = {
    "cumple": "el veredicto de cumplimiento",
    "profesion_valida": "si la profesión es la que piden las bases",
}

# Una experiencia sin `dias` es legítima (fecha ilegible); TODAS sin `dias` no lo
# es. Por eso el criterio es cobertura CERO, no un porcentaje: así un vacío
# legítimo aislado nunca dispara. Con 1 ó 2 filas el vacío total todavía puede
# ser legítimo, de modo que se exige un mínimo de filas para hablar de "columna
# en blanco" (medido sobre el corpus real: ningún espejo sano llega a cero).
MIN_FILAS_COBERTURA = 3

# Más de esto y se agrega en un solo hallazgo por profesional: un panel con 19
# avisos de la misma cosa no se lee.
MAX_FILAS_DETALLADAS = 3


# ── Normalización de texto ───────────────────────────────────────────────────
# Raíz de 7 letras: junta singular/plural y masculino/femenino ("sanitario" /
# "sanitarias" → "sanitar") sin fundir especialidades distintas — con 6 letras
# "eléctrico" y "electrónico" colisionan y se pierde un corrimiento real.
_LARGO_RAIZ = 7
_PALABRA = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)

# Palabras que aparecen en casi todos los cargos ("Especialista en Instalaciones
# …"): no distinguen a nadie y, si se dejan, tapan un veredicto ajeno.
_GENERICAS = frozenset({
    "especia", "ingenie", "obra", "instala", "inst", "profesi", "cargo",
    "similar", "valido", "tecnico", "del", "los", "las", "que", "con", "por",
    "para", "una", "uno", "sus", "como", "sin", "mas", "ano",
})


def _sin_tildes(palabra: str) -> str:
    plano = unicodedata.normalize("NFD", palabra.lower())
    return "".join(c for c in plano if not unicodedata.combining(c))


def _tokens(texto) -> list[tuple[str, str]]:
    """Pares (palabra tal como se lee, raíz) del texto. Ignora las genéricas."""
    if not isinstance(texto, str) or not texto.strip():
        return []
    out = []
    for palabra in _PALABRA.findall(texto):
        plano = _sin_tildes(palabra)
        if len(plano) < 3:
            continue
        if plano.endswith("s"):          # plural → singular antes de recortar
            plano = plano[:-1]
        raiz = plano[:_LARGO_RAIZ]
        if len(raiz) >= 3 and raiz not in _GENERICAS:
            out.append((palabra.lower(), raiz))
    return out


def _raices(texto) -> set[str]:
    """Palabras del texto reducidas a raíz, sin tildes, sin genéricas."""
    return {raiz for _palabra, raiz in _tokens(texto)}


def _palabras_de(texto, raices: set[str]) -> list[str]:
    """Las palabras del texto —tal como se leen— cuya raíz está en `raices`.

    El mensaje lo lee el Ing. Manuel: tiene que decir «valorizaciones», no
    «valoriz». Las raíces son una herramienta interna, no algo que mostrar.
    """
    vistas, out = set(), []
    for palabra, raiz in _tokens(texto):
        if raiz in raices and raiz not in vistas:
            vistas.add(raiz)
            out.append(palabra)
    return out


def _profesionales(espejo) -> list[dict]:
    if not isinstance(espejo, dict):
        return []
    profs = espejo.get("profesionales")
    return [p for p in profs if isinstance(p, dict)] if isinstance(profs, list) else []


def _experiencias(prof: dict) -> list[dict]:
    exps = prof.get("experiencias")
    return [e for e in exps if isinstance(e, dict)] if isinstance(exps, list) else []


def _lleno(v) -> bool:
    return v is not None and not (isinstance(v, str) and not v.strip())


def _etiqueta(prof: dict) -> str:
    """«N°7 (Especialista en Inst. Comunicaciones TIC)» — para el mensaje.

    Sin número (o sin cargo) se degrada a lo que haya: el mensaje lo lee una
    persona, así que nunca puede salir un «N°None».
    """
    cargo = prof.get("cargo")
    cargo = cargo.strip() if isinstance(cargo, str) and cargo.strip() else None
    n = prof.get("n_prof")
    if not isinstance(n, int):
        return f"«{cargo}»" if cargo else "sin identificar"
    return f"N°{n} ({cargo})" if cargo else f"N°{n}"


def _es_patron(veces: int, universo: int) -> bool:
    """¿Lo repetido alcanza para hablar de una corrida entera desalineada?

    Dos casos son dos casos. Se exige (a) al menos tres y (b) que sean la mayoría
    de aquellos sobre los que el candado pudo pronunciarse. Sin las dos cosas, lo
    observado se reporta como lo que es: hallazgos sueltos que hay que revisar.
    """
    return veces >= 3 and veces * 2 >= universo


# ── 1 · Cobertura: lo que el evaluador no entregó ────────────────────────────

def _trae_algo_del_evaluador(prof: dict) -> bool:
    """¿A este profesional le llegó ALGO del evaluador?

    Es la firma exacta del fallo del consolidador: si falta su índice, el
    profesional queda sin veredicto Y sus experiencias sin ningún cálculo.
    """
    if any(_lleno(prof.get(campo)) for campo in CAMPOS_PROF):
        return True
    return any(_lleno(exp.get(campo))
               for exp in _experiencias(prof) for campo in CAMPOS_EXP)


def _experiencia_vacia(exp: dict) -> bool:
    return not any(_lleno(exp.get(campo)) for campo in CAMPOS_EXP)


def cobertura_evaluador(espejo: dict) -> list[Hallazgo]:
    """Qué partes de la evaluación no llegaron — profesional por profesional."""
    profs = _profesionales(espejo)
    if not profs:
        return []
    exps_totales = [e for p in profs for e in _experiencias(p)]
    sin_evaluar = [p for p in profs if not _trae_algo_del_evaluador(p)]

    # Nadie tiene nada: el formato solo trae los datos copiados de la propuesta.
    if len(sin_evaluar) == len(profs):
        return [Hallazgo(
            "SIN_EVALUACION", CRITICA,
            f"Este análisis llegó SIN evaluación: ninguno de los {len(profs)} "
            f"profesionales tiene veredicto y ninguna de las {len(exps_totales)} "
            f"experiencias tiene cálculo. Hay que volver a correrlo — el formato "
            f"solo trae los datos copiados de la propuesta.")]

    out: list[Hallazgo] = []
    for prof in sin_evaluar:
        out.append(Hallazgo(
            "PROFESIONAL_SIN_EVALUAR", ALERTA,
            f"Al profesional {_etiqueta(prof)} no le llegó NADA de la evaluación: "
            f"ni veredicto de cumplimiento ni cálculo de sus experiencias, aunque "
            f"el análisis sí evaluó a otros. Su parte del formato sale en blanco: "
            f"hay que evaluarlo antes de usar este archivo.",
            n_prof=prof.get("n_prof")))

    # Que falte medio equipo no es un hueco: es una corrida a medias.
    if len(sin_evaluar) >= 2 and len(sin_evaluar) * 2 >= len(profs):
        out.insert(0, Hallazgo(
            "EVALUACION_INCOMPLETA", CRITICA,
            f"{len(sin_evaluar)} de los {len(profs)} profesionales quedaron SIN "
            f"evaluar. No es un dato suelto que falte: falta la evaluación de buena "
            f"parte del equipo, así que este análisis hay que volver a correrlo."))

    evaluados = [p for p in profs if _trae_algo_del_evaluador(p)]
    out += _columnas_en_blanco(evaluados)
    out += _filas_sin_evaluar(evaluados)
    return out


def _columnas_en_blanco(evaluados: list[dict]) -> list[Hallazgo]:
    """Una columna del formato que sale vacía en TODOS los que sí se evaluaron."""
    out: list[Hallazgo] = []
    exps = [e for p in evaluados for e in _experiencias(p)]

    if len(exps) >= MIN_FILAS_COBERTURA:
        for campo, glosa in CAMPOS_EXP.items():
            if any(_lleno(e.get(campo)) for e in exps):
                continue
            out.append(Hallazgo(
                "COBERTURA_NULA", ALERTA,
                f"No se evaluó {glosa} en NINGUNA de las {len(exps)} experiencias "
                f"del análisis: esa columna del formato sale en blanco. El archivo "
                f"se ve completo, pero ese dato no está evaluado."))

    if len(evaluados) >= MIN_FILAS_COBERTURA:
        for campo, glosa in CAMPOS_PROF.items():
            if any(_lleno(p.get(campo)) for p in evaluados):
                continue
            out.append(Hallazgo(
                "COBERTURA_NULA", ALERTA,
                f"No se registró {glosa} en NINGUNO de los {len(evaluados)} "
                f"profesionales evaluados: esa columna del formato sale en blanco."))
    return out


def _filas_sin_evaluar(evaluados: list[dict]) -> list[Hallazgo]:
    """Experiencias sin ningún dato del evaluador, teniendo hermanas con datos.

    Es el mismo fallo del consolidador un nivel más abajo. El veredicto y el
    cálculo se buscan por separado (`profesionales_eval[i]` y
    `experiencias_eval[i]`), así que un profesional puede traer veredicto y NO
    traer ni un cálculo detrás — o perder solo una fila (`eeByN[n]`) dentro de un
    bloque por lo demás completo.
    """
    con_calculo = [p for p in evaluados
                   if any(not _experiencia_vacia(e) for e in _experiencias(p))]
    out: list[Hallazgo] = []
    for prof in evaluados:
        exps = _experiencias(prof)
        if len(exps) < 2:
            continue                   # con una sola fila no hay hermana que contraste
        vacias = [e for e in exps if _experiencia_vacia(e)]
        if not vacias:
            continue

        if len(vacias) == len(exps):
            # A NADIE se le calculó nada → eso es una columna en blanco y ya lo
            # dice `_columnas_en_blanco`; repetirlo por profesional sería ruido.
            otros = [p for p in con_calculo if p is not prof]
            if not otros or len(exps) < MIN_FILAS_COBERTURA:
                continue
            out.append(Hallazgo(
                "EXPERIENCIA_SIN_EVALUAR", ALERTA,
                f"Ninguna de las {len(exps)} experiencias del profesional "
                f"{_etiqueta(prof)} tiene cálculo, aunque él sí tiene veredicto y a "
                f"los demás profesionales sí se les calcularon las suyas. Ese "
                f"veredicto no se apoya en ningún dato: hay que rehacerlo.",
                n_prof=prof.get("n_prof")))
            continue

        if len(vacias) > MAX_FILAS_DETALLADAS:
            out.append(Hallazgo(
                "EXPERIENCIA_SIN_EVALUAR", ALERTA,
                f"{len(vacias)} de las {len(exps)} experiencias del profesional "
                f"{_etiqueta(prof)} quedaron sin evaluar: esas filas del formato "
                f"salen en blanco mientras las otras sí tienen cálculo.",
                n_prof=prof.get("n_prof")))
            continue
        for exp in vacias:
            n = exp.get("n") if isinstance(exp.get("n"), int) else exps.index(exp) + 1
            folio = exp.get("folio")
            de_donde = f", del folio {folio}," if isinstance(folio, int) else ""
            out.append(Hallazgo(
                "EXPERIENCIA_SIN_EVALUAR", ALERTA,
                f"La experiencia n°{n} del profesional {_etiqueta(prof)}"
                f"{de_donde} quedó sin evaluar: no tiene días ni validación de "
                f"cargo ni de tipo de obra, aunque sus otras experiencias sí. Esa "
                f"fila del formato sale en blanco.",
                n_prof=prof.get("n_prof"), n_exp=n))
    return out


# ── 2 · Veredicto ajeno / corrimiento ────────────────────────────────────────

def _distintivas(profs: list[dict]) -> dict[int, set[str]]:
    """Raíces del cargo que identifican a UN solo profesional de la lista.

    Lo compartido (supervisor, coordinador…) no sirve para decidir de quién
    habla un texto; solo lo exclusivo. Si dos profesionales declaran el mismo
    cargo, ninguno tiene raíces exclusivas y el candado se abstiene con ellos.
    """
    por_prof = {}
    for i, p in enumerate(profs):
        por_prof[i] = _raices(p.get("cargo"))
    cuenta = Counter(r for rs in por_prof.values() for r in rs)
    return {i: {r for r in rs if cuenta[r] == 1} for i, rs in por_prof.items()}


def _cargos_validos(prof: dict) -> str:
    """`requisitos.cargos_validos` como texto (llega como lista o como string)."""
    req = prof.get("requisitos")
    validos = req.get("cargos_validos") if isinstance(req, dict) else None
    if isinstance(validos, (list, tuple)):
        return "; ".join(str(v) for v in validos)
    return validos if isinstance(validos, str) else ""


def _vocabulario_propio(prof: dict, distintivas: set[str]) -> set[str]:
    """Lo exclusivo de su cargo + todos los cargos que las bases le aceptan.

    Los `cargos_validos` entran para NO acusar de ajeno un veredicto que usa el
    sinónimo de las bases en vez del título del cargo ("tecnología de
    información y comunicaciones" por "TIC").
    """
    return distintivas | _raices(_cargos_validos(prof))


def _vocabulario_del_concurso(profs: list[dict]) -> set[str]:
    """Raíces presentes en la mayoría de los sustentos.

    "salud" está en todos los veredictos de un concurso hospitalario porque es
    el objeto del concurso, no la especialidad de nadie; si se deja pasar,
    cualquier texto queda atribuido al profesional cuyo cargo la contenga
    ("Especialista en Seguridad y SALUD en el Trabajo"). Se descarta lo que
    comparte la mayoría: solo lo que aparece en pocos sustentos identifica.
    """
    textos = [_raices(p.get("cumple")) for p in profs if isinstance(p.get("cumple"), str)]
    if len(textos) < 3:
        return set()                   # con 2 sustentos no hay "mayoría" que medir
    cuenta = Counter(r for t in textos for r in t)
    umbral = max(2, (len(textos) + 1) // 2)
    return {r for r, c in cuenta.items() if c >= umbral}


def veredictos_ajenos(espejo: dict) -> list[Hallazgo]:
    """Detecta veredictos que hablan de la especialidad de OTRO profesional.

    Dispara solo con las dos condiciones a la vez: (a) el texto no menciona
    nada propio del profesional y (b) sí menciona algo exclusivo de otro. Con
    una sola de las dos habría falsos positivos — un veredicto escueto no es
    prueba de nada.

    Cada caso es una ALERTA (revisar ese sustento). Declarar la corrida entera
    inservible es otra cosa: para eso hace falta patrón (el mismo desplazamiento
    en la mayoría) o corroboración independiente. En el corpus real hay
    evaluadores que escriben sustentos escuetos y otros que nombran de pasada la
    especialidad vecina; con dos coincidencias así se invalidaría trabajo bueno.
    """
    profs = _profesionales(espejo)
    if len(profs) < 2:
        return []                      # sin con quién comparar no hay señal
    distintivas = _distintivas(profs)
    comunes = _vocabulario_del_concurso(profs)

    out: list[Hallazgo] = []
    desplazamientos: list[int] = []
    evaluables = 0
    for i, prof in enumerate(profs):
        texto = prof.get("cumple")
        if not isinstance(texto, str) or not texto.strip():
            continue
        propio = _vocabulario_propio(prof, distintivas[i])
        if not propio:
            continue                   # sin vocabulario propio: abstenerse
        evaluables += 1
        raices = _raices(texto)
        if raices & propio:
            continue                   # habla de lo suyo

        # A quién pertenece el texto: al que más palabras suyas —y solo suyas—
        # aparezcan. Empate → el más cercano en la lista (un corrimiento mueve
        # una o dos posiciones, no diez), y a igual distancia el de más arriba.
        candidatos = [((distintivas[j] - comunes) & raices, j)
                      for j in range(len(profs)) if j != i]
        pistas, j = max(candidatos, key=lambda c: (len(c[0]), -abs(c[1] - i), -c[1]))
        if not pistas:
            continue                   # no habla de lo suyo, pero tampoco de otro

        ajeno = profs[j]
        desplazamientos.append(j - i)
        dichas = _palabras_de(texto, pistas)
        out.append(Hallazgo(
            "VEREDICTO_AJENO", ALERTA,
            f"El sustento del profesional {_etiqueta(prof)} no habla de su "
            f"especialidad: menciona {', '.join(f'«{p}»' for p in dichas)}, "
            f"que es lo propio del profesional {_etiqueta(ajeno)}. Parece el "
            f"veredicto de otro profesional — ni este resultado ni el de "
            f"{_etiqueta(ajeno)} son de fiar.",
            n_prof=prof.get("n_prof")))

    if len(desplazamientos) >= 2:
        paso, veces = Counter(desplazamientos).most_common(1)[0]
        if veces >= 2:
            out.insert(0, _corrimiento(espejo, profs, paso, veces, evaluables))
    return out


def _corrimiento(espejo: dict, profs: list[dict], paso: int, veces: int,
                 evaluables: int) -> Hallazgo:
    """Corrimiento sistemático (crítica) o coincidencia repetida (alerta).

    La diferencia no la hace el candado léxico consigo mismo: la hace el patrón
    (mayoría de los evaluables movidos igual) o una evidencia INDEPENDIENTE del
    texto — que la propia skill haya tenido que corregir cargos, o que los
    requisitos de las bases estén corridos el mismo número de puestos.
    """
    corroboran = []
    if len(_avisos_cargo_corregido(espejo)) >= 2:
        corroboran.append("el sistema ya tuvo que corregir el cargo de varios profesionales")
    mismo_paso_requisitos = sum(1 for _i, _dueno, d in _requisitos_ajenos(profs) if d == paso)
    if mismo_paso_requisitos >= 2:
        corroboran.append("los requisitos de las bases también quedaron corridos igual")

    if _es_patron(veces, evaluables) or corroboran:
        respaldo = f" Lo confirma que {corroboran[0]}." if corroboran else ""
        return Hallazgo(
            "CORRIMIENTO", CRITICA,
            f"Los sustentos quedaron CORRIDOS: {veces} de los {evaluables} "
            f"profesionales recibieron el del {_direccion(paso)}.{respaldo} Toda la "
            f"corrida hay que repetirla; entre esos resultados hay CUMPLE y NO "
            f"CUMPLE que no pertenecen a quien los tiene asignados.")
    return Hallazgo(
        "POSIBLE_CORRIMIENTO", ALERTA,
        f"{veces} de los {evaluables} profesionales tienen un sustento que suena "
        f"al del {_direccion(paso)}. Pueden ser dos redacciones desafortunadas o "
        f"el arranque de una evaluación corrida: hay que leer esos sustentos "
        f"antes de firmar, pero el resto del análisis se sostiene.")


def _direccion(paso: int) -> str:
    if paso == 1:
        return "profesional siguiente"
    if paso == -1:
        return "profesional anterior"
    return f"profesional {abs(paso)} puestos más {'abajo' if paso > 0 else 'arriba'}"


def veredicto_faltante_al_final(espejo: dict) -> list[Hallazgo]:
    """El último de la lista sin veredicto mientras los demás sí: firma del corrimiento.

    Si NADIE tiene veredicto no dispara — eso es ausencia total y lo reporta
    `cobertura_evaluador` (no es un corrimiento).
    """
    profs = _profesionales(espejo)
    if len(profs) < 2:
        return []
    con = [p for p in profs if _lleno(p.get("cumple"))]
    if not con or _lleno(profs[-1].get("cumple")):
        return []
    return [Hallazgo(
        "VEREDICTO_COLA", ALERTA,
        f"El último profesional de la lista, {_etiqueta(profs[-1])}, se quedó SIN "
        f"veredicto mientras los otros {len(con)} sí lo tienen. Es la señal típica "
        f"de una evaluación corrida un puesto: revisar a quién pertenece cada "
        f"sustento antes de usar este formato.",
        n_prof=profs[-1].get("n_prof"))]


# ── 3 · El veredicto cita experiencias que no existen ────────────────────────

# "n3", "n=3", "n 3" — pero NO "N° 3" (que numera profesionales o anexos).
_RE_INDICE = re.compile(r"\bn\s*=?\s*(\d{1,2})\b", re.IGNORECASE)
# "las 4 constancias", "ninguna de las 4 constancias", "las 3 obras".
_RE_CONTEO = re.compile(
    r"\b(?:las|los|de)\s+(\d{1,2})\s+"
    r"(constancias?|certificados?|experiencias?)\b", re.IGNORECASE)


def referencias_inexistentes(espejo: dict) -> list[Hallazgo]:
    """El sustento se refiere a experiencias o a un número de documentos que no tiene.

    Un certificado puede cubrir varios periodos (y un periodo puede tener dos
    documentos), así que el conteo citado NO tiene por qué igualar al número de
    filas: por eso el descuadre de conteo es advertencia — pista, no prueba.
    Citar una experiencia que no existe sí es objetivo.
    """
    out: list[Hallazgo] = []
    for prof in _profesionales(espejo):
        texto = prof.get("cumple")
        if not isinstance(texto, str) or not texto.strip():
            continue
        exps = _experiencias(prof)
        numeros = {e.get("n") for e in exps if isinstance(e.get("n"), int)}
        if not numeros:
            continue

        citados = sorted({int(m) for m in _RE_INDICE.findall(texto)} - numeros)
        # 0 no es un índice; los mayores al máximo real son los que delatan.
        citados = [c for c in citados if c > 0]
        if citados:
            lista = ", ".join(f"n°{c}" for c in citados)
            out.append(Hallazgo(
                "EXPERIENCIA_INEXISTENTE", ALERTA,
                f"El sustento del profesional {_etiqueta(prof)} se apoya en la(s) "
                f"experiencia(s) {lista}, que ese profesional NO tiene (solo se "
                f"registraron {len(exps)}). El sustento describe otro expediente.",
                n_prof=prof.get("n_prof")))

        for cantidad, _sustantivo in _RE_CONTEO.findall(texto):
            if int(cantidad) != len(exps):
                out.append(Hallazgo(
                    "CONTEO_DESCUADRA", ADVERTENCIA,
                    f"El sustento del profesional {_etiqueta(prof)} habla de "
                    f"{cantidad} documentos, pero se registraron {len(exps)} "
                    f"experiencias suyas. Puede ser legítimo (un certificado que "
                    f"cubre varios periodos); conviene confirmarlo.",
                    n_prof=prof.get("n_prof")))
                break                  # una sola nota por profesional
    return out


# ── 4 · Se le aplicaron los requisitos de otro cargo ─────────────────────────

def _requisitos_ajenos(profs: list[dict]) -> list[tuple[int, Optional[int], Optional[int]]]:
    """(i, dueño, desplazamiento) de cada profesional medido con la vara de otro.

    El cargo declarado no comparte NINGUNA palabra significativa con el cargo de
    bases que se le aplicó — ni con los `cargos_validos` de ese cargo, que son
    los sinónimos que las bases aceptan. Mirar también los `cargos_validos` evita
    acusar por abreviaturas del postor ("ESPECIALISTA EN IIEE" contra
    "Especialista en Instalaciones Eléctricas"): el cargo de bases sí lo admite.

    `dueño` es el profesional cuyo cargo declarado SÍ corresponde a esos
    requisitos. Sin dueño identificable la señal es débil (puede ser solo una
    diferencia de redacción) y quien llama se abstiene de acusar.
    """
    out = []
    for i, prof in enumerate(profs):
        propio = _raices(prof.get("cargo"))
        nombre_bases = _raices(prof.get("cargo_bases_nombre"))
        if not propio or not nombre_bases:
            continue                   # sin los dos nombres no hay nada que comparar
        if propio & (nombre_bases | _raices(_cargos_validos(prof))):
            continue                   # el cargo de bases sí cubre lo que declaró

        duenos = [j for j, otro in enumerate(profs)
                  if j != i and (_raices(otro.get("cargo")) & nombre_bases)]
        dueno = duenos[0] if len(duenos) == 1 else None
        out.append((i, dueno, (dueno - i) if dueno is not None else None))
    return out


def requisitos_de_otro_cargo(espejo: dict) -> list[Hallazgo]:
    """El cargo declarado y el cargo de las bases que se le aplicó no coinciden.

    Es el residuo del corrimiento que el candado `match_cargo.js` no alcanza a
    corregir: cuando no encuentra el cargo por nombre se queda con el número que
    puso el evaluador, y con él viajan los `cargos_validos` — se mide al
    profesional con la vara de otra especialidad.

    Basta UNA palabra significativa en común ("Supervisor de Obra" vs "Jefe de
    Supervisión de Obra" es el mismo cargo escrito distinto); se exige que no
    haya NINGUNA para no castigar diferencias de redacción.
    """
    profs = _profesionales(espejo)
    out: list[Hallazgo] = []
    desplazamientos: list[int] = []
    for i, dueno, paso in _requisitos_ajenos(profs):
        prof = profs[i]
        cargo_bases = f"el cargo N°{prof.get('cargo_bases_num')} de las bases " \
                      f"({prof.get('cargo_bases_nombre')})"
        if dueno is None:
            # Nadie más declara ese cargo: puede ser una abreviatura del postor
            # ("IIEE" por "Instalaciones Eléctricas"). Se avisa sin acusar.
            out.append(Hallazgo(
                "REQUISITO_DUDOSO", ADVERTENCIA,
                f"Al profesional {_etiqueta(prof)} se le aplicó {cargo_bases}, y el "
                f"nombre no se parece al cargo con el que se presentó. Puede ser la "
                f"misma especialidad escrita distinta (una abreviatura); conviene "
                f"confirmar que es el cargo que le toca.",
                n_prof=prof.get("n_prof")))
            continue

        desplazamientos.append(paso)
        out.append(Hallazgo(
            "REQUISITO_AJENO", ALERTA,
            f"Al profesional {_etiqueta(prof)} se le aplicaron los requisitos de "
            f"{cargo_bases}, que es otra especialidad. Esos requisitos son los del "
            f"profesional {_etiqueta(profs[dueno])}. Se le está midiendo con la "
            f"vara equivocada: su resultado no vale.",
            n_prof=prof.get("n_prof")))

    # Mismo desplazamiento en la mayoría = la tabla de cargos entera se corrió. Es
    # el residuo que `match_cargo.js` no pudo corregir (no encontró el cargo por
    # nombre y se quedó con el número del evaluador), y arrastra los requisitos.
    if len(desplazamientos) >= 2:
        paso, veces = Counter(desplazamientos).most_common(1)[0]
        comparables = sum(1 for p in profs
                          if _raices(p.get("cargo")) and _raices(p.get("cargo_bases_nombre")))
        if _es_patron(veces, comparables):
            out.insert(0, Hallazgo(
                "CORRIMIENTO_REQUISITOS", CRITICA,
                f"Los requisitos de las bases se aplicaron CORRIDOS: a {veces} de "
                f"los {comparables} profesionales se les exigió lo del "
                f"{_direccion(paso)}. Cada uno quedó medido con la vara de otra "
                f"especialidad, así que ningún CUMPLE ni NO CUMPLE de esta corrida "
                f"es utilizable."))
    return out


# ── 5 · Sospecha ya declarada por la propia skill ────────────────────────────

def _avisos(espejo) -> list[dict]:
    if not isinstance(espejo, dict):
        return []
    avisos = espejo.get("observaciones_claude")
    return [a for a in avisos if isinstance(a, dict)] if isinstance(avisos, list) else []


def _avisos_cargo_corregido(espejo) -> list[dict]:
    return [a for a in _avisos(espejo)
            if "cargo_corregido" in (str(a.get("tipo") or "") + str(a.get("codigo") or ""))]


def sospecha_declarada(espejo: dict) -> list[Hallazgo]:
    """Los avisos `cargo_corregido` del consolidador son señal de desalineación.

    Ese aviso significa que el evaluador asignó un cargo de las bases distinto al
    que dice el nombre del cargo declarado. El NÚMERO ya quedó corregido de forma
    determinística por `match_cargo.js`; lo que nadie corrigió es el TEXTO del
    veredicto que el evaluador escribió pensando en el otro cargo — y eso hay que
    leerlo. Es una señal INDIRECTA: por sí sola manda a revisar, nunca invalida la
    corrida. Invalidar exige evidencia directa (el texto del sustento o los
    requisitos), que es lo que miran los candados de arriba.
    """
    corregidos = _avisos_cargo_corregido(espejo)
    if not corregidos:
        return []
    if len(corregidos) == 1:
        return [Hallazgo(
            "CARGO_CORREGIDO", ALERTA,
            "El sistema tuvo que corregir el cargo que el evaluador asignó a 1 "
            "profesional. El cargo quedó bien; lo que hay que revisar es que su "
            "sustento hable de la especialidad correcta.")]
    return [Hallazgo(
        "CARGO_CORREGIDO", ALERTA,
        f"El sistema tuvo que corregir el cargo que el evaluador asignó a "
        f"{len(corregidos)} profesionales. Los cargos quedaron bien, pero "
        f"equivocarse en tantos indica que la evaluación venía desalineada: hay "
        f"que leer esos {len(corregidos)} sustentos y confirmar que hablan de la "
        f"especialidad que les toca.")]


# ── Corrida completa + veredicto agregado ────────────────────────────────────

def _revisable(espejo) -> bool:
    """¿El espejo tiene la forma mínima para poder revisarlo?

    No basta con que no reviente: si no hay una lista de profesionales, los
    candados no miran NADA y el silencio no significa que esté sano.
    """
    if not isinstance(espejo, dict):
        return False
    return bool(_profesionales(espejo))


MSG_NO_REVISABLE = (
    "No se pudo revisar este análisis: el archivo no trae la lista de "
    "profesionales, así que no hay nada contra qué contrastar la evaluación. NO "
    "quiere decir que esté bien — quiere decir que no se pudo mirar. Hay que "
    "volver a generarlo."
)


def revisar_integridad(espejo: dict) -> list[Hallazgo]:
    """Todos los candados de integridad sobre un espejo, lo más grave primero."""
    if not _revisable(espejo):
        return [Hallazgo("NO_REVISABLE", ALERTA, MSG_NO_REVISABLE)]
    hallazgos = (
        cobertura_evaluador(espejo)
        + veredictos_ajenos(espejo)
        + veredicto_faltante_al_final(espejo)
        + referencias_inexistentes(espejo)
        + requisitos_de_otro_cargo(espejo)
        + sospecha_declarada(espejo)
    )
    return sorted(hallazgos, key=lambda h: _ORDEN_SEV.get(h.severidad, 9))


def evaluar_confiabilidad(espejo: dict) -> Confiabilidad:
    """¿Se puede usar esta evaluación? Veredicto agregado para marcar el job.

    - no_revisable → el espejo no tiene la forma esperada y no se pudo revisar
      nada. Falla CERRADO: la ausencia de datos jamás se reporta como luz verde.
    - no_confiable → hay algo que invalida resultados (falso CUMPLE / falso NO
      CUMPLE en juego). No se entrega sin repetir la corrida.
    - revisar      → hay huecos o piezas sospechosas; el formato sirve, pero un
      humano tiene que mirar lo señalado antes de firmar.
    - confiable    → ningún candado disparó. NO significa que la evaluación sea
      correcta: significa que corresponde a lo que se pidió.
    """
    hallazgos = revisar_integridad(espejo)
    if hallazgos and hallazgos[0].codigo == "NO_REVISABLE":
        return Confiabilidad(NO_REVISABLE, MSG_NO_REVISABLE, hallazgos)
    graves = [h for h in hallazgos if h.severidad == CRITICA]
    if graves:
        return Confiabilidad(NO_CONFIABLE, graves[0].mensaje, hallazgos)
    alertas = [h for h in hallazgos if h.severidad == ALERTA]
    if alertas:
        return Confiabilidad(
            REVISAR,
            f"Hay {len(alertas)} punto(s) de la evaluación que un humano debe "
            f"revisar antes de usar este formato: {alertas[0].mensaje}",
            hallazgos)
    base = ("La evaluación entregada corresponde a los profesionales y experiencias "
            "del análisis (no se revisó si sus conclusiones son correctas)")
    notas = [h for h in hallazgos if h.severidad == ADVERTENCIA]
    if notas:
        return Confiabilidad(
            CONFIABLE, f"{base}. Quedan {len(notas)} nota(s) menor(es) por confirmar, "
                       f"ninguna pone en duda un resultado.", hallazgos)
    return Confiabilidad(CONFIABLE, f"{base}.", hallazgos)


def a_observaciones(hallazgos: list[Hallazgo]) -> list:
    """Convierte a `pipeline.Observacion` (etapa VALIDACION). Import diferido:
    el módulo se usa y se prueba sin depender del schema del pipeline."""
    from schemas import pipeline

    return [pipeline.Observacion(
        codigo=h.codigo, severidad=h.severidad, mensaje=h.mensaje,
        origen=pipeline.Etapa.VALIDACION, referencia=h.referencia)
        for h in hallazgos]
