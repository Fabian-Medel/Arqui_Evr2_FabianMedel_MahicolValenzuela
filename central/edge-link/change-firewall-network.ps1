$ErrorActionPreference = 'Stop'
try {
    $rule = Get-NetFirewallRule -Name 'SAAD-Edge01-mTLS' -ErrorAction SilentlyContinue
    if ($rule) {
        $rule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -LocalAddress 192.168.1.23 -RemoteAddress 192.168.1.24
    } else {
        New-NetFirewallRule -Name 'SAAD-Edge01-mTLS' -DisplayName 'SAAD edge-01 HTTPS' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -LocalAddress 192.168.1.23 -RemoteAddress 192.168.1.24 -Profile Any | Out-Null
    }
    Get-NetFirewallRule -Name 'SAAD-Edge01-mTLS' | Get-NetFirewallAddressFilter | Select-Object LocalAddress,RemoteAddress | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot 'network-firewall-result.json')
    exit 0
} catch {
    $_.Exception.Message | Set-Content (Join-Path $PSScriptRoot 'network-firewall-error.txt')
    exit 1
}
