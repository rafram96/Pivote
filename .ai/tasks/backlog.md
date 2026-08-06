# Backlog

> Entradas nuevas: formato estructurado obligatorio —
> `../conventions/formato_tarea_estructurada.md`. Las entradas viejas de
> abajo se migran solo si se tocan.

## Técnico (listo para ejecutar)

---
id: T-TAREA-RUC-ADJUDICATARIO
tipo: tarea
zona: orquestador/ (etapas_reales.py, etapa SUNAT) + validacion/ (candado_seace.py)
agente_origen: fable
estado: pendiente
depende_de: [T-TAREA-SEACE-F5]
---
**Resolución del RUC exacto del emisor vía adjudicatario SEACE (~0.5 día).
Idea de Rafael, 2026-08-05, registrada con su OK. Cotización: definir —
candidato a bolsa o a presentarse junto con el paquete F5.
Registrada en GitHub como
[#83](https://github.com/rafram96/Pivote/issues/83) (2026-08-06).**

**Problema**: cuando el certificado no trae RUC del emisor, la etapa SUNAT
busca por nombre — y los consorcios de nombre genérico ("CONSORCIO
SUPERVISOR…") producen el caso `ambiguo: N candidatos` (visible en panel
desde el 3-ago, pero sin resolver). ALT04/HABIDO/histórico quedan sin
verificar o a merced de un match de texto.

**La llave que F5 destapó**: cuando el candado confirma el proceso, la
metadata OCDS trae el **RUC exacto del adjudicatario** (`supplier`) — la
supervisora que ganó el proceso es el emisor de la constancia de terceros.
Verificado en Vitarte: INDECONSULT RUC 20263373058 figura como supplier.

**Diseño — árbol de casos (boceto de Rafael 2026-08-05, refinado; VINCULANTE)**:

CASO 0 (gate previo, anti-circularidad inquebrantable): solo aplica si
`seace.candado == "confirmado"` POR las señales independientes
(entidad + objeto + temporal), SIN contar la señal `adjudicatario`. Lo que
se verifica no puede elegir su propia identidad (lección solape-selector,
familia ADR-005). Sin proceso, pre-2018, `por_confirmar` o `contradice` →
TODO sigue como hoy (búsqueda por nombre + ambiguo visible). Jamás degradar
lo que funciona. Cobertura honesta: en Vitarte, 10 de 29 experiencias.

CASO 1 — el certificado SÍ trae RUC del emisor → COMPROBAR:
  1a. RUC declarado == RUC adjudicatario → sello "RUC verificado contra el
      proceso" (máxima confianza; SUNAT ya corría con ese RUC, ahora con
      respaldo oficial).
  1b. RUC distinto PERO nombre del emisor ≈ un integrante del consorcio
      adjudicatario (parties del OCDS) → NO es discordancia: rotular
      "emisor = integrante del consorcio adjudicatario". Los consorcios
      emiten por el líder o con RUC propio del consorcio. Nunca fusionar
      silenciosamente.
  1c. RUC distinto Y nombre tampoco cuadra → Observación severidad ALERTA:
      "el RUC declarado no es el del adjudicatario del proceso". NO se
      enriquece NI se reemplaza el declarado (se consulta el declarado en
      SUNAT igual; la alerta viaja a Excel/espejo). El sistema no corrige
      al certificado: lo confronta.

CASO 2 — sin RUC declarado, nombre del emisor vs adjudicatario con
score_match_empresa (MISMOS umbrales del candado — una sola vara):
  ≥85 → ENRIQUECER: SUNAT consulta el RUC del adjudicatario, procedencia
      rotulada "RUC obtenido del proceso SEACE confirmado". BONUS: si la
      búsqueda por nombre había dado AMBIGUO con N candidatos y uno tiene
      ese RUC → se resuelve la ambigüedad por intersección (el caso del
      consorcio homónimo que motivó esta tarea).
  60–84 → ZONA GRIS: abstención total — ni enriquecer ni alertar. Flujo
      actual + nota informativa "adjudicatario del proceso: X (RUC Y) — no
      se pudo confirmar que sea el emisor". Decisión humana.

