[CmdletBinding(SupportsShouldProcess)]
param(
    [string] $InstallRoot = (Join-Path $env:LOCALAPPDATA 'Arthur\runtime'),
    [switch] $RemoveRuntimeData,
    [switch] $RemovePrivatePython
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installRootPath = [System.IO.Path]::GetFullPath($InstallRoot)
$localArthurRoot = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Arthur'))
$pythonRoot = Join-Path $localArthurRoot 'python'

function Test-PathWithin {
    param(
        [string] $Path,
        [string] $Root
    )
    $resolvedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    return $resolvedPath.Equals($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
        $resolvedPath.StartsWith("$resolvedRoot\", [System.StringComparison]::OrdinalIgnoreCase)
}

$patterns = @(
    'arthur_supervisor.py',
    'arthur_voice_bridge.py',
    'arthur_prompt_worker.py',
    'arthur_dashboard_server.py'
)
$processes = Get-CimInstance Win32_Process | Where-Object {
    $commandLine = $_.CommandLine
    $_.ProcessId -ne $PID -and
        $_.Name -match '^python(w)?\.exe$' -and
        $commandLine -and
        $commandLine.IndexOf($installRootPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($patterns | Where-Object { $commandLine -like "*$_*" })
}
foreach ($arthurProcess in $processes) {
    Stop-Process -Id $arthurProcess.ProcessId -Force -ErrorAction Stop
}

Unregister-ScheduledTask -TaskName 'Arthur Voice Bridge' -Confirm:$false -ErrorAction SilentlyContinue

if ($RemoveRuntimeData) {
    if (-not (Test-PathWithin -Path $installRootPath -Root $localArthurRoot)) {
        throw "Refusing to recursively remove an Arthur runtime outside LocalAppData: $installRootPath"
    }
    if ((Test-Path -LiteralPath $installRootPath) -and $PSCmdlet.ShouldProcess($installRootPath, 'Remove Arthur runtime data')) {
        Remove-Item -LiteralPath $installRootPath -Recurse -Force
        Write-Host "[Arthur uninstall] Removed runtime data: $installRootPath"
    }
}

if ($RemovePrivatePython) {
    if ((Test-Path -LiteralPath $pythonRoot) -and $PSCmdlet.ShouldProcess($pythonRoot, 'Remove Arthur private Python')) {
        Remove-Item -LiteralPath $pythonRoot -Recurse -Force
        Write-Host "[Arthur uninstall] Removed private Python: $pythonRoot"
    }
}

if ((-not $RemoveRuntimeData) -and (-not $RemovePrivatePython)) {
    Write-Host '[Arthur uninstall] Arthur stopped. Local runtime data and private Python were preserved.'
}
