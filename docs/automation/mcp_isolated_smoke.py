"""L2 synthetic MCP smoke in a new, workspace-local OCS profile.

Creates only synthetic geometry. Never discovers the normal user profile.
"""

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from PIL import Image

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
from mcp_budgeted_run import CheckpointError
from mcp_capture_budget import CaptureBudget
from masterplan.artifact_evidence import artifact_ref
from masterplan.planspec import dry_run


def native_geometry(entities: list[dict]) -> dict[str, dict]:
    result = {}
    for entity in entities:
        kind = entity["type"]
        if kind == "Arc":
            result[kind] = {key: entity[key] for key in
                            ("handle", "layer", "center", "radius", "start_angle", "end_angle")}
        elif kind == "Polyline":
            result[kind] = {"handle": entity["handle"], "layer": entity["layer"],
                            "vertices": entity["vertices"],
                            "is_closed": entity["properties"]["is_closed"],
                            "constant_width": entity["properties"]["constant_width"],
                            "thickness": entity["properties"]["thickness"]}
    return result


def same_geometry(before: object, after: object, *, tolerance: float = 1e-6) -> bool:
    if isinstance(before, dict) and isinstance(after, dict):
        return before.keys() == after.keys() and all(
            same_geometry(before[key], after[key], tolerance=tolerance) for key in before)
    if isinstance(before, list) and isinstance(after, list):
        return len(before) == len(after) and all(same_geometry(a, b, tolerance=tolerance)
                                                 for a, b in zip(before, after))
    if type(before) in (int, float) and type(after) in (int, float):
        return math.isfinite(before) and math.isfinite(after) and abs(before - after) <= tolerance
    return before == after


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


