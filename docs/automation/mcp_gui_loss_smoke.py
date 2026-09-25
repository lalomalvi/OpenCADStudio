"""L2 fail-closed probe after loss of this harness's synthetic GUI child.

This probe intentionally terminates only the GUI process that it launched in a
new workspace-local profile. It never opens a user document or replays a batch.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, MODERN, ProtocolError, ToolError, UncertainMutation
from mcp_isolated_smoke import read_state


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    run = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") + "-gui-loss-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    profile = run / "profile"
    temporary = run / "temp"
    profile.mkdir()
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    gui = subprocess.Popen([str(server), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(server, environment=environment, timeout=5)
    report = {"schema_version": "mcp-gui-loss-l2-1", "status": "failed",
              "run": str(run), "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "gui_pid": gui.pid}
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        session = selected["session_id"]
        if selected.get("process_id") != gui.pid or Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("Selected GUI is not this harness's synthetic child")
        report["session_id"] = session
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "gui-loss-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Synthetic startup modal remains")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "gui-loss-new-" + uuid.uuid4().hex}})
        state = read_state(client, session)
        batch_id = "gui-loss-batch-" + uuid.uuid4().hex
        batch = {"op": "run_script", "request_id": batch_id, "document_id": state["document_id"],
                 "revision": state["revision"],
                 "commands": [f"LINE {n},0 {n},10" for n in range(60)]}
        metadata = {"io.modelcontextprotocol/protocolVersion": MODERN,
                    "io.modelcontextprotocol/clientCapabilities": {}}
        initial = client.rpc("tools/call", {"name": "ocs_execute",
            "arguments": {"ocs_session_id": session, "request": batch, "wait_seconds": 0},
            "_meta": metadata})["structuredContent"]
        report["initial"] = {key: initial.get(key) for key in
                             ("status", "completed_commands", "request_id")}
        if initial.get("status") != "running":
            raise ProtocolError("Synthetic batch did not enter running state")
        journal_dir = profile / "OpenCADStudio" / "automation" / "batch-journal"
        journals = list(journal_dir.glob("*.json"))
        if len(journals) != 1:
            raise ProtocolError("Expected one durable journal before GUI loss")
        report["journal_sha256_before_loss"] = hashlib.sha256(journals[0].read_bytes()).hexdigest().upper()

        # This is the only intentional process kill: PID is the Popen child above.
        gui.kill()
        gui.wait(timeout=10)
        report["gui_exit_code"] = gui.returncode
        calls_before = client.tool_calls
        try:
            client.recover(session, batch_id, deadline=time.monotonic() + 12)
        except (ToolError, UncertainMutation, ProtocolError) as exc:
            report["recovery_error_type"] = type(exc).__name__
            if isinstance(exc, ToolError):
                report["recovery_code"] = exc.result.get("code")
        else:
            raise ProtocolError("GUI loss was incorrectly reported as a successful recovery")
        report["recovery_tool_calls"] = client.tool_calls - calls_before
        if report["recovery_tool_calls"] != 1:
            raise ProtocolError("Recovery must only query the operation once after confirmed GUI loss")
        try:
            client.mutate(session, {"op": "run", "request_id": "gui-loss-next-" + uuid.uuid4().hex,
                                    "cmd": "LINE 100,0 100,10", "document_id": state["document_id"],
                                    "revision": state["revision"]})
        except UncertainMutation:
            report["new_mutation_blocked"] = True
        else:
            raise ProtocolError("New mutation was not blocked after unreconciled GUI loss")
        if client.tool_calls != calls_before + 1:
            raise ProtocolError("Blocked mutation unexpectedly reached the MCP server")
        report["status"] = "passed_fail_closed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
        raise
    finally:
        if gui.poll() is None:
            gui.kill()
            gui.wait(timeout=10)
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        report["gui_exited"] = gui.poll() is not None
        (run / "gui-loss-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
