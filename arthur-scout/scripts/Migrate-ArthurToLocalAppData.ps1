[CmdletBinding()]
param(
    [string] $PackageRoot = '',
    [string] $SourceRoot = "$env:USERPROFILE\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad",
    [string] $DestinationRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [switch] $SkipStop
)

$ErrorActionPreference = 'Stop'

if (-not $PackageRoot) {
    $PackageRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)
$sourceConfig = Join-Path $SourceRoot 'arthur.config.json'
if (-not (Test-Path -LiteralPath $sourceConfig)) {
    throw "Arthur config was not found: $sourceConfig"
}

if ([string]::Equals($SourceRoot, $DestinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Arthur is already using the requested local runtime directory.'
}

if (-not $SkipStop) {
    $patterns = @(
        'arthur_supervisor.py',
        'arthur_voice_bridge.py',
        'arthur_prompt_worker.py',
        'arthur_dashboard_server.py'
    )
    $runtimeRoots = @($SourceRoot, $DestinationRoot)
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $commandLine = $_.CommandLine
        $matchesRoot = $commandLine -and ($runtimeRoots | Where-Object {
            $commandLine.IndexOf($_, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        })
        $matchesRoot -and ($patterns | Where-Object { $commandLine -like "*$_*" })
    }
    foreach ($arthurProcess in $processes) {
        Stop-Process -Id $arthurProcess.ProcessId -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 2
}

New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
Copy-Item -Path (Join-Path $PackageRoot 'src\*.py') -Destination $DestinationRoot -Force
foreach ($script in 'Start-Arthur.ps1','Update-Arthur.ps1','Install-ArthurZipformerModel.ps1','Migrate-ArthurToLocalAppData.ps1','Remove-ArthurLegacyData.ps1') {
    Copy-Item -LiteralPath (Join-Path $PackageRoot "scripts\$script") -Destination $DestinationRoot -Force
}
Copy-Item -LiteralPath (Join-Path $PackageRoot 'config\automations.template.json') -Destination (Join-Path $DestinationRoot 'automations.template.json') -Force
Copy-Item -LiteralPath (Join-Path $PackageRoot 'requirements.txt') -Destination $DestinationRoot -Force

$statePatterns = @(
    'arthur_*.json',
    'arthur_*.jsonl',
    'arthur_*.log',
    'arthur_*.md',
    'arthur_*.csv',
    'arthur_*.txt'
)
foreach ($pattern in $statePatterns) {
    Get-ChildItem -LiteralPath $SourceRoot -File -Filter $pattern -ErrorAction SilentlyContinue |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $DestinationRoot -Force }
}

$sourceModels = Join-Path $SourceRoot 'models'
$destinationModels = Join-Path $DestinationRoot 'models'
if (Test-Path -LiteralPath $sourceModels) {
    Copy-Item -LiteralPath $sourceModels -Destination $DestinationRoot -Recurse -Force
}

$config = Get-Content -LiteralPath $sourceConfig -Raw | ConvertFrom-Json
$config.runtime.scratchpadPath = $DestinationRoot
if ($config.speechRecognition.modelDirectory -and -not [System.IO.Path]::IsPathRooted([string] $config.speechRecognition.modelDirectory)) {
    $config.speechRecognition.modelDirectory = 'models\zipformer-en-balanced-int8'
}
$destinationConfig = Join-Path $DestinationRoot 'arthur.config.json'
$temporaryConfig = "$destinationConfig.$([guid]::NewGuid().ToString('N')).tmp"
$configJson = ($config | ConvertTo-Json -Depth 20) + [Environment]::NewLine
[System.IO.File]::WriteAllText(
    $temporaryConfig,
    $configJson,
    [System.Text.UTF8Encoding]::new($false)
)
Move-Item -LiteralPath $temporaryConfig -Destination $destinationConfig -Force

$report = [ordered]@{
    status = 'prepared'
    sourceRoot = $SourceRoot
    destinationRoot = $DestinationRoot
    destinationConfig = $destinationConfig
    modelsCopied = Test-Path -LiteralPath $destinationModels
    migratedAt = (Get-Date).ToString('o')
    sourcePreserved = $true
}
$reportPath = Join-Path $DestinationRoot 'arthur_migration_report.json'
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8
$report | ConvertTo-Json -Depth 10
