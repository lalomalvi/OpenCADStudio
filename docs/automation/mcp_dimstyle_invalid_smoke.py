"""L2 rejection probe for integer DIMSTYLE fields on an owned synthetic GUI."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from mcp_isolated_smoke import read_state


CASES = (
    "DIMSTYLE SET Standard dimdec -1",
    "DIMSTYLE SET Standard dimdec 1.5",
    "DIMSTYLE SET Standard dimdec 9",
    "DIMSTYLE SET Standard dimzin -1",
    "DIMSTYLE SET Standard dimzin 2.5",
    "DIMSTYLE SET Standard dimzin 16",
)


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    binary = Path(sys.argv[1] if len(sys.argv) > 1 else
                  repo / "target/debug/OpenCADStudio.exe").resolve(strict=True)
    run = repo / "target/mcp-isolated" / ("dimstyle-invalid-" + uuid.uuid4().hex[:8])
    run.mkdir(parents=True, exist_ok=False)
    profile, temporary = run / "profile", run / "temp"
    profile.mkdir()
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    gui = subprocess.Popen([str(binary), "--new-instance"], cwd=repo,
                           env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    report = {"schema_version": "mcp-dimstyle-invalid-l2-1",
              "status": "failed", "pid": gui.pid,
              "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest().upper(),
              "cases": []}
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected["process_id"] != gui.pid:
            raise ProtocolError("Owned GUI identity differs")
        session = selected["session_id"]
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "action", "name": "close_modal",
                            "request_id": "style-modal-" + uuid.uuid4().hex}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Owned GUI startup modal remains")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "style-new-" + uuid.uuid4().hex}})
        for command in CASES:
            before = read_state(client, session)
            try:
                result = client.tool("ocs_execute", {"ocs_session_id": session,
                    "request": {"op": "run", "cmd": command,
                                "request_id": "style-negative-" + uuid.uuid4().hex}})
            except ToolError as error:
                result = error.result
            after = read_state(client, session)
            report["cases"].append({"command": command,
                                    "result": result,
                                    "revision_before": before["revision"],
                                    "revision_after": after["revision"],
                                    "geometry_revision_before": before["geometry_revision"],
                                    "geometry_revision_after": after["geometry_revision"]})
        if not all(item["result"].get("ok") is False and
                   item["result"].get("error") ==
                   "DIMSTYLE: invalid integer property value" and
                   item["result"].get("changes") == [] and
                   item["revision_before"] == item["revision_after"] and
                   item["geometry_revision_before"] ==
                   item["geometry_revision_after"]
                   for item in report["cases"]):
            raise ProtocolError("Invalid DIMSTYLE command changed the document")
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "cmd": "QUIT",
                            "request_id": "style-quit-" + uuid.uuid4().hex}})
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=30)
        report["status"] = "passed"
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error_message"] = str(error)[:300]
        raise
    finally:
        client.close()
        if gui.poll() is None:
            gui.terminate()  # only the owned child, never an existing GUI
            gui.wait(timeout=10)
            report["cleanup"] = "terminated_owned_child"
        report["gui_exited"] = gui.poll() is not None
        with (run / "report.json").open("x", encoding="utf-8") as target:
            json.dump(report, target, sort_keys=True, indent=2)
            target.write("\n")
        print(json.dumps({"report": str(run / "report.json"),
                          "status": report["status"],
                          "rejected_without_revision": len(report["cases"]),
                          "gui_exited": report["gui_exited"]}))


if __name__ == "__main__":
    main()
