[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'Hermes Companion Live Gateway',
    [string]$BridgeTaskName = 'Hermes Companion Bridge'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'
function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $content = Get-Content $Path -Raw
    $escapedName = [regex]::Escape($Name)
    if ($content -match "(?m)^${escapedName}=") { $content = [regex]::Replace($content, "(?m)^${escapedName}=.*$", "$Name=$Value") }
    else { $content += "`n$Name=$Value`n" }
    [IO.File]::WriteAllText($Path, $content, (New-Object Text.UTF8Encoding($false)))
}
if ($PSCmdlet.ShouldProcess($TaskName, 'Disable optional Hermes live gateway')) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path $EnvFile) {
        Set-DotEnvValue $EnvFile 'HERMES_SERVE_URL' ''
        Set-DotEnvValue $EnvFile 'HERMES_SERVE_SESSION_TOKEN' ''
    }
    if (Get-ScheduledTask -TaskName $BridgeTaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $BridgeTaskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $BridgeTaskName
    }
}
Write-Host 'Optional Live Gateway disabled. Durable HTTP runs remain available.' -ForegroundColor Green
