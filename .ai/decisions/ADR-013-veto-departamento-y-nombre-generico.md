# ADR-013 · Veto de departamento contradictorio y candado de nombre genérico

- Fecha: 2026-07-26 · Estado: **implementado y validado con la golden ANCHA**
  (26-jul: la golden estrecha era inerte para estos vetos — solo `proyecto`+`cui`;
  se ensanchó con join contra el espejo, 277/277 casos enriquecidos, 0 degradados,
  baseline promovido en `f56e97f`). Issue #46 cerrada 2026-07-28.
- Precisa parcialmente: **ADR-005** (§3, "el departamento NO desempata homónimos")

## Contexto

Job real `36d710f27694`, profesional 1, experiencia 1, folio 119. El sistema
emparejó:

| | Certificado | Obra elegida (CUI 2405647) |
|---|---|---|
| Qué es | Construcción del **Hospital de EsSalud** | **Instalación de los servicios de tomografía** |
| Dónde | Ciudad de Tarapoto, **SAN MARTÍN** | Puerto Maldonado, Tambopata, **MADRE DE DIOS** |
| Cuándo | 26/10/2012 – 15/02/2014 | 18/06/2016 – 15/11/2016 |
| Cuánto | S/1'445,335.70 · 11 525 m² | S/415,342 ejecutado |

Veredicto emitido: `via = NOMBRE`, *"establecimiento verificado por nombre"*.
Un falso CUMPLE silencioso, que es el peor fallo posible del producto.

Dos candados fallaron a la vez, y por razones distintas:

**1 · El veto de ubicación no actuó.** El certificado declara "Ciudad de
Tarapoto, Departamento de San Martín". Tarapoto es *distrito* de la provincia de
San Martín, así que el texto no calza el patrón `provincia de X` y **la provincia
quedó sin declarar del lado del certificado** → el veto de provincia (ADR-005 §3)
es inerte por diseño (nunca veta por ausencia). El departamento sí estaba
declarado en ambos lados y se contradecía, pero ADR-005 lo excluía explícitamente.

**2 · El nombre no podía sostener la resolución.** `proyecto` = "HOSPITAL DE
ESSALUD": tres tokens — uno genérico (`HOSPITAL`, ya en `_STOP`), una preposición
y el nombre de una **entidad** presente en cientos de inversiones (`ESSALUD`). La
compuerta de tokens exige `n_hit ≥ mitad`, y con un único token la mitad es uno:
`ESSALUD` aparecía en el nombre de la obra de Madre de Dios → compuerta superada
con score 105. El score medía **parecido de vocabulario, no identidad**.

## Decisión

### 1 · El departamento contradictorio VETA (con las garantías del de provincia)

Un candidato cuya ficha MEF declara un departamento que **contradice** al
declarado por el certificado se aparta a `vetados` (visible en la cola de
revisión), igual que ya ocurre con la provincia. Garantías idénticas, ninguna
nueva excepción:

- **Contradicción positiva, nunca ausencia**: exige el departamento declarado en
  AMBOS lados y que el valor del MEF no aparezca en NINGÚN otro término de
  ubicación del certificado (`_ubigeo_contra`).
- **`ruc_match` exime de todo veto** (el RUC del emisor como ejecutor/supervisor
  de la obra es evidencia más fuerte que cualquier inferencia geográfica).
- **Sin ficha MEF, la señal es inerte** (no se inventa una contradicción).
- **Solo en el camino por NOMBRE**: un CUI citado en el certificado se resuelve
  en el PASO 0 y sigue siendo autoritativo aunque su ubicación oficial difiera
  (COAR y proyectos multi-región; caso 2:27 Cusco→Pasco, que el golden confirma
  como CORRECTO). El veto vive en `_rankear`, adonde el CUI citado nunca llega.
- **El gemelo apartado sigue protegido**: `guard_empate_geo` ya manda a revisión
  con ambos visibles cuando un candidato vetado por ubicación queda a ≤4 puntos
  del ganador — la red por si el veto apartó al correcto. El veto nuevo reutiliza
  el mismo marcador (`veto = "ubigeo"`), así que hereda esa red sin tocarla.

