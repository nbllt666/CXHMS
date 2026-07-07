$p = Get-Process -Id 23820 -ErrorAction SilentlyContinue
if ($p) {
    Write-Host "Process 23820 exists: $($p.ProcessName)"
} else {
    Write-Host "Process 23820 does not exist"
}
