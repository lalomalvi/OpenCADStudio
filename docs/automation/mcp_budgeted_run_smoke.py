"""L2 budget pause/resume against an isolated OpenCADStudio GUI and MCP restart."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_budgeted_run import BudgetedRun
from mcp_client import Client, ProtocolError, UncertainMutation
from mcp_isolated_smoke import read_state


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    repo = Path(__file__).resolve().parents[2]
    output = repo / "target" / "mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                                  "-budget-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"
    profile.mkdir()
    temporary = output / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-budgeted-run-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "output": str(output)}
    gui = subprocess.Popen([str(server), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(server, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        session = selected["session_id"]
        if selected.get("process_id") != gui.pid or Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("Isolated GUI identity differs from launched process")
        report["session"] = {"id": session, "pid": gui.pid}
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "budget-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Isolated GUI still has a startup modal")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "budget-new-" + uuid.uuid4().hex}})
        commands = ["LINE 10,0 11,0", "LINE 11,0 12,0"]
        checkpoint = output / "checkpoint.jsonl"
        run_id = "budget-" + uuid.uuid4().hex[:12]
        paused = BudgetedRun(client, session, commands, checkpoint, run_id).run(
            max_steps=1, max_elapsed_seconds=30)
        if paused != {"status": "paused", "next_step": 1,
                      "completed_steps": 1, "total_steps": 2}:
            raise ProtocolError("Budget did not pause after one command")
        report["paused"] = paused
        client.close()
        client = Client(server, environment=environment)
        client.handshake()
        completed = BudgetedRun(client, session, commands, checkpoint, run_id).run(
            max_steps=1, max_elapsed_seconds=30)
        if completed != {"status": "completed", "next_step": 2,
                         "completed_steps": 2, "total_steps": 2}:
            raise ProtocolError("Checkpoint did not resume after MCP restart")
        report["resumed"] = completed
        found = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                         "parameters": {"type": "Line", "detail": "full"}})
        lines = found.get("entities", [])
        endpoints = sorted((line.get("start"), line.get("end")) for line in lines)
        if len(lines) != 2 or endpoints != sorted([([10.0, 0.0, 0.0], [11.0, 0.0, 0.0]),
                                                    ([11.0, 0.0, 0.0], [12.0, 0.0, 0.0])]):
            raise ProtocolError("Resumed fixture has duplicated or missing lines")
        report["line_count"] = len(lines)
        report["checkpoint_sha256"] = hashlib.sha256(checkpoint.read_bytes()).hexdigest().upper()
        saved_path = output / "budgeted.dwg"
        saved = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save_verified", "request_id": "budget-save-" + uuid.uuid4().hex,
                        "path": str(saved_path), "target_format": "dwg", "target_version": "2018"}})
        result = saved.get("result", saved)
        if result.get("verified") is not True or result.get("manifest", {}).get("by_type", {}).get("Line") != 2:
            raise ProtocolError("Resumed synthetic drawing did not save/reopen")
        report["dwg_sha256"] = hashlib.sha256(saved_path.read_bytes()).hexdigest().upper()
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "budget-clean-" + uuid.uuid4().hex,
                        "path": str(output / "session-clean.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "budget-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=10)
        report["status"] = "passed"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        client.close()
        report["gui_exited"] = gui.poll() is not None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
