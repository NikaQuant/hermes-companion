[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is required.' }
& python .\scripts\build-web.py
Push-Location (Join-Path $Root 'apps\windows')
try {
    & npm install
    & npm run build
} finally { Pop-Location }
$bundle = Join-Path $Root 'apps\windows\src-tauri\target\release\bundle'
Write-Host "Windows installers: $bundle" -ForegroundColor Green
