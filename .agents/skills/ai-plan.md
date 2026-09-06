---
description: Traducir una spec clarificada a plan técnico, verificado contra la constitución antes de escribirse
argument-hint: SPC-xxx [pistas de stack o restricciones técnicas]
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-plan — ¿cómo?

Entrada del usuario: $ARGUMENTS (un ID `SPC-xxx`, opcionalmente seguido de
pistas técnicas del usuario: stack preferido, restricciones, integraciones)

Aquí sí se habla de tecnología — pero **cada decisión lleva su porqué y la
alternativa que descartaste**. Un plan sin justificaciones es una opinión.

## Precondición

Lee `.ai/specs/SPC-xxx_*.md` completa.

- Si tiene marcadores `[NEEDS CLARIFICATION]`: detente y recomienda
  `/ai-clarify SPC-xxx`. No planifiques sobre ambigüedades.
- Si está en `draft` sin marcadores: puedes continuar, pero dilo explícitamente.
- Si tiene `research_ref`: lee esa INV — sus limitaciones y alternativas son
  restricciones del plan.

## Paso 1 — Gate constitucional (ANTES de diseñar)

1. Lee `.ai/constitution.md` si existe; si el manifiesto declara un proyecto
   padre, lee también la constitución del sistema padre. Lee `.ai/conventions/`
   si existe (coding, git, naming).
2. Enumera los principios aplicables a esta feature.
3. Contrasta el enfoque que tienes en mente contra cada uno **antes de
   escribirlo**. Si algo lo viola: o corriges el enfoque, o la desviación va a
   `### Complejidad justificada` con su porqué. No hay tercera opción
   silenciosa.

## Paso 2 — Escribir el plan

Completa la sección `## Plan` de la spec (reemplaza el "Pendiente"):

```markdown
## Plan

### Verificación constitucional

| Principio | Cumple | Nota |
|---|---|---|

### Enfoque y arquitectura

(componentes, responsabilidades, flujo de datos — con el porqué de cada
decisión y la alternativa descartada)

### Stack

(tecnologías concretas y por qué estas; qué pistas dio el usuario)

### Modelo de datos            ← solo si la feature maneja datos propios

### Integraciones y contratos  ← solo si habla con sistemas externos

### Riesgos técnicos

(qué puede salir mal y la señal temprana de cada riesgo)

### Complejidad justificada    ← solo si hubo desviaciones del gate
```

Reglas de diseño:

- **Preferir lo simple**: no agregues capas, abstracciones ni generalidad que
  la spec no pide. Usa los frameworks directamente; la abstracción se gana con
  la segunda necesidad real, no con la primera imaginada.
- Las subsecciones marcadas "solo si" se omiten cuando no aplican — un plan
  corto y denso vale más que uno largo y hueco.
- El plan debe ser lo bastante concreto para que `/ai-tasks` derive tareas
  mecánicamente: si una parte no se puede convertir en tareas, le falta detalle.
- Sin código de producto — pseudocódigo o contratos de interfaz como máximo.

## Paso 3 — Decisiones duraderas → ADR

Si tomaste una decisión con alternativas reales y consecuencias que vivirán más
que esta feature (elección de stack, patrón de integración, formato de datos),
créala como ADR con `raf-ai new decision "<título>"`, completa contexto /
alternativas / decisión / consecuencias, y referencia su ID desde el plan.

## Paso 4 — Estado

`status: "planned"` y `updated` al día de hoy.

## Cierre

1. `raf-ai index` y `raf-ai validate`; deben pasar (los warnings se reportan, los errores se corrigen).
2. Actualiza `.ai/handoffs/current.md`: estado y siguiente paso.
3. Resume al usuario: enfoque elegido en 3-5 líneas, decisiones clave con su
   porqué, ADRs creados, y recomienda `/ai-tasks SPC-xxx`.
