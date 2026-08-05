# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

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
- **Hallazgos nuevos SIN issue aún**: (a) `funciones_similares` 62/62 null en
  urgente1 → la 2ª puerta del candado #31 quedó inerte (¿certs sin funciones
  o agente no las busca?); (b) celdas de abstención en blanco sin rótulo
  (escribir "POR VERIFICAR" en celda — familia #55); (c) exención ruc_match
  (golden ancha) sigue sin issue. Cola visible: #55; #54, #57, #19 y #42
  quedaron cerradas el 2-ago. El diseño expediente/obra sigue en #70.
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
