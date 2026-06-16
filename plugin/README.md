# Plugin `infoobras-pivote` (skill + MCP para Cowork / Claude Desktop)

Empaqueta la skill **analizar-licitacion-osce** y el MCP **infoobras-onprem-bridge**
como un solo plugin instalable, porque **Cowork no lee `~/.claude/skills/`** (eso es
solo del CLI de Claude Code) — Cowork carga skills vía **plugins**.

## Estructura (formato oficial de plugins de Claude Code)
```
plugin/
├── .claude-plugin/plugin.json          ← manifiesto (name, version, …)   [versionado]
├── .mcp.json                            ← declara el MCP (usa ${CLAUDE_PLUGIN_ROOT}) [versionado]
├── build.ps1                            ← ensambla skill + MCP            [versionado]
├── skills/analizar-licitacion-osce/     ← copia de ../skill/             [build output]
└── mcp-server/                          ← copia de ../mcp-server/        [build output]
```
La skill queda namespaced: se invoca **`/infoobras-pivote:analizar-licitacion-osce`**.

## 1) Ensamblar (re-correr tras editar skill o MCP)
```powershell
pwsh plugin\build.ps1
```

## 2) Probar en Claude Code (CLI) sin instalar
```powershell
claude --plugin-dir .\plugin
# luego:  /infoobras-pivote:analizar-licitacion-osce bases.pdf propuesta.pdf
```

## 3) Usar en Cowork / Claude Desktop
> ⚠ El paso exacto de la UI de Cowork no está 100% confirmado (varía por versión).
> La vía general: Claude Desktop → **Customize / Extensions** → instalar plugin desde
> carpeta local (apuntar a esta carpeta `plugin/`), o empaquetarla en `.zip` y usar
> `--plugin-url` / la importación de la UI. Si tu Cowork no ofrece "instalar desde
> carpeta", se distribuye vía un **marketplace** (ver docs de Claude Code › plugins).

El MCP requiere el **backend corriendo** en `http://127.0.0.1:8001` (ver
`docs/backend/pruebas_e2e.html`). El `.mcp.json` ya apunta ahí.
