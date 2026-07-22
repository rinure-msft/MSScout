param(
    [string] $PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
)

$ErrorActionPreference = 'Stop'

$required = @(
    'src\arthur_voice_bridge.py',
    'src\arthur_supervisor.py',
    'src\arthur_queue_watchdog.py',
    'src\arthur_cleanup_chats.py',
    'src\arthur_cleanup_recordings.py',
    'src\arthur_voice_listener_log.py',
    'scripts\Start-Arthur.ps1',
    'config\arthur.config.template.json',
    'config\voice-commands.json',
    'config\automations.template.json'
)

foreach ($relative in $required) {
    $path = Join-Path $PackageRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required package file: $relative"
    }
}

python -m py_compile (Join-Path $PackageRoot 'src\arthur_voice_bridge.py') (Join-Path $PackageRoot 'src\arthur_supervisor.py') (Join-Path $PackageRoot 'src\arthur_queue_watchdog.py') (Join-Path $PackageRoot 'src\arthur_cleanup_chats.py') (Join-Path $PackageRoot 'src\arthur_cleanup_recordings.py') (Join-Path $PackageRoot 'src\arthur_voice_listener_log.py')
Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'src') -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\arthur.config.template.json') -Raw | ConvertFrom-Json | Out-Null
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\voice-commands.json') -Raw | ConvertFrom-Json | Out-Null
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Raw | ConvertFrom-Json | Out-Null

Write-Host 'Arthur package validation passed.'
