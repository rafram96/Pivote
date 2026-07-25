# Backlog

> Entradas nuevas: formato estructurado obligatorio —
> `../conventions/formato_tarea_estructurada.md`. Las entradas viejas de
> abajo se migran solo si se tocan.

## Técnico (listo para ejecutar)

---
id: T-TAREA-ADR010
tipo: tarea
zona: otro (contrato espejo + skill + orquestador/)
agente_origen: desarrollador
estado: aprobado
depende_de: []
---
**Implementar ADR-010: tipo de concurso (A/B) como parámetro declarado por la skill.**
Campo aditivo `concurso.tipo_evaluacion` ("expedientes"|"obras") en las 3 copias
del contrato espejo (espejo.py/espejo.js/espejo.ts) + validador + consolidador;
la skill lo lee del objeto de la convocatoria (agent-bases ya lo extrae) con
vocabulario cerrado; form-field opcional en `/api/pivote/analizar`;
`EtapaInfoObrasReal` enruta por el parámetro con precedencia
espejo > form > `PIVOTE_FORZAR_EXPEDIENTES` > `es_expediente_exp` (fallback +
telemetría de discrepancia). El resolver de CUI NO se toca (ya es independiente
del tipo). Incluir aquí el filtro de secciones de descarga/Excel por camino
(absorbe la tarea "Camino A: no descargar secciones de obra" de abajo).
Verificación: pytest + golden sin cambios + replay San Isidro con el campo.

- [ ] **Deploy del refactor** — tarea CROSS-REPO; checklist canónico en
  `InfoObras/.ai/tasks/active.md` (nivel sistema). Regla: todo junto (ADR-007).
