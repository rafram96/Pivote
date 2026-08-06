# Completado (más reciente primero)

## 2026-08-05

---
id: T-REFACTOR-003
tipo: refactor
zona: persistencia/
agente_origen: fable
estado: cerrada  # decisión de Rafael, 2026-08-05
depende_de: [T-SONDEO-B01, T-SONDEO-B02, T-SONDEO-B03, T-SONDEO-B04, T-SONDEO-B05, T-SONDEO-B06]
---
**Cerrar ADR-009 con la evidencia del sondeo B — estatus GLOBAL de PostgreSQL.**
Cierra también **F-SCHEMA** (unificar `db/schema.sql` con el DDL real).

### Cerrada el 2026-08-05

**La decisión, textual (Rafael):** «Para 003: Postgres dejó de ser opcional,
ahora se usa para la base MEF. Se debe consolidar el schema.sql para ambos usos
(el más importante es el uso para el MEF).»

Registrada como **addendum fechado** en
`.ai/decisions/ADR-009-migracion-postgres-mef.md` (el ADR ya declaraba PG
obligatorio para el ETL; lo que faltaba era el estatus de sistema):

1. **PG OBLIGATORIO en el despliegue** — el compose siempre lo levanta. La razón
   es la **base MEF**, no el respaldo de jobs. Jerarquía explícita: MEF
   principal, respaldo lógico secundario.
2. **La degradación con gracia EN CÓDIGO se CONSERVA, deliberadamente**: `BaseMef`
   cae al índice RAM/CSV y el respaldo se desactiva con un warning (B03-fix).
   Obligatorio operacionalmente ≠ frágil ante una caída transitoria: un PG caído
   no tumba nada, pero es un estado **ANORMAL** que el operador debe corregir.
3. **Lo que NO resuelve, dicho sin adornos**: el write-path bloqueante con PG
   caído a mitad de job (B02) y la ausencia de cola de re-sincronización (B01)
   quedan como **deuda consciente**, con `scripts/migrar_a_postgres.py` (manual,
   upserts, no borra huérfanos) como único mitigador.
4. **Consecuencia de deploy anotada, NO implementada**: `healthcheck` +
   `depends_on` de Postgres en el compose pasan al runbook
   (`docs/despliegue/despliegue-runbook.md` §12, con su ⚠).

**`backend/db/schema.sql` consolidado** (F-SCHEMA). Era un esquema aspiracional
que nadie ejecutaba y que era estructuralmente incompatible con la realidad: 4
tablas (`concursos`, `jobs`, `espejos`, `enriquecimientos`), columnas GENERATED,
dos funciones y dos vistas (`base_datos`, `analisis`) que consultaban tablas que
ningún DDL crea. Ahora es el **espejo documental fiel de los DOS DDL vivos**, con
el **MEF primero** por decisión de Rafael:

- `mef` (`scripts/actualizar_base_mef.py::_DDL_PG`): `mef.loads`,
  `mef.investments` + 3 índices, `mef.active_load`;
- respaldo lógico (`orquestador/repositorio_pg.py::_DDL`): `jobs`, `documentos`,
  `profesionales` + 2 índices.

Cada bloque va **verbatim** entre marcas `>>> ESPEJO … <<<`, con prosa fuera de
las marcas explicando quién crea qué y cuándo (el código lo crea solo; el archivo
es referencia y bootstrap manual) y la advertencia de que **el archivo NO es
fuente de verdad**. Las vistas y tablas fantasma se eliminaron sin sustituto: los
docs ya se habían corregido (T-TAREA-001) para dejar de listar «la vista SQL».

**Guarda anti-divergencia** — `backend/tests/test_schema_sql.py`, 4 pruebas
offline, sin PG ni red: extrae los bloques marcados, normaliza (fuera comentarios
`--`, blancos e indentación) y los compara contra las constantes del código; una
prueba exige que no sobre ni falte ningún bloque; otra impide que las vistas
fantasma vuelvan a colarse como DDL. **Verificada de verdad**: cambiar un solo
tipo en el archivo (`fila_origen INTEGER` → `BIGINT`) la hace fallar.
**Límite documentado en el módulo**: es comparación de TEXTO — no valida que el
SQL sea válido para PostgreSQL ni que la BD desplegada coincida; eso exige un PG
real y esos tests siguen gateados por `PIVOTE_TEST_DB_URL`.

