# Operational contract for desktop installation agents

“Download, install and open” means complete download/build → verified package →
per-user installation/portable folder → resolved absolute executable → verified
rendered GUI → MCP on that **same** binary. `git clone`, build completion and a
started process do not satisfy that request.

1. Read [Windows](windows.md) or [macOS](macos.md) and run `diagnose` first.
   Check installation, PATH and conventional locations before declaring a tool
   missing. Track source, package/download, installation and log directories.
2. Query the fork's real releases. Prefer only a compatible package with the
   required origin/version metadata, checksum and MCP verification. Never label
   upstream, an old local binary or a tag without evidence as this fork.
3. If no package exists, execute `build` and install its printed ZIP. Do not ask
   the user for a path this workflow is responsible for generating. If a native
   toolchain or permission is missing, retain the diagnosis and complete
   independent preparation before naming the exact pending operator action.
4. Execute `install`, `open`, `path` and `verify` as appropriate. Pass a custom
   `--install-dir` consistently. `path` prints only the resolved executable;
   `config` generates its actual command/args/profile, `mcp` forwards only protocol
   stdio with that profile, and `open` starts the GUI. Do not conflate them.
5. Inspect `summary.json`, PID-correlated session, window/capture and actual
   GUI image. Preserve private drawings and active sessions. The helper's new
   empty document uses `OCS_CONFIG_DIR` in its own logs. Never run a CAD mutation
   on an unowned session returned by global discovery.
6. Report version, full source commit when available, dirty/clean state,
   architecture, provenance, package/hash, application, MCP executable and logs
   as absolute paths. Separate protocol acceptance, GUI acceptance, CAD
   semantics, Finder acceptance, signing/notarization and native CI.
7. Source-build and package verification do not authorize publishing a release,
   pushing changes or installing global dependencies. Leave reviewed artifacts
   ready if such an action is not authorized. Never bypass Gatekeeper/SmartScreen.

Private profiles contain automation authentication descriptors. Keep them local;
publish only the selected summaries, logs and synthetic captures listed in CI.
Never upload `gui-config` or `protocol-config` directories or bridge tokens.

The dated [audit and verification](audit-20260928.md) records what actually ran.
The reusable workflow has no default publication step; an existing release or
explicit reusable caller is required to upload approved artifacts.
