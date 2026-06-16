# Ensambla el plugin `infoobras-pivote` copiando la skill y el MCP del repo a la
# estructura que Claude Code/Cowork espera. Re-córrelo cuando edites la skill o
# el MCP para re-sincronizar. Las carpetas copiadas (skills/, mcp-server/) son
# build output (gitignoreadas); lo versionado es el manifiesto + este script.
$ErrorActionPreference = "Stop"
$plugin = $PSScriptRoot
$repo   = Split-Path $plugin -Parent

function Copiar($src, $dst) {
  if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
  robocopy "$src" "$dst" /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
  if ($LASTEXITCODE -le 7) { $global:LASTEXITCODE = 0 } else { throw "robocopy falló ($LASTEXITCODE) copiando $src" }
}

Write-Host "→ skill   → skills/analizar-licitacion-osce"
Copiar "$repo\skill"      "$plugin\skills\analizar-licitacion-osce"
Write-Host "→ MCP     → mcp-server"
Copiar "$repo\mcp-server" "$plugin\mcp-server"

# Sanidad
$ok = (Test-Path "$plugin\skills\analizar-licitacion-osce\SKILL.md") `
  -and (Test-Path "$plugin\mcp-server\mcp.js") `
  -and (Test-Path "$plugin\mcp-server\node_modules") `
  -and (Test-Path "$plugin\.claude-plugin\plugin.json")
if ($ok) { Write-Host "✅ plugin ensamblado en $plugin" }
else     { throw "❌ faltan piezas tras ensamblar" }
