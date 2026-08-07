param(
    [string] $PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
)

$ErrorActionPreference = 'Stop'

$required = @(
    'install.ps1',
    'uninstall.ps1',
    'src\arthur_config.py',
    'src\arthur_automation_sync.py',
    'src\arthur_speech.py',
    'src\arthur_voice_bridge.py',
    'src\arthur_voice_catalog.py',
    'src\arthur_supervisor.py',
    'src\arthur_prompt_worker.py',
    'src\arthur_preflight.py',
    'src\arthur_email_handoff.py',
    'src\arthur_scout_handoff.py',
    'src\arthur_schedule_briefing.py',
    'src\arthur_dashboard_server.py',
    'src\arthur_status_dashboard.py',
    'src\arthur_version.py',
    'src\arthur_queue_watchdog.py',
    'src\arthur_cleanup_chats.py',
    'src\arthur_cleanup_recordings.py',
    'src\arthur_voice_listener_log.py',
    'scripts\Start-Arthur.ps1',
    'scripts\Migrate-ArthurToLocalAppData.ps1',
    'scripts\Remove-ArthurLegacyData.ps1',
    'scripts\Install-ArthurZipformerModel.ps1',
    'scripts\New-ArthurPackageManifest.ps1',
    'scripts\Update-Arthur.ps1',
    'requirements.txt',
    'config\arthur.config.template.json',
    'config\automations.template.json',
    'tests\test_dashboard.py',
    'tests\test_voice_security.py',
    'tests\Test-ArthurUpgrade.ps1'
)

foreach ($relative in $required) {
    $path = Join-Path $PackageRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required package file: $relative"
    }
}

$resolvedPackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$legalRoot = if (Test-Path -LiteralPath (Join-Path $resolvedPackageRoot 'LICENSE')) {
    $resolvedPackageRoot
}
else {
    Split-Path -Parent $resolvedPackageRoot
}
if (-not (Test-Path -LiteralPath (Join-Path $legalRoot 'LICENSE'))) {
    throw 'Missing Arthur licence file: LICENSE'
}

python -m py_compile (Join-Path $PackageRoot 'src\arthur_config.py') (Join-Path $PackageRoot 'src\arthur_speech.py') (Join-Path $PackageRoot 'src\arthur_voice_bridge.py') (Join-Path $PackageRoot 'src\arthur_voice_catalog.py') (Join-Path $PackageRoot 'src\arthur_supervisor.py') (Join-Path $PackageRoot 'src\arthur_prompt_worker.py') (Join-Path $PackageRoot 'src\arthur_preflight.py') (Join-Path $PackageRoot 'src\arthur_email_handoff.py') (Join-Path $PackageRoot 'src\arthur_scout_handoff.py') (Join-Path $PackageRoot 'src\arthur_schedule_briefing.py') (Join-Path $PackageRoot 'src\arthur_dashboard_server.py') (Join-Path $PackageRoot 'src\arthur_status_dashboard.py') (Join-Path $PackageRoot 'src\arthur_version.py') (Join-Path $PackageRoot 'src\arthur_queue_watchdog.py') (Join-Path $PackageRoot 'src\arthur_cleanup_chats.py') (Join-Path $PackageRoot 'src\arthur_cleanup_recordings.py') (Join-Path $PackageRoot 'src\arthur_voice_listener_log.py')
Get-ChildItem -LiteralPath (Join-Path $PackageRoot 'src') -Directory -Filter '__pycache__' -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
$config = Get-Content -LiteralPath (Join-Path $PackageRoot 'config\arthur.config.template.json') -Raw | ConvertFrom-Json
if ($config.speechRecognition.backend -ne 'zipformer' -or $config.speechRecognition.postActivationBackend -ne 'zipformer') {
    throw 'Arthur config must use Zipformer for both speech recognition stages.'
}
Get-Content -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Raw | ConvertFrom-Json | Out-Null
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Install-ArthurZipformerModel.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Migrate-ArthurToLocalAppData.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Remove-ArthurLegacyData.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\New-ArthurPackageManifest.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'tests\Test-ArthurUpgrade.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Update-Arthur.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Export-ArthurPackage.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'install.ps1') -Raw))
[void][scriptblock]::Create((Get-Content -LiteralPath (Join-Path $PackageRoot 'uninstall.ps1') -Raw))

