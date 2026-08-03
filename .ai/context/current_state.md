# Estado actual del proyecto

> Última actualización: **2026-08-02** · rama de trabajo: `demo`

## Fixes pre-deploy #68, #64, #42 y #65 completos

- **#68:** el recorte TDR usa el rango físico completo declarado y detecta
  folios sospechosamente repetidos; el Excel no lo presenta como un recorte
  individual exacto.
- **#64:** el cómputo efectivo empieza como mínimo en la fecha real de inicio
  de obra, sin cortar por la fecha final de ficha.
- **#42 (backend + Panel):** resolver una revisión responde `202`, persiste
  `en_curso/completada/error`, se consulta por polling y nunca deja la pantalla
  bloqueada sin una acción de reintento.
- **#65:** contrato espejo v1.3.0 con `supuestos` estructurados; el Excel pinta
  violeta solo la procedencia inferida y conserva amarillo para «por verificar».

Gate: **727 passed, 25 skipped**, 57 pruebas de entregables, 36 del
consolidador, 9 espejos históricos en paridad Pydantic/Zod, `compileall` y
`diff --check`. Panel: build productivo Next.js aprobado. No se tocó el
resolver CUI; no aplicó golden. No hubo despliegue.

## ADR-S007 y tren de rescates A–D COMPLETO

`demo` vuelve a ser la línea de producto; `refactor` queda congelada en
`65d41af`. El primer rescate parte del tag local `demo-pre-rescates`
(`5503082`) y corrige el WAF/timeout de Bases Integradas sin traer runtime v2.
La rama suma `d4d3612` (fix) y `6e37605` (pruebas y red offline). Suite:
**709 passed, 25 skipped**. La validación pública con CUI 2279396 descargó un
RAR válido de 1,561,634 bytes sin dejar `.part`. Actualmente no hay servicios
de Pivote corriendo en el servidor del cliente. A avanzó por fast-forward a
`demo` como `586f430`.

El tag local `demo-pre-B-atomicos` marca el retorno previo a B. En
`rescue/B-atomicos`, `c67e290` añade un reintento de unos 200 ms solo para
`PermissionError` de `os.replace` y lo conecta exclusivamente a la escritura
JSON del repositorio; los ZIP quedan fuera. Validación: **9 focales pasaron, 4
skips de PostgreSQL; 713 passed, 25 skipped** en suite completa, `compileall`
y `diff --check`. No hubo push ni despliegue.
B avanzó por fast-forward a `demo` como `3beb94b`.

El tag `demo-pre-C-ingesta` marca `90a3e1e`. C quedó integrado como `bb263c1`:
la API valida JSON, límites de Excel, ZIP y magia PDF antes de crear el job;
un ZIP roto ya no se ignora. Se mantuvieron `201 + job_id`, tareas en segundo
plano y layout. No entraron las defensas diferidas. Validación: **22 API; 717
passed, 25 skipped**, compilación y diff limpios.

El tag `demo-pre-D-cache-seace` marca `3156d26`. D quedó integrado como
`345c601`: una caché compartida por `fileCode` valida magia PDF/ZIP/RAR,
publica atómicamente y reutiliza el documento entre experiencias y jobs. La
descarga sigue secuencial y no trae piezas del runtime v2. Prueba clave: una
descarga de red, tres entregables idénticos. Gate final del tren: **34 focales;
721 passed, 25 skipped**, `compileall` y diff limpios. No se tocó el resolver.
No hubo push ni despliegue; actualmente Pivote no corre en el servidor.

## ReniPress integrado al orquestador (29-jul, `demo`)

El usuario reactivó ReniPress con una meta más amplia que la sonda original:
convertirla progresivamente en producto integrable. Primer corte construido
sobre `demo` vigente:

- `backend/scraping/renipress.py`: cliente inyectable y modelos estables, con
  configuración por entorno, reintentos y distinción entre búsqueda válida sin
  filas y portal no disponible.
- `GET /api/pivote/renipress`: contrato HTTP reusable; `200` para fuente sana
  (con o sin resultados) y `503` para caída de SUSALUD.
- `tools/renipress.py`: CLI de diagnóstico sobre el mismo módulo.
- `EtapaRenipressReal` es ahora la rama 3c del pipeline y corre en paralelo con
  InfoObras y SUNAT después de resolver el CUI. Consulta toda experiencia cuyo
  proyecto declara rubro salud, pública o privada, con caché por término.
