# Handoff — punto de continuación

> Actualizado: **2026-07-28**. Si eres un agente nuevo: lee esto completo,
> luego `context/current_state.md` y los ADRs. No necesitas ninguna
> conversación previa.

## Cierre del 2026-07-28 — Correcciones de Identidad en Lircay (#58, #59, #60, #61)

Auditada la corrida de Lircay (job `371fa5a1e704`), se aplicaron 4 fixes en `fix/identidad-lircay`:
1. **#60 (`excel_final.py`):** Se separó el rótulo del Excel entre "CUI del certificado" y "No consignado en el certificado — el sistema identificó el CUI X" para no confundir la inferencia del backend con un dato del documento.
2. **#58 (`cui.py::resolver_con_dedup`):** La herencia por folio ahora exige coincidencia de emisor (score de empresa ≥ 70) para evitar que folios corridos por la skill hereden obras ajenas (rechaza Arcadia≠Picota).
3. **#59 (`cui.py::_paso_codigo_citado`):** Se acotó la exención del CUI exacto para que caigan a `revision` los códigos citados cuya obra contradiga simultáneamente nombre, departamento y rubro (caso Navarro, P9-E3).
4. **#61 (`cui.py`):** Se añadió veto de fase para que registros de InfoObras de "ELABORACIÓN DE EXPEDIENTE TÉCNICO" no respalden experiencias de ejecución/supervisión vía `ruc_match` (caso Santa Anita, P2-E3).

Resultados: 627 tests pasados, 0 regresiones. Los 3 casos de Lircay (2:4, 9:3, 2:3) pasan ordenadamente a `revision`.

## Cierre del 2026-07-27 — FALSO CUMPLE corregido

Auditar 3 análisis reales (156 experiencias) destapó **5 profesionales en verde con
el tiempo efectivo bajo el mínimo**. Cerrado en #51 / PR #56 (`cf9804b` en `demo`),
619 tests. Lo que hay que saber: **la conciliación ya existía y estaba inhabilitada
por un regex** que solo leía «años» cuando las bases dicen «meses» (0 de 44). Ver
`context/current_state.md` y las lecciones nuevas en `memory/common_mistakes.md`.

Queda abierto de esa auditoría: #57 (la columna TOTAL la calcula el LLM y no es
confiable) y 3 defectos sin dueño — oferta económica incompleta, experiencia del
postor no computable y jerga técnica en el entregable. Inventario completo en el
comentario de auditoría de #51.

## Handoff previo (2026-07-27) — gobierno y saneamiento

Detalle completo en [`2026-07-27_claude.md`](2026-07-27_claude.md). Sesión sin
código de producto; un commit (`27c8cde`). Lo que hay que saber antes de tocar nada:

1. **La skill instalada ahora es un junction a `Pivote/skill/`**, no una copia.
   Llevaba 13 días corriendo una versión del 14-jul **sin el escudo de integridad**
   (podía subir corridas incompletas). ⛔ **Nunca borrar ese enlace con `rm -rf`**
   — se lleva el destino. Ver `conventions/coding.md`.
2. **El repo es PÚBLICO.** Antes de commitear un documento, revisar si trae precios,
   cuentas por cobrar o la IP del servidor. `docs/comercial/` está gitignored por eso.
3. **Antes de proponer un diseño, buscar en `decisions/`.** Hoy se abrió una issue
   re-derivando ADR-010, que ya estaba decidido.
4. **T-008 ya no promete Postgres/Hot-Cold/pg_trgm** en el material comercial —
   no existe en el código. El épico ETL #12-#25 es trabajo pendiente, no hecho.
5. ⚠ **`ai-cli` no se puede usar en este nivel**: `counters.json` está en 0 con
   ADR-013 existiendo → `ai-cli new` colisiona. Y `validate` da 67 errores
   preexistentes (frontmatter faltante en los 13 ADR y en 3 índices de `tasks/`).
   El nivel `InfoObras/.ai` valida limpio.

