# macOS: install, locate and open this fork

This is **lalomalvi/OpenCADStudio**. A clone is source, not a `.app` installation.
The [fork releases](https://github.com/lalomalvi/OpenCADStudio/releases) had no
releases on **2026-09-28**. Upstream's DMG is not proof of this fork's MCP.

The new workflow builds **separate** Apple Silicon (`aarch64-apple-darwin`) and
Intel (`x86_64-apple-darwin`) packages on native runners. Producer af002fa1
(2026.40) passed both native macOS 15 jobs, including installation, MCP, GUI,
synthetic CAD and Finder. See the [current distribution audit](public-distribution-audit-20260928.md)
for source/package identities, hashes and publication status. There is no
universal binary. Minimum deployment target is configured as macOS 11.0;
successful CI on macOS 15 does not prove the minimum OS works. [Rust's Apple target requirements](https://doc.rust-lang.org/rustc/platform-support/apple-darwin.html)
describe the compiler baseline, not the product's full compatibility matrix.

## End user: fork bundle when published

Choose the architecture shown by `uname -m`. A shell running under Rosetta can
report x86_64 on Apple Silicon; use a native terminal/Python for native builds.
Download `OpenCADStudio-fork-<version>-<commit>-macos-arm64-<hash>.zip` or
`...-macos-x86_64-<hash>.zip`, plus `.zip.sha256`, from the same fork release.
Verify the digest:

```bash
cd "$HOME/Downloads"
shasum -a 256 -c EXACT_PACKAGE.zip.sha256
```

Expand with Archive Utility (or `ditto -x -k`) so bundle permissions/signature
metadata survive. Keep `distribution.json` and `LICENSE` with the payload.
Copy the **entire** `OpenCADStudio.app` to a new per-user folder under
`~/Applications/OpenCADStudio Fork/`. Do not merge into an existing bundle.
Double-click it in Finder. Confirm the actual editor window renders; a launcher
process is insufficient. The signed packaging script also produces a
platform-specific DMG, with an Applications shortcut; that output is optional,
and the managed installer consumes the verified ZIP.

Signing status matters: local/default CI bundles are **ad-hoc signed**, without
Developer ID or notarization. The packaging script verifies the code signature,
including the QuickLook extension, but that is not Gatekeeper acceptance.
No identity or notarization credentials have been established for this fork.
To publish a normally trusted download, an operator must provide
`DEVELOPER_ID="Developer ID Application: ..."` and a `NOTARY_PROFILE` already
stored in Keychain, run the signed packaging script, verify Apple's Accepted
result and stapling, then approve publication. A restricted machine may require
an approved signed release. Do not disable Gatekeeper or bulk-remove quarantine.
Use Apple's supported per-app review only after verifying the source and policy.

The app needs system graphics/frameworks and fonts; it does not need Rust,
Python, Git, Homebrew, librsvg or the build checkout at runtime. Missing custom
drawing fonts are a separate document-specific issue.

## Automated installation

The helper needs Python 3.11+ (standard library only), plus the checkout.
Python is not a CAD runtime requirement. It checks common Python locations;
do not assume Homebrew exists. From the source directory:

```bash
bash scripts/desktop-macos.sh download
bash scripts/desktop-macos.sh open
bash scripts/desktop-macos.sh path
```

Today `download` reports no compatible fork package and exits 2. When given a
reviewed local/CI ZIP, install it with:

```bash
bash scripts/desktop-macos.sh install --package "$HOME/Downloads/EXACT_PACKAGE.zip"
bash scripts/desktop-macos.sh open
```

The matching checksum sidecar is required, or provide `--sha256` from a trusted
publisher. The installer verifies origin, binary target/version, every payload
hash and MCP before recording a prepared installation. Default location:
`~/Applications/OpenCADStudio Fork/<package-hash>/OpenCADStudio.app`.
`installation.json` records absolute paths. Repeat installation reuses a verified
slot; newer packages get another slot. `--install-dir '/absolute/path with spaces'`
must be reused for subsequent `open`, `path`, `mcp` and `verify` commands.

`open` renders a new empty document under a private profile, validates the
installed GUI's descriptor/PID and a window PNG, then leaves it open.
`verify --gui` closes only its own test GUI. `verify --finder` separately opens
the exact installed `.app` through LaunchServices using a private profile,
correlates the relay and its child GUI, requires a rendered capture, then closes
them. Both native checks passed on both macOS CI architectures for producer
af002fa1 (2026.40); the operator still needs to check their own Mac and downloaded package.

## Developer or agent: unprepared machine to GUI

Check what exists before installing anything:

```bash
command -v git python3 rustup rustc cargo
test -x "$HOME/.cargo/bin/rustup" && "$HOME/.cargo/bin/rustup" show
xcode-select -p
xcrun --sdk macosx --show-sdk-path
uname -m
```

If absent, explicitly install Xcode Command Line Tools with
`xcode-select --install`, [Python 3.11+](https://www.python.org/downloads/macos/),
and [Rustup](https://rust-lang.org/tools/install/). CLT supplies Git, Clang,
linker, macOS SDK, Swift, `iconutil`, `codesign` and `hdiutil`. Full Xcode is not
assumed. Bundle icon generation additionally requires `rsvg-convert` (librsvg).
Use an existing installation via PATH, your approved package manager, or an
explicit librsvg installation. **Homebrew is optional**; if already installed,
`brew install librsvg` is a concrete choice. No package manager is installed by
the helper. Reopen the terminal after PATH changes.

Then, in a new folder:

```bash
git clone https://github.com/lalomalvi/OpenCADStudio.git "$HOME/CAD Source/OpenCADStudio"
cd "$HOME/CAD Source/OpenCADStudio"
case "$(uname -m)" in
  arm64) RUST_HOST=aarch64-apple-darwin ;;
  x86_64) RUST_HOST=x86_64-apple-darwin ;;
  *) echo 'Unsupported architecture' >&2; exit 2 ;;
esac
rustup toolchain install "1.98.1-$RUST_HOST" --profile minimal
rustup override set "1.98.1-$RUST_HOST"
bash scripts/desktop-macos.sh diagnose
MACOSX_DEPLOYMENT_TARGET=11.0 bash scripts/desktop-macos.sh build
```

Stop on a nonzero exit. `build` uses `Cargo.lock` and `--locked --release`,
reuses `packaging/build_macos_signed.sh`, builds the GUI, Finder launcher and
QuickLook thumbnailer, generates icons, signs inside-out, and produces a ZIP,
manifest and checksum. It audits every Mach-O with `otool -L` and rejects any
non-system unbundled library. The default signature is explicitly ad-hoc.
Use the ZIP path printed by the build:

```bash
bash scripts/desktop-macos.sh install --package '/absolute/printed/EXACT_PACKAGE.zip'
bash scripts/desktop-macos.sh open
EXE="$(bash scripts/desktop-macos.sh path)"
"$EXE" --version
```

No lower Rust compiler is claimed tested; the previously undeclared MSRV is
recorded in the audit. Windows resolved dependency metadata has a 1.92 lower
bound (iced/hayro); that does not validate macOS or the entire application's
MSRV at 1.92. The distribution compiler is pinned to 1.98.1.

## Finder and MCP are different entry points

`Info.plist` sets `CFBundleExecutable=OpenCADStudio`, a Finder file-event relay.
The real GUI/MCP binary is its sibling:
`OpenCADStudio.app/Contents/MacOS/OpenCADStudio-App`. The bundle identifier is
`io.github.lalomalvi.OpenCADStudioFork`, avoiding upstream's LaunchServices identity.

Finder: open the `.app`. MCP: use **OpenCADStudio-App --mcp**, never the relay:

```bash
"$EXE" --mcp
# Or forward client stdio through the helper:
bash scripts/desktop-macos.sh mcp
bash scripts/desktop-macos.sh config
```

Illustrative client fragment (replace with `path` output):

```json
{
  "command": "/Users/YOUR_USER/Applications/OpenCADStudio Fork/PACKAGE_HASH/OpenCADStudio.app/Contents/MacOS/OpenCADStudio-App",
  "args": ["--mcp"]
}
```

The enclosing config is client-specific. GUI launch has no `--mcp`.
After helper `open`, `config` emits the real command/args and `env.OCS_CONFIG_DIR`
for that exact isolated GUI; helper `mcp` forwards the same environment. A raw
binary without the override discovers the normal user profile, appropriate for
a Finder-opened app, and may include older sessions.
`verify` runs legacy/modern protocol negotiation, enumerates the four tools,
rejects stdout contamination, requires clean stdin-EOF shutdown and discovers
sessions with `launch_if_none:false`, without private drawings.

Logs: `<checkout>/target/desktop-logs/<timestamp-id>/summary.json`, `build.log`,
`bundle.log`, `dynamic-libraries.json`, `mcp.log`, `gui.log`, `gui.png`,
`gui-verification.json`; override with `--logs` and a new absolute folder.
Commands have bounded waits: version 20s, protocol 180s, GUI 60s, each build
3600s, notarization 30m. Exit 0 applies only to the reported stage; 2 means
blocked. Missing executable, bad hash/signature, unbundled dylib, failed
protocol or failed GUI is not a successful installation.
