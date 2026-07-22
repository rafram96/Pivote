# .ai — Base de conocimiento del proyecto

**Única fuente de verdad de contexto** para cualquier agente (Claude Code, Gemini
CLI, Codex, etc.) o desarrollador nuevo. No asumas que existe ninguna conversación
previa: todo lo importante está (o debe estar) aquí.

## Cómo usar esta carpeta

1. **Empieza por [`handoffs/current.md`](handoffs/current.md)** — qué se estaba
   haciendo, qué falta, siguiente paso.
2. [`context/current_state.md`](context/current_state.md) — estado real del proyecto.
3. [`architecture/overview.md`](architecture/overview.md) — cómo está construido.
4. [`decisions/`](decisions/) — por qué es así (ADRs; nunca se editan, se superseden).
5. [`conventions/`](conventions/) y [`memory/`](memory/) — antes de escribir código.

## Reglas de mantenimiento (obligatorias para todo agente)

- Al terminar cualquier tarea importante: actualizar `context/current_state.md`
  y `handoffs/current.md` **sin que el usuario lo pida**.
- Decisión arquitectónica nueva → ADR nuevo (nunca modificar uno histórico).
- Cambio de arquitectura → actualizar `architecture/`.
- Aprendizaje reusable → `memory/`. Convención nueva → `conventions/`.
- No inventar: lo no verificado se marca **"Pendiente de documentar."**
- No duplicar contenido entre archivos; mantenerlos pequeños y especializados.
- Esta carpeta es parte del código: se versiona y se commitea con los cambios.

## Idioma

Todo en **español** (convención dura del proyecto: código, docs, commits).