## Nota (2026-07-26) — fixtures preparados para probar el backend nuevo

Detalle completo en [`2026-07-26_claude.md`](2026-07-26_claude.md). En una línea:
`Pronis_Sonitor/`, `Soritor2/` y `Consorcio-Lircay/` quedaron preparadas con
`_prep/MAPA.md`; **no había propuestas repetidas** (sí bases triplicadas,
≈273 MB); mapa de carpetas en `fixtures/ing manuel/_CONCURSOS.md`. Tres cosas
que importan para cualquier corrida:

1. En **Soritor** el factor **C. Sostenibilidad Social está eliminado**
   (tachado) — no puntúa.
2. En **Lircay** las bases dicen "sin tachas" y **sí tienen tachado en 16
   páginas** (equipamiento estratégico y funciones BIM) → usar
   `_prep/bases_texto.txt`.
3. En **Lircay falta la oferta económica** de los 2 postores → sin límite
   inferior.

Herramientas en `src/tools/`: `detectar_tachado_pdf.py`, `trocear_pdf.py`,
`render_paginas.py`.

## Nota de mantenimiento (2026-07-23) — el checklist de deploy RECAYÓ una vez

La auditoría de migración de la base `.ai` (dos niveles) encontró que
`context/roadmap.md` y `context/current_state.md` volvían a resumir el
checklist de deploy — el mismo patrón que ADR-S002 ya había corregido — y
los resúmenes eran peligrosos: omitían el merge del Panel y la regla de
orden de ADR-007 (plugin SOLO después del backend nuevo). Fase 1 de la
corrección ejecutada: ambos quedaron reducidos a puntero a
`InfoObras/.ai/tasks/active.md` (fuente única; verificado que ahí la regla
de orden está literal y el paso del Panel existe). Si ves el checklist
copiado en cualquier otro archivo, es una regresión: bórralo y deja puntero.

Más tarde el mismo día: **merge fast-forward `sonda/refactor-cui` → `demo`**
(`c31f71a`, solo local — push pendiente de confirmación del desarrollador;
la sonda no recibe más commits) y **Fase 2 de la corrección cerrada** sobre
`demo` (commits `c7045a7…`): coexistencia overview↔topology declarada, lista
T-00x consolidada en `vision.md` (raíz), tareas reubicadas por nivel,
ADR-S004 en la raíz, conteo de la golden con fuente única en
`architecture/backend.md`.

## Nota (2026-07-25) — ADR-011 arrancó, y un bug que apareció de paso

`EtapaResolucionCui.correr` (`etapas_reales.py`) acumulaba observaciones
`MULTI_OBRA` / `PROBABLE` / `PRIVADA` y **no las pasaba a `_res`**: se perdían
en el return, así que nunca llegaban al job ni al panel (solo quedaban, a
medias, en el enriquecimiento). Corregido en PR-1 del Issue #26. Si ves una
etapa que arma una lista `obs` y no la devuelve, es el mismo patrón.

## Nota (2026-07-26) — PRs 33/34/35 revisadas, corregidas y mergeadas a demo

