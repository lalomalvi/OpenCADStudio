"""L2 owned lifecycle: launch and close only a fresh synthetic GUI profile."""

import hashlib
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
    trace_path = run / "rpc-trace.jsonl"
    client = Client(server, environment=environment, trace_path=trace_path, run_id=run.name)
    try:
        client.handshake()
        selected = client.ready_session(launch_if_none=True, timeout=90)
        session = selected["session_id"]
        report["session"] = {"id": session, "pid": selected.get("process_id"),
                             "started_at_unix_ms": selected.get("process_started_at_unix_ms")}
        if selected.get("executable_path") != str(server):
            raise ProtocolError("Owned GUI executable differs from tested build")
        catalog = client.tool("ocs_read", {"ocs_session_id": session, "op": "commands",
                                           "parameters": {"limit": 1000}})
        available = set(catalog.get("commands", []))
        requested = ("ARC", "PLINE", "DIMLINEAR", "DIMALIGNED", "BLOCK", "INSERT",
                     "HATCH", "LAYER", "CLAYER", "PSETUPIN")
        report["capability_census"] = {
            "registered_count": catalog.get("count"),
            "commands_sha256": hashlib.sha256("\n".join(sorted(available)).encode()).hexdigest(),
            "candidates": {name: {"registered": name in available} for name in requested},
        }
        if catalog.get("count") != len(available):
            raise ProtocolError("Command catalog was truncated")
        time.sleep(2.2)
        live = client.ready_session(session_id=session, wait_for_existing=True, timeout=10)
        if live.get("heartbeat_age_ms") is None or live["heartbeat_age_ms"] > 5000:
            raise ProtocolError("Owned GUI heartbeat is absent or stale")
        if os.name == "nt" and live.get("process_identity") != "matched":
            raise ProtocolError("Windows process creation time did not match descriptor")
        report["heartbeat_age_ms"] = live["heartbeat_age_ms"]
        report["process_identity"] = live.get("process_identity")
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
        quarantine = profile / "OpenCADStudio" / "automation" / "quarantine"
        report["quarantined_descriptor_count"] = len(list(quarantine.glob("*.json"))) if quarantine.is_dir() else 0
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        trace_text = trace_path.read_text(encoding="utf-8")
        report["rpc_trace"] = {"events": len(trace_text.splitlines()),
                               "write_failed": client.trace.failed,
                               "contains_token_field": '"token"' in trace_text}
        if report["status"] == "passed" and (client.trace.failed or '"token"' in trace_text
                                                or not trace_text):
            report["status"] = "partial"
        (run / "owned-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