**Salvaguarda adicional — `depto_declarado`.** El departamento solo cuenta cuando
viene con **intención geográfica**: el campo `ubicacion` del certificado o un
rótulo explícito «departamento/región de X». Un topónimo suelto dentro del
nombre no basta, porque los establecimientos **se llaman** como departamentos
("I.E. San Martín de Porres" en Lima). `ubigeo_cert` devuelve ahora las dos
señales: `depto` (amplia — puntúa y EXIME del veto: cuantos más departamentos
tolerados, menos veta) y `depto_declarado` (estricta — la única que habilita el
veto).

### 2 · Candado de nombre genérico (umbral N = 1)

Si el nombre del proyecto no conserva **ningún** token distintivo tras descartar
genéricos de obra (`_STOP`) y **nombres de entidad del Estado** (`_ENTIDADES`:
ESSALUD, MINSA, PRONIED, GOBIERNO, MUNICIPALIDAD…), el match por nombre no basta:
se exige **corroboración dura** —RUC del emisor en la obra, N° de institución
compartido, entidad contratante ≈ ficha MEF, o coincidencia POSITIVA de
provincia/distrito— y sin ella se va a **revisión con los candidatos visibles**.
Nunca un descarte silencioso.

El departamento **no cuenta como corroboración**: ADR-005 midió que no desempata
homónimos, y admitirlo aquí sería regalar la señal justo donde no discrimina.

`_ENTIDADES` se mantiene FUERA de `_STOP` a propósito: como token de búsqueda y
de puntuación esas palabras sí ayudan a acotar; solo se descuentan al medir
cuánto contenido **propio** tiene el nombre.

## Por qué esto NO contradice ADR-005, sino que lo precisa

ADR-005 §3 cierra con *"El departamento NO desempata homónimos (viven en el
mismo)"*. Esa frase es y sigue siendo **verdadera**, y describe un problema de
**desempate**: entre dos proyectos homónimos del mismo departamento, el
departamento no aporta información. Nada de eso cambia aquí — un homónimo del
mismo departamento se comporta exactamente igual que antes (test de no-regresión).

Lo que ADR-005 nunca decidió, y en la práctica se leyó como si hubiera decidido,
es qué hacer cuando el departamento **se contradice**. Desempatar y contradecir
son operaciones distintas: la primera elige entre candidatos compatibles, la
segunda descarta un candidato incompatible. El propio ADR-005 ya aplica ese
criterio —"contradicción declarada en ambos lados = veto"— a la provincia. Esta
decisión aplica **el mismo criterio, un nivel más arriba**, para los certificados
que declaran el departamento pero no la provincia.

**La salvaguarda de fondo de ADR-005 se conserva y se midió.** El riesgo que
justificaba la exclusión era el registro del MEF bajo la **sede de la entidad
ejecutora** en vez de la obra física. Sobre el corpus (37 espejos, 1519
experiencias, 909 resueltas): las **5** resoluciones cuya ficha MEF está en LIMA
—el patrón de sede— contradicen **también la provincia**, o sea que ADR-005 ya
las vetaba por su propia regla. El veto de departamento **no abre esa clase de
falso negativo**; solo alcanza casos que la provincia no podía ver.

## Alternativas descartadas

- **Eximir del veto a las entidades nacionales / multi-región (ESSALUD, MINSA,
  PRONIS, ARCC)**, que era la salvaguarda intuitiva. **Descartada por medición**:
  el caso Tarapoto ES de ESSALUD y otro de los del delta es del MINEDU (UE 118) —
  la exención habría neutralizado exactamente los dos mal-resueltos que motivan
  el ADR. Y no compra nada a cambio: la clase que pretendía proteger (sede en
  Lima) ya está cubierta por el veto de provincia, como se midió arriba. Lo que
  distingue "sede de la entidad" de "otra obra" no es qué entidad es, sino si la
  ubicación del MEF corresponde a esa sede; el corpus no muestra ningún caso de
  ese tipo que el veto nuevo alcance.
