 = " http://192.168.31.182:5000\
 = 5900
 = \balongma2026\
 = JICHENGTEST
 = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { .IPAddress -like \192.*\ }
if () { = [0].IPAddress } else { = \127.0.0.1\ }
Write-Host \Hostname: \
Write-Host \IP Address: \
 = @{hostname=;os_type=\windows\;ip_address=;vnc_port=;vnc_password=} | ConvertTo-Json
Write-Host \JSON: \