Orquestación completa: #33 (pestañas/nombres) la mergeó el desarrollador;
#34 (SUNAT histórico) se mergeó tras corregir el hallazgo H2 del review
(`d59f900`: «habido durante la obra» exigía solo que un tramo TOCARA el
periodo → verde con días sin dato; ahora pide cobertura completa y degrada a
«No verificable» con los huecos listados); #35 (ADR-011 multi-obra) mergeó
limpia; #36 arregló el choque de integración 33×35 (tests con nombre de
pestaña viejo). Suite en demo: **333 passed**. H1 del review (fixture
`hacer_motor` sin `extras_sunat` → pytest puede tocar la red) quedó SIN
corregir por decisión del desarrollador. Pendientes que dejaron los merges:
**un solo rebuild del plugin** (33/34/35 tocaron skill/schemas — ADR-007:
viaja con el backend), ~~regenerar `golden_cui_baseline.json`~~ (HECHO 26-jul,
ver nota abajo)
(el actual es pre-refactor y da −10 falsos), y los issues del panel
(sub-obras panel#1 + render SUNAT).

25-jul: **issue #30 — el emisor del certificado en SUNAT** (rama
`rafram96/issue-30-mostrar-representante-legal`). Sondeada y cableada la
consulta "Información Histórica" (`getinfHis`, sin captcha) además de los
representantes legales (`getRepLeg`, ya existía sin usar). El bloque emisor del
Excel ahora responde **¿estaba HABIDO al emitir el certificado y durante la
obra?** con la pregunta en el título del campo, lista los representantes
(informativo — ADR-008 descartó ALT-12), y suma un cuadro histórico contiguo
(R:U) que corrió el de representante de obra a W:Z. Falta el render en el
panel (repo `Panel-InfoObras`): el JSON ya viaja con `representantes`,
`historico` y `habido`.
## Nota (2026-07-26) — issue #32, el factor de evaluación en cada hoja P

Rama `rafram96/issue-32-embeber-el-factor-2` (`17b1e04`), sobre demo ya con
33/34/35 dentro. Lo que un agente nuevo necesita para retomarlo:

- **Falta lo único que no se puede hacer offline**: correr un job real y MIRAR
  el recorte. No basta `regenerar_excel_final`: hay que re-correr
  `extraer_certificados.js` con `bases.pdf` y volver a subir el ZIP, porque los
  `certs/` en disco no tienen el `P{n}_FACTOR.pdf`. No re-scrapea nada.
- **El riesgo vivo es el número de página**, no el código: lo elige un LLM
  (`agent-bases`), y un recorte de la página equivocada se ve legítimo. El
  script valida el rango y avisa por stdout; la corrección real es mirarlo.
- **No agrava el pendiente de rebuild del plugin**: el cambio es compatible en
  ambos sentidos (un `P{n}_FACTOR.pdf` en un backend viejo se ignora; un
  backend nuevo sin el archivo genera la hoja como antes). Viaja con el rebuild
  único que ya deben 33/34/35.
- **Pendiente de cliente**: confirmar si el TDR y el Anexo 16 se quedan al
  INICIO de la hoja (hoy) o bajan junto al factor. Son dos líneas en
  `excel_final.py`.

## Nota (2026-07-26) — baseline de la golden REGENERADO, y la caché ya sirve

El baseline vivía desde el 20-jul (PRE-refactor T-008) y comparar contra él daba
−10 correctos que parecían regresión y eran la deuda de no regenerarlo. Además
`--solo-cache` había dejado de funcionar: la caché es de ANTES de que el resolver
fusionara candidatos MEF, así que le faltaban **642 de 1957 claves** (461 `cod:`,
181 `nom:`) y abortaba en el primer hueco.

