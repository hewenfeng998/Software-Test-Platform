$hostname = $args[0]
$ipAddress = $args[1]
$serverUrl = $args[2]

Write-Host "Hostname: $hostname"
Write-Host "IP Address: $ipAddress"
Write-Host "Server: $serverUrl"

$body = @{
    hostname = $hostname
    os_type = "windows"
    ip_address = $ipAddress
    vnc_port = 5900
    vnc_password = "balongma2026"
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "$serverUrl/balongma/register" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30
    Write-Output $response.machine_id | Out-File -FilePath "temp_id.txt" -Encoding utf8
    Write-Host "Registered successfully"
} catch {
    Write-Error "Failed: $_"
}