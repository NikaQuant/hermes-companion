[CmdletBinding()]
param(
    [switch]$Release
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Root 'apps\web'
Set-Location $Root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Python is required.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js/npm is required for Capacitor.' }
& python .\scripts\build-web.py
& npm install
Set-Location $Web
if (-not (Test-Path 'android')) { & npx cap add android }
& npx cap sync android
Set-Location (Join-Path $Web 'android')
$task = if ($Release) { 'assembleRelease' } else { 'assembleDebug' }
& .\gradlew.bat $task
$variant = if ($Release) { 'release' } else { 'debug' }
$apk = Get-ChildItem ".\app\build\outputs\apk\$variant\*.apk" | Select-Object -First 1
if (-not $apk) { throw 'Gradle finished but no APK was found.' }
$Artifacts = Join-Path $Root 'artifacts'; New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
$target = Join-Path $Artifacts "Hermes-Companion-$variant.apk"
Copy-Item $apk.FullName $target -Force
Write-Host "APK: $target" -ForegroundColor Green
if ($Release) { Write-Warning 'Release APK must be signed with your private Android signing key before distribution.' }
