"""Reuse a frozen Luna chain and a 21-line apartment plan in owned CAD."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image

from cli_development_trial import parse_cli_events
from horizontal_crops_trial import _write_new
from integrated_apartment_dimensions import compile_integrated_apartment
from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from reserved_runner import Invocation
from reserved_trial import _file_sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class IntegratedTrialError(ValueError):
    pass


def validate_bundle(root: Path, image: Path, binary: Path) -> tuple[dict, dict, dict]:
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    base = root.parent / "apartment-horizontal-bundle-v1"
    chain = root.parent / "apartment-bottom-chain-v1"
    if frozen.get("schema_version") != "m7-integrated-dimension-freeze-1" or \
            frozen.get("acceptance_m7") is not False or \
            frozen.get("source_sha256") != _file_sha(image) or \
            frozen.get("base_plan_sha256") != _file_sha(base / "model-plan.json") or \
            frozen.get("base_report_sha256") != _file_sha(base / "report.json") or \
            frozen.get("chain_freeze_sha256") != _file_sha(chain / "freeze.json") or \
            frozen.get("chain_events_sha256") != _file_sha(chain / "events.jsonl") or \
            frozen.get("chain_report_sha256") != _file_sha(chain / "report.json") or \
            frozen.get("compiler_sha256") != _file_sha(
                Path(__file__).with_name("integrated_apartment_dimensions.py")) or \
            frozen.get("planspec_sha256") != _file_sha(
                Path(__file__).with_name("planspec.py")) or \
            frozen.get("runner_sha256") != _file_sha(Path(__file__)) or \
            frozen.get("cad_binary_sha256") != _file_sha(binary):
        raise IntegratedTrialError("Frozen dimension integration differs")
    base_plan = json.loads((base / "model-plan.json").read_text(encoding="utf-8"))
    chain_freeze = json.loads((chain / "freeze.json").read_text(encoding="utf-8"))
    if chain_freeze.get("source_sha256") != frozen["source_sha256"] or \
            chain_freeze.get("expected_widths_m") != [2.58, 2.85, 2.58, 2.85, 1.0, 2.0] or \
            chain_freeze.get("acceptance_m7") is not False:
        raise IntegratedTrialError("Source axis-chain contract differs")
    observation, usage = parse_cli_events(chain / "events.jsonl")
    with Image.open(image) as bitmap:
        plan, compiled = compile_integrated_apartment(
            base_plan, observation, image_width=bitmap.width,
            image_height=bitmap.height, frozen=frozen)
    return plan, compiled, usage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root, image, binary = (value.resolve(strict=True) for value in
                           (args.run_root, args.image, args.binary))
    plan, compiled, usage = validate_bundle(root, image, binary)
    _write_new(root / "model-plan.json", plan)
    report = {"schema_version": "m7-integrated-dimension-trial-1",
              "status": "failed", "acceptance_m7": False,
              "effective_model": "unverified_by_cli_jsonl",
              "model_reuse": "bottom_chain_v1_same_events_no_new_model_call",
              "source_sha256": _file_sha(image),
              "freeze_sha256": _file_sha(root / "freeze.json"),
              "plan_sha256": _file_sha(root / "model-plan.json"),
              "binary_sha256": _file_sha(binary),
              "usage_cli_source_run": usage,
              "l3_plan_gate": "passed_scoped_reused_source",
              "cad_status": "pending"}
    profile, temporary, cad_root = (root / name for name in
                                    ("profile", "temp", "cad"))
    for path in (profile, temporary, cad_root):
        path.mkdir(exist_ok=False)
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    gui = subprocess.Popen([str(binary), "--new-instance"],
                           cwd=binary.parent.parent.parent, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise IntegratedTrialError("Owned CAD process identity differs")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "integrated-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        if state.get("modal"):
            raise IntegratedTrialError("Owned CAD modal remained open")
        invocation = Invocation(
            "development", root.name, 1,
            "integrated-" + hashlib.sha256(str(root).encode()).hexdigest()[:24],
            image, root / "freeze.json", binary, "gpt-6-luna", "medium",
            _file_sha(image), _file_sha(root / "freeze.json"), _file_sha(binary))
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        report.update({"cad_status": "passed_l2_internal",
                       "cad_evidence_sha256": _file_sha(evidence_path),
                       "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "added_entities": evidence["added_entities"],
                       "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "save", "request_id": "integrated-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            report["quit_result"] = client.tool("ocs_execute", {
                "ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "integrated-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        gui.wait(timeout=60)
        report["status"] = "passed_scoped_reuse_l3_cad_l2"
        report["shutdown"] = "exited"
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error_message"] = str(error)[:300]
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        if gui.poll() is None:
            gui.terminate()  # this owned child only
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        _write_new(root / "report.json", report)
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
