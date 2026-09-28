<p align="center">
  <a href="README.md">English</a> ·
  <a href="docs/readme/README.bg.md">Български</a> ·
  <a href="docs/readme/README.pt-BR.md">Português (Brasil)</a> ·
  <a href="docs/readme/README.cs.md">Čeština</a> ·
  <a href="docs/readme/README.nl.md">Nederlands</a> ·
  <a href="docs/readme/README.fr.md">Français</a> ·
  <a href="docs/readme/README.fi.md">Suomi</a> ·
  <a href="docs/readme/README.de.md">Deutsch</a> ·
  <a href="docs/readme/README.el.md">Ελληνικά</a> ·
  <a href="docs/readme/README.hu.md">Magyar</a> ·
  <a href="docs/readme/README.it.md">Italiano</a> ·
  <a href="docs/readme/README.ja.md">日本語</a> ·
  <a href="docs/readme/README.ko.md">한국어</a> ·
  <a href="docs/readme/README.pl.md">Polski</a> ·
  <a href="docs/readme/README.ru.md">Русский</a> ·
  <a href="docs/readme/README.zh-CN.md">简体中文</a> ·
  <a href="docs/readme/README.es.md">Español</a> ·
  <a href="docs/readme/README.zh-TW.md">繁體中文</a> ·
  <a href="docs/readme/README.tr.md">Türkçe</a> ·
  <a href="docs/readme/README.hi.md">हिन्दी</a> ·
  <a href="docs/readme/README.ar.md">العربية</a>
</p>

<p align="center">
  <img src="assets/logo.svg" width="112" alt="Open CAD Studio logo">
</p>

<h1 align="center">Open CAD Studio</h1>

<p align="center">
  Open-source 2D drafting and 3D modeling for desktop and web, built with Rust.
</p>

<p align="center">
  <a href="https://github.com/lalomalvi/OpenCADStudio/releases"><strong>Fork releases and verified packages</strong></a>
  <a href="https://github.com/HakanSeven12/OpenCADStudio/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/HakanSeven12/OpenCADStudio"></a>
  <a href="LICENSE"><img alt="GPL-3.0 license" src="https://img.shields.io/github/license/HakanSeven12/OpenCADStudio"></a>
</p>

<p align="center">
  <a href="https://www.opencadstudio.com"><strong>Launch the web app</strong></a>
  ·
  <a href="docs/install/windows.md"><strong>Install on Windows</strong></a>
  ·
  <a href="docs/install/macos.md"><strong>Install on macOS</strong></a>
  ·
  <a href="https://github.com/HakanSeven12/OpenCADStudio/discussions"><strong>Join the discussion</strong></a>
</p>

<p align="center">
  <img src="site/workspace.png" alt="Open CAD Studio workspace" width="100%">
</p>

## Install and open this fork

This repository is **lalomalvi/OpenCADStudio**, a desktop CAD fork with a native
`--mcp` entry point. Cloning downloads source code; it does **not** install or
open the application. Upstream downloads are separate products/revisions.

| Platform | Complete installation and opening guide | Automated entry point |
| --- | --- | --- |
| Windows x64/MSVC | [Windows: package or source → verified GUI](docs/install/windows.md) | `& '.\scripts\desktop.ps1' diagnose` |
| macOS Apple Silicon | [macOS: bundle or source → verified GUI](docs/install/macos.md) | `bash scripts/desktop-macos.sh diagnose` |
| macOS Intel | [Separate native Intel package and Finder verification](docs/install/macos.md) | `bash scripts/desktop-macos.sh diagnose` |

