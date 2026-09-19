[CmdletBinding()]
param(
    [int]$Port = 8787,
    [switch]$Public,
    [string]$LogFile = ''
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "Virtual environment is missing. Run scripts\bootstrap-windows.ps1 first." }
if (-not (Test-Path (Join-Path $Root '.env'))) { throw ".env is missing. Run scripts\bootstrap-windows.ps1 first." }
$HostAddress = if ($Public) { '0.0.0.0' } else { '127.0.0.1' }
$LogDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not $LogFile) { $LogFile = Join-Path $LogDir 'bridge.log' }
if ((Test-Path $LogFile) -and (Get-Item $LogFile).Length -gt 10MB) {
    Move-Item $LogFile "$LogFile.$(Get-Date -Format yyyyMMdd-HHmmss).old" -Force
}
"[$(Get-Date -Format o)] Starting Hermes Companion on $HostAddress`:$Port" | Out-File -FilePath $LogFile -Append -Encoding utf8
# Launch through a generated .cmd file. PowerShell's `*>>` operator on a native process
# fails when this script runs hidden from Task Scheduler (no console handle: uvicorn exits
# 1 and writes nothing), and passing a quoted command line to `cmd /c` gets mangled by
# Start-Process. A .cmd file avoids both: cmd appends stdout+stderr to the single log.
$Runner = Join-Path $Root 'logs\start-bridge.cmd'
$RunnerBody = @"
@echo off
cd /d "$Root"
"$Python" -m uvicorn app.main:app --app-dir "$Root\services\bridge" --host $HostAddress --port $Port --proxy-headers --forwarded-allow-ips 127.0.0.1 >> "$LogFile" 2>&1
"@
Set-Content -Path $Runner -Value $RunnerBody -Encoding ASCII -Force
$Process = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', $Runner -WorkingDirectory $Root -WindowStyle Hidden -PassThru
$Process.WaitForExit()
exit $Process.ExitCode
