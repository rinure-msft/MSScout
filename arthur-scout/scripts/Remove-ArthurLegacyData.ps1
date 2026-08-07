[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)]
    [string] $SourceRoot,
    [string] $BackupRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\legacy-backups'),
    [switch] $Remove
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$sourceRootPath = (Resolve-Path -LiteralPath $SourceRoot).Path
$backupRootPath = [System.IO.Path]::GetFullPath($BackupRoot)
if ($sourceRootPath -notmatch '(?i)[\\/]OneDrive(?:[^\\/]*)[\\/]') {
    throw "Legacy cleanup only supports OneDrive source directories: $sourceRootPath"
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceRootPath 'arthur.config.json'))) {
    throw "Arthur legacy config was not found: $sourceRootPath"
}

$fileNames = @(
    'arthur.config.json',
    'arthur.config.template.json',
    'arthur.version.json',
    'automations.template.json',
    'requirements.txt',
    'requirements-nemotron.txt',
    'speech-benchmark-plan.json',
    'voice-commands.json',
    'Start-Arthur.ps1',
    'Start-ArthurSpeechBenchmark.ps1',
    'Install-ArthurNemotronModel.ps1',
    'Install-ArthurZipformerModel.ps1',
    'Migrate-ArthurToLocalAppData.ps1',
    'Update-Arthur.ps1',
    'arthur_model_comparison.wav',
    'asr_comparison_clean.wav'
)
$directoryNames = @(
    '__pycache__',
    'arthur_archive',
    'arthur_edge_profile',
    'models',
    'speech-benchmark'
)

$candidates = [System.Collections.Generic.List[System.IO.FileSystemInfo]]::new()
Get-ChildItem -LiteralPath $sourceRootPath -Force | ForEach-Object {
    $isArthurFile = (-not $_.PSIsContainer) -and (
        $_.Name -like 'arthur_*' -or
        $fileNames -contains $_.Name
    )
    $isArthurDirectory = $_.PSIsContainer -and ($directoryNames -contains $_.Name)
    if ($isArthurFile -or $isArthurDirectory) {
        $candidates.Add($_)
    }
}

$files = @(
    $candidates | ForEach-Object {
        if ($_.PSIsContainer) {
            Get-ChildItem -LiteralPath $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue
        } else {
            $_
        }
    }
)
$totalBytes = ($files | Measure-Object -Property Length -Sum).Sum
$summary = [ordered]@{
    sourceRoot = $sourceRootPath
    candidates = $candidates.Count
    files = $files.Count
    bytes = $totalBytes
    removeRequested = [bool] $Remove
}

if (-not $Remove) {
    $summary.status = 'audit-only'
    $summary | ConvertTo-Json -Depth 10
    return
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = Join-Path $backupRootPath "Scratchpad-$stamp"
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
foreach ($candidate in $candidates) {
    Copy-Item -LiteralPath $candidate.FullName -Destination $backupPath -Recurse -Force
}

$backupFiles = @(Get-ChildItem -LiteralPath $backupPath -Recurse -File -Force)
$backupBytes = ($backupFiles | Measure-Object -Property Length -Sum).Sum
if (($backupFiles.Count -ne $files.Count) -or ($backupBytes -ne $totalBytes)) {
    throw "Legacy backup verification failed: $backupPath"
}

foreach ($candidate in $candidates) {
    if ($PSCmdlet.ShouldProcess($candidate.FullName, 'Remove migrated Arthur legacy data')) {
        Remove-Item -LiteralPath $candidate.FullName -Recurse -Force
    }
}

$summary.status = 'removed'
$summary.backupPath = $backupPath
$summary.backupFiles = $backupFiles.Count
$summary.backupBytes = $backupBytes
$summary.completedAt = (Get-Date).ToString('o')
$reportPath = Join-Path $backupPath 'arthur_legacy_cleanup_report.json'
$summary | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 10
