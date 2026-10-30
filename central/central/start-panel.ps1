param([switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot
if ($Rebuild -or -not (Test-Path '.\build\web\index.html')) {
    flutter build web --target lib/saad_admin.dart
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar el panel.' }
}
$pythonExe = 'C:\Users\maiqo\AppData\Local\Programs\Python\Python314\python.exe'
Set-Location '.\build\web'
& $pythonExe -m http.server 3000 --bind 127.0.0.1
