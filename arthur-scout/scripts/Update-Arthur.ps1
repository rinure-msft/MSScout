param(
    [string] $PackageRoot = '',
    [string] $InstallRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [string] $ExpectedManifestSha256 = '',
    [ValidateSet('startup', 'updates')]
    [string] $GreetingScenario = 'updates',
    [switch] $SkipRestart,
    [switch] $WhatIf,
    [switch] $TrustedPackageSource,
    [switch] $AllowUnverifiedDeveloperPackage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$InstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$env:PYTHONNOUSERSITE = '1'

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
$PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path

function Write-ArthurUpdate {
    param([string] $Message)
    Write-Host "[Arthur update] $Message"
}

function Write-Utf8NoBom {
    param(
        [string] $Path,
        [string] $Content
    )

    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    try {
        [System.IO.File]::WriteAllText(
            $temporary,
            $Content,
            [System.Text.UTF8Encoding]::new($false)
        )
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Assert-SafePackagePath {
    param([string] $RelativePath)

    if (-not $RelativePath -or [System.IO.Path]::IsPathRooted($RelativePath)) {
        throw "Unsafe package manifest path: $RelativePath"
    }
    $normalised = $RelativePath.Replace('/', '\')
    $segments = @($normalised -split '\\')
    if ($segments -contains '..' -or $normalised.Contains(':')) {
        throw "Package manifest path escapes PackageRoot: $RelativePath"
    }
    return [System.IO.Path]::GetFullPath((Join-Path $PackageRoot $normalised))
}

function Get-ArthurRelativePath {
    param(
        [string] $BasePath,
        [string] $TargetPath
    )

    $base = [System.IO.Path]::GetFullPath($BasePath).TrimEnd('\') + '\'
    $target = [System.IO.Path]::GetFullPath($TargetPath)
    $baseUri = [System.Uri]::new($base)
    $targetUri = [System.Uri]::new($target)
    return [System.Uri]::UnescapeDataString(
        $baseUri.MakeRelativeUri($targetUri).ToString()
    ).Replace('/', '\')
}

function Get-ArthurSha256 {
    param([string] $Path)

    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($sha256.ComputeHash($stream))).Replace('-', '')
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Assert-ArthurPackageIntegrity {
    $manifestPath = Join-Path $PackageRoot 'arthur.package-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        if ($AllowUnverifiedDeveloperPackage) {
            Write-Warning 'Using an unverified developer package. Do not use this mode for downloaded releases.'
            return $null
        }
        throw "Arthur package manifest not found: $manifestPath"
    }

    $manifestHash = Get-ArthurSha256 -Path $manifestPath
    if ($ExpectedManifestSha256) {
        if ($manifestHash -ne $ExpectedManifestSha256.Trim().ToUpperInvariant()) {
            throw "Arthur package manifest hash mismatch. Expected $ExpectedManifestSha256, received $manifestHash."
        }
    }
    elseif (-not $TrustedPackageSource -and -not $AllowUnverifiedDeveloperPackage) {
        throw 'ExpectedManifestSha256 is required for downloaded update packages.'
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int] $manifest.schemaVersion -ne 1 -or -not $manifest.packageVersion) {
        throw 'Arthur package manifest schema is invalid.'
    }
    $listed = [System.Collections.Generic.HashSet[string]]::new(
        [System.StringComparer]::OrdinalIgnoreCase
    )
    foreach ($file in @($manifest.files)) {
        $relative = [string] $file.path
        $path = Assert-SafePackagePath -RelativePath $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Arthur package file is missing: $relative"
        }
        $actualLength = (Get-Item -LiteralPath $path).Length
        if ($actualLength -ne [int64] $file.bytes) {
            throw "Arthur package file length mismatch: $relative"
        }
        $actualHash = Get-ArthurSha256 -Path $path
        if ($actualHash -ne [string] $file.sha256) {
            throw "Arthur package file hash mismatch: $relative"
        }
        if (-not $listed.Add($relative.Replace('\', '/'))) {
            throw "Arthur package manifest contains a duplicate path: $relative"
        }
    }

    $actualFiles = @(
        Get-ChildItem -LiteralPath $PackageRoot -File -Recurse |
            ForEach-Object {
                (Get-ArthurRelativePath -BasePath $PackageRoot -TargetPath $_.FullName).Replace('\', '/')
            } |
            Where-Object { $_ -ne 'arthur.package-manifest.json' }
    )
    foreach ($relative in $actualFiles) {
        if (-not $listed.Contains($relative)) {
            throw "Arthur package contains an unlisted file: $relative"
        }
    }
    if ($listed.Count -ne $actualFiles.Count) {
        throw 'Arthur package manifest does not match the package file set.'
    }

    Write-ArthurUpdate "Verified package manifest for Arthur $($manifest.packageVersion): $manifestHash"
    return [ordered]@{
        hash = $manifestHash
        version = [string] $manifest.packageVersion
    }
}

function Get-ArthurPython {
    $manifestPath = Join-Path $InstallRoot 'arthur.runtime.json'
    if (Test-Path -LiteralPath $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($manifest.pythonExecutable -and (Test-Path -LiteralPath ([string] $manifest.pythonExecutable))) {
            return [System.IO.Path]::GetFullPath([string] $manifest.pythonExecutable)
        }
    }
    $localPython = Join-Path (Split-Path -Parent $InstallRoot) 'python\python.exe'
    if (Test-Path -LiteralPath $localPython) {
        return $localPython
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }
    throw 'Arthur Python is unavailable. Repair the desktop installation before updating.'
}

function Copy-ArthurDirectoryContents {
    param(
        [string] $Source,
        [string] $Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    foreach ($item in Get-ChildItem -LiteralPath $Source -Force) {
        Copy-Item -LiteralPath $item.FullName -Destination $Destination -Recurse -Force
    }
}

function Set-StagedRuntimePaths {
    param(
        [string] $StagedRuntime,
        [string] $StagedPython,
        [string] $FinalPython
    )

    $configPath = Join-Path $StagedRuntime 'arthur.config.json'
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $config.runtime.scratchpadPath = $InstallRoot
    $config.runtime.browserProfilePath = Join-Path (Split-Path -Parent $InstallRoot) 'EdgeProfile'
    Write-Utf8NoBom -Path $configPath -Content (($config | ConvertTo-Json -Depth 20) + [Environment]::NewLine)

    $runtimeManifestPath = Join-Path $StagedRuntime 'arthur.runtime.json'
    $runtimeManifest = Get-Content -LiteralPath $runtimeManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $runtimeManifest.installRoot = $InstallRoot
    $runtimeManifest.pythonExecutable = Join-Path $FinalPython 'python.exe'
    $runtimeManifest.updateStatus = 'pending'
    Write-Utf8NoBom -Path $runtimeManifestPath -Content (($runtimeManifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

    $pathFile = Get-ChildItem -LiteralPath $StagedPython -Filter 'python*._pth' -File | Select-Object -First 1
    if (-not $pathFile) {
        throw 'Staged embedded Python path configuration was not found.'
    }
    $pathLines = @(
        Get-Content -LiteralPath $pathFile.FullName |
            ForEach-Object {
                if ($_ -eq $StagedRuntime) {
                    $InstallRoot
                }
                else {
                    $_
                }
            }
    )
    [System.IO.File]::WriteAllLines(
        $pathFile.FullName,
        $pathLines,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function New-ArthurUpdateStage {
    $dataRoot = Split-Path -Parent $InstallRoot
    $stageRoot = Join-Path $dataRoot ('.update-' + [guid]::NewGuid().ToString('N'))
    $stagedRuntime = Join-Path $stageRoot 'runtime'
    $stagedPython = Join-Path $stageRoot 'python'
    $finalPython = Join-Path $dataRoot 'python'

    try {
        New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
        Copy-ArthurDirectoryContents -Source $InstallRoot -Destination $stagedRuntime
        Copy-ArthurDirectoryContents -Source $finalPython -Destination $stagedPython

        $installer = Join-Path $PackageRoot 'install.ps1'
        if (-not (Test-Path -LiteralPath $installer)) {
            throw "Arthur package installer was not found: $installer"
        }
        Invoke-Checked -FilePath 'powershell.exe' -ArgumentList @(
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            $installer,
            '-InstallRoot',
            $stagedRuntime,
            '-PythonRoot',
            $stagedPython,
            '-InstallDependencies',
            '-InstallSpeechModel'
        ) -StepName 'Staged Arthur installation' | Out-Null

        Set-StagedRuntimePaths `
            -StagedRuntime $stagedRuntime `
            -StagedPython $stagedPython `
            -FinalPython $finalPython

        return [ordered]@{
            root = $stageRoot
            runtime = $stagedRuntime
            python = $stagedPython
            finalPython = $finalPython
        }
    }
    catch {
        if (Test-Path -LiteralPath $stageRoot) {
            Remove-Item -LiteralPath $stageRoot -Recurse -Force
        }
        throw
    }
}

function Switch-ArthurStage {
    param([System.Collections.IDictionary] $Stage)

    $dataRoot = Split-Path -Parent $InstallRoot
    $rollbackRoot = Join-Path $dataRoot ('.rollback-' + [guid]::NewGuid().ToString('N'))
    $rollbackRuntime = Join-Path $rollbackRoot 'runtime'
    $rollbackPython = Join-Path $rollbackRoot 'python'
    New-Item -ItemType Directory -Path $rollbackRoot -Force | Out-Null

    $runtimeMoved = $false
    $pythonMoved = $false
    try {
        if (Test-Path -LiteralPath $InstallRoot) {
            Move-Item -LiteralPath $InstallRoot -Destination $rollbackRuntime
            $runtimeMoved = $true
        }
        if (Test-Path -LiteralPath $Stage.finalPython) {
            Move-Item -LiteralPath $Stage.finalPython -Destination $rollbackPython
            $pythonMoved = $true
        }
        Move-Item -LiteralPath $Stage.runtime -Destination $InstallRoot
        Move-Item -LiteralPath $Stage.python -Destination $Stage.finalPython
    }
    catch {
        if ((Test-Path -LiteralPath $InstallRoot) -and $runtimeMoved) {
            Remove-Item -LiteralPath $InstallRoot -Recurse -Force
        }
        if ((Test-Path -LiteralPath $Stage.finalPython) -and $pythonMoved) {
            Remove-Item -LiteralPath $Stage.finalPython -Recurse -Force
        }
        if ($runtimeMoved -and (Test-Path -LiteralPath $rollbackRuntime)) {
            Move-Item -LiteralPath $rollbackRuntime -Destination $InstallRoot
        }
        if ($pythonMoved -and (Test-Path -LiteralPath $rollbackPython)) {
            Move-Item -LiteralPath $rollbackPython -Destination $Stage.finalPython
        }
        throw
    }

    return [ordered]@{
        root = $rollbackRoot
        runtime = $rollbackRuntime
        python = $rollbackPython
        hadRuntime = $runtimeMoved
        hadPython = $pythonMoved
    }
}

function Restore-ArthurStage {
    param(
        [System.Collections.IDictionary] $Stage,
        [System.Collections.IDictionary] $Rollback
    )

    Stop-ArthurProcesses
    $failedRoot = Join-Path (Split-Path -Parent $InstallRoot) ('.failed-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $failedRoot -Force | Out-Null
    if (Test-Path -LiteralPath $InstallRoot) {
        Move-Item -LiteralPath $InstallRoot -Destination (Join-Path $failedRoot 'runtime')
    }
    if (Test-Path -LiteralPath $Stage.finalPython) {
        Move-Item -LiteralPath $Stage.finalPython -Destination (Join-Path $failedRoot 'python')
    }
    if ($Rollback.hadRuntime -and (Test-Path -LiteralPath $Rollback.runtime)) {
        Move-Item -LiteralPath $Rollback.runtime -Destination $InstallRoot
    }
    if ($Rollback.hadPython -and (Test-Path -LiteralPath $Rollback.python)) {
        Move-Item -LiteralPath $Rollback.python -Destination $Stage.finalPython
    }
    Remove-Item -LiteralPath $failedRoot -Recurse -Force -ErrorAction SilentlyContinue
}

function Complete-ArthurRuntimeManifest {
    $manifestPath = Join-Path $InstallRoot 'arthur.runtime.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $manifest.updateStatus = 'complete'
    Write-Utf8NoBom -Path $manifestPath -Content (($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
}

function Remove-StaleArthurUpdateDirectories {
    $dataRoot = Split-Path -Parent $InstallRoot
    $prefix = [System.IO.Path]::GetFullPath($dataRoot).TrimEnd('\') + '\'
    $staleDirectories = @(
        Get-ChildItem -LiteralPath $dataRoot -Directory -Force |
            Where-Object {
                $_.Name -like '.update-*' -or
                $_.Name -like '.rollback-*' -or
                $_.Name -like '.failed-*'
            }
    )
    foreach ($directory in $staleDirectories) {
        $resolved = [System.IO.Path]::GetFullPath($directory.FullName)
        if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe Arthur update cleanup path: $resolved"
        }
        try {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
        catch {
            Write-Warning "Could not remove stale Arthur update directory $resolved`: $($_.Exception.Message)"
        }
    }
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
    $patterns = @(
        'arthur_supervisor.py',
        'arthur_voice_bridge.py',
        'arthur_prompt_worker.py',
        'arthur_dashboard_server.py'
    )
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $cmd = $_.CommandLine
        $cmd -and
            $cmd.IndexOf($InstallRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            ($patterns | Where-Object { $cmd -like "*$_*" })
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
    $archiveRoot = Join-Path (Split-Path -Parent $InstallRoot) 'archives'
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
    Copy-Item -Path (Join-Path $srcRoot '*.py') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Start-Arthur.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Update-Arthur.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Migrate-ArthurToLocalAppData.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Remove-ArthurLegacyData.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $scriptsRoot 'Install-ArthurZipformerModel.ps1') -Destination $InstallRoot -Force
    Copy-Item -LiteralPath (Join-Path $configRoot 'automations.template.json') -Destination (Join-Path $InstallRoot 'automations.template.json') -Force
    Copy-Item -LiteralPath (Join-Path $PackageRoot 'requirements.txt') -Destination $InstallRoot -Force

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
    $pythonExecutable = Get-ArthurPython
    $configPath = Join-Path $InstallRoot 'arthur.config.json'
    Invoke-Checked -FilePath $pythonExecutable -ArgumentList @((Join-Path $InstallRoot 'arthur_config.py'), '--config', $configPath, '--validate') -StepName 'Config validation' | Out-Null
    Invoke-Checked -FilePath $pythonExecutable -ArgumentList @((Join-Path $InstallRoot 'arthur_preflight.py'), '--strict', '--write') -StepName 'Preflight validation' | Out-Null

    $smokePath = Join-Path $InstallRoot 'arthur_voice_command_smoke_test.json'
    $smokeOutput = Invoke-Checked -FilePath $pythonExecutable -ArgumentList @((Join-Path $InstallRoot 'arthur_voice_bridge.py'), '--smoke-test-commands') -StepName 'Voice command smoke tests'
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
    $pythonExecutable = Get-ArthurPython
    $commit = Get-PackageCommit
    $versionArgs = @((Join-Path $InstallRoot 'arthur_version.py'), '--write')
    if ($commit) {
        $versionArgs += @('--commit-sha', $commit)
    }
    Invoke-Checked -FilePath $pythonExecutable -ArgumentList $versionArgs -StepName 'Version manifest update' | Out-Null
    Invoke-Checked -FilePath $pythonExecutable -ArgumentList @((Join-Path $InstallRoot 'arthur_status_dashboard.py')) -StepName 'Dashboard generation' | Out-Null
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

function Wait-ArthurHealth {
    $deadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Seconds 2
        $health = Get-ArthurHealth
        $voice = $health.voiceHeartbeat
        if ($voice -and $voice.pid -and $voice.status -notin @('error', 'mic_timeout')) {
            return $health
        }
    } while ((Get-Date) -lt $deadline)
    throw 'Arthur did not produce a healthy voice heartbeat after the update.'
}

$report = [ordered]@{
    status = 'running'
    packageRoot = $PackageRoot
    installRoot = $InstallRoot
    startedAt = (Get-Date).ToString('o')
    steps = @()
}
$backupPath = $null
$stage = $null
$rollback = $null
$stopped = $false
$switched = $false

try {
    $manifestInfo = Assert-ArthurPackageIntegrity
    if ($manifestInfo) {
        $report.packageManifestSha256 = $manifestInfo.hash
        $report.packageVersion = $manifestInfo.version
        $report.steps += 'verified package manifest and file hashes'
    }
    else {
        $report.steps += 'accepted explicit unverified developer package'
    }

    if ($WhatIf) {
        Write-ArthurUpdate "WhatIf: would stage a verified update, install pinned dependencies and Zipformer, atomically switch runtime and Python, validate, restart, and retain rollback until healthy."
        $report.status = 'what-if'
    } else {
        $backupPath = Backup-ArthurLive
        $report.backupPath = $backupPath
        $report.steps += 'archived current live Arthur files'
        Stop-ArthurProcesses
        $stopped = $true
        $report.steps += 'stopped existing Arthur processes'
        $stage = New-ArthurUpdateStage
        $report.steps += 'staged runtime, private Python, pinned dependencies and verified speech model'
        $rollback = Switch-ArthurStage -Stage $stage
        $switched = $true
        $report.steps += 'atomically switched runtime and private Python'
        Invoke-ArthurPostUpdate
        $report.steps += 'updated version manifest and regenerated local dashboard'
        Start-Arthur
        $report.steps += 'restarted Arthur'
        if (-not $SkipRestart) {
            $report.health = Wait-ArthurHealth
            $report.steps += 'confirmed healthy voice heartbeat'
        }
        $report.status = 'passed'
        if ($rollback -and (Test-Path -LiteralPath $rollback.root)) {
            Remove-Item -LiteralPath $rollback.root -Recurse -Force
        }
        Complete-ArthurRuntimeManifest
        Remove-StaleArthurUpdateDirectories
        $report.steps += 'marked the runtime complete and removed stale update staging'
    }
} catch {
    $report.status = 'failed'
    $report.error = $_.Exception.Message
    if ($switched -and $stage -and $rollback) {
        try {
            Restore-ArthurStage -Stage $stage -Rollback $rollback
            $report.restoredFrom = $rollback.root
            $report.steps += 'restored the previous runtime and private Python'
            if (-not $SkipRestart) {
                Start-Arthur
                $report.steps += 'restarted Arthur after rollback'
                $report.health = Wait-ArthurHealth
            }
        } catch {
            $report.restoreError = $_.Exception.Message
        }
    }
    elseif ($stopped -and -not $SkipRestart) {
        try {
            Start-Arthur
            $report.steps += 'restarted unchanged Arthur runtime after staging failure'
            $report.health = Wait-ArthurHealth
        }
        catch {
            $report.restoreError = $_.Exception.Message
        }
    }
    throw
} finally {
    if ($stage -and (Test-Path -LiteralPath $stage.root)) {
        Remove-Item -LiteralPath $stage.root -Recurse -Force -ErrorAction SilentlyContinue
    }
    $report.completedAt = (Get-Date).ToString('o')
    $reportPath = Join-Path $InstallRoot 'arthur_update_report.json'
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    $report | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $reportPath -Encoding UTF8
    Write-ArthurUpdate "Update report: $reportPath"
    Write-Output ($report | ConvertTo-Json -Depth 20)
}
