"""Independently compare a scoped apartment door and dimensions by DWG handle."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from apartment_door_trial import validate_bundle
from multi_axis_chain_l4 import _close, _point
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha


class DoorL4Error(ValueError):
    pass


def assess(run: Path, image: Path, binary: Path, external_path: Path) -> dict:
    plan, compiled, metadata = validate_bundle(run, image, binary)
    if (json.loads((run / "model-plan.json").read_text(encoding="utf-8")) != plan or
            json.loads((run / "door-composite.json").read_text(encoding="utf-8")) != metadata):
        raise DoorL4Error("Saved composite differs from frozen source")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise DoorL4Error("Owned CAD evidence is absent or ambiguous")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    if (report.get("schema_version") != "m7-apartment-door-trial-1" or
            report.get("status") != "passed_scoped_door_l2" or
            report.get("acceptance_m7") is not False or
            report.get("gui_exited") is not True or
            report.get("freeze_sha256") != _file_sha(run / "freeze.json") or
            report.get("plan_sha256") != _file_sha(run / "model-plan.json") or
            report.get("composite_sha256") != _file_sha(run / "door-composite.json") or
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or
            cad.get("commands_sha256") != compiled["commands_sha256"] or
            len(handles) != 35 or
            set(handles) != {item["planspec_id"] for item in compiled["commands"]}):
        raise DoorL4Error("Frozen CAD run differs")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if (external.get("schema_version") != "mcp-autocad-audit-l4-17" or
            external.get("product") != "AutoCAD Core Console" or
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or
            external.get("input_unchanged") is not True or
            external.get("audit_zero_errors_zero_fixes") is not True or
            external.get("insunits") != 6 or external.get("unit_match") is not True or
            external.get("model_census_count") != 35 or
            external.get("model_types") != {"LINE": 27, "ARC": 1, "DIMENSION": 7} or
            external.get("layer_states", {}).get("OCS_DIM_REF", {}).get("color_aci", 0) >= 0 or
            external.get("census_done") is not True or
            external.get("census_sha256") != _file_sha(census_path) or
            external.get("forced_termination") is not False or
            external.get("exit_code") != 0 or
            external.get("verdict") != "audit_and_census_passed"):
        raise DoorL4Error("AutoCAD audit or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            fields = row.split("|")
            if len(fields) != 19 or fields[2] in census:
                raise DoorL4Error("AutoCAD census row differs")
            census[fields[2]] = fields
    if set(census) != set(handles.values()):
        raise DoorL4Error("AutoCAD handles differ")
    nodes = {item["id"]: (float(item["x"]), float(item["y"]), 0.0)
             for item in plan["nodes"]}
    dimensions = {item["id"]: item for item in plan["dimensions"]}
    placements = {item["dimension_id"]: item
                  for item in plan["dimension_placements"]}
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
                    measure.get("dxf_13") == fields[13] and
                    measure.get("dxf_14") == fields[14] and
                    style.get("name") == "OCS_AXIS_METRIC_FIXED" and
                    style.get("decimal_places") == 2 and
                    style.get("zero_suppression") == 0 and
                    style.get("text_height_m") == 0.25 and
                    style.get("arrow_size_m") == 0.08 and
                    style.get("gap_m") == 0.02)
        elif name == "door-swing":
            hinge = (*metadata["door_hinge_m"], 0.0)
            radius = float(metadata["door_opening_width_m"])
            same = (fields[1] == "ARC" and fields[3] == "A-DOOR" and
                    _close(_point(fields[9]), hinge) and
                    abs(float(fields[17]) - radius) <= 1e-6 and
                    abs(float(fields[11]) - math.pi / 2) <= 1e-6 and
                    abs(float(fields[18]) - math.pi) <= 1e-6)
        else:
            match = re.fullmatch(r"LINE ([-+\d.eE]+),([-+\d.eE]+) "
                                 r"([-+\d.eE]+),([-+\d.eE]+)",
                                 command["command"])
            if match is None:
                raise DoorL4Error("Compiled LINE command differs")
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            observed_a, observed_b = _point(fields[9]), _point(fields[16])
            same = (fields[1] == "LINE" and fields[3] == command["layer"] and
                    ((_close(observed_a, (x0, y0, 0.0)) and
                      _close(observed_b, (x1, y1, 0.0))) or
                     (_close(observed_b, (x0, y0, 0.0)) and
                      _close(observed_a, (x1, y1, 0.0)))))
        matched.append({"planspec_id": name, "handle": handles[name],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matched)
    return {"schema_version": "m7-apartment-door-l4-1",
            "status": "passed_scoped_l4" if count == 35 else "failed_scoped_l4",
            "acceptance_m7": False, "architectural_lines": 22,
            "door_leaf_lines": 1, "door_arcs": 1,
            "hidden_support_lines": 4, "native_dimensions": 7,
            "freeze_sha256": _file_sha(run / "freeze.json"),
            "report_sha256": _file_sha(run / "report.json"),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": 35,
            "geometry_comparison": matched}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verdict = assess(args.run_root.resolve(strict=True),
                     args.image.resolve(strict=True),
                     args.binary.resolve(strict=True),
                     args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(verdict, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({key: verdict[key] for key in
                      ("status", "geometry_matches", "geometry_total")}))
    if verdict["status"] != "passed_scoped_l4":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
