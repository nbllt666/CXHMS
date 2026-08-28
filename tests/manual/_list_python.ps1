Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, ParentProcessId, CommandLine | Format-List
