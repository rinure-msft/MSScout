param(
    [string] $InstallRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [switch] $RemoveRuntimeData
)

$ErrorActionPreference = 'Stop'

Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match 'python' -and ($_.CommandLine -like '*arthur_supervisor.py*' -or $_.CommandLine -like '*arthur_voice_bridge.py*') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Unregister-ScheduledTask -TaskName 'Arthur Voice Bridge' -Confirm:$false -ErrorAction SilentlyContinue

if ($RemoveRuntimeData -and (Test-Path -LiteralPath $InstallRoot)) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
    Write-Host "Removed Arthur runtime directory: $InstallRoot"
} else {
    Write-Host 'Stopped Arthur and removed scheduled task if present. Runtime files were preserved.'
}