- El contrato completo queda en
  `enriquecimiento["n_prof:n_exp"]["renipress"]`; la etapa aparece en el
  progreso del API y participa en checkpoints/reanudación.
- `encontrado` y `sin_resultados` son evidencia informativa.
  `portal_no_disponible` produce `ERROR_PARCIAL`, nunca “no existe”.
- No cambia veredictos ni crea revisión humana: la política de coincidencia
  automática sigue pendiente de un corpus auditado de homónimos, bajas y
  ausencias.
- Validación: **90 pruebas focalizadas** y suite completa
  **704 passed, 25 skipped**.

## Validación de CUI citado con ETL MEF (#69, 29-jul)

El resolver consume ahora `funcion` y nombre oficial de la ficha PostgreSQL
para contrastar un CUI citado en Paso 0. Una contradicción positiva de rubro
degrada a revisión; la ausencia de clasificación no veta. Caso real validado:
Hospital Abancay II + CUI 2105743 → ficha de redes eléctricas, función
`ENERGÍA` → revisión. No se relajó el candado de candidatos solo-MEF porque la
golden v4 aún no existe.

Paso 0 tampoco corta ya el flujo al detectar esa contradicción: descarta el
código como ancla, busca nuevamente por el resto de datos y conserva los
candidatos encontrados. El resultado permanece en revisión hasta confirmación
humana; recién entonces puede viajar al Excel un CUI sustituto.

## Replanificación ETL MEF v2 (29-jul)

Rama hija `plan/etl-mef-v2`. La primera revisión fue documental; luego se
implementó el diseño serving-first descrito abajo. Se descartó usar la
épica #12 como especificación: sus issues eran brainstorm. Se perfiló en
streaming el corte real 2026-07-26 de los tres CSV: **620,985 filas, 640.7 MB,
95 columnas, 579,481 CUIs**, 41,505 filas sin CUI pero ninguna sin CUI y SNIP,
ningún CUI cruzado entre estados y un solo duplicado lógico.

Documentos fuente:

- `docs/backend/eda_datos_abiertos_mef.md`: EDA, cobertura, aliases, tipos,
  anomalías y estimación de capacidad;
- `docs/backend/modulo_etl_mef.md`: plan reescrito desde cero;
- `ADR-009`: aceptado para planificación como capa PG que **convive** con el
  índice RAM de ADR-002.

Decisiones: tarea semanal del Programador de tareas de Windows → contenedor
one-shot; `load_id` común; raw JSONB + canonical tipado + serving versionado;
puntero de carga activa en vez de swap de tablas; carga completa activa +
anterior hasta medir almacenamiento real. La Fase 0 (EDA reproducible, carga PG
desechable y benchmark de capacidad) precede al DDL final y a la cotización.
Las issues de GitHub aún no se reescribieron.

### Decisión e implementación serving-first (continuación)

El objetivo se acotó al consumidor real: el resolver. Decisión final del
desarrollador: **índice RAM para búsqueda difusa + PostgreSQL obligatorio para
la ficha enriquecida por CUI/SNIP**. Raw histórico se difiere. Implementado:
retry/backoff, aliases `COD_SNIP`/`NOM_*`, cargas inmutables, manifest atómico,
retención de dos cargas, schema `mef`, carga por COPY, recarga sin reinicio y
health de frescura.

Validación real aislada (PostgreSQL 16 Docker, no base activa): 620,985 filas /
620,984 identidades en **117.5 s**; gzip 32.5 MB; tabla+índices PG 719.3 MB;
14,665 entidades. Lookup: primer pool 171 ms, siguientes 6–9 ms sin cargar RAM.
Diferencial: 100 fichas + 20 rankings, cero cambios en contrato legacy. Se
encontró una fila activa sin nombre: se conserva por CUI y se registra.
Suite: **685 passed, 25 skipped** + integración PostgreSQL explícita aprobada.

## Reunión con el cliente 29-jul — lo que cambió (fuente: transcripción)

- **El cliente está haciendo A MANO lo de bases+contratos**, certificado por
  certificado, con un prompt propio en su Claude (busca el contrato, lo abre,
  verifica el cargo del especialista, guarda por proyecto). Lo pidió «hace
  semanas». **T-004 pasa a prioridad máxima**; diseño listo en
  `docs/plan-integracion-bases-contrato.md` (v2, ajustado con la transcripción).