CASO 3 — sin RUC declarado y nombre <60 → ALERTA, NO ENRIQUECER:
  "el emisor del certificado no coincide con el adjudicatario del proceso
  confirmado". Dato erróneo o tercero ajeno emitiendo — enriquecer
  contaminaría SUNAT en cascada.

Regla de contención vigente (backlog sistema, 5-ago): todas las señales
nuevas entran por los mecanismos EXISTENTES (Observacion → Excel/espejo),
sin vistas nuevas en el panel hasta la sesión de diseño de alertas.

**Tests**: promoción con candado confirmado-sin-RUC; NO promoción cuando la
confirmación dependía de la señal adjudicatario (anti-circularidad);
consorcio vs integrante rotulados; bandera roja RUC declarado ≠ adjudicatario;
cobertura pre-2018 intacta (sin cambios de comportamiento); cero red en
pytest. Gate: suite completa, `resolucion/cui.py` intacto.

*(T-TAREA-CRUCES-FECHAS pasó a `in_progress.md` el 2026-08-05 — Rafael la
aprobó; el detalle vinculante viaja con la entrada.)*

---
id: T-TAREA-CRONOLOGIA-VERTICAL
tipo: tarea
zona: entregables/ (excel_final.py — bloque de cruces en hojas P)
agente_origen: fable
estado: pendiente
depende_de: []
---
**Reformatear el bloque de cruces/cronología DENTRO de las hojas por
profesional — feedback de Rafael 2026-08-06: «lo considero complicado de leer,
tal vez un formato vertical».**

Alcance: SOLO el apéndice de cruces bajo la PARTE 5 de cada hoja P (el híbrido
de T-011). La hoja global «Cronología de expedientes» NO recibió la
observación y no se toca. Restricciones vigentes: el formato congelado
(CLAUDE + Base de Datos + hojas P) no cambia de orden ni contenido — solo la
FORMA del apéndice; palabras de evaluador; convención de colores intacta
(verde calza / rojo incoherencia / amarillo por verificar / violeta supuesto).
Formato pendiente de diseñar con Rafael antes de implementar (propuso
vertical: una fila por pregunta en vez de tabla ancha).

---
id: T-TAREA-OCR-REMOTO
tipo: tarea
zona: api/ + deploy/ (Dockerfile) + skill/ (scripts/)
agente_origen: desarrollador
estado: pendiente
depende_de: []
---
**OCR como servicio del backend: la skill manda el PDF por LAN y el server
devuelve los `pNNNN.txt` (idea de Rafael, 2026-07-28 — COTIZABLE, no arranca
sin conversación comercial).**

Hoy el Camino A exige Tesseract instalado en el Windows del cliente (con el
PATH bien puesto — fricción medida incluso en la laptop de Rafael el 28-jul).
La idea: mover el OCR al server on-prem para que la máquina del ing. solo
necesite Claude Code + MCP.

**Diseño acordado (matices que NO perder):**
1. **NUNCA "imágenes por MCP" en sentido literal**: los argumentos de una tool
   call pasan por el modelo (el modelo es la tubería — mismo motivo del límite
   de `subir_analisis`). El transporte es el patrón `subir_carpeta.js`: la tool
   recibe una RUTA y un cliente postea **multipart desde disco**.
2. **Se manda el PDF tal cual, no páginas renderizadas**: las páginas escaneadas
   YA son JPEGs embebidos; el server los extrae con `pdfimages -j` en segundos.
   700 PNGs renderizados pesarían más que el PDF original.
3. **Job ASÍNCRONO con progreso, jamás request síncrono** — la lección de #42
   (ECONNRESET): 700 páginas de OCR dentro de un request muere. Reusar el
   patrón job de `descargar-cui`: `POST /api/pivote/ocr` (multipart) →
   `{ocr_id}` → poll → `GET /ocr/{id}/resultado` (zip de `pNNNN.txt`).
4. **Server side**: `apt-get install tesseract-ocr tesseract-ocr-spa` en el
   Dockerfile (más fácil que instalar Tesseract en Windows) + N workers en
   paralelo + disco temporal con limpieza.
