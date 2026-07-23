# Agentes: empezar aquí

Base de conocimiento de este repo: **`.ai/`** — arranca por
`.ai/handoffs/current.md` y sigue `.ai/README.md`. Es la única fuente de
verdad de contexto; no asumas conversaciones previas.

Si el checkout incluye el nivel superior (`../.ai/` en la carpeta
`InfoObras/`), empieza por `../.ai/manifest.md` (vista de sistema: topología,
tareas cross-repo, panel). Este repo es autosuficiente si se clonó solo.

Reglas duras: español en todo; el backend jamás llama APIs cloud de IA; datos
del cliente jamás al repo; cambios al resolver exigen pytest + golden
(`.ai/handoffs/current.md`, «Regla de oro»); `git add` con rutas explícitas.

(El `CLAUDE.md` de `.claude/` está gitignored — este archivo es la entrada
versionada para cualquier agente.)
