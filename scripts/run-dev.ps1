[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Run bootstrap-windows.ps1 first.' }
$bridge = Start-Process powershell -PassThru -ArgumentList @('-NoExit','-NoProfile','-Command', "Set-Location '$Root'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services\bridge --host 127.0.0.1 --port 8787 --reload")
try { & npm run dev } finally { Stop-Process -Id $bridge.Id -Force -ErrorAction SilentlyContinue }
