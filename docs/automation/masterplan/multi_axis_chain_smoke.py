"""L2 smoke for one synthetic three-dimension axis chain in an owned GUI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image

from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from planspec import dry_run
from reserved_runner import Invocation
from reserved_trial import _file_sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError  # noqa: E402


def measures(client: Client, session: str, handles: dict[str, str]) -> dict[str, float]:
    dimension_ids = ("axis-left", "axis-right", "axis-total")
    response = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
        "parameters": {"handles": [handles[name] for name in dimension_ids],
                       "detail": "full"}})
    by_handle = {item.get("handle"): item for item in response.get("entities", [])}
    if set(by_handle) != {handles[name] for name in dimension_ids}:
        raise ProtocolError("Synthetic chain dimension handles differ")
    expected = {"axis-left": 1.5, "axis-right": 1.5, "axis-total": 3.0}
    observed = {}
    for name in dimension_ids:
        item = by_handle[handles[name]]
        actual = item.get("properties", {}).get("Linear", {}).get("base", {}).get("actual_measurement")
        if item.get("type") != "Dimension" or item.get("layer") != "0" or \
                type(actual) not in {int, float} or abs(actual - expected[name]) > 1e-6:
            raise ProtocolError(f"Synthetic chain {name} measure or type differs")
        observed[name] = actual
    return observed


def main() -> None:
    repo = Path(__file__).resolve().parents[3]
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else
                  repo / "target/debug/OpenCADStudio.exe").resolve(strict=True)
    fixture = Path(__file__).with_name("fixtures") / \
        "synthetic-wall-axis-chain-v8.planspec.json"
    plan = json.loads(fixture.read_text(encoding="utf-8"))
    compiled = dry_run(plan)
    if not compiled["executable"] or len(compiled["commands"]) != 7 or \
            compiled["dimension_compilation"] != {
                "status": "compiled_multi_axis_spans", "generated_parts": 3}:
        raise ProtocolError("Synthetic chain did not pass frozen dry-run")
    root = repo / "target/mcp-multi-axis-chain" / (
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=False)
    cad_root = root / "cad"
    cad_root.mkdir()
    profile, temporary = root / "profile", root / "temp"
    profile.mkdir()
    temporary.mkdir()
    source = root / "synthetic-source.png"
    Image.new("RGB", (32, 32), (255, 255, 255)).save(source)
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "m4-multi-axis-chain-l2-1", "status": "failed",
              "fixture_sha256": _file_sha(fixture),
              "binary_sha256": _file_sha(binary),
              "commands_sha256": compiled["commands_sha256"],
              "dimension_graph": compiled["dimension_graph"]}
    gui = subprocess.Popen([str(binary), "--new-instance"], cwd=repo,
                           env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise ProtocolError("Synthetic chain GUI child identity differs")
        session = selected["session_id"]
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "axis-chain-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if state.get("modal"):
            raise ProtocolError("Synthetic chain startup modal remained open")
        invocation = Invocation("synthetic", "axis-chain", 1,
                                "axis-chain-" + uuid.uuid4().hex,
                                source, fixture, binary, "synthetic", "none",
                                _file_sha(source), _file_sha(fixture), _file_sha(binary))
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        handles = evidence["handles_by_id"]
        before = measures(client, session, handles)
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if any(doc.get("dirty") for doc in state.get("documents", [])):
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "save", "request_id": "axis-chain-clean-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        dwg = evidence_path.parent / evidence["dwg"]["file"]
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "open", "request_id": "axis-chain-reopen-" + uuid.uuid4().hex,
                        "path": str(dwg)}})
        after = measures(client, session, handles)
        if before != after:
            raise ProtocolError("Synthetic chain measure changed after DWG reopen")
        report.update({"status": "passed_l2_internal", "session_pid": gui.pid,
                       "cad_evidence_sha256": _file_sha(evidence_path),
                       "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "handles_by_id": handles, "measures_before": before,
                       "measures_after": after})
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run", "request_id": "axis-chain-quit-" + uuid.uuid4().hex,
                        "cmd": "QUIT"}})
        gui.wait(timeout=60)
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
            gui.terminate()  # only the child launched above
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        with (root / "report.json").open("x", encoding="utf-8") as target:
            json.dump(report, target, sort_keys=True, indent=2)
            target.write("\n")
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
