# Workflow de conocimiento

## Arranque

1. Leer `manifest.md`.
2. Leer `handoffs/current.md`.
3. Consultar `context/current_state.md` y la arquitectura afectada.
4. Revisar tareas y ADR relacionados antes de cambiar código.

## Durante el trabajo

- Crear IDs exclusivamente con `raf-ai new`.
- Registrar como ADR una elección duradera con alternativas reales.
- Registrar como tarea el trabajo ejecutable que deja de importar al completarse.
- Actualizar primero la documentación cuando cambie una decisión de arquitectura.

## Cierre

1. Actualizar `context/current_state.md`.
2. Actualizar `handoffs/current.md` con estado, evidencia y siguiente paso.
3. Ejecutar `raf-ai index` y `raf-ai validate`.
4. Confirmar que no hay secretos, duplicación ni enlaces rotos evidentes.
