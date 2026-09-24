"""L2 synthetic proof of guarded associative wall length edits."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from mcp_face_dimension_smoke import request, save_verified
from mcp_isolated_smoke import read_state
from mcp_wall_thickness_smoke import same_wall_geometry
from masterplan.planspec import dry_run


FIXTURES = {
    "synthetic-wall-axis-endpoints-v9.planspec.json": (4.0, 4.5),
    "synthetic-wall-aligned-endpoints-v9.planspec.json": (5.0, 5.5),
}


def dimension(client, session, handle):
    result = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
        "parameters": {"handle": handle, "detail": "full"}})
    entity = result.get("entities", [{}])[0]
    properties = entity.get("properties", {})
    value = next((properties[kind]["base"].get("actual_measurement")
                  for kind in ("Linear", "Aligned") if kind in properties), None)
    if entity.get("type") != "Dimension" or not isinstance(value, (int, float)):
        raise ProtocolError("Axis dimension is absent or unmeasured")
    return value


def wall_edges(client, session, handles):
    points = []
    for handle in handles:
        result = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
            "parameters": {"handle": handle, "detail": "full"}})
        entity = result.get("entities", [{}])[0]
        if entity.get("type") != "Line":
            raise ProtocolError("Wall edge is not a LINE")
        points.append((entity["start"], entity["end"]))
    for index in range(4):
        if any(abs(points[index][1][axis] - points[(index + 1) % 4][0][axis]) > 1e-6
               for axis in range(3)):
            raise ProtocolError("Wall outline is open")
    a, b = points[0]
    c = points[1][1]
    length = sum((b[axis] - a[axis]) ** 2 for axis in range(3)) ** 0.5
    thickness = sum((c[axis] - b[axis]) ** 2 for axis in range(3)) ** 0.5
    return {"closed": True, "length_m": length, "thickness_m": thickness,
            "points": [[item[0], item[1]] for item in points]}


def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    fixture_name = sys.argv[2] if len(sys.argv) > 2 else next(iter(FIXTURES))
    if fixture_name not in FIXTURES or not server.is_file():
        raise ValueError("Expected a v9 synthetic fixture and built server")
    initial, edited_length = FIXTURES[fixture_name]
    fixture = repo / "docs/automation/masterplan/fixtures" / fixture_name
    plan = json.loads(fixture.read_text(encoding="utf-8"))
    compiled = dry_run(plan)
    if not compiled["executable"] or len(compiled["execution_steps"]) != 14:
        raise ProtocolError("Fixture did not compile to four edges and one dimension")
    output = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                               "-wall-length-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile, temporary = output / "profile", output / "temp"
    profile.mkdir(); temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-wall-length-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "planspec": {"fixture": fixture_name,
                           "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest().upper(),
                           "commands_sha256": compiled["commands_sha256"],
                           "dimension_style": plan["dimension_style"]},
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
            raise ProtocolError("Isolated GUI identity differs")
        report["session"] = {"id": session, "pid": gui.pid}
        state = read_state(client, session)
        for _ in range(6):
            if not state.get("modal"):
                break
            request(client, session, "action", name="close_modal")
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Startup modal remains")
        request(client, session, "new")
        commands = [step["command"] for step in compiled["execution_steps"]]
        created = request(client, session, "run_script", strict=True, commands=commands)
        added = {change["step"]: change["handle"] for change in created.get("changes", [])
                 if change.get("kind") == "Added"}
        if created.get("completed_commands") != len(commands) or len(added) != 5:
            raise ProtocolError("Expected exactly five created entities")
        handles = {step["planspec_id"]: added[index]
                   for index, step in enumerate(compiled["execution_steps"])
                   if step["planspec_id"] is not None}
        edges = [handles[f"wall-1__edge_{index}"] for index in range(4)]
        dim = handles["axis-span"]
        report["planspec"]["handles_by_id"] = handles
        report["handles"] = {"wall_edges": edges, "dimension": dim,
                             "start_cap": edges[3], "end_cap": edges[1]}
        before = wall_edges(client, session, edges)
        if abs(before["length_m"] - initial) > 1e-6 or \
                abs(before["thickness_m"] - 0.2) > 1e-6 or \
                abs(dimension(client, session, dim) - initial) > 1e-6:
            raise ProtocolError("Initial geometry or native dimension differs")
        first = save_verified(client, session, output / "before-edit.dwg")
        request(client, session, "open", path=first["path"])
        if not same_wall_geometry(before, wall_edges(client, session, edges)):
            raise ProtocolError("Coordinates changed on first DWG reopen")
        state = read_state(client, session)
        stale = {"op": "edit_wall_length", "request_id": "stale-" + uuid.uuid4().hex,
                 "document_id": state["document_id"], "revision": state["revision"],
                 "edge_handles": edges, "dimension_handle": dim,
                 "expected_length_m": initial + 0.1, "new_length_m": edited_length,
                 "expected_thickness_m": 0.2}
        try:
            client.tool("ocs_execute", {"ocs_session_id": session, "request": stale})
        except ToolError as error:
            if "wall_length_stale" not in str(error):
                raise
        else:
            raise ProtocolError("Stale length edit unexpectedly completed")
        if abs(wall_edges(client, session, edges)["length_m"] - initial) > 1e-6:
            raise ProtocolError("Stale edit was not rejected without geometry change")
        state = read_state(client, session)
        edit_id = "length-" + uuid.uuid4().hex
        payload = {**stale, "request_id": edit_id, "revision": state["revision"],
                   "expected_length_m": initial}
        changed = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if changed.get("status") != "completed" or \
                changed.get("result", {}).get("closed_outline") is not True:
            raise ProtocolError("Guarded length edit did not complete")
        recovered = client.tool("ocs_read", {"ocs_session_id": session, "op": "operation",
            "parameters": {"request_id": edit_id}})
        if recovered.get("status") != "completed":
            raise ProtocolError("Committed edit could not be reconciled")
        revision_after = read_state(client, session)["revision"]
        replay = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if replay != changed or read_state(client, session)["revision"] != revision_after:
            raise ProtocolError("Request replay duplicated the edit")
        after = wall_edges(client, session, edges)
        measured = dimension(client, session, dim)
        if abs(after["length_m"] - edited_length) > 1e-6 or \
                abs(after["thickness_m"] - 0.2) > 1e-6 or \
                abs(measured - edited_length) > 1e-6:
            raise ProtocolError("Edited geometry or associative dimension differs")
        second = save_verified(client, session, output / "after-edit.dwg")
        if first["manifest"] != second["manifest"]:
            raise ProtocolError("Entity manifest changed on length edit")
        request(client, session, "open", path=second["path"])
        reopened = wall_edges(client, session, edges)
        if not same_wall_geometry(after, reopened) or \
                abs(dimension(client, session, dim) - edited_length) > 1e-6:
            raise ProtocolError("Edited length or dimension changed on DWG reopen")
        report.update({"status": "passed", "measurements_m": {"initial": initial,
                       "edited": measured}, "wall_before": before, "wall_after": after,
                       "wall_reopened_after": reopened, "first_save": first,
                       "second_save": second, "operation_recovered": True,
                       "replay_without_mutation": True, "stale_rejected": True})
        for _ in range(4):
            if gui.poll() is not None:
                break
            try:
                request(client, session, "run", cmd="QUIT")
            except (ProtocolError, ToolError, UncertainMutation):
                break
            try:
                gui.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error"] = str(error)
        raise
    finally:
        client.close()
        if gui.poll() is None:
            gui.terminate()
            try:
                gui.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gui.kill(); gui.wait(timeout=5)
        report["gui_exited"] = gui.poll() is not None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
