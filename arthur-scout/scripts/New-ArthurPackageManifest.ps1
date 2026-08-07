[CmdletBinding()]
param(
    [string] $PackageRoot = (Split-Path -Parent (Split-Path -Parent $PSCommandPath)),
    [string] $PackageVersion = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$manifestName = 'arthur.package-manifest.json'
$manifestPath = Join-Path $root $manifestName

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

if (-not $PackageVersion) {
    $versionFile = Join-Path $root 'src\arthur_version.py'
    if (-not (Test-Path -LiteralPath $versionFile)) {
        throw "Arthur version file was not found: $versionFile"
    }
    $versionText = Get-Content -LiteralPath $versionFile -Raw
    $match = [regex]::Match($versionText, 'PACKAGE_VERSION\s*=\s*"(?<version>[^"]+)"')
    if (-not $match.Success) {
        throw "Arthur package version could not be read from $versionFile"
    }
    $PackageVersion = $match.Groups['version'].Value
}

$files = @(
    Get-ChildItem -LiteralPath $root -File -Recurse |
        ForEach-Object {
            $relative = (Get-ArthurRelativePath -BasePath $root -TargetPath $_.FullName).Replace('\', '/')
            if ($relative -ne $manifestName) {
                [ordered]@{
                    path = $relative
                    bytes = $_.Length
                    sha256 = (Get-ArthurSha256 -Path $_.FullName)
                }
            }
        } |
        Sort-Object { $_.path }
)

$manifest = [ordered]@{
    schemaVersion = 1
    packageVersion = $PackageVersion
    generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    files = $files
}

$temporary = "$manifestPath.$([guid]::NewGuid().ToString('N')).tmp"
try {
    [System.IO.File]::WriteAllText(
        $temporary,
        ($manifest | ConvertTo-Json -Depth 10) + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )
    Move-Item -LiteralPath $temporary -Destination $manifestPath -Force
}
finally {
    Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
}

Write-Output $manifestPath
