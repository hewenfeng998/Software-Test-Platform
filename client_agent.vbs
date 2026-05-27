Set objHTTP = CreateObject("MSXML2.XMLHTTP")
Set objWMIService = GetObject("winmgmts:{impersonationLevel=impersonate}!\\.\root\cimv2")

serverUrl = "http://192.168.31.182:5000"
vncPort = 5900
vncPassword = "balongma2026"

Set colItems = objWMIService.ExecQuery("Select * from Win32_ComputerSystem")
For Each objItem in colItems
    hostname = objItem.Name
Next

Set colIPConfig = objWMIService.ExecQuery("Select * from Win32_NetworkAdapterConfiguration Where IPEnabled=True")
ipAddress = "127.0.0.1"
For Each objIP in colIPConfig
    If Not IsNull(objIP.IPAddress) Then
        ipAddress = objIP.IPAddress(0)
        Exit For
    End If
Next

WScript.Echo "Hostname: " & hostname
WScript.Echo "IP Address: " & ipAddress
WScript.Echo ""
WScript.Echo "Registering..."

jsonStart = "{""hostname"":"""
jsonHost = hostname
jsonMid1 = """,""os_type"":""windows"",""ip_address"":"""
jsonIP = ipAddress
jsonMid2 = """,""vnc_port"":"
jsonPort = CStr(vncPort)
jsonMid3 = ",""vnc_password"":"""
jsonPass = vncPassword
jsonEnd = """}"

jsonBody = jsonStart & jsonHost & jsonMid1 & jsonIP & jsonMid2 & jsonPort & jsonMid3 & jsonPass & jsonEnd

On Error Resume Next
objHTTP.Open "POST", serverUrl & "/balongma/register", False
objHTTP.setRequestHeader "Content-Type", "application/json"
objHTTP.send(jsonBody)

If Err.Number <> 0 Then
    WScript.Echo "ERROR: Registration failed!"
    WScript.Echo "Error: " & Err.Description
    WScript.Quit(1)
End If

responseText = objHTTP.responseText

Set regex = New RegExp
regex.Pattern = """machine_id"":(\d+)"
Set matches = regex.Execute(responseText)
If matches.Count > 0 Then
    machineId = matches(0).SubMatches(0)
    
    WScript.Echo "=========================================="
    WScript.Echo "Registration successful!"
    WScript.Echo "Machine ID: " & machineId
    WScript.Echo "=========================================="
    WScript.Echo "Waiting for remote control..."
    WScript.Echo ""
    
    Do While True
        On Error Resume Next
        Set objHTTP2 = CreateObject("MSXML2.XMLHTTP")
        objHTTP2.Open "POST", serverUrl & "/balongma/heartbeat/" & machineId, False
        objHTTP2.send
        Err.Clear
        
        WScript.Sleep 5000
    Loop
Else
    WScript.Echo "ERROR: Failed to get machine ID!"
    WScript.Echo "Response: " & responseText
    WScript.Quit(1)
End If