**Coherencia documental revisada**: `.ai/architecture/database.md` (divergencia
declarada CERRADA + estatus obligatorio), `.ai/architecture/backend.md` y
`.ai/prompts/reviewer.md` (la vista fantasma ya no está ni en el archivo),
`docs/backend/modelo_datos.md` (el bloque «DECISIÓN TOMADA 2026-07-01» quedó
marcado como SUPERADO: describe un esquema que jamás se construyó) y
`docs/despliegue/despliegue-runbook.md` §12 (persistencia real + el pendiente
del healthcheck).

**Limpieza de paso**: el backlog tenía un bloque de **160 líneas pegado dos
veces** (B01–B06, F01, T-TAREA-003 y T-REFACTOR-001/002/003; la primera copia de
T-REFACTOR-003 estaba truncada a media frase). Verificado byte a byte que las dos
copias eran idénticas antes de borrar una.

**Gates**: suite **870 passed, 25 skipped** (línea base 866/25; +4 pruebas
nuevas, cero regresiones) · cero red y cero PG real en pytest ·
`backend/resolucion/cui.py` intacto → no aplica golden · `compileall` y
`git diff --check` limpios · panel y skill sin tocar.

## 2026-08-04
- **Issue #80 (parcial) — rescatables del ZIP + correctivo de rumbo**: el
  almacén central SHA-256 se implementó y luego se REVIRTIÓ por decisión de
  Rafael (la dedup va en la descarga, no en la entrega — spec D1–D5 en la
  issue). Quedaron: árbol completo por experiencia, manifiestos SHA-256 junto
  a los PDF, estados humanizados e índice que explica compartidos. La caché
  de descarga por `obra_id` sigue PENDIENTE (#80 abierta). Medición del
  problema: 1,205 referencias → 317 contenidos únicos (~73% redundante).
- **Auditoría EsSalud — issues #32 y #72–#79**: consistencia inclusiva en todas
  las hojas; abstenciones InfoObras provisionales; veredictos visibles en P;
  Factor A sobre exceso efectivo; ALT04 reconciliado con histórico; CUI y
  procedencia en Base de Datos; saneo, controles y deduplicación del portal;
  validación semántica del recorte Factor A. Replay corregido generado fuera del
  repo. Gate: **742 passed, 25 skipped** + **54/54** Node. Resolver: abstención
  pura, sin promoción y sin golden disponible.

## 2026-08-02
- **Issues #54, #57 y #66** (`7593dea`): gate estructural para decisiones sin
  sustento en skill y backend; TOTAL declarado bajo autoridad del backend con
  desglose visible hasta el efectivo; captura de CUI literal dentro de prosa y
  rótulo de coincidencia verificada. Gate: **731 passed, 25 skipped** + **54/54**
  scripts, compilación y diff limpios. Sin deploy; resolver intacto.
- **Fixes pre-deploy #68, #64, #42 y #65**: recorte TDR amplio y honesto;
  cómputo efectivo desde el inicio real de obra; revisión `202` con estado
  persistido y panel recuperable; supuestos con procedencia estructurada y
  color violeta. Gate: **727 passed, 25 skipped**, contrato histórico y build
  productivo del Panel aprobados. Sin deploy; resolver CUI intacto.
- **ADR-S007 — tren de rescates A–D hacia `demo`**: A destraba el WAF de
  SEACE y bloquea red accidental en pytest; B reintenta `PermissionError` de
  escrituras JSON en NTFS; C valida todos los insumos antes de crear el job,
  hace ruidoso el ZIP roto y exige magia PDF; D deduplica documentos SEACE por
  `fileCode` mediante caché compartida, válida y atómica. Tags de retorno:
  `demo-pre-rescates`, `demo-pre-B-atomicos`, `demo-pre-C-ingesta` y
  `demo-pre-D-cache-seace`. Gate final: **721 passed, 25 skipped**, compilación
  y diff limpios; resolver intacto, sin golden. Todo integrado localmente en
  `demo`; sin push ni despliegue. `refactor` permanece congelada en `65d41af`.

## 2026-07-26
- **Issue #32 — factor de evaluación embebido** (`17b1e04`, rama
  `rafram96/issue-32-embeber-el-factor-2`): la página del Cuadro de Factores
  (4.2 A) cierra cada hoja de profesional, junto al TDR y el Anexo 16 que ya
  se embebían. Cadena: `agent-bases.pagina_factores` → `_meta` → recorte
  `P{n}_FACTOR.pdf` (misma página replicada por profesional, para no tocar el
  filtro `P*` del ingest ni el reparto por `n_prof`) → `excel_final`.
  De paso: **`regenerar_excel_final` ya no arranca los embeds** — nunca pasaba
  `certificados`, así que el backfill de cargos devolvía el entregable sin
  ninguna imagen. Falta la verificación sobre un job real (huachocolpa).

