"""Independent, scoped L4 verdict for the synthetic four-edge wall fixture.

This never promotes M7 G0-G10. It binds an AutoCAD report to one verified
reserved slot, its CAD evidence/DWG and an explicit synthetic bridge.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from owned_cad_executor import verify_owned_cad_evidence
from reserved_evaluator import inspect_slot
from reserved_runner import verify_envelope
from reserved_trial import TrialJournal, _file_sha


class ExternalVerdictError(ValueError):
    pass


_HASH = re.compile(r"[0-9A-F]{64}")


def _read(path: Path) -> dict:
    if not isinstance(path, Path) or not path.is_absolute() or not path.is_file() \
            or path.suffix.lower() != ".json" or path.stat().st_size > 2_000_000:
        raise ExternalVerdictError("Absolute bounded JSON evidence is required")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ExternalVerdictError("Evidence JSON must be an object")
    return value


def assess_synthetic_wall(journal: TrialJournal, arm: str, case_id: str,
                          repetition: int, *, bridge_path: Path,
                          autocad_path: Path) -> dict:
    """Require positive independent geometry, unit, audit and provenance checks."""
    binding = inspect_slot(journal, arm, case_id, repetition)
    slot = journal.verified_slot(arm, case_id, repetition)
    result = slot["result"]
    if result["disposition"] != "completed" or result["evidence_file"] is None:
        raise ExternalVerdictError("A completed reserved invocation is required")
    run = journal.path.parent.resolve(strict=True)
    envelope_path = (run / result["evidence_file"]).resolve(strict=True)
    envelope = verify_envelope(envelope_path)
    ref = envelope.get("cad_evidence")
    if not isinstance(ref, dict):
        raise ExternalVerdictError("CAD evidence is missing")
    cad_path = (run / ref["file"]).resolve(strict=True)
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad.get("handles_by_id")
    if not isinstance(handles, dict) or len(handles) != 4 or \
            cad.get("added_entities") != 4:
        raise ExternalVerdictError("Four mapped synthetic wall edges are required")
    pipeline_path = run.parent / "report.json"
    pipeline = _read(pipeline_path)
    bridge = _read(bridge_path)
    external = _read(autocad_path)
    fixture = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"
    dwg_sha = cad["dwg"]["sha256"]
    if pipeline.get("schema_version") != "m7-reserved-pipeline-l2-1" or \
            pipeline.get("status") != "passed" or \
            pipeline.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            pipeline.get("dwg_sha256") != dwg_sha or \
            pipeline.get("fixture_sha256") != _file_sha(fixture) or \
            bridge.get("schema_version") != "m7-l4-bridge-1" or \
            bridge.get("status") != "passed" or \
            bridge.get("negative_seed") is not None or \
            bridge.get("source_pipeline_report_sha256") != _file_sha(pipeline_path) or \
            bridge.get("source_cad_evidence_sha256") != _file_sha(cad_path) or \
            bridge.get("verified_output", {}).get("sha256") != dwg_sha or \
            bridge.get("planspec", {}).get("fixture") != fixture.name or \
            bridge.get("planspec", {}).get("fixture_sha256") != _file_sha(fixture) or \
            bridge.get("planspec", {}).get("handles_by_id") != handles:
        raise ExternalVerdictError("Synthetic bridge does not bind the reserved CAD run")
    blockers = []
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            not isinstance(external.get("executable_version"), str) or \
            not _HASH.fullmatch(str(external.get("executable_sha256", ""))):
        blockers.append("external_engine_identity_invalid")
    if external.get("input_sha256_before") != dwg_sha or \
            external.get("input_sha256_after") != dwg_sha or \
            external.get("input_unchanged") is not True:
        blockers.append("external_input_changed_or_wrong")
    if external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("census_done") is not True or \
            external.get("forced_termination") is not False or \
            type(external.get("exit_code")) is not int or external["exit_code"] != 0 or \
            external.get("verdict") != "audit_and_census_passed":
        blockers.append("external_audit_or_process_failed")
    if external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 4 or \
            external.get("model_types") != {"LINE": 4}:
        blockers.append("external_units_or_census_differs")
    rows = external.get("geometry_comparison")
    matched_rows = (sum(isinstance(item, dict) and
                        item.get("handle") == handles.get(item.get("planspec_id")) and
                        item.get("matched_1e_6") is True for item in rows)
                    if isinstance(rows, list) else 0)
    if not isinstance(rows, list) or len(rows) != 4 or \
            {item.get("planspec_id") for item in rows if isinstance(item, dict)} != set(handles) or \
            any(not isinstance(item, dict) or item.get("handle") != handles.get(item.get("planspec_id"))
                or item.get("matched_1e_6") is not True for item in rows) or \
            external.get("source_report_match") is not True or \
            external.get("geometry_source_valid") is not True or \
            external.get("wall_model_count_match") is not True or \
            external.get("semantic_verdict") != "matched_scoped":
        blockers.append("external_geometry_or_provenance_differs")
    return {"schema_version": "m7-synthetic-external-verdict-1",
            "status": "passed_scoped_l4" if not blockers else "failed_scoped_l4",
            "scope": "synthetic-wall-four-edges-only", "blockers": blockers,
            "slot_journal_sha256": binding["journal_sha256"],
            "invocation_envelope_sha256": binding["invocation_envelope_sha256"],
            "bridge_sha256": _file_sha(bridge_path),
            "autocad_report_sha256": _file_sha(autocad_path),
            "dwg_sha256": dwg_sha, "geometry_matches": matched_rows,
            "m7_gates": {f"G{i}": "pending" for i in range(11)}}


def load_synthetic_journal(root: Path, binary: Path) -> TrialJournal:
    """Reopen only the synthetic six-case fixture layout from the L2 harness."""
    repo = Path(__file__).resolve().parents[3]
    allowed = (repo / "target/mcp-reserved-pipeline").resolve(strict=True)
    root = root.resolve(strict=True)
    if root.parent != allowed:
        raise ExternalVerdictError("Only synthetic reserved pipeline runs are supported")
    images = {f"case-{i}": root / "images" / f"synthetic-{i}.png"
              for i in range(6)}
    oracles = {f"case-{i}": root / "oracles" / f"case-{i}.json"
               for i in range(6)}
    protocol = root / "protocol.json"
    return TrialJournal(
        root / "run" / "attempts.jsonl", "synthetic-m7",
        cohort_path=root / "cohort.json", image_paths=images,
        input_root=root / "images", oracle_manifest_path=root / "oracle-freeze.json",
        oracle_paths=oracles, oracle_root=root / "oracles",
        arm_protocols={"baseline": protocol, "candidate": protocol},
        arm_binaries={"baseline": binary.resolve(strict=True),
                      "candidate": binary.resolve(strict=True)},
        requested_model="gpt-6-luna", effort="medium",
        hardware_label="synthetic-host",
        supervisor_protocol_path=root / "synthetic-supervisor.txt",
        supervisor_model="gpt-6-sol", supervisor_effort="low")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--bridge", required=True, type=Path)
    parser.add_argument("--autocad", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    journal = load_synthetic_journal(arguments.run_root, arguments.binary)
    verdict = assess_synthetic_wall(
        journal, "baseline", "case-0", 1,
        bridge_path=arguments.bridge.resolve(strict=True),
        autocad_path=arguments.autocad.resolve(strict=True))
    encoded = json.dumps(verdict, sort_keys=True, indent=2) + "\n"
    if arguments.output is not None:
        repo = Path(__file__).resolve().parents[3]
        allowed = (repo / "target/mcp-external").resolve(strict=True)
        output = arguments.output.resolve(strict=False)
        if not output.is_relative_to(allowed) or output.suffix.lower() != ".json":
            raise ExternalVerdictError("Verdict output must be under synthetic external target")
        with output.open("x", encoding="utf-8") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
    print(encoded)
    if verdict["status"] != "passed_scoped_l4":
        raise SystemExit(1)
