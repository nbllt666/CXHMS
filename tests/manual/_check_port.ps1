$r = Test-NetConnection -ComputerName 127.0.0.1 -Port 8001 -WarningAction SilentlyContinue
Write-Host ("Port 8001 open: " + $r.TcpTestSucceeded)