5. **Tope de subida nuevo** (`PIVOTE_MAX_MB_PDF`, ~600) — ojo que
   `_leer_limitado` acumula EN RAM; ver nota en `deploy/docker-compose.yml`.
6. **Fallback en TRES niveles, el local queda vivo**: OCR remoto (server) →
   Tesseract local (Camino A actual) → visión (Camino B). Server caído o skill
   fuera de la LAN del ing. no puede romper la corrida.
6b. **Fallback HÍBRIDO POR PÁGINA vía confianza de Tesseract (idea de Rafael,
   28-jul — PROBADO empíricamente ese día):**
   - Tesseract SÍ reporta confianza: salida TSV con `conf` **por palabra**
     (0-100; -1 en filas estructurales). `tesseract img out -l spa txt tsv`
     produce texto Y confianzas **en UNA sola pasada** (cero costo extra —
     verificado con el binario v5.5 local sobre la pág. 48 real de divino:
     113 palabras, conf media ponderada 91.2).
   - Agregación por página: **media ponderada por longitud de palabra** (la
     media simple la sesgan los fragmentos de 1-2 chars que el OCR alucina en
     sellos y firmas). Guardar además `n_palabras`: una página con conf alta
     pero 3 palabras es una página vacía/separadora (caso p82 de las bases de
     divino), no una página confiable.
   - Salida: junto a los `pNNNN.txt`, un **`confianzas.json`**
     `{pagina: {conf, n_palabras}}` — viaja en el mismo zip del server.
   - La skill marca las páginas bajo umbral y **solo ESAS** las lee Claude por
     visión (`Read` rasteriza PDFs — confirmado 28-jul): híbrido ~95%
     Tesseract gratis + ~5% visión donde de verdad hace falta. El umbral es
     CALIBRABLE con datos reales (los `_ocr_*` de divino ya existen para medir
     la distribución antes de fijarlo; arrancar explorando ~60-70).
   - ⚠ Límite honesto del mecanismo: la confianza atrapa páginas ILEGIBLES,
     no errores puntuales seguros de sí mismos (un `6`→`8` en un folio puede
     venir con conf alta). Para dígitos críticos (folios, montos, CUIs) la
     defensa siguen siendo los candados aguas abajo, no el umbral.
   - Este matiz **no depende del server**: aplica igual al Camino A local de
     hoy (`ocr_propuesta.py` puede emitir `confianzas.json` ya mismo — es el
     sub-pedazo de esta tarea que se puede adelantar barato y solo).
6c. **Escalada a visión POR DATO CRÍTICO (idea de Rafael, 28-jul — complementa
   6b, y es más precisa):** el umbral por página atrapa páginas ilegibles
   completas, pero el caso real medido es otro — la página se lee bien y UN
   dato crítico no (urgente1: la fecha final del cert de Tingo María salió
   ilegible del OCR → celdas L86-N87 vacías + total abstención; y el dígito
   final del CUI de Navarro dio 2198310 y 2198316 en dos corridas). Regla:
   **antes de escribir `POR VERIFICAR` en un dato crítico (fechas, folio,
   monto, CUI), el agente DEBE leer ESA página como imagen** (visión) — solo
   esa. Costo: 1 imagen por dato dudoso (~decenas de tokens) vs un `POR
   VERIFICAR` que cuesta revisión humana. Implementación barata YA HECHA en
   el prompt de agent-propuesta-profesional (28-jul, rama
   fix/mapa-postor-montos); la versión sistemática (lista de datos dudosos →
   pasada de visión dirigida) va con esta tarea.
7. **Constraint respetado**: Tesseract en el server es 100% on-prem (la regla
   prohíbe APIs cloud, no software local) y los PDFs van al server del propio
   cliente, que ya recibe el ZIP de certificados.

**Beneficio real**: setup CERO para Manuel (el OCR viaja con el deploy) +
paraleliza sin freír su máquina + LAN (350 MB = un par de minutos). La
velocidad es secundaria: la laptop de Rafael hizo 410 págs "en una pasada".

**Estimación**: ~1-1.5 días (endpoint+job+Dockerfile+cliente+fallback+docs).

