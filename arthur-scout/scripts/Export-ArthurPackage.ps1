[CmdletBinding()]
param(
    [string] $SourceRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [string] $OutputRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $OutputRoot) {
    $OutputRoot = Join-Path (Split-Path -Parent $SourceRoot) 'arthur-source-package'
}

$canonicalRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$repositoryRoot = Split-Path -Parent $canonicalRoot
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$packageRoot = Join-Path $OutputRoot 'arthur-scout'

function Copy-ArthurFile {
    param(
        [string] $Source,
        [string] $Destination
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required Arthur source file not found: $Source"
    }
    $destinationDirectory = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

if (Test-Path -LiteralPath $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
foreach ($directory in 'config','docs','scripts','src','tests') {
    New-Item -ItemType Directory -Path (Join-Path $packageRoot $directory) -Force | Out-Null
}

$pythonFiles = @(
    'arthur_automation_sync.py',
    'arthur_cleanup_chats.py',
    'arthur_cleanup_recordings.py',
    'arthur_config.py',
    'arthur_dashboard_server.py',
    'arthur_email_handoff.py',
    'arthur_preflight.py',
    'arthur_prompt_worker.py',
    'arthur_queue_watchdog.py',
    'arthur_schedule_briefing.py',
    'arthur_scout_handoff.py',
    'arthur_speech.py',
    'arthur_status_dashboard.py',
    'arthur_supervisor.py',
    'arthur_version.py',
    'arthur_voice_bridge.py',
    'arthur_voice_catalog.py',
    'arthur_voice_listener_log.py'
)
foreach ($file in $pythonFiles) {
    Copy-ArthurFile `
        -Source (Join-Path $source $file) `
        -Destination (Join-Path $packageRoot "src\$file")
}

foreach ($file in 'Start-Arthur.ps1','Update-Arthur.ps1') {
    Copy-ArthurFile `
        -Source (Join-Path $source $file) `
        -Destination (Join-Path $packageRoot "scripts\$file")
}

foreach ($file in @(
    'Install-ArthurZipformerModel.ps1',
    'Migrate-ArthurToLocalAppData.ps1',
    'New-ArthurPackageManifest.ps1',
    'Remove-ArthurLegacyData.ps1',
    'Test-Arthur.ps1'
)) {
    Copy-ArthurFile `
        -Source (Join-Path $canonicalRoot "scripts\$file") `
        -Destination (Join-Path $packageRoot "scripts\$file")
}
Copy-ArthurFile -Source $PSCommandPath -Destination (Join-Path $packageRoot 'scripts\Export-ArthurPackage.ps1')

foreach ($file in 'arthur.config.template.json','automations.template.json') {
    $preferred = Join-Path $source $file
    $configSource = if (Test-Path -LiteralPath $preferred) {
        $preferred
    }
    else {
        Join-Path $canonicalRoot "config\$file"
    }
    Copy-ArthurFile -Source $configSource -Destination (Join-Path $packageRoot "config\$file")
}

foreach ($file in 'README.md','install.ps1','uninstall.ps1','requirements.txt','.gitignore') {
    Copy-ArthurFile -Source (Join-Path $canonicalRoot $file) -Destination (Join-Path $packageRoot $file)
}
Copy-ArthurFile -Source (Join-Path $repositoryRoot 'LICENSE') -Destination (Join-Path $packageRoot 'LICENSE')

foreach ($file in 'architecture.md','install.md','model-selection.md','operations.md','prerequisites.md') {
    Copy-ArthurFile -Source (Join-Path $canonicalRoot "docs\$file") -Destination (Join-Path $packageRoot "docs\$file")
}

Copy-Item -Path (Join-Path $canonicalRoot 'tests\*') -Destination (Join-Path $packageRoot 'tests') -Recurse -Force

& (Join-Path $packageRoot 'scripts\New-ArthurPackageManifest.ps1') -PackageRoot $packageRoot | Out-Null
& (Join-Path $packageRoot 'scripts\Test-Arthur.ps1') -PackageRoot $packageRoot

Write-Host "Arthur source package ready: $packageRoot"
