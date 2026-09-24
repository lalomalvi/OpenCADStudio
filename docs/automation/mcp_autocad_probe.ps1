param(
    [Parameter(Mandatory = $true)]
    [string]$SyntheticDwg,
    [string]$AutoCadCore = 'C:\Program Files\Autodesk\AutoCAD 2025\accoreconsole.exe',
    [Nullable[int]]$ExpectedInsunits = $null,
    [string]$ExpectedSourceReportSha256 = '',
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

function Same-Angle([double]$expected, [double]$observed) {
    $turn = 2.0 * [Math]::PI
    $delta = [Math]::Abs(($observed - $expected) % $turn)
    return [Math]::Min($delta, $turn - $delta) -le 1e-6
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
(foreach ocs_layer_name '("A-THIN" "A-THICK")
  (setq ocs_layer_entity (tblobjname "LAYER" ocs_layer_name))
  (setq ocs_layer_data (if ocs_layer_entity (entget ocs_layer_entity) nil))
  (if ocs_layer_data
    (write-line (strcat "LAYERWEIGHT|" ocs_layer_name "|"
                        (ocs_value ocs_layer_data 370)) ocs_file)))
(setq ocs_layout_dict (dictsearch (namedobjdict) "ACAD_LAYOUT"))
(if ocs_layout_dict
  (write-line (strcat "MODELLAYOUT|" (vl-princ-to-string
    (dictsearch (cdr (assoc -1 ocs_layout_dict)) "Model"))) ocs_file))
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
      (write-line (strcat "PENWEIGHT|" (ocs_value ocs_data 5) "|"
                          (ocs_value ocs_data 370)) ocs_file)
      (write-line (strcat "COLORDATA|" (ocs_value ocs_data 5) "|"
                          (ocs_value ocs_data 62)) ocs_file)
      (if (= (cdr (assoc 0 ocs_data)) "TEXT")
        (write-line (strcat "TEXTDATA|" (ocs_value ocs_data 5) "|"
                            (ocs_value ocs_data 1) "|"
                            (ocs_value ocs_data 7)) ocs_file))
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
    $axisDefinitionComparison = @()
    $axisStyleComparison = @()
    $axisFixtureValid = $null
    $lengthGeometryComparison = @()
    $lengthFixtureValid = $null
    $plotProfileComparison = @()
    $plotGeometryComparison = @()
    $plotSourceValid = $null
    $plotContentComparison = @()
    $plotContentSourceValid = $null
    $plotContentExpectedCount = 4
    $plotCtbComparison = @()
    $plotCtbSourceValid = $null
    $modelLayoutFields = @{}
    if ($censusDone) {
        $layoutLine = $lines | Where-Object { $_.StartsWith('MODELLAYOUT|') } |
            Select-Object -First 1
        if ($layoutLine) {
            foreach ($pair in [regex]::Matches($layoutLine,
                '\((\d+)\s+\.\s+(.*?)\)(?=\s+\(\d+\s+\.)')) {
                $code = $pair.Groups[1].Value
                if (-not $modelLayoutFields.ContainsKey($code)) {
                    $modelLayoutFields[$code] = $pair.Groups[2].Value
                }
            }
        }
    }
    $richSourceReport = $null
    $sourceReportMatch = $null
    $sourceReportPath = Join-Path ([IO.Path]::GetDirectoryName($drawing)) 'report.json'
    if (Test-Path -LiteralPath $sourceReportPath -PathType Leaf) {
        $sourceReport = Get-Content -LiteralPath $sourceReportPath -Raw | ConvertFrom-Json
        $sourceReportMatch = $sourceReport.status -eq 'passed' -and
            ($sourceReport.verified_output.sha256 -eq $before -or
             $sourceReport.first_save.sha256 -eq $before -or
             $sourceReport.second_save.sha256 -eq $before -or
             $sourceReport.verified_dwg.sha256 -eq $before)
        if ($ExpectedSourceReportSha256) {
            $sourceReportMatch = $sourceReportMatch -and
                (Get-FileHash -LiteralPath $sourceReportPath -Algorithm SHA256).Hash -eq
                    $ExpectedSourceReportSha256
        }
        if ($sourceReport.schema_version -eq 'mcp-metric-page-setup-l2-1' -and
            $sourceReport.status -eq 'passed' -and
            $sourceReport.verified_dwg.sha256 -eq $before) {
            $plotSourceValid = ((@($sourceReport.fixture_commands) -join ';') -ceq
                'SETVAR INSUNITS 6;LINE 0,0 4,0;LINE 4,0 4,1')
            $setup = $sourceReport.page_setup_after
            $plotSourceValid = $plotSourceValid -and
                $sourceReport.page_setup_before.metric_scale_denominator -eq 100 -and
                $setup.metric_scale_denominator -eq 100 -and
                $setup.insertion_units -eq 6 -and
                $setup.paper_mm[0] -eq 210 -and $setup.paper_mm[1] -eq 297
            $expectedCodes = [ordered]@{
                '2' = [string]$setup.printer; '4' = [string]$setup.paper_size
                '40' = 0.0; '41' = 0.0; '42' = 0.0; '43' = 0.0
                '44' = 210.0; '45' = 297.0
                '142' = 10.0; '143' = 1.0; '70' = 1156.0
                '72' = 1.0; '73' = 1.0; '74' = 1.0; '75' = 1.0
                '147' = 254.0
            }
            foreach ($code in $expectedCodes.Keys) {
                $want = $expectedCodes[$code]
                $got = $modelLayoutFields[$code]
                $matched = if ($code -in @('2','4')) {
                    $null -ne $got -and $want -ceq $got
                } else {
                    $null -ne $got -and $null -ne (Read-DxfNumber $got) -and
                        [Math]::Abs([double]$want - [double](Read-DxfNumber $got)) -le 1e-6
                }
                $plotProfileComparison += [ordered]@{
                    code = $code; expected = $want; autocad = $got; matched = $matched
                }
            }
            for ($index = 0; $index -lt 2; $index++) {
                $handle = [string]$sourceReport.line_handles[$index]
                $row = $entityByHandle[$handle]
                $line = $sourceReport.line_entities[$index]
                $start = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $end = if ($row) { Read-DxfPoint $row[16] } else { $null }
                $plotGeometryComparison += [ordered]@{
                    handle = $handle; expected_start = $line.start; expected_end = $line.end
                    autocad_start = $start; autocad_end = $end
                    matched = $row -and $row[1] -eq 'LINE' -and
                        (Same-Point $line.start $start) -and (Same-Point $line.end $end)
                }
            }
        }
        if ($sourceReport.schema_version -eq 'mcp-metric-ctb-l2-1' -and
            $sourceReport.status -eq 'passed' -and
            $sourceReport.verified_dwg.sha256 -eq $before) {
            $plotCtbSourceValid = ((@($sourceReport.commands) -join ';') -ceq
                'SETVAR INSUNITS 6;LINE 0,0 4,0;LINE 4,0 4,1') -and
                $sourceReport.page_setup_before.plot_style_sheet -ceq 'monochrome.ctb' -and
                $sourceReport.page_setup_after.plot_plot_styles -eq $true -and
                $sourceReport.color_oracle.red_px -gt 0 -and
                $sourceReport.color_oracle.green_px -gt 0 -and
                $sourceReport.color_oracle.monochrome_black_at_color_px /
                    [Math]::Max(1,$sourceReport.color_oracle.sampled_color_px) -ge 0.9
            $setup = $sourceReport.page_setup_after
            $expectedCodes = [ordered]@{
                '2'='none_device'; '4'='ISO_A4_(210.00_x_297.00_MM)';
                '7'=[string]$setup.plot_style_sheet;
                '40'=0.0; '41'=0.0; '42'=0.0; '43'=0.0;
                '44'=210.0; '45'=297.0; '142'=10.0; '143'=1.0;
                '70'=1188.0; '72'=1.0; '73'=1.0; '74'=1.0;
                '75'=1.0; '147'=254.0
            }
            foreach ($code in $expectedCodes.Keys) {
                $want = $expectedCodes[$code]
                $got = $modelLayoutFields[$code]
                $matched = if ($code -in @('2','4','7')) {
                    $null -ne $got -and $want -ceq $got
                } else {
                    $null -ne $got -and $null -ne (Read-DxfNumber $got) -and
                        [Math]::Abs([double]$want - [double](Read-DxfNumber $got)) -le 1e-6
                }
                $plotCtbComparison += [ordered]@{kind='layout';code=$code;
                    expected=$want;autocad=$got;matched=[bool]$matched}
            }
            for ($index=0; $index -lt 2; $index++) {
                $handle=[string]$sourceReport.line_handles[$index]
                $source=$sourceReport.line_entities[$index]
                $row=$entityByHandle[$handle]
                $colorLine=$lines | Where-Object { $_.StartsWith("COLORDATA|$handle|") } |
                    Select-Object -First 1
                $parts=if ($colorLine) { $colorLine -split '\|' } else { @() }
                $want=@(1,3)[$index]
                $matched=$source.handle -eq $handle -and $source.type -eq 'Line' -and
                    $source.properties.common.color.Index -eq $want -and
                    $row -and $row[1] -eq 'LINE' -and
                    (Same-Point $source.start (Read-DxfPoint $row[9])) -and
                    (Same-Point $source.end (Read-DxfPoint $row[16])) -and
                    $parts.Count -eq 3 -and (Read-DxfNumber $parts[2]) -eq $want
                $plotCtbComparison += [ordered]@{kind='colored_line';handle=$handle;
                    expected_aci=$want;
                    autocad_aci=if ($parts.Count -eq 3) { $parts[2] } else { $null };
                    matched=[bool]$matched}
            }
        }
        if ($sourceReport.schema_version -in @('mcp-metric-content-l2-1',
                'mcp-metric-pen-l2-1','mcp-metric-bylayer-l2-1') -and
            $sourceReport.status -eq 'passed' -and
            $sourceReport.verified_dwg.sha256 -eq $before) {
            $penFixture = $sourceReport.schema_version -eq 'mcp-metric-pen-l2-1'
            $bylayerFixture = $sourceReport.schema_version -eq 'mcp-metric-bylayer-l2-1'
            if ($penFixture -or $bylayerFixture) { $plotContentExpectedCount = 6 }
            $expectedCommands = @('SETVAR INSUNITS 6','LINE 0,0 4,0','LINE 4,0 4,1',
                'DIMSTYLE NEW OCS_PRINT_TEST',
                'DIMSTYLE SET OCS_PRINT_TEST dimtxt 0.2',
                'DIMSTYLE SET OCS_PRINT_TEST dimasz 0.08',
                'DIMSTYLE SET OCS_PRINT_TEST dimgap 0.03',
                'DIMSTYLE SET OCS_PRINT_TEST dimscale 1',
                'DIMSTYLE SET OCS_PRINT_TEST dimlfac 1','CDIMSTY OCS_PRINT_TEST',
                'TEXT 0.5,0.5 0.2 0 TEST123','DIMLINEAR 0,0 4,0 2,-0.5')
            if ($bylayerFixture) {
                $expectedCommands = @('SETVAR INSUNITS 6','LAYER NEW A-THIN',
                    'LAYER NEW A-THICK','CLAYER A-THIN','LINE 0,0 4,0',
                    'CLAYER A-THICK','LINE 4,0 4,1','CLAYER 0') +
                    @($expectedCommands[3..($expectedCommands.Count - 1)])
            }
            $plotContentSourceValid = $sourceReport.handles.Count -eq 4 -and
                $sourceReport.reopened_entities.Count -eq 4 -and
                ((@($sourceReport.commands) -join ';') -ceq ($expectedCommands -join ';')) -and
                $sourceReport.creation.completed_commands -eq $expectedCommands.Count
            if ($penFixture -or $bylayerFixture) {
                $plotContentSourceValid = $plotContentSourceValid -and
                    $sourceReport.results.'100'.raster_100dpi.thin_horizontal_px -eq 1 -and
                    $sourceReport.results.'100'.raster_100dpi.thick_vertical_px -eq 3 -and
                    $sourceReport.results.'50'.raster_100dpi.thin_horizontal_px -eq 1 -and
                    $sourceReport.results.'50'.raster_100dpi.thick_vertical_px -eq 3
            }
            if ($penFixture) {
                $plotContentSourceValid = $plotContentSourceValid -and
                    ((@($sourceReport.expected_pen_weight_100th_mm) -join ',') -eq '13,70')
            }
            if ($bylayerFixture) {
                $plotContentSourceValid = $plotContentSourceValid -and
                    $sourceReport.expected_layer_weights_100th_mm.'A-THIN' -eq 13 -and
                    $sourceReport.expected_layer_weights_100th_mm.'A-THICK' -eq 70
            }
            $handles = @($sourceReport.handles)
            if ($plotContentSourceValid) {
                for ($index = 0; $index -lt 2; $index++) {
                    $handle = [string]$handles[$index]
                    $source = $sourceReport.reopened_entities[$index]
                    $row = $entityByHandle[$handle]
                    $matched = $source.type -eq 'Line' -and $source.handle -eq $handle -and
                        $row -and $row[1] -eq 'LINE' -and
                        (Same-Point $source.start (Read-DxfPoint $row[9])) -and
                        (Same-Point $source.end (Read-DxfPoint $row[16]))
                    $plotContentComparison += [ordered]@{kind='line'; handle=$handle;
                        expected_start=$source.start; expected_end=$source.end;
                        autocad_start=if ($row) { Read-DxfPoint $row[9] } else { $null };
                        autocad_end=if ($row) { Read-DxfPoint $row[16] } else { $null };
                        matched=[bool]$matched}
                    if ($penFixture) {
                        $penLine = $lines | Where-Object {
                            $_.StartsWith("PENWEIGHT|$handle|") } | Select-Object -First 1
                        $penParts = if ($penLine) { $penLine -split '\|' } else { @() }
                        $want = @(13,70)[$index]
                        $sourceWeight = $source.properties.common.line_weight.Value
                        $penMatch = $penParts.Count -eq 3 -and
                            $sourceWeight -eq $want -and
                            (Read-DxfNumber $penParts[2]) -eq $want
                        $plotContentComparison += [ordered]@{kind='pen_weight';handle=$handle;
                            expected=$want;source=$sourceWeight;
                            autocad=if ($penParts.Count -eq 3) { $penParts[2] } else { $null };
                            matched=[bool]$penMatch}
                    }
                    if ($bylayerFixture) {
                        $layerName = @('A-THIN','A-THICK')[$index]
                        $want = @(13,70)[$index]
                        $penLine = $lines | Where-Object {
                            $_.StartsWith("PENWEIGHT|$handle|") } | Select-Object -First 1
                        $penParts = if ($penLine) { $penLine -split '\|' } else { @() }
                        $layerLine = $lines | Where-Object {
                            $_.StartsWith("LAYERWEIGHT|$layerName|") } | Select-Object -First 1
                        $layerParts = if ($layerLine) { $layerLine -split '\|' } else { @() }
                        $sourceLayerWeight = $sourceReport.reopened_layers.$layerName.properties.line_weight.Value
                        $layerMatch = $source.layer -ceq $layerName -and
                            $source.properties.common.line_weight -ceq 'ByLayer' -and
                            $sourceLayerWeight -eq $want -and
                            $row[3] -ceq $layerName -and $penParts.Count -eq 3 -and
                            $penParts[2] -ceq '-' -and
                            $layerParts.Count -eq 3 -and
                            (Read-DxfNumber $layerParts[2]) -eq $want
                        $plotContentComparison += [ordered]@{kind='bylayer_weight';
                            handle=$handle;layer=$layerName;expected=$want;
                            source_layer_weight=$sourceLayerWeight;
                            entity_weight=if ($penParts.Count -eq 3) {
                                $penParts[2] } else { $null };
                            layer_weight=if ($layerParts.Count -eq 3) { $layerParts[2] } else { $null };
                            matched=[bool]$layerMatch}
                    }
                }
                $textHandle = [string]$handles[2]
                $textSource = $sourceReport.reopened_entities[2]
                $textRow = $entityByHandle[$textHandle]
                $textLine = $lines | Where-Object { $_.StartsWith("TEXTDATA|$textHandle|") } |
                    Select-Object -First 1
                $textParts = if ($textLine) { $textLine -split '\|' } else { @() }
                $textPoint = @($textSource.properties.insertion_point.x,
                    $textSource.properties.insertion_point.y,
                    $textSource.properties.insertion_point.z)
                $textMatch = $textSource.type -eq 'Text' -and
                    $textSource.handle -eq $textHandle -and $textRow -and
                    $textRow[1] -eq 'TEXT' -and
                    (Same-Point $textPoint (Read-DxfPoint $textRow[9])) -and
                    [Math]::Abs([double]$textSource.properties.height -
                        [double](Read-DxfNumber $textRow[17])) -le 1e-6 -and
                    $textParts.Count -eq 4 -and
                    $textParts[2] -ceq $textSource.properties.value -and
                    $textParts[3] -ceq $textSource.properties.style
                $plotContentComparison += [ordered]@{kind='text';handle=$textHandle;
                    expected=$textSource.properties.value;
                    autocad=if ($textParts.Count -eq 4) { $textParts[2] } else { $null };
                    matched=[bool]$textMatch}
                $dimHandle = [string]$handles[3]
                $dimSource = $sourceReport.reopened_entities[3]
                $dimRow = $entityByHandle[$dimHandle]
                $dimStyle = $dimensionStyles[$dimHandle]
                $base = $dimSource.properties.Linear.base
                $dimMatch = $dimSource.type -eq 'Dimension' -and
                    $dimSource.handle -eq $dimHandle -and $dimRow -and
                    $dimRow[1] -eq 'DIMENSION' -and
                    [Math]::Abs([double](Read-DxfNumber $dimRow[4]) - 4.0) -le 1e-6 -and
                    (Same-Point @(0.0,0.0,0.0) (Read-DxfPoint $dimRow[13])) -and
                    (Same-Point @(4.0,0.0,0.0) (Read-DxfPoint $dimRow[14])) -and
                    $base.actual_measurement -eq 4.0 -and
                    $base.style_name -ceq 'OCS_PRINT_TEST' -and
                    $dimStyle.name -ceq 'OCS_PRINT_TEST' -and
                    $dimStyle.text_height_m -eq 0.2 -and
                    $dimStyle.arrow_size_m -eq 0.08 -and
                    $dimStyle.gap_m -eq 0.03 -and
                    $dimStyle.scale -eq 1.0 -and
                    $dimStyle.measurement_factor -eq 1.0
                $plotContentComparison += [ordered]@{kind='dimension';handle=$dimHandle;
                    expected_measurement=4.0;
                    autocad_measurement=if ($dimRow) { Read-DxfNumber $dimRow[4] } else { $null };
                    expected_style='OCS_PRINT_TEST';autocad_style=$dimStyle;
                    matched=[bool]$dimMatch}
            }
        }
        if ($sourceReport.schema_version -eq 'mcp-wall-length-l2-1' -and
            $sourceReport.status -eq 'passed' -and
            ($sourceReport.first_save.sha256 -eq $before -or
             $sourceReport.second_save.sha256 -eq $before)) {
            $fixtureName = [string]$sourceReport.planspec.fixture
            $lengthFixtureValid = $fixtureName -in @(
                'synthetic-wall-axis-endpoints-v9.planspec.json',
                'synthetic-wall-aligned-endpoints-v9.planspec.json')
            if ($lengthFixtureValid) {
                $fixturePath = Join-Path $PSScriptRoot (Join-Path 'masterplan\fixtures' $fixtureName)
                $lengthFixtureValid = (Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash -eq
                    $sourceReport.planspec.fixture_sha256
            }
            $wall = if ($sourceReport.first_save.sha256 -eq $before) {
                $sourceReport.wall_before
            } else { $sourceReport.wall_after }
            $expected[$sourceReport.handles.dimension] = if ($sourceReport.first_save.sha256 -eq $before) {
                [double]$sourceReport.measurements_m.initial
            } else { [double]$sourceReport.measurements_m.edited }
            for ($index = 0; $index -lt 4; $index++) {
                $handle = [string]$sourceReport.handles.wall_edges[$index]
                $row = $entityByHandle[$handle]
                $start = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $end = if ($row) { Read-DxfPoint $row[16] } else { $null }
                $lengthGeometryComparison += [ordered]@{
                    handle = $handle; expected_start = $wall.points[$index][0]
                    expected_end = $wall.points[$index][1]; autocad_start = $start
                    autocad_end = $end; matched = $row -and $row[1] -eq 'LINE' -and
                        (Same-Point $wall.points[$index][0] $start) -and
                        (Same-Point $wall.points[$index][1] $end)
                }
            }
            foreach ($item in @(@{ index = 0; source = $sourceReport.handles.start_cap },
                                @{ index = 1; source = $sourceReport.handles.end_cap })) {
                $observedRef = @($dimensionReferences | Where-Object {
                    $_.dimension -eq $sourceReport.handles.dimension -and $_.index -eq $item.index })
                $faceReferenceComparison += [ordered]@{
                    dimension = $sourceReport.handles.dimension; index = $item.index
                    expected_source = $item.source
                    observed_source = if ($observedRef.Count -eq 1) { $observedRef[0].source } else { $null }
                    observed_osnap = if ($observedRef.Count -eq 1) { $observedRef[0].osnap } else { $null }
                    matched = $observedRef.Count -eq 1 -and
                        $observedRef[0].source -eq $item.source -and $observedRef[0].osnap -eq 2
                }
            }
        }
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
            $sourceReport.verified_output.sha256 -eq $before -and
            $sourceReport.axis_dimension.handle) {
            $axisHandle = [string]$sourceReport.axis_dimension.handle
            $expected[$axisHandle] = [double]$sourceReport.axis_dimension.roundtrip_measurement
            $axisFixtureName = [string]$sourceReport.planspec.fixture
            $axisFixtureValid = $axisFixtureName -in @(
                'synthetic-wall-axis-span-v8.planspec.json',
                'synthetic-wall-axis-span-vertical-v8.planspec.json',
                'synthetic-wall-axis-endpoints-v9.planspec.json',
                'synthetic-wall-aligned-endpoints-v9.planspec.json')
            if ($axisFixtureValid) {
                $axisFixturePath = Join-Path $PSScriptRoot (Join-Path 'masterplan\fixtures' $axisFixtureName)
                $axisFixtureValid = (Get-FileHash -LiteralPath $axisFixturePath -Algorithm SHA256).Hash -eq
                    $sourceReport.planspec.fixture_sha256
            }
            if ($axisFixtureValid) {
                $axisFixture = Get-Content -LiteralPath $axisFixturePath -Raw | ConvertFrom-Json
                $spec = $axisFixture.dimensions[0]
                $expectedKind = if ($spec.axis -eq 'aligned') { 'Aligned' } else { 'Linear' }
                $kindMatches = if ($axisFixture.schema_version -eq 'planspec-9') {
                    $sourceReport.axis_dimension.kind -eq $expectedKind
                } else {
                    $null -eq $sourceReport.axis_dimension.kind -or
                    $sourceReport.axis_dimension.kind -eq $expectedKind
                }
                $axisFixtureValid = $axisHandle -eq
                    [string]$sourceReport.planspec.handles_by_id.($spec.id) -and
                    [Math]::Abs([double]$sourceReport.axis_dimension.roundtrip_measurement -
                                [double]$spec.value) -le 1e-6 -and
                    $kindMatches
                foreach ($field in @('name', 'text_height_m', 'arrow_size_m', 'gap_m',
                                     'scale', 'measurement_factor')) {
                    $fixtureValue = $axisFixture.dimension_style.$field
                    $reportValue = $sourceReport.axis_dimension.dimension_style.$field
                    $axisFixtureValid = $axisFixtureValid -and $(if ($field -eq 'name') {
                        $fixtureValue -ceq $reportValue } else {
                        [Math]::Abs([double]$fixtureValue - [double]$reportValue) -le 1e-6 })
                }
                $startNode = @($axisFixture.nodes | Where-Object { $_.id -eq $spec.start })[0]
                $endNode = @($axisFixture.nodes | Where-Object { $_.id -eq $spec.end })[0]
                $startPoint = @(([double]$startNode.x + [double]$axisFixture.origin.x),
                                ([double]$startNode.y + [double]$axisFixture.origin.y), 0.0)
                $endPoint = @(([double]$endNode.x + [double]$axisFixture.origin.x),
                              ([double]$endNode.y + [double]$axisFixture.origin.y), 0.0)
                $offset = [double]$axisFixture.dimension_placements[0].offset_m
                $isHorizontal = $spec.axis -eq 'x'
                $isAligned = $spec.axis -eq 'aligned'
                $lineCoordinate = if ($isHorizontal) { $startPoint[1] + $offset } else {
                    $startPoint[0] - $offset }
                $rotation = if ($isHorizontal) { 0.0 } else { [Math]::PI / 2.0 }
                $row = $entityByHandle[$axisHandle]
                $measured = $dimensionMeasurements[$axisHandle]
                $observedStart = if ($measured) { Read-DxfPoint $measured.dxf_13 } else { $null }
                $observedEnd = if ($measured) { Read-DxfPoint $measured.dxf_14 } else { $null }
                $definition = if ($row) { Read-DxfPoint $row[9] } else { $null }
                $observedRotation = if ($row) { Read-DxfNumber $row[11] } else { $null }
                $observedLine = if ($definition) { $definition[$(if ($isHorizontal) { 1 } else { 0 })] } else { $null }
                if ($isAligned) {
                    $dx = $endPoint[0] - $startPoint[0]
                    $dy = $endPoint[1] - $startPoint[1]
                    $length = [Math]::Sqrt($dx * $dx + $dy * $dy)
                    $normalX = -$dy / $length
                    $normalY = $dx / $length
                    $lineCoordinate = $offset
                    $observedLine = if ($definition) {
                        ($definition[0] - $startPoint[0]) * $normalX +
                        ($definition[1] - $startPoint[1]) * $normalY
                    } else { $null }
                    # DIMALIGNED orientation is defined by DXF13/14; its DXF50
                    # can be zero and is not an angular acceptance oracle.
                    $rotation = $null
                }
                $axisDefinitionComparison += [ordered]@{
                    dimension = $axisHandle; expected_start = $startPoint; expected_end = $endPoint
                    autocad_start = $observedStart; autocad_end = $observedEnd
                    expected_line_coordinate = $lineCoordinate; autocad_line_coordinate = $observedLine
                    expected_rotation_rad = $rotation; autocad_rotation_rad = $observedRotation
                    orientation_basis = if ($isAligned) { 'dxf_13_14' } else { 'dxf_50' }
                    matched = $row -and $row[1] -eq 'DIMENSION' -and
                        (Same-Point $startPoint $observedStart) -and
                        (Same-Point $endPoint $observedEnd) -and
                        $null -ne $observedLine -and
                        [Math]::Abs($lineCoordinate - $observedLine) -le 1e-6 -and
                        ($isAligned -or ($null -ne $observedRotation -and
                            [Math]::Abs($rotation - $observedRotation) -le 1e-6))
                }
            }
            $axisStyle = $sourceReport.axis_dimension.dimension_style
            $observedStyle = $dimensionStyles[$axisHandle]
            foreach ($field in @('name', 'text_height_m', 'arrow_size_m', 'gap_m',
                                 'scale', 'measurement_factor')) {
                $want = $axisStyle.$field
                $got = if ($observedStyle) { $observedStyle.$field } else { $null }
                $matched = $null -ne $got -and $(if ($field -eq 'name') {
                    $want -ceq $got } else { [Math]::Abs([double]$want - [double]$got) -le 1e-6 })
                $axisStyleComparison += [ordered]@{ dimension = $axisHandle; property = $field
                    expected = $want; observed = $got; matched = $matched }
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
    $axisDefinitionMismatch = @($axisDefinitionComparison | Where-Object { -not $_.matched }).Count -gt 0
    $axisStyleMismatch = @($axisStyleComparison | Where-Object { -not $_.matched }).Count -gt 0
    $axisFixtureMismatch = $axisFixtureValid -eq $false
    $lengthMismatch = $lengthFixtureValid -eq $false -or
        @($lengthGeometryComparison | Where-Object { -not $_.matched }).Count -gt 0 -or
        ($lengthGeometryComparison.Count -gt 0 -and $declaredCount -ne 5)
    $plotMismatch = $plotSourceValid -eq $false -or
        @($plotProfileComparison | Where-Object { -not $_.matched }).Count -gt 0 -or
        @($plotGeometryComparison | Where-Object { -not $_.matched }).Count -gt 0 -or
        ($plotSourceValid -eq $true -and
         ($plotProfileComparison.Count -ne 16 -or $plotGeometryComparison.Count -ne 2 -or
          $declaredCount -ne 2))
    $plotContentMismatch = $plotContentSourceValid -eq $false -or
        @($plotContentComparison | Where-Object { -not $_.matched }).Count -gt 0 -or
        ($plotContentSourceValid -eq $true -and
         ($plotContentComparison.Count -ne $plotContentExpectedCount -or
          $declaredCount -ne 4 -or
          $types.LINE -ne 2 -or $types.TEXT -ne 1 -or $types.DIMENSION -ne 1))
    $plotCtbMismatch = $plotCtbSourceValid -eq $false -or
        @($plotCtbComparison | Where-Object { -not $_.matched }).Count -gt 0 -or
        ($plotCtbSourceValid -eq $true -and
         ($plotCtbComparison.Count -ne 19 -or $declaredCount -ne 2 -or
          $types.LINE -ne 2))
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
                                  'synthetic-two-door-wall-v8.planspec.json',
                                  'synthetic-window.planspec.json',
                                  'synthetic-wall-join.planspec.json',
                                  'synthetic-joined-door.planspec.json',
                                  'synthetic-joined-door-second.planspec.json',
                                  'synthetic-three-wall-chain.planspec.json',
                                  'synthetic-wall-face-dimension-readable-v7.planspec.json',
                                  'synthetic-wall-face-dimension-vertical-v7.planspec.json',
                                  'synthetic-wall-axis-span-v8.planspec.json',
                                  'synthetic-wall-axis-span-vertical-v8.planspec.json',
                                  'synthetic-wall-axis-endpoints-v9.planspec.json',
                                  'synthetic-wall-aligned-endpoints-v9.planspec.json')) {
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
            if ($fixture.schema_version -in @('planspec-3', 'planspec-7', 'planspec-8', 'planspec-9') -and
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
                 $fixture.openings[0].kind -in @('door', 'window')) -or
                ($fixture.schema_version -eq 'planspec-8' -and
                 $fixture.walls.Count -eq 1 -and $fixture.openings.Count -eq 2 -and
                 @($fixture.openings | Where-Object { $_.kind -eq 'door' }).Count -eq 2)) {
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
                if (($fixture.schema_version -eq 'planspec-4' -and
                     $fixture.openings.Count -eq 1 -and $fixture.openings[0].kind -eq 'door') -or
                    ($fixture.schema_version -eq 'planspec-8' -and
                     $fixture.openings.Count -eq 2 -and
                     @($fixture.openings | Where-Object { $_.kind -eq 'door' }).Count -eq 2)) {
                  foreach ($door in $fixture.openings) {
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
                        (Same-Angle $expectedStartAngle $arcStart) -and
                        (Same-Angle $expectedEndAngle $arcEnd)
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
            }
            if ($fixture.schema_version -eq 'planspec-5' -and
                $fixture.walls.Count -eq 2 -and $fixture.joins.Count -eq 1 -and
                $fixture.openings.Count -le 1) {
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
                $door = if ($fixture.openings.Count -eq 1) { $fixture.openings[0] } else { $null }
                if ($door) {
                    $doorOnSecond = $door.wall_id -eq $second.id
                    $targetLength = if ($doorOnSecond) { $lengthB } else { $lengthA }
                    $targetJoinEnd = if ($doorOnSecond) { $join.wall_b_end } else { $join.wall_a_end }
                    $gapStart = if ($targetJoinEnd -eq 'end') {
                        $targetLength - [double]$door.offset_m - [double]$door.width_m
                    } else { [double]$door.offset_m }
                    $gapEnd = $gapStart + [double]$door.width_m
                }
                $expectedSegments = @()
                for ($index = 0; $index -lt 8; $index++) {
                    $startLocal = $local[$index]
                    $endLocal = $local[($index + 1) % 8]
                    if ($door -and -not $doorOnSecond -and $index -eq 0) {
                        $expectedSegments += [ordered]@{ part = 'outline_0_before'; source = $first.id
                            start = $startLocal; end = @($gapStart, -$half) }
                        $expectedSegments += [ordered]@{ part = 'outline_0_after'; source = $first.id
                            start = @($gapEnd, -$half); end = $endLocal }
                    } elseif ($door -and -not $doorOnSecond -and $index -eq 2) {
                        $expectedSegments += [ordered]@{ part = 'outline_2_before'; source = $first.id
                            start = $startLocal; end = @($gapEnd, $half) }
                        $expectedSegments += [ordered]@{ part = 'outline_2_after'; source = $first.id
                            start = @($gapStart, $half); end = $endLocal }
                    } elseif ($door -and $doorOnSecond -and $index -eq 3) {
                        $expectedSegments += [ordered]@{ part = 'outline_3_before'; source = $second.id
                            start = $startLocal; end = @($half, $gapStart) }
                        $expectedSegments += [ordered]@{ part = 'outline_3_after'; source = $second.id
                            start = @($half, $gapEnd); end = $endLocal }
                    } elseif ($door -and $doorOnSecond -and $index -eq 5) {
                        $expectedSegments += [ordered]@{ part = 'outline_5_before'; source = $second.id
                            start = $startLocal; end = @(-$half, $gapEnd) }
                        $expectedSegments += [ordered]@{ part = 'outline_5_after'; source = $second.id
                            start = @(-$half, $gapStart); end = $endLocal }
                    } else {
                        $owner = if ($index -lt 3) { $first.id } elseif ($index -lt 6) {
                            $second.id } else { $join.id }
                        $expectedSegments += [ordered]@{ part = "outline_$index"; source = $owner
                            start = $startLocal; end = $endLocal }
                    }
                }
                if ($door) {
                    foreach ($jamb in @(@('jamb_start', $gapStart), @('jamb_end', $gapEnd))) {
                        if ($doorOnSecond) {
                            $expectedSegments += [ordered]@{ part = [string]$jamb[0]; source = $door.id
                                start = @(-$half, [double]$jamb[1]); end = @($half, [double]$jamb[1]) }
                        } else {
                            $expectedSegments += [ordered]@{ part = [string]$jamb[0]; source = $door.id
                                start = @([double]$jamb[1], -$half); end = @([double]$jamb[1], $half) }
                        }
                    }
                }
                foreach ($segment in $expectedSegments) {
                    $expectedStart = Join-Point $junction $u $v $segment.start[0] $segment.start[1]
                    $expectedEnd = Join-Point $junction $u $v $segment.end[0] $segment.end[1]
                    $partId = if ($segment.source -eq $door.id -and $door) {
                        '{0}__{1}' -f $door.id, $segment.part
                    } else { '{0}__{1}' -f $join.id, $segment.part }
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
                        planspec_id = $partId; source_id = $segment.source; kind = 'WALL_UNION_EDGE'
                        handle = $handle; expected_layer = $first.layer
                        expected_start = $expectedStart; expected_end = $expectedEnd
                        autocad_start = $observedStart; autocad_end = $observedEnd
                        matched_1e_6 = [bool]$matched
                    }
                }
                if ($door) {
                    $doorWall = if ($doorOnSecond) { $second } else { $first }
                    $wallStart = $nodes[$doorWall.start]
                    $wallEnd = $nodes[$doorWall.end]
                    $wallDx = $wallEnd[0] - $wallStart[0]
                    $wallDy = $wallEnd[1] - $wallStart[1]
                    $wallLength = [Math]::Sqrt($wallDx * $wallDx + $wallDy * $wallDy)
                    $uxDoor = $wallDx / $wallLength
                    $uyDoor = $wallDy / $wallLength
                    $width = [double]$door.width_m
                    $offset = [double]$door.offset_m
                    $side = if ($door.swing.side -eq 'left') { 1.0 } else { -1.0 }
                    $hingeAtStart = $door.swing.hinge -eq 'start'
                    $distance = if ($hingeAtStart) { $offset } else { $offset + $width }
                    $hinge = Wall-Point $wallStart $uxDoor $uyDoor (-$uyDoor * $half) ($uxDoor * $half) $distance $side
                    $direction = if ($hingeAtStart) { 1.0 } else { -1.0 }
                    $closed = @(($hinge[0] + $direction * $uxDoor * $width),
                                ($hinge[1] + $direction * $uyDoor * $width), 0.0)
                    $opened = @(($hinge[0] - $uyDoor * $side * $width),
                                ($hinge[1] + $uxDoor * $side * $width), 0.0)
                    $leafId = '{0}__leaf_open' -f $door.id
                    $leafHandle = [string]$richSourceReport.planspec.handles_by_id.($leafId)
                    $leafRow = if ($leafHandle) { $entityByHandle[$leafHandle] } else { $null }
                    $leafStart = if ($leafRow) { Read-DxfPoint $leafRow[9] } else { $null }
                    $leafEnd = if ($leafRow) { Read-DxfPoint $leafRow[16] } else { $null }
                    $leafMatched = $leafRow -and $leafRow[1] -eq 'LINE' -and $leafRow[3] -eq $doorWall.layer -and
                        (((Same-Point $hinge $leafStart) -and (Same-Point $opened $leafEnd)) -or
                         ((Same-Point $hinge $leafEnd) -and (Same-Point $opened $leafStart)))
                    $geometryComparison += [ordered]@{ planspec_id = $leafId; source_id = $door.id
                        kind = 'DOOR_LEAF'; handle = $leafHandle; expected_layer = $doorWall.layer
                        expected_start = $hinge; expected_end = $opened
                        autocad_start = $leafStart; autocad_end = $leafEnd; matched_1e_6 = [bool]$leafMatched }
                    $arcId = '{0}__swing_arc' -f $door.id
                    $arcHandle = [string]$richSourceReport.planspec.handles_by_id.($arcId)
                    $arcRow = if ($arcHandle) { $entityByHandle[$arcHandle] } else { $null }
                    $arcCenter = if ($arcRow) { Read-DxfPoint $arcRow[9] } else { $null }
                    $arcRadius = if ($arcRow) { Read-DxfNumber $arcRow[17] } else { $null }
                    $arcStart = if ($arcRow) { Read-DxfNumber $arcRow[11] } else { $null }
                    $arcEnd = if ($arcRow) { Read-DxfNumber $arcRow[18] } else { $null }
                    $turn = 2 * [Math]::PI
                    $expectedStartAngle = ([Math]::Atan2(($closed[1] - $hinge[1]),
                        ($closed[0] - $hinge[0])) + $turn) % $turn
                    $expectedEndAngle = ([Math]::Atan2(($opened[1] - $hinge[1]),
                        ($opened[0] - $hinge[0])) + $turn) % $turn
                    if ($direction * $side -lt 0) {
                        $angle = $expectedStartAngle
                        $expectedStartAngle = $expectedEndAngle
                        $expectedEndAngle = $angle
                    }
                    $arcMatched = $arcRow -and $arcRow[1] -eq 'ARC' -and $arcRow[3] -eq $doorWall.layer -and
                        (Same-Point $hinge $arcCenter) -and $null -ne $arcRadius -and
                        [Math]::Abs($arcRadius - $width) -le 1e-6 -and
                        $null -ne $arcStart -and $null -ne $arcEnd -and
                        (Same-Angle $expectedStartAngle $arcStart) -and
                        (Same-Angle $expectedEndAngle $arcEnd)
                    $geometryComparison += [ordered]@{ planspec_id = $arcId; source_id = $door.id
                        kind = 'DOOR_SWING_ARC'; handle = $arcHandle; expected_layer = $doorWall.layer
                        expected_center = $hinge; expected_radius = $width; angle_unit = 'radians'
                        expected_start_angle = $expectedStartAngle; expected_end_angle = $expectedEndAngle
                        autocad_center = $arcCenter; autocad_radius = $arcRadius
                        autocad_start_angle = $arcStart; autocad_end_angle = $arcEnd
                        matched_1e_6 = [bool]$arcMatched }
                }
            }
            if ($fixtureName -eq 'synthetic-three-wall-chain.planspec.json') {
                # Frozen independent coordinate oracle for the v5 synthetic
                # chain. A changed fixture is detected by these comparisons.
                $oracle = @(
                    @('wall-horizontal', 0, -0.1, 4, -0.1),
                    @('wall-horizontal', 4, -0.1, 4, 0),
                    @('wall-vertical', 4, 0, 4.1, 0),
                    @('wall-vertical', 4.1, 0, 4.1, 2.9),
                    @('wall-top', 4.1, 2.9, 7, 2.9),
                    @('wall-top', 7, 2.9, 7, 3.1),
                    @('wall-top', 7, 3.1, 4, 3.1),
                    @('wall-top', 4, 3.1, 4, 3),
                    @('wall-vertical', 4, 3, 3.9, 3),
                    @('wall-vertical', 3.9, 3, 3.9, 0.1),
                    @('wall-horizontal', 3.9, 0.1, 0, 0.1),
                    @('wall-horizontal', 0, 0.1, 0, -0.1)
                )
                for ($index = 0; $index -lt $oracle.Count; $index++) {
                    $partId = 'three-wall-union__outline_{0}' -f $index
                    $expected = $oracle[$index]
                    $expectedStart = @([double]$expected[1], [double]$expected[2], 0.0)
                    $expectedEnd = @([double]$expected[3], [double]$expected[4], 0.0)
                    $handle = [string]$richSourceReport.planspec.handles_by_id.($partId)
                    $row = if ($handle) { $entityByHandle[$handle] } else { $null }
                    $observedStart = if ($row) { Read-DxfPoint $row[9] } else { $null }
                    $observedEnd = if ($row) { Read-DxfPoint $row[16] } else { $null }
                    $matched = $row -and $row[1] -eq 'LINE' -and $row[3] -eq '0' -and
                        (((Same-Point $expectedStart $observedStart) -and
                          (Same-Point $expectedEnd $observedEnd)) -or
                         ((Same-Point $expectedStart $observedEnd) -and
                          (Same-Point $expectedEnd $observedStart)))
                    $geometryComparison += [ordered]@{
                        planspec_id = $partId; source_id = [string]$expected[0]
                        kind = 'THREE_WALL_UNION_EDGE'; handle = $handle; expected_layer = '0'
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
              'synthetic-wall-join.planspec.json', 'synthetic-joined-door.planspec.json',
              'synthetic-joined-door-second.planspec.json',
              'synthetic-three-wall-chain.planspec.json',
              'synthetic-two-door-wall-v8.planspec.json',
              'synthetic-wall-axis-span-v8.planspec.json',
              'synthetic-wall-axis-span-vertical-v8.planspec.json',
              'synthetic-wall-axis-endpoints-v9.planspec.json',
              'synthetic-wall-aligned-endpoints-v9.planspec.json')) {
        $wallModelCountMatch = $declaredCount -eq $geometryComparison.Count
    }
    if ($richSourceReport.axis_dimension.handle) {
        $wallModelCountMatch = $declaredCount -eq ($geometryComparison.Count + 1)
    }
    if ($richSourceReport.schema_version -eq 'mcp-wall-thickness-l2-1') {
        $wallModelCountMatch = $declaredCount -eq ($geometryComparison.Count + 1)
    }
    $report = [ordered]@{
        schema_version = 'mcp-autocad-audit-l4-17'
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
        axis_definition_comparison = $axisDefinitionComparison
        axis_style_comparison = $axisStyleComparison
        axis_fixture_valid = $axisFixtureValid
        length_fixture_valid = $lengthFixtureValid
        length_geometry_comparison = $lengthGeometryComparison
        model_layout_fields = $modelLayoutFields
        plot_source_valid = $plotSourceValid
        plot_profile_comparison = $plotProfileComparison
        plot_geometry_comparison = $plotGeometryComparison
        plot_content_source_valid = $plotContentSourceValid
        plot_content_comparison = $plotContentComparison
        plot_ctb_source_valid = $plotCtbSourceValid
        plot_ctb_comparison = $plotCtbComparison
        property_comparison = $propertyComparison
        geometry_source_valid = $geometrySourceValid
        source_report_match = $sourceReportMatch
        wall_model_count_match = $wallModelCountMatch
        geometry_comparison = $geometryComparison
        semantic_verdict = if ($sourceReportMatch -eq $false -or $dimensionMismatch -or
                              $faceReferenceMismatch -or $faceStyleMismatch -or $facePlacementMismatch -or
                              $faceFixtureMismatch -or
                              $axisDefinitionMismatch -or $axisStyleMismatch -or $axisFixtureMismatch -or
                              $propertyMismatch -or $geometryMismatch -or $lengthMismatch -or
                              $plotMismatch -or $plotContentMismatch -or $plotCtbMismatch -or
                              $wallModelCountMatch -eq $false) {
            'mismatch'
        } elseif ($expected.Count -gt 0 -or $faceReferenceComparison.Count -gt 0 -or
                  $facePlacementComparison.Count -gt 0 -or
                  $faceStyleComparison.Count -gt 0 -or
                  $axisDefinitionComparison.Count -gt 0 -or
                  $axisStyleComparison.Count -gt 0 -or
                  $propertyComparison.Count -gt 0 -or
                  $geometryComparison.Count -gt 0 -or $lengthGeometryComparison.Count -gt 0 -or
                  $plotProfileComparison.Count -gt 0 -or
                  $plotContentComparison.Count -gt 0 -or
                  $plotCtbComparison.Count -gt 0) {
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
                  $axisDefinitionMismatch -or $axisStyleMismatch -or $axisFixtureMismatch -or
                  $propertyMismatch -or $geometryMismatch -or $lengthMismatch -or
                  $plotMismatch -or $plotContentMismatch -or $plotCtbMismatch -or
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
