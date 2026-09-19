[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$Port = 9119,
    [string]$TaskName = 'Hermes Companion Live Gateway',
    [string]$BridgeTaskName = 'Hermes Companion Bridge'
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root '.env'
if ($env:USERNAME -ieq 'HermesSafety') { throw 'Refusing to configure the regular live gateway under HermesSafety.' }
if (-not (Test-Path $EnvFile)) { throw 'Missing .env. Run bootstrap-windows.ps1 first.' }
if (-not (Get-Command hermes -ErrorAction SilentlyContinue)) { throw "The 'hermes' CLI is not on PATH." }

function Set-DotEnvValue([string]$Path, [string]$Name, [string]$Value) {
    $content = Get-Content $Path -Raw
    $escapedName = [regex]::Escape($Name)
    if ($content -match "(?m)^${escapedName}=") {
        $content = [regex]::Replace($content, "(?m)^${escapedName}=.*$", "$Name=$Value")
    } else {
        if (-not $content.EndsWith("`n")) { $content += "`n" }
        $content += "$Name=$Value`n"
    }
    [IO.File]::WriteAllText($Path, $content, (New-Object Text.UTF8Encoding($false)))
}

$bytes = New-Object byte[] 48
# Windows PowerShell 5.1 (.NET Framework) has no RandomNumberGenerator::Fill — it was added
# in .NET Core. Use the legacy CSP there, Fill on PowerShell 7+/.NET Core.
if ([Security.Cryptography.RandomNumberGenerator].GetMethod('Fill')) {
    [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
} else {
    $rng = New-Object Security.Cryptography.RNGCryptoServiceProvider
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
}
$token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
$url = "http://127.0.0.1:$Port"
if ($PSCmdlet.ShouldProcess($EnvFile, 'Enable the optional loopback Hermes serve relay')) {
    Set-DotEnvValue $EnvFile 'HERMES_SERVE_URL' $url
    Set-DotEnvValue $EnvFile 'HERMES_SERVE_SESSION_TOKEN' $token
    try {
        $Identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls $EnvFile /inheritance:r /grant:r "${Identity}:(F)" '*S-1-5-18:(F)' | Out-Null
    } catch { Write-Warning "Could not tighten .env ACL: $($_.Exception.Message)" }

    $launcher = Join-Path $PSScriptRoot 'Start-HermesServe.ps1'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`" -Port $Port" -WorkingDirectory $Root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    if (Get-ScheduledTask -TaskName $BridgeTaskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $BridgeTaskName -ErrorAction SilentlyContinue
        Start-ScheduledTask -TaskName $BridgeTaskName
    }
}
Write-Host "Live Gateway enabled at $url/api/ws through a loopback-only hermes serve process." -ForegroundColor Green
Write-Host 'Remote clients still connect only to Hermes Companion; the bridge issues one-time WebSocket tickets.' -ForegroundColor Cyan
