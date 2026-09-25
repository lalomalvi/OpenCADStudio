"""AutoCAD L4 comparison for a deterministic LINE/ARC/DIMLINEAR case."""

import argparse
import json
import math
from pathlib import Path
import re

from m8_case_cli import validate, verify
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha
from multi_axis_chain_l4 import _close, _point


LINE = re.compile(r"^LINE ([-+\d.eE]+),([-+\d.eE]+) ([-+\d.eE]+),([-+\d.eE]+)$")
ARC = re.compile(r"^ARC ([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+)$")
DIM = re.compile(r"^DIMLINEAR ([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+) "
                 r"([-+\d.eE]+),([-+\d.eE]+)$")


class MixedL4Error(ValueError):
    pass


def circle3(a, mid, b):
    ax, ay = a
    mx, my = mid
    bx, by = b
    denominator = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(denominator) < 1e-10:
        raise MixedL4Error("ARC points are collinear")
    a2, m2, b2 = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
    center = ((a2 * (my - by) + m2 * (by - ay) + b2 * (ay - my)) / denominator,
              (a2 * (bx - mx) + m2 * (ax - bx) + b2 * (mx - ax)) / denominator)
    angles = [math.atan2(point[1] - center[1], point[0] - center[0]) % (2 * math.pi)
              for point in (a, mid, b)]
    sweep = (angles[2] - angles[0]) % (2 * math.pi)
    if (angles[1] - angles[0]) % (2 * math.pi) > sweep:
        start, end = angles[2], angles[0]
    else:
        start, end = angles[0], angles[2]
    return center, math.dist(center, a), start, end


def angle_close(a, b):
    difference = abs((a - b) % (2 * math.pi))
    return min(difference, 2 * math.pi - difference) <= 1e-6


def assess(root: Path, plan_path: Path, binary: Path, external_path: Path) -> dict:
    local = verify(root, plan_path, binary)
    _, compiled = validate(root, plan_path, binary)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    dimensions = {item["id"]: item for item in plan.get("dimensions", [])}
    command_types = {}
    for command in compiled["commands"]:
        kind = ("LINE" if LINE.fullmatch(command["command"]) else
                "ARC" if ARC.fullmatch(command["command"]) else
                "DIMENSION" if DIM.fullmatch(command["command"]) else None)
        if kind is None:
            raise MixedL4Error("Unsupported command in mixed L4 case")
        command_types[kind] = command_types.get(kind, 0) + 1
    evidence_paths = list((root / "cad").glob("*.json"))
    if len(evidence_paths) != 1:
        raise MixedL4Error("Owned CAD evidence count differs")
    cad = verify_owned_cad_evidence(evidence_paths[0])
    handles = cad["handles_by_id"]
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    expected_count = len(compiled["commands"])
    if (external.get("product") != "AutoCAD Core Console"
            or external.get("input_sha256_before") != local["dwg_sha256"]
            or external.get("input_sha256_after") != local["dwg_sha256"]
            or external.get("input_unchanged") is not True
            or external.get("audit_zero_errors_zero_fixes") is not True
            or external.get("insunits") != 6 or external.get("unit_match") is not True
            or external.get("model_census_count") != expected_count
            or external.get("model_types") != command_types
            or external.get("census_sha256") != _file_sha(census_path)
            or external.get("forced_termination") is not False
            or external.get("exit_code") != 0
            or external.get("verdict") != "audit_and_census_passed"):
        raise MixedL4Error("AutoCAD audit, units or census integrity differs")
    if "OCS_DIM_REF" in {item["layer"] for item in compiled["commands"]} and \
            external.get("layer_states", {}).get("OCS_DIM_REF", {}).get("color_aci", 0) >= 0:
        raise MixedL4Error("Hidden reference layer became visible")
    rows = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ENTITY|"):
            fields = line.split("|")
            if len(fields) != 19 or fields[2] in rows:
                raise MixedL4Error("AutoCAD census row differs")
            rows[fields[2]] = fields
    if (len(rows) != expected_count or set(rows) != set(handles.values())
            or set(handles) != {command["planspec_id"] for command in compiled["commands"]}):
        raise MixedL4Error("AutoCAD handles differ from PlanSpec")
    comparisons = []
    for command in compiled["commands"]:
        name, layer = command["planspec_id"], command["layer"]
        fields = rows[handles[name]]
        raw = command["command"]
        if (match := LINE.fullmatch(raw)):
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            a, b = _point(fields[9]), _point(fields[16])
            same = (fields[1] == "LINE" and fields[3] == layer and
                    ((_close(a, (x0, y0, 0)) and _close(b, (x1, y1, 0))) or
                     (_close(b, (x0, y0, 0)) and _close(a, (x1, y1, 0)))))
        elif (match := ARC.fullmatch(raw)):
            values = [float(value) for value in match.groups()]
            center, radius, start, end = circle3(
                tuple(values[:2]), tuple(values[2:4]), tuple(values[4:6]))
            same = (fields[1] == "ARC" and fields[3] == layer
                    and _close(_point(fields[9]), (*center, 0))
                    and abs(float(fields[17]) - radius) <= 1e-6
                    and angle_close(float(fields[11]), start)
                    and angle_close(float(fields[18]), end))
        else:
            match = DIM.fullmatch(raw)
            values = [float(value) for value in match.groups()]
            dimension = dimensions.get(name)
            measure = external.get("dimension_measurements", {}).get(handles[name], {})
            style = external.get("dimension_styles", {}).get(handles[name], {})
            # AutoCAD stores the dimension-line endpoint in DXF 10, not the
            # DIMLINEAR placement click that appears in the compiled command.
            dimension_line_end = ((values[2], values[5], 0) if
                                  abs(values[2] - values[0]) >= abs(values[3] - values[1])
                                  else (values[4], values[3], 0))
            same = bool(dimension and fields[1] == "DIMENSION" and fields[3] == layer
                        and _close(_point(fields[13]), (values[0], values[1], 0))
                        and _close(_point(fields[14]), (values[2], values[3], 0))
                        and _close(_point(fields[9]), dimension_line_end)
                        and abs(float(fields[4]) - float(dimension["value"])) <= 1e-6
                        and measure.get("dxf_42") == fields[4]
                        and style.get("name") == "OCS_AXIS_METRIC_FIXED"
                        and style.get("decimal_places") == 2)
        comparisons.append({"planspec_id": name, "handle": handles[name],
                            "matched_1e_6": bool(same)})
    matches = sum(item["matched_1e_6"] for item in comparisons)
    return {"schema_version": "m8-deterministic-mixed-l4-1",
            "status": "passed_scoped_l4" if matches == expected_count else "failed_scoped_l4",
            "geometry_matches": matches, "geometry_total": expected_count,
            "geometry_comparison": comparisons,
            "contract_sha256": local["contract_sha256"],
            "report_sha256": local["report_sha256"],
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": local["dwg_sha256"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.run_root.resolve(strict=True), args.plan.resolve(strict=True),
                    args.binary.resolve(strict=True), args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"], result["geometry_matches"], result["geometry_total"])
    raise SystemExit(0 if result["status"] == "passed_scoped_l4" else 1)


if __name__ == "__main__":
    main()
