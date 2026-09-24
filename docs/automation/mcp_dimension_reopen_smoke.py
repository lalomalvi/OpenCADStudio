"""Synthetic L2 proof that a dimension remains linked after DWG reopening.

Uses a fresh workspace-local profile. A failed run is preserved for controlled
recovery; it never kills a GUI process merely because a Python call failed.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, UncertainMutation
from mcp_isolated_smoke import read_state


def measure(client: Client, session: str, handle: str) -> float:
    result = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                      "parameters": {"handle": handle, "detail": "full"}})
    entity = result.get("entities", [{}])[0]
    value = (entity.get("properties", {}).get("Linear", {}).get("base", {})
             .get("actual_measurement"))
    if entity.get("type") != "Dimension" or not isinstance(value, (int, float)):
        raise ProtocolError("Synthetic dimension is absent or unmeasured")
    return value


def verified_save(client: Client, session: str, path: Path) -> dict:
    response = client.tool("ocs_execute", {"ocs_session_id": session,
        "request": {"op": "save_verified", "request_id": "assoc-save-" + uuid.uuid4().hex,
                    "path": str(path), "target_format": "dwg", "target_version": "2018"}})
    result = response.get("result", response)
    if result.get("verified") is not True or not path.is_file():
        raise ProtocolError("Synthetic associative drawing did not save and reopen")
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if result.get("sha256", "").upper() != digest:
        raise ProtocolError("Synthetic associative DWG hash differs from backend")
    return {"file": path.name, "sha256": digest, "bytes": path.stat().st_size,
            "manifest": result.get("manifest")}


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    repo = Path(__file__).resolve().parents[2]
    output = repo / "target" / "mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                                  "-assoc-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"
    profile.mkdir()
    temporary = output / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-dimension-reopen-l2-1", "status": "failed",
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
        report["session"] = {"id": session, "pid": gui.pid,
                             "started_at_unix_ms": selected.get("process_started_at_unix_ms")}
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "assoc-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Isolated GUI still has a startup modal")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "assoc-new-" + uuid.uuid4().hex}})
        created = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run_script", "request_id": "assoc-create-" + uuid.uuid4().hex,
                        "strict": True, "commands": ["LINE 70,0 72.5,0",
                                                      "DIMLINEAR 70,0 72.5,0 71.25,1"]}})
        handles = [change["handle"] for change in created.get("changes", [])
                   if change.get("kind") == "Added"]
        if created.get("completed_commands") != 2 or len(handles) != 2:
            raise ProtocolError("Synthetic line/dimension handles were not created")
        line, dimension = handles
        initial = measure(client, session, dimension)
        if abs(initial - 2.5) > 1e-6:
            raise ProtocolError("Initial synthetic dimension is not 2.50")
        first = output / "before-reopen.dwg"
        report["first_save"] = verified_save(client, session, first)
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "assoc-clean-" + uuid.uuid4().hex,
                        "path": str(output / "session-before.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "open", "request_id": "assoc-open-" + uuid.uuid4().hex,
                        "path": str(first)}})
        reopened_measure = measure(client, session, dimension)
        if abs(reopened_measure - 2.5) > 1e-6:
            raise ProtocolError("Dimension measure changed on first DWG reopen")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "set_properties", "request_id": "assoc-edit-" + uuid.uuid4().hex,
                        "collection": "entities", "handle": line,
                        "updates": [{"path": "/end/x", "expected": 72.5, "value": 73.5}]}})
        edited_measure = measure(client, session, dimension)
        report["association"] = {"line_handle": line, "dimension_handle": dimension,
                                 "initial_measurement": initial,
                                 "reopened_measurement": reopened_measure,
                                 "edited_measurement": edited_measure}
        if abs(edited_measure - 3.5) > 1e-6:
            raise ProtocolError("Dimension lost source linkage after DWG reopen")
        second = output / "after-reopen.dwg"
        report["second_save"] = verified_save(client, session, second)
        if report["second_save"]["manifest"] != report["first_save"]["manifest"]:
            raise ProtocolError("Edited dimension left stale generated geometry in saved DWG")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "assoc-final-clean-" + uuid.uuid4().hex,
                        "path": str(output / "session-after.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "assoc-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=10)
        report["status"] = "passed"
        report["shutdown"] = "exited"
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
