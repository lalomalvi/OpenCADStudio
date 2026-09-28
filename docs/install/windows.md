# Windows: install, locate and open this fork

This guide is for **lalomalvi/OpenCADStudio**, Windows x64, MSVC. Windows ARM64,
32-bit and GNU distributions are not offered by this workflow. A Git clone is
source code. It is not an installed desktop application.

## End user: published ZIP, when available

The [fork releases](https://github.com/lalomalvi/OpenCADStudio/releases) had **no
releases on 2026-09-28**. Do not substitute an upstream installer: it is a
different source revision and does not establish this fork's MCP behavior.
Use the source route below today, or an explicitly approved CI package from the
new distribution workflow after its native checks pass.

The fork format is `OpenCADStudio-fork-<version>-<commit>-windows-x86_64-<hash>.zip`
(development packages also say `dirty`). It contains `distribution.json`, the
GPL license, `application/OpenCADStudio.exe` and any required app-local MSVC
runtime DLLs. ZIP was selected because it supports a per-user portable location,
requires no administrator, and does not replace file associations or register
thumbnail handlers. The inherited MSI is per-machine and is not this fork's
supported installation path.

To use a published package without Python: download its ZIP and `.zip.sha256`
from the **same fork release**. Compare the hash in PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Users\YOUR_USER\Downloads\EXACT_PACKAGE.zip'
```

Extract into a new per-user folder, for example
`%LOCALAPPDATA%\Programs\OpenCADStudio Fork\<package>`. Open the ZIP's extracted
top-level folder (named `OpenCADStudio-fork-...`). Keep the entire payload
and its runtime DLLs together. Double-click its `application\OpenCADStudio.exe` in
Explorer. Check that the editor window renders. Keep the exact absolute path for
later use; create a shortcut to this executable if desired. The application
does not need Git, Rust, Python, VS Build Tools or a source checkout at runtime.
This manual route requires checking the manifest, version and GUI yourself.

For automated hash, origin, version, resource, MCP and GUI verification, the
helper needs **Python 3.11+** and this checkout (or its `scripts` and
`docs/automation/mcp_smoke.py` files). Python is a helper prerequisite, not a
CAD runtime dependency. From the checkout:

```powershell
& '.\scripts\desktop.ps1' download
& '.\scripts\desktop.ps1' open
& '.\scripts\desktop.ps1' path
```

`download` reads only this fork's release API, selects the host architecture,
requires a checksum, and rejects binaries without the fork metadata and MCP
surface. If no compatible package exists it exits **2** with the source route.
For a known local/CI package:

```powershell
& '.\scripts\desktop.ps1' install --package 'C:\Downloads with spaces\EXACT_PACKAGE.zip'
& '.\scripts\desktop.ps1' open
```

The `.zip.sha256` must be next to the ZIP, or supply `--sha256` with a trusted
digest. Checksums establish transport integrity; they are not publisher signatures.
Default location: `%LOCALAPPDATA%\Programs\OpenCADStudio Fork\<package-hash>\application`.
`installation.json` in the parent records the absolute application, executable,
source commit, package and logs. Installations are immutable slots: a repeat
reuses the verified package, and a new package does not overwrite an old one.
`--install-dir 'C:\My user apps\OpenCADStudio Fork'` selects another location;
pass the same option to `open`, `path`, `verify` and `mcp`.

## Developer or agent: unprepared machine to open GUI

First check installation **and** PATH. The diagnosis is read-only:

```powershell
Get-Command git, python, py, rustup, rustc, cargo -ErrorAction SilentlyContinue
Test-Path -LiteralPath "$env:USERPROFILE\.cargo\bin\rustup.exe"
& '.\scripts\desktop.ps1' diagnose
```

If Python is missing, check `py -3`, `C:\Python3*` and
`%LOCALAPPDATA%\Programs\Python` before saying it is absent. The PowerShell
entry checks these conventional locations. Rust is also checked under
`CARGO_HOME\bin` or `%USERPROFILE%\.cargo\bin`; Build Tools is checked through
`vswhere`, not by assuming `link.exe` must be on PATH.

Explicitly install only missing prerequisites:

1. [Git for Windows](https://git-scm.com/download/win).
2. [Python 3.11+](https://www.python.org/downloads/windows/) for the helper.
3. [Rustup](https://rust-lang.org/tools/install/), MSVC toolchain.
4. [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/):
   **Desktop development with C++**, MSVC x64/x86 build tools
   (`Microsoft.VisualStudio.Component.VC.Tools.x86.x64`) and Windows 10/11 SDK
   with headers, UCRT, x64 import libraries and resource compiler. C/C++ is used
   by native dependencies; linker/SDK and MSVC redistributable files are also
   needed for packaging. No separate CMake/Homebrew/WiX requirement is imposed
   by the fork ZIP route. See [Microsoft's Rust setup](https://learn.microsoft.com/en-us/windows/dev-environment/rust/setup).

Reopen PowerShell after installers change PATH; the current terminal does not
inherit later environment changes. Scripts never install global tools silently.
Then run this complete source route (choose an empty download folder):

```powershell
git clone https://github.com/lalomalvi/OpenCADStudio.git 'C:\CAD Source\OpenCADStudio'
Set-Location -LiteralPath 'C:\CAD Source\OpenCADStudio'
rustup toolchain install 1.98.1-x86_64-pc-windows-msvc --profile minimal
rustup override set 1.98.1-x86_64-pc-windows-msvc
& '.\scripts\desktop.ps1' diagnose
& '.\scripts\desktop.ps1' build
```

Stop on a nonzero exit. `build` runs Cargo **--locked --release**, verifies MCP,
audits runtime imports, packages resources, and prints the ZIP's absolute path.
It does not yet claim GUI installation. Use that printed path:

```powershell
$package = 'C:\CAD Source\OpenCADStudio\dist\EXACT_PRINTED_PACKAGE.zip'
& '.\scripts\desktop.ps1' install --package $package
& '.\scripts\desktop.ps1' open
$exe = & '.\scripts\desktop.ps1' path
& $exe --version
```

`open` starts that installed binary from outside the checkout with a new empty
document and a private profile, verifies its PID, GUI session, visible native
window and rendered PNG. It leaves that verified GUI open. Normal Explorer
opening uses the user's usual profile; the helper deliberately preserves it.
`verify --gui` performs the same isolated check and closes only its owned GUI.
A process launch alone is never reported as successful opening.

Rust **1.98.1** is the tested/pinned distribution compiler. Cargo.toml previously
declared no MSRV; resolved Windows dependency metadata requires at least **1.92**
(iced/hayro), but 1.92 has not been tested as the whole application's MSRV. The dependency lock pins
Git and registry sources. `--locked` makes dependency selection repeatable, but
does not promise byte-identical builds or identical GPU drivers.

## MCP and logs

GUI: no `--mcp`. MCP: same verified executable, **stdio**:

```powershell
& $exe --mcp
# Alternatively: helper forwards stdio without banners
& '.\scripts\desktop.ps1' mcp
& '.\scripts\desktop.ps1' config
```

`--mcp` waits for a client on stdin; it is not the GUI command. Illustrative
client fragment (replace the user, hash and path with `path` output):

```json
{
  "command": "C:\\Users\\YOUR_USER\\AppData\\Local\\Programs\\OpenCADStudio Fork\\PACKAGE_HASH\\application\\OpenCADStudio.exe",
  "args": ["--mcp"]
}
```

Do not wrap `command` in additional quotes or concatenate `--mcp` into it.
Client-specific enclosing configuration varies. `verify` tests modern discovery
2026-07-28, legacy negotiation 2024-11-05/2025-03-26/2025-06-18/2025-11-25,
the four published tools, JSON-RPC-only stdout, clean EOF and
`ocs_sessions(launch_if_none:false)`, in an isolated profile.

After helper `open`, use `config` to generate the **actual** command/args and
`env.OCS_CONFIG_DIR` for its isolated GUI. The helper's `mcp` action forwards that
same environment. A raw binary launched without this environment uses the normal
user profile (appropriate for an Explorer-opened GUI), which can contain other
sessions; do not select an older/upstream session as if it were this installation.

Logs default to `<checkout>\target\desktop-logs\<timestamp-id>`:
`summary.json`, `build.log`, `dynamic-libraries.json`, `mcp.log`, `gui.log`,
`gui-verification.json`, `gui.png`. `--logs` selects a new absolute folder.
Timeouts: command 120s, version 20s, MCP request 15s, complete protocol suite
180s, GUI startup 60s, source build 3600s. Exit 0 means only the stage named in
the summary passed; 2 means blocked/error. Missing executable, failed hash,
failed protocol and failed GUI cannot return success.

Unsigned development packages can encounter SmartScreen/policy restrictions.
Verify source and hash, and follow your organization's approval process. The
scripts neither bypass security nor claim a publisher signature. A GPU driver
capable of a working wgpu backend and an interactive desktop are required;
Windows 11 x64 is the local acceptance host; Windows 10 compatibility has not
been established by this campaign. Consult the dated verification report for
the exact OS/build exercised.