**Availability audited 2026-09-28:** the [fork release API](https://github.com/lalomalvi/OpenCADStudio/releases)
returned no releases. Until a verified fork distribution is published, follow
the source route in your platform guide. The new native CI produces ZIPs,
version/source manifests and SHA-256 checksums, and tests installed payloads
outside the checkout. The clean 2026.40 producer af002fa1 passed all three native
jobs, including GUI/MCP/CAD and Finder on both Mac architectures. Its packages
remain reviewed CI artifacts until release publication is authorized. See the
[current distribution audit](docs/install/public-distribution-audit-20260928.md).

The helpers need Python 3.11+; the packaged CAD application does not. With the
listed native build prerequisites ready:

```powershell
# Windows (PowerShell), from this checkout
& '.\scripts\desktop.ps1' build
& '.\scripts\desktop.ps1' install --package 'ABSOLUTE_PRINTED_PACKAGE.zip'
& '.\scripts\desktop.ps1' open
& '.\scripts\desktop.ps1' path
```

```bash
# macOS, from this checkout
bash scripts/desktop-macos.sh build
bash scripts/desktop-macos.sh install --package '/absolute/printed/package.zip'
bash scripts/desktop-macos.sh open
bash scripts/desktop-macos.sh path
```

`open` verifies an isolated new GUI and leaves it open. `path` prints its absolute
MCP executable. `mcp` starts **stdio --mcp**, while `verify --gui` checks an owned
GUI and closes it. Each summary reports the actual stage; package preparation
alone never claims installation/opening. See the [agent contract](docs/install/agents.md)
and [dated audit/verification](docs/install/audit-20260928.md). The original installation audit belongs to the older 2026.38 development binary; the current distribution audit records clean 2026.40 Windows/Mac acceptance, hashes and release preparation. See the [current distribution audit](docs/install/public-distribution-audit-20260928.md).

## Overview

Open CAD Studio is a cross-platform application for technical drawing, layout work, and solid modeling. It reads and writes DWG and DXF drawings natively, with a shared editing core across the desktop and browser versions.

The project is under active development. Keep backups of important production drawings and report reproducible problems through [GitHub Issues](https://github.com/HakanSeven12/OpenCADStudio/issues).

## Highlights

- **Native drawing workflow** — open, edit, recover, and save DWG and DXF files without a conversion service.
- **Precise 2D drafting** — lines, polylines, curves, splines, hatches, object snaps, tracking, layers, blocks, and external references.
- **Documentation tools** — text, dimensions, leaders, tolerances, tables, model space, paper space, viewports, and plot styles.
- **Kernel-backed 3D modeling** — solid primitives, extrusion, revolution, sweep, loft, Boolean operations, and ACIS entity tessellation.
- **GPU rendering** — accelerated 2D and 3D viewports through `wgpu`, with orthographic and perspective cameras.
- **Extensible workflows** — native plugins, command scripts, headless conversion, and a line-based JSON automation API.

<p align="center">
  <img src="site/modeling.png" alt="3D model in Open CAD Studio" width="100%">
</p>

## File workflows

| Format or workflow | Support |
| --- | --- |
| DWG | Read and write; versioned save targets from R14 through 2018 |
| DXF | Read and write; versioned save targets from R14 through 2018 |
| BAK / SV$ | Open drawing backups and autosave files |
| OBJ | Import polygon meshes |
| LandXML | Import `CgPoint` survey points |
| STL | Export 3D mesh data |
| STEP AP203 | Export 3D mesh data |
| PDF | Plot layouts and selected geometry on desktop |
| CSV | Extract entity property data |
| CTB / STB | Load and edit plot style tables |

## Desktop or web

Use the [web app](https://www.opencadstudio.com) for immediate access with no installation. Drawings are selected through the browser and saved as local downloads.

Use the desktop application for system printing, PDF output, external plugins,
command scripts and headless automation. File associations and file-manager
thumbnails depend on packaging; the fork Windows ZIP does not register them.

## Other distributions

Upstream maintains its own Windows/Linux/macOS release mechanism. These are not
published packages of this fork and do not establish its MCP behavior. Linux
source/build instructions below remain available; the new fork installation
acceptance campaign covers Windows x64 and separate macOS architectures only.

## Languages

Open CAD Studio can follow the system language or use any of these 21 interface languages:

> Arabic · Brazilian Portuguese · Bulgarian · Czech · Dutch · English · Finnish · French · German · Greek · Hindi · Hungarian · Italian · Japanese · Korean · Polish · Russian · Simplified Chinese · Spanish · Traditional Chinese · Turkish

Change the language from the application settings. The browser version also uses the browser's preferred locale when **System** is selected.

## Build from source

### Desktop

Requirements:

- Git
- Rust 1.98.1 for the fork distribution route (lower MSRV not validated)
- Platform graphics and font development libraries

On Ubuntu or Debian, install the native dependencies with:

```bash
sudo apt update
sudo apt install libgl1-mesa-dev libx11-dev libxcursor-dev libxi-dev \
  libxrandr-dev libxkbcommon-dev libwayland-dev libfontconfig1-dev \
  libfreetype6-dev
```

Then build and run:

```bash
git clone https://github.com/lalomalvi/OpenCADStudio.git
cd OpenCADStudio
cargo build --locked --release --bin OpenCADStudio
```

The resulting binary is written to `target/release/OpenCADStudio` (`OpenCADStudio.exe` on Windows).

### Web

Install the WebAssembly target and build tools once:

```bash
rustup target add wasm32-unknown-unknown
cargo install trunk wasm-bindgen-cli
```

Start the development server:

```bash
trunk serve
```

## Automation

The desktop binary supports one-shot conversion, a persistent headless server, and a client-neutral MCP endpoint for AI applications:

```bash
OpenCADStudio --export input.dwg output.dxf
OpenCADStudio --export input-r12.dxf output.dwg --target-version R14
OpenCADStudio --serve
OpenCADStudio --serve --port 4242
OpenCADStudio --mcp
```

The automation server exchanges one JSON object per line over standard input/output or a local TCP socket. The self-contained MCP endpoint exposes the live desktop editor through the same tools to every compatible client. Its `audit` and `save_verified` operations check an explicit DWG/DXF target version, lossy records, raw DXF handle references, reopen the output, compare its semantic manifest, and return a SHA-256 hash. To connect a client, configure it to launch `OpenCADStudio --mcp`. See the [MCP control guide](docs/automation/README.md).

## Plugins

Desktop plugins run in separate processes and communicate with the host through the versioned plugin API. The browser build does not load native plugins.

- [Plugin architecture](docs/plugin-architecture.md)
- [Plugin template](docs/plugin-template/README.md)
- [Plugin registry](plugins/README.md)

## Project documentation

- [Automation API](docs/automation/README.md)
- [Plugin architecture](docs/plugin-architecture.md)
- [Tessellation pipeline](docs/tessellation.md)
- [Security policy](SECURITY.md)

## Contributing

Bug reports, focused pull requests, translations, documentation improvements, and plugin contributions are welcome.

- Search existing [issues](https://github.com/HakanSeven12/OpenCADStudio/issues) before opening a new report.
- Use [Discussions](https://github.com/HakanSeven12/OpenCADStudio/discussions) for questions and ideas.
- Report vulnerabilities privately by following the [security policy](SECURITY.md).

Application translations live in `locales/*/opencadstudio.ftl`; source labels map through
`src/locale_catalog.rs`. After editing translations, run `python3 scripts/export-locales.py`
to refresh web and desktop packaging labels. Validate with `python3 scripts/test_site.py`
and `cargo test --lib i18n::tests`.

## Project growth

### Stars

<a href="https://github.com/HakanSeven12/OpenCADStudio/stargazers">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://www.opencadstudio.com/star-history-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://www.opencadstudio.com/star-history-light.svg">
    <img alt="Open CAD Studio star history" src="https://www.opencadstudio.com/star-history-light.svg">
  </picture>
</a>

### Release downloads

<a href="https://github.com/HakanSeven12/OpenCADStudio/releases">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://www.opencadstudio.com/download-history-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://www.opencadstudio.com/download-history-light.svg">
    <img alt="Open CAD Studio release download history" src="https://www.opencadstudio.com/download-history-light.svg">
  </picture>
</a>

## Support the project

If Open CAD Studio helps your work, support continued development through [GitHub Sponsors](https://github.com/sponsors/HakanSeven12) or [Patreon](https://www.patreon.com/HakanSeven12).

## License

Open CAD Studio is distributed under the [GNU General Public License v3.0](LICENSE).
