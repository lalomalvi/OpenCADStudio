param(
    [Parameter(Mandatory = $true)][string]$SyntheticDwg,
    [string]$AutoCadCore = 'C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe',
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 required' }
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$allowed = [IO.Path]::GetFullPath((Join-Path $repo 'target/mcp-isolated'))
$drawing = (Resolve-Path -LiteralPath $SyntheticDwg).Path
if (-not $drawing.StartsWith($allowed.TrimEnd([char]'\') + '\',
                            [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetExtension($drawing).ToLowerInvariant() -ne '.dwg') {
    throw 'Only synthetic DWG under this worktree target/mcp-isolated is allowed'
}
if (-not (Test-Path -LiteralPath $AutoCadCore -PathType Leaf)) {
    throw 'AutoCAD Core Console executable absent'
}
if ($TimeoutSeconds -lt 30 -or $TimeoutSeconds -gt 300) {
    throw 'TimeoutSeconds must be 30..300'
}
$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-hatch-edit-' +
    [Guid]::NewGuid().ToString('N').Substring(0, 8)
$output = Join-Path $repo (Join-Path 'target/mcp-external' $runId)
New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
$profile = Join-Path $output 'profile'
$temp = Join-Path $output 'temp'
New-Item -ItemType Directory -Path $profile, $temp -ErrorAction Stop | Out-Null
$copy = Join-Path $output 'input-copy.dwg'
Copy-Item -LiteralPath $drawing -Destination $copy -ErrorAction Stop
$sourceSha = (Get-FileHash -LiteralPath $drawing -Algorithm SHA256).Hash
$copyBeforeSha = (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash
if ($sourceSha -ne $copyBeforeSha) { throw 'Synthetic copy SHA differs before edit' }
$editLog = (Join-Path $output 'edit-census.txt').Replace('\','/')
$lispPath = Join-Path $output 'hatch-edit.lsp'
$scriptPath = Join-Path $output 'hatch-edit.scr'
$lisp = @"
(vl-load-com)
(setq ocs_file (open "$editLog" "w"))
(setq ocs_contour (handent "64"))
(setq ocs_hatch (handent "65"))
(if (and ocs_contour ocs_hatch)
  (progn
    (setq ocs_data (entget ocs_contour))
    (setq ocs_points (mapcar 'cdr (vl-remove-if-not '(lambda (p) (= (car p) 10)) ocs_data)))
    (if (and (= (cdr (assoc 0 ocs_data)) "LWPOLYLINE")
             (= (cdr (assoc 0 (entget ocs_hatch))) "HATCH")
             (= (length ocs_points) 3)
             (equal (cadr ocs_points) '(24.0 0.0) 0.000001))
      (progn
        (setq ocs_vertex_index 0)
        (setq ocs_updated
          (mapcar '(lambda (pair)
            (if (= (car pair) 10)
              (progn
                (setq ocs_vertex_index (1+ ocs_vertex_index))
                (if (= ocs_vertex_index 2) (cons 10 '(25.0 0.0)) pair))
              pair)) ocs_data))
        (if (entmod ocs_updated)
          (progn (entupd ocs_contour)
                 (command "_.REGENALL")
                 (write-line "EDIT|64|24,0|25,0" ocs_file))
          (write-line "EDIT_FAILED|ENTMOD" ocs_file)))
      (write-line "EDIT_FAILED|PRECONDITION" ocs_file)))
  (write-line "EDIT_FAILED|HANDLES" ocs_file))
(close ocs_file)
(princ "OCS_HATCH_EDIT_DONE")
(princ)
"@
[IO.File]::WriteAllText($lispPath, $lisp, [Text.UTF8Encoding]::new($false))
$loadPath = $lispPath.Replace('\','/')
$scriptLines = @("(load ""$loadPath"")", '_.QSAVE', '_.QUIT', '_N', '')
[IO.File]::WriteAllText($scriptPath, ($scriptLines -join [Environment]::NewLine),
                        [Text.ASCIIEncoding]::new())

$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $AutoCadCore
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.StandardOutputEncoding = [Text.Encoding]::Unicode
$start.StandardErrorEncoding = [Text.Encoding]::Unicode
$start.WorkingDirectory = $output
$start.Environment['APPDATA'] = $profile
$start.Environment['LOCALAPPDATA'] = $profile
$start.Environment['TEMP'] = $temp
$start.Environment['TMP'] = $temp
@('/i', $copy, '/s', $scriptPath, '/l', 'en-US',
  '/isolate', $runId, $profile) | ForEach-Object { [void]$start.ArgumentList.Add($_) }
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
$forced = $false
try {
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $forced = $true
        $process.Kill($true)
        $process.WaitForExit()
    }
    $logPath = Join-Path $output 'autocad.log'
    [IO.File]::WriteAllText($logPath, ($stdout.Result + $stderr.Result),
                            [Text.UTF8Encoding]::new($false))
    $log = [IO.File]::ReadAllText($logPath)
    $editRows = @(if (Test-Path -LiteralPath $editLog) {
        [IO.File]::ReadAllLines($editLog)
    } else { @() })
    $afterSha = (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash
    $sourceAfterSha = (Get-FileHash -LiteralPath $drawing -Algorithm SHA256).Hash
    $report = [ordered]@{
        schema_version = 'mcp-hatch-autocad-edit-l4-1'
        run_id = $runId
        source_sha256_before = $sourceSha
        source_sha256_after = $sourceAfterSha
        source_unchanged = $sourceSha -eq $sourceAfterSha
        copy_sha256_before = $copyBeforeSha
        copy_sha256_after = $afterSha
        copy_changed = $copyBeforeSha -ne $afterSha
        edit_rows = @($editRows)
        edit_marker = $log.Contains('OCS_HATCH_EDIT_DONE')
        forced_termination = $forced
        exit_code = $process.ExitCode
        log_sha256 = (Get-FileHash -LiteralPath $logPath -Algorithm SHA256).Hash
        status = if ($sourceSha -eq $sourceAfterSha -and
                    $copyBeforeSha -ne $afterSha -and
                    @($editRows).Count -eq 1 -and
                    $editRows[0] -ceq 'EDIT|64|24,0|25,0' -and
                    $log.Contains('OCS_HATCH_EDIT_DONE') -and
                    -not $forced -and $process.ExitCode -eq 0) {
            'edited_copy_needs_external_reopen'
        } else { 'failed_or_uncertain' }
    }
    [IO.File]::WriteAllText((Join-Path $output 'report.json'),
                            ($report | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
                            [Text.UTF8Encoding]::new($false))
    $report | ConvertTo-Json -Depth 4
    if ($report.status -ne 'edited_copy_needs_external_reopen') { exit 1 }
}
finally {
    $process.Dispose()
}
