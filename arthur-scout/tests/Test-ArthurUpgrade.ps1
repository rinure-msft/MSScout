[CmdletBinding()]
param(
    [string] $PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSCommandPath))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Join-Path $env:TEMP ('arthur-upgrade-test-' + [guid]::NewGuid().ToString('N'))
$runtime = Join-Path $root 'runtime'
$pythonRoot = Join-Path $root 'python'
$configPath = Join-Path $runtime 'arthur.config.json'
$previousPython = $env:ARTHUR_PYTHON

try {
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $legacyConfig = [ordered]@{
        assistantName = 'Arthur'
        userDisplayName = 'Test User'
        userFirstName = 'Test'
        timezone = 'Europe/London'
        voice = [ordered]@{
            tts = 'edge'
            edgeVoice = 'en-GB-RyanNeural'
        }
        microphone = [ordered]@{
            deviceIndex = 0
            threshold = 350
        }
        runtime = [ordered]@{
            scratchpadPath = $runtime
        }
        enabledCommands = @('help', 'voice_command_index', 'prompt_window')
    }
    [System.IO.File]::WriteAllText(
        $configPath,
        ($legacyConfig | ConvertTo-Json -Depth 10) + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        $python = Get-Command python -ErrorAction Stop
    }
    $env:ARTHUR_PYTHON = $python.Source

    & (Join-Path $PackageRoot 'install.ps1') `
        -InstallRoot $runtime `
        -PythonRoot $pythonRoot
    if ($LASTEXITCODE -ne 0) {
        throw 'Arthur legacy configuration upgrade failed.'
    }

    $upgraded = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if ($upgraded.speechRecognition.backend -ne 'zipformer') {
        throw 'The v0.3 configuration was not upgraded to Zipformer.'
    }
    if (@($upgraded.enabledCommands) -notcontains 'prompt_window') {
        throw 'The v0.3 configuration did not preserve the explicit Scout handoff choice.'
    }
    if (@($upgraded.enabledCommands) -notcontains 'open_dashboard') {
        throw 'The v0.3 configuration did not gain the local dashboard command.'
    }
    if ($upgraded.scout.queueEnabled -ne $true) {
        throw 'The v0.3 configuration did not enable Scout queueing by default.'
    }
    $actualRuntime = [System.IO.Path]::GetFullPath([string] $upgraded.runtime.scratchpadPath)
    $expectedRuntime = [System.IO.Path]::GetFullPath($runtime)
    if (-not $actualRuntime.Equals($expectedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'The upgraded runtime path is incorrect.'
    }
    $expectedBrowserProfile = Join-Path $root 'EdgeProfile'
    if (-not ([System.IO.Path]::GetFullPath([string] $upgraded.runtime.browserProfilePath).Equals(
        [System.IO.Path]::GetFullPath($expectedBrowserProfile),
        [System.StringComparison]::OrdinalIgnoreCase
    ))) {
        throw 'The upgraded browser profile path is incorrect.'
    }

    $manifest = Get-Content -LiteralPath (Join-Path $runtime 'arthur.runtime.json') -Raw | ConvertFrom-Json
    if ($manifest.packageVersion -ne '0.4.0') {
        throw 'The upgraded runtime manifest version is incorrect.'
    }
    if ($manifest.updateStatus -ne 'complete') {
        throw 'The upgraded runtime manifest was not marked complete.'
    }

    Write-Host 'Arthur v0.3 configuration upgrade test passed.'
}
finally {
    $env:ARTHUR_PYTHON = $previousPython
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}
