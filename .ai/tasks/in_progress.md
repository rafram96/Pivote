# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

---
id: T-REFACTOR-001
tipo: refactor
zona: scraping/ (+ entregables/zip_infoobras.py)
agente_origen: fable
estado: aprobado  # Rafael, 2026-08-05: "Concuerdo con el T-REFACTOR-001"
depende_de: [T-SONDEO-A03]
---
**Unificar reintentos/backoff y semántica de fallo en scraping.**

### Cerrada el 2026-08-05 — decisión en `decisions/ADR-014-reintentos-unificados.md`

**Qué había**: **15 bucles de reintento artesanales** en 7 módulos, con 4
fórmulas de backoff, 3 formas de jitter y **6 valores de retorno para el mismo
evento** («el portal no respondió»): excepción, `None`, `[]`, `False`,
`{encontrados: 0}` y un dataclass. Cada llamador tenía que conocer el dialecto de
su fuente, y confundir «vacío» con «caído» ya costó el caso 6:1.

**Qué se hizo**: un solo `con_reintentos()` en `scraping/errores_red.py` —
`Politica(intentos, base, modo, jitter, tope)` + clasificación única con
`corto()` + `Resultado(respondio, valor, error, intentos)`. La distinción
vacío-vs-caído es **mecánica, no de disciplina**: `Resultado.__bool__` lanza
`TypeError`, así que `if res:` —el error del 6:1 en una línea— explota con un
mensaje que la explica. Se migraron **13 bucles en 6 módulos** (`infoobras`,
`mef`, `sunat`, `seace_abierto`, `renipress`, `zip_infoobras`) **sin tocar un
solo contrato externo**: cada función traduce el `Resultado` a lo que ya
devolvía. Los contadores por hilo del ZIP entraron por el gancho
`al_reintentar`.

**Qué NO se migró, a propósito** (detalle y porqué en el ADR §Pendientes
conscientes): `resolucion/cui.py::_Infra._query` —**el archivo quedó intacto**,
no aplica golden y su `warning` con la excepción cruda es traza forense—; el
reintento del `codigoObra` faltante de `fetch_by_cui` (no es red: el dato vino
incompleto); las conflaciones vacío=caído de `obtener_informes_control` y
`descargar_datos_cierre` (cambiar su retorno mueve lo que ve el índice del ZIP:
es tarea de producto); y los retries de disco/CLI/orquestación fuera de
`scraping/`.

**Un cambio declarado**: `mef._get` y `seace_abierto._get` hacían
`kw.pop("timeout")` dentro del bucle y perdían el timeout del llamador a partir
del 2º intento. Ahora rige en todos. Ningún llamador vivo pasa `timeout` ahí.

**Gate**: `pytest backend/tests -q` → **902 passed, 25 skipped** (base 870;
+32 tests nuevos, **cero tests existentes modificados** — ése fue el criterio de
que la semántica no se movió). Sin red y sin dormir. `compileall` y
`git diff --check` limpios. `cui.py`, panel y skill sin tocar. Sin push.

---
id: T-TAREA-002
tipo: tarea
zona: scraping/ (infoobras.py)
agente_origen: fable
estado: aprobado  # Rafael, 2026-08-05
depende_de: [T-SONDEO-A01]
---
**Eliminar el resolver legacy muerto de `backend/scraping/infoobras.py`.**

### Cerrada el 2026-08-05

**Qué era**: **483 líneas** (1347–1829, el final del archivo salvo `sondear`)
con un **SEGUNDO resolver de CUI por nombre**, anterior a `resolucion/cui.py`:
`buscar_obras_por_nombre`, `verificar_profesional_en_obra` +
`VerificacionProfesional`, `buscar_obra_por_certificado` + `ObraCandidata`,
`_score_candidata`, `_extraer_palabras_clave`, `_jaccard`, `_normalizar_tokens`.
Puntuaba con Jaccard, aceptaba desde `min_score=15.0` y ante ambigüedad
**«aún así retornamos el mejor»** — exactamente el sobre-compromiso que ADR-005
eliminó. El riesgo no era que corriera (no corría): era que una sesión futura lo
encontrara y lo usara creyendo que es el resolver.

**Cero callers, verificado antes de borrar** con grep del repo completo
(`backend/`, `skill/`, `tests/`, `tools/`, `scripts/`, `docs/`). La única
importación viva del nombre está en `tools/demos/demo_server.py`, y apunta al
**otro repo** (`src.scraping.infoobras` de `Alpamayo-InfoObras`, cargado por
`sys.path.insert`): no toca este archivo.

**Lo que NO se movió**, porque `resolucion/cui.py` lo importa diferido desde
`scraping.infoobras`: `BASE_MAPA`, `_crear_session`, `coincide_codigo`,
`_extraer_datos_ejecucion`, `_procesar_avances`, `seleccionar_obra`. Verificado
tras el borrado que los 6 —más `fetch_by_cui`, `_buscar_por_cui`, `sondear`,
`elegir_obra_raw`, `periodos_inactividad`,
`parsear_aprobacion_expediente`— siguen resolviéndose desde el módulo: la
superficie pública que los tests monkeypatchean quedó idéntica salvo lo borrado.

**Arrastres**: se fueron con el código sus dos únicas pruebas
(`test_extraer_palabras_clave_obra_hospitalaria`,
`test_normalizar_tokens_y_jaccard` en `tests/test_infoobras_parsing.py`), con
una nota en su lugar apuntando a dónde vive hoy la desambiguación por nombre. Y
`docs/backend/analisis_tamanio_y_modularizacion.md` planeaba un
`verificacion.py` para ese bloque en el PR 5 de la modularización: la ficha del
PR ahora dice 1,358 líneas y por qué el submódulo ya no tiene qué albergar.

**Gates**: suite **866 passed, 25 skipped** — la línea base de esta sesión eran
868 (865 + las 3 de B03) y bajan exactamente las 2 pruebas del código borrado:
cero regresiones · `import scraping.infoobras` y `import resolucion.cui`
limpios · `compileall` y `git diff --check` limpios · `cui.py` sin tocar en esta
tarea (no aplica golden) · panel y skill sin tocar.

