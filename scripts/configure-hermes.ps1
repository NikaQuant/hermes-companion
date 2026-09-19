[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$SkipRestart
)
# Thin wrapper: the real work is in scripts/wire-hermes.py, which reads config/profiles.json
# and wires whichever profiles exist on THIS machine (no hard-coded profile list).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }
$args = @((Join-Path $PSScriptRoot 'wire-hermes.py'))
if ($DryRun) { $args += '--dry-run' }
if ($SkipRestart) { $args += '--no-restart' }
& $Python @args
if ($LASTEXITCODE -ne 0) { throw 'Hermes wiring failed.' }
