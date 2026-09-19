[CmdletBinding()]
param([string]$Email = "")
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run bootstrap-windows.ps1 first.' }
$args = @((Join-Path $PSScriptRoot 'reset-admin-password.py'), '--root', $Root)
if ($Email) { $args += @('--email', $Email) }
& $Python @args
