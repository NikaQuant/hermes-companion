[CmdletBinding()]
param(
    [switch]$SkipHermesConfiguration,
    [switch]$SkipDesktopPlugin,
    [switch]$SkipStartupTask,
    [switch]$BuildReactPrototype,
    [switch]$EnableLiveGateway,
    [string]$AdminEmail = ''
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host '=== Hermes Companion v0.3 bootstrap ===' -ForegroundColor Magenta

if ($env:USERNAME -ieq 'HermesSafety') { throw 'Run this only inside the regular Administrator Hermes world, not HermesSafety.' }
if ($Root -match '(?i)Hermes[-_ ]?Safety|ProgramData\Hermes-Safety') { throw "Refusing Safety World install path: $Root" }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Required command not found: python' }
if (-not $SkipHermesConfiguration -and -not (Get-Command hermes -ErrorAction SilentlyContinue)) {
    throw 'The Hermes CLI is required unless -SkipHermesConfiguration is used.'
}

if (-not (Test-Path 'config\profiles.json') -and -not $SkipHermesConfiguration) {
    Write-Host 'Discovering local Hermes profiles...' -ForegroundColor Cyan
    & python (Join-Path $PSScriptRoot 'discover-profiles.py') --force
    if ($LASTEXITCODE -ne 0) { throw 'Profile discovery failed.' }
} elseif (-not $SkipHermesConfiguration) {
    $existing = (Get-Content 'config\profiles.json' -Raw | ConvertFrom-Json).profiles | ForEach-Object { $_.slug }
    if (@($existing).Count -le 1) {
        Write-Host 'Discovering local Hermes profiles...' -ForegroundColor Cyan
        & python (Join-Path $PSScriptRoot 'discover-profiles.py') --force
        if ($LASTEXITCODE -ne 0) { throw 'Profile discovery failed.' }
    }
}

if (-not (Test-Path '.env')) {
    $generate = @((Join-Path $PSScriptRoot 'generate-env.py'), '--root', $Root)
    if ($AdminEmail) { $generate += @('--email', $AdminEmail) }
    & python @generate
    if ($LASTEXITCODE -ne 0) { throw 'Environment provisioning failed.' }
} else {
    Write-Host '.env already exists; preserving it.' -ForegroundColor Yellow
}

$protected = @(
    '.env',
    'services\bridge\data',
    'services\bridge\data\uploads',
    'backups',
    'logs'
)
foreach ($path in $protected | Where-Object { $_ -ne '.env' }) { New-Item -ItemType Directory -Force -Path $path | Out-Null }
try {
    $Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    foreach ($path in $protected) {
        if (-not (Test-Path $path)) { continue }
        $resolved = Resolve-Path $path
        if ((Get-Item $resolved).PSIsContainer) {
            & icacls $resolved /inheritance:r /grant:r "${Identity}:(OI)(CI)(F)" '*S-1-5-18:(OI)(CI)(F)' | Out-Null
        } else {
            & icacls $resolved /inheritance:r /grant:r "${Identity}:(F)" '*S-1-5-18:(F)' | Out-Null
        }
    }
} catch {
    Write-Warning "Could not tighten Windows ACLs automatically: $($_.Exception.Message)"
}

if (-not (Test-Path '.venv\Scripts\python.exe')) { & python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& .\.venv\Scripts\python.exe -m pip install -e '.\services\bridge'
if ($LASTEXITCODE -ne 0) { throw 'Bridge dependency installation failed.' }
& .\.venv\Scripts\python.exe .\scripts\build-web.py
if ($LASTEXITCODE -ne 0) { throw 'PWA build failed.' }
& .\.venv\Scripts\python.exe .\scripts\validate-release.py --installed
if ($LASTEXITCODE -ne 0) { throw 'Release validation failed.' }

if ($BuildReactPrototype) {
    foreach ($command in @('node', 'npm')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Required for -BuildReactPrototype: $command" }
    }
    & npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed.' }
    & npm run typecheck:react
    if ($LASTEXITCODE -ne 0) { throw 'React prototype typecheck failed.' }
    & npm run build:react
    if ($LASTEXITCODE -ne 0) { throw 'React prototype build failed.' }
}

if (-not $SkipHermesConfiguration) { & (Join-Path $PSScriptRoot 'configure-hermes.ps1') }
if (-not $SkipDesktopPlugin) { & (Join-Path $PSScriptRoot 'install-desktop-plugin.ps1') -Force }
if (-not $SkipStartupTask) { & (Join-Path $PSScriptRoot 'install-startup-task.ps1') }
if ($EnableLiveGateway) { & (Join-Path $PSScriptRoot 'enable-live-gateway.ps1') }

if (-not $SkipStartupTask) {
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8787/api/health' -TimeoutSec 2
            if ($health.status -eq 'ok') { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw 'Bridge task was installed but the local health check did not become ready. Inspect logs\bridge.log.' }
}

Write-Host ''
Write-Host 'Hermes Companion is ready at http://127.0.0.1:8787' -ForegroundColor Green
Write-Host 'The plaintext administrator password was never written to .env.' -ForegroundColor Cyan
Write-Host 'For remote/mobile access, put this loopback service behind private HTTPS or a VPN.' -ForegroundColor Cyan
Write-Host 'Do not expose Hermes ports 8642 or 9119 directly.' -ForegroundColor Yellow
