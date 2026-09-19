[CmdletBinding()]
param(
    [int]$Port = 9119,
    [string]$HostAddress = '127.0.0.1',
    [string]$EnvFile = ''
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $Root '.env' }
if ($env:USERNAME -ieq 'HermesSafety') { throw 'Refusing to run the regular Hermes live gateway under HermesSafety.' }
if ($HostAddress -notin @('127.0.0.1','::1','localhost')) {
    throw 'Hermes Companion requires hermes serve to remain loopback-only. Use the Companion bridge for remote access.'
}
if (-not (Test-Path $EnvFile)) { throw "Missing $EnvFile" }
if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) { throw "The 'hermes' CLI is not on PATH." }
$values = @{}
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') { $values[$matches[1].Trim()] = $matches[2].Trim() }
}
$token = $values['HERMES_SERVE_SESSION_TOKEN']
if (-not $token -or $token.Length -lt 16) { throw 'HERMES_SERVE_SESSION_TOKEN is missing or too short. Run enable-live-gateway.ps1.' }
$env:HERMES_DASHBOARD_SESSION_TOKEN = $token
& hermes serve --host $HostAddress --port $Port
exit $LASTEXITCODE
