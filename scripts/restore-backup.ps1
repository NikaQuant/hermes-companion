[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [string]$TaskName = 'Hermes Companion Bridge',
    [switch]$RestoreProfiles,
    [switch]$RestoreEnv,
    [switch]$RestoreUploads,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run bootstrap-windows.ps1 first.' }
if (-not (Test-Path $Archive)) { throw "Backup not found: $Archive" }
if (-not $PSCmdlet.ShouldProcess($Root, "Restore Hermes Companion from $Archive")) { return }
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
try {
    $args = @((Join-Path $PSScriptRoot 'restore-backup.py'), (Resolve-Path $Archive), '--root', $Root)
    if ($RestoreProfiles) { $args += '--restore-profiles' }
    if ($RestoreEnv) { $args += '--restore-env' }
    if ($RestoreUploads) { $args += '--restore-uploads' }
    if ($Force) { $args += '--force' }
    & $Python @args
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed.' }
    try {
        $Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        foreach ($relative in @('.env','services\bridge\data','backups')) {
            $target = Join-Path $Root $relative
            if (-not (Test-Path $target)) { continue }
            if ((Get-Item $target).PSIsContainer) {
                & icacls $target /inheritance:r /grant:r "${Identity}:(OI)(CI)(F)" '*S-1-5-18:(OI)(CI)(F)' | Out-Null
            } else {
                & icacls $target /inheritance:r /grant:r "${Identity}:(F)" '*S-1-5-18:(F)' | Out-Null
            }
        }
    } catch { Write-Warning "Restore completed, but ACL hardening failed: $($_.Exception.Message)" }
} finally {
    if ($task) { Start-ScheduledTask -TaskName $TaskName }
}
