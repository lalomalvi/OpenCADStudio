# Native Windows entry point. The helper needs Python; the GUI/MCP binary does not.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$desktopArguments = @($args)
function Invoke-DesktopHelper([string]$Executable, [string[]]$DesktopPrefix = @()) {
    $helperPath = Join-Path $PSScriptRoot 'desktop.py'
    if ($desktopArguments.Count -gt 0 -and $desktopArguments[0] -eq 'mcp') {
        # PowerShell's native pipeline can close a stdio server's stdin early.
        # Copy raw bytes with .NET streams; no PowerShell text pipeline/banners.
        $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $startInfo.FileName = $Executable
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardInput = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $nativeArguments = @($DesktopPrefix) + @($helperPath) + $desktopArguments
        $quotedArguments = foreach ($argument in $nativeArguments) {
            $value = [regex]::Replace([string]$argument, '(\\*)"', '$1$1\"')
            $value = [regex]::Replace($value, '(\\+)$', '$1$1')
            '"' + $value + '"'
        }
        $startInfo.Arguments = $quotedArguments -join ' '
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $startInfo
        # .NET Framework builds StandardInput's StreamWriter from Console.InputEncoding.
        # UTF-8 with a BOM inserts a preamble into otherwise raw JSON-RPC pipes.
        # Select BOM-free UTF-8 only while constructing this child, then restore it.
        $originalInputEncoding = [Console]::InputEncoding
        try {
            [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
            if (-not $process.Start()) { [Console]::Error.WriteLine('MCP helper did not start.'); exit 2 }
            $childInput = $process.StandardInput.BaseStream
        } finally {
            [Console]::InputEncoding = $originalInputEncoding
        }
        $clientInput = [Console]::OpenStandardInput()
        $inputBuffer = [byte[]]::new(65536)
        $inputRead = $clientInput.ReadAsync($inputBuffer, 0, $inputBuffer.Length)
        $outputCopy = $process.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput())
        $errorCopy = $process.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError())
        while (-not $process.HasExited) {
            if ($inputRead.IsCompleted) {
                $byteCount = $inputRead.GetAwaiter().GetResult()
                if ($byteCount -eq 0) {
                    $process.StandardInput.Close()
                    $process.WaitForExit()
                    break
                }
                $childInput.Write($inputBuffer, 0, $byteCount)
                $childInput.Flush()
                $inputRead = $clientInput.ReadAsync($inputBuffer, 0, $inputBuffer.Length)
            }
            [System.Threading.Thread]::Sleep(10)
        }
        $null = $outputCopy.GetAwaiter().GetResult()
        $null = $errorCopy.GetAwaiter().GetResult()
        exit $process.ExitCode
    }
    & $Executable @DesktopPrefix $helperPath @desktopArguments
    exit $LASTEXITCODE
}
$candidates = @(
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    'C:\Python313\python.exe', 'C:\Python312\python.exe', 'C:\Python311\python.exe'
)
$python = $null
try {
    $python = Get-Command python -CommandType Application -ErrorAction Stop |
        Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
} catch { }
if ($python -and $python.Source -notlike '*WindowsApps*') {
    Invoke-DesktopHelper $python.Source
}
$launcher = $null
try { $launcher = Get-Command py -CommandType Application -ErrorAction Stop | Select-Object -First 1 } catch { }
if ($launcher) {
    Invoke-DesktopHelper $launcher.Source @('-3')
}
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        Invoke-DesktopHelper $candidate
    }
}
[Console]::Error.WriteLine('Python 3.11+ helper is missing or outside PATH. Check py -3, C:\Python3* and your per-user Programs\Python folder. Reopen terminal after installing Python. The downloaded GUI itself does not require Python; see docs/install/windows.md.')
exit 2
