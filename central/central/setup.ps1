$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.env')) {
    function New-Secret {
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($bytes)
        $rng.Dispose()
        return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
    }
    @("DB_PASSWORD=$(New-Secret)", "JWT_SECRET=$(New-Secret)", "ADMIN_PASSWORD=$(New-Secret)") | Set-Content '.env' -Encoding ascii
}
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose no pudo iniciar. Compruebe Docker Desktop.' }
