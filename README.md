<p align="center"><a href="README.md">English</a> · <a href="docs/readme/README.es.md">Español</a></p>

<p align="center"><img src="assets/logo.svg" width="112" alt="OpenCADStudio open-source CAD logo"></p>

# OpenCADStudio — CAD and MCP for an open BIM ecosystem

**An open-source CAD fork maintained by Luis Martínez ([lalomalvi](https://github.com/lalomalvi)) to develop the drawing and automation layer of a BIM ecosystem for architecture, engineering and construction (AEC).** Built on [OpenCADStudio by Hakan Seven](https://github.com/HakanSeven12/OpenCADStudio), it combines Rust-based 2D drafting and 3D modeling, DWG/DXF workflows and a native **Model Context Protocol (MCP)** interface for compatible AI clients.

Luis develops this community fork as part of his work on an open BIM ecosystem and his collaboration with the [OpenAEC Foundation initiative](https://open-aec.com/en/) in the Netherlands. The focus is practical: installable tools, inspectable operations, traceable drawing outputs and engineering workflows that people can review.

[Fork website](https://lalomalvi.github.io/OpenCADStudio/) · [Open the browser CAD](https://lalomalvi.github.io/OpenCADStudio/app/) · [Download 2026.40.1](https://github.com/lalomalvi/OpenCADStudio/releases/tag/v2026.40.1) · [Windows installation](docs/install/windows.md) · [macOS installation](docs/install/macos.md) · [MCP API](docs/automation/API-SPEC.md) · [Español](docs/readme/README.es.md)

## Download, install and open

**Release 2026.40.1 is published for Windows x64, macOS Apple Silicon and macOS Intel.** Each architecture has its own ZIP, `.zip.sha256` checksum and `.zip.json` provenance manifest. Download all three matching files from the [fork release](https://github.com/lalomalvi/OpenCADStudio/releases/tag/v2026.40.1). ZIP packages support per-user installation without replacing an existing installation.

| Platform | Release package | Complete guide |
|---|---|---|
| Windows x64 / MSVC | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-windows-x86_64-89d9222bd46a.zip` | [Windows: verify, install, open and locate the EXE](docs/install/windows.md) |
| macOS Apple Silicon | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-macos-arm64-0c5abd0690cb.zip` | [macOS: verify, install the .app and open in Finder](docs/install/macos.md) |
| macOS Intel | `OpenCADStudio-fork-2026.40.1-196b1b7c554a-macos-x86_64-1e6cedd0bddc.zip` | [macOS Intel installation](docs/install/macos.md) |

For a manual installation, verify the ZIP checksum, extract the entire payload into a new per-user folder and open `application/OpenCADStudio.exe` on Windows or `OpenCADStudio.app` on macOS. Keep its resources together. The packaged CAD needs no Rust, Git or Python at runtime; the optional installation helper needs **Python 3.11+**.

For automated download, installation and verified opening, run from this fork's checkout:

```powershell
# Windows — PowerShell
& '.\scripts\desktop.ps1' download --tag v2026.40.1
& '.\scripts\desktop.ps1' open
& '.\scripts\desktop.ps1' path
```

```bash
# macOS — native terminal on Apple Silicon or Intel
bash scripts/desktop-macos.sh download --tag v2026.40.1
bash scripts/desktop-macos.sh open
bash scripts/desktop-macos.sh path
```

`download` verifies and installs the host package. `open` checks an isolated GUI and leaves it open. `path` prints the absolute installed executable. `mcp` starts stdio on that same binary; it is a separate operation from opening the GUI. A Git clone downloads source; installation and opening require the steps above.

**Signing:** Windows 2026.40.1 is NotSigned; both Mac bundles are ad-hoc signed without accredited Developer ID/notarization. Checksums prove integrity, not publisher identity or Gatekeeper/SmartScreen acceptance. Native macOS 15 CI passed; the configured macOS 11 deployment target and the operator's own Mac remain unverified. The guides explain these boundaries without disabling system protections.

## Why this fork exists

BIM work connects drawings, geometry, engineering information and people. This fork develops the CAD and automation part of that workflow, with clear interfaces between the editor, an AI client, its executor and the person reviewing the result.

The work concentrates on:

- **Usable desktop delivery:** verified packages, immutable installation slots, explicit executable paths and working GUI/MCP outside the build checkout.
- **Client-neutral automation:** one native MCP interface for session discovery, drawing inspection, controlled operations and captures.
- **Traceable CAD output:** explicit DWG/DXF target versions, audit results, reopen checks, hashes and retained evidence.
- **Open engineering workflows:** connecting CAD work to a broader BIM ecosystem through documented contracts and separately validated integrations.
- **Upstream collaboration:** integrating reviewed snapshots and contributing focused improvements while preserving the original project's authorship and GPL license.

### BIM scope: current capabilities and direction

| Area | Current position |
|---|---|
| CAD foundation | Native DWG/DXF drawing workflows, 2D drafting and 3D modeling inherited from OpenCADStudio |
| AI and MCP | Native stdio endpoint and documented session/read/execute/capture tools |
| Desktop delivery | Published, verified Windows x64 and separate Mac ARM64/Intel packages |
| Image-to-CAD robustness | An ongoing, scoped campaign with contracts and retained evidence; see the [masterplan checkpoint](docs/automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md) |
| BIM interoperability | Ecosystem direction; IFC/IFCX/BCF connectors and exchange guarantees require their own implementation and acceptance |

The 2026.40.1 release establishes the CAD/MCP distribution described here. Full BIM authoring, IFC certification, engineering compliance and global CAD fidelity are separate acceptance scopes.

## OpenAEC context and attribution

[OpenAEC](https://open-aec.com/en/) develops, supports and promotes open-source software across the AEC chain. Its website presents Hakan Seven's Open CAD Studio as a community project aligned with its ecosystem. The initiative is based in Dordrecht, the Netherlands.

| Role | Reference |
|---|---|
| Original CAD project and author | [Hakan Seven / OpenCADStudio](https://github.com/HakanSeven12/OpenCADStudio) |
| This community fork and maintainer | [Luis Martínez / lalomalvi](https://github.com/lalomalvi), [fork repository](https://github.com/lalomalvi/OpenCADStudio) |
| Luis's collaboration context | [OpenAEC Foundation initiative](https://open-aec.com/en/) |
| Fork packages and verification | [Releases](https://github.com/lalomalvi/OpenCADStudio/releases), [distribution audit](docs/install/public-distribution-audit-20260928.md) |

This README records the fork's purpose and work. Upstream code, contributors and project identity retain their attribution. The [upstream browser demo](https://www.opencadstudio.com) is separately maintained; use this fork's releases for its desktop/MCP distribution.

## Native MCP for CAD automation

The installed editor exposes four tools through **Model Context Protocol**:

| Tool | Purpose |
|---|---|
| `ocs_sessions` | Discover editor sessions, readiness and identity |
| `ocs_read` | Inspect capabilities, document state, records, geometry and operation results |
| `ocs_execute` | Submit editor operations, record updates and sequential batches |
| `ocs_capture` | Capture a bounded viewport or window image for review |

Run the installed binary with `--mcp`. For clients with separate fields, use the actual absolute executable as `command` and `["--mcp"]` as `args`. The helper's `config` command generates the installed configuration; it can include the isolated profile used by a verified open GUI.

```powershell
& '.\scripts\desktop.ps1' config
& '.\scripts\desktop.ps1' verify --gui
```

```bash
bash scripts/desktop-macos.sh config
bash scripts/desktop-macos.sh verify --gui
```

`verify --gui` closes only its own verification session. Use private configurations and synthetic fixtures for automation acceptance. Preserve user drawings and sessions. Protocol success, visual acceptance, persistence and independent CAD interoperability each have their own evidence.

Start with the [MCP operator guide](docs/automation/README.md), [API specification](docs/automation/API-SPEC.md), [client guide](docs/automation/mcp_client.md) and [agent installation contract](docs/install/agents.md).

## CAD features inherited from OpenCADStudio

- Native DWG/DXF reading and writing with explicit target versions.
- Lines, polylines, curves, hatches, object snaps, layers, blocks and external references.
- Text, dimensions, tables, model/paper space, viewports and plot styles.
- Solid primitives, extrusion, revolution, sweep, loft, Boolean operations and ACIS tessellation.
- GPU rendering through `wgpu`, desktop printing/PDF workflows and process-isolated plugins.
- A shared Rust core for desktop and browser builds, with 21 interface languages.

![OpenCADStudio CAD workspace inherited from the upstream project](site/workspace.png)

Plugin architecture and resources: [architecture](docs/plugin-architecture.md), [template](docs/plugin-template/README.md), [registry](plugins/README.md). Mac release bundles include the RustPython plugin; the Windows ZIP does not include that optional plugin. Desktop plugins and browser capabilities have different scopes.

## Verification and known limits

Source for the published packages: [`196b1b7c554a17299fd546850614db4bfc77de7a`](https://github.com/lalomalvi/OpenCADStudio/commit/196b1b7c554a17299fd546850614db4bfc77de7a), Cargo **2026.40.1**, Rust **1.98.1**, clean release builds with **Cargo.lock / --locked**.

- [Native distribution CI](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36519975664): all three platforms passed package/install/resource/corruption/MCP/GUI/synthetic CAD checks; both Mac targets passed Finder.
- [Workspace and host CI](https://github.com/lalomalvi/OpenCADStudio/actions/runs/36519903206): Rust workspace, Python automation and real hosts on Windows/Linux passed.
- Local Windows acceptance verified the same published package outside the checkout with an isolated GUI and synthetic drawings.

The published v2026.40.1 corrects the PLANT description and includes the browser clock fix plus the nine upstream commits frozen at 60f35e2b. Its Windows-generated DWG 2000/2013/2018 and DXF 2000 pass AutoCAD AUDIT with zero errors, five entities, clean exit and unchanged hashes. The public web opens an empty Drawing1 without new console errors. The historical v2026.40 and its nine original assets remain unchanged. These bounded checks do not establish global CAD parity or complete browser editing/export acceptance. See the [dated distribution audit](docs/install/public-distribution-audit-20260928.md).

## Build and contribute

Use the platform guide for native prerequisites, diagnosis and the complete build → package → install → open route. Distribution builds pin Rust **1.98.1** and use **--locked**. Lower whole-application MSRV is not validated. The helpers never install global dependencies silently.

```bash
git clone https://github.com/lalomalvi/OpenCADStudio.git
cd OpenCADStudio
```

Then follow [Windows](docs/install/windows.md) or [macOS](docs/install/macos.md). Linux source development remains available; this fork's published release matrix covers Windows and the two Mac architectures.

For browser development, the inherited source route uses the `wasm32-unknown-unknown` target, Trunk and wasm-bindgen-cli; see [build configuration](Trunk.toml) and [web CI](.github/workflows/web-check.yml). Browser compilation is distinct from native package acceptance.

Focused [pull requests to this fork](https://github.com/lalomalvi/OpenCADStudio/pulls) are welcome. Include the problem, scope, source revision and verification evidence. For upstream-wide issues and contributions, use the [original project](https://github.com/HakanSeven12/OpenCADStudio). Follow the [security policy](SECURITY.md) for vulnerability reports.

## Documentation and project record

- [Spanish project overview](docs/readme/README.es.md)
- [Windows installation](docs/install/windows.md) and [macOS installation](docs/install/macos.md)
- [Native MCP API](docs/automation/API-SPEC.md) and [automation guide](docs/automation/README.md)
- [Image-to-CAD robustness masterplan](docs/automation/masterplan/00-INDICE.md) and [current checkpoint](docs/automation/masterplan/05-CHECKPOINT-Y-CONTINUACION.md)
- [Upstream synchronization procedure](docs/automation/FORK-SYNC.md)
- [Public distribution audit and evidence](docs/install/public-distribution-audit-20260928.md)

English and Spanish describe this fork's current purpose and delivery. Other [language READMEs](docs/readme/) retain upstream translations; the linked installation guides and verification record govern fork-specific delivery.

## License and upstream credit

OpenCADStudio and this fork are distributed under the [GNU General Public License v3.0](LICENSE). Preserve copyright, license and source obligations when redistributing. Credit belongs to Hakan Seven and the upstream contributors for the original CAD application, and to the contributors identified in this fork's history for their changes.

To support the original project, see [Hakan Seven's GitHub Sponsors](https://github.com/sponsors/HakanSeven12).
