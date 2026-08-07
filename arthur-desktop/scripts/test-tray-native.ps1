[CmdletBinding()]
param(
    [string] $ProjectRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

foreach ($relative in @(
    'dist\preload\index.cjs',
    'dist\renderer\popover.html',
    'dist\renderer\halo.html',
    'dist\renderer\widget.html'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $relative))) {
        throw "Build Arthur before running the native tray smoke test: $relative"
    }
}

$temporaryRoot = Join-Path $env:TEMP "arthur-tray-smoke-$([guid]::NewGuid().ToString('N'))"
$bundlePath = Join-Path $temporaryRoot 'tray-native-smoke.cjs'
$resultPath = Join-Path $temporaryRoot 'result.json'
$succeeded = $false
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
try {
    Push-Location $ProjectRoot
    try {
        & npx esbuild tests/integration/tray-native-smoke.ts `
            --bundle `
            --platform=node `
            --format=cjs `
            --external:electron `
            "--outfile=$bundlePath"
        if ($LASTEXITCODE -ne 0) {
            throw 'Arthur native tray smoke harness build failed.'
        }

        $env:ARTHUR_TRAY_SMOKE_PROJECT_ROOT = $ProjectRoot
        $env:ARTHUR_TRAY_SMOKE_RESULT = $resultPath
        & npx electron $bundlePath
        if ($LASTEXITCODE -ne 0) {
            $detail = ''
            if (Test-Path -LiteralPath $resultPath) {
                $detail = Get-Content -LiteralPath $resultPath -Raw
            }
            throw "Arthur native tray smoke test failed. $detail"
        }
        $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
        if ($result.status -ne 'passed') {
            throw "Arthur native tray smoke test returned status: $($result.status)"
        }
        $succeeded = $true
    }
    finally {
        Remove-Item Env:\ARTHUR_TRAY_SMOKE_PROJECT_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:\ARTHUR_TRAY_SMOKE_RESULT -ErrorAction SilentlyContinue
        Pop-Location
    }
}
finally {
    if ($succeeded -and (Test-Path -LiteralPath $temporaryRoot)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    } elseif (Test-Path -LiteralPath $temporaryRoot) {
        Write-Warning "Arthur tray smoke artifacts preserved for diagnosis: $temporaryRoot"
    }
}
