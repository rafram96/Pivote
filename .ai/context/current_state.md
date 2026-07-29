# Estado actual del proyecto

> Última actualización: **2026-07-28** · rama de trabajo: **`fix/identidad-lircay`** (sobre `demo`, sin push)

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
  precio* — que es lo que ADR-009 tiene EN CONSTRUCCIÓN y el épico ETL (#12-#25).
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
