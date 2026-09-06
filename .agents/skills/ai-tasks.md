---
description: Derivar tareas TSK ejecutables y trazables desde el plan de una spec — sin empezar a implementar
argument-hint: SPC-xxx
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-tasks — del plan al trabajo

Entrada del usuario: $ARGUMENTS (debe ser un ID `SPC-xxx`)

Este comando **termina antes de la primera línea de código**. Deriva el
trabajo; no lo ejecuta.

## Precondición

Lee `.ai/specs/SPC-xxx_*.md` completa. Si `status` no es `planned`, detente y
recomienda el paso que falta (`/ai-clarify` o `/ai-plan`). Revisa también
`.ai/tasks/INDEX.md` para no duplicar tareas existentes.

## Paso 1 — Derivar las tareas

Recorre el plan componente por componente y los requisitos FR-xx de la spec, y
deriva tareas con estas propiedades:

- **Pequeña**: completable en una sesión de trabajo. Si no cabe, pártela.
- **Verificable**: su checklist se puede marcar con evidencia concreta (un test
  que pasa, un comando que corre, un archivo que existe con X contenido).
- **Trazable**: cada tarea nace de un FR o de un componente del plan, y lo dice.
- **Ordenada**: si depende de otra tarea, lo declara.

Orden recomendado de derivación: contratos/modelos primero, luego pruebas de
esos contratos, luego implementación, al final integración y pulido.

## Paso 2 — Crear cada tarea

Usa `raf-ai new task "<título>"` (el tipo `task` ya existe en la CLI) y
completa el archivo generado:

- Frontmatter: completa `spec_ref: "SPC-xxx"`, `depends_on: []` y
  `parallelizable: true|false`; ajusta `priority` y `updated`.
- `## Objetivo`: el resultado verificable, en una frase.
- `## Checklist`: pasos concretos y verificables (3-7 ítems).
- Al final del cuerpo agrega la referencia de origen:
  - `Origen: FR-03 / componente <nombre del plan>`
- El cuerpo puede repetir `Paralelizable:` y `Depende de:` para lectura humana,
  pero el frontmatter es la fuente de verdad desde schema v2.

## Paso 3 — Conectar la spec

Agrega al final de la spec (antes de `## Plan` o al final del documento):

```markdown
## Tareas derivadas

| Orden | ID | Título | Paralelizable |
|---|---|---|---|
```

La spec queda en `status: "planned"` (pasará a `done` cuando sus tareas cierren).

## Reglas

- Toda tarea trazable: si no puedes escribir su línea `Origen:`, la tarea no
  nace del plan — o sobra la tarea o le falta detalle al plan (dilo).
- Cobertura completa: al terminar, verifica que cada FR de la spec tenga al
  menos una tarea. Si un FR quedó sin tarea, o lo cubres o explicas por qué no.
- No infles: nada de tareas "configurar entorno" o "revisar código" genéricas;
  solo trabajo que produce un cambio verificable.
- No implementes nada, ni "de paso".

## Cierre

1. `raf-ai index` y `raf-ai validate` — aquí sí deben pasar limpio (las tasks
   son un tipo soportado). Corrige lo que reporten.
2. Actualiza `.ai/handoffs/current.md`: estado ("SPC-xxx con N tareas
   derivadas") y siguiente paso (la primera tarea del orden).
3. Reporta al usuario la tabla de tareas (orden, ID, título, paralelizable) y
   con cuál empezar.
