"""Seal one completed synthetic CAD run from actual local report and files.

Writes sanitized AUDIT, SAVE, VERDICT and SEAL once in the run directory.
The drawing and private profile remain local and are never embedded in JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from artifact_evidence import verify_ref
from planspec import dry_run


class SealError(ValueError):
    pass


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().upper()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _write_once(path: Path, value: Any) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    with os.fdopen(os.open(path, flags, 0o600), "wb") as target:
        target.write(_json_bytes(value))
        target.flush()
        os.fsync(target.fileno())


def prepare(run: Path, binary: Path) -> dict[str, Any]:
    root = run.resolve(strict=True)
    report_path = root / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "passed" or report.get("gui_exited") is not True \
            or report.get("shutdown") != "exited":
        raise SealError("CAD run did not finish with GUI exit")
    if digest(binary) != report.get("binary_sha256"):
        raise SealError("Runtime binary hash differs from run report")
    fixture = Path(__file__).with_name("fixtures") / "synthetic-room.planspec.json"
    compiled = dry_run(json.loads(fixture.read_text(encoding="utf-8")))
    planspec = report.get("planspec", {})
    if not compiled["executable"] or digest(fixture).lower() != planspec.get("fixture_sha256") \
            or compiled["commands_sha256"] != planspec.get("commands_sha256") \
            or len(planspec.get("handles_by_id", {})) != len(compiled["commands"]):
        raise SealError("PlanSpec fixture, commands or handle coverage differs")
    audit = report.get("audit_summary", {})
    saved = report.get("verified_output", {})
    if audit.get("status") != "passed" or audit.get("summary") != {"errors": 0, "warnings": 0} \
            or audit.get("target", {}).get("lossless") is not True \
            or audit.get("unknown_entities") != 0 \
            or audit.get("manifest") != saved.get("reopened_manifest"):
        raise SealError("Audit and reopened manifest do not agree")
    drawing = Path(saved.get("path", ""))
    if drawing.resolve(strict=True).parent != root or drawing.name != "synthetic-verified.dwg":
        raise SealError("Verified drawing escapes the synthetic run")
    if digest(drawing) != saved.get("sha256") or drawing.stat().st_size != saved.get("bytes"):
        raise SealError("Verified drawing hash or size changed")
    references = []
    if "capture_artifact" in report:
        reference = report["capture_artifact"]
        try:
            verify_ref(root, reference, document_id=reference["document_id"],
                       geometry_revision=reference["geometry_revision"],
                       camera_revision=reference["camera_revision"])
        except (ValueError, KeyError, OSError) as error:
            raise SealError("Capture artifact differs from its revision-bound reference") from error
        references.append(reference)
    audit_public = {"schema_version": "m3-audit-1", "status": audit["status"],
                    "summary": audit["summary"], "target": audit["target"],
                    "manifest": audit["manifest"], "bounds": audit["bounds"],
                    "unknown_entities": audit["unknown_entities"]}
    save_public = {"schema_version": "m3-save-1", "file": drawing.name,
                   "sha256": saved["sha256"], "bytes": saved["bytes"],
                   "reopened_manifest": saved["reopened_manifest"],
                   "verification_engine": "OpenCADStudio-internal"}
    verdict = {"schema_version": "m3-verdict-1", "status": "partial",
               "passed_gates": ["synthetic_planspec", "mcp_execution", "internal_audit",
                                "internal_dwg_reopen", "gui_exit"] +
                               (["capture_revision_checked"] if references else []),
               "pending_gates": ["image_interpretation", "render_fence", "external_cad_engine",
                                 "human_review"],
               "model_identity": "unknown", "billed_cost": None}
    return {"AUDIT.json": audit_public, "SAVE.json": save_public,
            "VERDICT.json": verdict,
            "ARTIFACTS.json": {"schema_version": "m3-artifacts-1", "references": references},
            "drawing_sha256": saved["sha256"], "binary_sha256": report["binary_sha256"],
            "report_sha256": digest(report_path)}


def seal_run(run: Path, binary: Path) -> dict[str, Any]:
    root = run.resolve(strict=True)
    prepared = prepare(root, binary)
    for name in ("AUDIT.json", "SAVE.json", "VERDICT.json", "ARTIFACTS.json", "SEAL.json"):
        if (root / name).exists():
            raise SealError("Evidence files already exist; preserve this cut and use a new run")
    for name in ("AUDIT.json", "SAVE.json", "VERDICT.json", "ARTIFACTS.json"):
        _write_once(root / name, prepared[name])
    sealed_files = {name: digest(root / name) for name in
                    ("AUDIT.json", "SAVE.json", "VERDICT.json", "ARTIFACTS.json")}
    seal = {"schema_version": "m3-cad-seal-2", "status": "partial",
            "files_sha256": sealed_files, "report_sha256": prepared["report_sha256"],
            "drawing_sha256": prepared["drawing_sha256"],
            "binary_sha256": prepared["binary_sha256"]}
    _write_once(root / "SEAL.json", seal)
    return seal


def verify_seal(run: Path, binary: Path) -> None:
    root = run.resolve(strict=True)
    seal = json.loads((root / "SEAL.json").read_text(encoding="utf-8"))
    prepared = prepare(root, binary)
    version = seal.get("schema_version")
    if version not in {"m3-cad-seal-1", "m3-cad-seal-2"} or seal.get("status") != "partial" \
            or seal.get("report_sha256") != prepared["report_sha256"] \
            or seal.get("drawing_sha256") != prepared["drawing_sha256"] \
            or seal.get("binary_sha256") != prepared["binary_sha256"]:
        raise SealError("Seal source hashes differ")
    covered = {"AUDIT.json", "SAVE.json", "VERDICT.json"}
    if version == "m3-cad-seal-2":
        covered.add("ARTIFACTS.json")
    for name, expected in seal.get("files_sha256", {}).items():
        if name not in covered \
                or digest(root / name) != expected \
                or (version == "m3-cad-seal-2" and
                    (root / name).read_bytes() != _json_bytes(prepared[name])):
            raise SealError("Sealed evidence file changed")
    if set(seal.get("files_sha256", {})) != covered:
        raise SealError("Seal file coverage is incomplete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_seal(args.run, args.binary)
        print("sealed evidence verified")
    else:
        print(json.dumps(seal_run(args.run, args.binary), indent=2))


if __name__ == "__main__":
    main()
