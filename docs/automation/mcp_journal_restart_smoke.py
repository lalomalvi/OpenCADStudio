"""L2 synthetic batch recovery after intentionally restarting only MCP stdio."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, MODERN, ProtocolError
from mcp_isolated_smoke import read_state


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    run = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") + "-journal-" + uuid.uuid4().hex[:8])
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
    report = {"schema_version": "mcp-journal-restart-l2-1", "status": "failed",
              "run": str(run), "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "gui_pid": gui.pid}
    first = Client(server, environment=environment)
    second = None
    first_closed = False
    try:
        first.handshake()
        selected = first.ready_session(wait_for_existing=True, timeout=90)
        session = selected["session_id"]
        if selected.get("process_id") != gui.pid or Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("Discovered GUI is not the synthetic child")
        report["session_id"] = session
        state = read_state(first, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            first.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "journal-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(first, session)
        if state.get("modal"):
            raise ProtocolError("Startup modal remains")
        first.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "journal-new-" + uuid.uuid4().hex}})
        state = read_state(first, session)
        batch_id = "journal-batch-" + uuid.uuid4().hex
        batch = {"op": "run_script", "request_id": batch_id,
                 "document_id": state["document_id"], "revision": state["revision"],
                 "commands": ["LINE 0,0 10,0", "LINE 10,0 10,10", "CIRCLE 5,5 2"]}
        # A modern request without the Tasks extension returns the first
        # bounded batch response instead of polling it to completion.
        metadata = {"io.modelcontextprotocol/protocolVersion": MODERN,
                    "io.modelcontextprotocol/clientCapabilities": {}}
        initial = first.rpc("tools/call", {"name": "ocs_execute",
            "arguments": {"ocs_session_id": session, "request": batch, "wait_seconds": 0},
            "_meta": metadata})["structuredContent"]
        report["initial"] = {key: initial.get(key) for key in
                             ("status", "code", "error", "completed_commands")}
        if initial.get("status") != "running" or initial.get("completed_commands") not in {0, 1}:
            raise ProtocolError("Initial batch did not stop with recoverable progress")
        report["completed_before_restart"] = initial["completed_commands"]
        journal_dir = profile / "OpenCADStudio" / "automation" / "batch-journal"
        if len(list(journal_dir.glob("*.json"))) != 1:
            raise ProtocolError("Expected exactly one durable batch journal")
        first.close()
        first_closed = True
        second = Client(server, environment=environment)
        second.handshake()
        same = second.ready_session(session_id=session, launch_if_none=False)
        if same.get("process_id") != gui.pid:
            raise ProtocolError("GUI identity changed across MCP restart")
        recovered = second.recover(session, batch_id)
        if recovered.get("completed_commands") != 3 or recovered.get("added_entities") != 3:
            raise ProtocolError("Recovery did not finish exactly three synthetic entities")
        report["completed_after_restart"] = recovered["completed_commands"]
        report["added_entities"] = recovered["added_entities"]
        destination = run / "journal-verified.dwg"
        saved = second.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save_verified", "request_id": "journal-save-" + uuid.uuid4().hex,
                        "path": str(destination), "target_format": "dwg", "target_version": "2018"}})
        verified = saved.get("result", saved)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
        if verified.get("verified") is not True or verified.get("sha256", "").upper() != digest:
            raise ProtocolError("Recovered synthetic DWG failed verified save")
        report["verified_output"] = {"path": str(destination), "sha256": digest,
                                     "bytes": destination.stat().st_size}
        second.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "journal-clean-save-" + uuid.uuid4().hex,
                        "path": str(run / "journal-session.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        state = read_state(second, session)
        if any(doc.get("dirty") for doc in state["documents"]):
            raise ProtocolError("Synthetic document remains dirty")
        try:
            second.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "journal-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
        except ProtocolError:
            pass
        gui.wait(timeout=10)
        report["status"] = "passed"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        if second is not None:
            try:
                second.close()
            except ProtocolError:
                report["second_mcp_close"] = "error"
        elif not first_closed:
            try:
                first.close()
            except ProtocolError:
                report["first_mcp_close"] = "error"
        report["gui_exited"] = gui.poll() is not None
        (run / "journal-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
