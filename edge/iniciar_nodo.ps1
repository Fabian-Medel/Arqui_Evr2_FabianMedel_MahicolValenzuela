# Inicia el nodo completo: adaptador del actuador, API de acceso y pantalla del kiosco.
# Si ya estaba abierto, lo reinicia.
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_nodo.ps1            maqueta sin hardware
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_nodo.ps1 -Arduino   con el Arduino conectado por USB
param([switch]$Arduino)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Get-Process saad_edge -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'edge_service\.py|edge_api\.py|actuator\\app\.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$actuador = if ($Arduino) { '.\actuator\app.py' } else { '.\actuator\app.py --simular' }
Start-Process $python -ArgumentList $actuador -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
Start-Process $python -ArgumentList '.\edge_service.py' -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
Start-Sleep -Seconds 2
Start-Process (Join-Path $PSScriptRoot 'app\saad_edge.exe') -WorkingDirectory (Join-Path $PSScriptRoot 'app')
