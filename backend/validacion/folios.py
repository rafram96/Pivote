"""
Verificación folio ↔ certificado (issue #47).

El problema real (job `95af90f1578e`, prof 1, experiencia 1): el espejo declara
`folio = 358` para un certificado de SAN CARLOS CONTRATISTAS GENERALES SRL, pero
el folio 358 es un documento de la Municipalidad Distrital de San José — el
certificado de San Carlos está en el **359**. El folio está corrido en −1, y como
el MISMO número alimenta la cita al evaluador y el recorte de la imagen que se
embebe en el Excel, el error se propaga en silencio: el sustento que ve el Comité
no es el documento que dice ser.

Este módulo pone la única contraprueba barata que existe: leer la capa de texto
de la página principal del recorte y comprobar que **el emisor declarado aparece
ahí**. Señales, de más fuerte a más débil:

  1. el **RUC** literal — 11 dígitos exactos, con frontera;
  2. el **nombre** de la entidad como **frase contigua**, tolerante al ruido del
     OCR pero no a palabras sueltas repartidas por el documento.

Por qué frase contigua y no términos sueltos
────────────────────────────────────────────
La primera versión de este módulo buscaba cada palabra del emisor por separado
en toda la página. Eso da por bueno justo lo que se persigue: contra el folio
corrido de referencia —una constancia de la «MUNICIPALIDAD DISTRITAL DE SAN
JOSE» que nombra al «Ing. Juan Carlos Mendoza Rojas»— el emisor «SAN CARLOS
CONTRATISTAS GENERALES SRL» quedaba «confirmado» porque SAN venía de «San José»
y CARLOS del nombre del ingeniero. Medido sobre esa misma página, la frase
completa puntúa 57: la contigüidad separa los casos que las palabras sueltas
confunden.

Dos barreras independientes, y las dos deben ceder para dar por bueno un folio:

  A. la frase del emisor aparece contigua en el texto compactado (exacta o con
     ruido de OCR: umbral 90);
  B. **dentro de esa misma ventana** aparecen todos los términos distintivos.

Medido contra los dos únicos certificados reales con capa de texto (job
`36d710f27694`, dos consorcios hermanos que comparten «CONSORCIO SUPERVISOR
HOSPITAL»): cada certificado confirma su propio emisor con 100, y cruzados
puntúan 87 y 76 — por debajo del umbral de A; y aunque A cediera, B falla porque
la ventana de Tarapoto no contiene «MOYOBAMBA» (33) ni al revés (37).

Asimetría deliberada — «un falso CUMPLE es el peor fallo»:

  · `ok=True`  el emisor aparece → el folio es coherente.
  · `ok=False` el documento SÍ tiene texto legible y el emisor NO aparece →
    folio sospechoso, hay que avisar.
  · `ok=None`  no hay con qué verificar (recorte escaneado sin capa de texto,
    experiencia sin emisor ni RUC, **identidad declarada sin señal distintiva**,
    archivo ausente) → **ausencia de evidencia, no evidencia de error**. Jamás
    se degrada a `False`.

El tercer caso de `None` es tan importante como los otros: «S & S CONSULTORES Y
CONTRATISTAS GENERALES S.A.C.» no deja NINGÚN término propio, solo palabras que
comparte medio sector. Un certificado de «JJ CONTRATISTAS GENERALES S.R.L.» que
en su cuerpo diga «servicios de consultores y contratistas generales» satisface
la contigüidad sin ser la misma empresa. Cuando la identidad se reduce a
genéricos —o a un único término corto— el veredicto correcto es abstenerse, no
un match débil: sin señal distintiva, ni el sí ni el no son de fiar.

Distinguir `None` de `False` es lo único que hace usable al módulo: en la corrida
real `95af90f1578e` los 63 recortes son escaneos puros (la capa de texto trae, a
lo sumo, el sello «358» del número de folio), así que confundirlos convertiría
una corrida entera en falsas alarmas. Por eso «no verificable» se decide por
**letras** extraídas, no por caracteres: el sello de folio son dígitos y no
acredita nada.

El veredicto se emite SOLO sobre la página principal del recorte, aunque el PDF
traiga más. Mirar las páginas vecinas para dar por bueno el folio lavaría
exactamente el error que se persigue (en el caso real el certificado correcto
está en la página siguiente). Si el emisor aparece en una página posterior se
reporta como `pagina_alterna` — es un indicio fuerte de folio corrido, no un
salvavidas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

import fitz
from rapidfuzz import fuzz

# ── Umbrales ────────────────────────────────────────────────────────────────
# Letras (no caracteres) mínimas en la página para considerar que hay capa de
# texto verificable. Un certificado real trae cientos; los recortes escaneados
# traen 0 letras y a lo sumo el sello del folio en dígitos («358»). 40 deja
# fuera sellos y membretes sueltos sin exigir el documento completo.
LETRAS_MINIMAS = 40

# Barrera A — la frase del emisor, contigua sobre el texto compactado.
# Medido contra los certificados reales: el emisor propio puntúa 100 (coincide
# literal), el membrete con una letra mal leída («MOVOBAMBA» por MOYOBAMBA) 97,
# y el consorcio hermano —comparte «CONSORCIO SUPERVISOR HOSPITAL»— 87 y 76.
# 90 cae en el hueco: tolera el ruido del OCR y no confunde entidades vecinas.
UMBRAL_FRASE = 90

# Frase mínima para que la contigüidad signifique algo. Por debajo, coincidir no
# distingue a nadie.
LARGO_MIN_FRASE = 8

# Barrera B — cada término distintivo, dentro de la ventana que casó la frase.
# El fuzzy solo se concede a términos largos: «MOYOBAMBA» contra «MOVOBAMBA»
# puntúa 88.9, y ninguna entidad distinta de la muestra se acerca (33 y 37).
UMBRAL_FUZZY = 88
LARGO_MIN_FUZZY = 6

# Un único término distintivo de este largo o menos no alcanza para sostener un
# veredicto: «CONSORCIO HOSPITAL DEL SUR» se apoya entero en «SUR», que cabe
# dentro de «SURCO» sin que nadie lo note. Con identidad así, abstenerse.
LARGO_MIN_DISTINTIVO = 5

ESTADO_OK = "coincide"
ESTADO_SOSPECHOSO = "sospechoso"
ESTADO_NO_VERIFICABLE = "no_verificable"

SENAL_RUC = "ruc"
SENAL_NOMBRE = "nombre"

# Formas societarias y su desarrollo: no identifican a nadie y el documento las
# escribe como quiere («S.R.L.», «S R L», o directamente las omite). Fuera de la
# frase que se busca, para que su ausencia no rompa la contigüidad.
_FORMAS = {
    "SA", "SAC", "SAA", "SRL", "SCRL", "EIRL", "LTDA", "SRLTDA", "SCRLTDA",
    "SOCIEDAD", "ANONIMA", "CERRADA", "ABIERTA", "LIMITADA", "RESPONSABILIDAD",
    "INDIVIDUAL", "COMANDITA", "CIVIL",
}

# Honoríficos: el extractor los arrastra al nombre del emisor cuando quien firma
# es una persona («Ing. Hugo Pichilingue Mugruza»), pero el documento puede
# firmar «Hugo Pichilingue Mugruza, Ingeniero Civil». Exigirlos daba alarmas
# sobre el documento correcto.
_HONORIFICOS = {
    "ING", "INGA", "INGENIERO", "ARQ", "ARQTO", "LIC", "LICENCIADO", "DR",
    "DRA", "SR", "SRA", "SRTA", "MG", "MGTR", "MSC", "ECON", "ABOG", "CPC",
    "BACH", "TEC",
}

# Lo que se poda de la frase antes de buscarla: no está garantizado en el
# membrete y su ausencia no debe romper la contigüidad.
_RELLENO = _FORMAS | _HONORIFICOS

# Nexos y artículos: no identifican, pero SÍ se dejan dentro de la frase (son
# parte del membrete y aportan largo a la contigüidad).
_VACIOS = {"DE", "DEL", "LA", "EL", "LOS", "LAS", "Y", "E", "EN", "AL", "A", "PARA", "POR", "CON"}

# Palabras que casi toda entidad del sector comparte: encontrarlas NO prueba
# nada. Sin esta lista, «Consorcio Supervisor Hospital de Moyobamba» daría por
# bueno un certificado del «Consorcio Supervisor Hospital Tarapoto» (comparten 3
# de 4 términos) — el falso CUMPLE exacto que el módulo debe evitar.
_GENERICOS = {
    "MUNICIPALIDAD", "MUNICIPAL", "DISTRITAL", "PROVINCIAL", "GOBIERNO",
    "REGIONAL", "REGION", "MINISTERIO", "DIRECCION", "GERENCIA", "SUBGERENCIA",
    "UNIDAD", "EJECUTORA", "PROGRAMA", "PROYECTO", "PROYECTOS", "ESPECIAL",
    "EMPRESA", "CONSORCIO", "CONTRATISTA", "CONTRATISTAS", "GENERAL",
    "GENERALES", "INGENIERO", "INGENIEROS", "INGENIERIA", "CONSULTOR",
    "CONSULTORES", "CONSULTORA", "CONSULTORIA", "ASOCIADOS", "SERVICIO",
    "SERVICIOS", "SUPERVISOR", "SUPERVISORA", "SUPERVISION", "CONSTRUCTORA",
    "CONSTRUCCION", "CONSTRUCCIONES", "CORPORACION", "GRUPO", "OBRA", "OBRAS",
    "HOSPITAL", "CENTRO", "SALUD", "PUBLICO", "PUBLICA", "NACIONAL",
    "INSTITUCION", "ENTIDAD", "COMITE", "FONDO",
}

_PARENTESIS = re.compile(r"\([^)]*\)")
_SIN_DIGITO = re.compile(r"\D")

# Separadores tolerados ENTRE los dígitos del RUC: los que mete la maquetación
# («20 505 655 215», «20.505.655-215», o un salto de línea). Deliberadamente NO
# incluye «/» ni letras, para que el RUC no pueda armarse cruzando campos
# distintos del documento.
_SEP_RUC = r"[ \t.\-]{0,2}\n?[ \t.\-]{0,2}"


@dataclass(frozen=True)
class Verificacion:
    """Veredicto sobre UNA experiencia. `ok=None` no es alarma: es abstención."""
    ok: bool | None
    estado: str
    motivo: str
    senal: str | None = None          # qué disparó el hallazgo: RUC o nombre
    letras: int = 0                   # letras leídas en la página principal
    encontrados: tuple[str, ...] = ()  # términos del emisor hallados
    faltantes: tuple[str, ...] = ()    # términos del emisor ausentes
    pagina_alterna: int | None = None  # el emisor aparece en esta página (1-based)
    n_prof: int | None = None
    n_exp: int | None = None
    folio: int | None = None
    ruta: str | None = None

    @property
    def sospechoso(self) -> bool:
        """Azúcar para el integrador: solo `False` amerita aviso al evaluador."""
        return self.ok is False


# ── Normalización ───────────────────────────────────────────────────────────

def normalizar(texto) -> str:
    """Mayúsculas, sin tildes, sin puntuación (mismo criterio que cargo_nucleo)."""
    t = unicodedata.normalize("NFKD", str(texto if texto is not None else ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def compactar(texto) -> str:
    """Normaliza y borra TODO espacio.

    El OCR de estas propuestas parte y pega palabras a discreción («c o n», «d e»,
    membretes cortados por salto de línea). Comparar sin espacios neutraliza las
    dos averías de una vez, y es la única forma de que el membrete espaciado
    —«S A N  C A R L O S»— siga siendo el mismo nombre.
    """
    return normalizar(texto).replace(" ", "")


def _tokens_emisor(entidad) -> list[str]:
    """Palabras del nombre declarado, sin la glosa entre paréntesis.

    Lo que va entre paréntesis es apunte editorial del extractor («PROYECTO
    ESPECIAL ALTO MAYO (Gobierno Regional San Martín)»), no membrete: exigirlo
    daría falsas alarmas.
    """
    limpio = _PARENTESIS.sub(" ", str(entidad if entidad is not None else ""))
    return [t for t in normalizar(limpio).split(" ") if t]


def frase_emisor(entidad) -> str:
    """La frase contigua que debe aparecer en el documento (barrera A).

    Se poda solo el relleno que el membrete puede omitir —forma societaria y
    honoríficos—; los nexos y hasta las palabras genéricas se quedan, porque son
    parte del nombre impreso y su largo es justamente lo que da poder de
    discriminación a la contigüidad.
    """
    return "".join(t for t in _tokens_emisor(entidad) if t not in _RELLENO)


def terminos_emisor(entidad) -> tuple[str, ...]:
    """Términos que IDENTIFICAN a la entidad emisora (barrera B).

    Se descartan nexos, formas societarias, honoríficos y las palabras genéricas
    del sector. Si no queda ninguno, se devuelve vacío y el módulo se abstiene:
    ya no se cae a los genéricos, porque emitir un veredicto POSITIVO con
    palabras que comparte medio sector es convertir la ausencia de dato
    identificatorio en evidencia a favor.
    """
    vistos = dict.fromkeys(_tokens_emisor(entidad))
    return tuple(t for t in vistos
                 if len(t) > 1 and t not in _VACIOS and t not in _RELLENO
                 and t not in _GENERICOS)


def identidad_verificable(entidad) -> bool:
    """¿El nombre declarado da para sostener un veredicto sobre el folio?

    Hacen falta las dos barreras: una frase con largo suficiente Y al menos una
    señal distintiva de peso. Un único término corto no basta —cabe dentro de
    otra palabra sin que se note— y ninguno, menos.
    """
    if len(frase_emisor(entidad)) < LARGO_MIN_FRASE:
        return False
    distintivos = terminos_emisor(entidad)
    if not distintivos:
        return False
    return len(distintivos) > 1 or len(distintivos[0]) > LARGO_MIN_DISTINTIVO


def ruc_normalizado(ruc) -> str | None:
    """RUC en 11 dígitos, o None si el dato no sirve como señal dura."""
    d = _SIN_DIGITO.sub("", str(ruc if ruc is not None else ""))
    return d if len(d) == 11 else None


# ── Búsqueda de las señales ─────────────────────────────────────────────────

def contiene_ruc(texto, ruc) -> bool:
    """¿El RUC aparece literal, como número propio?

    Se toleran los separadores de maquetación entre dígitos («20 505 655 215»,
    «R.U.C.\\n20505655215») pero no letras ni «/», y se exige frontera: ni antes
    ni después puede haber otro dígito. Sin esa doble restricción el RUC se
    arma cruzando campos —«Expediente 205-056/55-215 del año 2016» contiene los
    once dígitos en orden— y la señal dura del módulo deja de serlo.
    """
    d = ruc_normalizado(ruc)
    if not d:
        return False
    patron = r"(?<!\d)" + _SEP_RUC.join(d) + r"(?!\d)"
    return re.search(patron, str(texto or "")) is not None


def localizar_frase(frase: str, texto_compacto: str) -> tuple[int, int] | None:
    """Ventana del texto compactado donde la frase aparece CONTIGUA, o None.

    Primero se busca literal; si el OCR estropeó alguna letra, se acepta la mejor
    ventana que alcance `UMBRAL_FRASE`. Lo que nunca se acepta es reunir la
    frase a partir de palabras dispersas por el documento: esa era la puerta por
    la que un certificado ajeno pasaba por propio.
    """
    if len(frase) < LARGO_MIN_FRASE or not texto_compacto:
        return None
    pos = texto_compacto.find(frase)
    if pos >= 0:
        return pos, pos + len(frase)
    alineacion = fuzz.partial_ratio_alignment(
        frase, texto_compacto, score_cutoff=UMBRAL_FRASE)
    if alineacion is None:
        return None
    return alineacion.dest_start, alineacion.dest_end


def termino_presente(termino: str, ventana: str) -> bool:
    """¿El término distintivo está DENTRO de la ventana que casó la frase?

    La comparación es compactada también para los términos cortos: el membrete
    real llega como «CORPORACION K.G.» o «S A N  C A R L O S», y buscarlos con
    frontera de palabra sobre el texto crudo daba alarmas sobre el documento
    correcto. Acotar la búsqueda a la ventana es lo que hace segura esa laxitud:
    fuera de ella, «UNION» seguiría apareciendo dentro de «reunión».
    """
    if termino in ventana:
        return True
    return (len(termino) >= LARGO_MIN_FUZZY
            and fuzz.partial_ratio(termino, ventana) >= UMBRAL_FUZZY)


def buscar_emisor(texto, entidad=None, ruc=None) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """(señal, términos encontrados, términos faltantes) del emisor en el texto.

    Con el RUC basta. Si no está, el nombre acredita solo cuando pasa las DOS
    barreras: frase contigua (A) y todos los términos distintivos dentro de esa
    ventana (B). Si la frase no aparece, se devuelven todos los distintivos como
    faltantes; si aparece pero la ventana no los contiene todos, se devuelve el
    detalle para que el aviso pueda citar qué es lo que no calza.
    """
    if contiene_ruc(texto, ruc):
        return SENAL_RUC, (), ()
    distintivos = terminos_emisor(entidad)
    if not distintivos:
        return None, (), ()
    ventana = localizar_frase(frase_emisor(entidad), compactar(texto))
    if ventana is None:
        return None, (), distintivos
    ini, fin = ventana
    recorte = compactar(texto)[ini:fin]
    hallados = tuple(t for t in distintivos if termino_presente(t, recorte))
    faltan = tuple(t for t in distintivos if t not in hallados)
    return (None if faltan else SENAL_NOMBRE), hallados, faltan


# ── Veredicto sobre texto ya extraído (núcleo puro) ─────────────────────────

def verificar_texto(texto, entidad_emisora=None, ruc_emisor=None) -> Verificacion:
    """Veredicto sobre el texto de UNA página. Es el núcleo puro del módulo."""
    tiene_ruc = ruc_normalizado(ruc_emisor) is not None
    nombre_sirve = identidad_verificable(entidad_emisora)
    if not tiene_ruc and not nombre_sirve:
        if terminos_emisor(entidad_emisora) or frase_emisor(entidad_emisora):
            return Verificacion(
                None, ESTADO_NO_VERIFICABLE,
                f"«{entidad_emisora}» no aporta un nombre distintivo (solo palabras "
                "que comparte medio sector) ni RUC: encontrarlo no probaría que el "
                "documento sea suyo, y no encontrarlo no probaría lo contrario.")
        return Verificacion(
            None, ESTADO_NO_VERIFICABLE,
            "La experiencia no declara entidad emisora ni RUC: no hay contra qué "
            "contrastar el documento.")

    letras = sum(1 for c in str(texto or "") if c.isalpha())
    if letras < LETRAS_MINIMAS:
        return Verificacion(
            None, ESTADO_NO_VERIFICABLE,
            "El documento es una imagen escaneada sin texto legible: no se puede "
            "comprobar el folio.", letras=letras)

    senal, hallados, faltan = buscar_emisor(texto, entidad_emisora, ruc_emisor)
    if senal == SENAL_RUC:
        return Verificacion(
            True, ESTADO_OK,
            f"El documento menciona el RUC {ruc_normalizado(ruc_emisor)} del emisor declarado.",
            senal=SENAL_RUC, letras=letras)
    if senal == SENAL_NOMBRE:
        return Verificacion(
            True, ESTADO_OK,
            f"El documento menciona a «{entidad_emisora}».",
            senal=SENAL_NOMBRE, letras=letras, encontrados=hallados)
    if not nombre_sirve:
        # Tiene RUC (por eso llegó hasta aquí) pero el documento no lo imprime, y
        # el nombre no da para juzgar. Un certificado válido puede perfectamente
        # no llevar el RUC: callarse aquí es obligatorio.
        return Verificacion(
            None, ESTADO_NO_VERIFICABLE,
            f"El documento no menciona el RUC {ruc_normalizado(ruc_emisor)} y "
            f"«{entidad_emisora}» no aporta un nombre distintivo con el que "
            "contrastarlo: no se puede concluir nada sobre el folio.", letras=letras)
    if hallados:
        detalle = (f"aparece un nombre parecido, pero no calza en "
                   f"{', '.join(f'«{t}»' for t in faltan)}")
    else:
        detalle = "el nombre no aparece en el documento"
    return Verificacion(
        False, ESTADO_SOSPECHOSO,
        f"El documento es legible pero no corresponde a «{entidad_emisora}» "
        f"({detalle}). El folio podría estar corrido.",
        letras=letras, encontrados=hallados, faltantes=faltan)


def verificar_paginas(paginas, entidad_emisora=None, ruc_emisor=None) -> Verificacion:
    """Juzga la página PRINCIPAL; las demás solo enriquecen el aviso.

    Si el emisor no está en la principal pero sí en una posterior, el veredicto
    sigue siendo sospechoso — es la firma típica del folio corrido — y se anota
    en qué página aparece.
    """
    paginas = list(paginas or [])
    if not paginas:
        return Verificacion(
            None, ESTADO_NO_VERIFICABLE,
            "El recorte del certificado no tiene páginas: no se puede comprobar el folio.")

    v = verificar_texto(paginas[0], entidad_emisora, ruc_emisor)
    if v.ok is not False:
        return v
    for i, texto in enumerate(paginas[1:], start=2):
        if verificar_texto(texto, entidad_emisora, ruc_emisor).ok:
            return replace(
                v, pagina_alterna=i,
                motivo=f"{v.motivo} El emisor sí aparece en la página {i} del "
                       f"recorte: el folio parece corrido.")
    return v


# ── Lectura del PDF (única frontera de E/S) ─────────────────────────────────

def extraer_paginas(ruta) -> list[str] | None:
    """Texto de cada página del recorte; None si el archivo falta o no se abre."""
    p = Path(ruta)
    if not p.is_file() or p.stat().st_size == 0:
        return None
    try:
        with fitz.open(p) as doc:
            return [pg.get_text() for pg in doc]
    except Exception:
        # PDF corrupto o ilegible: es ausencia de evidencia, no una alarma.
        return None


def ruta_certificado(carpeta_certs, n_prof: int, n_exp: int) -> Path:
    """`<carpeta>/P{n_prof}_E{n_exp}.pdf` — el recorte de esa experiencia."""
    return Path(carpeta_certs) / f"P{n_prof}_E{n_exp}.pdf"


def verificar_certificado(ruta, experiencia: dict, n_prof: int | None = None) -> Verificacion:
    """Verifica el recorte de una experiencia del espejo contra su emisor declarado."""
    exp = experiencia or {}
    datos = dict(n_prof=n_prof, n_exp=exp.get("n"), folio=exp.get("folio"), ruta=str(ruta))
    paginas = extraer_paginas(ruta)
    if paginas is None:
        return Verificacion(
            None, ESTADO_NO_VERIFICABLE,
            "No se encontró el recorte del certificado: no se puede comprobar el folio.",
            **datos)
    v = verificar_paginas(paginas, exp.get("entidad_emisora"), exp.get("ruc_emisor"))
    return replace(v, **datos)


def revisar_certificados(carpeta_certs, espejo: dict) -> list[Verificacion]:
    """Recorre el espejo completo y verifica el recorte de cada experiencia.

    Solo lee: no toca el espejo ni escribe nada. El integrador decide qué hacer
    con los `ok is False` (los `None` no se muestran como alerta).
    """
    salida: list[Verificacion] = []
    for prof in (espejo or {}).get("profesionales") or []:
        n_prof = prof.get("n_prof")
        for exp in prof.get("experiencias") or []:
            ruta = ruta_certificado(carpeta_certs, n_prof, exp.get("n"))
            salida.append(verificar_certificado(ruta, exp, n_prof))
    return salida
