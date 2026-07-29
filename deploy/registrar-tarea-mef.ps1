[CmdletBinding()]
param(
    [string]$TaskName = "InfoObras - Actualizar base MEF",
    [string]$At = "03:00"
)

$ErrorActionPreference = "Stop"
$wrapper = Join-Path $PSScriptRoot "actualizar-mef.ps1"
if (-not (Test-Path -LiteralPath $wrapper)) {
    throw "No se encontró el wrapper: $wrapper"
}

$hora = [DateTime]::ParseExact($At, "HH:mm", $null)
$accion = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`""
$trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 `
    -DaysOfWeek Sunday -At $hora
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME `
    -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $accion `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Actualiza semanalmente los artefactos locales MEF de InfoObras." `
    -Force

Write-Output "Tarea registrada: $TaskName (domingos $At)."
Write-Output "Ejecute una prueba manual desde el Programador de tareas antes de habilitarla."
