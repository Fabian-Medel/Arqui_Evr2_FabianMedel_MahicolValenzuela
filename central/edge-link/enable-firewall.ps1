$ErrorActionPreference = 'Stop'
try {
    $rule = Get-NetFirewallRule -Name 'SAAD-Edge01-mTLS' -ErrorAction SilentlyContinue
    if (-not $rule) {
        New-NetFirewallRule -Name 'SAAD-Edge01-mTLS' -DisplayName 'SAAD edge-01 HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -LocalAddress 172.20.10.6 -RemoteAddress 172.20.10.4 -Profile Any | Out-Null
    }
    Get-NetFirewallRule -Name 'SAAD-Edge01-mTLS' | Select-Object Name,Enabled,Direction,Action | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'firewall-result.json')
    exit 0
} catch {
    $_.Exception.Message | Set-Content (Join-Path $PSScriptRoot 'firewall-error.txt')
    exit 1
}