Corrida en vivo autorizada por el desarrollador (26-jul, sobre `demo` = `b7d4c4a`,
post-merge de #48): **339 s, 1.2 s/caso, cero `portal_caido`**. La caché quedó
completa (7.9 MB) y **`--solo-cache` vuelve a correr offline** — verificado.

Baseline nuevo (es el vigente): correcto **230** · incorrecto **10** · revisión 34
· privada 3. Contra el viejo: incorrecto 16→10, y la matriz de transiciones da
**cero `correcto → incorrecto`** (el criterio duro de la Regla de oro). Los 8
`correcto → revisión` son el costo de abstención que ADR-005 ya había aceptado.
El viejo se conservó como `golden_cui_baseline.prerefactor.json`.

⚠ Un solo caso empeoró de verdad (`revisión → incorrecto`): CUI **2195439**
(I.E. N° 0022 Jorge Ríos) — y es **uno de los dos casos de "verdad auditada
dudosa"** que ya estaban en el backlog (Tocache vs Loreto). Antes de tratarlo como
regresión hay que resolver cuál es la verdad.

## Nota (2026-07-26) — la golden ANCHA es el baseline, y lo que revela

La golden armaba cada caso con solo `proyecto` + `cui` (fechas en None), así que
**toda regla que lea `ubicacion`, `entidad_contratante` o `ruc_emisor` era INERTE
en ella**: los vetos de ubigeo, ADR-013 entero, `ruc_match`, `ent_match` y la
clasificación de privadas nunca se ejercitaban. Se comprobó cuando ADR-013 dio
matriz perfectamente diagonal — probó cero regresión y no validó nada.

Ensanchada (`golden_cui.py` hace join contra el espejo de origen por
`job` + `prof:exp`): **277/277 casos enriquecidos, 0 degradados**. El baseline
ancho ya está promovido (autorizado 26-jul); los anteriores quedan como
`golden_cui_baseline.estrecha.json` y `.prerefactor.json`.

⚠ **Lo que revela, y hay que mirarlo**: con los datos completos el resolver
saca **14 mal-resueltos, no 10**, y aparece **1 `correcto → incorrecto`** más 3
`revisión → incorrecto`, varios **vía RUC**. No es regresión del código: es que
la golden estrecha nunca lo midió. La hipótesis a investigar es que la exención
«`ruc_match` exime de todo veto» sea demasiado fuerte — el RUC del emisor casa
con una obra donde esa empresa participó, pero no con la del certificado.

## Nota (2026-07-26) — #47: los certificados son escaneos

De los **729 recortes** del corpus, **solo 2 traen capa de texto**; los otros 727
son escaneos puros. La verificación folio↔emisor está implementada y cableada en
VALIDACIÓN, pero solo puede pronunciarse sobre el 0.3%: el caso que motivó la
issue (`95af90f1578e` prof 1 exp 1, folio 358 en vez de 359) es un escaneo y el
módulo se abstiene. Decisión del desarrollador: **la abstención "No verificable"
es el comportamiento correcto**; adivinar sobre 727 escaneos sería ruido en masa.
Detectar el corrimiento de folio en general exige verificar ANTES del recorte
(lado skill, donde está el PDF completo) o meter OCR.

## ¿Qué se estaba haciendo?

Semana 20-22 jul: **refactor completo del resolver de CUI** (rama
`sonda/refactor-cui`, 13 commits) — base local MEF, público-primero, camino
expedientes/obra, candados de abstención — validado con una auditoría golden de
277 casos (errores silenciosos 16→10, cero regresiones) y corridas reales.
Además: optimización de la skill (Paso 4.5), rescate del análisis San Isidro, y
actualización del paquete comercial de extras (T-003…T-008).

## ¿Qué falta? (en orden recomendado)

1. **Deploy como paquete** (cross-repo: backend + panel + plugin + server) —
   el checklist canónico vive en **`InfoObras/.ai/tasks/active.md`** (nivel
   sistema); aquí no se copia. Regla clave: NO entregar el plugin sin el
   backend nuevo (ADR-007).
2. Pulido camino A (filtro de secciones de obra en descargas/Excel).
3. Reunión de cotización (materiales: `docs/nuevos_modulos/*.html` v3).
4. Resto: `tasks/backlog.md`.

## Archivos clave

- Resolver: `backend/resolucion/cui.py` (+ `base_mef.py`, `texto.py`).
- Orquestación: `backend/orquestador/etapas_reales.py` (caller del resolver,
  camino A/B, clamps) y `motor.py`.
- Validación: `backend/scripts/golden_cui.py` + baselines en
  `backend/datos_pivote/golden_cui_*.json` (gitignored pero presentes local).
- Skill: `skill/SKILL.md` (Paso 4.5) y `skill/prompts/agent-propuesta-profesional.md`.
- Jobs de referencia local: `b4f385c31811` (San Isidro camino A, entregado),
  `c9c769976750` (replay BNP con `revision_manual.md`).

## Nota (2026-07-26) — #28 paso 1: el dato que estaba y nadie leía

Antes de agregar columnas a la base MEF, revisar si el campo ya está cargado.
`estado_dataset` viajaba en `base_mef.py` desde F3, se exponía en la ficha del
candidato y **ningún consumidor lo leía**: 229k de 494k filas son DESACTIVADAS
y competían de igual a igual con las vivas. Usarlo rompió el empate de Sullana
de 4 a 2 y liberó el 23% del presupuesto de consultas al portal, sin regenerar
el artefacto (PR #39). El alcance original de la #28 arrancaba por regenerar la
base; el orden correcto era al revés.

**Regla que salió de acá:** las señales de la base MEF son DESEMPATE, jamás
filtro. 15 de 191 verdades auditadas viven en filas DESACTIVADA (un CUI
reformulado queda desactivado y el certificado cita al viejo). Y el guard exige
el dato en AMBOS lados: un CUI ausente de la base es DESCONOCIDO, no vivo —
resolver apoyándose en la ausencia de información es adivinar.

**Trampas del dataset de 68 campos, medidas (para el paso 2):**
- `DES_TIPOLOGIA` está VACÍA en los dos CUIs de referencia (2483109, 2502652);
  0% en desactivadas, 32.6% global. No sirve como veto.
- `TIPO_INVERSION` no es binario "PROYECTO vs IOARR": son 8 valores y las obras
  ARCC del caso HV son `INTERVENCIONES IRI`. Un veto por tipo mata al correcto.
- Las DESACTIVADAS no traen `PRIMER/ULTIMO_DEVENGADO` (solo el acumulado).
- `golden_cui.py:190` arma la experiencia con `fecha_inicial: None` → cualquier
  regla de ventana temporal es INERTE en el golden. Para medirla hay que
  enriquecer el corpus con las fechas del cert (join `job` + `prof:exp` contra
  los `espejo.json`).

## Riesgos vivos

- Server en producción corre el código VIEJO hasta el deploy.
- Los baselines/caches de la golden viven solo en esta laptop (datos_pivote
  gitignored) — no borrarlos; sin ellos la re-validación exige corrida en vivo
  (~1.5 h contra InfoObras).
- Límite de gasto mensual de la cuenta Claude alcanzado (21-jul): subagentes
  pueden morir a mitad; preferir trabajo directo o esperar el ciclo.
- 2 verdades de auditoría dudosas (ver `tasks/backlog.md`).

## Regla de oro antes de tocar el resolver

> ⚠ **NOTA (2026-07-28) — EL CORPUS DE LA GOLDEN SE PERDIÓ IRREMEDIABLEMENTE**
> (confirmado por el desarrollador): `auditoria_cui_v3.xlsx` (~277 verdades
> humanas), `_golden_cui_cache.json` y `golden_cui_baseline.json` no existen
> en ninguna máquina. **El ciclo de abajo NO se puede ejecutar** hasta
> reconstruir el corpus (plan v4: exportar las revisiones resueltas en el
> panel del server —cada CUI pegado por el evaluador es una verdad humana—
> + capturar los reclamos de auditoría del ing. como filas de verdad; luego
> regenerar caché y baseline). MIENTRAS TANTO: solo se aceptan cambios del
> resolver de **ABSTENCIÓN PURA** (resuelto→revisión, nunca al revés) con
> regresiones unitarias dirigidas + replay de jobs reales del server con
> `scripts/resubir_job.py` (antes/después). Aflojar vetos o recalibrar
> umbrales queda PROHIBIDO hasta que la golden v4 exista — es exactamente
> lo que ADR-005 no permite hacer sin instrumento.

Cualquier cambio se valida así, en este orden (ciclo HISTÓRICO, hoy sin
instrumento — ver nota):
`pytest backend/tests -q` (offline) → `golden_cui.py --con-base --solo-cache`
→ comparar contra `golden_cui_baseline.json`. Criterio: mal-resueltos nunca
suben, cero correcto→incorrecto. Nunca relajar compuertas para "ganar" casos
(ADR-005).