---
id: T-TAREA-001
tipo: tarea
zona: otro (prosa de backend/scraping, backend/resolucion, backend/schemas y .ai/)
agente_origen: fable
estado: aprobado  # Rafael, 2026-08-05
depende_de: [T-SONDEO-A02, T-SONDEO-A05, T-SONDEO-B04]
---
**Saneo documental de la zona backend — SOLO PROSA, CERO CÓDIGO.** Un doc que
miente es peor que ninguno: `.ai/` promete que código y documentación no se
contradicen.

### Cerrada el 2026-08-05

**Verificado uno por uno antes de tocar nada:**

1. **`backend/scraping/README.md` — engaño confirmado, reescrito.** Era una
   copia literal del README de `src/referencia/`: decía «copias de SOLO
   LECTURA», «no editar nada aquí», «cuando termine el pivote esta carpeta
   puede borrarse», daba rutas de `Alpamayo-InfoObras`, listaba 4 snapshots que
   no existen en la carpeta y anunciaba **ALT-12 como funcionalidad activa**
   («firmante ≠ representante legal») cuando ADR-008 la descartó con evidencia.
   Ahora describe lo que la carpeta contiene HOY —los 6 módulos reales
   (`infoobras`, `sunat`, `mef`, `seace_abierto`, `renipress`, `errores_red`)—
   el patrón parseo-puro↔fetch, la distinción vacío≠caído, y **qué NO vive
   aquí**: la resolución de CUI por nombre es de `resolucion/cui.py`.
2. **`resolucion/texto.py` (cabecera) — engaño confirmado, corregido.** Decía
   «por ahora ambos conviven con las definiciones duplicadas (no se edita
   cui.py)» y «en una fase posterior cui.py pasará a IMPORTAR de este módulo».
   `cui.py:31` YA importa de aquí y no quedan duplicados: describía un estado
   transitorio terminado, e invitaba a editar la copia equivocada.
3. **`resolucion/cui.py` (cabecera) — engaño confirmado, reescrito.** Describía
   el método del prototipo (`tools/buscar_cui_por_nombre.py`: similitud +
   departamento + fecha + RUC) sin una palabra de base MEF, público-primero,
   vetos ni candados: quien leía solo la cabecera entendía un resolver que ya no
   existe. Ahora resume los 6 pasos vigentes, los vetos, ADR-003/005 y el
   vocabulario cerrado de `estado`, con puntero a `architecture/backend.md` como
   fuente completa. ⚠ **El diff de `cui.py` es EXCLUSIVAMENTE docstring de
   módulo — ni una sola línea de código**: sin la golden, la única protección
   posible es que no haya cambio de comportamiento concebible.
4. **`scraping/sunat.py:697` — YA ESTABA CORREGIDO, se saltó.** El docstring de
   `consultar_representantes` ya dice que el dato es informativo y que ADR-008
   descartó ALT-12. Lo que seguía mintiendo era el **encabezado de sección de la
   línea 639** («insumo de ALT12»), que sí se corrigió.
5. **`.ai/architecture/backend.md` — engaño confirmado, corregido.** Listaba «la
   vista SQL» como cuarto consumidor del contrato del resolver. Esa vista
   (`base_datos`, en `db/schema.sql`) no existe en ninguna BD que el código
   arranque, y el schema es estructuralmente incompatible con el DDL real (B04).
   Son 3 consumidores. (`contracts.md`, que la tarea citaba, no existe.)

**Otros docs engañosos de la misma zona, hallados y corregidos:**

- **`.ai/prompts/reviewer.md:16`** repetía «los 4 consumidores … vista SQL» — el
  mismo error, y en el prompt con el que se revisa el trabajo, o sea el sitio
  donde más caro sale.
- **Tres comentarios que presentaban ALT-12 como viva**: `schemas/pipeline.py`
  (la etapa SUNAT y la lista de códigos de `Observacion`), `schemas/espejo.py`
  (`ruc_emisor` «→ … + ALT12») y el encabezado de sección de
  `tests/test_sunat_parsing.py`.
- **`.ai/architecture/database.md`**: decía que el DDL real «corre al arrancar»
  —desde B03-fix se aplica en el primer uso que conecta— y describía
  `db/schema.sql` como simplemente «distinto». Ahora dice lo que B04 probó: no
  lo ejecuta nadie y es **incompatible**; aplicarlo levantaría un esquema
  paralelo muerto.

**Gates**: cero código tocado (el diff completo son docstrings, comentarios y
`.md`) · suite **868 passed, 25 skipped**, sin movimiento · `compileall` y
`git diff --check` limpios · panel y skill sin tocar.

---
id: T-TAREA-B03-FIX
tipo: tarea
zona: persistencia/ (repositorio_pg.py) + api/ (app.py)
agente_origen: fable
estado: aprobado  # Rafael, 2026-08-05
depende_de: [T-SONDEO-B03, T-SONDEO-F01]
---
**Un Postgres caído no puede tumbar el arranque del backend.** Alcance MÍNIMO:
el rediseño del write-path con PG caído (B01/B02) sigue siendo territorio de la
sesión ADR-009 y NO se toca aquí.

### Cerrada el 2026-08-05

**El defecto**: con `PIVOTE_DB_URL` definida, `RepositorioPostgres.__init__`
corría EN EL IMPORT de `api/app.py` — abría el pool y ejecutaba el DDL sin
try/except. Si Postgres no respondía, el backend NO ARRANCABA, pese a que el
respaldo es formalmente opcional (los archivos son la fuente de verdad). Era el
único defecto capaz de morder EN el deploy desde cero, con el compose levantando
Postgres y backend a la vez.

**El arreglo**, con la base MEF como modelo de estilo (singleton perezoso +
try/except → `base=None` → el análisis sigue):

1. **Construir `RepositorioPostgres` ya no toca la red**: solo guarda el DSN.
   El pool y el DDL se abren en `abrir()`, y `_pool` pasó a ser una propiedad
   que llama a `abrir()` — cualquier consulta la abre sola, así que ni los
   métodos del repositorio ni los tests gateados cambiaron de forma.
