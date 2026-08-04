param(
    [string] $PackageRoot = '',
    [string] $InstallRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [ValidateSet('startup', 'updates')]
    [string] $GreetingScenario = 'updates',
    [switch] $SkipRestart,
    [switch] $WhatIf
)

$ErrorActionPreference = 'Stop'

if (-not $PackageRoot -or $PackageRoot.Trim().Length -eq 0) {
    $scriptParent = Split-Path -Parent $PSCommandPath
    $packageCandidate = Split-Path -Parent $scriptParent
    if ((Test-Path -LiteralPath (Join-Path $packageCandidate 'src')) -and (Test-Path -LiteralPath (Join-Path $packageCandidate 'config'))) {
        $PackageRoot = $packageCandidate
    } elseif ((Test-Path -LiteralPath (Join-Path $scriptParent 'src')) -and (Test-Path -LiteralPath (Join-Path $scriptParent 'config'))) {
        $PackageRoot = $scriptParent
    } else {
        throw 'PackageRoot was not provided and could not be inferred. Run from an arthur-scout package or pass -PackageRoot.'
    }
}

function Write-ArthurUpdate {
    param([string] $Message)
    Write-Host "[Arthur update] $Message"
}

function Invoke-Checked {
    param(
        [string] $FilePath,
        [string[]] $ArgumentList,
        [string] $StepName
    )
    $output = & $FilePath @ArgumentList 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "$StepName failed: $($output -join [Environment]::NewLine)"
    }
    return $output
}

function Get-PackageCommit {
    try {
        return (git -C $PackageRoot rev-parse --short HEAD 2>$null).Trim()
    } catch {
        return ''
    }
}

function Stop-ArthurProcesses {
    $patterns = @('arthur_supervisor.py', 'arthur_voice_bridge.py', 'arthur_prompt_worker.py')
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $cmd = $_.CommandLine
        $cmd -and ($patterns | Where-Object { $cmd -like "*$_*" })
    }
    foreach ($process in $processes) {
        Stop-Process -Id $process.ProcessId -Force
        Write-ArthurUpdate "Stopped PID $($process.ProcessId): $($process.Name)"
    }
    Start-Sleep -Seconds 2
}

function Backup-ArthurLive {
    if (-not (Test-Path -LiteralPath $InstallRoot)) {
        Write-ArthurUpdate "No existing Arthur install found to back up: $InstallRoot"
        return $null
    }
    $archiveRoot = Join-Path $InstallRoot 'arthur_archive'
    New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $staging = Join-Path $env:TEMP "arthur_live_backup_$stamp"
    $zip = Join-Path $archiveRoot "arthur_live_backup_$stamp.zip"
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $patterns = @('*.py', '*.ps1', '*.json', '*.jsonl', '*.md', '*.txt', '*.csv', 'automations.template.json')
    foreach ($pattern in $patterns) {
        Get-ChildItem -LiteralPath $InstallRoot -File -Filter $pattern -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notin @('arthur_update_report.json') } |
            ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $staging -Force }
    }
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip -Force
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    Write-ArthurUpdate "Backed up live Arthur files to $zip"
    return $zip
}

function Restore-ArthurBackup {
    param([string] $BackupPath)
    if (-not $BackupPath -or -not (Test-Path -LiteralPath $BackupPath)) {
        throw "Arthur backup archive not found: $BackupPath"
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $restore = Join-Path $env:TEMP "arthur_restore_$stamp"
    Remove-Item -LiteralPath $restore -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $restore -Force | Out-Null
    Expand-Archive -LiteralPath $BackupPath -DestinationPath $restore -Force
    Copy-Item -Path (Join-Path $restore '*') -Destination $InstallRoot -Recurse -Force
    Remove-Item -LiteralPath $restore -Recurse -Force -ErrorAction SilentlyContinue
    Write-ArthurUpdate "Restored Arthur files from $BackupPath"
}

function Copy-ArthurPackage {
    if (-not (Test-Path -LiteralPath $PackageRoot)) {
        throw "Package root not found: $PackageRoot"
    }
    $srcRoot = Join-Path $PackageRoot 'src'
    $scriptsRoot = Join-Path $PackageRoot 'scripts'
    $configRoot = Join-Path $PackageRoot 'config'
    foreach ($required in @($srcRoot, $scriptsRoot, $configRoot)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Required package directory not found: $required"
        }
    }

    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $srcRoot '*.py') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Start-Arthur.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Update-Arthur.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $configRoot 'automations.template.json') -Destination (Join-Path $InstallRoot 'automations.template.json') -Force

    $configTarget = Join-Path $InstallRoot 'arthur.config.json'
    if (-not (Test-Path -LiteralPath $configTarget)) {
        Copy-Item -LiteralPath (Join-Path $configRoot 'arthur.config.template.json') -Destination $configTarget
        Write-ArthurUpdate "Created config template at $configTarget. Fill placeholders before starting Arthur."
    } else {
        Write-ArthurUpdate "Preserved local config: $configTarget"
    }

    foreach ($file in 'arthur_prompt_queue.jsonl','arthur_prompt_responses.jsonl') {
        $path = Join-Path $InstallRoot $file
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType File -Path $path | Out-Null
        }
    }
}

