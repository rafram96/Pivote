# ADR-009 · Capa PostgreSQL del ETL MEF y convivencia con el índice RAM

- Fecha: 2026-07-23; revisado 2026-07-29
- Estado: **ACEPTADO PARA PLANIFICACIÓN**
- Alcance: arquitectura del módulo ETL; no autoriza todavía su implementación

## Contexto

ADR-002 resolvió una necesidad concreta: construir semanalmente un archivo
compacto e índice RAM para que el resolver de CUI tenga candidatos locales y
pueda degradar a InfoObras si la base no está disponible.

El perfilado real de los tres CSV del corte 2026-07-26 encontró 620,985 filas,
640.7 MB y 95 columnas distintas. El proceso existente publica 10 campos y
descarta el resto. Preservar, consultar y auditar el corpus completo es un
módulo nuevo; no es una corrección de consumo de memoria ni una sustitución
necesaria del resolver.

La épica #12 y sus issues se redactaron como brainstorm. Las decisiones de este
ADR se apoyan en el EDA y el código real, no en aquel desglose.

## Decisión

1. Se añade PostgreSQL como capa raw/canonical consultable del ETL MEF, en un
   schema independiente `mef` del clúster previsto.
2. El índice RAM y sus artefactos continúan como camino primario del resolver.
   PostgreSQL no es dependencia de arranque ni de resolución.
3. El ETL produce ambas representaciones en una misma ejecución, con un
   `load_id` común.
4. Las cargas son inmutables y versionadas. Un puntero identifica la activa;
   no se hace swap mediante renombrado de tablas.
5. La fila completa se conserva en raw JSONB. Canonical solo contiene campos
   tipados con consumidor y calidad comprobada.
6. La ejecución semanal la dispara un cron operativo: en el despliegue actual,
   el Programador de tareas de Windows invoca un contenedor one-shot mediante
   un wrapper PowerShell.
7. La indisponibilidad de PostgreSQL no interrumpe el resolver. Sí hace fallar
   una nueva carga completa y deja activa la versión anterior.
8. Retención inicial: carga completa activa y anterior; metadata permanente.
   Se amplía solo después de medir una carga real, backup y restauración.

ADR-002 permanece vigente y no es supersedido.

## Modelo

- `mef.loads`: ciclo de vida, versión y diagnóstico de cada ejecución.
- `mef.source_files`: checksums, esquema y perfil por CSV.
- `mef.raw_rows`: fila íntegra JSONB, sin deduplicar.
- `mef.investments`: proyección canónica por identidad y carga.
- `mef.active_load`: único puntero a la carga publicada.
- Serving en disco: gzip, catálogo, metadata y manifest versionados.

Identidad canónica: CUI cuando existe; SNIP en caso contrario. Raw conserva
`(load_id, source, source_row)` para no ocultar duplicados.

## Publicación y fallo

Filesystem y PostgreSQL no comparten transacción. El pipeline construye
artefactos versionados, carga y valida PostgreSQL, publica el manifest mediante
reemplazo atómico y finalmente actualiza el puntero PG en una transacción
corta. Ambos exponen el `load_id`; un desacuerdo es visible y reanudable.

Una ejecución fallida no toca la carga activa. El resolver conserva su
degradación actual si no puede cargar artefactos. El health check diferencia
base sana, vencida, última carga fallida y desacuerdo de versiones.

## Alternativas descartadas

### Reemplazar RAM por PostgreSQL

No aporta valor al resolver actual, introduce una dependencia de arranque y
elimina una degradación ya probada. La RAM no es una restricción.

### Solo archivos, sin PostgreSQL

Satisface al resolver, pero no permite consultar ni gobernar de forma práctica
las 95 columnas, cargas históricas, perfiles y trazabilidad.

### Una tabla nueva y rename por semana

Complica referencias, permisos y recuperación. Las cargas versionadas con un
puntero hacen explícita la historia y permiten rollback sin DDL operativo.

### Guardar únicamente el último snapshot

Impide comparar drift y rollback. Se mantienen dos cargas completas hasta
obtener mediciones reales de capacidad.

### Scheduler dentro del backend

Añade procesos y coordinación innecesarios al servicio web. El servidor ya
tiene un programador operativo adecuado y Docker para ejecutar el job aislado.

## Consecuencias

Positivas:

- se preserva el corpus completo sin alterar el resolver;
- cada respuesta puede rastrearse a una carga;
- drift, rollback y fallos quedan operables;
- raw admite nuevas necesidades sin volver a descargar un corte perdido.

Costos:

- una carga podría superar ampliamente 1 GB en PostgreSQL contando TOAST e
  índices;
- hay que operar retención, backups, locks y monitoreo;
- la publicación entre disco y PG es coordinada, no estrictamente atómica;
- schema hot e índices requieren benchmark antes de congelarse.

## Validación previa a implementación

- EDA reproducible y contrato por fuente;
- importación desechable de una carga completa en PostgreSQL;
- medición de tabla, TOAST, índices, carga, consultas, backup y restore;
- prueba de rollback y desacuerdo de `load_id`;
- revisión del DDL final.

## Referencias

- `docs/backend/eda_datos_abiertos_mef.md`
- `docs/backend/modulo_etl_mef.md`
- `.ai/decisions/ADR-002-base-local-mef.md`
- `.ai/architecture/database.md`
