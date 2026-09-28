# Keep native acceptance state outside the Cargo target cache.
param(
    [string]$Workspace = $env:GITHUB_WORKSPACE,
    [string]$RuntimeTemp = $env:RUNNER_TEMP
)
$ErrorActionPreference = 'Stop'
if (-not $Workspace -or -not $RuntimeTemp) { throw 'Workspace and runner temp are required' }
$workspaceRoot = [IO.Path]::GetFullPath($Workspace)
$runtimeRoot = [IO.Path]::GetFullPath($RuntimeTemp)
foreach ($directory in @($workspaceRoot, $runtimeRoot)) {
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Missing CI directory: $directory" }
}
$comparison = if ($IsWindows) { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
$workspaceBoundary = $workspaceRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($runtimeRoot.Equals($workspaceRoot, $comparison) -or $runtimeRoot.StartsWith($workspaceBoundary, $comparison)) {
    throw 'Runner temp must be outside the build workspace'
}
$cachedLogs = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'target/desktop-logs'))
if (-not $cachedLogs.StartsWith($workspaceBoundary, $comparison)) { throw 'Cached logs escaped the workspace' }
if (Test-Path -LiteralPath $cachedLogs) {
    $item = Get-Item -LiteralPath $cachedLogs -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Cached logs must be an ordinary directory owned by the CI workspace'
    }
    # Preserve restored evidence; it is neither new acceptance nor cache input.
    $preserved = Join-Path $runtimeRoot ('OCS restored desktop logs ' + [guid]::NewGuid().ToString('N'))
    Move-Item -LiteralPath $cachedLogs -Destination $preserved
    Write-Host "Preserved restored desktop logs: $preserved"
}
if ($env:GITHUB_ENV) {
    $logs = Join-Path $runtimeRoot ("OCS desktop evidence-$env:GITHUB_RUN_ID-$env:GITHUB_RUN_ATTEMPT")
    Add-Content -LiteralPath $env:GITHUB_ENV -Encoding utf8 -Value "OCS_DESKTOP_LOG_ROOT=$logs"
}