function Invoke-ArthurValidation {
    $configPath = Join-Path $InstallRoot 'arthur.config.json'
    Invoke-Checked -FilePath 'python' -ArgumentList @((Join-Path $InstallRoot 'arthur_config.py'), '--config', $configPath, '--validate') -StepName 'Config validation' | Out-Null
    Invoke-Checked -FilePath 'python' -ArgumentList @((Join-Path $InstallRoot 'arthur_preflight.py'), '--strict', '--write') -StepName 'Preflight validation' | Out-Null

    $smokePath = Join-Path $InstallRoot 'arthur_voice_command_smoke_test.json'
    $smokeOutput = Invoke-Checked -FilePath 'python' -ArgumentList @((Join-Path $InstallRoot 'arthur_voice_bridge.py'), '--smoke-test-commands') -StepName 'Voice command smoke tests'
    $raw = $smokeOutput -join [Environment]::NewLine
    $start = $raw.IndexOf('{')
    if ($start -lt 0) {
        throw 'Voice command smoke tests did not produce JSON output.'
    }
    $json = $raw.Substring($start)
    Set-Content -LiteralPath $smokePath -Value $json -Encoding UTF8
    $result = $json | ConvertFrom-Json
    if ($result.status -ne 'passed') {
        throw "Voice command smoke tests failed: $json"
    }
    Write-ArthurUpdate "Smoke tests passed: commands=$($result.commands), aliases=$($result.aliases)."
}

function Invoke-ArthurPostUpdate {
    $commit = Get-PackageCommit
    $versionArgs = @((Join-Path $InstallRoot 'arthur_version.py'), '--write')
    if ($commit) {
        $versionArgs += @('--commit-sha', $commit)
    }
    Invoke-Checked -FilePath 'python' -ArgumentList $versionArgs -StepName 'Version manifest update' | Out-Null
    Invoke-Checked -FilePath 'python' -ArgumentList @((Join-Path $InstallRoot 'arthur_automation_sync.py'), '--template', (Join-Path $InstallRoot 'automations.template.json')) -StepName 'Automation sync' | Out-Null
    Invoke-Checked -FilePath 'python' -ArgumentList @((Join-Path $InstallRoot 'arthur_status_dashboard.py')) -StepName 'Dashboard generation' | Out-Null
}

function Start-Arthur {
    if ($SkipRestart) {
        Write-ArthurUpdate 'Skipping restart by request.'
        return
    }
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot 'Start-Arthur.ps1') -GreetingScenario $GreetingScenario
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur restart failed.'
    }
}

function Get-ArthurHealth {
    $voice = Join-Path $InstallRoot 'arthur_voice_bridge_heartbeat.json'
    $worker = Join-Path $InstallRoot 'arthur_prompt_worker_heartbeat.json'
    return [ordered]@{
        voiceHeartbeat = if (Test-Path -LiteralPath $voice) { Get-Content -LiteralPath $voice -Raw | ConvertFrom-Json } else { $null }
        workerHeartbeat = if (Test-Path -LiteralPath $worker) { Get-Content -LiteralPath $worker -Raw | ConvertFrom-Json } else { $null }
    }
}

$report = [ordered]@{
    status = 'running'
    packageRoot = $PackageRoot
    installRoot = $InstallRoot
    startedAt = (Get-Date).ToString('o')
    steps = @()
}
$backupPath = $null

try {
    if ($WhatIf) {
        Write-ArthurUpdate "WhatIf: would back up $InstallRoot, update from $PackageRoot, preserve arthur.config.json, validate, restart, regenerate dashboard, and report status."
        $report.status = 'what-if'
    } else {
        $backupPath = Backup-ArthurLive
        $report.backupPath = $backupPath
        $report.steps += 'archived current live Arthur files'
        Stop-ArthurProcesses
        $report.steps += 'stopped existing Arthur processes'
        Copy-ArthurPackage
        $report.steps += 'copied package files and preserved config'
        Invoke-ArthurValidation
        $report.steps += 'validated config, preflight, and smoke tests'
        Invoke-ArthurPostUpdate
        $report.steps += 'updated version manifest, synced automations, and regenerated dashboard'
        Start-Arthur
        $report.steps += 'restarted Arthur'
        Start-Sleep -Seconds 6
        $report.health = Get-ArthurHealth
        $report.status = 'passed'
    }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    if ($backupPath) {
        try {
            Stop-ArthurProcesses
            Restore-ArthurBackup -BackupPath $backupPath
            $report.restoredFrom = $backupPath
            $report.steps += 'restored last known-good Arthur files'
            if (-not $SkipRestart) {
                Start-Arthur
                $report.steps += 'restarted Arthur after rollback'
                Start-Sleep -Seconds 6
                $report.health = Get-ArthurHealth
            }
        } catch {
            $report.restoreError = $_.Exception.Message
        }
    }
    throw
} finally {
    $report.completedAt = (Get-Date).ToString('o')
    $reportPath = Join-Path $InstallRoot 'arthur_update_report.json'
    $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-ArthurUpdate "Update report: $reportPath"
    Write-Output ($report | ConvertTo-Json -Depth 20)
}
