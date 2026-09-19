[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$InstallRoot = 'C:\HermesCompanion',
    [switch]$SkipHermesConfiguration,
    [switch]$SkipDesktopPlugin,
    [switch]$EnableLiveGateway
)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'deploy-windows.ps1') -InstallRoot $InstallRoot `
    -SkipHermesConfiguration:$SkipHermesConfiguration `
    -SkipDesktopPlugin:$SkipDesktopPlugin `
    -EnableLiveGateway:$EnableLiveGateway `
    -Confirm:$false