- **Confianza erosionada**: dijo que **no revisará más Excels** hasta que los
  resultados sean precisos — él ya trabaja su propio Excel; **lo que consume es
  el ZIP** de documentos. «Lo que no puede fallar es que me busque otro proyecto
  y me dé otro» (= exactamente #46/#51, ya corregidos, pero él aún no lo ha
  visto reflejado). Los documentos van primero; el candado, en segunda entrega.
- **Requisito N°1 de T-004, en sus palabras**: segmentar por tipo de proceso —
  un hospital puede tener hasta 4 juegos de bases (preinversión / expediente /
  supervisión / ejecución) con el MISMO CUI; solo valen las bases INTEGRADAS.
- **Pedido nuevo (resuelto 2-ago)**: marcar con color los datos SUPUESTOS del
  Excel → [#65](https://github.com/rafram96/Pivote/issues/65).
- **RENIPRESS despriorizado por él mismo** («ya olvidémonos», para no atrasar
  bases+contratos). Capturas de pantalla: pedidas y descartadas (aceptó).
  Firmante/representante legal: reconfirmó que NO va (ADR-008 se sostiene).
- **Web HK**: no la ha revisado (su red corporativa bloquea la página; por
  teléfono sí carga). Se le reenvía el link por WhatsApp. Rafael regaló el
  tiempo desplegado (~2 meses). El cobro queda pendiente de su revisión.
- ⚠ **Comercial**: NO se habló de precios ni adelantos — el cliente trata los
  extras como pendientes del flujograma. Manejo en `docs/comercial/`.

## T-004 en construcción (29-jul, rama `feat/seace-abierto`)

- **F1 HECHA** (`70c78e8`): `backend/scraping/seace_abierto.py` — cache CONOSCE
  (una vez, atómica, tolerante a fallos), cliente OCDS ([] = dato / None =
  portal caído), y `seleccionar_proceso` con el requisito N°1 del cliente:
  **jamás cruzar de tipo**; desempate por vigencia solo dentro del tipo; con
  varios candidatos sin fechas → el más reciente + flag `ambiguo`. 18 tests
  offline. Probado EN VIVO con el CUI 2279396 (Pichanaki): 5 procesos y
  clasificación correcta.
- **F2 HECHA, lista para PR** (Codex, 29-jul): selección integrada en
  `EtapaInfoObrasReal`, descarga diferida independiente de `obra_id`, marcas
  idempotentes separadas InfoObras/SEACE, archivos/notas dentro de cada
  experiencia del ZIP y bloque informativo en el Excel. No cambia veredictos
  ni el contrato espejo. Suite completa: **677 passed, 24 skipped**.
- **Hallazgo de validación viva F2 (CUI 2279396)**: el contrato descargó como
  PDF (1.45 MB); las Bases Integradas elegidas están publicadas como **RAR** y
  su host devolvió HTTP 403. El código conserva PDF/ZIP/RAR con su extensión
  real y, ante 403/HTML, deja `*_ERROR.txt` en vez de fingir un PDF válido.
  Reintento posterior al commit `d77d054`: mismo HTTP 403; simular navegador
  (`User-Agent`, `Referer` y sesión previa) terminó en timeout. No se creó un
  RAR parcial. Es una restricción/intermitencia del host de archivos, no una
  selección incorrecta del proceso.
- **Documentación de operación y contingencia**:
  - `docs/uso-manual-seace-abierto.md` — receta operable HOY por certificado
    (preparar caché, elegir tipo, descargar los documentos con los nombres del
    entregable, tabla de decisiones y problemas conocidos);
  - `docs/plan-integracion-bases-contrato.md` **ANEXO** — implementación F2,
    contratos internos y pendientes F3/F5.
- Falta: **F3** (fechas→T-005) y F5 (candado). Deploy/redeploy queda
  expresamente fuera de esta entrega y a cargo manual de Rafael.

## Arquitectura visual v3 (29-jul)

`docs/nuevos_modulos/arquitectura-sistema.html` fue rehecho como vista integral
para Manuel y Rafael. Parte del flujo horizontal de `para RAFAEL-V2.xlsx` y
explicita público-primero, SUNAT transversal y RENIPRESS como evidencia auxiliar
para toda experiencia de salud. Se corrigió el estado del ETL: hoy existe la
base mínima manual de 10 campos; cron, hot/cold PostgreSQL, API y paralelización
siguen en el roadmap. Incluye matriz de estado real y arquitectura actual/futura.

## Lo del 2026-07-28 (resumen — detalle en `handoffs/2026-07-28_claude.md`)

- **9 issues resueltas en la rama** `fix/identidad-lircay`: #58/#59/#60/#61
  (identidad: DEDUP exige emisor, tope al CUI citado, veto de fase ET,
  procedencia del CUI en el Excel — diagnóstico con certificados FÍSICOS del
  Tomo II de Lircay), #52/#53 completadas (parser de oferta conservador +
  candado `OFERTA_INCOMPLETA` + prompt multi-tomo) y #47 implementada
  (verificación folio↔emisor en la skill + `folio_verificado` en el contrato +
  el Excel no embebe sin confirmar). Suite: **637 passed**.
