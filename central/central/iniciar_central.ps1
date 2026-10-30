# Inicia la central completa: PostgreSQL, API central, API sync, proxy mTLS (8443) y panel de administracion.
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\central\iniciar_central.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
docker compose -f compose.yaml -f compose.edge.yaml up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no pudo iniciar. Compruebe Docker Desktop.' }
$panel = Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
if (-not $panel) {
    Start-Process powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'start-panel.ps1') -WindowStyle Minimized
    Start-Sleep -Seconds 2
}
Start-Process 'http://localhost:3000'
