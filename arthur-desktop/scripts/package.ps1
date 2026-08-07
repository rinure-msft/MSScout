[CmdletBinding()]
param(
    [ValidateSet('dir', 'nsis')]
    [string] $Target = 'dir',
    [string] $OutputRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\build-output'),
    [switch] $RequireSignature
)

$ErrorActionPreference = 'Stop'

if ($RequireSignature -and (-not $env:CSC_LINK -or -not $env:CSC_KEY_PASSWORD)) {
    throw 'Stable Arthur packaging requires CSC_LINK and CSC_KEY_PASSWORD.'
}

New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$builderArguments = @(
    'electron-builder',
    '--win',
    $Target,
    '--x64',
    '--publish',
    'never',
    "--config.directories.output=$OutputRoot"
)
if ($RequireSignature) {
    $builderArguments += '--config.forceCodeSigning=true'
}
& npx @builderArguments
if ($LASTEXITCODE -ne 0) {
    throw "Arthur desktop $Target packaging failed."
}

if ($RequireSignature) {
    $artifacts = @(
        Get-ChildItem -LiteralPath $OutputRoot -File -Filter 'Arthur*.exe' -Recurse
    )
    if ($artifacts.Count -eq 0) {
        throw 'Arthur signed packaging did not produce an executable artifact.'
    }
    foreach ($artifact in $artifacts) {
        $signature = Get-AuthenticodeSignature -LiteralPath $artifact.FullName
        if ($signature.Status -ne 'Valid') {
            throw "Arthur artifact is not correctly signed: $($artifact.FullName) ($($signature.Status))"
        }
    }
}

Write-Host "Arthur desktop package output: $OutputRoot"
