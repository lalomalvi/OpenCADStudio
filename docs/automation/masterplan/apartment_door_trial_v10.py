"""Execute a typed PlanSpec v10 apartment door in an owned CAD process."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from apartment_door_compiler import _last_observation
from apartment_door_compiler_v10 import compose
from door_crop_observation import evaluate as evaluate_door
from horizontal_crops_trial import _write_new
from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from reserved_runner import Invocation
from reserved_trial import _file_sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class DoorTrialError(ValueError):
    pass


def validate_bundle(root: Path, source: Path, binary: Path):
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    prior = root.parent / "apartment-integrated-dimensions-hidden-v3"
    wall = root.parent / "apartment-door-jamb-wall-v1"
    door = root.parent / "apartment-door-discovery-v4"
    if (frozen.get("schema_version") != "m7-apartment-door-trial-freeze-2" or
            frozen.get("acceptance_m7") is not False or
            frozen.get("source_sha256") != _file_sha(source) or
            frozen.get("base_plan_sha256") != _file_sha(prior / "model-plan.json") or
            frozen.get("base_report_sha256") != _file_sha(prior / "report.json") or
            frozen.get("wall_freeze_sha256") != _file_sha(wall / "freeze.json") or
            frozen.get("wall_events_sha256") != _file_sha(wall / "events.jsonl") or
            frozen.get("door_freeze_sha256") != _file_sha(door / "freeze.json") or
            frozen.get("door_events_sha256") != _file_sha(door / "events.jsonl") or
            frozen.get("door_verdict_sha256") != _file_sha(door / "verdict.json") or
            frozen.get("compiler_sha256") != _file_sha(
                Path(__file__).with_name("apartment_door_compiler_v10.py")) or
            frozen.get("prior_compiler_sha256") != _file_sha(
                Path(__file__).with_name("apartment_door_compiler.py")) or
            frozen.get("schema_sha256") != _file_sha(
                Path(__file__).with_name("planspec-v10.schema.json")) or
            frozen.get("planspec_sha256") != _file_sha(
                Path(__file__).with_name("planspec.py")) or
            frozen.get("door_gate_sha256") != _file_sha(
                Path(__file__).with_name("door_crop_observation.py")) or
            frozen.get("runner_sha256") != _file_sha(Path(__file__)) or
            frozen.get("cad_binary_sha256") != _file_sha(binary)):
        raise DoorTrialError("Frozen source, code or CAD binary differs")
    if evaluate_door(door, source)["status"] != "passed_observation_only":
        raise DoorTrialError("Door source failed observation gate")
    wall_freeze = json.loads((wall / "freeze.json").read_text(encoding="utf-8"))
    if wall_freeze.get("source_sha256") != frozen["source_sha256"]:
        raise DoorTrialError("Jamb wall source differs")
    base_plan = json.loads((prior / "model-plan.json").read_text(encoding="utf-8"))
    return compose(base_plan, _last_observation(wall / "events.jsonl"),
                   _last_observation(door / "events.jsonl"), wall_freeze)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root, image, binary = (path.resolve(strict=True) for path in
                           (args.run_root, args.image, args.binary))
    plan, compiled, metadata = validate_bundle(root, image, binary)
    _write_new(root / "model-plan.json", plan)
    _write_new(root / "door-composite.json", metadata)
    report = {"schema_version": "m7-apartment-door-trial-2", "status": "failed",
              "acceptance_m7": False,
              "effective_model": "unverified_by_cli_jsonl",
              "source_sha256": _file_sha(image),
              "freeze_sha256": _file_sha(root / "freeze.json"),
              "plan_sha256": _file_sha(root / "model-plan.json"),
              "composite_sha256": _file_sha(root / "door-composite.json"),
              "binary_sha256": _file_sha(binary), "cad_status": "pending"}
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
            raise DoorTrialError("Owned CAD process identity differs")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "door-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        if state.get("modal"):
            raise DoorTrialError("Owned CAD modal remained open")
        invocation = Invocation(
            "development", root.name, 1,
            "door-v10-" + hashlib.sha256(str(root).encode()).hexdigest()[:24],
            image, root / "freeze.json", binary, "gpt-6-luna", "high",
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
                "request": {"op": "save", "request_id": "door-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            report["quit_result"] = client.tool("ocs_execute", {
                "ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "door-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        gui.wait(timeout=60)
        report["status"] = "passed_scoped_typed_door_l2"
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
            gui.terminate()  # owned child only
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
