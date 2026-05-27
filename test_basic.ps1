$server = "http://192.168.31.182:5000"
$vncPort = 5900
$vncPass = "balongma2026"
$hostname = $env:COMPUTERNAME
$ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '192.*' }
if ($ips) { $ip = $ips[0].IPAddress } else { $ip = '127.0.0.1' }
Write-Host "Hostname: $hostname"
Write-Host "IP Address: $ip"
$body = @{hostname=$hostname;os_type='windows';ip_address=$ip;vnc_port=$vncPort;vnc_password=$vncPass} | ConvertTo-Json
Write-Host "JSON: $body"