2. **El DDL se aplica en el primer uso que de verdad conecta**, no en el import.
   Viaja en una conexión suelta (`psycopg.connect`) que se usa como sonda ANTES
   de construir el pool: un `ConnectionPool` que no logra conectar deja hilos de
   reintento vivos y tarda ~5 s en cerrarse, así que el pool solo se crea cuando
   la BD ya respondió.
3. **`api/app.py` sondea UNA vez al arrancar** con tope
   `PIVOTE_DB_TIMEOUT_BOOT` (default 5 s). Si la BD no responde: **un** warning
   con lo que el operador necesita (qué quedó desactivado, que los análisis
   siguen, cómo reactivarlo) y el repositorio se queda en archivos puros — cero
   ruido por request, porque no se envuelve en `RepositorioConRespaldo`. Si
   responde, todo queda exactamente como antes.
4. `scripts/migrar_a_postgres.py` llama `pg.abrir()` explícito: ahí la BD SÍ es
   obligatoria y debe fallar antes de leer los archivos.

**Consecuencia consciente**: un Postgres que aparece DESPUÉS del arranque no se
engancha solo; hay que reiniciar el backend (y `migrar_a_postgres.py`
re-sincroniza lo escrito mientras tanto). Es la misma degradación explícita de
la base MEF, y se prefiere a reintentar por escritura — que es justamente el
costo de latencia que documenta B02 y que decide ADR-009.

**Comprobación manual** (simular la BD caída y ver el backend arrancar):

```
cd backend
PIVOTE_DB_URL=postgresql://pivote:pivote@127.0.0.1:1/pivote \
PIVOTE_DB_TIMEOUT_BOOT=3 \
../venv/Scripts/uvicorn api.app:app --port 8001
```

Se espera: **un** `WARNING api.app: Postgres no respondió al arrancar
(ConnectionTimeout…) … queda DESACTIVADO …`, el servidor levantando igual y
`GET /api/pivote/salud` respondiendo 200. Subir un análisis y verlo terminar
confirma que opera 100% sobre archivos, sin un solo warning más. Con
`PIVOTE_DB_URL` apuntando a una BD viva no aparece ningún warning y el respaldo
escribe como siempre.

**Gates**: suite **868 passed, 25 skipped** (línea base 865/25; +3 pruebas
offline, cero regresiones) · los tests Postgres siguen gateados por
`PIVOTE_TEST_DB_URL` · cero red externa en pytest (el DSN muerto es 127.0.0.1) ·
`compileall` y `git diff --check` limpios · `cui.py`, panel y skill sin tocar.

---
id: T-TAREA-CRUCES-FECHAS
tipo: tarea
zona: reglas/ (cruces_fechas.py) + orquestador/ (etapas_reales.py) + entregables/ (excel_final.py, hoja nueva)
agente_origen: fable
estado: en_progreso  # aprobada por Rafael el 2026-08-05 ("lanza otro agente
#   opus para que resuelva el T-011"); arrancada el mismo día
depende_de: [T-TAREA-SEACE-F5]
---
**T-005 comercial (ticket T-011, S/1,200; 2–2.5 días): cruces de fechas
contrato/ET ↔ certificado + hoja «Cronología de expedientes» en el Excel.
Ejecutar DESPUÉS de F5 — consume fechas cuya identidad F5 valida. Partidas y
rango interno en el dashboard projects-list (T-011).**

**D1 AM — Fechas estructuradas desde datos abiertos (S/250)**: extraer
`fecha_suscripcion_contrato` (CONOSCE) / `dateSigned` (OCDS) y vigencias al
bloque `seace` del enriquecimiento. SIN OCR — campo del dataset, verificado
con datos reales. El contrato PDF queda solo como sustento en el ZIP.

**D1 PM — Dos reglas nuevas al motor de alertas (S/500)**, mismo esquema ALT
— no crear un mecanismo paralelo:
1. Inicio del profesional ≥ fecha de firma del contrato del proceso (nadie
   supervisa antes de que el contrato exista).
2. Término del profesional ≤ fecha de la resolución de aprobación del ET
   (para experiencias de expediente; la resolución ya llega vía T-003/MEF).
Semántica de abstención OBLIGATORIA: sin fuente (pre-2018, ~14% de
experiencias) → veredicto provisional "Por confirmar"; JAMÁS un NO CUMPLE
por ausencia de datos (misma regla que el clamp del Paso 5).

**D2 — Hoja nueva «Cronología de expedientes» (S/300)**: ficha por proyecto
(contrato del ET → resolución de aprobación → modificaciones) + tabla
comparativa final. Es una hoja ADICIONAL: las 5 hojas congeladas del formato
(decisión cliente 2026-06-10) no se tocan. Colores/rotulado con las
convenciones vigentes (violeta = supuesto, amarillo = por verificar,
_sin_jerga aplicado).

**D2.5 — QA (S/150)**: suite offline + un caso real cotejado contra lectura
manual del PDF; comparación de espejo antes/después (solo campos nuevos).

**Gates**: los 2 cruces disparan en un caso sintético y uno real; cero red en
pytest; resolver intacto; el Excel regenerado de un job viejo sin datos SEACE
no rompe (hoja Cronología vacía con nota, no crash).

### Estado al cierre de la sesión del 2026-08-05 — CÓDIGO COMPLETO

**Hecho** (en `demo`, commits `ae96924` + `c369fe9`, sin push ni despliegue):

- **`backend/reglas/cruces_fechas.py`** (nuevo, PURO — ni red ni disco): las
  dos reglas, con el vocabulario cerrado (`coincide` / `dispara` /
  `por_confirmar`) y sus frases ya redactadas en lenguaje de evaluador.
- **Las tolerancias, con su porqué**: regla A = **15 días**, LA MISMA constante
  del candado F5 (`TOLERANCIA_DIAS_FIRMA`) importada, no copiada — una sola
  vara para la misma comparación, o el Excel diría una cosa en el bloque del
  proceso y otra en la cronología. Regla B = **30 días**, vara propia porque
  mide otra cosa (el cierre administrativo entre la resolución de aprobación y
  la conformidad del servicio).
- **Aritmética día-exacta**, jamás truncada a mes. Tests del borde
  «mismo mes, días incompatibles» (05/01 vs 30/01 = 25 días → dispara) y de los
  bordes exactos de las dos tolerancias (15 sí / 16 no · 30 sí / 31 no).
