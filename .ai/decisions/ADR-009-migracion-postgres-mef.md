# ADR-009 · ETL MEF serving-first: índice RAM + PostgreSQL

- Fecha: 2026-07-23; decisión final 2026-07-29
- Estado: **ACEPTADO**

## Contexto

ADR-002 creó un archivo compacto y un índice RAM para que el resolver busque
inversiones por nombre sin depender de la red. El objetivo del nuevo ETL es
enriquecer ese resolver: una vez identificado un CUI/SNIP candidato, debe poder
contrastar más datos oficiales.

La RAM no es una restricción, pero cargar allí toda la ficha no aporta valor.
PostgreSQL ya forma parte del despliegue on-prem y el desarrollador confirmó que
es el destino obligatorio. El EDA real encontró 620,985 filas, 579,481 CUIs y
una sola identidad duplicada.

## Decisión

El ETL publica dos representaciones coordinadas:

1. `inversiones.csv.gz`, cargado en RAM, conserva la búsqueda difusa por nombre.
2. `mef.investments` en PostgreSQL conserva la ficha enriquecida y se consulta
   por `(load_id, CUI/SNIP)`.

El schema independiente `mef` contiene:

- `mef.loads`: estado y metadata de cada carga;
- `mef.investments`: ficha canónica por identidad y carga;
- `mef.active_load`: puntero operativo a la carga publicada.

Los artefactos de disco y PostgreSQL comparten `load_id`. El resolver toma el
`load_id` del manifest de disco y lo incluye en la consulta SQL; así nunca mezcla
el índice RAM de una versión con fichas de otra.

Publicación:

1. construir gzip, catálogo y metadata en staging;
2. cargar PostgreSQL por `COPY` y reconciliar el total de identidades;
3. marcar la carga `validated`;
4. publicar el manifest mediante `os.replace`;
5. actualizar `mef.active_load` en una transacción.

PostgreSQL es obligatorio para ejecutar una nueva carga. Si cae durante una
consulta del resolver, `BaseMef` degrada a la ficha mínima del gzip y el análisis
puede continuar.

La ficha v1 incluye identidad, nombre, estado/situación, entidad, ubicación
compatible, nivel/sector/función, tipo de inversión, tipología, modalidad,
montos, fechas, expediente técnico y OPMI/UF/UEI/UEP. Las coordenadas se
excluyen.

## Consecuencias

Positivas:

- consulta enriquecida compartida entre procesos;
- tipos e índices gobernados en PostgreSQL;
- trazabilidad y rollback por carga;
- la búsqueda RAM ya validada no se reescribe;
- queda una base directa para API/panel futuros.

Costos:

- PostgreSQL pasa a ser requisito del cron, aunque no del resolver en ejecución;
- filesystem y PG no comparten una transacción distribuida;
- se mantienen dos representaciones derivadas;
- cada nueva señal de scoring exige pytest + golden.

## Alternativas descartadas

### Todo en RAM

Aumenta carga inicial y replica campos por proceso sin beneficiar el lookup
exacto.

### SQLite

Era técnicamente suficiente para una sola máquina, pero contradice la decisión
de infraestructura del proyecto y no comparte naturalmente las fichas entre
procesos/consumidores.

### Reemplazar RAM por PostgreSQL

Obligaría a rediseñar la búsqueda difusa ya validada y haría al resolver
dependiente de PG. No aporta una mejora demostrada.

## Regla para enriquecer el resolver

El ETL transporta datos, no cambia el scoring. Cada campo nuevo debe definir
coincidencia, contradicción y ausencia. Tipología, modalidad y unidades
responsables nunca rechazan por estar vacías. Todo cambio al resolver exige
pytest y golden.

## Addendum 2026-08-05 — estatus GLOBAL de PostgreSQL: OBLIGATORIO

Lo que este ADR ya decía («PostgreSQL es obligatorio para ejecutar una nueva
carga») valía solo para el ETL. Quedaba abierto el estatus a nivel de SISTEMA:
obligatorio u opcional. Esa era la pregunta de `T-REFACTOR-003`, alimentada por
los sondeos B01–B06.

**Decisión de Rafael, textual (2026-08-05):**

