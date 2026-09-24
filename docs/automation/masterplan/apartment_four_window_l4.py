"""Compare every entity of the schematic window apartment in AutoCAD."""

import argparse
import json
import math
from pathlib import Path
import re

from apartment_west_window_compiler import compose
from west_window_observation import score
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha
from multi_axis_chain_l4 import _close, _point


class WindowL4Error(ValueError):
    pass


def assess(run, image, binary, external_path):
    base = run.parent / "apartment-integrated-three-windows-v1"
    observed = run.parent / "apartment-west-window-v1"
    freeze = json.loads((run / "freeze.json").read_text(encoding="utf-8"))
    code = Path(__file__).parent
    bound = {"source_sha256": _file_sha(image),
             "base_plan_sha256": _file_sha(base / "model-plan.json"),
             "base_report_sha256": _file_sha(base / "report.json"),
             "observation_freeze_sha256": _file_sha(observed / "freeze.json"),
             "observation_events_sha256": _file_sha(observed / "events.jsonl"),
             "observation_verdict_sha256": _file_sha(observed / "verdict.json"),
             "compiler_sha256": _file_sha(code / "apartment_west_window_compiler.py"),
             "extension_sha256": _file_sha(code / "window_extension.py"),
             "runner_sha256": _file_sha(code / "apartment_four_window_trial.py"),
             "planspec_sha256": _file_sha(code / "planspec.py"),
             "schema_sha256": _file_sha(code / "planspec-v11.schema.json"),
             "observation_gate_sha256": _file_sha(code / "west_window_observation.py"),
             "cad_binary_sha256": _file_sha(binary)}
    if freeze.get("schema_version") != "m7-apartment-four-window-trial-freeze-1" or \
            any(freeze.get(key) != value for key, value in bound.items()):
        raise WindowL4Error("Frozen source, code or binary differs")
    observation = score(image, observed, persist=False)
    if observation["status"] != "passed_observation_only":
        raise WindowL4Error("Window observation did not pass")
    plan, compiled, window = compose(
        json.loads((base / "model-plan.json").read_text(encoding="utf-8")), observation)
    if (plan != json.loads((run / "model-plan.json").read_text(encoding="utf-8")) or
            window != json.loads((run / "window-composite.json").read_text(encoding="utf-8"))):
        raise WindowL4Error("Saved PlanSpec differs from frozen observation")
    reports = list((run / "cad").glob("*.json"))
    if len(reports) != 1:
        raise WindowL4Error("CAD evidence is absent or ambiguous")
    cad = verify_owned_cad_evidence(reports[0])
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    handles = cad["handles_by_id"]
    if (report.get("schema_version") != "m7-apartment-four-window-trial-1" or
            report.get("status") != "passed_scoped_four_window_l2" or
            report.get("gui_exited") is not True or
            report.get("plan_sha256") != _file_sha(run / "model-plan.json") or
            report.get("cad_evidence_sha256") != _file_sha(reports[0]) or
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or
            cad.get("commands_sha256") != compiled["commands_sha256"] or
            len(handles) != 55 or
            set(handles) != {item["planspec_id"] for item in compiled["commands"]}):
        raise WindowL4Error("CAD report differs from PlanSpec")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if (external.get("product") != "AutoCAD Core Console" or
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or
            external.get("input_unchanged") is not True or
            external.get("audit_zero_errors_zero_fixes") is not True or
            external.get("insunits") != 6 or external.get("unit_match") is not True or
            external.get("model_census_count") != 55 or
            external.get("model_types") != {"LINE": 47, "ARC": 1, "DIMENSION": 7} or
            external.get("layer_states", {}).get("OCS_DIM_REF", {}).get("color_aci", 0) >= 0 or
            external.get("census_sha256") != _file_sha(census_path) or
            external.get("forced_termination") is not False or
            external.get("exit_code") != 0 or
            external.get("verdict") != "audit_and_census_passed"):
        raise WindowL4Error("AutoCAD audit or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            fields = row.split("|")
            if len(fields) != 19 or fields[2] in census:
                raise WindowL4Error("AutoCAD census row differs")
            census[fields[2]] = fields
    if set(census) != set(handles.values()):
        raise WindowL4Error("AutoCAD handles differ")
    nodes = {item["id"]: (float(item["x"]), float(item["y"]), 0.0)
             for item in plan["nodes"]}
    dimensions = {item["id"]: item for item in plan["dimensions"]}
    placements = {item["dimension_id"]: item for item in plan["dimension_placements"]}
    matched = []
    for command in compiled["commands"]:
        name = command["planspec_id"]
        fields = census[handles[name]]
        if name in dimensions:
            dimension = dimensions[name]
            a, b = nodes[dimension["start"]], nodes[dimension["end"]]
            location = (b[0], a[1] + float(placements[name]["offset_m"]), 0.0)
            measure = external.get("dimension_measurements", {}).get(handles[name], {})
            style = external.get("dimension_styles", {}).get(handles[name], {})
            same = (fields[1] == "DIMENSION" and fields[3] == "0" and
                    abs(float(fields[4]) - float(dimension["value"])) <= 1e-6 and
                    _close(_point(fields[13]), a) and _close(_point(fields[14]), b) and
                    _close(_point(fields[9]), location) and
                    measure.get("dxf_42") == fields[4] and
                    style.get("name") == "OCS_AXIS_METRIC_FIXED" and
                    style.get("decimal_places") == 2)
        elif name == "door-swing":
            hinge = nodes["door-jamb-top"]
            leaf = nodes["door-leaf-tip"]
            radius = math.dist(hinge, leaf)
            same = (fields[1] == "ARC" and fields[3] == "A-DOOR" and
                    _close(_point(fields[9]), hinge) and
                    abs(float(fields[17]) - radius) <= 1e-6 and
                    abs(float(fields[11]) - math.pi/2) <= 1e-6 and
                    abs(float(fields[18]) - math.pi) <= 1e-6)
        else:
            match = re.fullmatch(r"LINE ([-+\d.eE]+),([-+\d.eE]+) "
                                 r"([-+\d.eE]+),([-+\d.eE]+)", command["command"])
            if match is None:
                raise WindowL4Error("Compiled LINE command differs")
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            a, b = _point(fields[9]), _point(fields[16])
            same = (fields[1] == "LINE" and fields[3] == command["layer"] and
                    ((_close(a, (x0, y0, 0)) and _close(b, (x1, y1, 0))) or
                     (_close(b, (x0, y0, 0)) and _close(a, (x1, y1, 0)))))
        matched.append({"planspec_id": name, "handle": handles[name],
                        "matched_1e_6": bool(same)})
    count = sum(row["matched_1e_6"] for row in matched)
    return {"schema_version": "m7-apartment-four-window-l4-1",
            "status": "passed_scoped_l4" if count == 55 else "failed_scoped_l4",
            "acceptance_m7": False, "geometry_matches": count, "geometry_total": 55,
            "window": window, "geometry_comparison": matched,
            "freeze_sha256": _file_sha(run / "freeze.json"),
            "report_sha256": _file_sha(run / "report.json"),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.run_root.resolve(strict=True), args.image.resolve(strict=True),
                    args.binary.resolve(strict=True), args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"], result["geometry_matches"], result["geometry_total"])
    raise SystemExit(0 if result["status"] == "passed_scoped_l4" else 1)