$requirements = Get-Content -LiteralPath (Join-Path $PackageRoot 'requirements.txt') -Raw
if ($requirements -notmatch '(?m)^sherpa-onnx') {
    throw 'Arthur runtime requirements must include sherpa-onnx.'
}
if ($requirements -match '(?m)^faster-whisper') {
    throw 'Arthur continuous runtime must not depend on faster-whisper.'
}
$ciRequirementsPath = Join-Path $PackageRoot 'requirements-ci.txt'
if (Test-Path -LiteralPath $ciRequirementsPath) {
    $ciRequirements = Get-Content -LiteralPath $ciRequirementsPath -Raw
    if ($ciRequirements -match '(?m)^-r\s+requirements\.txt' -or $ciRequirements -match '(?m)^(pywin32|pypiwin32|comtypes)') {
        throw 'Arthur Linux CI requirements must not include Windows-only runtime packages.'
    }
}
$installText = Get-Content -LiteralPath (Join-Path $PackageRoot 'install.ps1') -Raw
$expectedCopyCommand = "Copy-Item -Path (Join-Path `$packageRoot 'src\*.py')"
if (-not $installText.Contains($expectedCopyCommand)) {
    throw 'Arthur installer must expand src\*.py with Copy-Item -Path.'
}
if ($installText -match '(?i)OneDrive.+Scratchpad') {
    throw 'Arthur installer must not default runtime data to OneDrive.'
}
if ($installText -match '(?<!Un)Register-ScheduledTask') {
    throw 'Arthur installer must not register a second startup mechanism.'
}
if ($installText -notmatch 'Remove-ArthurObsoleteRuntimeFiles') {
    throw 'Arthur installer must remove obsolete benchmark and Nemotron files.'
}
if ($installText -match 'Get-FileHash') {
    throw 'Arthur setup must use its self-contained SHA-256 helper when launched from the desktop application.'
}
$startText = Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Start-Arthur.ps1') -Raw
if ($startText -match 'Sync-ArthurAutomations|arthur_automation_sync\.py') {
    throw 'Arthur startup must not mutate Scout automations.'
}
$bridgeText = Get-Content -LiteralPath (Join-Path $PackageRoot 'src\arthur_voice_bridge.py') -Raw
if ($bridgeText -match 'arthur_bridge_utterance_.+\.wav|wavfile\.write') {
    throw 'Arthur must not retain raw microphone utterances by default.'
}
if ($bridgeText -notmatch '"activation_id": LAST_ACTIVATION_ID' -or $bridgeText -notmatch 'def mark_activation') {
    throw 'Arthur wake activations must persist a durable heartbeat activation ID.'
}
if ($bridgeText -notmatch 'get_config\(\"assistantName\",\s*\"Arthur\"\)') {
    throw 'Arthur wake matching must use the configured assistant name.'
}
$defaultCommands = @($config.enabledCommands)
if ($defaultCommands -contains 'prompt_window') {
    throw 'Arthur must not enable arbitrary voice-to-Scout prompts by default.'
}
if ($defaultCommands -notcontains 'open_dashboard') {
    throw 'Arthur must preserve the owner-provided open dashboard command.'
}
if ($config.scout.queueEnabled -ne $true) {
    throw 'Arthur Scout queueing must default to on.'
}
if ($bridgeText -match 'Auto-escalated to Copilot') {
    throw 'Arthur must not auto-escalate unmatched voice speech to Scout.'
}
if ($bridgeText -notmatch '"source": "voice"' -or $bridgeText -notmatch '"authorization": authorization') {
    throw 'Arthur voice queue entries must carry source and authorization metadata.'
}
if ($bridgeText -notmatch 'Blocked Scout queue entry because queueing is disabled') {
    throw 'Arthur must block Scout queue entries while queueing is off.'
}
$workerText = Get-Content -LiteralPath (Join-Path $PackageRoot 'src\arthur_prompt_worker.py') -Raw
if ($workerText -notmatch 'Legacy voice prompt blocked' -or $workerText -notmatch 'authorization != "enabled_command"') {
    throw 'Arthur prompt worker must reject untrusted voice queue entries.'
}
$dashboardServerText = Get-Content -LiteralPath (Join-Path $PackageRoot 'src\arthur_dashboard_server.py') -Raw
if ($dashboardServerText -notmatch 'DEFAULT_HOST = "127\.0\.0\.1"' -or $dashboardServerText -notmatch 'frame-ancestors') {
    throw 'Arthur dashboard server must remain loopback-only with browser security headers.'
}
$dashboardText = Get-Content -LiteralPath (Join-Path $PackageRoot 'src\arthur_status_dashboard.py') -Raw
if ($dashboardText -notmatch 'class="brand-mark"' -or $dashboardText -notmatch '--cp-bg') {
    throw 'Arthur dashboard must use the desktop visual language.'
}
$updateText = Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Update-Arthur.ps1') -Raw
if ($updateText -notmatch 'Assert-ArthurPackageIntegrity' -or $updateText -notmatch 'New-ArthurUpdateStage') {
    throw 'Arthur updates must verify package integrity and stage changes before activation.'
}
if ($updateText -notmatch 'runtime\.browserProfilePath = Join-Path \(Split-Path -Parent \$InstallRoot\)') {
    throw 'Arthur staged updates must rewrite the browser profile to the final LocalAppData path.'
}
$speechText = Get-Content -LiteralPath (Join-Path $PackageRoot 'src\arthur_speech.py') -Raw
if ($speechText -notmatch 'sync_assistant_hotword') {
    throw 'Zipformer hotword bias must follow the configured assistant name.'
}
$zipformerInstallText = Get-Content -LiteralPath (Join-Path $PackageRoot 'scripts\Install-ArthurZipformerModel.ps1') -Raw
if ($zipformerInstallText -match 'Get-FileHash') {
    throw 'Arthur model setup must not depend on PowerShell module auto-loading.'
}

$templateText = Get-Content -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Raw
foreach ($requiredName in 'Arthur Email Handoff Sender v2','Arthur Scout Task Handoff Processor','Arthur Morning Brief','Arthur Evening Brief','Arthur Copilot prompt responder Chat Cleanup') {
    if ($templateText -notlike "*$requiredName*") {
        throw "Automation template missing required automation: $requiredName"
    }
}

Write-Host 'Arthur package validation passed.'
