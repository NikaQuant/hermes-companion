[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Url)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'
if (-not (Test-Path $EnvFile)) { throw 'Missing .env' }
$Url = $Url.TrimEnd('/')
if ($Url -notmatch '^https://') { throw 'The public app URL must use HTTPS.' }
$content = Get-Content $EnvFile -Raw
if ($content -match '(?m)^PUBLIC_APP_URL=') { $content = [regex]::Replace($content, '(?m)^PUBLIC_APP_URL=.*$', "PUBLIC_APP_URL=$Url") }
else { $content += "`nPUBLIC_APP_URL=$Url`n" }
Set-Content -Path $EnvFile -Value $content -NoNewline
Write-Host "PUBLIC_APP_URL set to $Url. Restart the bridge task." -ForegroundColor Green
