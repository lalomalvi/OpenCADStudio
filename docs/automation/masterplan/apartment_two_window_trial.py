"""Run a frozen schematic window plan in an owned OpenCADStudio instance."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from apartment_second_window_compiler import compose
from east_north_window_observation import score
from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from reserved_runner import Invocation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_new(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root, image, binary = (path.resolve(strict=True) for path in
                           (args.run_root, args.image, args.binary))
    parent = root.parent
    base = parent / "apartment-integrated-window-v11b"
    observed = parent / "apartment-east-north-window-v1"
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    expected = {
        "source_sha256": digest(image),
        "base_plan_sha256": digest(base / "model-plan.json"),
        "base_report_sha256": digest(base / "report.json"),
        "observation_freeze_sha256": digest(observed / "freeze.json"),
        "observation_events_sha256": digest(observed / "events.jsonl"),
        "observation_verdict_sha256": digest(observed / "verdict.json"),
        "compiler_sha256": digest(Path(__file__).with_name("apartment_second_window_compiler.py")),
        "runner_sha256": digest(Path(__file__)),
        "planspec_sha256": digest(Path(__file__).with_name("planspec.py")),
        "schema_sha256": digest(Path(__file__).with_name("planspec-v11.schema.json")),
        "observation_gate_sha256": digest(Path(__file__).with_name("east_north_window_observation.py")),
        "cad_binary_sha256": digest(binary),
    }
    if (frozen.get("schema_version") != "m7-apartment-two-window-trial-freeze-1" or
            frozen.get("cad_permitted") is not True or
            any(frozen.get(key) != value for key, value in expected.items())):
        raise ValueError("Frozen CAD inputs differ")
    verdict = score(image, observed, persist=False)
    if verdict["status"] != "passed_observation_only" or \
            digest(observed / "verdict.json") != expected["observation_verdict_sha256"]:
        raise ValueError("Window observation differs")
    plan, compiled, window = compose(
        json.loads((base / "model-plan.json").read_text(encoding="utf-8")), verdict)
    write_new(root / "model-plan.json", plan)
    write_new(root / "window-composite.json", window)
    report = {"schema_version": "m7-apartment-two-window-trial-1", "status": "failed",
              "source_sha256": digest(image), "freeze_sha256": digest(root / "freeze.json"),
              "plan_sha256": digest(root / "model-plan.json"),
              "window_sha256": digest(root / "window-composite.json"),
              "binary_sha256": digest(binary), "cad_status": "pending",
              "acceptance_m7": False, "effective_model": "unverified_by_cli_jsonl"}
    profile, temporary, cad_root = (root / name for name in ("profile", "temp", "cad"))
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
            raise ValueError("Owned GUI identity differs")
        session = selected["session_id"]
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "window-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if state.get("modal"):
            raise ValueError("Owned GUI modal remained open")
        invocation = Invocation("development", root.name, 1,
            "two-window-" + hashlib.sha256(str(root).encode()).hexdigest()[:24],
            image, root / "freeze.json", binary, "gpt-6-luna", "medium",
            digest(image), digest(root / "freeze.json"), digest(binary))
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        report.update({"cad_status": "passed_l2_internal", "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "cad_evidence_sha256": digest(evidence_path),
                       "added_entities": evidence["added_entities"], "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "save", "request_id": "window-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "window-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=60)
        report["status"] = "passed_scoped_two_window_l2"
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
            gui.terminate()
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        write_new(root / "report.json", report)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
