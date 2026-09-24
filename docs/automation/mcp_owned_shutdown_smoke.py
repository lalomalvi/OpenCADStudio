"""L2 owned lifecycle: launch and close only a fresh synthetic GUI profile."""

import json
import os
from pathlib import Path
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, ToolError
from mcp_isolated_smoke import read_state


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    run = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") + "-owned-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    profile = run / "profile"
    temporary = run / "temp"
    profile.mkdir()
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-owned-shutdown-l2-1", "status": "failed", "run": str(run)}
    client = Client(server, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(launch_if_none=True, timeout=90)
        session = selected["session_id"]
        report["session"] = {"id": session, "pid": selected.get("process_id"),
                             "started_at_unix_ms": selected.get("process_started_at_unix_ms")}
        if selected.get("executable_path") != str(server):
            raise ProtocolError("Owned GUI executable differs from tested build")
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "owned-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal") or any(document.get("dirty") for document in state["documents"]):
            raise ProtocolError("Owned GUI is not clean after startup")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "owned-new-" + uuid.uuid4().hex}})
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run", "request_id": "owned-line-" + uuid.uuid4().hex,
                        "cmd": "LINE 0,0 1,0"}})
        request = {"op": "shutdown_owned_session", "request_id": "owned-close-" + uuid.uuid4().hex,
                   "owned_root": str(run), "process_id": selected["process_id"],
                   "process_started_at_unix_ms": selected["process_started_at_unix_ms"],
                   "executable_path": selected["executable_path"]}
        close_request = {**request, "op": "close_document", "policy": "require_saved",
                         "request_id": "owned-close-document-" + uuid.uuid4().hex}
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                                        "request": {**close_request, "request_id": "owned-close-dirty-" + uuid.uuid4().hex}})
        except ToolError as error:
            if error.result.get("code") != "dirty_document":
                raise
            report["close_dirty_refused"] = True
        else:
            raise ProtocolError("Close did not refuse a dirty document")
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                                        "request": {**request, "request_id": "owned-dirty-" + uuid.uuid4().hex}})
        except ToolError as error:
            if error.result.get("code") != "dirty_document":
                raise
            report["dirty_refused"] = True
        else:
            raise ProtocolError("Shutdown did not refuse a dirty document")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "owned-save-" + uuid.uuid4().hex,
                        "path": str(run / "owned-synthetic.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                                        "request": {**request, "request_id": "owned-foreign-" + uuid.uuid4().hex,
                                                    "owned_root": str(profile)}})
        except ToolError as error:
            if error.result.get("code") != "foreign_document":
                raise
            report["foreign_refused"] = True
        else:
            raise ProtocolError("Shutdown did not refuse a foreign document")
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                                        "request": {**close_request, "request_id": "owned-close-foreign-" + uuid.uuid4().hex,
                                                    "owned_root": str(profile)}})
        except ToolError as error:
            if error.result.get("code") != "foreign_document":
                raise
            report["close_foreign_refused"] = True
        else:
            raise ProtocolError("Close did not refuse a foreign document")
        document_to_close = read_state(client, session)["document_id"]
        closed_document = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": close_request})
        after_close = read_state(client, session)
        if (closed_document.get("status") != "completed" or
                any(doc["id"] == document_to_close for doc in after_close["documents"])):
            raise ProtocolError("Owned synthetic document did not close")
        report["document_closed"] = document_to_close
        result = client.tool("ocs_execute", {"ocs_session_id": session, "request": request})
        if result.get("status") != "completed" or result.get("result", {}).get("closed") is not True:
            raise ProtocolError("Owned GUI did not close")
        repeat = client._tool_raw("ocs_execute", {"ocs_session_id": session, "request": request})
        if repeat != result:
            raise ProtocolError("Repeated shutdown request did not return the same outcome")
        discovery = client.tool("ocs_sessions", {"launch_if_none": False})
        if discovery.get("status") != "absent" or discovery.get("result"):
            raise ProtocolError("Owned GUI remains discoverable after shutdown")
        report["status"] = "passed"
        report["closed_pid"] = selected["process_id"]
        report["repeat_same_result"] = True
        report["discovery_after"] = "absent"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        (run / "owned-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