- **GATE ANTI-CIRCULARIDAD — el corazón del diseño, y donde se refinó la
  especificación**. La instrucción decía «solo dispara si el candado está
  `confirmado`». Tomada al pie de la letra, la regla A **jamás podría
  disparar**: la señal `temporal` del candado usa esas mismas dos fechas, así
  que un desfase mayor a la tolerancia deja el candado en `contradice` y la
  regla quedaría muda para siempre — el caso borde que Rafael pidió probar es
  literalmente inalcanzable bajo esa lectura. El gate implementado es el
  equivalente funcional y ya canónico en la casa (CASO 0 de
  `T-TAREA-RUC-ADJUDICATARIO`, familia ADR-005): **identidad confirmada por las
  señales INDEPENDIENTES de la fecha que se va a cruzar** — ≥2 señales fuertes
  a favor entre entidad/adjudicatario/objeto y cero en contra entre ellas.
  Consecuencias, todas verificadas con tests: candado `confirmado` → la regla
  concluye COINCIDE; `por_confirmar` → siempre se abstiene (nunca hay 2 señales
  ajenas); `contradice` por entidad u objeto → se abstiene; `contradice` SOLO
  por la fecha, con la identidad sostenida aparte → **dispara**, que es
  exactamente el hallazgo que la regla existe para nombrar. Es más conservador
  que la lectura literal en un caso (`confirmado` gracias a temporal + una
  sola señal ajena → abstención), y la abstención siempre está permitida.
  El gate de la regla B es su equivalente: el MEF tiene que confirmar que el
  emisor de la constancia es el proyectista del expediente
  (`contratista.veredicto == "ok"`), no basta con que el MEF haya respondido.
- **Fecha de la aprobación del ET**: el 08-A del MEF publica el NÚMERO de la
  resolución, casi nunca su fecha («N° 262-2023-GRH/GRI»). Precedencia
  implementada: (1) `aprobacion_expediente.fecha` de InfoObras — día completo,
  deducido del nombre del archivo, se marca `inferida` → **violeta** en el
  Excel, y como puede ser posterior a la resolución real solo puede callar una
  incoherencia, nunca inventarla; (2) una fecha DD/MM/AAAA dentro del rótulo de
  la resolución. Un año o un mes sueltos **no** se aceptan: sin día no hay
  fecha, y deducirla es justo lo prohibido.
- **Cableado**: `EtapaReglasReal` calcula los cruces al final (necesita SEACE +
  MEF + InfoObras ya corridos), los persiste en
  `enriquecimiento[…]["cruces_fechas"]` y emite `Observacion` ALERTA con
  códigos `FECHA_CONTRATO` / `FECHA_APROBACION_ET` **solo** cuando el resultado
  es `dispara`. Una abstención se persiste con su razón y NO levanta alerta.
- **Hoja «Cronología de expedientes»** (`excel_final.py`), ADITIVA y al final
  del libro: ficha por proyecto (proceso, entidad convocante, firma, vigencia,
  correspondencia con el certificado, resolución de aprobación con su
  procedencia, modificaciones de plazo) + tabla comparativa de 11 columnas, una
  fila por experiencia, con las dos preguntas en palabras del evaluador.
  Convenciones respetadas: violeta = deducido, amarillo = por verificar, verde/
  rojo en los veredictos, `_sin_jerga` en TODA celda (incluidos los títulos —
  el nombre del proyecto viene del espejo y arrastra marcas del consolidador),
  cero enums crudos. `inyectar_cruces_fechas` los calcula al regenerar cuando
  el job no los trae, con el mismo motor puro.
- **Compatibilidad probada sobre un job real, no sintético**: Lircay
  (`371fa5a1e704`, 67 experiencias, cero datos SEACE) regenerado con el código
  de `HEAD` y con el nuevo → **19 hojas congeladas idénticas celda por celda**
  (valor, formato numérico y color) y una hoja más al final, con la nota
  «Sin procesos verificables».
- **Comprobación manual**: subcomandos `cruces` (replay de un job, con
  `--excel` para regenerar el entregable aparte) y `cruce-caso` (un caso
  escrito a mano, sin red ni job — la única forma de ejercitar la regla B
  cuando ningún job la ejercita) en
  `backend/scripts/probar_candado_seace.py`, más los 7 casos copy-paste de
  **`docs/pruebas/t011-comprobacion-manual.md`**.

**Replay Vitarte (`7e9306a321ac`, offline)**: 31 experiencias · regla A se
pronuncia sobre las 31 → **9 cuadran, 0 no cuadran, 22 se abstienen** (21
porque el CUI no figura en datos abiertos —cobertura desde 2018— y 1 porque
solo hay 1 de 2 señales ajenas a la fecha). **Regla B: 0**, ese job se corrió
sin la verificación MEF de expedientes y no hay ninguno que cotejar. Cero
incoherencias de fechas en ese análisis es un RESULTADO, no un fallo de la
herramienta: los casos 1 y 3 del documento la muestran disparando.

**Extensión HÍBRIDA aprobada por Rafael el mismo día** («Sí, híbrido. Porque
debe haber cronología por cada experiencia que hay por un profesional»): además
de la hoja global —que se conserva como vista de conjunto del Comité— cada hoja
P lleva, bajo la PARTE 5, un bloque **CRUCE DE FECHAS CONTRA EL CONTRATO Y LA
APROBACIÓN DEL EXPEDIENTE** con una entrada por experiencia (proceso de
referencia, las tres/cuatro fechas, los dos veredictos y la explicación a todo
lo ancho). **Cero lógica duplicada**: las dos vistas leen
`excel_final.presentacion_cruces`, que traduce a celdas lo que decide
`reglas/cruces_fechas.py` — un texto o un color cambian en los dos sitios a la
vez, con test que lo fija. Las experiencias sin proceso publicado aparecen con
su abstención rotulada, nunca desaparecen. De paso se corrigió el defecto que
Rafael detectó al revisar la hoja: las columnas de fecha nacían sin formato
largo y mostraban `2018-05-29 00:00:00`; ahora las cuatro de la tabla global y
las cuatro del bloque llevan `dd/mm/yyyy` (año de 4 dígitos: aquí el año ES el
dato).

