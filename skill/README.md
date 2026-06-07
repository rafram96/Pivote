# Pieza 1 · Skill `analizar-licitacion-osce`

Código de la skill de Claude Code / Cowork que corre en la **PC del ingeniero**.

> 🚧 Placeholder — el código aún no se escribe. Diseño en
> [`docs/skill/skill_design.md`](../docs/skill/skill_design.md).

Orquesta 3 subagentes (`agent-bases`, `agent-propuesta`, `agent-evaluador`),
consolida y emite **Excel + JSON espejo** (contrato en
[`docs/contrato/`](../docs/contrato/)).

En despliegue, el contenido de esta carpeta se copia/symlinkea a
`~/.claude/skills/analizar-licitacion-osce/` en la máquina del cliente.
