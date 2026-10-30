$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
foreach ($required in @('edge_db.py', 'verify_face.py', 'data\edge.db', 'models\yunet.onnx', 'models\sface.onnx', 'edge-01-connection\connection.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $required))) {
        throw "Falta $required en $projectRoot. Extrae la carpeta saad-edge-kiosk dentro del proyecto del edge."
    }
}
$backupDir = Join-Path $projectRoot ('backups\kiosk-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
$files = @('edge_web.py', 'kiosk\index.html', 'kiosk\style.css', 'kiosk\app.js')
foreach ($file in $files) {
    $destination = Join-Path $projectRoot $file
    if (Test-Path -LiteralPath $destination) {
        $backup = Join-Path $backupDir $file
        New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
        Copy-Item -LiteralPath $destination -Destination $backup
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $file) -Destination $destination
}
Write-Output 'Kiosco instalado. La base de datos, modelos, certificados y API anterior se conservaron.'
Write-Output 'Inicia con: .\.venv\Scripts\python.exe .\edge_web.py'
