"""L2 synthetic MCP smoke in a new, workspace-local OCS profile.

Creates only synthetic geometry. Never discovers the normal user profile.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from masterplan.planspec import dry_run


def read_state(client: Client, session: str, *, timeout: float = 10.0) -> dict:
    """A cold GUI can briefly miss a bounded descriptor probe; retry reads only."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        except ToolError as exc:
            transient = ("matching sessions", "Selected session handshake", "Selected session descriptor")
            if (exc.result.get("code") != "invalid_arguments" or
                    not any(item in exc.result.get("error", "") for item in transient) or
                    time.monotonic() >= deadline):
                raise
            time.sleep(0.2)


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    repo = Path(__file__).resolve().parents[2]
    output = repo / "target" / "mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"
    profile.mkdir()
    temporary = output / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    # Child-only profile override. No real AppData or global environment changes.
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-isolated-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "output": str(output)}
    fixture = Path(__file__).resolve().parent / "masterplan/fixtures/synthetic-room.planspec.json"
    compiled = dry_run(json.loads(fixture.read_text(encoding="utf-8")))
    if not compiled["executable"] or len(compiled["commands"]) != 3:
        raise ProtocolError("Synthetic PlanSpec has unsupported or missing commands")
    report["planspec"] = {"fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                          "commands_sha256": compiled["commands_sha256"],
                          "command_count": len(compiled["commands"])}
    gui = subprocess.Popen([str(server), "--new-instance"], cwd=repo, env=environment,
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
    client = Client(server, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        session = selected["session_id"]
        if selected.get("process_id") != gui.pid:
            raise ProtocolError("Discovered session does not belong to the launched GUI")
        if Path(selected["executable_path"]).resolve() != server:
            raise ProtocolError("Discovered executable differs from tested build")
        report["session"] = {"id": session, "pid": gui.pid,
                             "started_at_unix_ms": selected.get("process_started_at_unix_ms")}

        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "request_id": "l2-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Isolated GUI still has a startup modal")

        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "l2-new-" + uuid.uuid4().hex}})
        state = read_state(client, session)
        if not isinstance(state.get("document_id"), int):
            raise ProtocolError("New synthetic document was not activated")
        script = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run_script", "request_id": "l2-script-" + uuid.uuid4().hex,
                        "strict": True,
                        "commands": [item["command"] for item in compiled["commands"]]}})
        if script.get("completed_commands") != 3 or script.get("added_entities") != 3:
            raise ProtocolError("Synthetic script did not create three entities")
        handles = {}
        for step, item in enumerate(compiled["commands"]):
            created = [change["handle"] for change in script.get("changes", [])
                       if change.get("step") == step and change.get("kind") == "Added"
                       and isinstance(change.get("handle"), str)]
            if len(created) != 1:
                raise ProtocolError("PlanSpec command did not map to exactly one new handle")
            handles[item["planspec_id"]] = created[0]
        if len(set(handles.values())) != len(handles):
            raise ProtocolError("PlanSpec handles are not unique")
        report["planspec"]["handles_by_id"] = handles
        audit = client.tool("ocs_read", {"ocs_session_id": session, "op": "audit",
                                         "parameters": {"target_format": "dwg", "target_version": "2018"}})
        if audit.get("ok") is not True:
            raise ProtocolError("Synthetic DWG audit failed")
        destination = output / "synthetic-verified.dwg"
        saved = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save_verified", "request_id": "l2-save-" + uuid.uuid4().hex,
                        "path": str(destination), "target_format": "dwg", "target_version": "2018"}})
        verified = saved.get("result", saved)
        if verified.get("verified") is not True or not destination.is_file():
            raise ProtocolError("Synthetic verified save failed")
        actual_hash = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
        if verified["sha256"].upper() != actual_hash:
            raise ProtocolError("Synthetic output hash differs from backend report")
        report.update({"status": "passed", "script": {"completed_commands": 3,
                                                      "added_entities": 3},
                       "audit_ok": True,
                       "verified_output": {"path": str(destination), "sha256": actual_hash,
                                           "bytes": destination.stat().st_size}})

        # Save the working tab separately so QUIT cannot discard unsaved work.
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "l2-clean-save-" + uuid.uuid4().hex,
                        "path": str(output / "synthetic-session.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        if any(document.get("dirty") for document in state["documents"]):
            report["shutdown"] = "waiting_user_dirty_document"
            return
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "l2-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}}, deadline=time.monotonic() + 5)
        except (ProtocolError, UncertainMutation):
            pass  # Process exit, checked independently below.
        try:
            gui.wait(timeout=10)
            report["shutdown"] = "exited"
        except subprocess.TimeoutExpired:
            report["shutdown"] = "waiting_user_or_unclosed"
    except Exception as error:
        report["error_type"] = type(error).__name__
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        report["gui_exited"] = gui.poll() is not None
        if report["status"] == "passed" and not report["gui_exited"]:
            report["status"] = "partial"
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