**Alcance real del cambio en el libro, dicho sin adornos**: `CLAUDE` y
`Base de Datos` quedan **byte-idénticas**; las hojas por profesional **sí
cambian**, y por decisión explícita — el bloque es un apéndice bajo la
conclusión del tiempo efectivo. Verificado con el método del worktree sobre
Lircay (`371fa5a1e704`, 19 hojas, código `70f39bf` vs el nuevo): cero celdas
modificadas en CLAUDE y Base de Datos, **cero contenido preexistente perdido en
todo el libro**, y el recorte del factor baja intacto.

**Gates**: `backend/resolucion/cui.py` intacto byte a byte → **no aplica
golden** · suite **826 passed, 25 skipped** (línea base 789/25; +37 pruebas,
cero regresiones) · cero red en pytest · `compileall` y `git diff --check`
limpios · panel intacto (regla de contención del 5-ago).

**PENDIENTE**: el D2.5 de la especificación pide además **un caso real cotejado
contra la lectura manual del PDF** — hoy ningún job local tiene un expediente
verificado en el MEF que ejercite la regla B de punta a punta. Queda para la
corrida en el servidor, junto con la de F5.

## T-TAREA-SEACE-F5 — candado de identidad CUI↔proceso (en progreso, 2026-08-05)

### Estado al cierre de la sesión del 2026-08-05 — CÓDIGO COMPLETO, FALTA SERVIDOR

**Hecho** (en `demo`, sin push ni despliegue):

- **`backend/validacion/candado_seace.py`** (nuevo, PURO — ni red ni disco):
  confirmación asimétrica con veredicto ternario en
  `enriquecimiento[…]["seace"]["candado"]`. Cinco señales: `entidad`
  (comparador `score_match_empresa` de `scraping/sunat.py` **reutilizado**, no
  duplicado — el de `mef.py` está afinado para nombres de OBRA y no quita
  sufijos legales), `adjudicatario`, `objeto`, `temporal` (fuertes) y `monto`
  (débil). Umbrales: 85 a favor / 60 en contra (zona gris 60–84 = abstención),
  `TOLERANCIA_DIAS_FIRMA = 15` **días completos**, monto ±20%.
- **Señal `adjudicatario`, hallazgo del Paso 0**: el RUC del emisor del
  certificado suele ser el del **adjudicatario** del proceso (constancia de
  terceros). Es una igualdad de RUC, no un parecido de texto — la señal más
  contundente. **Solo suma**: su ausencia NO contradice (un consorciado emite
  con RUC propio).
- **Aritmética temporal día-exacta** (requisito de Rafael): nunca se trunca a
  mes. Test del caso borde `test_temporal_mismo_mes_dias_incompatibles` (firma
  30/01 vs inicio declarado 05/01 → 25 días → NO cuadra pese a compartir enero),
  más los dos bordes exactos de la tolerancia (15 días sí / 16 no). **NO se
  tocó el clamp del Paso 5** — esa mejora es tarea aparte.
- **Cableado**: `etapas_reales.py` persiste `seace.proceso` (identidad
  estructurada) + `seace.candado` y emite Observación ADVERTENCIA en
  `contradice`. `excel_final.py::render_seace` y el índice del ZIP
  (`zip_infoobras.py`, txt/md/json) muestran el rótulo. **La descarga NO se
  bloquea**. Panel intacto (D-P1a es otra tarea).
- **Compatibilidad**: un job sin campo `candado` genera Excel e índice
  exactamente como antes (`rotulo()` devuelve `None`). Con test.
- **Comprobación manual**: `backend/scripts/probar_candado_seace.py`
  (subcomandos `caso` y `replay`, `--vivo` para red, caché en
  `datos_pivote/referencia/seace_procesos/`) + checklist copy-paste en
  **`docs/pruebas/f5-comprobacion-manual.md`**.

**Dos defectos reales destapados y corregidos de paso:**

1. La ventana del proceso salía de `contracts[0]`, y el orden de la fuente es
   arbitrario. CUI 2343407 (Challhuahuacho/PRONIS): `contracts[0]` era un
   registro de DOS DÍAS de 2024 y el contrato real era el segundo (2018–2020) →
   dos experiencias legítimas salían «NO COINCIDE». Ahora la ventana abarca
   TODOS los contratos y la firma es la más temprana; también arregla la «Fecha
   de firma» del Excel (`seace.fecha_suscripcion`/`vigencia` derivan del
   resumen).
2. **Los 3 `*_ERROR.txt` de Bases Integradas del job Vitarte NO eran del host**:
   `extension_documento` leía `format` (clave OCDS) sobre el bloque persistido,
   que la guarda como `formato` → extensión siempre `.pdf` → la validación por
   magia tiraba el ZIP/RAR. Corregido (acepta ambas claves). Verificado en vivo:
   el ZIP baja 428,781 bytes y el RAR 1,515,008.

**Gates**: `backend/resolucion/cui.py` intacto byte a byte → **no aplica
golden** · suite **789 passed, 25 skipped** (línea base 757/25; +32 tests,
cero regresiones) · cero red en pytest · `compileall` y `git diff --check`
limpios.

**Hallazgo Paso 0 (Altiplano, consulta en vivo a OCDS el 2026-08-05)**: el CUI
2300016 publica **14 procesos y los 14 son adquisición de equipamiento
biomédico** de EsSalud CEABE (`goods`). NO existe proceso de supervisión,
ejecución ni expediente bajo ese CUI, con ninguna nomenclatura (la API solo
acepta `projectID`; no hay búsqueda por texto). **El selector NO se equivoca**:
es un `sin_tipo` legítimo, no un miss que corregir. Test que lo fija:
`test_altiplano_sin_proceso_de_supervision`.

