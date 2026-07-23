# Formato de tarea estructurada (tasks/)

Aplica a **toda entrada nueva** en `tasks/backlog.md` (y `active`/`in_progress`
cuando una tarea pasa a ejecución) desde 2026-07-23. Objetivo: que el
planificador (Fable) pueda leer el backlog sin interpretar prosa libre y que
cada agente conozca su zona antes de tocar código. Las entradas viejas NO se
migran de golpe — solo si se van a tocar de todos modos.

## Estructura por tarea

Bloque YAML + descripción libre corta debajo:

```yaml
---
id: T-SONDEO-001
tipo: sondeo | tarea | refactor
zona: resolucion/ | scraping/ | orquestador/ | persistencia/ | otro
agente_origen: agente-a | agente-b | fable | opus | desarrollador
estado: pendiente | en_progreso | esperando_aprobacion | aprobado | completado
depende_de: []
---
```

Descripción: qué es, por qué importa; si es hallazgo de sondeo, qué se
investigó y qué se encontró (archivo y función/línea si aplica).

## Campos

- **id**: único, prefijo por tipo (`T-SONDEO-`, `T-TAREA-`, `T-REFACTOR-`),
  consecutivo.
- **tipo**:
  - `sondeo` — hallazgo de investigación; NO implica trabajo. Fable lo evalúa.
  - `tarea` — ejecución directa sin decisión arquitectónica detrás (aplica la
    prueba de 3 preguntas: `InfoObras/.ai/constitution.md`, Artículo 4).
  - `refactor` — toca arquitectura; **solo Fable puede crearlas**, y solo tras
    aprobación del desarrollador.
- **zona**: carpeta/módulo. Evita que dos agentes de sondeo se pisen y define
  a qué worktree se asigna el trabajo.
- **agente_origen**: trazabilidad — si algo se contradice después, se sabe de
  dónde vino cada afirmación.
- **estado**: `esperando_aprobacion` es el estado con el que Fable presenta un
  plan; **nadie avanza una tarea a `aprobado` salvo el desarrollador** (o
  Fable citando su aprobación explícita).
- **depende_de**: ids de los que depende; `[]` si es independiente.

## Regla de escritura durante sondeo

Los agentes de sondeo solo crean entradas `tipo: sondeo`, nunca `refactor`.
Si un sondeo cree que algo amerita refactor, lo documenta como hallazgo y
Fable decide — el sondeo nunca decide por sí mismo que algo se refactoriza.