## 2026-07-25
- **T-TAREA-ADR011 · certificados multi-obra** (Issue #26), en 3 PRs sobre
  `demo` — rama `rafram96/issue-26-t-multi-001`, SIN pushear todavía:
  - **PR-1** (`74cc80e`): la skill desglosa paquetes SIN CUI (antes el
    disparador exigía código por sub-obra, así que el caso HV ni llegaba al
    backend); fixture HV congelado, válido en Pydantic y en zod.
  - **PR-2** (`ed26628`): escalera CUI→nombre + `_exp_derivada` + mapeo aditivo
    de estados. Detalle que no estaba en el ADR: no heredar `ubicacion` NO basta
    — la geografía de la madre entra igual por `entidad_contratante`
    (`ubigeo_cert`, `_muni_contradice`), y hay que apagarla con
    `_solo_geo_propia`.
  - **PR-3**: candado multi-rubro, contradicción exigida ENTRE dos sub-obras.
  - Golden 277 casos con **cero drift** en las dos corridas (PR-2 y PR-3).
  - Bug colateral corregido: `EtapaResolucionCui.correr` descartaba TODAS sus
    observaciones (`MULTI_OBRA`/`PROBABLE`/`PRIVADA`) por no pasar `obs` a
    `_res`.
  - Pendiente del ADR: P2 (Escenario B con sub-fechas por anexo) sigue
    pospuesto — el contrato ya lo modela, falta un cert real que lo exija.

## 2026-07-22
- Base de conocimiento de NIVEL SISTEMA creada en la raíz `InfoObras/.ai/`
  (repo git propio; ADR-S001): panel documentado, contratos cross-repo,
  legacy inventariado; `CLAUDE.md` del Panel reescrito como puntero.
- Base de conocimiento `.ai/` creada.
- Documentos del paquete de extras actualizados a v3 (T-008 incorporado) +
  `arquitectura-sistema.html` nuevo (commits `5025ccb`, `f2bde36`).
- Análisis del spec "para RAFAEL-V2.xlsx" → matriz + cotización interna.

## 2026-07-21
- **F8**: vetos de ubicación (provincia/distrito/entidad municipal) + guard de
  empate geo; golden 10 mal-resueltos, cero regresiones (`3ec1581`). Terminado
  a mano tras corte del subagente por límite de gasto.
- **Camino A**: clasificador por toda la evidencia + `PIVOTE_FORZAR_EXPEDIENTES`
  + fix del prompt de la skill (`90b25be`); San Isidro re-corrido (28
  expedientes verificados en MEF, cero clamps indebidos).
- **Skill Paso 4.5 acotado** (`df053ee`): fin de la fuga de ~3M tokens.
- Rescate completo del análisis San Isidro sin gastar tokens de skill (espejo
  sobreviviente + scripts determinísticos + backend): job `b4f385c31811` con
  Excel de imágenes embebidas + 249 MB de sustento + ZIP.
- Auditoría manual de las 105 experiencias del replay BNP
  (`datos_pivote/c9c769976750/revision_manual.md`): 4 CUIs mal → origen del F8.
- Tesseract habilitado en la laptop (spa tessdata) → OCR Camino A local.

## 2026-07-20
- **F0-F7 del refactor del resolver** (commits `a732936…b341a22`): golden
  baseline (277 casos), base local MEF (ETL + índice), refactor estructural,
  fusión de candidatos, solape eliminado de la selección (ADR-003),
  público-primero + catálogo de entidades (ADR-004), candados F7 (ADR-005).
- Pruebas vivas: replay 9 exps y 105 exps de punta a punta.
- Validaciones empíricas previas: cobertura CSVs MEF 191/194; precisión fuzzy
  (top-1 67%, candidatos 82-85%); análisis de entidades contratantes (1042).

## Antes del refactor (hitos mayores, ver git log de `demo`)
- T-003 verificación de expedientes MEF (cerrado S/2,600) + fix aprobación ET.
- Deploy on-prem inicial (2026-07-12). Postgres respaldo. Progreso fino
  (paquete A). Sondas SEACE/CONOSCE/OCDS (GO) y RENIPRESS (GO).