- **Vetar con la señal amplia de departamento (`depto`)**: mismo delta exacto
  sobre el corpus (6 y 6 casos, conjuntos idénticos), pero abre la clase del
  topónimo espurio (1.3% de las experiencias tienen el departamento SOLO en el
  título). Coste cero, riesgo distinto de cero → se restringe.
- **Usar el departamento de InfoObras (`nombrDepartamento`) además del MEF**: lo
  haría disparar sin ficha MEF, pero es la señal que `_puntuar` ya penaliza con
  −10 precisamente por poco fiable, y convertir en veto lo que se calibró como
  penalización suave exige la golden. Queda fuera.
- **Umbral N = 2 tokens distintivos**: sobre el corpus se llevaría el **25.5%**
  de los nombres y el **11.5%** del corpus resuelto a revisión. Por encima del
  techo aceptable — un candado que manda a revisión trabajo bien hecho destruye
  el producto igual que un falso CUMPLE, solo que más despacio. Rechazado por
  medición, no por criterio.
- **Sumar `geo_match` al `_senal_dura` del guard de empate**: los umbrales de ese
  guard (DELTA = 4) están calibrados contra la golden y ADR-005 exige recalibrar
  solo con ella. El ubigeo positivo entra únicamente en la puerta nueva.

## Verificación

**Medición sobre el corpus** (37 espejos de `datos_pivote/*/espejo.json`, 1519
experiencias, 909 resueltas, 901 con ficha MEF):

| | |
|---|---|
| experiencias con departamento declarado | 1433 (94.3%) — explícito en 92.9% |
| resueltas con departamento contradictorio | 36 (4.0% de las que tienen ficha) |
| … de esas, ya vetadas hoy por PROVINCIA | 25 |
| … de esas, por CUI citado (fuera del veto) | 5 |
| **DELTA REAL del veto de departamento** | **6 (0.39% del corpus)** — 4 casos únicos |
| nombres con 0 tokens distintivos | 16 (1.05%) |
| **mandadas a revisión por el candado de nombre** | **3 (0.20% del corpus)** — 2 casos únicos |
| con umbral N=2 (descartado) | 175 (11.5%) |

Los **6** casos del delta del veto y los **3** del candado de nombre se
inspeccionaron uno por uno: **los 6 son mal-resueltos** (Hospital EsSalud
Tarapoto → tomografía en Madre de Dios; Hospital de Alta Complejidad de Ica →
acceso a un hospital de Trujillo; Escuelas de Ingeniería de la UN de Trujillo →
Escuela de Nutrición en Tumbes; Catholic High School de Chimbote → I.E. pública
N°81700 de Virú — la queja literal del cliente del 14-jul). **Cero falsos
negativos medidos.**

**Suite**: `pytest backend/tests` completo verde — 557 pasados (539 antes), 17
saltados. 18 tests nuevos, entre ellos el caso Tarapoto con los datos exactos del
job y los tres de no-regresión que ADR-005 protege (homónimos del mismo
departamento, exención por `ruc_match`, ausencia de departamento en un lado).

**Lo que NO se pudo verificar**: el ciclo golden no corre en esta laptop. La
caché offline `_golden_cui_cache.json` es anterior al resolver actual (le faltan
642 de 1957 claves) y completarla exigiría consultas en vivo a InfoObras. **Este
cambio queda pendiente de validación golden en el servidor antes de mergear.**

## Consecuencias

- Se cierran dos vías de falso CUMPLE silencioso por resolución por nombre.
- Coste en falsos negativos: **≤ 0.6% del corpus** a revisión manual (0.39% +
  0.20%, sin solape salvo el caso Tarapoto que dispara ambos). En el corpus
  medido ese coste fue **cero**: todo lo apartado estaba mal resuelto.
- Los candidatos apartados **siempre quedan visibles** en la cola de revisión con
  su motivo; el mensaje distingue ahora si la contradicción fue de departamento,
  de provincia o de municipalidad.
- `ubigeo_cert` gana la clave `depto_declarado`. Un `sig` construido a mano sin
  ella deja el departamento inerte (nunca veta por falta de información).
- Ampliar `_ENTIDADES` cambia el alcance del candado de nombre: exige volver a
  medir el corpus, no basta la intuición.
