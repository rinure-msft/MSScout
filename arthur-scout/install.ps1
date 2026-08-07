[CmdletBinding()]
param(
    [string] $InstallRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [string] $PythonRoot = '',
    [switch] $InstallDependencies,
    [switch] $InstallSpeechModel,
    [switch] $CreateScheduledTask,
    [switch] $AllowCloudStorage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$pythonVersion = '3.13.14'
$pythonArchiveUrl = "https://www.python.org/ftp/python/$pythonVersion/python-$pythonVersion-embed-amd64.zip"
$pythonArchiveSha256 = '90B4E5B9898B72D744650524BFF92377C367F44BD5FBD09E3148656C080AD907'
$pipBootstrapUrl = 'https://raw.githubusercontent.com/pypa/get-pip/f6f644156f23dfe9acc06e7b9ca75eee311f2e37/public/get-pip.py'
$pipBootstrapSha256 = 'FB24E693BAB954209A063D90953621412CCAD4A500905A726286E038F508DDF6'
$packageRoot = Split-Path -Parent $PSCommandPath
$installRootPath = [System.IO.Path]::GetFullPath($InstallRoot)
if (-not $PythonRoot) {
    $PythonRoot = Join-Path (Split-Path -Parent $installRootPath) 'python'
}
$pythonRootPath = [System.IO.Path]::GetFullPath($PythonRoot)

function Write-ArthurInstall {
    param([string] $Message)
    Write-Host "[Arthur install] $Message"
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

function Get-ArthurPackageVersion {
    $versionFile = Join-Path $packageRoot 'src\arthur_version.py'
    $versionText = Get-Content -LiteralPath $versionFile -Raw
    $match = [regex]::Match($versionText, 'PACKAGE_VERSION\s*=\s*"(?<version>[^"]+)"')
    if (-not $match.Success) {
        throw "Arthur package version could not be read from $versionFile"
    }
    return $match.Groups['version'].Value
}

function Test-CloudPath {
    param([string] $Path)
    return $Path -match '(?i)[\\/](OneDrive(?: - [^\\/]+)?|Dropbox|Google Drive)(?:[\\/]|$)'
}

function Write-Utf8NoBom {
    param(
        [string] $Path,
        [string] $Content
    )
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllText(
        $temporary,
        $Content,
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Merge-ArthurConfigDefaults {
    param(
        [pscustomobject] $Defaults,
        [pscustomobject] $Current
    )

    foreach ($property in $Defaults.PSObject.Properties) {
        $existing = $Current.PSObject.Properties[$property.Name]
        if (-not $existing) {
            $Current | Add-Member -NotePropertyName $property.Name -NotePropertyValue $property.Value
            continue
        }
        if (($property.Value -is [pscustomobject]) -and ($existing.Value -is [pscustomobject])) {
            Merge-ArthurConfigDefaults -Defaults $property.Value -Current $existing.Value | Out-Null
        }
    }
    return $Current
}

function Set-ArthurPythonPath {
    param(
        [string] $DestinationRoot,
        [string] $ModuleRoot
    )

    $pathFile = Get-ChildItem -LiteralPath $DestinationRoot -Filter 'python*._pth' -File | Select-Object -First 1
    if (-not $pathFile) {
        throw 'Embedded Python path configuration was not found.'
    }
    $pythonLibrary = 'python' + (($pythonVersion -split '\.')[0..1] -join '') + '.zip'
    $pathContent = @(
        $pythonLibrary,
        '.',
        'Lib',
        'Lib\site-packages',
        $ModuleRoot,
        'import site'
    )
    [System.IO.File]::WriteAllText(
        $pathFile.FullName,
        ($pathContent -join [Environment]::NewLine) + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Install-ArthurPip {
    param([string] $PythonExecutable)

    $downloadRoot = Join-Path $env:TEMP "arthur-pip-$([guid]::NewGuid().ToString('N'))"
    $pipBootstrap = Join-Path $downloadRoot 'get-pip.py'
    New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
    try {
        Invoke-WebRequest -Uri $pipBootstrapUrl -OutFile $pipBootstrap -UseBasicParsing
        $pipHash = Get-ArthurSha256 -Path $pipBootstrap
        if ($pipHash -ne $pipBootstrapSha256) {
            throw "pip bootstrap hash mismatch. Expected $pipBootstrapSha256, received $pipHash."
        }
        $env:PYTHONNOUSERSITE = '1'
        $pipOutput = & $PythonExecutable -s $pipBootstrap --no-warn-script-location 2>&1
        $pipExitCode = $LASTEXITCODE
        foreach ($line in $pipOutput) {
            Write-ArthurInstall ([string] $line)
        }
        if ($pipExitCode -ne 0) {
            throw 'Private pip bootstrap failed.'
        }
    }
    finally {
        if (Test-Path -LiteralPath $downloadRoot) {
            Remove-Item -LiteralPath $downloadRoot -Recurse -Force
        }
    }
}

function Install-ArthurPython {
    param(
        [string] $DestinationRoot,
        [string] $ModuleRoot
    )

    $pythonExecutable = Join-Path $DestinationRoot 'python.exe'
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        $downloadRoot = Join-Path $env:TEMP "arthur-python-$([guid]::NewGuid().ToString('N'))"
        $archive = Join-Path $downloadRoot "python-$pythonVersion-embed-amd64.zip"
        New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
        try {
            Write-ArthurInstall "Downloading private Python $pythonVersion runtime."
            Invoke-WebRequest -Uri $pythonArchiveUrl -OutFile $archive -UseBasicParsing
            $hash = Get-ArthurSha256 -Path $archive
            if ($hash -ne $pythonArchiveSha256) {
                throw "Python archive hash mismatch. Expected $pythonArchiveSha256, received $hash."
            }
            if (Test-Path -LiteralPath $DestinationRoot) {
                Remove-Item -LiteralPath $DestinationRoot -Recurse -Force
            }
            New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
            Expand-Archive -LiteralPath $archive -DestinationPath $DestinationRoot -Force
        }
        finally {
            if (Test-Path -LiteralPath $downloadRoot) {
                Remove-Item -LiteralPath $downloadRoot -Recurse -Force
            }
        }
    }
    if (-not (Test-Path -LiteralPath $pythonExecutable)) {
        throw "Private Python executable was not created: $pythonExecutable"
    }
    Set-ArthurPythonPath -DestinationRoot $DestinationRoot -ModuleRoot $ModuleRoot
    $env:PYTHONNOUSERSITE = '1'
    $pipModule = Join-Path $DestinationRoot 'Lib\site-packages\pip\__init__.py'
    if (-not (Test-Path -LiteralPath $pipModule)) {
        Install-ArthurPip -PythonExecutable $pythonExecutable
    }
    return $pythonExecutable
}

function Resolve-ArthurPython {
    param([switch] $Provision)

    $localPython = Join-Path $pythonRootPath 'python.exe'
    if ($Provision) {
        return Install-ArthurPython -DestinationRoot $pythonRootPath -ModuleRoot $installRootPath
    }
    if (Test-Path -LiteralPath $localPython) {
        return $localPython
    }
    if ($env:ARTHUR_PYTHON -and (Test-Path -LiteralPath $env:ARTHUR_PYTHON)) {
        return [System.IO.Path]::GetFullPath($env:ARTHUR_PYTHON)
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }
    throw 'Python is unavailable. Re-run with -InstallDependencies to provision Arthur private Python.'
}

function Copy-ArthurRuntime {
    New-Item -ItemType Directory -Path $installRootPath -Force | Out-Null
    Copy-Item -Path (Join-Path $packageRoot 'src\*.py') -Destination $installRootPath -Force
    foreach ($script in @(
        'Start-Arthur.ps1',
        'Update-Arthur.ps1',
        'Migrate-ArthurToLocalAppData.ps1',
        'Remove-ArthurLegacyData.ps1',
        'Install-ArthurZipformerModel.ps1',
        'New-ArthurPackageManifest.ps1'
    )) {
        Copy-Item -LiteralPath (Join-Path $packageRoot "scripts\$script") -Destination $installRootPath -Force
    }
    Copy-Item -LiteralPath (Join-Path $packageRoot 'config\automations.template.json') -Destination (Join-Path $installRootPath 'automations.template.json') -Force
    Copy-Item -LiteralPath (Join-Path $packageRoot 'requirements.txt') -Destination $installRootPath -Force
}

function Remove-ArthurObsoleteRuntimeFiles {
    foreach ($name in @(
        'arthur_speech_benchmark.py',
        'arthur_speech_benchmark_recorder.py',
        'Install-ArthurNemotronModel.ps1',
        'requirements-nemotron.txt',
        'speech-benchmark-plan.json',
        'Start-ArthurSpeechBenchmark.ps1',
        'voice-commands.json'
    )) {
        $path = Join-Path $installRootPath $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path -Force
        }
    }
    $benchmarkDirectory = Join-Path $installRootPath 'speech-benchmark'
    if (Test-Path -LiteralPath $benchmarkDirectory -PathType Container) {
        Remove-Item -LiteralPath $benchmarkDirectory -Recurse -Force
    }
}

function Initialize-ArthurConfig {
    $configSource = Join-Path $packageRoot 'config\arthur.config.template.json'
    $configTarget = Join-Path $installRootPath 'arthur.config.json'
    $defaults = Get-Content -LiteralPath $configSource -Raw -Encoding UTF8 | ConvertFrom-Json
    $isNewConfig = -not (Test-Path -LiteralPath $configTarget)
    if ($isNewConfig) {
        $config = $defaults
        $displayName = [Environment]::UserName
        $firstName = ($displayName -split '[\s._-]', 2)[0]
        $config.userDisplayName = $displayName
        $config.userFirstName = $firstName
        $config.timezone = 'Europe/London'
        $config.notification.selfEmail = ''
        $config.azureDevOps.organization = ''
        $config.azureDevOps.project = ''
        $config.azureDevOps.url = ''
        $config.azureDevOps.defaultAssignee = ''
        $config.azureDevOps.defaultAssigneeEmail = ''
        $config.scout.queueEnabled = $true
        $config.enabledCommands = @($defaults.enabledCommands)
    }
    else {
        $config = Get-Content -LiteralPath $configTarget -Raw -Encoding UTF8 | ConvertFrom-Json
        $config = Merge-ArthurConfigDefaults -Defaults $defaults -Current $config
    }

    $workiqCandidates = @(
        (Join-Path $env:USERPROFILE '.scout\bin\workiq.cmd'),
        (Join-Path $env:USERPROFILE '.copilot\bin\workiq.cmd')
    )
    $automationCandidates = @(
        (Join-Path $env:USERPROFILE '.scout\m-automations\automations.json'),
        (Join-Path $env:USERPROFILE '.copilot\m-automations\automations.json')
    )
    $workiqPath = $workiqCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    $automationPath = $automationCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

    $config.runtime.scratchpadPath = $installRootPath
    $config.runtime.browserProfilePath = Join-Path (Split-Path -Parent $installRootPath) 'EdgeProfile'
    $timezoneAliases = @{
        'GMT Standard Time' = 'Europe/London'
        'Mountain Standard Time' = 'America/Denver'
    }
    $configuredTimezone = [string] $config.timezone
    if ($timezoneAliases.ContainsKey($configuredTimezone)) {
        $config.timezone = $timezoneAliases[$configuredTimezone]
    }
    if ($isNewConfig) {
        $config.runtime.workiqPath = if ($workiqPath) { $workiqPath } else { '' }
        $config.runtime.automationFile = if ($automationPath) { $automationPath } else { '' }
        $config.runtime.promptResponderAutomationId = ''
    }
    $config.speechRecognition.backend = 'zipformer'
    $config.speechRecognition.postActivationBackend = 'zipformer'
    foreach ($obsoleteSpeechField in @(
        'preloadPostActivationBackend',
        'modelAlias',
        'appName',
        'language',
        'chunkMilliseconds',
        'resultTimeoutSeconds',
        'autoDownload'
    )) {
        $config.speechRecognition.PSObject.Properties.Remove($obsoleteSpeechField)
    }
    if (@($config.enabledCommands) -notcontains 'open_dashboard') {
        $config.enabledCommands += 'open_dashboard'
    }
    $modelDirectory = [string] $config.speechRecognition.modelDirectory
    if ([System.IO.Path]::IsPathRooted($modelDirectory)) {
        $modelLeaf = Split-Path -Leaf $modelDirectory
        if ($modelLeaf -eq 'zipformer-en-balanced-int8') {
            $config.speechRecognition.modelDirectory = 'models\zipformer-en-balanced-int8'
        }
    }

    $content = ($config | ConvertTo-Json -Depth 20) + [Environment]::NewLine
    Write-Utf8NoBom -Path $configTarget -Content $content
    return $configTarget
}

if ((Test-CloudPath -Path $installRootPath) -and (-not $AllowCloudStorage)) {
    throw "Arthur runtime data cannot be installed under a cloud-synchronised path: $installRootPath"
}

if ($CreateScheduledTask) {
    Write-Warning 'The legacy Arthur scheduled task is no longer supported. Use Start with Windows in the Arthur desktop application.'
}
Unregister-ScheduledTask -TaskName 'Arthur Voice Bridge' -Confirm:$false -ErrorAction SilentlyContinue

Copy-ArthurRuntime
Remove-ArthurObsoleteRuntimeFiles
$configTarget = Initialize-ArthurConfig
$pythonExecutable = Resolve-ArthurPython -Provision:$InstallDependencies
$env:ARTHUR_CONFIG = $configTarget
$env:ARTHUR_PYTHON = $pythonExecutable
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYTHONNOUSERSITE = '1'

if ($InstallDependencies) {
    Write-ArthurInstall "Installing Python dependencies into $pythonRootPath."
    & $pythonExecutable -s -m pip install --no-warn-script-location -r (Join-Path $packageRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur Python dependency installation failed.'
    }
}

if ($InstallSpeechModel) {
    $speechConfig = Get-Content -LiteralPath $configTarget -Raw -Encoding UTF8 | ConvertFrom-Json
    $backend = [string] $speechConfig.speechRecognition.backend
    if ($backend -ne 'zipformer') {
        throw "Unsupported Arthur speech backend: $backend"
    }
    $modelInstaller = Join-Path $packageRoot 'scripts\Install-ArthurZipformerModel.ps1'
    & $modelInstaller -InstallRoot $installRootPath -PythonExecutable $pythonExecutable
    if ($LASTEXITCODE -ne 0) {
        throw "Arthur $backend model installation failed."
    }
}

$versionScript = Join-Path $installRootPath 'arthur_version.py'
$commitSha = ''
try {
    $commitSha = (git -C $packageRoot rev-parse --short HEAD 2>$null).Trim()
}
catch {
    $commitSha = ''
}
if (Test-Path -LiteralPath $versionScript) {
    $versionArgs = @($versionScript, '--write')
    if ($commitSha) {
        $versionArgs += @('--commit-sha', $commitSha)
    }
    & $pythonExecutable -s @versionArgs | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur version manifest generation failed.'
    }
}

& $pythonExecutable -s (Join-Path $installRootPath 'arthur_config.py') --config $configTarget --validate | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Arthur configuration validation failed.'
}

if ($InstallDependencies) {
    & $pythonExecutable -s (Join-Path $installRootPath 'arthur_preflight.py') --write | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur preflight checks failed.'
    }
}

foreach ($file in @('arthur_prompt_queue.jsonl', 'arthur_prompt_responses.jsonl')) {
    $path = Join-Path $installRootPath $file
    if (-not (Test-Path -LiteralPath $path)) {
        New-Item -ItemType File -Path $path | Out-Null
    }
}

$packageManifestSha256 = ''
$packageManifestPath = Join-Path $packageRoot 'arthur.package-manifest.json'
if (Test-Path -LiteralPath $packageManifestPath) {
    $packageManifestSha256 = Get-ArthurSha256 -Path $packageManifestPath
}
$runtimeManifest = [ordered]@{
    schemaVersion = 1
    packageVersion = (Get-ArthurPackageVersion)
    packageManifestSha256 = $packageManifestSha256
    updateStatus = 'complete'
    installRoot = $installRootPath
    pythonExecutable = $pythonExecutable
    speechBackend = 'zipformer'
    modelDirectory = 'models\zipformer-en-balanced-int8'
    installedAt = (Get-Date).ToString('o')
}
Write-Utf8NoBom -Path (Join-Path $installRootPath 'arthur.runtime.json') -Content (($runtimeManifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine)

Write-ArthurInstall "Arthur installed to $installRootPath"
Write-ArthurInstall "Private Python: $pythonExecutable"
