# Deja la central limpia antes de grabar: borra eventos, estados de apertura y auditoria.
# Conserva el usuario admin y los nodos. Con -Todo borra tambien estudiantes, permisos y enrolamientos.
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\central\limpiar_para_demo.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\central\limpiar_para_demo.ps1 -Todo
param([switch]$Todo)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$alcance = if ($Todo) { 'eventos, auditoria, estudiantes, permisos y enrolamientos' } else { 'eventos y auditoria' }
if ((Read-Host "Se borraran: $alcance. Escribe BORRAR para continuar") -cne 'BORRAR') {
    Write-Output 'Cancelado. No se borro nada.'
    return
}
$sql = 'DELETE FROM actuations; DELETE FROM events; DELETE FROM audit;'
if ($Todo) {
    # La nueva version de politica hace que los nodos eliminen tambien los rostros de estos estudiantes.
    $sql += " DELETE FROM enrollments; DELETE FROM permissions; DELETE FROM students; INSERT INTO policy_changes(actor,kind,target) VALUES ('admin','reset','demo');"
}
docker compose exec -T db psql -U saad -d saad -c $sql
if ($LASTEXITCODE -ne 0) { throw 'No se pudo limpiar la base. Compruebe que la central este iniciada.' }
Write-Output 'Central limpia.'