- [ ] **EPIC #12: Sistema ETL del MEF** (Registrado en GitHub Project #1 `InfoObras Development`):
  - [ ] **[Feature #13] Ingesta y Extracción de Datos Abiertos del MEF**
    - [ ] `T-ETL-001` (#14): Ingesta streaming con reintentos y tolerancia a fallos (3 CSVs MEF).
    - [ ] `T-ETL-002` (#15): Soporte offline y parámetro `--desde-dir`.
  - [ ] **[Feature #16] Normalización y Estructuración Dual (Hot / Cold Path)**
    - [ ] `T-ETL-003` (#17): Extracción y normalización de 16 campos calientes (Hot Path).
    - [ ] `T-ETL-004` (#18): Empaquetado de payload crudo completo de 68 campos (Cold Path JSONB).
    - [ ] `T-ETL-005` (#19): Extracción de catálogo de entidades públicas y siglas.
  - [ ] **[Feature #20] Persistencia PostgreSQL y Carga Atómica Zero-Downtime**
    - [ ] `T-ETL-006` (#21): Control de calidad de volumen y Sanity Check (Gate >= 400k filas).
    - [ ] `T-ETL-007` (#22): Swap atómico de tablas PostgreSQL (`mef_inversiones_staging` -> `mef_inversiones`).
  - [ ] **[Feature #23] Búsqueda Paralela y Cron de Refresco**
    - [ ] `T-ETL-008` (#24): Cron semanal y actualización de `metadata.json`.
    - [ ] `T-ETL-009` (#25): Engine de búsqueda paralela N profesionales (SQL + Python Scoring).
- [ ] Camino A: no descargar ni pintar secciones de obra (valorizaciones,
  cronograma) en expedientes; silenciar advertencias COBERTURA para expedientes.
- [ ] Re-revisar con el cliente los 2 casos de verdad auditada dudosa:
  2195439 (Tocache vs Loreto) y 2064566 (Cotabambas vs Antabamba).
- [ ] Unificar `backend/db/schema.sql` con el DDL real de `repositorio_pg.py`
  (o marcar schema.sql como documental).
- [ ] Tool MCP `buscar_cui` servida por el backend (pedido cliente 06-jul) +
  endpoint de descarga por 1 CUI reutilizando el ZIP (hacerlo job).

## Extras cotizados (esperan aprobación del cliente)

- [ ] Lista canónica T-00x con estado: `InfoObras/.ai/context/vision.md`
  (fuente única, nivel sistema) — aquí no se copia.

## Ideas (sin compromiso, evidencia parcial)

- [ ] Modo "local primero" del resolver (medir recall con golden antes).
- [ ] Skill: imágenes a media resolución para el agente-mapa cuando Camino B
  sea inevitable (el Camino A/Tesseract ya funciona en la laptop).

(El progreso fino B/C/D es CROSS-REPO — vive en
`InfoObras/.ai/tasks/backlog.md`, aquí no se copia.)

---

# Sondeo 2026-07-23 (consolidado por fable — ids A*/B* conservan el agente de origen)

## Sondeo 2026-07-23 — agente-a (zona: resolucion/ + scraping/)

---
id: T-SONDEO-A01
tipo: sondeo
zona: scraping/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**Resolver legacy muerto dentro de `backend/scraping/infoobras.py` (≈480 líneas sin callers).**
`buscar_obra_por_certificado` (línea 1684), `verificar_profesional_en_obra` (1401),
`buscar_obras_por_nombre` (1347) y sus helpers (`_jaccard` 1518, `_extraer_palabras_clave` 1545,
`_score_candidata` 1615, `_normalizar_tokens` 1509) no tienen NINGÚN caller fuera del propio
archivo (grep en todo backend/: solo el README los menciona). Es un segundo resolver de CUI
por nombre, anterior a `resolucion/cui.py`, con criterios que CONTRADICEN la filosofía vigente:
`min_score=15.0`, y ante ambigüedad (diff < 5.0) "aún así retornamos el mejor" (línea 1763-1769)
— exactamente el sobre-compromiso que ADR-005 eliminó. Riesgo: que una sesión futura lo
encuentre y lo use creyendo que es el resolver. Además `buscar_obras_por_nombre` duplica
verbatim el param-dict de `ConsultaInfoObras._query` (cui.py:603-614) pero SIN reintentos y
devolviendo `[]` ante excepción (semántica que cui.py corrigió con `PortalNoResponde`).
Alternativa a evaluar: eliminar el bloque (o moverlo a un módulo `_legacy` explícito) vs.
dejarlo con docstring de deprecación; comparar contra el costo de mantener dos verdades.
Decisión de Fable.

---
id: T-SONDEO-A02
tipo: sondeo
zona: scraping/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**`backend/scraping/README.md` describe OTRA carpeta y contradice ADRs vigentes.**
El archivo es una copia del viejo README de `src/referencia/` (snapshots de Alpamayo,
2026-05-27): dice "copias de SOLO LECTURA", "No editar nada aquí", "cuando termine el pivote
esta carpeta puede borrarse", da rutas de `Alpamayo-InfoObras` y presenta ALT12 como
funcionalidad activa ("firmante ≠ representante legal") cuando ADR-008 la descartó.
Nada de eso aplica a `backend/scraping/` (código de producción del pivote). Mismo patrón
del bug documental de la cifra de RAM: doc que no coincide con el código que acompaña.
Alternativa: reescribirlo con el mapa real (infoobras/mef/sunat/errores_red + patrón
funciones-puras/fetch) o borrarlo y dejar que `architecture/backend.md` sea la fuente única.

---
id: T-SONDEO-A03
tipo: sondeo
zona: scraping/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**Tres implementaciones distintas de reintentos/backoff con semánticas de fallo inconsistentes.**
(1) `resolucion/cui.py::ConsultaInfoObras._query` (617-647): 3 intentos, backoff lineal
`1.5*(i+1)`, agotado → lanza `PortalNoResponde`; loguea la excepción CRUDA con `%r` en vez de
`errores_red.corto()` (único sitio de scraping que no usa el clasificador que se creó justo
para eso). (2) `scraping/infoobras.py`: ~5 loops artesanales repetidos (warmup 282, búsqueda
CUI 324, DatosEjecucion 433...), lineal, agotado → `[]`/`None`. (3) `scraping/mef.py::_get`
(296-310): backoff EXPONENCIAL `_BACKOFF * 2**i`, agotado → `None`. Tres formas de decir
"portal caído" (excepción / lista vacía / None) obligan a cada caller a conocer el dialecto
de su fuente; la memoria del proyecto ya registró que "vacío ≠ PortalNoResponde" causó el
caso 6:1. Alternativa a comparar: helper único `con_reintentos()` en `scraping/errores_red.py`
(parametrizable lineal/exponencial, siempre loguea con `corto()`) vs. dejarlo como está
(costo: cada portal nuevo reinventa el loop). NO es urgente — es deuda, no bug.

---
id: T-SONDEO-A04
tipo: sondeo
zona: resolucion/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**`es_entidad_publica` escanea linealmente 11k entidades con rapidfuzz por CADA llamada, sin
caché — y en un punto se llama dos veces con el mismo argumento.**
`resolucion/base_mef.py::es_entidad_publica` (239-256): loop O(n) con `token_set_ratio` sobre
`self._entidades` (11,004). En `resolucion/cui.py::_clasificar_privada` (922-924) se invoca
DOS veces seguidas con la misma `entidad` (una para el bool, otra para el score). También se
invoca por experiencia en `_compuertas` (1261-1262); propuestas con decenas de experiencias
de la misma entidad contratante repiten el escaneo completo cada vez. Alternativa a evaluar:
(a) memo/`lru_cache` por nombre normalizado en `BaseMef` (barato, sin cambiar semántica) y
arreglar la doble llamada; (b) índice invertido por token sobre entidades (como el de
inversiones) — probablemente sobredimensionado. Medir primero cuánto pesa en una corrida real
(la traza del job ya tiene los spans) para no optimizar a ciegas. Ojo: NO tocar el umbral 90
(ADR-004, es DURO).

---
id: T-SONDEO-A05
tipo: sondeo
zona: resolucion/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**Docstrings desfasados en la zona (mismo patrón de la cifra de RAM).**
(1) `resolucion/texto.py` (cabecera, líneas 4-9): dice "por ahora ambos conviven con las
definiciones duplicadas (no se edita cui.py)" y "en una fase posterior cui.py pasará a
IMPORTAR de este módulo" — cui.py YA importa de texto.py (cui.py:31) y ya no hay duplicados;
la nota describe un estado transitorio que terminó. (2) `resolucion/cui.py` (cabecera, 1-14):
describe el método viejo del prototipo (`tools/buscar_cui_por_nombre.py`, "similitud +
departamento + fecha + RUC") sin mencionar base MEF, público-primero, vetos de rubro/ubigeo
ni candados F7 — quien lea solo la cabecera entiende un resolver que ya no existe (la doc
buena está en backend.md). (3) `scraping/sunat.py::consultar_representantes` (697): "Insumo
de ALT12: ¿el firmante está facultado según SUNAT?" — ALT-12 fue descartada como regla
(ADR-008); el dato es informativo para el panel. Corrección de prosa, cero cambio de código;
importa porque `.ai/` promete que el código y la doc no se contradicen.

---
id: T-SONDEO-A06
tipo: sondeo
zona: scraping/
agente_origen: agente-a
estado: pendiente
depende_de: []
---
**Dos normalizadores/comparadores de nombres de empresa paralelos: `scraping/mef.py` vs
`scraping/sunat.py`.**
`mef.py::_norm/_SUFIJOS/_nombres_coinciden` (97-126: quita sufijos societarios S.A.C./E.I.R.L./
CONTRATISTAS..., compara por substring de núcleos o ≥2 tokens) y `sunat.py::
normalizar_nombre_empresa/score_match_empresa` (247-297) resuelven la MISMA pregunta ("¿estos
dos nombres son la misma empresa?") con listas de sufijos y criterios DISTINTOS. Consecuencia
real posible: un emisor puede "coincidir" en el bloque VERIFICACIÓN SEACE/MEF y no coincidir
en el cruce SUNAT del mismo Excel (o viceversa) — inconsistencia visible al evaluador.
Alternativa a comparar: extraer un comparador único (p.ej. `scraping/nombres_empresa.py` o
ampliar `resolucion/texto.py`) con UNA lista de sufijos, vs. dejarlos separados si los
formatos de origen justifican criterios distintos (habría que documentar el porqué en el
código). Requiere mini-golden de pares nombre-declarado/nombre-fuente antes de unificar,
para no mover veredictos `ok/no_verificable` existentes.

## Sondeo agente-b (2026-07-23) — orquestador + persistencia

---
id: T-SONDEO-B01
tipo: sondeo
zona: persistencia/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**Comportamiento real de `RepositorioConRespaldo` si Postgres falla a mitad de escritura: divergencia silenciosa SIN cola de reparación, y borrados fantasma.**
Investigado: `backend/orquestador/repositorio.py:235-305` y `backend/scripts/migrar_a_postgres.py`.
Hallazgos: (1) toda escritura va primero al primario (archivos) y luego `_respaldar()` (repositorio.py:249-254) traga CUALQUIER excepción y solo loguea — no hay reintento, ni cola, ni marca de "PG desincronizado"; la única reparación es correr `migrar_a_postgres.py` A MANO. (2) `migrar_a_postgres.py` solo hace upserts: si un `eliminar(job_id)` ocurrió con PG caído, las filas del job quedan FANTASMA en PG para siempre (el re-sync no borra huérfanos), y `buscar_profesionales()` (repositorio_pg.py:197-221) las seguiría devolviendo en la búsqueda del panel. (3) No hay transaccionalidad entre primario y respaldo (por diseño). Relevancia ADR-009: hoy el "best-effort" es coherente porque PG es solo respaldo; si PG pasa a OBLIGATORIO, este contrato entero (tragar excepciones, leer siempre de archivos, re-sync manual sin borrado de huérfanos) deja de ser válido y hay que redefinirlo — no basta con quitar el try.

---
id: T-SONDEO-B02
tipo: sondeo
zona: persistencia/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**Costo de latencia oculto del write-through con PG caído: cada escritura respaldada bloquea hasta el timeout del pool.**
Investigado: `repositorio.py:249-254` + `repositorio_pg.py:84` (`ConnectionPool(dsn, min_size=1, max_size=4, open=True)`) + `orquestador/motor.py`.
Hallazgo: `_respaldar` es SÍNCRONO en el hilo del pipeline; con PG caído, cada `self._pool.connection()` bloquea hasta el timeout del pool de psycopg_pool (default ~30 s) antes de lanzar la excepción que se traga. El motor hace checkpoint (guardar job) tras CADA etapa (`motor.py:270-274`) más guardados de enriquecimiento por etapa (`motor.py:116,129,177`) → un job de 8 etapas con PG caído puede sumar varios MINUTOS de espera muerta, y `resolver_revision` (un clic del evaluador) también la paga. "Best-effort" hoy significa "no falla", no "no cuesta". Pendiente de confirmar el timeout exacto configurado (no se pasa `timeout=` explícito). Relevancia ADR-009: evidencia REAL para el punto "Postgres obligatorio vs opcional" — el modo opcional actual ya degrada mal en caída parcial.

---
id: T-SONDEO-B03
tipo: sondeo
zona: orquestador/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**Arranque del sistema: asimetría total entre base MEF (degrada con gracia) y Postgres (tumba el backend al arrancar aunque sea "opcional").**
Investigado: `backend/api/app.py:53-57` y `repositorio_pg.py:81-86` vs `orquestador/etapas_reales.py:200-210`.
Hallazgos: (1) con `PIVOTE_DB_URL` definida, `RepositorioPostgres.__init__` se ejecuta EN EL IMPORT de `app.py` (nivel módulo): abre el pool y ejecuta el DDL (`con.execute(_DDL)`) — si PG no responde en ese momento, la excepción sube y el backend NO ARRANCA, pese a que PG es formalmente un respaldo opcional. No hay try/except alrededor en app.py. (2) La base MEF, en cambio, es un singleton perezoso que se construye recién en la etapa RESOLUCION_CUI con try/except → base=None (`etapas_reales.py:206-210`): si falta o falla, el análisis sigue InfoObras-solo. Consecuencia adicional: el primer job tras un arranque paga los ~15-60 s de carga del índice DENTRO de la etapa (sin warm-up al boot). Relevancia ADR-009: alimenta directo el pendiente "qué pasa si Postgres no está disponible al arrancar" — hoy la respuesta empírica es "no arranca", que ya es de facto el comportamiento obligatorio que el ADR discute.

---
id: T-SONDEO-B04
tipo: sondeo
zona: persistencia/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**Confirmado: el DDL real de `repositorio_pg.py` y `backend/db/schema.sql` siguen divergiendo — y son estructuralmente incompatibles, no solo distintos.**
Investigado: `repositorio_pg.py:35-68` (_DDL, corre en cada arranque con PIVOTE_DB_URL) vs `backend/db/schema.sql` (164 líneas, no lo ejecuta nadie en el código).
Diferencias exactas: DDL real = 3 tablas (`jobs` con columnas planas `concurso_id`/`estado` rellenadas desde Python; `documentos(clave,tipo,datos)` JSONB genérico que mezcla espejo/enriquecimiento/concurso/decisiones; `profesionales` con `*_norm` para LIKE). schema.sql = 4 tablas (`concursos`, `jobs`, `espejos`, `enriquecimientos` — NO existen `decisiones` ni `profesionales`), con columnas GENERATED (`estado`, `postor`…), FKs con ON DELETE CASCADE, funciones `fecha_segura`/`numero_seguro` y 2 vistas (`base_datos`, `analisis`) que referencian tablas (`espejos`, `enriquecimientos`) que el DDL real jamás crea → aplicar schema.sql sobre una BD real crearía un esquema paralelo muerto; sus vistas no funcionan contra las tablas reales. Nota: `architecture/backend.md` menciona "la vista SQL" como consumidor del contrato del resolver — esa vista (`base_datos`, schema.sql:86-140) hoy NO existe en ninguna BD que arranque el código. Ya hay un bullet viejo en este backlog ("unificar o marcar documental"); esta entrada aporta el detalle exacto. Relevancia ADR-009: el punto pendiente de revisión del esquema debería decidir el destino de schema.sql en el mismo acto.

---
id: T-SONDEO-B05
tipo: sondeo
zona: persistencia/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**`guardar_espejo` en Postgres no es atómico (documento e índice de profesionales van en transacciones separadas) y el índice `profesionales` es una capacidad que SOLO existe en PG.**
Investigado: `repositorio_pg.py:135-137` y `170-195`.
Hallazgos: (1) `guardar_espejo` hace `_guardar_doc(...)` (una conexión/tx) y luego `_indexar_profesionales(...)` (OTRA conexión/tx con DELETE+INSERT): una caída entre ambas deja el espejo nuevo con índice viejo (o vacío) hasta el próximo re-guardado — hoy inocuo porque el panel puede caer al escaneo de archivos, pero deja de serlo si PG es la fuente. (2) `buscar_profesionales` (la búsqueda global del panel) solo existe en `RepositorioPostgres` — no está en el Protocol `Repositorio` (repositorio.py:41-55) ni tiene equivalente en `RepositorioArchivos`; es la ÚNICA lectura del sistema que va al respaldo en vez del primario, invirtiendo el principio "toda lectura va a archivos". Relevancia ADR-009: es el único consumidor real que ya necesita PG — evidencia útil para el Contexto del ADR (hoy vacío) sobre qué motiva de verdad la migración.

---
id: T-SONDEO-B06
tipo: sondeo
zona: orquestador/
agente_origen: agente-b
estado: pendiente
depende_de: []
---
**Mapa de dependencia del orquestador sobre el índice MEF en memoria: UN solo punto de consumo, bien aislado tras inyección con default None.**
Investigado: `etapas_reales.py` completo (grep de `base_mef`/`base=`).
Hallazgos: el orquestador consume el índice MEF EXCLUSIVAMENTE en `EtapaResolucionCuiReal.correr` (`etapas_reales.py:200-248`): construye `base = base_mef.instancia()` una vez por corrida de etapa y lo pasa como argumento a `resolver_obras(..., base=base)` y `resolver_con_dedup(..., base=base)` (la lógica interna vive en resolucion/ — fuera de mi zona, no la desarrollo). Ninguna otra etapa (InfoObras, SUNAT, reglas, excel, persistencia) ni el motor tocan la base. El patrón "costura inyectable + default None" (memory/recurring_patterns.md) está respetado: si algún día `base` fuera un backend PG (ADR-009), el único cambio en el orquestador sería qué objeto se construye en esas ~8 líneas — el resto del pipeline es agnóstico. Único acoplamiento implícito: el costo de la primera carga (~15-60 s) se paga dentro de la etapa y se atribuye a su `duracion_ms`, sesgando el resumen de cuellos de botella del motor (`motor.py:204-214`) en el primer job tras cada arranque. Fuera de mi zona pero anotado: `verificar_cui` del MEF vivo (scraping/mef.py) se inyecta aparte vía `PIVOTE_VERIFICAR_MEF` y no depende del índice local.

## Reconciliación del sondeo (fable, 2026-07-23)

---
id: T-SONDEO-F01
tipo: sondeo
zona: otro
agente_origen: fable
estado: pendiente
depende_de: []
---
**Reconciliación A↔B: sin contradicciones entre agentes; UNA tensión doc↔código
verificada y resuelta.** `database.md` y el comentario de `api/app.py:50-52`
dicen «si la BD se cae, el análisis sigue»; B03 afirma que con PG caído el
backend NO arranca. Verificado contra el código (app.py:53-57 construye
`RepositorioPostgres` en el import; `repositorio_pg.py:84-86` abre pool
`open=True` + DDL): AMBOS son ciertos en su ámbito — la frase del doc aplica a
caídas DURANTE ejecución (write-through tragado); al ARRANQUE, PG caído tumba
el proceso. Queda como verdad: «best-effort solo en runtime; el boot es
fail-fast de facto». También verificado A01: cero callers del resolver legacy
fuera de `infoobras.py`. Relación entre zonas detectada: A04 y B06 miran el
mismo índice MEF desde lados opuestos (costo interno vs costura del
orquestador) — ambos alimentan ADR-009; A03 (semántica de fallos en scraping)
y B01/B02 (fallos de persistencia) son el mismo tema transversal
«fallo silencioso vs señal explícita» en capas distintas.

## Plan propuesto (fable, 2026-07-23) — TODO esperando aprobación del desarrollador

---
id: T-TAREA-001
tipo: tarea
zona: otro
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-A02, T-SONDEO-A05, T-SONDEO-B04]
---
**Saneo documental de la zona backend** (solo prosa, cero código): reescribir
o eliminar `backend/scraping/README.md` (hoy describe otro repo y da ALT-12
por viva); corregir docstrings desfasados (`texto.py` cabecera, `cui.py`
cabecera, `sunat.py:697`); corregir en `backend.md`/`contracts.md` la mención
a «la vista SQL» como consumidor del contrato del resolver (la vista vive solo
en el schema.sql aspiracional — no existe en ninguna BD real). 3 preguntas:
es ejecución pura → tarea. Riesgo: nulo. Ejecutable de inmediato.

---
id: T-TAREA-002
tipo: tarea
zona: scraping/
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-A01]
---
**Eliminar el resolver legacy muerto de `infoobras.py`** (~480 líneas,
1347-1828: `buscar_obras_por_nombre`, `verificar_profesional_en_obra`,
`buscar_obra_por_certificado` + helpers). Sin callers (verificado). 3
preguntas: el porqué ya vive en ADR-002…005 (el ADR que impide reconstruir un
resolver por nombre en scraping YA existe); borrar código muerto no es
decisión nueva; git conserva la historia → tarea, no refactor ni ADR.
Criterio: pytest verde + golden intacta (sin callers no debe moverse nada).
⚠ Riesgo deploy: toca código que el deploy pausado va a shipear — ejecutar
DESPUÉS del deploy validado, o aceptar re-validación.

---
id: T-TAREA-003
tipo: tarea
zona: resolucion/
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-A04]
---
**Medir y abaratar `es_entidad_publica`**: primero medir su peso real con la
traza de un job existente (no optimizar a ciegas); luego fix mínimo = caché
por nombre normalizado en `BaseMef` + eliminar la doble llamada de
`_clasificar_privada` (cui.py:922-924). NO tocar el umbral 90 (ADR-004). El
índice invertido de entidades (alternativa b del hallazgo) se descarta por
sobredimensionado salvo que la medición diga lo contrario. 3 preguntas:
optimización sin cambio semántico → tarea. Criterio: golden idéntica
(mal-resueltos y transiciones sin cambios) + pytest verde.
⚠ Mismo riesgo deploy que T-TAREA-002.

---
id: T-REFACTOR-001
tipo: refactor
zona: scraping/
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-A03]
---
**Unificar reintentos/backoff y semántica de fallo en scraping**: helper único
`con_reintentos()` en `errores_red.py` (lineal/exponencial parametrizable,
log SIEMPRE con `corto()`), y señal de fallo consistente (`PortalNoResponde`
≠ vacío) en los tres módulos. Es refactor con ADR NUEVO (ADR-010) al
ejecutarse: hubo alternativa real (status quo: cada portal su dialecto) y un
agente nuevo repetiría el error vacío≠caído que ya costó el caso 6:1
(recurring_patterns.md). Criterio: pytest + golden sin cambios + revisar que
ningún caller dependa del dialecto viejo (`[]`/`None`). Post-deploy.

---
id: T-REFACTOR-002
tipo: refactor
zona: scraping/
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-A06]
---
**Comparador único de nombres de empresa** (`mef.py::_nombres_coinciden` vs
`sunat.py::score_match_empresa` → un solo módulo con UNA lista de sufijos), o
decisión documentada de mantenerlos separados si los formatos de origen lo
justifican. Refactor con ADR nuevo; PRE-requisito: mini-golden de pares
nombre-declarado/nombre-fuente para probar que no se mueven veredictos
`ok/no_verificable` existentes. ⚠ Puede cambiar veredictos VISIBLES al
evaluador → estrictamente post-deploy y con evidencia.

---
id: T-REFACTOR-003
tipo: refactor
zona: persistencia/
agente_origen: fable
estado: esperando_aprobacion
depende_de: [T-SONDEO-B01, T-SONDEO-B02, T-SONDEO-B03, T-SONDEO-B04, T-SONDEO-B05, T-SONDEO-B06]
---
**Completar y cerrar ADR-009 (sesión dedicada con el desarrollador) con la
evidencia del sondeo B — NO crea ADR nuevo, actualiza el existente**: Contexto
real (B05: `buscar_profesionales` es el ÚNICO consumidor que ya exige PG e
invierte «toda lectura va a archivos»); redefinición del contrato best-effort
si PG pasa a obligatorio (B01: sin cola de reparación, borrados fantasma en el
re-sync; B02: bloqueo síncrono ~30 s/escritura con PG caído); comportamiento
de arranque (B03: hoy fail-fast de facto — ver T-SONDEO-F01); destino de
`db/schema.sql` en el mismo acto (B04: estructuralmente incompatible con el
DDL real); plan de migración quirúrgico (B06: un solo punto de consumo,
costura `base=` ya inyectable; decidir ahí warm-up del índice al boot).
NADA se implementa antes de cerrar el ADR.
