$ErrorActionPreference = 'Stop'

$Scratch = 'C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad'
$BridgeScript = Join-Path $Scratch 'arthur_voice_bridge.py'
$SupervisorScript = Join-Path $Scratch 'arthur_supervisor.py'
$AutomationFile = 'C:\Users\riur\.copilot\m-automations\automations.json'
$StdoutLog = Join-Path $Scratch 'arthur_voice_bridge_stdout.log'
$StderrLog = Join-Path $Scratch 'arthur_voice_bridge_stderr.log'
$SupervisorStdoutLog = Join-Path $Scratch 'arthur_supervisor_stdout.log'
$SupervisorStderrLog = Join-Path $Scratch 'arthur_supervisor_stderr.log'
$PromptQueueFile = Join-Path $Scratch 'arthur_prompt_queue.jsonl'
$PromptResponsesFile = Join-Path $Scratch 'arthur_prompt_responses.jsonl'
$ArthurMicDevice = 1
$ArthurThreshold = 350

$EnabledArthurAutomationNames = @(
    'Arthur Copilot prompt responder'
)

$DisabledArthurAutomationNames = @(
    'Arthur recording cleanup',
    'Arthur prompt queue executor',
    'Arthur voice transcript polling',
    'Arthur Copilot response startup'
)

function Write-ArthurStatus {
    param([string] $Message)
    Write-Host "[Arthur startup] $Message"
}

function Enable-ArthurAutomations {
    if (-not (Test-Path -LiteralPath $AutomationFile)) {
        throw "Automation file not found: $AutomationFile"
    }

    $parsedAutomations = Get-Content -LiteralPath $AutomationFile -Raw | ConvertFrom-Json
    $automations = @($parsedAutomations | ForEach-Object { $_ })
    $changed = $false
    $enabledCount = 0

    foreach ($automation in $automations) {
        if ($EnabledArthurAutomationNames -contains $automation.name) {
            $enabledCount++
            if (-not $automation.enabled) {
                $automation.enabled = $true
                $changed = $true
            }
        }
        if ($DisabledArthurAutomationNames -contains $automation.name) {
            if ($automation.enabled) {
                $automation.enabled = $false
                $changed = $true
            }
        }
    }

    if ($enabledCount -ne $EnabledArthurAutomationNames.Count) {
        Write-ArthurStatus "Enabled $enabledCount of $($EnabledArthurAutomationNames.Count) known Arthur automations; check automation names if any are missing."
    }

    if ($changed) {
        $json = ConvertTo-Json -InputObject $automations -Depth 20
        Set-Content -LiteralPath $AutomationFile -Value $json -Encoding UTF8
        Write-ArthurStatus 'Arthur-side automations enabled.'
    } else {
        Write-ArthurStatus 'Arthur-side automations were already enabled.'
    }
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

    $argumentList = '"' + $SupervisorScript + '" --mic-device ' + $ArthurMicDevice + ' --threshold ' + $ArthurThreshold
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
if (-not (Test-Path -LiteralPath $PromptQueueFile)) {
    New-Item -ItemType File -Path $PromptQueueFile | Out-Null
}
if (-not (Test-Path -LiteralPath $PromptResponsesFile)) {
    New-Item -ItemType File -Path $PromptResponsesFile | Out-Null
}

Enable-ArthurAutomations
Start-ArthurSupervisor
Write-ArthurStatus 'Startup complete.'
