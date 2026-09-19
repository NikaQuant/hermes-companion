[CmdletBinding()]
param(
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes",
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
if ($env:USERNAME -ieq 'HermesSafety') { throw 'Refusing to install the regular Companion plugin under the HermesSafety account.' }
$normalized = [IO.Path]::GetFullPath($HermesHome)
if ($normalized -match '(?i)Hermes[-_ ]?Safety|ProgramData\\Hermes-Safety') { throw "Refusing Safety World target: $normalized" }
$Source = Join-Path $Root 'apps\desktop-plugin\plugin.js'
$TargetDir = Join-Path $normalized 'desktop-plugins\hermes-companion'
$Target = Join-Path $TargetDir 'plugin.js'
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
if ((Test-Path $Target) -and -not $Force) {
    $backup = "$Target.$(Get-Date -Format yyyyMMdd-HHmmss).bak"
    Copy-Item $Target $backup
    Write-Host "Backed up existing plugin to $backup"
}
Copy-Item $Source $Target -Force
Write-Host "Installed: $Target" -ForegroundColor Green
Write-Host "Restart Hermes Desktop, then open Companion from the sidebar or command palette." -ForegroundColor Cyan
Write-Warning "Some Hermes Desktop releases have had runtime-loader regressions for disk plugins. The web/PWA/APK remains independent of that loader."
