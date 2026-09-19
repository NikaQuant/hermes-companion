[CmdletBinding()]
param(
    [string]$Label = 'manual',
    [string]$Output = '',
    [switch]$IncludeSecrets,
    [switch]$IncludeUploads
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run bootstrap-windows.ps1 first.' }
$args = @((Join-Path $PSScriptRoot 'backup-local.py'), '--root', $Root, '--label', $Label)
if ($Output) { $args += @('--output', $Output) }
if ($IncludeSecrets) { $args += '--include-env' }
if ($IncludeUploads) { $args += '--include-uploads' }
$result = & $Python @args
if ($LASTEXITCODE -ne 0) { throw 'Backup failed.' }
$result | Write-Host
$archive = $result | Select-Object -First 1
if ($archive -and (Test-Path $archive)) {
    try {
        $Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls $archive /inheritance:r /grant:r "${Identity}:(F)" '*S-1-5-18:(F)' | Out-Null
    } catch { Write-Warning "Could not tighten backup ACL: $($_.Exception.Message)" }
}