**PENDIENTE — corrida integral en el SERVIDOR del cliente** (explícitamente
fuera del alcance de esta sesión; no hay deploy): snapshot/punto de retorno
previo (ADR-S007), corrida con una propuesta real y comparación del espejo
antes/después — **solo pueden cambiar los campos `seace.*`**. Ojo: al
redesplegar, las descargas de Bases Integradas que antes quedaban en `_ERROR`
ahora sí bajarán (fix #2), así que el ZIP crecerá; es lo esperado.

---
id: T-TAREA-SEACE-F5
tipo: tarea
zona: orquestador/ (descargas_seace.py, etapas_reales.py) + scraping/ (seace_abierto.py)
agente_origen: fable
estado: en_progreso  # aprobada por Rafael el 2026-08-05: "apruebo F5, quiero
#   varios tests aparte de automatizados que yo pueda comprobar" (el estado
#   `aprobado` del historial NO se borra: queda citado aquí)
depende_de: []
---
**F5 de T-004: candado de identidad CUI↔proceso + corrida integral en el
servidor (saldo comercial S/800 del ticket T-010; 1–1.5 días). Plan aprobado
por Rafael el 2026-08-04; NO arranca hasta presentar/cerrar la cotización
S/2,800 con Manuel.**

**Problema**: hoy el selector SEACE elige el proceso por CUI + tipo, pero nada
confirma que el proceso elegido corresponda de verdad al certificado que se
evalúa. Un proceso equivocado promovería Bases/Contrato de otro concurso como
evidencia — el peor fallo posible (mismo patrón que el veto de rubro del
resolver, ADR-013).

**Diseño — confirmación asimétrica (promover exige señales; degradar es el
default)**:
1. Señales a cruzar ANTES de promover: (a) entidad convocante del proceso vs
   entidad contratante/emisora del certificado (comparador de nombres de
   empresa existente en scraping/sunat.py — reutilizar, no duplicar);
   (b) objeto del proceso vs tipo de la experiencia (ya existe la segmentación
   estricta expediente/supervisión/ejecución — F5 la endurece con la entidad);
   (c) ventana temporal: la convocatoria/firma del proceso debe ser coherente
   con el periodo del certificado (firma ≤ inicio del profesional, con
   tolerancia); (d) monto referencial si ambos lados lo publican (señal débil,
   solo suma — nunca veta sola).
2. Resultado ternario en `enriquecimiento.seace.candado`:
   `confirmado` (≥2 señales fuertes, cero contradicciones) ·
   `por_confirmar` (señales insuficientes) · `contradice` (alguna señal
   fuerte en contra). Solo `confirmado` presenta los documentos como
   verificados; los otros dos usan el render "Por confirmar" que YA existe en
   excel_final.py (render_seace) — no inventar UI nueva.
3. La descarga NO se bloquea: los PDFs igual van al ZIP (sustento), lo que
   cambia es el rótulo de confianza en Excel/panel/índice.

**Fixtures obligatorios (de la corrida Vitarte, ya en datos_pivote):**
- POSITIVO: Pedro Sánchez Meza (proceso correcto, bases+contrato bajados) →
  `confirmado`.
- NEGATIVO: Altiplano CUI 2300016 ("procesos vistos: otro" en obra 2021+) —
  ANTES de codear, verificar a mano en CONOSCE si su proceso de supervisión
  existe con otra nomenclatura; ese resultado define si el fixture prueba
  `por_confirmar` o un miss del selector a corregir.
- Reintento de las 3 descargas `_ERROR` de Vitarte (Challhuahuacho ×2,
  La Libertad) — deben resolverse o quedar con nota honesta.

**Cierre**: corrida integral en el SERVIDOR del cliente con una propuesta
real, snapshot/punto de retorno previo (regla ADR-S007), y comparación del
espejo antes/después (solo pueden cambiar los campos `seace.*`).

**Gates**: suite completa sin regresiones; cero red en pytest (fixtures
sintéticos para el candado); `backend/resolucion/cui.py` intacto (no aplica
golden); los tests del candado cubren promoción, degradación y contradicción.


- **✅ #63 CERRADA CON VALIDACIÓN VIVA (29-jul 09:19)**: re-corrida
  `8a4b468ac700` (resubir de urgente1; `resubir_job.py` arreglado al layout
  carpeta) → 13:1 = **PLAN DE CONTINGENCIA, inicio 11/11/2024** (la fecha que
  esperaba el ing.), `registros_cui: 2` visible en la ficha, y el checkpoint
  atrapó un **2º caso de fase (SALDO)** en la misma corrida. Cola 23→21
  (lista en `experiencias_por_confirmar.xlsx` del job, enviada a Rafael).
  ⚠ `resubir` NO envía certs → se copiaron del job viejo (idénticos, mismo
  espejo) y se regeneró `final.xlsx` (182 imágenes). Descargas del ZIP en
  curso al cierre de esta nota (monitor de fondo activo).
- **(histórico) 🔧 #63 IMPLEMENTADA (29-jul): checkpoint de fase para CUI multi-registro**
  (merge `0395942` en `demo`, pusheado). Caso LaFora del feedback del ing.:
  cert «PLAN DE CONTINGENCIA» resuelto contra la OBRA PRINCIPAL → fecha/
  valorizaciones/paralizaciones de la obra equivocada (sus O1 y O2). Diseño:
  checkpoint ÚNICO en `resolver()` con vocabulario cerrado de fases
  (fuzzy es ciego: los registros comparten la cola del nombre) + SWAP al
  hermano del CUI + revisión con registros listados + `registros_cui` visible
  en la ficha. Gate: 647 tests + replay 224 exps (único efecto = LaFora;
  delta 14:1 verificado preexistente con línea base). **Abierta hasta
  validación viva**: 13:1 de `e7c0fff6afb1` debe dar 500434 / 11/11/2024.
- **Feedback ing. 29-jul** (`docs/feedback/2026-07-29_bisbal_auditoria_ing.md`):
  audita el ENTREGABLE VIEJO (27-jul) — entregarle el paquete nuevo es la
  acción #1. O1/O2 → causa raíz #63 (ya implementada). Pendientes de decisión:
  P1 (evidencia visual — opción recomendada: embeber el ACTA de suspensión ya
  descargada, ~1 d) y P2 (fila PLAZO REAL verde, ~0.5 d, destrabada por #63).
  P3 ya existía. `final.xlsx` con 182 imágenes enviado a Rafael; swap sobre
  el job pendiente de que cierre el Excel bloqueado.

- **✅ CICLO CERRADO (28-jul noche): #47/#53/#62 CERRADAS con validación en
  vivo** (corrida urgente1, job `e7c0fff6afb1` — el postor de los reclamos de
  Manuel). Merge `440c361` a `demo` (pusheado): rescate montos_postor (Paso
  2.5), oferta por campo en el consolidador, escalada a visión por dato
  crítico. Evidencia clave: folio_verificado **62/62 real** (foliación negra
  única 549-552, 4/4 vs páginas físicas), postor 8/8 montos → 3.4 = SÍ,
  y los candados #59/#61 dispararon EN VIVO (2:1 veto fase ET · 9:3 código
  2198310→trocha demovido — verdad conocida: **2198318**). El espejo del job
  se reemplazó por el re-consolidado (backup `espejo.pre-fix-oferta.json`) y
  `final.xlsx` se regeneró SIN re-scrapear: oferta completa
  16,670,989.88 / 15,003,890.90 / 15,003,890.90.
- **Hallazgos sin issue — CERRADOS por decisión de Rafael (2026-08-05)**:
  (a) `funciones_similares` 62/62 null → SE DEJA COMO ESTÁ ("no cambia nada"):
  la 2ª puerta del candado #31 queda inerte a sabiendas; la evidencia de
  Vitarte sugiere que las constancias describen COMPONENTES de obra, no
  funciones de la persona — no abrir issue ni diagnóstico salvo que un caso
  real lo haga necesario. (c) exención ruc_match: OBSOLETA — la golden ancha
  ya no existe (corpus perdido, ver memoria golden-cui-corpus-perdido); no
  registrar ni resucitar. (b) celdas de abstención → absorbido por el residuo
  verificado de D-P1b en el backlog cross-repo (5-ago).
  Cola visible: #55; #54, #57, #19 y #42 cerradas el 2-ago. El diseño
  expediente/obra sigue en #70.
- **SIGUIENTE ACCIÓN GRANDE: redeploy del server del cliente** — `demo` acumula
  TODO el ciclo (#45-#62) y Manuel sigue viendo el código del 26-jul.

- **✅ #52, #53 y #47 COMPLETADAS (28-jul noche, rama `fix/identidad-lircay`)**:
  - `15d2170` — #52: parser de rescate REESCRITO conservador (el de `87ad1bf`
    capturaba 90.0 del «90% de la cuantía» como límite — probado contra la
    prosa real de Lircay), bloque de oferta SIEMPRE visible con avisos en
    hoja, candado `OFERTA_INCOMPLETA` en integridad. #53: prompt del mapa
    con búsqueda de montos multi-tomo + observación `postor_montos_incompletos`
    (guardrail backend ya estaba).
  - `7b13ead` — #47: verificación folio↔emisor EN LA SKILL (prompt), campo
    aditivo `folio_verificado` en las 3 copias del contrato (zod + Pydantic +
    whitelist del consolidador — sin esto se perdía en silencio), y el Excel
    NO embebe con `false` (banda «DOCUMENTO NO EMBEBIDO»).
  - Suite: **637 passed** · consolidador JS 35/0 · paridad por construcción.
  - ⚠ Hallazgo menor: `tools/validacion/test_contrato.py` tiene rutas stale
    (`fixtures/trujillo` → `fixtures/antiguo/trujillo`) — preexistente.
  - Cierre real de #47/#52/#53: merge + **prueba viva** (la verificación de
    folios y los montos multi-tomo solo se ejercitan con una corrida real de
    la skill).

