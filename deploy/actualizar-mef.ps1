[CmdletBinding()]
param(
    [string]$LogDirectory = "$env:ProgramData\InfoObras\logs"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$compose = Join-Path $PSScriptRoot "docker-compose.yml"
$lockPath = Join-Path ([System.IO.Path]::GetTempPath()) "infoobras-mef-etl.lock"
$lock = $null

try {
    $lock = [System.IO.File]::Open(
        $lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch [System.IO.IOException] {
    Write-Error "Ya existe una actualización MEF en ejecución."
    exit 75
}

try {
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $log = Join-Path $LogDirectory "actualizar-mef-$stamp.log"
    Set-Location -LiteralPath $repoRoot

    & docker compose -f $compose run --rm --no-deps backend `
        python scripts/actualizar_base_mef.py *> $log
    $code = $LASTEXITCODE

    Get-Content -LiteralPath $log
    if ($code -ne 0) {
        Write-Error "El ETL MEF falló con código $code. Log: $log"
        exit $code
    }
    Write-Output "ETL MEF completado. Log: $log"
} finally {
    if ($null -ne $lock) {
        $lock.Dispose()
    }
}
