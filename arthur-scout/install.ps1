param(
    [string] $InstallRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [switch] $CreateScheduledTask
)

$ErrorActionPreference = 'Stop'

$PackageRoot = Split-Path -Parent $PSCommandPath
$CommitSha = ''
try {
    $CommitSha = (git -C $PackageRoot rev-parse --short HEAD 2>$null).Trim()
} catch {
    $CommitSha = ''
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $PackageRoot 'src\*.py') -Destination $InstallRoot -Force
Copy-Item -LiteralPath (Join-Path $PackageRoot 'scripts\Start-Arthur.ps1') -Destination $InstallRoot -Force
Copy-Item -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Destination (Join-Path $InstallRoot 'automations.template.json') -Force

$configSource = Join-Path $PackageRoot 'config\arthur.config.template.json'
$configTarget = Join-Path $InstallRoot 'arthur.config.json'
if (-not (Test-Path -LiteralPath $configTarget)) {
    Copy-Item -LiteralPath $configSource -Destination $configTarget
    Write-Host "Created config template at $configTarget. Update placeholders before production use."
}

$versionScript = Join-Path $InstallRoot 'arthur_version.py'
if (Test-Path -LiteralPath $versionScript) {
    $versionArgs = @($versionScript, '--write')
    if ($CommitSha) {
        $versionArgs += @('--commit-sha', $CommitSha)
    }
    & python @versionArgs | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur version manifest generation failed.'
    }
}

$preflightScript = Join-Path $InstallRoot 'arthur_preflight.py'
if (Test-Path -LiteralPath $preflightScript) {
    & python $preflightScript --write | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur preflight checks failed.'
    }
}

$syncScript = Join-Path $InstallRoot 'arthur_automation_sync.py'
$syncTemplate = Join-Path $InstallRoot 'automations.template.json'
if ((Test-Path -LiteralPath $syncScript) -and (Test-Path -LiteralPath $syncTemplate)) {
    & python $syncScript --template $syncTemplate | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur automation synchronization failed.'
    }
}

foreach ($file in 'arthur_prompt_queue.jsonl','arthur_prompt_responses.jsonl') {
    $path = Join-Path $InstallRoot $file
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType File -Path $path | Out-Null
    }
}

if ($CreateScheduledTask) {
    $startScript = Join-Path $InstallRoot 'Start-Arthur.ps1'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName 'Arthur Voice Bridge' -Action $action -Trigger $trigger -Description 'Starts Arthur voice bridge for Microsoft Scout.' -Force | Out-Null
    Write-Host 'Registered scheduled task: Arthur Voice Bridge'
}

Write-Host "Arthur installed to $InstallRoot"
