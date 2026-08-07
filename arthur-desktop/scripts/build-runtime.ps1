[CmdletBinding()]
param(
    [string] $SourceRoot = '',
    [string] $OutputRoot = ''
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
if (-not $SourceRoot) {
    $SourceRoot = Join-Path $projectRoot '..\arthur-scout'
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $projectRoot 'runtime-dist\arthur-runtime'
}
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
if (Test-Path -LiteralPath $OutputRoot) {
    Remove-Item -LiteralPath $OutputRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null

foreach ($directory in 'config','docs','scripts','src') {
    Copy-Item -LiteralPath (Join-Path $source $directory) -Destination $OutputRoot -Recurse -Force
}
foreach ($file in 'README.md','install.ps1','uninstall.ps1','requirements.txt') {
    Copy-Item -LiteralPath (Join-Path $source $file) -Destination $OutputRoot -Force
}
Copy-Item -LiteralPath (Join-Path $projectRoot '..\LICENSE') -Destination $OutputRoot -Force

& (Join-Path $OutputRoot 'scripts\New-ArthurPackageManifest.ps1') -PackageRoot $OutputRoot | Out-Null

Write-Host "Arthur runtime sidecar prepared: $OutputRoot"
