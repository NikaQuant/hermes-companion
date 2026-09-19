[CmdletBinding()]
param([string]$Output = '')
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run bootstrap-windows.ps1 first.' }
$args = @((Join-Path $PSScriptRoot 'collect-diagnostics.py'), '--root', $Root)
if ($Output) { $args += @('--output', $Output) }
& $Python @args
