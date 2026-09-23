"""Generate sanitized M0 baseline without reading the private drawing."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PLAN = Path(__file__).resolve().parent
text = (PLAN / "01-BASELINE-Y-CORRECCIONES.md").read_text(encoding="utf-8")


def extract(label):
    match = re.search(rf"^- {re.escape(label)}: ([0-9A-F]{{64}})\.$", text, re.M)
    if not match:
        raise ValueError(f"Missing documented baseline: {label}")
    return match.group(1)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


release = (Path.home() / ".codex/worktrees/image-to-cad-hardening/OPEN CAD/target/release/OpenCADStudio.exe")
release_hash = hashlib.sha256(release.read_bytes()).hexdigest().upper() if release.is_file() else None
debug = ROOT / "target/debug/OpenCADStudio.exe"
debug_hash = hashlib.sha256(debug.read_bytes()).hexdigest().upper() if debug.is_file() else None
documented_release_hash = extract("SHA256 binario")
baseline = {
    "schema_version": "m0-baseline-1",
    "historical_case": "2026-09-23-luna-floorplan-01",
    "historical_status": "partial",
    "historical_hashes_from_existing_documentation_not_reopened": {
        "source_png_sha256": extract("SHA256 fuente"),
        "dwg_sha256": extract("SHA256 DWG"),
        "preview_sha256": extract("SHA256 preview"),
    },
    "historical_metrics_from_existing_documentation": {
        "responses": 84, "total_tokens": 9797952, "mcp_calls": 30,
        "entities": 273, "layers_used": 1,
    },
    "integration": {
        "base": git("merge-base", "origin/main", "codex/image-to-cad-hardening"),
        "origin_main_at_m0": git("rev-parse", "origin/main"),
        "experimental_head": git("rev-parse", "codex/image-to-cad-hardening"),
        "implementation_head": git("rev-parse", "HEAD"),
        "cargo_lock_sha256": hashlib.sha256((ROOT / "Cargo.lock").read_bytes()).hexdigest().upper(),
        "rustc_version": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        "cargo_version": subprocess.check_output(["cargo", "--version"], text=True).strip(),
        "validation_build_command": "cargo test --lib mcp::tests",
        "historical_release_code_revision": git("rev-parse", "4e5a69f3"),
        "historical_release_executable_sha256": release_hash,
        "historical_release_matches_documented_hash": release_hash == documented_release_hash,
        "current_debug_executable_sha256": debug_hash,
    },
    "scope_note": "Historical private PNG and DWG were not read by this generator.",
}
(PLAN / "BASELINE.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
