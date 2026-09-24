"""Isolated L2 proof of one guarded wall thickness edit with a native dimension."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from mcp_client import Client, ProtocolError, UncertainMutation
from mcp_face_dimension_smoke import dimension, request, save_verified
from mcp_isolated_smoke import read_state
from masterplan.planspec import dry_run


def wall_edges(client, session, handles, *, vertical):
    points = []
    for handle in handles:
        result = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
            "parameters": {"handle": handle, "detail": "full"}})
        entity = result.get("entities", [{}])[0]
        if entity.get("type") != "Line":
            raise ProtocolError("Wall part is not a LINE")
        points.append((entity["start"], entity["end"]))
    for index in range(4):
        end = points[index][1]
        start = points[(index + 1) % 4][0]
        if any(abs(end[axis] - start[axis]) > 1e-6 for axis in range(3)):
            raise ProtocolError("Wall outline is open")
    axis = 0 if vertical else 1
    thickness = abs(points[0][0][axis] - points[2][0][axis])
    return {"closed": True, "thickness_m": thickness,
            "points": [[item[0], item[1]] for item in points]}


def main():
    repo = Path(__file__).resolve().parents[2]
    server = Path(sys.argv[1] if len(sys.argv) > 1 else repo / "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    fixture_name = (sys.argv[2] if len(sys.argv) > 2 else
                    "synthetic-wall-face-dimension-vertical-v7.planspec.json")
    if fixture_name not in {"synthetic-wall-face-dimension-vertical-v7.planspec.json",
                            "synthetic-wall-face-dimension-readable-v7.planspec.json"}:
        raise ValueError("Only two versioned wall dimension fixtures are allowed")
    fixture = repo / "docs/automation/masterplan/fixtures" / fixture_name
    plan = json.loads(fixture.read_text(encoding="utf-8"))
    compiled = dry_run(plan)
    if not compiled["executable"] or len(compiled["commands"]) != 5:
        raise ProtocolError("Wall dimension fixture did not compile to five entities")
    vertical = compiled["dimension_compilation"]["status"] == \
        "compiled_single_vertical_face_thickness"
    output = repo / "target/mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                               "-wall-edit-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile, temporary = output / "profile", output / "temp"
    profile.mkdir(); temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-wall-thickness-l2-1", "status": "failed",
              "binary_sha256": hashlib.sha256(server.read_bytes()).hexdigest().upper(),
              "planspec": {"fixture": fixture.name,
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
            raise ProtocolError("Expected four wall LINEs and one DIMENSION")
        handles = {step["planspec_id"]: added[index]
                   for index, step in enumerate(compiled["execution_steps"])
                   if step["planspec_id"] is not None}
        edges = [handles[f"wall-1__edge_{index}"] for index in range(4)]
        dim = handles["wall-thickness"]
        report["planspec"]["handles_by_id"] = handles
        report["handles"] = {"first_face": edges[0], "second_face": edges[2],
                             "dimension": dim, "wall_edges": edges}
        before = wall_edges(client, session, edges, vertical=vertical)
        if abs(before["thickness_m"] - 0.2) > 1e-6 or abs(dimension(client, session, dim) - 0.2) > 1e-6:
            raise ProtocolError("Initial wall or dimension differs")
        first = save_verified(client, session, output / "before-edit.dwg")
        request(client, session, "save", path=str(output / "session-before.dwg"),
                target_format="dwg", target_version="2018")
        request(client, session, "open", path=first["path"])
        reopened_before = wall_edges(client, session, edges, vertical=vertical)
        if abs(reopened_before["thickness_m"] - 0.2) > 1e-6:
            raise ProtocolError("Wall thickness changed on reopen")
        state = read_state(client, session)
        edit_id = "wall-edit-" + uuid.uuid4().hex
        payload = {"op": "edit_wall_thickness", "request_id": edit_id,
                   "document_id": state["document_id"], "revision": state["revision"],
                   "edge_handles": edges, "expected_thickness_m": 0.2,
                   "new_thickness_m": 0.25}
        edited = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if edited.get("status") != "completed" or edited.get("result", {}).get("closed_outline") is not True:
            raise ProtocolError("Guarded wall edit did not complete")
        recovered = client.tool("ocs_read", {"ocs_session_id": session, "op": "operation",
            "parameters": {"request_id": edit_id}})
        if recovered.get("status") != "completed" or recovered.get("request_id") != edit_id:
            raise ProtocolError("Committed wall edit could not be reconciled by request_id")
        revision_after_edit = read_state(client, session)["revision"]
        replayed = client.tool("ocs_execute", {"ocs_session_id": session, "request": payload})
        if replayed != edited or read_state(client, session)["revision"] != revision_after_edit:
            raise ProtocolError("Replayed request_id duplicated the wall mutation")
        after = wall_edges(client, session, edges, vertical=vertical)
        measurement = dimension(client, session, dim)
        if abs(after["thickness_m"] - 0.25) > 1e-6 or abs(measurement - 0.25) > 1e-6:
            raise ProtocolError("Edited wall or dimension differs")
        second = save_verified(client, session, output / "after-edit.dwg")
        if first["manifest"] != second["manifest"]:
            raise ProtocolError("Wall edit changed DWG entity manifest")
        request(client, session, "save", path=str(output / "session-after.dwg"),
                target_format="dwg", target_version="2018")
        request(client, session, "open", path=second["path"])
        reopened_after = wall_edges(client, session, edges, vertical=vertical)
        if abs(reopened_after["thickness_m"] - 0.25) > 1e-6 or \
                abs(dimension(client, session, dim) - 0.25) > 1e-6:
            raise ProtocolError("Edited wall did not persist on reopen")
        report.update({"status": "passed", "edit_request_id": edit_id,
                       "measurements_m": {"initial": 0.2, "edited": measurement},
                       "wall_before": before, "wall_after": after,
                       "wall_reopened_after": reopened_after,
                       "first_save": first, "second_save": second,
                       "operation_recovered": True, "replay_without_mutation": True})
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
        if gui.poll() is None:
            gui.terminate()
            try:
                gui.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gui.kill()
                gui.wait(timeout=5)
        report["gui_exited"] = gui.poll() is not None
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
