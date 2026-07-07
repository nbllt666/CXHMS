$lines = Get-Content 'c:\CXHMS\logs\app.log' -Tail 80
$lines | Where-Object { $_ -match 'stream_chat|tool_call|finish_reason' } | Select-Object -Last 15
