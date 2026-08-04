param(
    [ValidateSet('startup', 'updates')]
    [string] $GreetingScenario = 'startup'
)

$ErrorActionPreference = 'Stop'

$Scratch = $PSScriptRoot
$ConfigFile = Join-Path $Scratch 'arthur.config.json'
if (-not (Test-Path -LiteralPath $ConfigFile)) {
    throw "Arthur config file is required and was not found: $ConfigFile. Copy arthur.config.template.json to arthur.config.json and fill the placeholders."
}
$ArthurConfig = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
if ($ArthurConfig -and $ArthurConfig.runtime -and $ArthurConfig.runtime.scratchpadPath) {
    $Scratch = [string] $ArthurConfig.runtime.scratchpadPath
}
$BridgeScript = Join-Path $Scratch 'arthur_voice_bridge.py'
$SupervisorScript = Join-Path $Scratch 'arthur_supervisor.py'
$AutomationFile = if ($ArthurConfig -and $ArthurConfig.runtime -and $ArthurConfig.runtime.automationFile) { [string] $ArthurConfig.runtime.automationFile } else { Join-Path $env:USERPROFILE '.copilot\m-automations\automations.json' }
$StdoutLog = Join-Path $Scratch 'arthur_voice_bridge_stdout.log'
$StderrLog = Join-Path $Scratch 'arthur_voice_bridge_stderr.log'
$SupervisorStdoutLog = Join-Path $Scratch 'arthur_supervisor_stdout.log'
$SupervisorStderrLog = Join-Path $Scratch 'arthur_supervisor_stderr.log'
$PromptQueueFile = Join-Path $Scratch 'arthur_prompt_queue.jsonl'
$PromptResponsesFile = Join-Path $Scratch 'arthur_prompt_responses.jsonl'
$AutomationSyncScript = Join-Path $Scratch 'arthur_automation_sync.py'
$AutomationTemplateFile = Join-Path $Scratch 'automations.template.json'
$PreflightScript = Join-Path $Scratch 'arthur_preflight.py'
$VersionScript = Join-Path $Scratch 'arthur_version.py'
$ArthurMicDevice = if ($ArthurConfig -and $ArthurConfig.microphone -and $null -ne $ArthurConfig.microphone.deviceIndex) { [int] $ArthurConfig.microphone.deviceIndex } else { 1 }
$ArthurThreshold = if ($ArthurConfig -and $ArthurConfig.microphone -and $null -ne $ArthurConfig.microphone.threshold) { [int] $ArthurConfig.microphone.threshold } else { 350 }
$ArthurTts = if ($ArthurConfig -and $ArthurConfig.voice -and $ArthurConfig.voice.tts) { [string] $ArthurConfig.voice.tts } else { 'edge' }
$ArthurTimezone = if ($ArthurConfig -and $ArthurConfig.timezone) { [string] $ArthurConfig.timezone } else { 'Mountain Standard Time' }

$EnabledArthurAutomationNames = @()

$DisabledArthurAutomationNames = @(
    'Arthur Copilot prompt responder',
    'Arthur recording cleanup',
    'Arthur prompt queue executor',
    'Arthur voice transcript polling',
    'Arthur Copilot response startup'
)

function Write-ArthurStatus {
    param([string] $Message)
    Write-Host "[Arthur startup] $Message"
}

function Test-ArthurConfig {
    $configHelper = Join-Path $Scratch 'arthur_config.py'
    if (-not (Test-Path -LiteralPath $configHelper)) {
        throw "Arthur config helper not found: $configHelper"
    }
    $result = & python $configHelper --config $ConfigFile --validate 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus ($result -join ' ')
}

function Test-ArthurPreflight {
    if (-not (Test-Path -LiteralPath $PreflightScript)) {
        throw "Arthur preflight script not found: $PreflightScript"
    }
    $result = & python $PreflightScript --strict --write 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus 'Arthur preflight checks passed.'
}

function Sync-ArthurAutomations {
    if (-not (Test-Path -LiteralPath $AutomationSyncScript)) {
        throw "Arthur automation sync script not found: $AutomationSyncScript"
    }
    if (-not (Test-Path -LiteralPath $AutomationTemplateFile)) {
        throw "Arthur automation template not found: $AutomationTemplateFile"
    }
    $result = & python $AutomationSyncScript --template $AutomationTemplateFile 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus 'Arthur automations synchronized from template.'
}

function Update-ArthurVersionManifest {
    if (-not (Test-Path -LiteralPath $VersionScript)) {
        Write-ArthurStatus "Arthur version script not found: $VersionScript"
        return
    }
    $args = @($VersionScript, '--write')
    if ($env:ARTHUR_COMMIT_SHA) {
        $args += @('--commit-sha', $env:ARTHUR_COMMIT_SHA)
    }
    $result = & python @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus 'Arthur version manifest updated.'
}

function Start-ArthurSupervisor {
    if (-not (Test-Path -LiteralPath $SupervisorScript)) {
        throw "Arthur supervisor script not found: $SupervisorScript"
    }

    $existing = Get-CimInstance Win32_Process |
        Where-Object { $_.Name -match 'python' -and $_.CommandLine -like '*arthur_supervisor.py*' }

    if ($existing) {
        $ids = ($existing | ForEach-Object { $_.ProcessId }) -join ', '
        Write-ArthurStatus "Arthur supervisor already running. PID(s): $ids"
        return
    }

    $argumentList = '"' + $SupervisorScript + '" --mic-device ' + $ArthurMicDevice + ' --threshold ' + $ArthurThreshold + ' --greeting-scenario ' + $GreetingScenario
    $env:ARTHUR_CONFIG = $ConfigFile
    $env:ARTHUR_TTS = $ArthurTts
    $env:ARTHUR_TIMEZONE = $ArthurTimezone
    $env:ARTHUR_GREETING_SCENARIO = $GreetingScenario
    $process = Start-Process -FilePath 'python' `
        -ArgumentList $argumentList `
        -WorkingDirectory $Scratch `
        -WindowStyle Hidden `
        -RedirectStandardOutput $SupervisorStdoutLog `
        -RedirectStandardError $SupervisorStderrLog `
        -PassThru

    Start-Sleep -Seconds 10
    $running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $running) {
        $errorTail = ''
        if (Test-Path -LiteralPath $SupervisorStderrLog) {
            $errorTail = (Get-Content -LiteralPath $SupervisorStderrLog -Tail 20) -join [Environment]::NewLine
        }
        throw "Arthur supervisor exited during startup. Check $SupervisorStderrLog. $errorTail"
    }

    Write-ArthurStatus "Arthur supervisor started. PID: $($process.Id)"
}

New-Item -ItemType Directory -Path $Scratch -Force | Out-Null
Test-ArthurConfig
Test-ArthurPreflight
Update-ArthurVersionManifest
if (-not (Test-Path -LiteralPath $PromptQueueFile)) {
    New-Item -ItemType File -Path $PromptQueueFile | Out-Null
}
if (-not (Test-Path -LiteralPath $PromptResponsesFile)) {
    New-Item -ItemType File -Path $PromptResponsesFile | Out-Null
}

Sync-ArthurAutomations
Start-ArthurSupervisor
Write-ArthurStatus 'Startup complete.'

