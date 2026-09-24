"""Request graceful close for an identified synthetic GUI session only."""

import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, ToolError


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    base = (repo / "target/mcp-isolated").resolve()
    run = Path(sys.argv[1]).resolve()
    expected_pid = int(sys.argv[2])
    if not run.is_relative_to(base) or run == base or not (run / "profile").is_dir():
        raise ValueError("Expected one run under target/mcp-isolated")
    server = (repo / "target/debug/OpenCADStudio.exe").resolve()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(run / "profile"), "LOCALAPPDATA": str(run / "profile"),
                        "TEMP": str(run / "temp"), "TMP": str(run / "temp")})
    client = Client(server, environment=environment)
    report = {"schema_version": "mcp-isolated-cleanup-1", "run": str(run),
              "expected_pid": expected_pid, "status": "failed"}
    try:
        state = client.ready_session(launch_if_none=False)
        if state.get("process_id") != expected_pid or Path(state["executable_path"]).resolve() != server:
            raise ProtocolError("GUI identity differs from expected process")
        session = state["session_id"]
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "cleanup-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if state.get("modal"):
            report["status"] = "waiting_user_modal"
            return
        if any(d.get("dirty") or (d.get("path") and not Path(d["path"]).resolve().is_relative_to(run))
               for d in state["documents"]):
            report["status"] = "waiting_user_document"
            return
        try:
            result = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "cleanup-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
            report["status"] = "quit_requested" if result.get("status") == "completed" else "quit_unconfirmed"
        except ToolError as error:
            report["status"] = "quit_rejected"
            report["code"] = error.result.get("code")
        except ProtocolError:
            report["status"] = "quit_response_lost"
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        (run / "cleanup.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