def main(*, semantic: bool = False, plan_fixture: str = "synthetic-room") -> None:
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
    if plan_fixture not in {"synthetic-room", "synthetic-layer", "synthetic-contour",
                            "synthetic-wall", "synthetic-wall-gap", "synthetic-door-swing",
                            "synthetic-window", "synthetic-wall-join",
                            "synthetic-two-door-wall-v8"}:
        raise ValueError("Only versioned synthetic PlanSpec fixtures are allowed")
    fixtures = Path(__file__).resolve().parent / "masterplan/fixtures"
    fixture = fixtures / f"{plan_fixture}.planspec.json"
    manifest = None
    if plan_fixture == "synthetic-layer":
        manifest = json.loads((fixtures / "capabilities-d51b9253.json").read_text(encoding="utf-8"))
        if report["binary_sha256"] != manifest["binary_sha256"]:
            raise ProtocolError("Layer capability manifest belongs to another build")
    compiled = dry_run(json.loads(fixture.read_text(encoding="utf-8")),
                       capabilities=set(manifest["verified_capabilities"]) if manifest else None)
    expected_count = 20 if plan_fixture == "synthetic-two-door-wall-v8" else \
        14 if plan_fixture in {"synthetic-door-swing", "synthetic-window"} else \
        8 if plan_fixture in {"synthetic-wall-gap", "synthetic-wall-join"} else \
        4 if plan_fixture in {"synthetic-contour", "synthetic-wall"} else 3
    if not compiled["executable"] or len(compiled["commands"]) != expected_count:
        raise ProtocolError("Synthetic PlanSpec has unsupported or missing commands")
    report["planspec"] = {"fixture": fixture.name,
                          "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                          "commands_sha256": compiled["commands_sha256"],
                          "topology": compiled["topology"],
                          "architecture": compiled["architecture"],
                          "door_clearance_qa": compiled["door_clearance_qa"],
                          "source_bounds": compiled["source_bounds"],
                          "wall_compilation": compiled["wall_compilation"],
                          "dwg_unit_profile": compiled["dwg_unit_profile"],
                          "command_count": len(compiled["commands"]),
                          "step_count": len(compiled["execution_steps"])}
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
        if manifest:
            catalog = client.tool("ocs_read", {"ocs_session_id": session, "op": "commands",
                                               "parameters": {"limit": 1000}})
            names = set(catalog.get("commands", []))
            actual = hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()
            if catalog.get("count") != len(names) or actual != manifest["commands_sha256"]:
                raise ProtocolError("Layer capability command catalog differs from manifest")
            report["planspec"]["capability_manifest"] = "capabilities-d51b9253.json"
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
        script_started_ns = time.monotonic_ns()
        script = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run_script", "request_id": "l2-script-" + uuid.uuid4().hex,
                        "strict": True,
                        "commands": [item["command"] for item in compiled["execution_steps"]]}})
        report.setdefault("client_timings_ms", {})["planspec_script_rpc"] = round(
            (time.monotonic_ns() - script_started_ns) / 1_000_000, 3)
        if script.get("completed_commands") != len(compiled["execution_steps"]) \
                or script.get("added_entities") != len(compiled["commands"]):
            raise ProtocolError("Synthetic script entity count differs from PlanSpec")
        command_timings = script.get("command_timings_ms")
        if script.get("command_timing_scope") != "gui_operation_elapsed" or \
                not isinstance(command_timings, list) or \
                len(command_timings) != len(compiled["execution_steps"]) or \
                any(not isinstance(value, (int, float)) or value < 0
                    for value in command_timings):
            raise ProtocolError("Synthetic script omitted GUI operation timings")
        report["command_timings_ms"] = {"scope": "gui_operation_elapsed",
                                         "by_step": command_timings,
                                         "sum": round(sum(command_timings), 3)}
        handles = {}
        for step, item in enumerate(compiled["execution_steps"]):
            if item["planspec_id"] is None:
                continue
            created = [change["handle"] for change in script.get("changes", [])
                       if change.get("step") == step and change.get("kind") == "Added"
                       and isinstance(change.get("handle"), str)]
            if len(created) != 1:
                raise ProtocolError("PlanSpec command did not map to exactly one new handle")
            handles[item["planspec_id"]] = created[0]
        if len(set(handles.values())) != len(handles):
            raise ProtocolError("PlanSpec handles are not unique")
        report["planspec"]["handles_by_id"] = handles
        handles_by_source = {}
        for item in compiled["commands"]:
            if item.get("source_id"):
                handles_by_source.setdefault(item["source_id"], []).append(
                    handles[item["planspec_id"]])
        if handles_by_source:
            report["planspec"]["handles_by_source"] = handles_by_source
        properties = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                              "parameters": {"handles": list(handles.values()),
                                                             "detail": "summary"}})
        layers_by_handle = {entity["handle"]: entity["layer"]
                            for entity in properties.get("entities", [])}
        expected_layers = {item["planspec_id"]: item["layer"] for item in compiled["commands"]}
        if {name: layers_by_handle.get(handle) for name, handle in handles.items()} != expected_layers:
            raise ProtocolError("PlanSpec entity layer differs from compiled layer")
        report["planspec"]["layers_by_id"] = expected_layers
        if semantic:
            native = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-native-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["ARC 0,0 5,5 10,0",
                                                          "PLINE 20,0 24,0 24,4 C"]}})
            if native.get("completed_commands") != 2 or native.get("added_entities") != 2:
                raise ProtocolError("Native ARC/PLINE fixture did not create two entities")
            native_handles = [change["handle"] for change in native.get("changes", [])
                              if change.get("kind") == "Added" and isinstance(change.get("handle"), str)]
            if len(native_handles) != 2 or len(set(native_handles)) != 2:
                raise ProtocolError("Native fixture handles are absent or duplicated")
            queried = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                            "parameters": {"handles": native_handles, "detail": "full"}})
            by_type = {entity["type"]: entity for entity in queried.get("entities", [])}
            if set(by_type) != {"Arc", "Polyline"}:
                raise ProtocolError("Native fixture degraded to unexpected entity types")
            arc = by_type["Arc"]
            if abs(arc.get("radius", 0) - 5) > 1e-6 or len(by_type["Polyline"].get("vertices", [])) != 3:
                raise ProtocolError("Native primitive geometry differs from fixture")
            if by_type["Polyline"].get("properties", {}).get("is_closed") is not True:
                raise ProtocolError("Native polyline is not closed")
            report["native_primitives"] = {"handles": native_handles,
                                           "types": sorted(by_type),
                                           "arc_radius": arc["radius"],
                                           "polyline_vertices": len(by_type["Polyline"]["vertices"]),
                                           "polyline_closed": True}
            native_before = native_geometry(queried["entities"])
            layered = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-layer-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["LAYER NEW A-WALL", "CLAYER A-WALL",
                                                          "LINE 30,0 34,0"]}})
            if layered.get("completed_commands") != 3 or layered.get("added_entities") != 1:
                raise ProtocolError("Layer fixture did not create exactly one line")
            layer_handles = [change["handle"] for change in layered.get("changes", [])
                             if change.get("kind") == "Added" and change.get("step") == 2]
            if len(layer_handles) != 1:
                raise ProtocolError("Layer fixture line handle is missing")
            layer_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                    "parameters": {"handle": layer_handles[0],
                                                                   "detail": "geometry"}})
            if layer_query.get("entities", [{}])[0].get("layer") != "A-WALL":
                raise ProtocolError("Layer fixture line was assigned to another layer")
            report["layer_fixture"] = {"handle": layer_handles[0], "layer": "A-WALL"}
            dimension = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-dimension-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["LAYER NEW A-DIMS", "CLAYER A-DIMS",
                                                          "DIMLINEAR 40,0 42.5,0 41.25,1",
                                                          "DIMALIGNED 46,0 49,4 48.5,3"]}})
            if dimension.get("completed_commands") != 4 or dimension.get("added_entities") != 2:
                raise ProtocolError("Native linear/aligned dimensions were not created")
            dimension_handles = [change["handle"] for change in dimension.get("changes", [])
                                 if change.get("kind") == "Added" and change.get("step") == 2]
            if len(dimension_handles) != 1:
                raise ProtocolError("Native dimension handle is absent")
            dimension_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                        "parameters": {"handle": dimension_handles[0],
                                                                       "detail": "full"}})
            dimension_entity = dimension_query.get("entities", [{}])[0]
            linear = dimension_entity.get("properties", {}).get("Linear", {})
            measured = linear.get("base", {}).get("actual_measurement")
            if (dimension_entity.get("type") != "Dimension" or
                    dimension_entity.get("layer") != "A-DIMS" or
                    not isinstance(measured, (int, float)) or abs(measured - 2.5) > 1e-6):
                raise ProtocolError("Native dimension geometry, measure or layer differs from fixture")
            report["dimension_fixture"] = {"handle": dimension_handles[0],
                                           "type": "Dimension", "layer": "A-DIMS",
                                           "actual_measurement": measured,
                                           "associativity": "unverified"}
            aligned_handles = [change["handle"] for change in dimension.get("changes", [])
                               if change.get("kind") == "Added" and change.get("step") == 3]
            if len(aligned_handles) != 1 or aligned_handles[0] == dimension_handles[0]:
                raise ProtocolError("Native aligned dimension handle is absent or duplicated")
            aligned_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                      "parameters": {"handle": aligned_handles[0],
                                                                     "detail": "full"}})
            aligned_entity = aligned_query.get("entities", [{}])[0]
            aligned = aligned_entity.get("properties", {}).get("Aligned", {})
            aligned_measure = aligned.get("base", {}).get("actual_measurement")
            if (aligned_entity.get("type") != "Dimension" or
                    aligned_entity.get("layer") != "A-DIMS" or
                    not isinstance(aligned_measure, (int, float)) or
                    abs(aligned_measure - 5.0) > 1e-6):
                raise ProtocolError("Aligned dimension geometry, measure or layer differs from fixture")
            report["aligned_dimension_fixture"] = {"handle": aligned_handles[0],
                                                    "type": "Dimension", "layer": "A-DIMS",
                                                    "actual_measurement": aligned_measure,
                                                    "associativity": "unverified"}
            source = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-block-source-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["LINE 55,0 57,0"]}})
            source_handles = [change["handle"] for change in source.get("changes", [])
                              if change.get("kind") == "Added"]
            if source.get("added_entities") != 1 or len(source_handles) != 1:
                raise ProtocolError("Block source line was not created")
            definition = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "batch", "request_id": "l2-block-def-" + uuid.uuid4().hex,
                            "steps": [{"op": "select", "handles": source_handles},
                                      {"op": "run", "cmd": "-BLOCK MCP-SYMBOL 55,0"}]}})
            report["block_fixture"] = {"source_handle": source_handles[0],
                                       "definition_steps": definition.get("completed_steps")}
            inserted = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-block-insert-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["INSERT MCP-SYMBOL R 30 62,0",
                                                          "INSERT MCP-SYMBOL S 2 66,0"]}})
            insert_handles = [change["handle"] for change in inserted.get("changes", [])
                              if change.get("kind") == "Added"]
            if inserted.get("completed_commands") != 2 or len(insert_handles) != 2:
                raise ProtocolError("Block instances were not inserted")
            inserts_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                      "parameters": {"handles": insert_handles,
                                                                     "detail": "full"}})
            inserts = inserts_query.get("entities", [])
            if (len(inserts) != 2 or any(entity.get("type") != "Block Reference" or
                                          entity.get("block") != "MCP-SYMBOL" for entity in inserts)):
                raise ProtocolError("Native block reference identity differs from fixture")
            report["block_fixture"]["insert_handles"] = insert_handles
            report["block_fixture"]["instances"] = [
                {"block": entity.get("block"), "position": entity.get("position"),
                 "x_scale": entity.get("properties", {}).get("x_scale"),
                 "y_scale": entity.get("properties", {}).get("y_scale"),
                 "rotation": entity.get("properties", {}).get("rotation")}
                for entity in inserts]
            first, second = report["block_fixture"]["instances"]
            if (not same_geometry(first["rotation"], math.radians(30)) or
                    not same_geometry(first["x_scale"], 1) or
                    not same_geometry(second["rotation"], 0) or
                    not same_geometry(second["x_scale"], 2) or
                    not same_geometry(second["y_scale"], 2)):
                raise ProtocolError("Block instance scale or rotation differs from fixture")
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-hatch-layer-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["LAYER NEW A-HATCH", "CLAYER A-HATCH"]}})
            hatch = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "batch", "request_id": "l2-hatch-" + uuid.uuid4().hex,
                            "steps": [{"op": "run", "cmd": "HATCH"},
                                      {"op": "input", "kind": "point", "point": [23, 1, 0]},
                                      {"op": "input", "kind": "enter"}]}})
            if hatch.get("completed_steps") != 3:
                raise ProtocolError("HATCH batch did not finish all steps")
            hatch_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                     "parameters": {"type": "Hatch", "detail": "full"}})
            hatch_entities = hatch_query.get("entities", [])
            if (len(hatch_entities) != 1 or hatch_entities[0].get("type") != "Hatch" or
                    hatch_entities[0].get("layer") != "A-HATCH"):
                raise ProtocolError("HATCH did not create exactly one native entity")
            hatch_entity = hatch_entities[0]
            hatch_props = hatch_entity.get("properties", {})
            hatch_before = {"layer": hatch_entity.get("layer"),
                            "is_associative": hatch_props.get("is_associative"),
                            "is_solid": hatch_props.get("is_solid"),
                            "pattern_scale": hatch_props.get("pattern_scale"),
                            "pattern_angle": hatch_props.get("pattern_angle"),
                            "paths": hatch_props.get("paths")}
            if not isinstance(hatch_before["paths"], list) or not hatch_before["paths"]:
                raise ProtocolError("HATCH boundary paths are absent")
            report["hatch_fixture"] = {"handle": hatch_entity["handle"],
                                       "layer": hatch_before["layer"],
                                       "is_associative_flag": hatch_before["is_associative"],
                                       "is_solid": hatch_before["is_solid"],
                                       "pattern_scale": hatch_before["pattern_scale"],
                                       "pattern_angle": hatch_before["pattern_angle"],
                                       "path_count": len(hatch_before["paths"])}
            assoc_setup = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run_script", "request_id": "l2-assoc-setup-" + uuid.uuid4().hex,
                            "strict": True, "commands": ["CLAYER 0", "LINE 70,0 72.5,0",
                                                          "CLAYER A-DIMS",
                                                          "DIMLINEAR 70,0 72.5,0 71.25,1"]}})
            assoc_line = [change["handle"] for change in assoc_setup.get("changes", [])
                          if change.get("kind") == "Added" and change.get("step") == 1]
            assoc_dim = [change["handle"] for change in assoc_setup.get("changes", [])
                         if change.get("kind") == "Added" and change.get("step") == 3]
            if len(assoc_line) != 1 or len(assoc_dim) != 1:
                raise ProtocolError("Associative dimension fixture handles are absent")
            assoc_before_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                           "parameters": {"handle": assoc_dim[0],
                                                                          "detail": "full"}})
            initial_measure = (assoc_before_query.get("entities", [{}])[0]
                               .get("properties", {}).get("Linear", {}).get("base", {})
                               .get("actual_measurement"))
            if not isinstance(initial_measure, (int, float)) or abs(initial_measure - 2.5) > 1e-6:
                raise ProtocolError("Initial associative dimension measure differs from fixture")
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "set_properties", "request_id": "l2-assoc-edit-" + uuid.uuid4().hex,
                            "collection": "entities", "handle": assoc_line[0],
                            "updates": [{"path": "/end/x", "expected": 72.5, "value": 73.5}]}})
            assoc_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                     "parameters": {"handle": assoc_dim[0],
                                                                    "detail": "full"}})
            assoc_entity = assoc_query.get("entities", [{}])[0]
            assoc_measure = (assoc_entity.get("properties", {}).get("Linear", {})
                             .get("base", {}).get("actual_measurement"))
            report["association_fixture"] = {"source_handle": assoc_line[0],
                                             "dimension_handle": assoc_dim[0],
                                             "initial_measurement": initial_measure,
                                             "expected_measurement": 3.5,
                                             "observed_measurement": assoc_measure}
            if not isinstance(assoc_measure, (int, float)) or abs(assoc_measure - 3.5) > 1e-6:
                raise ProtocolError("Dimension did not follow edited source endpoint")
        audit = client.tool("ocs_read", {"ocs_session_id": session, "op": "audit",
                                         "parameters": {"target_format": "dwg", "target_version": "2018"}})
        if audit.get("ok") is not True:
            raise ProtocolError("Synthetic DWG audit failed")
        report["audit_summary"] = {key: audit.get(key) for key in
                                   ("status", "summary", "target", "manifest", "bounds",
                                    "unknown_entities")}
        destination = output / "synthetic-verified.dwg"
        save_started_ns = time.monotonic_ns()
        saved = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save_verified", "request_id": "l2-save-" + uuid.uuid4().hex,
                        "path": str(destination), "target_format": "dwg", "target_version": "2018"}})
        report.setdefault("client_timings_ms", {})["save_verified_rpc"] = round(
            (time.monotonic_ns() - save_started_ns) / 1_000_000, 3)
        verified = saved.get("result", saved)
        if verified.get("verified") is not True or not destination.is_file():
            raise ProtocolError("Synthetic verified save failed")
        if verified.get("timings", {}).get("scope") != "gui_process_monotonic":
            raise ProtocolError("Synthetic verified save omitted GUI phase timings")
        if semantic:
            by_type = verified.get("manifest", {}).get("by_type", {})
            if by_type.get("Arc") != 1 or by_type.get("Polyline") != 1:
                raise ProtocolError("Native primitives did not survive internal DWG reopen")
            report["native_primitives"]["reopened_types"] = {"Arc": 1, "Polyline": 1}
            if verified.get("manifest", {}).get("by_layer", {}).get("A-WALL") != 1:
                raise ProtocolError("Synthetic layer assignment did not survive DWG reopen")
            report["layer_fixture"]["reopened_count"] = 1
            if verified.get("manifest", {}).get("by_type", {}).get("Dimension") != 3:
                raise ProtocolError("Native dimensions did not survive DWG reopen")
            report["dimension_fixture"]["reopened_count"] = 1
            report["aligned_dimension_fixture"]["reopened_count"] = 1
            if verified.get("manifest", {}).get("by_type", {}).get("Block Reference") != 3:
                raise ProtocolError("Block references did not survive DWG reopen")
            report["block_fixture"]["reopened_count"] = 3
            if verified.get("manifest", {}).get("by_type", {}).get("Hatch") != 1:
                raise ProtocolError("Native hatch did not survive DWG reopen")
            report["hatch_fixture"]["reopened_count"] = 1
        actual_hash = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
        if verified["sha256"].upper() != actual_hash:
            raise ProtocolError("Synthetic output hash differs from backend report")
        report.update({"status": "passed", "script": {"completed_commands": len(compiled["execution_steps"]),
                                                      "added_entities": len(compiled["commands"])},
                       "audit_ok": True,
                       "verified_output": {"path": str(destination), "sha256": actual_hash,
                                           "bytes": destination.stat().st_size,
                                           "engine_timings_ms": verified["timings"],
                                           "source_manifest": verified.get("source_manifest"),
                                           "materialized_manifest": verified.get("materialized_manifest"),
                                           "reopened_manifest": verified.get("manifest")}})

        # Save the working tab separately so QUIT cannot discard unsaved work.
        client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save", "request_id": "l2-clean-save-" + uuid.uuid4().hex,
                        "path": str(output / "synthetic-session.dwg"),
                        "target_format": "dwg", "target_version": "2018"}})
        if semantic:
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "open", "request_id": "l2-reopen-" + uuid.uuid4().hex,
                            "path": str(destination)}})
            reopened = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                "parameters": {"handles": native_handles,
                                                               "detail": "full"}})
            native_after = native_geometry(reopened.get("entities", []))
            if set(native_after) != {"Arc", "Polyline"} or not same_geometry(native_before, native_after):
                raise ProtocolError("Native primitive geometry changed after internal DWG reopen")
            report["native_primitives"]["roundtrip_geometry"] = "matched_1e-6_internal"
            dimension_after = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                       "parameters": {"handle": dimension_handles[0],
                                                                      "detail": "full"}})
            restored = dimension_after.get("entities", [{}])[0]
            restored_linear = restored.get("properties", {}).get("Linear", {})
            restored_measure = restored_linear.get("base", {}).get("actual_measurement")
            if (restored.get("type") != "Dimension" or restored.get("layer") != "A-DIMS" or
                    not isinstance(restored_measure, (int, float)) or
                    abs(restored_measure - measured) > 1e-6):
                raise ProtocolError("Native dimension measure/layer changed after DWG reopen")
            report["dimension_fixture"]["roundtrip_measurement"] = restored_measure
            aligned_after = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                     "parameters": {"handle": aligned_handles[0],
                                                                    "detail": "full"}})
            restored_aligned = aligned_after.get("entities", [{}])[0]
            restored_aligned_measure = (restored_aligned.get("properties", {})
                                        .get("Aligned", {}).get("base", {})
                                        .get("actual_measurement"))
            if (restored_aligned.get("type") != "Dimension" or
                    restored_aligned.get("layer") != "A-DIMS" or
                    not isinstance(restored_aligned_measure, (int, float)) or
                    abs(restored_aligned_measure - aligned_measure) > 1e-6):
                raise ProtocolError("Aligned dimension measure/layer changed after DWG reopen")
            report["aligned_dimension_fixture"]["roundtrip_measurement"] = restored_aligned_measure
            inserts_after = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                      "parameters": {"handles": insert_handles,
                                                                     "detail": "full"}})
            instances_after = [{"block": entity.get("block"), "position": entity.get("position"),
                                "x_scale": entity.get("properties", {}).get("x_scale"),
                                "y_scale": entity.get("properties", {}).get("y_scale"),
                                "rotation": entity.get("properties", {}).get("rotation")}
                               for entity in inserts_after.get("entities", [])]
            if not same_geometry(report["block_fixture"]["instances"], instances_after):
                raise ProtocolError("Block instance transform changed after DWG reopen")
            report["block_fixture"]["roundtrip_transforms"] = "matched_1e-6_internal"
            hatch_after_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                          "parameters": {"handle": hatch_entity["handle"],
                                                                         "detail": "full"}})
            restored_hatch = hatch_after_query.get("entities", [{}])[0]
            restored_hatch_props = restored_hatch.get("properties", {})
            hatch_after = {"layer": restored_hatch.get("layer"),
                           "is_associative": restored_hatch_props.get("is_associative"),
                           "is_solid": restored_hatch_props.get("is_solid"),
                           "pattern_scale": restored_hatch_props.get("pattern_scale"),
                           "pattern_angle": restored_hatch_props.get("pattern_angle"),
                           "paths": restored_hatch_props.get("paths")}
            if restored_hatch.get("type") != "Hatch" or not same_geometry(hatch_before, hatch_after):
                raise ProtocolError("HATCH boundary or style changed after DWG reopen")
            report["hatch_fixture"]["roundtrip_properties"] = "matched_1e-6_internal"
            assoc_after_query = client.tool("ocs_read", {"ocs_session_id": session, "op": "query",
                                                          "parameters": {"handle": assoc_dim[0],
                                                                         "detail": "full"}})
            restored_assoc = assoc_after_query.get("entities", [{}])[0]
            restored_assoc_measure = (restored_assoc.get("properties", {}).get("Linear", {})
                                      .get("base", {}).get("actual_measurement"))
            if (restored_assoc.get("type") != "Dimension" or
                    not isinstance(restored_assoc_measure, (int, float)) or
                    abs(restored_assoc_measure - 3.5) > 1e-6):
                raise ProtocolError("Edited associative dimension changed after DWG reopen")
            report["association_fixture"]["roundtrip_measurement"] = restored_assoc_measure
        if plan_fixture in {"synthetic-wall", "synthetic-wall-gap", "synthetic-door-swing",
                            "synthetic-window", "synthetic-wall-join",
                            "synthetic-two-door-wall-v8"}:
            zoom = client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "run", "request_id": "l2-zoom-extents-" + uuid.uuid4().hex,
                            "cmd": "ZOOM EXTENTS"}})
            report["capture_framing"] = {"command": "ZOOM EXTENTS",
                                         "status": zoom.get("status")}
            if zoom.get("status") != "completed":
                raise ProtocolError("Synthetic wall capture could not fit extents")
            # ZOOM updates the drawing view and marks the working tab dirty.
            # Save that isolated tab again so shutdown never discards it.
            client.tool("ocs_execute", {"ocs_session_id": session,
                "request": {"op": "save", "request_id": "l2-framed-save-" + uuid.uuid4().hex,
                            "path": str(output / "synthetic-session.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        capture_path = (output / "capture.png").resolve()
        capture_checkpoint = (output / "capture-budget.jsonl").resolve()
        capture_budget = CaptureBudget(client, session, capture_checkpoint,
                                       "l2-capture-" + session[:12],
                                       max_captures=1, max_bytes=20_000_000)
        capture_started_ns = time.monotonic_ns()
        # Fixed CAD anchors for this versioned synthetic fixture. They cover each
        # leaf and arc, allowing regions to be traced to the same rendered frame.
        landmarks = None
        if plan_fixture == "synthetic-two-door-wall-v8":
            landmarks = [
                {"id": "door-south-hinge", "point": [1, 0.1, 0]},
                {"id": "door-south-closed", "point": [1.9, 0.1, 0]},
                {"id": "door-south-arc-mid", "point": [1.636396103, 0.736396103, 0]},
                {"id": "door-south-open", "point": [1, 1, 0]},
                {"id": "door-east-hinge", "point": [2.2, 0.1, 0]},
                {"id": "door-east-closed", "point": [3, 0.1, 0]},
                {"id": "door-east-arc-mid", "point": [2.765685425, 0.665685425, 0]},
                {"id": "door-east-open", "point": [2.2, 0.9, 0]},
            ]
        budget_result = capture_budget.capture(capture_path,
                                                document_id=state["document_id"],
                                                geometry_revision=state["geometry_revision"],
                                                camera_revision=state["camera_revision"],
                                                landmarks=landmarks)
        capture = budget_result["metadata"]
        report.setdefault("client_timings_ms", {})["capture_rpc_and_artifact"] = round(
            (time.monotonic_ns() - capture_started_ns) / 1_000_000, 3)
        resumed_capture = capture_budget.capture(capture_path,
                                                 document_id=state["document_id"],
                                                 geometry_revision=state["geometry_revision"],
                                                 camera_revision=state["camera_revision"])
        if resumed_capture["status"] != "already_completed" or \
                resumed_capture["sha256"] != budget_result["sha256"]:
            raise ProtocolError("Capture budget did not reconcile completed artifact")
        try:
            capture_budget.capture((output / "second.png").resolve(),
                                   document_id=state["document_id"],
                                   geometry_revision=state["geometry_revision"],
                                   camera_revision=state["camera_revision"])
        except CheckpointError as error:
            if "budget is exhausted" not in str(error):
                raise
        else:
            raise ProtocolError("Capture budget allowed a second capture")
        report["capture_budget"] = {"status": budget_result["status"],
                                    "captures_used": 1, "max_captures": 1,
                                    "bytes_used": budget_result["bytes"],
                                    "max_bytes": 20_000_000,
                                    "checkpoint_sha256": hashlib.sha256(
                                        capture_checkpoint.read_bytes()).hexdigest().upper()}
        if capture.get("timings", {}).get("scope") != "gui_process_monotonic":
            raise ProtocolError("Synthetic capture omitted GUI phase timings")
        if capture.get("overlay_policy") != "drawing_only":
            raise ProtocolError("Synthetic viewport capture contains interactive overlays")
        report["capture_overlay_policy"] = capture["overlay_policy"]
        if landmarks is not None:
            if any(not point["inside"] for point in capture["landmarks_px"]):
                raise ProtocolError("Synthetic door landmark is outside captured viewport")
            report["capture_projection"] = {
                "contract": capture["projection_contract"],
                "landmarks_cad": landmarks,
                "landmarks_px": capture["landmarks_px"],
                "document_id": capture["document_id"],
                "geometry_revision": capture["geometry_revision"],
                "camera_revision": capture["camera_revision"]}
        report["capture_engine_timings_ms"] = capture["timings"]
        reference = artifact_ref(output, capture_path.name,
                                 document_id=capture["document_id"],
                                 geometry_revision=capture["geometry_revision"],
                                 camera_revision=capture["camera_revision"],
                                 region=capture["scope"])
        if (reference["width"], reference["height"]) != (capture["width"], capture["height"]):
            raise ProtocolError("Capture PNG dimensions differ from MCP metadata")
        report["capture_artifact"] = reference
        if landmarks is not None:
            # This L2 fixture renders light CAD strokes on a dark viewport.
            # Require visible ink near each independently specified CAD anchor.
            probes = []
            with Image.open(capture_path) as opened:
                rgb = opened.convert("RGB")
                for point in capture["landmarks_px"]:
                    x, y = (round(value) for value in point["pixel"])
                    peak = max(max(rgb.getpixel((px, py)))
                               for px in range(max(0, x - 3), min(rgb.width, x + 4))
                               for py in range(max(0, y - 3), min(rgb.height, y + 4)))
                    probes.append({"id": point["id"], "radius_px": 3,
                                   "peak_rgb_channel": peak, "threshold": 80,
                                   "visible": peak >= 80})
            report["capture_projection"]["pixel_probes"] = probes
            if any(not probe["visible"] for probe in probes):
                raise ProtocolError("Projected CAD landmark misses visible fixture ink")
        report["capture_fence"] = {key: capture[key] for key in
                                   ("rendered_geometry_revision", "rendered_camera_revision",
                                    "render_fence")}
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
