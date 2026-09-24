"""Isolated synthetic L2 proof of a midpoint dimension on two wall faces."""

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


def request(client, session, op, **fields):
    return client.tool("ocs_execute", {"ocs_session_id": session,
        "request": {"op": op, "request_id": "face-" + uuid.uuid4().hex, **fields}})


def dimension(client, session, handle):
    result = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
        "parameters": {"handle": handle, "detail": "full"}})
    entity = result.get("entities", [{}])[0]
    value = entity.get("properties", {}).get("Linear", {}).get("base", {}).get("actual_measurement")
    if entity.get("type") != "Dimension" or not isinstance(value, (int, float)):
        raise ProtocolError("Face dimension is absent or unmeasured")
    return value


def save_verified(client, session, path):
    response = request(client, session, "save_verified", path=str(path),
                       target_format="dwg", target_version="2018")
    result = response.get("result", response)
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if result.get("verified") is not True or result.get("sha256", "").upper() != digest:
        raise ProtocolError("Face dimension DWG did not verify")
    return {"path": str(path), "sha256": digest, "manifest": result.get("manifest")}


def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    fixture = repo / "docs/automation/masterplan/fixtures/synthetic-wall-face-dimension.planspec.json"
    plan = json.loads(fixture.read_text(encoding="utf-8"))
    if (plan["schema_version"] != "planspec-6" or len(plan["walls"]) != 1 or
            len(plan["dimension_bindings"]) != 1 or len(plan["dimensions"]) != 1 or
            plan["openings"] or plan["joins"]):
        raise ProtocolError("Unexpected face dimension fixture")
    output = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                               "-face-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile, temporary = output / "profile", output / "temp"
    profile.mkdir(); temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-face-dimension-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest().upper(),
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
            request(client, session, "action", name="close_modal")
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Isolated GUI still has a startup modal")
        request(client, session, "new")
        commands = ["SETVAR INSUNITS 6", "LINE 0,0.1 4,0.1",
                    "LINE 0,-0.1 4,-0.1", "DIMLINEAR 2,0.1 2,-0.1 2.5,0"]
        created = request(client, session, "run_script", strict=True, commands=commands)
        added = {change["step"]: change["handle"] for change in created.get("changes", [])
                 if change.get("kind") == "Added"}
        if created.get("completed_commands") != 4 or len(added) != 3:
            raise ProtocolError("Face source lines or native dimension were not created")
        upper, lower, dim = added[1], added[2], added[3]
        initial = dimension(client, session, dim)
        if abs(initial - 0.2) > 1e-6:
            raise ProtocolError("Initial face thickness differs from fixture")
        first = save_verified(client, session, output / "before-edit.dwg")
        request(client, session, "save", path=str(output / "session-before.dwg"),
                target_format="dwg", target_version="2018")
        request(client, session, "open", path=first["path"])
        reopened = dimension(client, session, dim)
        if abs(reopened - 0.2) > 1e-6:
            raise ProtocolError("Face dimension changed on DWG reopen")
        request(client, session, "set_properties", collection="entities", handle=upper,
                updates=[{"path": "/start/y", "expected": 0.1, "value": 0.15},
                         {"path": "/end/y", "expected": 0.1, "value": 0.15}])
        edited = dimension(client, session, dim)
        if abs(edited - 0.25) > 1e-6:
            raise ProtocolError("Face dimension did not follow edited source line")
        second = save_verified(client, session, output / "after-edit.dwg")
        if first["manifest"] != second["manifest"]:
            raise ProtocolError("Face dimension DWG manifest changed after edit")
        report.update({"status": "passed", "handles": {"upper": upper, "lower": lower,
                       "dimension": dim}, "measurements_m": {"initial": initial,
                       "reopened": reopened, "edited": edited},
                       "association": {"dimension_handle": dim,
                                       "edited_measurement": edited},
                       "first_save": first, "second_save": second})
        request(client, session, "save", path=str(output / "session-after.dwg"),
                target_format="dwg", target_version="2018")
        try:
            request(client, session, "run", cmd="QUIT")
        except (ProtocolError, UncertainMutation):
            pass
        gui.wait(timeout=10)
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        raise
    finally:
        client.close()
        report["gui_exited"] = gui.poll() is not None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