- **⚠ LA GOLDEN SE PERDIÓ** (corpus v3 + caché + baseline, irreversible).
  Sustituto: abstención pura + replay (`replay_enriquecimiento.py`, corrido:
  152 exps, solo cambian los 3 casos del ing.) + plan corpus v4
  (`exportar_verdades_panel.py` en el server). Ver nota en `handoffs/current.md`.
- **ETL re-planificado** "documento primero": 14→5 issues; bug confirmado
  #19 (12,102 entidades perdidas por `NOMBRE_*` vs `NOM_*`). Doc ancla:
  `docs/backend/modulo_etl_mef.md`.
- **Corrida viva de divino_nino EN CURSO** (Tesseract local = Camino A activo
  por primera vez). Al terminar: validar el tren + push/PR + redeploy.
- **DECISIÓN CERRADA (Rafael): la skill corre en Claude CODE — Cowork queda
  DESCARTADO como runtime.** Consecuencias: cambios de skill se despliegan con
  el merge (sin rebuild de plugin, sin "trenes de release"); `plugin/` +
  `build.ps1` quedan deprecados como referencia histórica; el setup de Manuel
  es Claude Code + MCP local (`.mcp.json`), no Cowork/Desktop.

## Lo del 2026-07-27 (documentación, entorno, alcance y un fix de veredicto)

