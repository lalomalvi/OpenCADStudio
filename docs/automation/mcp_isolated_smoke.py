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

from mcp_client import Client, ProtocolError, ToolError, UncertainMutation
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
    if plan_fixture not in {"synthetic-room", "synthetic-layer"}:
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
    if not compiled["executable"] or len(compiled["commands"]) != 3:
        raise ProtocolError("Synthetic PlanSpec has unsupported or missing commands")
    report["planspec"] = {"fixture": fixture.name,
                          "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                          "commands_sha256": compiled["commands_sha256"],
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
        script = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "run_script", "request_id": "l2-script-" + uuid.uuid4().hex,
                        "strict": True,
                        "commands": [item["command"] for item in compiled["execution_steps"]]}})
        if script.get("completed_commands") != len(compiled["execution_steps"]) \
                or script.get("added_entities") != len(compiled["commands"]):
            raise ProtocolError("Synthetic script did not create three entities")
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
        audit = client.tool("ocs_read", {"ocs_session_id": session, "op": "audit",
                                         "parameters": {"target_format": "dwg", "target_version": "2018"}})
        if audit.get("ok") is not True:
            raise ProtocolError("Synthetic DWG audit failed")
        report["audit_summary"] = {key: audit.get(key) for key in
                                   ("status", "summary", "target", "manifest", "bounds",
                                    "unknown_entities")}
        destination = output / "synthetic-verified.dwg"
        saved = client.tool("ocs_execute", {"ocs_session_id": session,
            "request": {"op": "save_verified", "request_id": "l2-save-" + uuid.uuid4().hex,
                        "path": str(destination), "target_format": "dwg", "target_version": "2018"}})
        verified = saved.get("result", saved)
        if verified.get("verified") is not True or not destination.is_file():
            raise ProtocolError("Synthetic verified save failed")
        if semantic:
            by_type = verified.get("manifest", {}).get("by_type", {})
            if by_type.get("Arc") != 1 or by_type.get("Polyline") != 1:
                raise ProtocolError("Native primitives did not survive internal DWG reopen")
            report["native_primitives"]["reopened_types"] = {"Arc": 1, "Polyline": 1}
            if verified.get("manifest", {}).get("by_layer", {}).get("A-WALL") != 1:
                raise ProtocolError("Synthetic layer assignment did not survive DWG reopen")
            report["layer_fixture"]["reopened_count"] = 1
            if verified.get("manifest", {}).get("by_type", {}).get("Dimension") != 2:
                raise ProtocolError("Native dimensions did not survive DWG reopen")
            report["dimension_fixture"]["reopened_count"] = 1
            report["aligned_dimension_fixture"]["reopened_count"] = 1
            if verified.get("manifest", {}).get("by_type", {}).get("Block Reference") != 3:
                raise ProtocolError("Block references did not survive DWG reopen")
            report["block_fixture"]["reopened_count"] = 3
        actual_hash = hashlib.sha256(destination.read_bytes()).hexdigest().upper()
        if verified["sha256"].upper() != actual_hash:
            raise ProtocolError("Synthetic output hash differs from backend report")
        report.update({"status": "passed", "script": {"completed_commands": len(compiled["execution_steps"]),
                                                      "added_entities": len(compiled["commands"])},
                       "audit_ok": True,
                       "verified_output": {"path": str(destination), "sha256": actual_hash,
                                           "bytes": destination.stat().st_size,
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
        state = client.tool("ocs_read", {"ocs_session_id": session, "op": "state"})
        capture_path = (output / "capture.png").resolve()
        capture = client.capture_artifact(session, capture_path,
                                          document_id=state["document_id"],
                                          geometry_revision=state["geometry_revision"],
                                          camera_revision=state["camera_revision"])
        reference = artifact_ref(output, capture_path.name,
                                 document_id=capture["document_id"],
                                 geometry_revision=capture["geometry_revision"],
                                 camera_revision=capture["camera_revision"])
        if (reference["width"], reference["height"]) != (capture["width"], capture["height"]):
            raise ProtocolError("Capture PNG dimensions differ from MCP metadata")
        report["capture_artifact"] = reference
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
