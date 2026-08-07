[CmdletBinding()]
param(
    [ValidateSet('startup', 'updates')]
    [string] $GreetingScenario = 'startup'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scratch = $PSScriptRoot
$configFile = Join-Path $scratch 'arthur.config.json'
if (-not (Test-Path -LiteralPath $configFile)) {
    throw "Arthur config file was not found: $configFile"
}
$arthurConfig = Get-Content -LiteralPath $configFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($arthurConfig -and $arthurConfig.runtime -and $arthurConfig.runtime.scratchpadPath) {
    $scratch = [System.IO.Path]::GetFullPath([string] $arthurConfig.runtime.scratchpadPath)
}

$bridgeScript = Join-Path $scratch 'arthur_voice_bridge.py'
$supervisorScript = Join-Path $scratch 'arthur_supervisor.py'
$supervisorStdoutLog = Join-Path $scratch 'arthur_supervisor_stdout.log'
$supervisorStderrLog = Join-Path $scratch 'arthur_supervisor_stderr.log'
$promptQueueFile = Join-Path $scratch 'arthur_prompt_queue.jsonl'
$promptResponsesFile = Join-Path $scratch 'arthur_prompt_responses.jsonl'
$preflightScript = Join-Path $scratch 'arthur_preflight.py'
$versionScript = Join-Path $scratch 'arthur_version.py'
$arthurMicDevice = if ($null -ne $arthurConfig.microphone.deviceIndex) { [int] $arthurConfig.microphone.deviceIndex } else { 1 }
$arthurThreshold = if ($null -ne $arthurConfig.microphone.threshold) { [int] $arthurConfig.microphone.threshold } else { 350 }
$arthurTts = if ($arthurConfig.voice.tts) { [string] $arthurConfig.voice.tts } else { 'edge' }
$arthurTimezone = if ($arthurConfig.timezone) { [string] $arthurConfig.timezone } else { 'Europe/London' }

function Write-ArthurStatus {
    param([string] $Message)
    Write-Host "[Arthur startup] $Message"
}

function Resolve-ArthurPython {
    if ($env:ARTHUR_PYTHON -and (Test-Path -LiteralPath $env:ARTHUR_PYTHON)) {
        return [System.IO.Path]::GetFullPath($env:ARTHUR_PYTHON)
    }

    $manifestPath = Join-Path $scratch 'arthur.runtime.json'
    if (Test-Path -LiteralPath $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.pythonExecutable -and (Test-Path -LiteralPath ([string] $manifest.pythonExecutable))) {
            return [System.IO.Path]::GetFullPath([string] $manifest.pythonExecutable)
        }
    }

    $localPython = Join-Path (Split-Path -Parent $scratch) 'python\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        return $localPython
    }

    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }
    throw 'Arthur Python is unavailable. Repair the desktop installation or run install.ps1 -InstallDependencies.'
}

$pythonExecutable = Resolve-ArthurPython
$env:ARTHUR_CONFIG = $configFile
$env:ARTHUR_PYTHON = $pythonExecutable
$env:PYTHONNOUSERSITE = '1'

function Test-ArthurConfig {
    $configHelper = Join-Path $scratch 'arthur_config.py'
    if (-not (Test-Path -LiteralPath $configHelper)) {
        throw "Arthur config helper not found: $configHelper"
    }
    $result = & $pythonExecutable -s $configHelper --config $configFile --validate 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus ($result -join ' ')
}

function Test-ArthurPreflight {
    if (-not (Test-Path -LiteralPath $preflightScript)) {
        throw "Arthur preflight script not found: $preflightScript"
    }
    $result = & $pythonExecutable -s $preflightScript --strict --write 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus 'Arthur preflight checks passed.'
}

function Update-ArthurVersionManifest {
    if (-not (Test-Path -LiteralPath $versionScript)) {
        Write-ArthurStatus "Arthur version script not found: $versionScript"
        return
    }
    $arguments = @($versionScript, '--write')
    if ($env:ARTHUR_COMMIT_SHA) {
        $arguments += @('--commit-sha', $env:ARTHUR_COMMIT_SHA)
    }
    $result = & $pythonExecutable -s @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($result -join [Environment]::NewLine)
    }
    Write-ArthurStatus 'Arthur version manifest updated.'
}

function Start-ArthurSupervisor {
    if (-not (Test-Path -LiteralPath $bridgeScript)) {
        throw "Arthur voice bridge not found: $bridgeScript"
    }
    if (-not (Test-Path -LiteralPath $supervisorScript)) {
        throw "Arthur supervisor not found: $supervisorScript"
    }

    $existing = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        $_.Name -match '^python(w)?\.exe$' -and
            $commandLine -and
            $commandLine.IndexOf($scratch, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $commandLine -like '*arthur_supervisor.py*'
    }
    if ($existing) {
        $ids = ($existing | ForEach-Object { $_.ProcessId }) -join ', '
        Write-ArthurStatus "Arthur supervisor already running. PID(s): $ids"
        return
    }

    $argumentList = '-s "' + $supervisorScript + '" --mic-device ' + $arthurMicDevice + ' --threshold ' + $arthurThreshold + ' --greeting-scenario ' + $GreetingScenario
    $env:ARTHUR_TTS = $arthurTts
    $env:ARTHUR_TIMEZONE = $arthurTimezone
    $env:ARTHUR_GREETING_SCENARIO = $GreetingScenario
    $process = Start-Process -FilePath $pythonExecutable `
        -ArgumentList $argumentList `
        -WorkingDirectory $scratch `
        -WindowStyle Hidden `
        -RedirectStandardOutput $supervisorStdoutLog `
        -RedirectStandardError $supervisorStderrLog `
        -PassThru

    Start-Sleep -Seconds 10
    $running = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if (-not $running) {
        $errorTail = ''
        if (Test-Path -LiteralPath $supervisorStderrLog) {
            $errorTail = (Get-Content -LiteralPath $supervisorStderrLog -Tail 20) -join [Environment]::NewLine
        }
        throw "Arthur supervisor exited during startup. Check $supervisorStderrLog. $errorTail"
    }
    Write-ArthurStatus "Arthur supervisor started. PID: $($process.Id)"
}

New-Item -ItemType Directory -Path $scratch -Force | Out-Null
Test-ArthurConfig
Test-ArthurPreflight
Update-ArthurVersionManifest
foreach ($path in @($promptQueueFile, $promptResponsesFile)) {
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType File -Path $path | Out-Null
    }
}
Start-ArthurSupervisor
Write-ArthurStatus 'Startup complete.'
