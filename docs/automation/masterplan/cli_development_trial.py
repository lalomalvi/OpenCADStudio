"""Evaluate one frozen Codex CLI image output, then draw it in an owned CAD GUI.

This is a development probe. CLI telemetry is not a direct Responses receipt.
The source image and model output remain under target/, outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image

from measurement_grid import compile_two_bay
from owned_cad_executor import OwnedCadExecutor, verify_owned_cad_evidence
from planspec import dry_run
from reserved_runner import Invocation
from reserved_trial import _file_sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_client import Client, ProtocolError, UncertainMutation  # noqa: E402


class CliTrialError(ValueError):
    pass


class CliAbstained(CliTrialError):
    pass


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise CliTrialError("Duplicate model JSON key")
        result[key] = value
    return result


def _reject_constant(_):
    raise CliTrialError("Nonfinite model number")


def _write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, sort_keys=True, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())


def parse_cli_events(path: Path) -> tuple[dict, dict]:
    if path.stat().st_size > 2_000_000:
        raise CliTrialError("CLI event stream exceeds limit")
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    if [item.get("type") for item in events] != [
            "thread.started", "turn.started", "item.completed", "turn.completed"]:
        raise CliTrialError("CLI produced missing or extra events")
    item = events[2].get("item")
    if not isinstance(item, dict) or item.get("type") != "agent_message" or \
            not isinstance(item.get("text"), str):
        raise CliTrialError("CLI has no single final model message")
    if item["text"].strip() == "UNSUPPORTED":
        raise CliAbstained("Model abstained under frozen prompt")
    try:
        plan = json.loads(item["text"], object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, ValueError) as error:
        raise CliTrialError("Model did not return strict PlanSpec JSON") from error
    usage = events[3].get("usage")
    if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or
            usage[key] < 0 for key in ("input_tokens", "cached_input_tokens",
                                     "output_tokens")):
        raise CliTrialError("CLI usage is missing")
    return plan, usage


def check_rectangle(plan: dict, width_px: int, height_px: int,
                    expected_width_m: float, expected_depth_m: float) -> dict:
    if not isinstance(plan, dict) or plan.get("schema_version") != "planspec-1" \
            or plan.get("units") != "m" or len(plan.get("nodes", [])) != 4 \
            or len(plan.get("lines", [])) != 4 or plan.get("circles") != [] \
            or plan.get("dimensions") != []:
        raise CliTrialError("Rectangle PlanSpec scope differs")
    compiled = dry_run(plan)
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 4:
        raise CliTrialError("Rectangle PlanSpec does not compile to four safe commands")
    nodes = {item["id"]: (float(item["x"]), float(item["y"]))
             for item in plan["nodes"]}
    edges = [(item["start"], item["end"]) for item in plan["lines"]]
    degree = {key: 0 for key in nodes}
    for start, end in edges:
        degree[start] += 1
        degree[end] += 1
    if any(value != 2 for value in degree.values()) or \
            len({frozenset(edge) for edge in edges}) != 4:
        raise CliTrialError("Rectangle contour is not a simple four-edge cycle")
    xs, ys = {value[0] for value in nodes.values()}, {value[1] for value in nodes.values()}
    if len(xs) != 2 or len(ys) != 2 or \
            set(nodes.values()) != {(x, y) for x in xs for y in ys} or \
            abs((max(xs) - min(xs)) - expected_width_m) > 0.001 or \
            abs((max(ys) - min(ys)) - expected_depth_m) > 0.001:
        raise CliTrialError("Measured rectangle differs from frozen criterion")
    for item in [*plan["nodes"], *plan["lines"]]:
        x0, y0, x1, y1 = item["source"]["region_px"]
        if x1 > width_px or y1 > height_px or not (x0 < x1 and y0 < y1):
            raise CliTrialError("Rectangle provenance region escapes the image")
    return compiled


def check_ct1(plan: dict, width_px: int, height_px: int) -> dict:
    return check_rectangle(plan, width_px, height_px, 0.20, 0.40)


def check_explicit_line_graph(plan: dict, width_px: int, height_px: int,
                              vertices: list, edges: list,
                              expected_regions: int) -> dict:
    """Compare a model graph to a private, frozen metric/topology oracle."""
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= 100 or \
            not isinstance(edges, list) or not 3 <= len(edges) <= 200 or \
            type(expected_regions) is not int or expected_regions < 1 or \
            not isinstance(plan, dict) or plan.get("schema_version") != "planspec-1" or \
            plan.get("units") != "m" or plan.get("origin") != {"x": 0, "y": 0} or \
            plan.get("circles") != [] or plan.get("dimensions") != [] or \
            len(plan.get("nodes", [])) != len(vertices) or \
            len(plan.get("lines", [])) != len(edges):
        raise CliTrialError("Frozen explicit line graph scope differs")
    points = []
    for vertex in vertices:
        if not isinstance(vertex, list) or len(vertex) != 2 or \
                any(type(value) not in {int, float} or not math.isfinite(value)
                    for value in vertex):
            raise CliTrialError("Frozen graph vertex is invalid")
        points.append(tuple(float(value) for value in vertex))
    if len(set(points)) != len(points):
        raise CliTrialError("Frozen graph vertices duplicate")
    expected_edges = set()
    adjacency = {index: set() for index in range(len(points))}
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2 or \
                any(type(index) is not int or not 0 <= index < len(points)
                    for index in edge) or edge[0] == edge[1]:
            raise CliTrialError("Frozen graph edge is invalid")
        key = frozenset(edge)
        if key in expected_edges:
            raise CliTrialError("Frozen graph edge duplicates")
        expected_edges.add(key)
        adjacency[edge[0]].add(edge[1])
        adjacency[edge[1]].add(edge[0])
    visited = {0}
    frontier = [0]
    while frontier:
        for neighbor in adjacency[frontier.pop()]:
            if neighbor not in visited:
                visited.add(neighbor)
                frontier.append(neighbor)
    if len(visited) != len(points) or \
            len(edges) - len(points) + 1 != expected_regions:
        raise CliTrialError("Frozen graph does not contain the stated regions")
    compiled = dry_run(plan)
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or \
            len(compiled["commands"]) != len(edges):
        raise CliTrialError("Model graph is not executable")
    mapping = {}
    used = set()
    for node in plan["nodes"]:
        actual = float(node["x"]), float(node["y"])
        matches = [index for index, expected in enumerate(points)
                   if max(abs(actual[axis] - expected[axis])
                          for axis in (0, 1)) <= 0.001]
        if len(matches) != 1 or matches[0] in used:
            raise CliTrialError("Model graph coordinate differs from oracle")
        mapping[node["id"]] = matches[0]
        used.add(matches[0])
    observed_edges = [frozenset((mapping[line["start"]],
                                 mapping[line["end"]]))
                      for line in plan["lines"]]
    if len(set(observed_edges)) != len(edges) or \
            set(observed_edges) != expected_edges:
        raise CliTrialError("Model graph topology differs from oracle")
    for item in [*plan["nodes"], *plan["lines"]]:
        x0, y0, x1, y1 = item["source"]["region_px"]
        if x1 > width_px or y1 > height_px or not (x0 < x1 and y0 < y1):
            raise CliTrialError("Model graph provenance region escapes image")
    return compiled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    root, image, binary = (value.resolve(strict=True)
                           for value in (args.run_root, args.image, args.binary))
    frozen = json.loads((root / "freeze.json").read_text(encoding="utf-8"))
    prompt = root / "prompt.txt"
    events = root / "events.jsonl"
    if frozen.get("schema_version") != "m7-cli-development-freeze-1" or \
            not isinstance(frozen.get("case_id"), str) or \
            not frozen["case_id"] or \
            frozen.get("requested_model") != "gpt-6-luna" or \
            frozen.get("effort") != "medium" or \
            frozen.get("acceptance_m7") is not False or \
            _file_sha(image) != frozen.get("source_sha256") or \
            _file_sha(prompt) != frozen.get("prompt_sha256") or \
            ("cad_binary_sha256" in frozen and
             _file_sha(binary) != frozen["cad_binary_sha256"]) or \
            ("measurement_compiler_sha256" in frozen and
             _file_sha(Path(__file__).with_name("measurement_grid.py")) !=
             frozen["measurement_compiler_sha256"]) or \
            ("validator_sha256" in frozen and
             _file_sha(Path(__file__).resolve(strict=True)) !=
             frozen["validator_sha256"]):
        raise CliTrialError("Frozen development input changed")
    try:
        plan, usage = parse_cli_events(events)
        with Image.open(image) as bitmap:
            width_px, height_px = bitmap.size
        output_kind = "planspec"
        if frozen.get("shape") == "explicit_line_graph_v1":
            compiled = check_explicit_line_graph(
                plan, width_px, height_px, frozen["expected_vertices"],
                frozen["expected_edges"], frozen["expected_regions"])
        elif frozen.get("shape") == "measurement_grid_two_bay_v1":
            plan = compile_two_bay(plan, frozen=frozen,
                                   image_width=width_px,
                                   image_height=height_px)
            compiled = check_explicit_line_graph(
                plan, width_px, height_px, frozen["expected_vertices"],
                frozen["expected_edges"], frozen["expected_regions"])
            output_kind = "typed_measurements_compiled_deterministically"
        elif frozen.get("shape", "rectangle") == "rectangle":
            compiled = check_rectangle(plan, width_px, height_px,
                                       float(frozen["expected_width_m"]),
                                       float(frozen["expected_depth_m"]))
        else:
            raise CliTrialError("Frozen shape contract is unsupported")
    except (CliTrialError, KeyError, TypeError, ValueError) as error:
        failed = {"schema_version": "m7-cli-development-trial-1",
                  "status": "abstained" if isinstance(error, CliAbstained)
                            else "failed_plan_gate", "case_id": frozen["case_id"],
                  "acceptance_m7": False, "source_sha256": _file_sha(image),
                  "prompt_sha256": _file_sha(prompt),
                  "freeze_sha256": _file_sha(root / "freeze.json"),
                  "events_sha256": _file_sha(events),
                  "requested_model": "gpt-6-luna", "effort": "medium",
                  "effective_model": "unverified_by_cli_jsonl",
                  "error_type": type(error).__name__,
                  "error_message": str(error)[:300]}
        _write_new(root / "report.json", failed)
        print(json.dumps(failed, indent=2))
        return
    _write_new(root / "model-plan.json", plan)
    reuse_path = root / "reuse-origin.json"
    if reuse_path.exists():
        reuse = json.loads(reuse_path.read_text(encoding="utf-8"))
        if reuse.get("events_sha256") != _file_sha(events) or \
                reuse.get("source_report_sha256", "") == "":
            raise CliTrialError("Reused model evidence is not bound")
    else:
        reuse = None
    profile, temporary, cad_root = (root / name for name in ("profile", "temp", "cad"))
    for path in (profile, temporary, cad_root):
        path.mkdir(exist_ok=False)
    environment = os.environ.copy()
    environment.update({"APPDATA": str(profile), "LOCALAPPDATA": str(profile),
                        "TEMP": str(temporary), "TMP": str(temporary)})
    report = {"schema_version": "m7-cli-development-trial-1", "status": "failed",
              "case_id": frozen["case_id"],
              "acceptance_m7": False, "requested_model": "gpt-6-luna",
              "effective_model": "unverified_by_cli_jsonl", "effort": "medium",
              "source_sha256": _file_sha(image), "prompt_sha256": _file_sha(prompt),
              "freeze_sha256": _file_sha(root / "freeze.json"),
              "events_sha256": _file_sha(events), "binary_sha256": _file_sha(binary),
              "plan_sha256": _file_sha(root / "model-plan.json"),
              "model_output_kind": output_kind,
              "model_reuse": reuse,
              "usage_cli_aggregate": usage, "l3_plan_gate": "passed_scoped",
              "geometry_check": "passed_scoped", "cad_status": "pending"}
    gui = subprocess.Popen([str(binary), "--new-instance"], cwd=binary.parent.parent.parent,
                           env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = Client(binary, environment=environment)
    try:
        client.handshake()
        selected = client.ready_session(wait_for_existing=True, timeout=90)
        if selected.get("process_id") != gui.pid:
            raise CliTrialError("Owned CAD process identity differs")
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        for _ in range(6):
            if not state.get("modal"):
                break
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "action", "request_id": "cli-modal-" + uuid.uuid4().hex,
                            "name": "close_modal"}})
            state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                              "op": "state"})
        if state.get("modal"):
            raise CliTrialError("Owned CAD modal remained open")
        request_id = "cli-" + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]
        invocation = Invocation("development", frozen["case_id"], 1, request_id,
                                image, prompt, binary, "gpt-6-luna", "medium",
                                _file_sha(image), _file_sha(prompt), _file_sha(binary))
        evidence_path = OwnedCadExecutor(client, gui, binary, cad_root,
                                         capture_viewport=True)(invocation, compiled)
        evidence = verify_owned_cad_evidence(evidence_path)
        report.update({"cad_status": "passed_l2_internal",
                       "cad_evidence_sha256": _file_sha(evidence_path),
                       "dwg_sha256": evidence["dwg"]["sha256"],
                       "capture_sha256": evidence["capture"]["sha256"],
                       "added_entities": evidence["added_entities"],
                       "session_pid": gui.pid})
        state = client.tool("ocs_read", {"ocs_session_id": selected["session_id"],
                                          "op": "state"})
        report["dirty_before_close"] = any(doc.get("dirty") for doc in
                                            state.get("documents", []))
        if report["dirty_before_close"]:
            client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "save", "request_id": "cli-clean-save-" + uuid.uuid4().hex,
                            "path": str(root / "cleanup-save.dwg"),
                            "target_format": "dwg", "target_version": "2018"}})
        try:
            quit_result = client.tool("ocs_execute", {"ocs_session_id": selected["session_id"],
                "request": {"op": "run", "request_id": "cli-quit-" + uuid.uuid4().hex,
                            "cmd": "QUIT"}})
            report["quit_result"] = quit_result
        except (ProtocolError, UncertainMutation) as error:
            report["quit_error_type"] = type(error).__name__
        gui.wait(timeout=60)
        report["status"] = "passed_scoped_cli_l3_cad_l2"
        report["shutdown"] = "exited"
    except Exception as error:
        report["error_type"] = type(error).__name__
        report["error_message"] = str(error)[:300]
        raise
    finally:
        try:
            client.close()
        except ProtocolError:
            report["mcp_close"] = "error"
        if gui.poll() is None:
            gui.terminate()  # only this freshly launched child
            try:
                gui.wait(timeout=5)
                report["cleanup"] = "terminated_owned_child"
            except subprocess.TimeoutExpired:
                report["cleanup"] = "owned_child_still_running"
        report["gui_exited"] = gui.poll() is not None
        _write_new(root / "report.json", report)
        print(json.dumps({"report": str(root / "report.json"), **report}, indent=2))


if __name__ == "__main__":
    main()
