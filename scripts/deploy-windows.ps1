[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = 'C:\HermesCompanion',
    [string]$AdminEmail = '',
    [switch]$SkipHermesConfiguration,
    [switch]$SkipDesktopPlugin,
    [switch]$EnableLiveGateway
)
$ErrorActionPreference = 'Stop'
$SourceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$InstallRoot = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($env:USERNAME -ieq 'HermesSafety') { throw 'Run this only under the regular Hermes Windows account.' }
if ($InstallRoot -match '(?i)Hermes[-_ ]?Safety|ProgramData\Hermes-Safety') { throw "Refusing Safety World target: $InstallRoot" }
$driveRoot = [IO.Path]::GetPathRoot($InstallRoot).TrimEnd('\')
$forbiddenRoots = @($driveRoot, $env:SystemRoot, $env:USERPROFILE, $env:ProgramData) |
    Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }
if ($forbiddenRoots -contains $InstallRoot) { throw "Refusing dangerous install target: $InstallRoot" }
if ($InstallRoot -ieq $SourceRoot) {
    throw 'The extracted release is already the requested install path. Run scripts\bootstrap-windows.ps1 directly, or choose a different -InstallRoot for rollback deployment.'
}
if (-not $PSCmdlet.ShouldProcess($InstallRoot, 'Install or upgrade Hermes Companion')) { return }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$rollback = "$InstallRoot.rollback-$stamp"
$bridgeTask = 'Hermes Companion Bridge'
$liveTask = 'Hermes Companion Live Gateway'
$hadInstall = Test-Path $InstallRoot

function Invoke-Robocopy([string]$From, [string]$To, [switch]$Mirror) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
    $mode = if ($Mirror) { '/MIR' } else { '/E' }
    $args = @($From, $To, $mode, '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP',
        '/XD', '.git', '.venv', 'node_modules', 'artifacts', 'backups', 'services\bridge\data', 'apps\web\android', 'apps\windows\src-tauri\target',
        '/XF', '.env')
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
}

Stop-ScheduledTask -TaskName $bridgeTask -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $liveTask -ErrorAction SilentlyContinue
try {
    if ($hadInstall) {
        Write-Host "Preserving rollback copy at $rollback" -ForegroundColor Cyan
        Invoke-Robocopy $InstallRoot $rollback
        foreach ($relative in @('.env','services\bridge\data','backups')) {
            $source = Join-Path $InstallRoot $relative
            if (Test-Path $source) {
                $destination = Join-Path $rollback $relative
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
                Copy-Item $source $destination -Recurse -Force
            }
        }
    }
    Invoke-Robocopy $SourceRoot $InstallRoot -Mirror
    Set-Location $InstallRoot
    $bootstrap = Join-Path $InstallRoot 'scripts\bootstrap-windows.ps1'
    $params = @{}
    if ($AdminEmail) { $params['AdminEmail'] = $AdminEmail }
    if ($SkipHermesConfiguration) { $params['SkipHermesConfiguration'] = $true }
    if ($SkipDesktopPlugin) { $params['SkipDesktopPlugin'] = $true }
    & $bootstrap @params
    if ($EnableLiveGateway) { & (Join-Path $InstallRoot 'scripts\enable-live-gateway.ps1') }
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/health' -TimeoutSec 15
    if ($health.status -ne 'ok') { throw 'Companion health check did not return ok.' }
    Write-Host "Hermes Companion $($health.version) deployed to $InstallRoot" -ForegroundColor Green
    if ($hadInstall) { Write-Host "Rollback copy retained at $rollback" -ForegroundColor Yellow }
} catch {
    Write-Error "Deployment failed: $($_.Exception.Message)"
    if ($hadInstall -and (Test-Path $rollback)) {
        Write-Warning 'Restoring previous installation files.'
        Invoke-Robocopy $rollback $InstallRoot -Mirror
        foreach ($relative in @('.env','services\bridge\data','backups')) {
            $source = Join-Path $rollback $relative
            if (Test-Path $source) {
                $destination = Join-Path $InstallRoot $relative
                New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
                if (Test-Path $destination) { Remove-Item $destination -Recurse -Force }
                Copy-Item $source $destination -Recurse -Force
            }
        }
        Start-ScheduledTask -TaskName $bridgeTask -ErrorAction SilentlyContinue
    }
    throw
}
