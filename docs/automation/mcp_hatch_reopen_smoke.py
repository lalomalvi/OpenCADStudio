"""Isolated L2 proof of associative HATCH after a synthetic DWG reopen.

The GUI uses a fresh profile inside target. Failed runs and their GUI process
remain available for the explicit isolated recovery helper.
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


def entity(client: Client, session: str, handle: str, expected_type: str) -> dict:
    response = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                        "parameters": {"handle": handle, "detail": "full"}})
    entities = response.get("entities", [])
    if len(entities) != 1 or entities[0].get("type") != expected_type:
        raise ProtocolError(f"Expected one {expected_type} at {handle}")
    return entities[0]


def boundary(hatch: dict) -> dict:
    props = hatch.get("properties", {})
    paths = props.get("paths")
    if props.get("is_associative") is not True or not isinstance(paths, list) or len(paths) != 1:
        raise ProtocolError("Synthetic HATCH has no single associative path")
    return {"paths": paths, "is_associative": props["is_associative"],
            "pattern_scale": props.get("pattern_scale"),
            "pattern_angle": props.get("pattern_angle")}


def has_vertex(boundary_state: dict, x: float, y: float) -> bool:
    edges = boundary_state["paths"][0].get("edges", [])
    return any(edge.get("Line", {}).get(end) == {"x": x, "y": y}
               for edge in edges for end in ("start", "end"))


def save(client: Client, session: str, path: Path) -> dict:
    reply = client.tool("ocs_execute", {"ocs_session_id": session,
        "request": {"op": "save_verified", "request_id": "hatch-save-" + uuid.uuid4().hex,
                    "path": str(path), "target_format": "dwg", "target_version": "2018"}})
    result = reply.get("result", reply)
    if result.get("verified") is not True or not path.is_file():
        raise ProtocolError("Synthetic HATCH save/reopen failed")
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if result.get("sha256", "").upper() != digest:
        raise ProtocolError("Synthetic HATCH DWG digest differs from backend")
    return {"file": path.name, "sha256": digest, "bytes": path.stat().st_size,
            "manifest": result.get("manifest")}


def main() -> None:
    server = Path(sys.argv[1] if len(sys.argv) > 1 else "target/debug/OpenCADStudio.exe").resolve()
    if not server.is_file():
        raise FileNotFoundError(server)
    repo = Path(__file__).resolve().parents[2]
    output = repo / "target" / "mcp-isolated" / (time.strftime("%Y%m%d-%H%M%S") +
                                                  "-hatch-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    profile = output / "profile"
    profile.mkdir()
    temporary = output / "temp"
    temporary.mkdir()
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "mcp-hatch-reopen-l2-1", "status": "failed",
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
                "request": {"op": "action", "request_id": "hatch-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = read_state(client, session)
        if state.get("modal"):
            raise ProtocolError("Isolated GUI still has a startup modal")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "new", "request_id": "hatch-new-" + uuid.uuid4().hex}})
        created = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run_script", "request_id": "hatch-create-" + uuid.uuid4().hex,
                        "strict": True, "commands": ["PLINE 20,0 24,0 24,4 C"]}})
        sources = [change["handle"] for change in created.get("changes", [])
                   if change.get("kind") == "Added"]
        if created.get("completed_commands") != 1 or len(sources) != 1:
            raise ProtocolError("Synthetic contour not created")
        source = sources[0]
        made = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "batch", "request_id": "hatch-fill-" + uuid.uuid4().hex,
                        "steps": [{"op": "run", "cmd": "HATCH"},
                                  {"op": "input", "kind": "point", "point": [23, 1, 0]},
                                  {"op": "input", "kind": "enter"}]}})
        if made.get("completed_steps") != 3:
            raise ProtocolError("HATCH batch did not finish")
        hatch_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                 "parameters": {"type": "Hatch", "detail": "full"}})
        hatches = hatch_query.get("entities", [])
        if len(hatches) != 1:
            raise ProtocolError("Expected one synthetic HATCH")
        hatch = hatches[0]["handle"]
        initial = boundary(hatches[0])
        if initial["paths"][0].get("boundary_handles") != [int(source, 16)] or not has_vertex(initial, 24.0, 0.0):
            raise ProtocolError("HATCH path does not reference the expected contour")
        report["association"] = {"source_handle": source, "hatch_handle": hatch,
                                 "initial_boundary": initial}
        first = output / "before-reopen.dwg"
        report["first_save"] = save(client, session, first)
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "hatch-clean-" + uuid.uuid4().hex,
                        "path": str(output / "session-before.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "open", "request_id": "hatch-open-" + uuid.uuid4().hex,
                        "path": str(first)}})
        reopened = boundary(entity(client, session, hatch, "Hatch"))
        if reopened != initial:
            raise ProtocolError("HATCH path changed on first internal reopen")
        contour = entity(client, session, source, "Polyline")
        vertices = contour.get("vertices", [])
        if len(vertices) != 3 or vertices[1] != [24.0, 0.0]:
            raise ProtocolError("Unexpected contour vertices after reopen")
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "set_properties", "request_id": "hatch-edit-" + uuid.uuid4().hex,
                        "collection": "entities", "handle": source,
                        "updates": [{"path": "/vertices/1/location/x", "expected": 24.0,
                                     "value": 25.0}]}})
        edited_contour = entity(client, session, source, "Polyline")
        edited = boundary(entity(client, session, hatch, "Hatch"))
        report["association"].update({"reopened_boundary": reopened,
                                      "edited_boundary": edited,
                                      "edited_vertices": edited_contour.get("vertices")})
        if (edited_contour.get("vertices", [None, None])[1] != [25.0, 0.0] or
                edited == reopened or not has_vertex(edited, 25.0, 0.0) or
                has_vertex(edited, 24.0, 0.0)):
            raise ProtocolError("HATCH boundary did not follow edited source")
        second = output / "after-reopen.dwg"
        report["second_save"] = save(client, session, second)
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "hatch-final-clean-" + uuid.uuid4().hex,
                        "path": str(output / "session-after.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "open", "request_id": "hatch-second-open-" + uuid.uuid4().hex,
                        "path": str(second)}})
        reopened_edited = boundary(entity(client, session, hatch, "Hatch"))
        report["association"]["edited_boundary_after_second_reopen"] = reopened_edited
        if reopened_edited != edited or entity(client, session, source, "Polyline").get("vertices", [None, None])[1] != [25.0, 0.0]:
            raise ProtocolError("Edited associative HATCH changed after second internal reopen")
        try:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "hatch-quit-" + uuid.uuid4().hex,
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
