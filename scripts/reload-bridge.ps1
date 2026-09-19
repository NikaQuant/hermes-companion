# Rebuild the PWA and restart the bridge so the new build is actually served.
# Stop-ScheduledTask alone leaves the uvicorn child alive on 8787, so kill it by PID.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
& .\.venv\Scripts\python.exe .\scripts\build-web.py | Select-Object -First 1

function Get-ListenerPid([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn -and $conn.OwningProcess) { return [int]$conn.OwningProcess }
    $line = netstat -ano | Select-String ":$Port\s" | Select-String 'LISTENING' | Select-Object -First 1
    if ($line) {
        $parts = ($line.ToString().Trim() -split '\s+')
        return [int]$parts[-1]
    }
    return $null
}

$pid8787 = Get-ListenerPid 8787
if ($pid8787) {
    Stop-Process -Id $pid8787 -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}
Start-ScheduledTask -TaskName 'Hermes Companion Bridge'
$deadline = (Get-Date).AddSeconds(40)
$health = $null
do {
    Start-Sleep -Seconds 1
    try { $health = Invoke-RestMethod http://127.0.0.1:8787/api/health -TimeoutSec 2 } catch { $health = $null }
} while (-not $health -and (Get-Date) -lt $deadline)
if (-not $health) { throw 'bridge did not come back on 8787' }
$html = (Invoke-WebRequest http://127.0.0.1:8787/ -UseBasicParsing).Content
$match = [regex]::Match($html, 'assets/app\.[a-f0-9]+\.js')
if (-not $match.Success) { throw 'served index did not reference a hashed app.js bundle' }
Write-Host "bridge ok, serving $($match.Value)" -ForegroundColor Green
