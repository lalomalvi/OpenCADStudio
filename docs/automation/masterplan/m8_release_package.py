"""Stage and verify a whitelisted, local Windows MCP release candidate."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tomllib
import zipfile


SOURCE_FILES = {
    "Cargo.lock": "Cargo.lock",
    "LICENSE": "LICENSE",
    "README.md": "docs/automation/masterplan/M8-RELEASE-QUICKSTART.md",
    "requirements.txt": "docs/automation/masterplan/m8-release-requirements.txt",
    "docs/automation/mcp_client.py": "docs/automation/mcp_client.py",
    "docs/automation/mcp_autocad_probe.ps1": "docs/automation/mcp_autocad_probe.ps1",
    "docs/automation/masterplan/m8_case_cli.py": "docs/automation/masterplan/m8_case_cli.py",
    "docs/automation/masterplan/m8_case_l4_mixed.py":
        "docs/automation/masterplan/m8_case_l4_mixed.py",
    "docs/automation/masterplan/m8_release_package.py":
        "docs/automation/masterplan/m8_release_package.py",
    "docs/automation/masterplan/multi_axis_chain_l4.py":
        "docs/automation/masterplan/multi_axis_chain_l4.py",
    "docs/automation/masterplan/owned_cad_executor.py":
        "docs/automation/masterplan/owned_cad_executor.py",
    "docs/automation/masterplan/planspec.py":
        "docs/automation/masterplan/planspec.py",
    "docs/automation/masterplan/provider_response_receipt.py":
        "docs/automation/masterplan/provider_response_receipt.py",
    "docs/automation/masterplan/reserved_cohort.py":
        "docs/automation/masterplan/reserved_cohort.py",
    "docs/automation/masterplan/reserved_oracle.py":
        "docs/automation/masterplan/reserved_oracle.py",
    "docs/automation/masterplan/reserved_runner.py":
        "docs/automation/masterplan/reserved_runner.py",
    "docs/automation/masterplan/reserved_trial.py":
        "docs/automation/masterplan/reserved_trial.py",
    "docs/automation/masterplan/usage_evidence.py":
        "docs/automation/masterplan/usage_evidence.py",
    "docs/automation/masterplan/fixtures/synthetic-wall.planspec.json":
        "docs/automation/masterplan/fixtures/synthetic-wall.planspec.json",
}
BINARY_MEMBER = "OpenCADStudio.exe"
ZIP_NAME = "OpenCADStudio-mcp-rc-windows-x64.zip"
MAX_MEMBER_BYTES = 400_000_000


class ReleasePackageError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def expected_members() -> set[str]:
    return set(SOURCE_FILES) | {BINARY_MEMBER}


def _check_text_member(name: str, data: bytes) -> None:
    if name == BINARY_MEMBER:
        return
    if b"C:\\Users\\" in data or b"c:\\users\\" in data.lower():
        raise ReleasePackageError(f"Local user path in public member {name}")
    if b"-----BEGIN " + b"PRIVATE KEY-----" in data or b"sk-" + b"proj-" in data:
        raise ReleasePackageError(f"Private material marker in public member {name}")


def _git_clean(root: Path) -> str:
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                            cwd=root, text=True, capture_output=True, check=True)
    if status.stdout.strip():
        raise ReleasePackageError("Commit and clean the source worktree before staging")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          text=True, capture_output=True, check=True).stdout.strip()


def _check_import_closure(repo: Path) -> None:
    local = {path.stem for directory in (repo / "docs/automation",
                                         repo / "docs/automation/masterplan")
             for path in directory.glob("*.py")}
    bundled = {Path(name).stem for name in SOURCE_FILES if name.endswith(".py")}
    for member, source in SOURCE_FILES.items():
        if not member.endswith(".py"):
            continue
        tree = ast.parse((repo / source).read_text(encoding="utf-8"))
        imports = {node.module.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) and node.module}
        imports.update(alias.name.split(".")[0] for node in ast.walk(tree)
                       if isinstance(node, ast.Import) for alias in node.names)
        missing = (imports & local) - bundled
        if missing:
            raise ReleasePackageError(f"Local import omitted from bundle: {member}: {sorted(missing)}")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def pe_machine(path: Path) -> int:
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ReleasePackageError("Release binary lacks DOS/PE header")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        if offset < 0x40 or offset > path.stat().st_size - 6:
            raise ReleasePackageError("Release binary PE offset differs")
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0":
            raise ReleasePackageError("Release binary PE signature differs")
        return struct.unpack("<H", stream.read(2))[0]


def stage(root: Path, binary: Path) -> dict:
    repo = Path(__file__).resolve().parents[3]
    allowed = (repo / "target/mcp-release-bundles").resolve()
    output = root.resolve()
    if output == allowed or not output.is_relative_to(allowed) or output.exists():
        raise ReleasePackageError("Use a new child of target/mcp-release-bundles")
    expected_binary = (repo / "target/mcp-release-build/release/OpenCADStudio.exe").resolve()
    if binary.resolve(strict=True) != expected_binary:
        raise ReleasePackageError("Only the isolated locked release build may be staged")
    commit = _git_clean(repo)
    _check_import_closure(repo)
    if binary.stat().st_size < 1_000_000 or pe_machine(binary) != 0x8664:
        raise ReleasePackageError("Windows x64 release executable is absent or invalid")
    version = tomllib.loads((repo / "Cargo.toml").read_text(encoding="utf-8"))["package"]["version"]
    payload = {}
    for member, source in SOURCE_FILES.items():
        path = repo / source
        if not path.is_file() or path.stat().st_size > MAX_MEMBER_BYTES:
            raise ReleasePackageError(f"Whitelisted source missing or too large: {source}")
        data = path.read_bytes()
        _check_text_member(member, data)
        payload[member] = data
    payload[BINARY_MEMBER] = binary.read_bytes()
    manifest = {
        "schema_version": "m8-local-release-bundle-1",
        "status": "candidate_partial_m7_gates_open",
        "platform": "windows-x86_64",
        "pe_machine": "AMD64-0x8664",
        "application_version": version,
        "source_git_sha": commit,
        "cargo_lock_sha256": sha256(repo / "Cargo.lock"),
        "build_command": "cargo build --release --locked --bin OpenCADStudio --target-dir target/mcp-release-build",
        "binary_signed": False,
        "model_call": False,
        "files": {name: {"sha256": sha256_bytes(data), "bytes": len(data)}
                  for name, data in sorted(payload.items())},
    }
    output.mkdir(parents=True)
    bundle = output / "bundle"
    bundle.mkdir()
    for name, data in sorted(payload.items()):
        destination = bundle / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (bundle / "manifest.json").write_bytes(manifest_bytes)
    archive = output / ZIP_NAME
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=True) as handle:
        for name, data in sorted(payload.items()):
            handle.writestr(_zip_info(name), data)
        handle.writestr(_zip_info("manifest.json"), manifest_bytes)
    (output / "archive.sha256").write_text(sha256(archive) + "\n", encoding="ascii")
    return verify(output)


def verify(root: Path) -> dict:
    root = root.resolve(strict=True)
    bundle = root / "bundle"
    if not bundle.is_dir():
        # Allow verification from an extracted bundle without its outer folder.
        bundle = root
        archive = None
    else:
        archive = root / ZIP_NAME
    manifest_path = bundle / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if (manifest.get("schema_version") != "m8-local-release-bundle-1"
            or manifest.get("status") != "candidate_partial_m7_gates_open"
            or manifest.get("platform") != "windows-x86_64"
            or manifest.get("pe_machine") != "AMD64-0x8664"
            or set(manifest.get("files", {})) != expected_members()
            or manifest.get("cargo_lock_sha256") !=
            manifest["files"]["Cargo.lock"]["sha256"]):
        raise ReleasePackageError("Bundle manifest or member allowlist differs")
    actual_files = {path.relative_to(bundle).as_posix() for path in bundle.rglob("*")
                    if path.is_file()}
    if actual_files != expected_members() | {"manifest.json"}:
        raise ReleasePackageError("Extracted bundle contains missing or extra files")
    for name, record in manifest["files"].items():
        path = bundle / name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(bundle.resolve()):
            raise ReleasePackageError(f"Bundle file escapes root: {name}")
        data = path.read_bytes()
        if len(data) != record.get("bytes") or sha256_bytes(data) != record.get("sha256"):
            raise ReleasePackageError(f"Bundle file changed: {name}")
        _check_text_member(name, data)
    if pe_machine(bundle / BINARY_MEMBER) != 0x8664:
        raise ReleasePackageError("Bundled executable is not Windows x64")
    archive_sha = None
    if archive is not None:
        archive_sha = sha256(archive)
        if (root / "archive.sha256").read_text(encoding="ascii").strip() != archive_sha:
            raise ReleasePackageError("Archive SHA differs")
        with zipfile.ZipFile(archive) as handle:
            names = handle.namelist()
            if (len(names) != len(set(names)) or
                    set(names) != expected_members() | {"manifest.json"}):
                raise ReleasePackageError("Archive member allowlist differs")
            for name in names:
                info = handle.getinfo(name)
                if info.is_dir() or info.file_size > MAX_MEMBER_BYTES:
                    raise ReleasePackageError("Archive member type or size differs")
                expected = manifest_bytes if name == "manifest.json" else (bundle / name).read_bytes()
                if handle.read(name) != expected:
                    raise ReleasePackageError(f"Archive member changed: {name}")
    return {"schema_version": "m8-local-release-bundle-verdict-1",
            "status": "passed_bundle_integrity",
            "source_git_sha": manifest["source_git_sha"],
            "manifest_sha256": sha256(manifest_path),
            "archive_sha256": archive_sha,
            "binary_sha256": manifest["files"][BINARY_MEMBER]["sha256"],
            "member_count": len(expected_members()),
            "model_call": False, "acceptance_m8": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("stage", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    if args.mode == "stage":
        if args.binary is None:
            raise ReleasePackageError("Release binary path required")
        result = stage(args.root, args.binary)
    else:
        result = verify(args.root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
