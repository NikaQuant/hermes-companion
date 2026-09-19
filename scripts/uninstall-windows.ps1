[CmdletBinding(SupportsShouldProcess, ConfirmImpact='High')]
param(
    [string]$InstallRoot = '',
    [string]$HermesHome = "$env:LOCALAPPDATA\hermes",
    [switch]$RemoveData
)
$ErrorActionPreference = 'Stop'
$Root = if ($InstallRoot) { [IO.Path]::GetFullPath($InstallRoot) } else { [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)) }
$Root = $Root.TrimEnd('\')
if ($env:USERNAME -ieq 'HermesSafety') { throw 'Refusing regular Companion uninstall under HermesSafety.' }
if ($Root -match '(?i)Hermes[-_ ]?Safety|ProgramData\Hermes-Safety') { throw "Refusing Safety World target: $Root" }
$driveRoot = [IO.Path]::GetPathRoot($Root).TrimEnd('\')
$forbiddenRoots = @($driveRoot, $env:SystemRoot, $env:USERPROFILE, $env:ProgramData, $env:LOCALAPPDATA) |
    Where-Object { $_ } | ForEach-Object { [IO.Path]::GetFullPath($_).TrimEnd('\') }
if ($forbiddenRoots -contains $Root) { throw "Refusing dangerous uninstall target: $Root" }
foreach ($marker in @('VERSION','scripts\Start-HermesCompanion.ps1','services\bridge')) {
    if (-not (Test-Path (Join-Path $Root $marker))) { throw "Target does not look like Hermes Companion; missing $marker" }
}
if (-not $PSCmdlet.ShouldProcess($Root, 'Uninstall Hermes Companion')) { return }
foreach ($name in @('Hermes Companion Bridge','Hermes Companion Live Gateway')) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}
$plugin = Join-Path $HermesHome 'desktop-plugins\hermes-companion'
if (Test-Path $plugin) { Remove-Item $plugin -Recurse -Force }
if ($RemoveData) {
    Remove-Item $Root -Recurse -Force
    Write-Host 'Hermes Companion and its local account data were removed.' -ForegroundColor Yellow
} else {
    foreach ($path in @('.venv','apps\web\dist')) {
        $target = Join-Path $Root $path
        if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    }
    Write-Host "Runtime removed. .env, database, uploads and backups remain under $Root." -ForegroundColor Green
}
Write-Host 'Hermes itself and every Safety World component were left untouched.' -ForegroundColor Cyan
