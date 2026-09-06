---
description: Ejecutar tareas TSK de una spec con evidencia, validate y commit por checkpoint — sin inventar alcance
argument-hint: TSK-xxx (una tarea) | SPC-xxx (todas las pendientes en orden)
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-implement — ejecutar con barandas

Entrada del usuario: $ARGUMENTS

Este comando implementa trabajo ya especificado. **El alcance lo define el
checklist de cada tarea, no tu criterio**: si descubres trabajo nuevo, se
registra como tarea nueva — no se hace "de paso".

## Contexto previo (leer antes de actuar)

1. `.ai/WORKFLOW.md`, `.ai/conventions/` (coding, git, naming) y
   `.ai/handoffs/current.md`.
2. La spec de referencia completa (incluido su `## Plan`) y los ADR vinculados.
3. `.ai/tasks/INDEX.md` para el estado global.

## Selección de tareas

- Entrada `TSK-xxx`: solo esa tarea.
- Entrada `SPC-xxx`: todas sus tareas `pending` en orden, respetando
  `Depende de:` (una tarea no arranca si una dependencia no está `completed`).

Antes de ejecutar cada tarea, verifica que sea ejecutable por un agente:

- `assignee` humano (p. ej. "Raf") o pasos que exigen acciones humanas
  (entrar a un portal con credenciales, llamar a alguien, decidir producto):
  **no la ejecutes**. Márcala como saltada en el reporte con el motivo y, si
  bloquea a las demás, detente ahí y dilo.
- `status: blocked`: sáltala y reporta el bloqueo.

## Por cada tarea

1. `status: "in_progress"` y `updated` al día.
2. Implementa siguiendo `conventions/` y el plan de la spec. Sin desvíos
   silenciosos: si el plan no encaja con la realidad, detén la tarea, anota el
   hallazgo en la tarea y repórtalo — no improvises arquitectura.
3. Marca cada ítem del checklist **solo con evidencia real**: el comando
   ejecutado y su salida, el test que pasa, el archivo que existe. La evidencia
   va en `## Evidencia de cierre` (comandos + resultados resumidos).
4. Verificación antes de cerrar:
   - Corre los tests/checks del proyecto si existen (los define `conventions/`
     o el README del repo).
   - `raf-ai validate` — errores se corrigen, warnings se reportan.
5. `status: "completed"`, `updated` al día.
6. **Commit por tarea** (checkpoint): mensaje convencional que referencia el
   ID, p. ej. `feat(sire): cliente RVIE con fixtures (TSK-005)`. Nada de
   acumular cinco tareas en un commit.
7. Si un paso falla dos veces por la misma causa: `status: "blocked"`, anota
   la causa y la última evidencia en `## Bloqueos`, commit de lo que haya
   avanzado si es coherente, y continúa con la siguiente tarea que no dependa
   de esta.

## Reglas duras

- **Secretos**: jamás en el repo ni en `.ai/` — ni en evidencia, ni en
  fixtures, ni en logs commiteados. Tokens y credenciales van al almacén que
  defina el plan (SO/keychain/env local).
- **Sin alcance nuevo**: features no pedidas, refactors "ya que estoy" y
  dependencias no contempladas en el plan requieren o una tarea nueva
  (`raf-ai new task`) o un ADR — no aparecen solas.
- **Nunca `completed` sin evidencia.** Un checklist marcado sin evidencia es
  peor que uno pendiente.

## Cierre de la sesión

1. Actualiza `.ai/context/current_state.md` si cambió algo estructural.
2. Actualiza `.ai/handoffs/current.md`: estado, última evidencia, siguiente
   paso concreto (la próxima tarea del orden).
3. `raf-ai index` y `raf-ai validate` en verde.
4. Reporta: tabla de tareas (completadas / bloqueadas / saltadas y por qué),
   evidencia clave, y qué sigue.