**Gates antes de priorizar**: (a) preguntar qué máquina tiene Manuel — si es
decente, el argumento queda solo en el setup; (b) va DESPUÉS de la cola
crítica (#62/#53, redeploy, validación urgente1); (c) entra a la conversación
comercial V2 como módulo con nombre propio (canal cotización, no garantía).

---
id: T-TAREA-ISSUE51
tipo: tarea
zona: orquestador/ (etapas_reales.py) + entregables/ (generar_excel.py, excel_final.py)
agente_origen: desarrollador
estado: completado (2026-07-27, commit 2677aad en fix/veredicto-dias-efectivos)
depende_de: []
---
**Implementar Fix para Issue #51 (Falso CUMPLE por falta de conciliación determinista de días efectivos):**
- **Solución Implementada**:
  1. `_RE_MINIMO` ampliado para capturar años, meses y días (44/44 requisitos capturados en Soritor, Lircay-hosp, Lircay-superv). Comparación realizada en días exactos para evitar desbordes de redondeo.
  2. Inyección persistente de `cumple_backend` en `regenerar_excel_final` y renderizado con celda roja en caso de contradicción en el Excel.
  3. Cobertura baja de valorizaciones conectada a la regla legal de abstención (ADR-005) $\rightarrow$ emite `POR VERIFICAR` indicando la causa real en lugar de un falso `NO CUMPLE`.
- **Verificación**: 619 tests pasados (5 tests nuevos), cero regresiones. BIM (P16) $\rightarrow$ `NO CUMPLE`; P6 $\rightarrow$ `POR VERIFICAR`.

---

id: T-TAREA-ISSUE52
tipo: tarea
zona: backend/ (scripts/generar_excel.py:283) + entregables/ + skill/
agente_origen: desarrollador
estado: aprobado
depende_de: []
---
**Defecto 8 — Oferta Económica Incompleta en Celdas Finales (Issue #52):**
- **Alcance Re-escopado**:
  1. **Parser determinístico en Backend**: Implementar fallback en backend para extraer los 3 montos (`cuantía`, `límite_inferior`, `propuesta`) desde el texto en prosa de `DETALLE` cuando la skill los ubique allí.
  2. **Candado de Ingesta Ruidoso**: Protestar ruidosamente si las 3 celdas resultan vacías tras el parsing, impidiendo la generación silenciosa.
  3. **Inyección Garantizada**: Asegurar la escritura directa de las 3 celdas en `backend/scripts/generar_excel.py:283`.

---

id: T-TAREA-ISSUE53
tipo: tarea
zona: backend/ (validacion/) + skill/ (prompts/agent-propuesta-mapa.md)
agente_origen: desarrollador
estado: aprobado
depende_de: []
---
**Defecto 9 — Experiencia del Postor No Evaluada Cuantitativamente (Issue #53):**
- **Alcance Re-escopado (Dos Trenes)**:
  1. **Tren Backend**: Guardrail 0/N en backend que emite alerta de primer nivel (ítem de revisión visible en panel/Excel) si los montos del postor vienen vacíos/0 en 0/N contratos (al tratarse del Req. 3.4 de Admisión).
  2. **Tren Skill**: Reforzar la extracción de `monto` en `agent-propuesta-mapa` para propuestas multi-tomo (se empaqueta en la rebuild única de la skill).

---

id: T-TAREA-ISSUE70
tipo: tarea
zona: skill/ + backend/ + panel (contrato coordinado)
agente_origen: codex
estado: pendiente
depende_de: []
---
**Diseño de clasificación auditable por concurso y experiencia (Issue #70):**
- Separar `tipo_concurso`, `tipo_experiencia` y modo de clasificación.
- Resolver vocabulario, precedencias, contradicciones y procedencia antes de
  tocar #50; migración aditiva coordinada en Pydantic, Zod y TypeScript.
- Requiere fixtures/golden propios porque sí cambia qué evidencia busca y cómo
  calcula el backend para cada experiencia.

---

id: T-TAREA-ISSUE55
tipo: tarea
zona: entregables/ (backend/scripts/generar_excel.py:137)
agente_origen: desarrollador
estado: aprobado
depende_de: []
---
**Defecto 11 — Jerga Técnica Filtrada en Celdas del Evaluador:**
- **Ubicación exacta**: Extender la función existente `_sin_jerga` en `generar_excel.py:137`.
- **Detalles**: Ampliar el vocabulario de `_sin_jerga` (que hoy solo limpia 1 término en PARTE 2) y aplicarlo también a las observaciones de la PARTE 4 para erradicar las 20 celdas con `funciones_similares=null` y `⟦crudo:…⟧`.

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

---
id: T-TAREA-ADR011
tipo: tarea
zona: skill + orquestador/ + entregables/
agente_origen: desarrollador
estado: completado (2026-07-25, ver completed.md — P2 sigue pospuesto)
depende_de: []
---
**Implementar ADR-011: Tratamiento de certificados multi-obra por sub-obras, resolución por resolver() completo y principio anti-alucinación.**
- P0: Skill extrae sub-obras limpias sin CUI (`obras: [{proyecto, cui: null}]`); Backend enruta cada sub-obra por `resolver()` completo de `cui.py`; Excel renderiza cada sub-obra como bloque independiente (Exp X.1, Exp X.2) con su recuadro MEF/InfoObras a la derecha. Cómputo de tiempo se mantiene en la Experiencia Madre (solape 100% legítimo).
- P1: Candado multi-rubro (alerta `POR CONFIRMAR (Requiere Anexo)` si hay mixtura de rubros sin sub-fechas).
- P2: Escenario B pospuesto hasta que aparezca certificado real que lo exija.
Verificación: pytest + test de Zod schema + comprobación con certificado HV Contratistas. (Registrado en GitHub Issue #26).

---
id: T-TAREA-MEF001
tipo: tarea
zona: api/ + resolucion/ + scripts/
agente_origen: desarrollador
estado: aprobado
depende_de: []
---
**Implementar Endpoint API (GET /api/pivote/mef/buscar) y CLI de búsqueda directa en la base local del MEF.**
- Exponer endpoint `GET /api/pivote/mef/buscar` con parámetros `q`, `dpto`, `prov`, `dist`, `entidad`, `limite` para consulta instantánea (<200 ms) sin red sobre los 452k CUIs de `base_mef.py`.
- Crear script CLI `python -m scripts.buscar_mef` para consultas de desarrollo/soporte.
- Degradación limpia si la base MEF local no está cargada en la máquina. (Registrado en GitHub Issue #27).

---
id: T-TAREA-RESOLVER004
tipo: tarea
zona: resolucion/ (cui.py)
agente_origen: desarrollador
estado: completado
depende_de: []
---
**Validación y recuperación tras CUI citado contradictorio (Paso 0).**
- El CUI citado se contrasta con nombre y función oficial de la ficha MEF.
- Una contradicción positiva descarta el código como ancla y reinicia la búsqueda
  por nombre, RUC, entidad, ubicación y candidatos MEF.
- El resultado conserva la alerta y los candidatos, pero queda en `REVISIÓN`
  hasta confirmación humana; nunca sustituye automáticamente el CUI del
  certificado sin golden v4.
- La investigación del Hospital II Abancay confirmó una obra EsSalud/UNOPS real,
  pero no un CUI/SNIP para su construcción. El `2105743` provenía solamente de
  la redacción de la issue y no tiene respaldo en el certificado recibido.
- No se relajó el candado F7 para Bocanegra: la carga real contiene más de una
  inversión con esos topónimos y la golden v4 todavía no existe.
- Implementado en `f648cc3` + `5360985`; suite: 688 passed, 25 skipped.

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
    - [x] ~~`T-ETL-008` (#24): Cron semanal y actualización de `metadata.json`.~~
      **HECHO 2026-08-05** — la parte que importaba (que el fallo del refresco
      deje de ser silencioso): bitácora estructurada por corrida
      (`resolucion/bitacora_mef.py`), umbral `PIVOTE_MEF_DIAS_FRESCURA` (default
      10 d) y aviso en las tres superficies existentes (`/api/pivote/salud`, el
      buscador de #27, observación `BASE_MEF_DESACTUALIZADA` en el análisis).
      **Instalar el cron sigue abierto: es tarea del deploy**, con el simulacro
      en `docs/despliegue/despliegue-runbook.md` §10.
    - [ ] `T-ETL-009` (#25): Engine de búsqueda paralela N profesionales.
      **MEDIDO 2026-08-05 → recomendación NO-GO, esperando decisión de Rafael.**
      Evidencia: `docs/pruebas/issue25-medicion-paralelismo.md` (reproducible con
      `backend/scripts/medir_paralelismo.py`, offline, 7 concursos reales / 333
      experiencias). Números: el **97,9 %** del tiempo de la etapa de resolución
      es espera del portal InfoObras; el bucle local cuesta **0,6 ms por
      experiencia** y las consultas a la base MEF **≤ 5,8 s por concurso**
      (p50 82 ms, p95 204 ms), o sea **0,4 %–1,7 %** de un job de 3 a 21 minutos.
      Techo de Amdahl de lo paralelizable POR REGLA (solo base local): **×1,004
      a ×1,017** sobre el job. Además, `BaseMef` serializa `buscar_candidatos()`
      con un `RLock` de instancia (un pool daría ×1 tal cual) y la herencia por
      folio de `resolver_con_dedup` depende del orden. Reabrir solo si el CPU
      local supera ~30 s por concurso o el p95 de la base pasa de ~1 s.
- [ ] Camino A: no descargar ni pintar secciones de obra (valorizaciones,
  cronograma) en expedientes; silenciar advertencias COBERTURA para expedientes.
- [x] ~~Re-revisar con el cliente los 2 casos de verdad auditada dudosa:
  2195439 (Tocache vs Loreto) y 2064566 (Cotabambas vs Antabamba).~~
  **CERRADO por decisión de Rafael (2026-08-05: «Mátalos, ya no importan»)**:
  su propósito era corregir el banco de verdades auditadas, y ese corpus ya no
  existe (mismo destino que la exención ruc_match). Si alguna de esas dos obras
  reaparece en un análisis real, el flujo actual la atrapa solo: cae en
  «Por confirmar» y decide un humano. No reabrir.
- [x] ~~Unificar `backend/db/schema.sql` con el DDL real de `repositorio_pg.py`
  (o marcar schema.sql como documental).~~ **HECHO 2026-08-05** (F-SCHEMA, con
  T-REFACTOR-003): es espejo documental de los DOS DDL reales (`mef` primero) y
  un test offline impide que vuelvan a divergir.
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

> `T-REFACTOR-001` (reintentos y semántica de fallo unificados) se **aprobó y
> ejecutó el 2026-08-05** — ver `in_progress.md` y
> `.ai/decisions/ADR-014-reintentos-unificados.md`.

---
id: T-REFACTOR-002
tipo: refactor
zona: scraping/
agente_origen: fable
estado: aprobado
depende_de: [T-SONDEO-A06]
---
**Comparador único de nombres de empresa** (`mef.py::_nombres_coinciden` vs
`sunat.py::score_match_empresa` → un solo módulo con UNA lista de sufijos).

**Decisión de Rafael (2026-08-05), textual: «Haz la opción mínima ahora y la
doble corrida después».** La tarea queda partida en dos:

### Parte 1 — opción mínima · EJECUTADA (commit `ab146a0`)
Prelimpiado compartido de nombres, **cero cambio de criterio** en los dos
comparadores. `etapas_reales._nombre_emisor_limpio` (que solo usaba la búsqueda
SUNAT) pasó a `scraping/nombres_empresa.py` — puro, sin red y sin dependencias,
para que scraping/, validacion/ y orquestador/ lo importen sin ciclos — y lo
consumen el candado SEACE (`candado_seace.py::_senal_entidad`) y la
verificación de expedientes (`mef.py::_nombres_coinciden`).
Ojo al hallazgo que obligó a `variantes()` en vez de limpiar a secas: **el
paréntesis no siempre es ruido**. En `DIESA S.R.L. (Promotora, Constructora e
Inmobiliaria Diaz Espinoza Asociados S.R.L.)` afuera quedó la sigla y dentro
está la razón social entera — prelimpiar hundía el parecido de 93 a 15, o sea
un `ok` que se volvía `no_verificable`. Se puntúan AMBAS formas y gana la
mejor → el cambio es **monótono** por construcción.
Medición: divergencias 534 → 521 sobre 3.736 pares, y **25 → 18 en los 294
pares 100 % reales**; cero veredictos empeorados. Tests: `test_nombres_empresa.py`
(17 casos, suite 902 → 919 passed / 25 skipped).

### Parte 2 — doble corrida · APROBADA PARA DESPUÉS (post-deploy)
Ambos comparadores **calculan**, la divergencia se **loguea** en la traza del
job, y **ningún veredicto se mueve** hasta medir sobre 2-3 concursos reales.
Recién con esos datos se fija el umbral y se cambia el decisor del bloque MEF.
Red obligatoria antes de unificar de verdad: **mini-golden de ~120 pares** en
`backend/tests/golden/nombres_empresa.csv` (`a,b,mismo,origen`) — 60 positivos
por RUC de los espejos de `datos_pivote/`, 30 negativos de consorcio, 15 alias
comerciales, 10 entidades públicas de `referencia/seace_procesos/`, 5
contratistas de `tests/fixtures/mef/`; ~1,5-2 h de armado (el generador de
candidatos ya se escribió para el dossier; el costo es etiquetar). Criterio de
aceptación: ≥95 % en positivos **y** ≥95 % en negativos.
⚠ Esta parte SÍ puede cambiar veredictos VISIBLES al evaluador → estrictamente
post-deploy y con evidencia. ADR nuevo al cerrarla.

### Evidencia que NO hay que re-investigar (dossier de decisión, 2026-08-05)
- **Divergen y mucho: 534 de 3.736 pares (14,3 %), en UNA sola dirección** — el
  de MEF dice SÍ y el de SUNAT NO. **Cero** casos al revés: `SUNAT=SÍ` implica
  siempre `MEF=SÍ`. Corpus: espejos+enriquecimientos de `datos_pivote/`,
  `tests/fixtures/mef/*_contratos.json`, `referencia/seace_procesos/*.json`;
  128 emisores reales distintos.
- **Ninguno de los dos es el bueno.** SUNAT falla por estricto: sobre los 82
  pares P1 con verdad clara (emisor del cert vs razón social del MISMO RUC)
  acierta 72/82 — se le escapan `SINOHYDRO … SUCURSAL DEL PERÚ` vs `SINOHYDRO
  CORPORATION LIMITED` (76), `CHUNG & TONG … EN LIQUIDACION` (73), `PRONIS` vs
  `UNIDAD EJECUTORA 125 PROGRAMA NACIONAL DE INVERSIONES EN SALUD` (74). MEF
  falla por laxo: su regla «≥2 palabras en común» hace que **cualquier par de
  consorcios sea la misma empresa** (`CONSORCIO SUPERVISOR URPA` = `YANAHUANCA`,
  `MUNICIPALIDAD DISTRITAL DE LUCMA` = `USQUIL`); 303 de los 509 falsos
  positivos empiezan con «CONSORCIO …».
- **La contradicción era visible en un MISMO Excel** (ejecutado, no supuesto):
  `CONSORCIO HOSPITAL ABANCAY (COLESI … & JOCA …)` vs `CONSORCIO HOSPITAL
  ABANCAY` daba `en_contra` FUERTE «son entidades distintas (46/100)» en el
  candado y `ok` en el bloque MEF. Ese caso lo cierra la Parte 1.
- Superficies: candado `candado_seace.py:301-302`; herencia por folio #58
  `cui.py:2033-2034`; cruce SUNAT `etapas_reales.py:1387-1392`; bloque MEF
  `mef.py:262` → `excel_final.py:809,1129,2336`; y **Regla B de cruces de
  fechas**, que exige `contratista.veredicto == "ok"`
  (`cruces_fechas.py:250-270,401`) — un falso positivo del de MEF hace comparar
  el término declarado contra la aprobación del expediente de OTRA empresa.
- Debilidad pre-existente registrada para la Parte 2: el de SUNAT ya puntúa 87
  a `CONSORCIO HOSPITALARIO DE COMAS` vs `CONSORCIO HOSPITALARIO DEL CENTRO`
  (dos consorcios distintos) sin paréntesis de por medio. El umbral 85 sobre
  nombres de consorcio es exactamente lo que el mini-golden tiene que decidir.

> `T-REFACTOR-003` (cerrar ADR-009: Postgres obligatorio vs opcional) se
> **CERRÓ el 2026-08-05** con la decisión de Rafael — ver `completed.md` y el
> addendum de `.ai/decisions/ADR-009-migracion-postgres-mef.md`. Estaba
> DUPLICADA en este archivo (junto con B01–B06, F01, T-TAREA-003 y
> T-REFACTOR-001/002, en un bloque pegado dos veces); el duplicado se eliminó
> en el mismo acto tras verificar que las 160 líneas eran idénticas.

---
id: T-REFACTOR-004
tipo: refactor
zona: backend/ (api/, entregables/, scraping/, orquestador/)
agente_origen: desarrollador
estado: esperando_aprobacion
depende_de: []
---
**Modularizar los archivos monolíticos del backend (plan v2, 2026-07-27 — reemplaza el alcance v1)**:
Plan completo, reglas de corte y protocolo de verificación en
`docs/backend/analisis_tamanio_y_modularizacion.md` (§3-§6). Revisado por
fable el 2026-07-27 (v2.1: singletons de `api/` a `estado.py` por ciclo de
import, fachadas de `scraping/` como `__init__.py` de paquete, re-exports
faltantes de `excel_final`, detector de ciclos propio en vez de pydeps).
- **Alcance — 7 PRs secuenciales (~8.25 d), un monolito por PR**:
  0. Arnés de verificación: `tools/comparar_xlsx.py` (diff normalizado, ignora timestamps de openpyxl), `comparar_zip.py` (CRC por entrada), `ciclos_import.py` (AST) + líneas base.
  1. `api/app.py` (988) → routers por recurso + `estado.py` (singletons); el trío `/descargar-cui` + `_correr_y_descargar` quedan en la fachada (R1).
  2. `entregables/excel_final.py` (1,661) → paquete `excel/`: desarme REAL de `construir_hoja_profesional` (1,254 líneas, 23 closures sobre estado mutable) con `ContextoHoja` explícito. No es mudar la función de archivo. Incluye partir `test_entregables.py`.
  3. `entregables/zip_infoobras.py` (872) → paquete; `descargar_cui` NO se muda de la fachada (los tests parchean sus 4 descargadores sobre el módulo).
  4. `scraping/sunat.py` (1,136) → paquete con `__init__.py` como fachada (el nombre público es el del módulo).
  5. `scraping/infoobras.py` (1,841) → paquete; `fetch_by_cui` vive en el `__init__.py`; los imports diferidos de `cui.py` NO se tocan.
  6. `orquestador/etapas_reales.py` (1,366) → paquete `etapas/` con hogar para las ~350 líneas que no son etapas (`descargar_documentos_job` es público — lo llama `api/app.py:238`). El gate de issues #52/#53/#54/#57 ya está cerrado; incluye partir `test_etapas_reales.py`.
- **FUERA de alcance**: `resolucion/cui.py` — núcleo de decisión con semántica en movimiento (circularidad del solape abierta). Reingresa como T-REFACTOR-005 cuando la golden lleve 2 semanas quieta (doc §6, condición de reingreso).
- **Reglas inquebrantables (doc §3)**: R1 función parcheada y llamador en el mismo módulo — es la regla que decide dónde cae cada corte; R2 las fachadas re-exportan también los ~19 símbolos privados que consumen tests y `app.py`; R3 un PR = un monolito; R4 cero cambios de comportamiento (bugs hallados → backlog, PR aparte); R5 los tests monolíticos se parten en el mismo PR.
- **Criterio de Aceptación (por PR, doc §4)**: V1 pytest verde con cero `skipped` nuevos + V2 diff normalizado de Excel/ZIP = 0 sobre jobs `ff44d2833590`/`371fa5a1e704` vía `tools/utils/regenerar_excel_final.py` (obligatorio en PRs 2-3) + V3 `golden_cui.py --con-base --solo-cache` con diff EXACTAMENTE cero (PRs 5-6; en refactor no aplica el criterio suave) + V4 ciclos de import sin subir.