- **🔧 #58-#61 IMPLEMENTADAS (28-jul PM) en rama `fix/identidad-lircay`**
  (commits `936e7c0` #58 · `5810d38` #59 · `ee17b7c` #61 · `02b5cca`+`c164d30`
  #60; también `87ad1bf` adelantó #52/#53). Suite completa: **627 passed,
  24 skipped** (los skips son los dumps SUNAT gitignored, preexistentes).
  Los 3 casos reales reproducidos como tests unitarios (2:4 no hereda, 9:3
  demovido con las 3 señales, 2:3 veto de fase; regresiones COAR y
  Pichanaki/Fortaleza verdes). ⚠ **GOLDEN IMPOSIBLE — corpus PERDIDO
  irremediablemente (confirmado por el desarrollador 2026-07-28)**:
  `auditoria_cui_v3.xlsx` (las ~277 verdades humanas), la caché y la
  baseline no existen en ninguna máquina. **Gate reemplazado para este
  merge**: los fixes son de ABSTENCIÓN PURA (solo `resuelto→revisión`,
  jamás al revés → "correcto→incorrecto" es estructuralmente imposible) +
  regresiones dirigidas verdes + **replay post-deploy con `resubir_job.py`**
  sobre los jobs reales del server (Lircay ×2, Soritor, Huachocolpa)
  comparando resoluciones antes/después. Ver la nota de la pérdida en
  `handoffs/current.md` y el plan de reconstrucción (corpus v4).
- **🧪 RECONSTRUCCIÓN EJECUTADA (28-jul tarde, commit `050677c`)**:
  (1) `scripts/replay_enriquecimiento.py` — replay offline por snapshot,
  corrido sobre 152 experiencias de los 3 jobs locales: los 3 casos de
  Manuel cambian EXACTO como dicen las issues (2:3→revisión fase #61,
  2:4→no hereda #58, 9:3→demovido #59); el resto de deltas son ruido de
  snapshot documentado (guards de empate sin campos completos del portal).
  (2) Semilla `datos_pivote/auditoria_cui_v4.xlsx` — 5 verdades verificadas
  (certs físicos Tomo II + base MEF). Hallazgo: el cert de 9:3 cita 2198316
  con TYPO de 1 dígito — la verdad es **2198318** (C.S. Yanahuanca, PASCO,
  ACTIVO); 2:4 no tiene registro en Invierte.pe (fondo contravalor
  Perú-Japón). (3) `scripts/exportar_verdades_panel.py` — cosechador para
  el server: cada revisión resuelta en el panel → fila de verdad v4.
  **Siguiente**: correrlo en el server (ahí están los jobs con revisiones
  resueltas) y regenerar caché+baseline cuando el corpus tenga volumen.
- **Auditoría Lircay del ing. (28-jul PM) — diagnóstico CERRADO, 4 issues
  nuevas (#58-#61)**. El job es `371fa5a1e704` (postor A, Consorcio
  Supervisión Hospital Lircay = "bisbal"); su Excel es del server con código
  del 26-jul (pre-#51: por eso el resumen P5 traía efectivos imposibles —
  391>177; en `demo` actual salen 435/177/559/0 coherentes → **falta
  REDEPLOY + regenerar**, no hay bug vigente ahí). Certificados verificados
  FÍSICOS (Tomo II 213-216, imágenes extraídas con pdfimages):
  - **#58** DEDUP hereda obra solo por folio (E4 Lurigancho→Picota; folio
    corrido por la skill = 2º caso de #47, evidencia física en comentario).
  - **#59** CUI citado "exacto" aceptado con nombre+dpto+rubro contradichos
    (P9 Navarro: Yanahuanca/Pasco → veredas Ferreñafe; posible colisión
    CUI↔SNIP en `cui_exacto`).
  - **#60** el Excel rotula el CUI resuelto como "(del certificado)" —
    probado que los certificados NO citan CUI (`cert_marco`,
    excel_final.py:1283).
  - **#61** `ruc_match` eligió la fase equivocada (registro del ET vs obra,
    Santa Anita) — 5º caso de la exención ruc_match de la golden ancha,
    primero con documento físico.
  E1/E2 de Minchola: identificación CORRECTA (no tocar). #2 cerrada
  (absorbida por ADR-010). ⚠ #58/#59/#61 tocan `cui.py` → golden
  obligatoria en cada una; refuerzan mantener `cui.py` FUERA de
  T-REFACTOR-004 hasta que estas cierren.

- **🔴 PRIORIDAD MÁXIMA vigente (2026-07-28): issues #47, #52 y #53**
  (`prioridad-critica` en GitHub).
  - **#52 y #53 — tren backend, arrancable ya**: parser de oferta desde la
    prosa de DETALLE + candado ruidoso de 3 celdas vacías (#52); guardrail
    0/N con ítem de revisión de primer nivel — el 3.4 es ADMISIÓN (#53).
    Ambas `aprobado` en `backlog.md` con alcance re-escopado (contraste
    plan vs código del 28-jul).
  - **#47 — REABIERTA el 2026-07-28**: el candado de `folios.py` (41ea419)
    solo cubre el **0.3% del corpus** (2 de 729 recortes traen capa de
    texto); el caso que originó la issue (`95af90f1578e` p1e1, folio 358 vs
    359) es un escaneo y el módulo se abstiene. Lo implementado queda firme
    (la abstención ES el comportamiento correcto; nada de corregir por
    páginas vecinas). El fix real va **del lado de la skill**, ANTES del
    recorte: `agent-propuesta-profesional` ya lee los folios como imagen y
    puede confirmar que la página muestra al emisor.
- **#45 y #46 CERRADAS el 2026-07-28** — estaban sustancialmente
  implementadas en `demo` (`recalculo.py` + `integridad.py` #45;
  `excel_final.py:367`/`:1375` + ADR-013 validado con la golden ancha #46).
  Remanente desprendido y NO olvidado: la pata skill de #45 (podar
  agent-evaluador, se solapa con #49).
- **⚠ CORRECCIÓN (2026-07-28, desarrollador): la skill es de Claude Code, NO
  de Cowork → los cambios de skill NO requieren rebuild de plugin.** Cae el
  argumento de "agrupar todo en una sola rebuild": #47, #49, #50/ADR-010,
  #54 y la pata prompt de #53 **pueden desplegarse por separado**, cada una
  cuando esté lista. Lo que sí conviene seguir agrupando es la **prueba viva
  end-to-end** (es cara en tokens/tiempo y de paso ejercita
  `funciones_similares` de #31, pendiente desde su merge) — pero es una
  decisión de eficiencia de QA, ya no una restricción de despliegue.

- T-TAREA-ADR011 (Issue #26) CERRADA el 2026-07-25 — ver `completed.md`.
  PR #35 REVISADA Y MERGEADA a `demo` (2026-07-26, merge `506815d`); issues #26 y #30 cerradas.
- **Issue #31 — candado de correspondencia de cargo**: código MERGEADO a `demo`
  (2026-07-26) e issue cerrada. Queda **prueba viva** (correr un concurso
  end-to-end con la skill nueva — es lo único que ejercita
  `funciones_similares` de verdad) y **deploy**: la skill cambió, así que va
  con rebuild del plugin de Cowork. Ver
  `.ai/decisions/ADR-012-candado-cargo-nucleo.md`.
- **Panel: las sub-obras no se ven** → rafram96/panel-infoObras#1. El hueco es
  de dos lados: el backend no expone `sub_obras` en
  `GET /jobs/{id}/profesionales` (`api/app.py:674-681`, ~2 líneas) y el panel no
  lo lee. Hoy una experiencia multi-obra se renderiza SIN información de obra,
  en silencio.
- **Issue #51 — Falso CUMPLE**: CERRADA el 2026-07-27 (PR [#56](https://github.com/rafram96/Pivote/pull/56) mergeado a `demo`, 619 tests passed).
- **Issues #54, #57 y #66**: cerradas en `7593dea`; ver `completed.md`.
- **Issue #70**: diseño pendiente para clasificación por concurso y experiencia;
  bloquea la implementación de #50.
- **Nuevas Tareas Creadas (Defectos 8, 9, 10, 11)**:
  - `T-TAREA-ISSUE52` (Defecto 8): Oferta económica incompleta en celdas de entregable.
  - `T-TAREA-ISSUE53` (Defecto 9): Experiencia del postor no computada cuantitativamente.
  - `T-TAREA-ISSUE70`: clasificación auditable por concurso y experiencia.
  - `T-TAREA-ISSUE55` (Defecto 11): Jerga técnica filtrada en celdas del evaluador.
- Ninguna otra tarea de código activa.
- Fase comercial: preparar/realizar la reunión de cotización con el cliente
  (materiales listos en `docs/nuevos_modulos/` v3 + interno en
  `docs/comercial/planeacion-v2-para-rafael.md`, gitignored).
