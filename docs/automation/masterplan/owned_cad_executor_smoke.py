"""L2 synthetic run of OwnedCadExecutor in a child-only OCS profile."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from owned_cad_executor import OwnedCadExecutor
from planspec import dry_run
from reserved_runner import Invocation

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


def main():
    repo = Path(__file__).resolve().parents[3]
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not binary.is_file():
        raise FileNotFoundError(binary)
    root = repo / "target" / "mcp-owned-executor" / (
        time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=False)
    profile = root / "profile"
    profile.mkdir()
    temporary = root / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    fixture = Path(__file__).with_name("fixtures") / "synthetic-wall.planspec.json"
    compiled = dry_run(json.loads(fixture.read_text(encoding="utf-8")))
    source = root / "synthetic-source.png"
    source.write_bytes(b"synthetic source marker; no private image")
    protocol = root / "synthetic-protocol.txt"
    protocol.write_text("synthetic protocol; no model call\n", encoding="utf-8")
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()
    invocation = Invocation("baseline", "synthetic-wall", 1, "owned-cad-synthetic-1",
                            source, protocol, binary, "gpt-6-luna", "medium",
                            sha(source), sha(protocol), sha(binary))
    report = {"schema_version": "m7-owned-cad-l2-smoke-1", "status": "failed",
              "binary_sha256": sha(binary), "fixture_sha256": sha(fixture)}
    gui = subprocess.Popen([str(binary), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise ProtocolError("Isolated GUI identity differs from launched child")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "owned-cad-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        report["preflight"] = {"modal": bool(state.get("modal")),
                               "active_command": bool(state.get("active_command")),
                               "dirty_document_count": sum(bool(doc.get("dirty"))
                                                           for doc in state.get("documents", []))}
        evidence = OwnedCadExecutor(client, gui, binary, root,
                                    capture_viewport=True)(invocation, compiled)
        cad = json.loads(evidence.read_text(encoding="utf-8"))
        report.update({"status": "passed", "session_pid": gui.pid,
                       "evidence_file": evidence.name,
                       "evidence_sha256": sha(evidence),
                       "dwg_sha256": cad["dwg"]["sha256"],
                       "capture_sha256": cad["capture"]["sha256"],
                       "completed_commands": cad["completed_commands"],
                       "added_entities": cad["added_entities"]})
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        report["post_save"] = {"modal": bool(state.get("modal")),
                               "active_command": bool(state.get("active_command")),
                               "dirty_document_count": sum(bool(doc.get("dirty"))
                                                           for doc in state.get("documents", []))}
        if report["post_save"]["dirty_document_count"]:
            # Preserve the verified DWG; save the GUI's live document separately
            # to make this owned synthetic process clean for shutdown.
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "save", "request_id": "owned-cad-clean-save-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
            report["after_cleanup_save_dirty_count"] = sum(
                bool(doc.get("dirty")) for doc in state.get("documents", []))
        try:
            quit_result = client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "owned-cad-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
            report["quit_status"] = quit_result.get("status")
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        try:
            gui.wait(timeout=10)
            report["shutdown"] = "exited"
        except subprocess.TimeoutExpired:
            report["shutdown"] = "waiting_user_or_unclosed"
            report["status"] = "partial"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        if report["status"] in {"failed", "partial"} and gui.poll() is None:
            gui.terminate()  # Only this synthetic child, not an existing user GUI.
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_own_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "child_still_running"
        report["gui_exited"] = gui.poll() is not None
        with (root / "report.json").open("x", encoding="utf-8") as target:
            json.dump(report, target, sort_keys=True, indent=2)
            target.write("\n")
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
