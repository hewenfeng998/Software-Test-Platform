$ErrorActionPreference = 'SilentlyContinue'

$server = "http://192.168.31.182:5000"

$hostname = $env:COMPUTERNAME
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' }
if ($ips) {
    $ip = $ips[0].IPAddress
} else {
    $ip = '127.0.0.1'
}

Write-Host ""
Write-Host "================================================"
Write-Host "     Balongma Automation Test Agent"
Write-Host "================================================"
Write-Host ""
Write-Host "Hostname: $hostname"
Write-Host "IP Address: $ip"
Write-Host ""
Write-Host "================================================"
Write-Host "Registering with server..."
Write-Host "================================================"

$body = @{
    hostname = $hostname
    os_type = 'windows'
    ip_address = $ip
} | ConvertTo-Json

try {
    $resp = Invoke-RestMethod -Uri "$server/balongma/register" -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 30
    
    Write-Host ""
    Write-Host "================================================"
    Write-Host "Registration successful!"
    Write-Host "Machine ID: $($resp.machine_id)"
    Write-Host "================================================"
    Write-Host "Remote control ready!"
    Write-Host ""
    Write-Host "Waiting for remote control sessions..."
    Write-Host "Press Ctrl+C to exit"
    Write-Host ""
    
    while ($true) {
        try {
            Invoke-RestMethod -Uri "$server/balongma/heartbeat/$($resp.machine_id)" -Method Post -TimeoutSec 5 | Out-Null
        } catch {}
        Start-Sleep -Seconds 5
    }
} catch {
    Write-Host ""
    Write-Host "ERROR: Registration failed!"
    Write-Host "Error Details: $_"
    Read-Host "Press Enter to exit"
}