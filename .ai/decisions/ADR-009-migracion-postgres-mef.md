# ADR-009 · Migración del índice MEF de memoria a PostgreSQL

- Fecha: 2026-07-23 (iniciado) · Estado: **EN CONSTRUCCIÓN — no implementar todavía**
- Se completará con el desarrollador en sesión dedicada; hasta entonces rige
  ADR-002 (índice en memoria, sin PG obligatorio).

## Contexto

*Pendiente de documentar* — por qué el índice en memoria actual
(`sys.intern` + índice invertido, ~370-402 MB, ver `architecture/backend.md`)
ya no es suficiente o qué motiva el cambio (multi-worker, arranque, consultas
concurrentes…). Completar con evidencia, no con proyecciones.

## Decisión

Se migrará a PostgreSQL. Postgres pasa a ser una dependencia **OBLIGATORIA**
del backend, reemplazando el rol actual de `RepositorioConRespaldo`
(hoy opcional / write-through best-effort).

## Puntos pendientes de definir antes de implementar

- [ ] Revisión y ajuste del esquema pg_trgm + FTS propuesto en
      `architecture/database.md` (indicación del desarrollador: el esquema
      actual debe revisarse/ajustarse, NO adoptarse tal cual).
- [ ] Qué pasa si Postgres no está disponible al arrancar: hoy el sistema
      degrada con gracia a «InfoObras-solo» si falta la base MEF; al ser
      obligatorio, definir el nuevo comportamiento de arranque.
- [ ] Plan de migración del índice existente: `actualizar_base_mef.py` hoy
      escribe a CSV/disco — definir si migra directo o hay convivencia
      temporal (memoria + PG).
- [ ] Relación con el deploy en curso: ¿parte del mismo deploy protegido de
      la Fase 1 (`InfoObras/.ai/tasks/active.md`, regla ADR-007) o fase de
      infraestructura POSTERIOR y separada?
- [ ] Qué pasa con la sección «Recomendaciones» de `database.md`: tiempos
      proyectados sin medir, y la paralelización que contradice
      `memory/recurring_patterns.md` (ya advertido inline en el saneo del
      2026-07-23 — solo sería válida contra la BD local, jamás contra
      portales en vivo).

## Opciones consideradas

*Pendiente de documentar cuando se evalúe*: mantener índice en memoria vs
Postgres vs convivencia temporal de ambos.

## Consecuencias

*Pendiente de documentar una vez cerrada la decisión.*

## Referencias

- Propuesta original: `architecture/database.md`, sección «PROPUESTA NO
  IMPLEMENTADA — esquema PostgreSQL (pg_trgm + FTS)».
- **ADR-002** (base local MEF, sin PG) — la decisión que este ADR
  reemplazaría al cerrarse (se supersede, no se edita).
