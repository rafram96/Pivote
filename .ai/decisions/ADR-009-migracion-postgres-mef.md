# ADR-009 · Migración del índice MEF de memoria a PostgreSQL

- Fecha: 2026-07-23 (iniciado) · Estado: **EN CONSTRUCCIÓN — no implementar todavía**
- Se completará con el desarrollador en sesión dedicada; hasta entonces rige
  ADR-002 (índice en memoria, sin PG obligatorio).

## Contexto

> **Encuadre corregido por el desarrollador (2026-07-28)** — reemplaza la
> premisa original de este ADR. Detalle en `docs/backend/modulo_etl_mef.md` §1.

1. **La RAM NO es la motivación.** Hay memoria de sobra; los ~370-402 MB del
   índice en memoria **no motivan nada** y ningún argumento debe partir de ahí.
2. **La motivación es de CAPACIDAD**: hoy la ingesta descarta ~58 de los 68
   campos del MEF y lo descartado no es recuperable sin re-descargar ~480 MB y
   reprocesar. El cold path JSONB (issue #18) existe para que ningún dato se
   pierda. **PG queda CONFIRMADO como necesario** para eso.
3. **Esto NO es una migración del alcance de ADR-002, es un MÓDULO NUEVO,
   completo y COTIZABLE** (épica #12). ADR-002 cubre lo *mínimo* para que el
   resolver tenga candidatos sin red, y **sigue vigente en su alcance: no se
   reabre ni se supersede**. Son alcances distintos, no posturas enfrentadas —
   lo construido bajo ADR-002 se conserva y el módulo nuevo lo absorbe o
   convive con él.

*Pendiente de documentar en sesión dedicada*: la decisión de convivencia (ver
abajo) y las consecuencias.

## Decisión

Se construye la capa de persistencia PG del módulo ETL (#12).

⚠ **PENDIENTE — no dar por decidido**: si Postgres pasa a dependencia
**obligatoria** del backend, o si convive con el índice en memoria como camino
de lectura rápido. **Como la RAM no es restricción, la convivencia es viable y
probablemente preferible**: preserva la degradación limpia a «InfoObras-solo»
que hoy existe cuando falta la base. La redacción original de este ADR daba por
sentada la obligatoriedad apoyándose en la premisa de recursos, que era falsa.

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
