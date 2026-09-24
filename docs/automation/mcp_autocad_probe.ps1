param(
    [Parameter(Mandatory = $true)]
    [string]$SyntheticDwg,
    [string]$AutoCadCore = 'C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe',
    [Nullable[int]]$ExpectedInsunits = $null,
    [int]$TimeoutSeconds = 35
)

$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'The isolated process runner requires PowerShell 7 (pwsh)'
}
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$allowed = [IO.Path]::GetFullPath((Join-Path $repo 'target\mcp-isolated'))
$drawing = (Resolve-Path -LiteralPath $SyntheticDwg).Path
$prefix = $allowed.TrimEnd([char]'\') + '\'
if (-not $drawing.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetExtension($drawing).ToLowerInvariant() -ne '.dwg') {
    throw 'Only a synthetic DWG below this worktree target/mcp-isolated may be probed'
}
if (-not (Test-Path -LiteralPath $AutoCadCore -PathType Leaf)) {
    throw 'AutoCAD Core Console executable is absent'
}
if ($TimeoutSeconds -lt 10 -or $TimeoutSeconds -gt 120) {
    throw 'TimeoutSeconds must be 10..120'
}

function Read-DxfNumber([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq '-') { return $null }
    $parsed = 0.0
    if ([double]::TryParse($value, [Globalization.NumberStyles]::Float,
            [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) { return $parsed }
    return $null
}

function Read-DxfPoint([string]$value) {
    $matches = [regex]::Matches($value, '[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?')
    if ($matches.Count -ne 3) { return $null }
    return @($matches | ForEach-Object { Read-DxfNumber $_.Value })
}

$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-autocad-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$output = Join-Path $repo (Join-Path 'target\mcp-external' $runId)
New-Item -ItemType Directory -Path $output -ErrorAction Stop | Out-Null
$profile = Join-Path $output 'profile'
$temporary = Join-Path $output 'temp'
New-Item -ItemType Directory -Path $profile, $temporary -ErrorAction Stop | Out-Null
$before = (Get-FileHash -LiteralPath $drawing -Algorithm SHA256).Hash
$censusPath = Join-Path $output 'model-census.txt'
$lispPath = Join-Path $output 'model-census.lsp'
$script = Join-Path $output 'autocad-probe.scr'
$censusLispPath = $censusPath.Replace('\', '/')
$lispText = @"
(vl-load-com)
(setq ocs_file (open "$censusLispPath" "w"))
(defun ocs_value (data code) (if (assoc code data) (vl-princ-to-string (cdr (assoc code data))) "-"))
(defun ocs_measure (entity data / value)
  (if (= (cdr (assoc 0 data)) "DIMENSION")
    (progn
      (setq value (vl-catch-all-apply
                   '(lambda () (vlax-get-property
                                 (vlax-ename->vla-object entity) 'Measurement)) nil))
      (if (vl-catch-all-error-p value) "-" (vl-princ-to-string value)))
    "-"))
(write-line (strcat "ACADVER|" (getvar "ACADVER")) ocs_file)
(write-line (strcat "INSUNITS|" (itoa (getvar "INSUNITS"))) ocs_file)
(setq ocs_set (ssget "_X" '((410 . "Model"))))
(if ocs_set
  (progn
    (write-line (strcat "COUNT|" (itoa (sslength ocs_set))) ocs_file)
    (setq ocs_index 0)
    (repeat (sslength ocs_set)
      (setq ocs_entity (ssname ocs_set ocs_index))
      (setq ocs_data (entget ocs_entity))
      (write-line
        (strcat "ENTITY|" (ocs_value ocs_data 0) "|" (ocs_value ocs_data 5) "|"
                (ocs_value ocs_data 8) "|" (ocs_value ocs_data 42) "|"
                (ocs_value ocs_data 70) "|" (ocs_value ocs_data 71) "|"
                (ocs_value ocs_data 91) "|" (ocs_value ocs_data 2) "|"
                (ocs_value ocs_data 10) "|" (ocs_value ocs_data 41) "|"
                (ocs_value ocs_data 50) "|" (ocs_measure ocs_entity ocs_data) "|"
                (ocs_value ocs_data 13) "|" (ocs_value ocs_data 14) "|"
                (ocs_value ocs_data 52)) ocs_file)
      (if (= (cdr (assoc 0 ocs_data)) "DIMENSION")
        (progn
          (write-line (strcat "DIMDATA|" (ocs_value ocs_data 5) "|"
                              (vl-princ-to-string ocs_data)) ocs_file)
          (write-line (strcat "DIMREACTOR|" (ocs_value ocs_data 5) "|"
                              (vl-princ-to-string
                                (entget (cdr (assoc 330 ocs_data))))) ocs_file)
          (setq ocs_ext (cdr (assoc 360 ocs_data)))
          (if ocs_ext
            (progn
              (setq ocs_assoc (dictsearch ocs_ext "ACAD_DIMASSOC"))
              (write-line (strcat "ASSOC_DICT|" (ocs_value ocs_data 5) "|"
                                  (vl-princ-to-string ocs_assoc)) ocs_file)
              (if ocs_assoc
                (write-line (strcat "ASSOC_DATA|" (ocs_value ocs_data 5) "|"
                                    (vl-princ-to-string
                                      (entget (cdr (assoc 360 ocs_assoc))))) ocs_file))))))
      (setq ocs_index (1+ ocs_index))))
  (write-line "COUNT|0" ocs_file))
(close ocs_file)
(princ "OCS_CENSUS_DONE")
(princ)
"@
[IO.File]::WriteAllText($lispPath, $lispText, [Text.UTF8Encoding]::new($false))
$loadPath = $lispPath.Replace('\', '/')
[IO.File]::WriteAllText($script, "(load `"$loadPath`")`n_.AUDIT`n_N`n_.QUIT`n_N`n",
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
$start.Environment['TEMP'] = $temporary
$start.Environment['TMP'] = $temporary
@('/i', $drawing, '/s', $script, '/l', 'en-US',
  '/isolate', $runId, $profile, '/readonly') | ForEach-Object {
    [void]$start.ArgumentList.Add($_)
}

$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
$forcedTermination = $false
try {
    [void]$process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        $forcedTermination = $true
        # This is only the process launched above with the isolated profile.
        $process.Kill($true)
        $process.WaitForExit()
    }
    $log = Join-Path $output 'autocad.log'
    [IO.File]::WriteAllText($log, ($stdout.Result + $stderr.Result),
                            [Text.UTF8Encoding]::new($false))
    $after = (Get-FileHash -LiteralPath $drawing -Algorithm SHA256).Hash
    $text = [IO.File]::ReadAllText($log)
    $auditZero = [regex]::IsMatch($text, 'Total errors found\s+0\s+fixed\s+0')
    $censusDone = $text.Contains('OCS_CENSUS_DONE') -and
                  (Test-Path -LiteralPath $censusPath -PathType Leaf)
    $entityRows = @()
    $declaredCount = $null
    $acadver = $null
    $insunits = $null
    if ($censusDone) {
        $lines = [IO.File]::ReadAllLines($censusPath)
        $entityRows = @($lines | Where-Object { $_.StartsWith('ENTITY|') })
        $countLine = $lines | Where-Object { $_.StartsWith('COUNT|') } | Select-Object -First 1
        $versionLine = $lines | Where-Object { $_.StartsWith('ACADVER|') } | Select-Object -First 1
        $unitsLine = $lines | Where-Object { $_.StartsWith('INSUNITS|') } | Select-Object -First 1
        if ($countLine) { $declaredCount = [int]($countLine -split '\|')[1] }
        if ($versionLine) { $acadver = ($versionLine -split '\|')[1] }
        if ($unitsLine) { $insunits = [int]($unitsLine -split '\|')[1] }
        $censusDone = $null -ne $declaredCount -and $declaredCount -eq $entityRows.Count -and
                      $null -ne $acadver
    }
    $types = @{}
    $dimensionMeasurements = @{}
    $entityByHandle = @{}
    foreach ($row in $entityRows) {
        $parts = $row -split '\|'
        $kind = $parts[1]
        $entityByHandle[$parts[2]] = $parts
        if (-not $types.ContainsKey($kind)) { $types[$kind] = 0 }
        $types[$kind]++
        if ($kind -eq 'DIMENSION') {
            $dimensionMeasurements[$parts[2]] = [ordered]@{
                dxf_42 = $parts[4]
                activex_measurement = $parts[12]
                dxf_13 = $parts[13]
                dxf_14 = $parts[14]
            }
        }
    }
    $expected = @{}
    $richSourceReport = $null
    $sourceReportPath = Join-Path ([IO.Path]::GetDirectoryName($drawing)) 'report.json'
    if (Test-Path -LiteralPath $sourceReportPath -PathType Leaf) {
        $sourceReport = Get-Content -LiteralPath $sourceReportPath -Raw | ConvertFrom-Json
        if ($sourceReport.status -eq 'passed' -and
            $sourceReport.verified_output.sha256 -eq $before) {
            $richSourceReport = $sourceReport
            foreach ($field in @('dimension_fixture', 'aligned_dimension_fixture')) {
                $fixture = $sourceReport.$field
                if ($fixture -and $fixture.handle -and $null -ne $fixture.roundtrip_measurement) {
                    $expected[$fixture.handle] = [double]$fixture.roundtrip_measurement
                }
            }
            $association = $sourceReport.association_fixture
            if ($association -and $association.dimension_handle -and
                $null -ne $association.roundtrip_measurement) {
                $expected[$association.dimension_handle] = [double]$association.roundtrip_measurement
            }
        }
        if ($sourceReport.status -eq 'passed' -and
            $sourceReport.second_save.sha256 -eq $before -and
            $sourceReport.association.dimension_handle -and
            $null -ne $sourceReport.association.edited_measurement) {
            $expected[$sourceReport.association.dimension_handle] =
                [double]$sourceReport.association.edited_measurement
        }
    }
    $dimensionComparison = @()
    foreach ($handle in ($expected.Keys | Sort-Object)) {
        $observed = $dimensionMeasurements[$handle]
        $dxfValue = $null
        if ($observed -and $observed.dxf_42 -ne '-') {
            $dxfValue = [double]::Parse($observed.dxf_42,
                [Globalization.CultureInfo]::InvariantCulture)
        }
        $dimensionComparison += [ordered]@{
            handle = $handle
            expected = $expected[$handle]
            autocad_dxf_42 = $dxfValue
            autocad_activex = if ($observed) { $observed.activex_measurement } else { $null }
            matched_1e_6 = ($null -ne $dxfValue -and
                            [Math]::Abs($dxfValue - $expected[$handle]) -le 1e-6)
        }
    }
    $dimensionMismatch = @($dimensionComparison | Where-Object { -not $_.matched_1e_6 }).Count -gt 0
    $propertyComparison = @()
    if ($richSourceReport) {
        $hatch = $richSourceReport.hatch_fixture
        if ($hatch -and $hatch.handle) {
            $row = $entityByHandle[$hatch.handle]
            $checks = [ordered]@{
                type = @('HATCH', $(if ($row) { $row[1] } else { $null }))
                layer = @($hatch.layer, $(if ($row) { $row[3] } else { $null }))
                associative = @([int][bool]$hatch.is_associative_flag,
                                $(if ($row) { Read-DxfNumber $row[6] } else { $null }))
                solid = @([int][bool]$hatch.is_solid,
                          $(if ($row) { Read-DxfNumber $row[5] } else { $null }))
                paths = @([int]$hatch.path_count,
                          $(if ($row) { Read-DxfNumber $row[7] } else { $null }))
                pattern_scale = @([double]$hatch.pattern_scale,
                                  $(if ($row) { Read-DxfNumber $row[10] } else { $null }))
                pattern_angle = @([double]$hatch.pattern_angle,
                                  $(if ($row) { Read-DxfNumber $row[15] } else { $null }))
            }
            foreach ($name in $checks.Keys) {
                $values = $checks[$name]
                $match = $null -ne $values[1] -and
                    $(if ($name -in @('type', 'layer')) { $values[0] -ceq $values[1] }
                      else { [Math]::Abs($values[0] - $values[1]) -le 1e-6 })
                $propertyComparison += [ordered]@{ handle = $hatch.handle; property = $name;
                    expected = $values[0]; observed = $values[1]; matched_1e_6 = $match }
            }
        }
        $block = $richSourceReport.block_fixture
        if ($block) {
            for ($index = 0; $index -lt $block.insert_handles.Count; $index++) {
                $handle = $block.insert_handles[$index]
                $instance = $block.instances[$index]
                $row = $entityByHandle[$handle]
                $position = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $checks = [ordered]@{
                    type = @('INSERT', $(if ($row) { $row[1] } else { $null }))
                    block = @($instance.block, $(if ($row) { $row[8] } else { $null }))
                    x_scale = @([double]$instance.x_scale,
                                $(if ($row) { Read-DxfNumber $row[10] } else { $null }))
                    y_scale = @([double]$instance.y_scale,
                                $(if ($row) { Read-DxfNumber $row[4] } else { $null }))
                    rotation = @([double]$instance.rotation,
                                 $(if ($row) { Read-DxfNumber $row[11] } else { $null }))
                }
                for ($axis = 0; $axis -lt 3; $axis++) {
                    $checks["position_$axis"] = @([double]$instance.position[$axis],
                        $(if ($position) { $position[$axis] } else { $null }))
                }
                foreach ($name in $checks.Keys) {
                    $values = $checks[$name]
                    $match = $null -ne $values[1] -and
                        $(if ($name -in @('type', 'block')) { $values[0] -ceq $values[1] }
                          else { [Math]::Abs($values[0] - $values[1]) -le 1e-6 })
                    $propertyComparison += [ordered]@{ handle = $handle; property = $name;
                        expected = $values[0]; observed = $values[1]; matched_1e_6 = $match }
                }
            }
        }
    }
    $propertyMismatch = @($propertyComparison | Where-Object { -not $_.matched_1e_6 }).Count -gt 0
    $report = [ordered]@{
        schema_version = 'mcp-autocad-audit-l4-3'
        run_id = $runId
        product = 'AutoCAD Core Console'
        executable_version = [Diagnostics.FileVersionInfo]::GetVersionInfo($AutoCadCore).FileVersion
        executable_sha256 = (Get-FileHash -LiteralPath $AutoCadCore -Algorithm SHA256).Hash
        input_name = [IO.Path]::GetFileName($drawing)
        input_sha256_before = $before
        input_sha256_after = $after
        input_unchanged = ($before -eq $after)
        audit_zero_errors_zero_fixes = $auditZero
        acadver = $acadver
        insunits = $insunits
        expected_insunits = $ExpectedInsunits
        unit_match = if ($null -eq $ExpectedInsunits) { $null } else {
            $insunits -eq $ExpectedInsunits
        }
        model_census_count = $declaredCount
        model_types = $types
        dimension_measurements = $dimensionMeasurements
        dimension_comparison = $dimensionComparison
        property_comparison = $propertyComparison
        semantic_verdict = if ($dimensionMismatch -or $propertyMismatch) { 'mismatch' }
                           elseif ($expected.Count -gt 0 -or $propertyComparison.Count -gt 0) {
            'matched_scoped'
        } else { 'unknown' }
        census_done = $censusDone
        census_sha256 = if ($censusDone) {
            (Get-FileHash -LiteralPath $censusPath -Algorithm SHA256).Hash
        } else { $null }
        forced_termination = $forcedTermination
        exit_code = $process.ExitCode
        log_sha256 = (Get-FileHash -LiteralPath $log -Algorithm SHA256).Hash
        verdict = if (-not $auditZero -or -not $censusDone -or $before -ne $after -or
                      ($null -ne $ExpectedInsunits -and $insunits -ne $ExpectedInsunits)) {
            'failed'
        } elseif ($dimensionMismatch -or $propertyMismatch) { 'semantic_mismatch'
        } elseif ($forcedTermination -or $process.ExitCode -ne 0) {
            'partial_abnormal_exit'
        } else { 'audit_and_census_passed' }
    }
    $reportPath = Join-Path $output 'report.json'
    [IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 5) + "`n",
                            [Text.UTF8Encoding]::new($false))
    $report | ConvertTo-Json -Depth 5
    if ($report.verdict -ne 'audit_and_census_passed') { exit 1 }
}
finally {
    $process.Dispose()
}
