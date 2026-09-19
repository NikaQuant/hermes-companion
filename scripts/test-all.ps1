[CmdletBinding()]
param(
    [switch]$TestReactSource,
    [switch]$GatewayE2E,
    [switch]$BrowserE2E
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not (Test-Path '.venv\Scripts\python.exe')) { & python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -e '.\services\bridge[dev]'
if ($LASTEXITCODE -ne 0) { throw 'Development dependency installation failed.' }
$arguments = @('.\scripts\test-all.py')
if ($GatewayE2E) { $arguments += '--gateway-e2e' }
if ($BrowserE2E) { $arguments += '--browser-e2e' }
& .\.venv\Scripts\python.exe @arguments
if ($LASTEXITCODE -ne 0) { throw 'Validation failed.' }
if ($TestReactSource) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm is required for -TestReactSource' }
    & npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
    & npm run typecheck:react
    if ($LASTEXITCODE -ne 0) { throw 'React prototype typecheck failed.' }
    & npm run build:react
    if ($LASTEXITCODE -ne 0) { throw 'React prototype build failed.' }
}
Write-Host 'All requested validation steps passed.' -ForegroundColor Green
