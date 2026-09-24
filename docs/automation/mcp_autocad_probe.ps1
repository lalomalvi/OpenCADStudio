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

function Same-Point($first, $second) {
    if ($null -eq $first -or $null -eq $second -or $first.Count -ne 3 -or
        $second.Count -ne 3) { return $false }
    for ($axis = 0; $axis -lt 3; $axis++) {
        if ([Math]::Abs([double]$first[$axis] - [double]$second[$axis]) -gt 1e-6) {
            return $false
        }
    }
    return $true
}

function Wall-Point($a, $ux, $uy, $nx, $ny, $distance, $side) {
    return ,@(($a[0] + $ux * $distance + $nx * $side),
              ($a[1] + $uy * $distance + $ny * $side), 0.0)
}

function Join-Point($junction, $u, $v, $s, $t) {
    return ,@(($junction[0] + $u[0] * $s + $v[0] * $t),
              ($junction[1] + $u[1] * $s + $v[1] * $t), 0.0)
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
(defun ocs_angle (data code) (if (assoc code data) (rtos (cdr (assoc code data)) 2 12) "-"))
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
                (ocs_angle ocs_data 50) "|" (ocs_measure ocs_entity ocs_data) "|"
                (ocs_value ocs_data 13) "|" (ocs_value ocs_data 14) "|"
                (ocs_value ocs_data 52) "|" (ocs_value ocs_data 11) "|"
                (ocs_value ocs_data 40) "|" (ocs_angle ocs_data 51)) ocs_file)
      (if (= (cdr (assoc 0 ocs_data)) "DIMENSION")
        (progn
          (setq ocs_style (tblsearch "DIMSTYLE" (cdr (assoc 3 ocs_data))))
          (if ocs_style
            (write-line
              (strcat "DIMSTYLE|" (ocs_value ocs_data 5) "|"
                      (ocs_value ocs_data 3) "|"
                      (ocs_value ocs_style 140) "|"
                      (ocs_value ocs_style 41) "|"
                      (ocs_value ocs_style 147) "|"
                      (ocs_value ocs_style 40) "|"
                      (ocs_value ocs_style 144)) ocs_file))
          (write-line (strcat "DIMDATA|" (ocs_value ocs_data 5) "|"
                              (vl-princ-to-string ocs_data)) ocs_file)
          (write-line (strcat "DIMREACTOR|" (ocs_value ocs_data 5) "|"
                              (vl-princ-to-string
                                (entget (cdr (assoc 330 ocs_data))))) ocs_file)
          (setq ocs_reactor (entget (cdr (assoc 330 ocs_data))))
          (setq ocs_ref_index 0)
          (setq ocs_ref_snap -1)
          (foreach ocs_pair ocs_reactor
            (if (= (car ocs_pair) 72) (setq ocs_ref_snap (cdr ocs_pair)))
            (if (= (car ocs_pair) 331)
              (progn
                (write-line
                  (strcat "DIMREF|" (ocs_value ocs_data 5) "|"
                          (itoa ocs_ref_index) "|"
                          (vl-princ-to-string (cdr (assoc 5 (entget (cdr ocs_pair))))) "|"
                          (itoa ocs_ref_snap)) ocs_file)
                (setq ocs_ref_index (1+ ocs_ref_index)))))
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
    $dimensionReferences = @()
    $dimensionStyles = @{}
    if ($censusDone) {
        foreach ($row in @($lines | Where-Object { $_.StartsWith('DIMREF|') })) {
            $parts = $row -split '\|'
            if ($parts.Count -eq 5) {
                $dimensionReferences += [ordered]@{ dimension = $parts[1]; index = [int]$parts[2];
                    source = $parts[3]; osnap = [int]$parts[4] }
            }
        }
        foreach ($row in @($lines | Where-Object { $_.StartsWith('DIMSTYLE|') })) {
            $parts = $row -split '\|'
            if ($parts.Count -eq 8) {
                $dimensionStyles[$parts[1]] = [ordered]@{ name = $parts[2];
                    text_height_m = Read-DxfNumber $parts[3];
                    arrow_size_m = Read-DxfNumber $parts[4];
                    gap_m = Read-DxfNumber $parts[5];
                    scale = Read-DxfNumber $parts[6];
                    measurement_factor = Read-DxfNumber $parts[7] }
            }
        }
    }
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
    $faceReferenceComparison = @()
    $faceStyleComparison = @()
    $facePlacementComparison = @()
    $faceFixtureValid = $null
    $richSourceReport = $null
    $sourceReportMatch = $null
    $sourceReportPath = Join-Path ([IO.Path]::GetDirectoryName($drawing)) 'report.json'
    if (Test-Path -LiteralPath $sourceReportPath -PathType Leaf) {
        $sourceReport = Get-Content -LiteralPath $sourceReportPath -Raw | ConvertFrom-Json
        $sourceReportMatch = $sourceReport.status -eq 'passed' -and
            ($sourceReport.verified_output.sha256 -eq $before -or
             $sourceReport.first_save.sha256 -eq $before -or
             $sourceReport.second_save.sha256 -eq $before)
        if ($sourceReport.schema_version -in @('mcp-face-dimension-l2-1',
                                               'mcp-wall-thickness-l2-1') -and
            $sourceReport.status -eq 'passed' -and $sourceReport.handles.dimension) {
            if ($sourceReport.first_save.sha256 -eq $before) {
                $expected[$sourceReport.handles.dimension] =
                    [double]$sourceReport.measurements_m.initial
            } elseif ($sourceReport.second_save.sha256 -eq $before) {
                $expected[$sourceReport.handles.dimension] =
                    [double]$sourceReport.measurements_m.edited
            }
            $firstFace = if ($sourceReport.handles.first_face) {
                $sourceReport.handles.first_face
            } else { $sourceReport.handles.upper }
            $secondFace = if ($sourceReport.handles.second_face) {
                $sourceReport.handles.second_face
            } else { $sourceReport.handles.lower }
            foreach ($item in @(@{ index = 0; source = $firstFace },
                                @{ index = 1; source = $secondFace })) {
                $observedRef = @($dimensionReferences | Where-Object {
                    $_.dimension -eq $sourceReport.handles.dimension -and
                    $_.index -eq $item.index })
                $faceReferenceComparison += [ordered]@{
                    dimension = $sourceReport.handles.dimension
                    index = $item.index
                    expected_source = $item.source
                    observed_source = if ($observedRef.Count -eq 1) { $observedRef[0].source } else { $null }
                    observed_osnap = if ($observedRef.Count -eq 1) { $observedRef[0].osnap } else { $null }
                    matched = $observedRef.Count -eq 1 -and
                              $observedRef[0].source -eq $item.source -and
                              $observedRef[0].osnap -eq 2
                }
            }
            if ($sourceReport.planspec.dimension_style) {
                $faceFixtureName = [string]$sourceReport.planspec.fixture
                $faceFixtureValid = $faceFixtureName -in @(
                    'synthetic-wall-face-dimension-v7.planspec.json',
                    'synthetic-wall-face-dimension-exterior-v7.planspec.json',
                    'synthetic-wall-face-dimension-readable-v7.planspec.json',
                    'synthetic-wall-face-dimension-vertical-v7.planspec.json')
                if ($faceFixtureValid) {
                    $faceFixturePath = Join-Path $PSScriptRoot (Join-Path 'masterplan\fixtures' $faceFixtureName)
                    $faceFixtureValid = (Get-FileHash -LiteralPath $faceFixturePath -Algorithm SHA256).Hash -eq
                        $sourceReport.planspec.fixture_sha256
                }
                if ($faceFixtureValid) {
                    $faceFixture = Get-Content -LiteralPath $faceFixturePath -Raw | ConvertFrom-Json
                    $dimensionSpec = $faceFixture.dimensions[0]
                    $startNode = @($faceFixture.nodes | Where-Object { $_.id -eq $dimensionSpec.start })[0]
                    $endNode = @($faceFixture.nodes | Where-Object { $_.id -eq $dimensionSpec.end })[0]
                    $offset = [double]$faceFixture.dimension_placements[0].offset_m
                    if ($dimensionSpec.axis -eq 'y') {
                        $expectedDefinition = @(([double]$startNode.x + $offset + [double]$faceFixture.origin.x),
                                                ([double]$endNode.y + [double]$faceFixture.origin.y), 0.0)
                        $expectedRotation = [Math]::PI / 2.0
                    } else {
                        $expectedDefinition = @(([double]$endNode.x + [double]$faceFixture.origin.x),
                                                ([double]$startNode.y + $offset + [double]$faceFixture.origin.y), 0.0)
                        $expectedRotation = 0.0
                    }
                    $dimensionRow = $entityByHandle[$sourceReport.handles.dimension]
                    $observedDefinition = if ($dimensionRow) { Read-DxfPoint $dimensionRow[9] } else { $null }
                    $observedRotation = if ($dimensionRow) { Read-DxfNumber $dimensionRow[11] } else { $null }
                    $positionIndex = if ($dimensionSpec.axis -eq 'y') { 0 } else { 1 }
                    $facePlacementComparison += [ordered]@{
                        dimension = $sourceReport.handles.dimension
                        position_axis = if ($positionIndex -eq 0) { 'x' } else { 'y' }
                        expected_line_position = $expectedDefinition[$positionIndex]
                        observed_line_position = if ($observedDefinition) {
                            $observedDefinition[$positionIndex]
                        } else { $null }
                        expected_rotation_rad = $expectedRotation
                        observed_rotation_rad = $observedRotation
                        matched = $dimensionRow -and $dimensionRow[1] -eq 'DIMENSION' -and
                            $null -ne $observedDefinition -and
                            [Math]::Abs($expectedDefinition[$positionIndex] -
                                        $observedDefinition[$positionIndex]) -le 1e-6 -and
                            $null -ne $observedRotation -and
                            [Math]::Abs($expectedRotation - $observedRotation) -le 1e-6
                    }
                }
                $expectedStyle = $sourceReport.planspec.dimension_style
                $observedStyle = $dimensionStyles[$sourceReport.handles.dimension]
                foreach ($field in @('name', 'text_height_m', 'arrow_size_m', 'gap_m',
                                     'scale', 'measurement_factor')) {
                    $expect = $expectedStyle.$field
                    $observe = if ($observedStyle) { $observedStyle[$field] } else { $null }
                    $matched = if ($field -eq 'name') { $expect -ceq $observe } else {
                        $null -ne $observe -and [Math]::Abs([double]$expect - [double]$observe) -le 1e-6
                    }
                    $faceStyleComparison += [ordered]@{ dimension = $sourceReport.handles.dimension;
                        property = $field; expected = $expect; observed = $observe; matched = $matched }
                }
            }
        }
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
        if ($sourceReport.schema_version -eq 'mcp-wall-thickness-l2-1' -and
            $sourceReport.status -eq 'passed' -and
            ($sourceReport.first_save.sha256 -eq $before -or
             $sourceReport.second_save.sha256 -eq $before)) {
            $richSourceReport = $sourceReport
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
    $faceReferenceMismatch = @($faceReferenceComparison | Where-Object { -not $_.matched }).Count -gt 0
    $faceStyleMismatch = @($faceStyleComparison | Where-Object { -not $_.matched }).Count -gt 0
    $facePlacementMismatch = @($facePlacementComparison | Where-Object { -not $_.matched }).Count -gt 0
    $faceFixtureMismatch = $faceFixtureValid -eq $false
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
    $geometryComparison = @()
    $geometrySourceValid = $null
    if ($richSourceReport -and $richSourceReport.planspec.fixture) {
        $fixtureName = [string]$richSourceReport.planspec.fixture
        if ($fixtureName -notin @('synthetic-room.planspec.json',
                                  'synthetic-layer.planspec.json',
                                  'synthetic-contour.planspec.json',
                                  'synthetic-wall.planspec.json',
                                  'synthetic-wall-gap.planspec.json',
                                  'synthetic-door-swing.planspec.json',
                                  'synthetic-window.planspec.json',
                                  'synthetic-wall-join.planspec.json',
                                  'synthetic-wall-face-dimension-readable-v7.planspec.json',
                                  'synthetic-wall-face-dimension-vertical-v7.planspec.json')) {
            $geometrySourceValid = $false
        } else {
            $fixturePath = Join-Path $PSScriptRoot (Join-Path 'masterplan\fixtures' $fixtureName)
            $geometrySourceValid = (Test-Path -LiteralPath $fixturePath -PathType Leaf) -and
                ((Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash -eq
                 $richSourceReport.planspec.fixture_sha256)
        }
        if ($geometrySourceValid) {
            $fixture = Get-Content -LiteralPath $fixturePath -Raw | ConvertFrom-Json
            $nodes = @{}
            foreach ($node in $fixture.nodes) {
                $nodes[$node.id] = @(
                    ([double]$node.x + [double]$fixture.origin.x),
                    ([double]$node.y + [double]$fixture.origin.y),
                    0.0
                )
            }
            foreach ($line in $fixture.lines) {
                $handle = [string]$richSourceReport.planspec.handles_by_id.($line.id)
                $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                $expectedStart = $nodes[$line.start]
                $expectedEnd = $nodes[$line.end]
                $matched = $row -and $row[1] -eq 'LINE' -and $row[3] -eq $line.layer -and
                    (((Same-Point $expectedStart $observedStart) -and
                      (Same-Point $expectedEnd $observedEnd)) -or
                     ((Same-Point $expectedStart $observedEnd) -and
                      (Same-Point $expectedEnd $observedStart)))
                $geometryComparison += [ordered]@{
                    planspec_id = $line.id; kind = 'LINE'; handle = $handle
                    expected_layer = $line.layer
                    expected_start = $expectedStart; expected_end = $expectedEnd
                    autocad_start = $observedStart; autocad_end = $observedEnd
                    matched_1e_6 = [bool]$matched
                }
            }
            foreach ($circle in $fixture.circles) {
                $handle = [string]$richSourceReport.planspec.handles_by_id.($circle.id)
                $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                $observedCenter = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $observedRadius = if ($row) { Read-DxfNumber $row[17] } else { $null }
                $expectedCenter = $nodes[$circle.center]
                $expectedRadius = [double]$circle.radius
                $matched = $row -and $row[1] -eq 'CIRCLE' -and
                    $row[3] -eq $circle.layer -and
                    (Same-Point $expectedCenter $observedCenter) -and
                    $null -ne $observedRadius -and
                    [Math]::Abs($expectedRadius - $observedRadius) -le 1e-6
                $geometryComparison += [ordered]@{
                    planspec_id = $circle.id; kind = 'CIRCLE'; handle = $handle
                    expected_layer = $circle.layer
                    expected_center = $expectedCenter; expected_radius = $expectedRadius
                    autocad_center = $observedCenter; autocad_radius = $observedRadius
                    matched_1e_6 = [bool]$matched
                }
            }
            if ($fixture.schema_version -in @('planspec-3', 'planspec-7') -and
                $fixture.walls.Count -eq 1 -and $fixture.openings.Count -eq 0) {
                $wall = $fixture.walls[0]
                $a = $nodes[$wall.start]
                $b = $nodes[$wall.end]
                $dx = $b[0] - $a[0]
                $dy = $b[1] - $a[1]
                $length = [Math]::Sqrt($dx * $dx + $dy * $dy)
                $effectiveThickness = [double]$wall.thickness_m
                if ($richSourceReport.schema_version -eq 'mcp-wall-thickness-l2-1' -and
                    $richSourceReport.second_save.sha256 -eq $before) {
                    $effectiveThickness = [double]$richSourceReport.measurements_m.edited
                }
                $half = $effectiveThickness / 2.0
                $nx = -$dy * $half / $length
                $ny = $dx * $half / $length
                $corners = @(
                    @(($a[0] + $nx), ($a[1] + $ny), 0.0),
                    @(($b[0] + $nx), ($b[1] + $ny), 0.0),
                    @(($b[0] - $nx), ($b[1] - $ny), 0.0),
                    @(($a[0] - $nx), ($a[1] - $ny), 0.0)
                )
                for ($index = 0; $index -lt 4; $index++) {
                    $partId = '{0}__edge_{1}' -f $wall.id, $index
                    $handle = [string]$richSourceReport.planspec.handles_by_id.($partId)
                    $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                    $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                    $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                    $expectedStart = $corners[$index]
                    $expectedEnd = $corners[($index + 1) % 4]
                    $matched = $row -and $row[1] -eq 'LINE' -and $row[3] -eq $wall.layer -and
                        (((Same-Point $expectedStart $observedStart) -and
                          (Same-Point $expectedEnd $observedEnd)) -or
                         ((Same-Point $expectedStart $observedEnd) -and
                          (Same-Point $expectedEnd $observedStart)))
                    $geometryComparison += [ordered]@{
                        planspec_id = $partId; source_id = $wall.id; kind = 'WALL_EDGE'
                        handle = $handle; expected_layer = $wall.layer
                        expected_start = $expectedStart; expected_end = $expectedEnd
                        autocad_start = $observedStart; autocad_end = $observedEnd
                        matched_1e_6 = [bool]$matched
                    }
                }
            }
            if (($fixture.schema_version -eq 'planspec-3' -and
                 $fixture.walls.Count -eq 1 -and $fixture.openings.Count -gt 0 -and
                 @($fixture.openings | Where-Object { $_.kind -ne 'clear' }).Count -eq 0) -or
                ($fixture.schema_version -eq 'planspec-4' -and
                 $fixture.walls.Count -eq 1 -and $fixture.openings.Count -eq 1 -and
                 $fixture.openings[0].kind -in @('door', 'window'))) {
                $wall = $fixture.walls[0]
                $a = $nodes[$wall.start]
                $b = $nodes[$wall.end]
                $dx = $b[0] - $a[0]
                $dy = $b[1] - $a[1]
                $length = [Math]::Sqrt($dx * $dx + $dy * $dy)
                $ux = $dx / $length
                $uy = $dy / $length
                $half = [double]$wall.thickness_m / 2.0
                $nx = -$uy * $half
                $ny = $ux * $half
                $intervals = @($fixture.openings | Sort-Object { [double]$_.offset_m }, id)
                $spans = @()
                $previous = 0.0
                foreach ($opening in $intervals) {
                    $start = [double]$opening.offset_m
                    $spans += ,@($previous, $start)
                    $previous = $start + [double]$opening.width_m
                }
                $spans += ,@($previous, $length)
                $expectedSegments = @()
                foreach ($sideSpec in @(@(1, 'left'), @(-1, 'right'))) {
                    $side = [int]$sideSpec[0]
                    $sideName = [string]$sideSpec[1]
                    for ($index = 0; $index -lt $spans.Count; $index++) {
                        $partId = '{0}__{1}_span_{2}' -f $wall.id, $sideName, $index
                        $expectedSegments += [ordered]@{
                            part_id = $partId; source_id = $wall.id
                            start = Wall-Point $a $ux $uy $nx $ny $spans[$index][0] $side
                            end = Wall-Point $a $ux $uy $nx $ny $spans[$index][1] $side
                        }
                    }
                }
                foreach ($cap in @(@('start_cap', 0.0), @('end_cap', $length))) {
                    $expectedSegments += [ordered]@{
                        part_id = '{0}__{1}' -f $wall.id, $cap[0]
                        source_id = $wall.id
                        start = Wall-Point $a $ux $uy $nx $ny $cap[1] 1
                        end = Wall-Point $a $ux $uy $nx $ny $cap[1] -1
                    }
                }
                foreach ($opening in $intervals) {
                    $start = [double]$opening.offset_m
                    foreach ($jamb in @(@('jamb_start', $start),
                                        @('jamb_end', ($start + [double]$opening.width_m)))) {
                        $expectedSegments += [ordered]@{
                            part_id = '{0}__{1}' -f $opening.id, $jamb[0]
                            source_id = $opening.id
                            start = Wall-Point $a $ux $uy $nx $ny $jamb[1] 1
                            end = Wall-Point $a $ux $uy $nx $ny $jamb[1] -1
                        }
                    }
                }
                foreach ($segment in $expectedSegments) {
                    $partId = $segment.part_id
                    $handle = [string]$richSourceReport.planspec.handles_by_id.($partId)
                    $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                    $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                    $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                    $matched = $row -and $row[1] -eq 'LINE' -and $row[3] -eq $wall.layer -and
                        (((Same-Point $segment.start $observedStart) -and
                          (Same-Point $segment.end $observedEnd)) -or
                         ((Same-Point $segment.start $observedEnd) -and
                          (Same-Point $segment.end $observedStart)))
                    $geometryComparison += [ordered]@{
                        planspec_id = $partId; source_id = $segment.source_id
                        kind = 'WALL_GAP_EDGE'; handle = $handle; expected_layer = $wall.layer
                        expected_start = $segment.start; expected_end = $segment.end
                        autocad_start = $observedStart; autocad_end = $observedEnd
                        matched_1e_6 = [bool]$matched
                    }
                }
                if ($fixture.schema_version -eq 'planspec-4') {
                    if ($fixture.openings[0].kind -eq 'window') {
                        $window = $fixture.openings[0]
                        foreach ($rail in @(@('sill_rail', 1.0, [double]$window.elevation.sill_m),
                                           @('head_rail', -1.0, [double]$window.elevation.head_m))) {
                            $partId = '{0}__{1}' -f $window.id, $rail[0]
                            $handle = [string]$richSourceReport.planspec.handles_by_id.($partId)
                            $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                            $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                            $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                            $start = Wall-Point $a $ux $uy $nx $ny ([double]$window.offset_m) ([double]$rail[1] / 2.0)
                            $end = Wall-Point $a $ux $uy $nx $ny ([double]$window.offset_m + [double]$window.width_m) ([double]$rail[1] / 2.0)
                            $start[2] = [double]$rail[2]
                            $end[2] = [double]$rail[2]
                            $matched = $row -and $row[1] -eq 'LINE' -and
                                $row[3] -eq $wall.layer -and
                                (((Same-Point $start $observedStart) -and
                                  (Same-Point $end $observedEnd)) -or
                                 ((Same-Point $start $observedEnd) -and
                                  (Same-Point $end $observedStart)))
                            $geometryComparison += [ordered]@{
                                planspec_id = $partId; source_id = $window.id
                                kind = 'WINDOW_RAIL_3D'; handle = $handle
                                expected_layer = $wall.layer
                                expected_start = $start; expected_end = $end
                                autocad_start = $observedStart; autocad_end = $observedEnd
                                matched_1e_6 = [bool]$matched
                            }
                        }
                    }
                }
                if ($fixture.schema_version -eq 'planspec-4' -and
                    $fixture.openings[0].kind -eq 'door') {
                    $door = $fixture.openings[0]
                    $width = [double]$door.width_m
                    $distance = [double]$door.offset_m
                    $side = if ($door.swing.side -eq 'left') { 1.0 } else { -1.0 }
                    $hingeAtStart = $door.swing.hinge -eq 'start'
                    $hingeDistance = if ($hingeAtStart) { $distance } else { $distance + $width }
                    $hinge = Wall-Point $a $ux $uy $nx $ny $hingeDistance $side
                    $direction = if ($hingeAtStart) { 1.0 } else { -1.0 }
                    $closed = @(($hinge[0] + $direction * $ux * $width),
                                ($hinge[1] + $direction * $uy * $width), 0.0)
                    $opened = @(($hinge[0] - $uy * $side * $width),
                                ($hinge[1] + $ux * $side * $width), 0.0)
                    $leafId = '{0}__leaf_open' -f $door.id
                    $leafHandle = [string]$richSourceReport.planspec.handles_by_id.($leafId)
                    $leafRow = if ($leafHandle) { $entityByHandle[$leafHandle] } else { $null }
                    $leafStart = if ($leafRow) { Read-DxfPoint $leafRow[9] } else { $null }
                    $leafEnd = if ($leafRow) { Read-DxfPoint $leafRow[16] } else { $null }
                    $leafMatched = $leafRow -and $leafRow[1] -eq 'LINE' -and
                        $leafRow[3] -eq $wall.layer -and
                        (((Same-Point $hinge $leafStart) -and (Same-Point $opened $leafEnd)) -or
                         ((Same-Point $hinge $leafEnd) -and (Same-Point $opened $leafStart)))
                    $geometryComparison += [ordered]@{
                        planspec_id = $leafId; source_id = $door.id; kind = 'DOOR_LEAF'
                        handle = $leafHandle; expected_layer = $wall.layer
                        expected_start = $hinge; expected_end = $opened
                        autocad_start = $leafStart; autocad_end = $leafEnd
                        matched_1e_6 = [bool]$leafMatched
                    }
                    $arcId = '{0}__swing_arc' -f $door.id
                    $arcHandle = [string]$richSourceReport.planspec.handles_by_id.($arcId)
                    $arcRow = if ($arcHandle) { $entityByHandle[$arcHandle] } else { $null }
                    $arcCenter = if ($arcRow) { Read-DxfPoint $arcRow[9] } else { $null }
                    $arcRadius = if ($arcRow) { Read-DxfNumber $arcRow[17] } else { $null }
                    $arcStart = if ($arcRow) { Read-DxfNumber $arcRow[11] } else { $null }
                    $arcEnd = if ($arcRow) { Read-DxfNumber $arcRow[18] } else { $null }
                    # AutoLISP entget exposes DXF 50/51 angles in radians.
                    $turn = 2 * [Math]::PI
                    $expectedStartAngle = [Math]::Atan2(($closed[1] - $hinge[1]),
                                                        ($closed[0] - $hinge[0]))
                    $expectedEndAngle = [Math]::Atan2(($opened[1] - $hinge[1]),
                                                      ($opened[0] - $hinge[0]))
                    $expectedStartAngle = ($expectedStartAngle + $turn) % $turn
                    $expectedEndAngle = ($expectedEndAngle + $turn) % $turn
                    $arcMatched = $arcRow -and $arcRow[1] -eq 'ARC' -and
                        $arcRow[3] -eq $wall.layer -and
                        (Same-Point $hinge $arcCenter) -and $null -ne $arcRadius -and
                        [Math]::Abs($arcRadius - $width) -le 1e-6 -and
                        $null -ne $arcStart -and $null -ne $arcEnd -and
                        [Math]::Abs((($arcStart + $turn) % $turn) - $expectedStartAngle) -le 1e-6 -and
                        [Math]::Abs((($arcEnd + $turn) % $turn) - $expectedEndAngle) -le 1e-6
                    $geometryComparison += [ordered]@{
                        planspec_id = $arcId; source_id = $door.id; kind = 'DOOR_SWING_ARC'
                        handle = $arcHandle; expected_layer = $wall.layer
                        expected_center = $hinge; expected_radius = $width
                        angle_unit = 'radians'
                        expected_start_angle = $expectedStartAngle
                        expected_end_angle = $expectedEndAngle
                        autocad_center = $arcCenter; autocad_radius = $arcRadius
                        autocad_start_angle = $arcStart; autocad_end_angle = $arcEnd
                        matched_1e_6 = [bool]$arcMatched
                    }
                }
            }
            if ($fixture.schema_version -eq 'planspec-5' -and
                $fixture.walls.Count -eq 2 -and $fixture.joins.Count -eq 1 -and
                $fixture.openings.Count -eq 0) {
                $join = $fixture.joins[0]
                $wallById = @{}
                foreach ($wall in $fixture.walls) { $wallById[$wall.id] = $wall }
                $first = $wallById[$join.wall_a_id]
                $second = $wallById[$join.wall_b_id]
                $junction = $nodes[$first.($join.wall_a_end)]
                $farAKey = if ($join.wall_a_end -eq 'end') { 'start' } else { 'end' }
                $farBKey = if ($join.wall_b_end -eq 'end') { 'start' } else { 'end' }
                $farA = $nodes[$first.$farAKey]
                $farB = $nodes[$second.$farBKey]
                $av = @(($farA[0] - $junction[0]), ($farA[1] - $junction[1]))
                $bv = @(($farB[0] - $junction[0]), ($farB[1] - $junction[1]))
                $lengthA = [Math]::Sqrt($av[0] * $av[0] + $av[1] * $av[1])
                $lengthB = [Math]::Sqrt($bv[0] * $bv[0] + $bv[1] * $bv[1])
                $u = @(($av[0] / $lengthA), ($av[1] / $lengthA))
                $v = @(($bv[0] / $lengthB), ($bv[1] / $lengthB))
                $half = [double]$first.thickness_m / 2.0
                $local = @(
                    @(0.0, -$half), @($lengthA, -$half), @($lengthA, $half),
                    @($half, $half), @($half, $lengthB), @(-$half, $lengthB),
                    @(-$half, 0.0), @(0.0, 0.0)
                )
                for ($index = 0; $index -lt 8; $index++) {
                    $startLocal = $local[$index]
                    $endLocal = $local[($index + 1) % 8]
                    $expectedStart = Join-Point $junction $u $v $startLocal[0] $startLocal[1]
                    $expectedEnd = Join-Point $junction $u $v $endLocal[0] $endLocal[1]
                    $partId = '{0}__outline_{1}' -f $join.id, $index
                    $handle = [string]$richSourceReport.planspec.handles_by_id.($partId)
                    $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                    $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                    $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                    $matched = $row -and $row[1] -eq 'LINE' -and $row[3] -eq $first.layer -and
                        (((Same-Point $expectedStart $observedStart) -and
                          (Same-Point $expectedEnd $observedEnd)) -or
                         ((Same-Point $expectedStart $observedEnd) -and
                          (Same-Point $expectedEnd $observedStart)))
                    $geometryComparison += [ordered]@{
                        planspec_id = $partId; source_id = $join.id; kind = 'WALL_UNION_EDGE'
                        handle = $handle; expected_layer = $first.layer
                        expected_start = $expectedStart; expected_end = $expectedEnd
                        autocad_start = $observedStart; autocad_end = $observedEnd
                        matched_1e_6 = [bool]$matched
                    }
                }
            }
        }
    }
    $geometryMismatch = ($geometrySourceValid -eq $false) -or
        @($geometryComparison | Where-Object { -not $_.matched_1e_6 }).Count -gt 0
    $wallModelCountMatch = $null
    if ($richSourceReport -and $richSourceReport.planspec.fixture -in
            @('synthetic-wall.planspec.json', 'synthetic-wall-gap.planspec.json',
              'synthetic-door-swing.planspec.json', 'synthetic-window.planspec.json',
              'synthetic-wall-join.planspec.json')) {
        $wallModelCountMatch = $declaredCount -eq $geometryComparison.Count
    }
    if ($richSourceReport.schema_version -eq 'mcp-wall-thickness-l2-1') {
        $wallModelCountMatch = $declaredCount -eq ($geometryComparison.Count + 1)
    }
    $report = [ordered]@{
        schema_version = 'mcp-autocad-audit-l4-11'
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
        face_reference_comparison = $faceReferenceComparison
        face_style_comparison = $faceStyleComparison
        face_placement_comparison = $facePlacementComparison
        face_fixture_valid = $faceFixtureValid
        property_comparison = $propertyComparison
        geometry_source_valid = $geometrySourceValid
        source_report_match = $sourceReportMatch
        wall_model_count_match = $wallModelCountMatch
        geometry_comparison = $geometryComparison
        semantic_verdict = if ($sourceReportMatch -eq $false -or $dimensionMismatch -or
                              $faceReferenceMismatch -or $faceStyleMismatch -or $facePlacementMismatch -or
                              $faceFixtureMismatch -or
                              $propertyMismatch -or $geometryMismatch -or
                              $wallModelCountMatch -eq $false) {
            'mismatch'
        } elseif ($expected.Count -gt 0 -or $faceReferenceComparison.Count -gt 0 -or
                  $facePlacementComparison.Count -gt 0 -or
                  $faceStyleComparison.Count -gt 0 -or
                  $propertyComparison.Count -gt 0 -or
                  $geometryComparison.Count -gt 0) {
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
        } elseif ($sourceReportMatch -eq $false -or $dimensionMismatch -or
                  $faceReferenceMismatch -or $faceStyleMismatch -or $facePlacementMismatch -or
                  $faceFixtureMismatch -or
                  $propertyMismatch -or $geometryMismatch -or
                  $wallModelCountMatch -eq $false) { 'semantic_mismatch'
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
