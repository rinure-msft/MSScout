[CmdletBinding()]
param(
    [string] $ProjectRoot = ''
)

$ErrorActionPreference = 'Stop'

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
}
$required = @(
    'dist\main\index.js',
    'dist\preload\index.cjs',
    'dist\renderer\index.html',
    'dist\renderer\popover.html',
    'dist\renderer\halo.html',
    'dist\renderer\widget.html',
    'runtime-dist\arthur-runtime\install.ps1',
    'runtime-dist\arthur-runtime\uninstall.ps1',
    'runtime-dist\arthur-runtime\LICENSE',
    'runtime-dist\arthur-runtime\arthur.package-manifest.json',
    'runtime-dist\arthur-runtime\src\arthur_voice_catalog.py',
    'runtime-dist\arthur-runtime\src\arthur_dashboard_server.py',
    'runtime-dist\arthur-runtime\scripts\Start-Arthur.ps1',
    'runtime-dist\arthur-runtime\scripts\Remove-ArthurLegacyData.ps1'
)
foreach ($relative in $required) {
    $path = Join-Path $ProjectRoot $relative
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing Arthur desktop package file: $relative"
    }
}

$html = Get-Content -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\index.html') -Raw
if ($html -notlike '*scoutTheme*') {
    throw 'Arthur renderer is missing Scout theme detection.'
}
foreach ($control in 'launch-at-login','start-minimized','start-runtime-on-launch','show-floating-indicator','activation-glow-mode') {
    if ($html -notlike "*$control*") {
        throw "Arthur renderer is missing startup control: $control"
    }
}
if ($html -match 'class="brand-mark"[^>]*>\s*A\s*<') {
    throw 'Arthur renderer still contains a letter-based logo.'
}

$popoverHtml = Get-Content -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\popover.html') -Raw
foreach ($control in 'service-dot','service-label','last-action','listen-toggle','open-settings') {
    if ($popoverHtml -notlike "*$control*") {
        throw "Arthur tray popover is missing control: $control"
    }
}
if ($popoverHtml -match 'recent-transcript') {
    throw 'Arthur tray popover must not surface transcript content.'
}

$haloHtml = Get-Content -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\halo.html') -Raw
if ($haloHtml -notlike "*script-src 'none'*") {
    throw 'Arthur activation halo must remain script-free.'
}

$widgetHtml = Get-Content -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\widget.html') -Raw
foreach ($control in 'widget-shell','widget-listen','widget-open') {
    if ($widgetHtml -notlike "*$control*") {
        throw "Arthur floating widget is missing control: $control"
    }
}
if ($widgetHtml -match 'transcript') {
    throw 'Arthur floating widget must not surface transcript content.'
}
$cssFiles = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\assets') -Filter '*.css' -File)
$css = ($cssFiles | ForEach-Object { Get-Content -LiteralPath $_.FullName -Raw }) -join [Environment]::NewLine
foreach ($token in '--cp-bg','--cp-accent') {
    if ($css -notlike "*$token*") {
        throw "Arthur renderer is missing required theme token: $token"
    }
}
$markFiles = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'dist\renderer\assets') -Filter 'arthur-mark*.svg' -File)
if ($markFiles.Count -ne 1) {
    throw 'Arthur renderer must contain one abstract SVG mark.'
}
$mark = Get-Content -LiteralPath $markFiles[0].FullName -Raw
if ($mark -match '<text\b') {
    throw 'Arthur SVG mark must not contain text.'
}

Write-Host 'Arthur desktop package verification passed.'