> «Para 003: Postgres dejó de ser opcional, ahora se usa para la base MEF. Se
> debe consolidar el schema.sql para ambos usos (el más importante es el uso
> para el MEF).»

### Qué queda decidido

1. **PostgreSQL es OBLIGATORIO en el despliegue.** El compose siempre lo
   levanta. La razón no es el respaldo de jobs: es la **base MEF**, cuya ficha
   enriquecida por `(load_id, CUI/SNIP)` vive únicamente ahí. Sin PG el sistema
   corre, pero corre ciego a esa ficha.
2. **Jerarquía de usos**: el uso MEF es el **principal**; el respaldo lógico de
   jobs (`RepositorioConRespaldo` → `RepositorioPostgres`) es **secundario** y
   conserva su contrato de siempre — los archivos son la fuente de verdad.
3. **La degradación con gracia EN CÓDIGO se CONSERVA, deliberadamente.** No es
   una contradicción con «obligatorio»: obligatorio operacionalmente ≠ frágil
   ante una caída transitoria.
   - `BaseMef` degrada al índice RAM/CSV y el análisis continúa (ya estaba en
     este ADR).
   - El respaldo de jobs se desactiva con **un** warning si PG no responde al
     arrancar (B03-fix, 5-ago: pool y DDL perezosos, `PIVOTE_DB_TIMEOUT_BOOT`).
   - Un PG caído **no tumba nada**, pero es un estado **ANORMAL** que el
     operador debe corregir. La degradación es una red de seguridad, no un modo
     de operación aceptable.

### Qué NO resuelve esta decisión (deuda consciente)

Declarar PG obligatorio no arregla el write-path. Se registra tal cual, sin
disfrazarlo de cerrado:

- **B02 — bloqueo síncrono con PG caído a mitad de job.** `_respaldar()` corre
  en el hilo del pipeline; con la BD caída DESPUÉS del arranque, cada escritura
  respaldada bloquea hasta el timeout del pool antes de tragarse la excepción.
  Un job de 8 etapas hace checkpoint por etapa: puede sumar minutos de espera
  muerta, y `resolver_revision` (un clic del evaluador) también la paga.
- **B01 — no hay cola de re-sincronización.** Una escritura perdida no se
  reintenta ni deja marca de «PG desincronizado», y un `eliminar(job_id)`
  ocurrido con PG caído deja filas fantasma que el re-sync nunca borra.

**Mitigador actual, y es el único**: `backend/scripts/migrar_a_postgres.py`
re-sincroniza **a mano** (upserts; no borra huérfanos). Ambos puntos quedan como
mantenimiento, no como parte de esta decisión.

### Consecuencia para el deploy

`healthcheck` + `depends_on` de PostgreSQL en el compose pasan a ser parte del
**runbook** de despliegue: si PG es obligatorio, el backend no debe arrancar
contra una BD que todavía no acepta conexiones y quedarse sin respaldo por
carrera de arranque. **No se implementa en esta tarea** — queda anotado para
`docs/despliegue/despliegue-runbook.md`.

### Destino de `db/schema.sql` (cerrado en el mismo acto — B04)

`backend/db/schema.sql` era un esquema **aspiracional** que nadie ejecutaba y
que era estructuralmente incompatible con los DDL reales. Queda reescrito como
**espejo documental fiel y consolidado** de los DOS DDL vivos, con el schema
`mef` primero (uso principal). No es fuente de verdad: el código lo es. Las
vistas fantasma (`base_datos`, `analisis`) y las tablas que nadie crea
(`concursos`, `espejos`, `enriquecimientos`) se eliminaron; los docs ya se
habían corregido para dejar de listar «la vista SQL» como consumidor real
(T-TAREA-001). Una prueba offline (`backend/tests/test_schema_sql.py`) compara
el archivo contra los DDL del código para que no vuelvan a divergir.

## Referencias

- `docs/backend/eda_datos_abiertos_mef.md`
- `docs/backend/modulo_etl_mef.md`
- `.ai/decisions/ADR-002-base-local-mef.md`
- `backend/db/schema.sql` (espejo documental de los DDL reales)
- Sondeos `T-SONDEO-B01`–`B06` y `T-SONDEO-F01` en `.ai/tasks/backlog.md`
