"""Save one owned synthetic dirty tab after a failed isolated lifecycle run."""

import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp_client import Client, ProtocolError
from mcp_isolated_smoke import read_state


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    base = (repo / "target/mcp-isolated").resolve()
    run = Path(sys.argv[1]).resolve()
    expected_pid = int(sys.argv[2])
    if run == base or not run.is_relative_to(base) or not (run / "profile").is_dir():
        raise ValueError("Expected one isolated run under target/mcp-isolated")
    server = (repo / "target/debug/OpenCADStudio.exe").resolve()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(run / "profile"), "LOCALAPPDATA": str(run / "profile"),
                        "TEMP": str(run / "temp"), "TMP": str(run / "temp")})
    client = Client(server, environment=environment)
    report = {"schema_version": "mcp-isolated-recovery-1", "run": str(run),
              "expected_pid": expected_pid, "status": "failed"}
    try:
        selected = client.ready_session(launch_if_none=False)
        if selected.get("process_id") != expected_pid or Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("GUI identity differs from expected synthetic process")
        session = selected["session_id"]
        state = read_state(client, session)
        if state.get("modal") or state.get("command"):
            raise ProtocolError("GUI has a modal or active command")
        documents = state["documents"]
        if sum(bool(doc.get("dirty")) for doc in documents) != 1:
            raise ProtocolError("Expected exactly one dirty synthetic tab")
        for document in documents:
            if document.get("path") and not Path(document["path"]).resolve().is_relative_to(run):
                raise ProtocolError("Foreign document path; stop")
        if not any(doc["id"] == state["document_id"] and doc["dirty"] for doc in documents):
            raise ProtocolError("Dirty synthetic tab is not active")
        destination = run / "recovered-synthetic.dwg"
        if destination.exists():
            raise ProtocolError("Recovery destination already exists")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "recover-save-" + uuid.uuid4().hex,
                        "path": str(destination), "target_format": "dwg", "target_version": "2018"}})
        state = read_state(client, session)
        if any(doc.get("dirty") for doc in state["documents"]):
            raise ProtocolError("Synthetic tab remains dirty")
        report["saved_synthetic"] = str(destination)
        try:
            result = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "recover-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
            report["quit_status"] = result.get("status")
        except ProtocolError:
            report["quit_status"] = "reply_lost"
        report["status"] = "save_complete_quit_requested"
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        (run / "recovery.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