- **FALSO CUMPLE cerrado** (#51, PR #56, `cf9804b` en `demo`). Auditando 3 análisis
  reales (156 experiencias) aparecieron **5 profesionales en verde con el tiempo
  efectivo por debajo del mínimo** — y el dato que los desmentía estaba en otra
  hoja del mismo archivo. La conciliación (`cumple_backend`) **ya existía** y estaba
  doblemente inhabilitada:
  - `_RE_MINIMO` solo leía «años» y las bases dicen «24/36 meses» → **0 de 44**
    mínimos captados en los 3 concursos. Ahora lee años/meses/días y compara en
    DÍAS (convertir a años y redondear volcaba los bordes): **44/44**.
  - `cumple_backend` solo llegaba a la API. Ahora viaja en el espejo (en vivo) y
    `regenerar_excel_final` lo reinyecta desde el enriquecimiento (regeneración).
    En el Excel, si contradice al veredicto la celda se pinta **roja** y el motivo
    va debajo.
  - Se cerró el **error inverso**: cobertura de valorizaciones casi nula recorta los
    días casi a cero y habría dado NO CUMPLE duro; la causa probable es obra mal
    emparejada (error nuestro) → entra a `veredicto_provisional` → POR VERIFICAR.
    De los 5 falsos CUMPLE: 1 traslape real (NO CUMPLE), 4 dato faltante (revisión).
  - 619 tests (5 nuevos con los casos reales BIM y P6 de Lircay).
- **Dos defectos de la skill arreglados** (`32017b7`): la PARTE 2 llegaba desalineada
  (el prompt del mapa nunca pedía `contrato` ni `proyecto`, y el juicio del evaluador
  no tenía dónde aterrizar → ahora se fusiona por la llave `n`), y el literal `null`
  se imprimía en celdas. De paso, `pick(x,"")` dejaba `observacion: null` en
  `formularios` — **invalidaba el espejo entero** cuando faltaba ese campo.

## Lo del 2026-07-27 (documentación, entorno y alcance — sin código de producto)

- **La skill instalada llevaba 13 días de atraso y le faltaba el escudo entero.**
  `~/.claude/skills/analizar-licitacion-osce` era una copia del 14-jul (rastreada
  al commit `1a2b5a2`): **cero** apariciones de `INCOMPLETO`, sin
  `process.exitCode = 1`, sin el bloque ⛔ GATE en `SKILL.md`. Es decir: no podía
  detener una corrida incompleta — exactamente la falla del 26-jul (veredictos
  corridos +1 y corrida sin evaluación, ambas subidas como buenas). El arreglo
  vivía en `demo` desde `0271ea7` y nunca llegó al entorno.
  **Resuelto de raíz**: la ruta instalada es ahora un **junction a `Pivote/skill/`**
  (ver `conventions/coding.md`) — la skill instalada ES la del repo, la deriva ya
  no es posible. 18/18 archivos en paridad, 31 tests verdes a través del enlace.
- **Alcance de T-008 corregido en el material comercial** (commit `27c8cde`):
  `plan-desarrollo-extras.html` y `arquitectura-sistema.html` vendían «Arquitectura
  Dual Hot/Cold Path JSONB», «swap atómico `mef_inversiones_staging`» y «pg_trgm».
  **Nada de eso existe en el código** (`grep` → cero): el ETL produce
  `inversiones.csv.gz` + `os.replace` sobre un archivo. Se reescribió describiendo
  lo real y el Postgres quedó como *evolución prevista, no construida y fuera del
  precio* — ADR-009 seguía EN CONSTRUCCIÓN en ese corte; fue revisado el 29-jul.
- **Cifras reales de la base MEF** (metadata del 26-jul): **620,985 filas →
  579,481 CUIs distintos** y **11,011 entidades**. Los docs decían 452,793 y 11,004.
- **Documento nuevo `docs/nuevos_modulos/caminos-a-b-estado.html`**: los 4 caminos
  del Excel (A/B × pública/privada) en cuadrícula con tablero de estado. Deja ver
  que una experiencia pública pasa por 7-9 verificaciones y una privada por 2-3 —
  por eso clasificar mal a privada es el error caro. Y que las 3 piezas sin
  desplegar (CUI, cargo↔bases, HABIDO) aparecen en los 4 caminos.
- **Cuarto estado en los diagramas**: «construido, falta desplegar» separado de «en
  producción». Antes el material decía «✔ en producción» sobre trabajo que vive
  solo en `demo`.
- **Issues nuevas**: [#49 Economizar Skill](https://github.com/rafram96/Pivote/issues/49)
  (con inventario de las responsabilidades que absorbió el backend) y
  [#50 parámetro de tipo de concurso](https://github.com/rafram96/Pivote/issues/50)
  (= implementación de **ADR-010**, ya decidido — ver la corrección en el hilo).
- **Corrección de un dato que este archivo daba mal**: `demo` **sí está pusheada**
  (`origin/demo` 0/0). El checklist decía «solo local, falta push» desde el 23-jul.

## Dos huecos del flujograma, abiertos con el cliente

Aparecieron al ordenar el Excel por camino (no se ven en su disposición original):

1. **RENIPRESS no se pide para expedientes privados** — solo para obra. Un
   expediente técnico de una clínica privada tiene el mismo problema de existencia.
2. **Los cruces de fechas solo se piden en el camino A** — en obra el Excel pide
   únicamente el cargo, aunque la misma regla aplicaría con el contrato de supervisión.

## Terminado y validado (sin desplegar)

- **Integridad de la evaluación + visibilidad del Excel** (#45/#46/#47, PR #48
  y ADR-013, en `demo`). Suite **565**. Lo que cambia para el evaluador:
  - el bloque InfoObras del Excel **muestra el nombre de la obra** (antes solo
    código y CUI: ninguna identificación era auditable de un vistazo);
  - la advertencia de revisión **ya no se esconde tras un `elif`** — eran 403
    de 999 ítems sin resolver (40%) invisibles, en 31 jobs;
  - **el backend calcula** días/meses/años, `anterior_colegiatura` e
    `incluye_covid` (etapa VALIDACIÓN): dejan de depender de que el LLM los
    mande, que es como salieron vacías las corridas del 26-jul;
  - el consolidador de la skill **falla ruidosamente** si la evaluación no
    cubre 1:1 lo declarado, y ya no imprime `OK` cuando hay críticos;
  - **veto por departamento contradictorio** + **candado de nombre genérico**
    (ADR-013): cierran el caso Tarapoto (Hospital EsSalud de San Martín contra
    una tomografía en Madre de Dios). Costo medido en el corpus: 0.6% a
    revisión, y las 6 experiencias del delta del veto son mal-resueltos.
  - `scripts/reparar_evaluacion.py` rellena jobs viejos sin re-correr la skill.
- **Golden regenerada** (corrida en vivo autorizada, 26-jul): baseline nuevo
  230 correctos / 10 incorrectos / 34 revisión, **cero `correcto→incorrecto`**.
  La caché quedó completa y `--solo-cache` volvió a funcionar offline.
  ⚠ **La golden es ciega a media regla del resolver**: sus casos solo llevan
  `proyecto` y `cui`, sin `ubicacion`/`entidad`/`ruc_emisor`, así que los vetos
  de ubigeo y el candado de nombre no se ejercitan (ADR-013 dio matriz
  diagonal: probó cero regresión, no validó nada). Ensancharla está en curso.

- **Issue #32 — factor de evaluación al final de cada hoja P** (`17b1e04`):
  cierra el punto 2 del feedback del 28-jul. Verificado e2e con PDFs
  sintéticos; **falta la corrida sobre un job real**. Toca skill (prompt
  `agent-bases`, consolidador, `extraer_certificados.js`) y backend
  (`excel_final.py`), pero es compatible en ambos sentidos de despliegue: un
  `P{n}_FACTOR.pdf` que llegue a un backend viejo se ignora, y un backend nuevo
  sin el archivo genera la hoja como antes. Arrastra un fix:
  `regenerar_excel_final` conservaba cero imágenes.
- **Issue #30 — emisor del certificado en SUNAT** (rama
  `rafram96/issue-30-mostrar-representante-legal`): representantes legales +
  información histórica (`getinfHis`, sondeada 25-jul) en el bloque emisor del
  Excel, con la respuesta calculada a "¿estaba HABIDO al emitir y durante la
  obra?" en el título del campo. Cuadro histórico nuevo en R:U (representante
  de obra corrido a W:Z). Una consulta por RUC por job. 276 tests verdes +
  prueba en vivo contra 6 RUCs. **Pendiente: render en el panel.**
- **Refactor del resolver de CUI (T-008)** — rama `sonda/refactor-cui`, 13
  commits (`a732936…f2bde36`): base local MEF + público-primero + vetos de
  identidad + candados de abstención + camino A/B. Golden 277 casos: errores
  silenciosos **16 → 10**, cero regresiones. 268 tests verdes.
- **Camino A (expedientes)**: clasificador por toda la evidencia + modo
  `PIVOTE_FORZAR_EXPEDIENTES=1`; validado con el concurso San Isidro.
- **Skill optimizada**: Paso 4.5 acotado (elimina fuga de ~3M tokens/corrida);
  prompt del extractor conserva el envoltorio "Elaboración del ET:".
- **Análisis San Isidro CP-01-2026 entregado** al usuario: job `b4f385c31811`
  (camino A), Excel 12.5 MB con imágenes, 44 CUIs, 28 verificados en MEF.
- **Documentos del paquete de extras v3** (docs/nuevos_modulos/): 4 HTML
  actualizados con T-008 + `arquitectura-sistema.html` nuevo.
- Cotización interna lista: `docs/comercial/planeacion-v2-para-rafael.md`
  (gitignored — no va al repo).

- **Issue #28 (T-MULTI-002) paso 1 — desempate por estado del MEF**, mergeado
  a `demo` el 2026-07-26 (PR #39, `14f9fe8`): `estado_dataset` ya viajaba en la
  base local desde F3 y **ningún consumidor lo leía** (229k de 494k filas son
  DESACTIVADAS y competían de igual a igual con las vivas). Ahora ordena el
  presupuesto de fetches, desempata el ranking a igual score y separa homónimos
  en el guard de empate — siempre como DESEMPATE, nunca como filtro (15 de 191
  verdades auditadas viven en filas DESACTIVADA: CUIs reformulados que el cert
  cita). Consultas al portal gastadas en desactivadas: 32.2% → 9.3%. Empate de
  Sullana 4 → 2 candidatos. 375 tests verdes. **Golden en vivo NO corrido** (el
  reordenamiento cambia qué CUIs se consultan → la caché no los tiene).

## En progreso

- **Fixtures listos para probar el backend nuevo** (2026-07-26): preparadas
  `Pronis_Sonitor/`, `Soritor2/` y `Consorcio-Lircay/` con `_prep/MAPA.md`
  (inventario, offsets de folio, tachado, descartes). Índice nuevo
  `fixtures/ing manuel/_CONCURSOS.md` = qué carpeta es qué concurso/postor.
  Herramientas reusables en `src/tools/`: `detectar_tachado_pdf.py` (validado
  contra el caso HuachoColpa: 10/10 páginas), `trocear_pdf.py` y
  `render_paginas.py`. **Mejor fixture para probar: `Soritor2/`** (born-digital,
  95 MB, sin troceo). Detalle en `handoffs/2026-07-26_claude.md`.

- **Issue #31 — candado cargo↔bases (ADR-012)**, mergeado a `demo` el
  2026-07-26: `backend/validacion/cargo_nucleo.py`
  exige el núcleo de especialidad COMPLETO (OR entre alternativas, AND dentro)
  y usa las funciones como segunda puerta; marca rojo/amarillo en el Excel sin
  tocar el formato ni el cómputo de días. Replay: 15 rojas + 116 amarillas
  sobre 1421 experiencias, con los 4 casos del Comité detectados. Falta prueba
  viva + deploy (la skill cambió → rebuild del plugin).
- Fase comercial: presentar extras a Manuel
  (T-003+T-008 entregados S/5,400; T-004/005/006 por desarrollar S/4,400).

## Problemas abiertos

- **Bases de Lircay (`Consorcio-Lircay/`) traen tachado pese a llamarse "sin
  tachas"**: 16 páginas, y lo eliminado toca equipamiento estratégico (pick-up
  2021+, software, miras, "Con Estación Total") y las funciones BIM del
  personal → leer `_prep/bases_texto.txt`, **nunca el PDF crudo**.
- **Falta la oferta económica de los 2 postores de Lircay** → sin límite
  inferior ni puntaje de precio. Pedírselas a Manuel.
- Corridas camino A: aún se **descargan y pintan** secciones de obra
  (valorizaciones ~805 archivos) en expedientes — cosmético/pesado, no afecta
  veredictos. Advertencias COBERTURA se emiten para expedientes (no descuentan).
- 2 casos de la auditoría con "verdad" dudosa (2195439 Tocache/Loreto,
  2064566 Cotabambas/Antabamba) — re-revisar con Manuel.
- Divergencia schema.sql vs DDL real de Postgres (ver architecture/database.md).
- SUNAT con error_parcial intermitente en corridas largas (portal, no bug).

## Riesgos

- Hay un **deploy pendiente**: el refactor ya está mergeado a `demo` y **pusheado**
  (verificado 27-jul: `origin/demo` 0/0), pero el server corre el código viejo.
  Los pasos y el ORDEN del deploy viven SOLO en `InfoObras/.ai/tasks/_active.md`
  (fuente única).
- **El repo `Pivote` es PÚBLICO.** Todo lo que se commitea se publica en internet
  de forma permanente (el historial no se borra). `docs/comercial/` está gitignored
  por eso — el 27-jul un dashboard con S/ 10,300 en cuentas por cobrar, precios por
  ticket y la IP del servidor del cliente llegó a estar a un `git add` de publicarse.
- **`ai-cli validate` falla en este nivel con 67 errores preexistentes**: los 13 ADR
  y los 3 índices de `tasks/` no tienen frontmatter YAML, y `counters.json` está en
  `{CAP:0, TSK:0, ADR:0}` con ADR-013 ya existiendo → **`ai-cli new` colisionaría**.
  El nivel InfoObras valida limpio. Reparación pendiente (ver handoff del 27-jul).
- Límite de gasto mensual de Claude alcanzado el 21-jul (los subagentes pueden
  morir a mitad — el trabajo F8 se terminó a mano por eso).

## Siguiente prioridad recomendada

1. Deploy en paquete del refactor — checklist de deploy: ver
   `InfoObras/.ai/tasks/active.md` (fuente única).
2. Filtro de secciones de descarga/Excel en modo camino A.
3. Reunión de cotización con los 5 HTML de docs/nuevos_modulos/.
