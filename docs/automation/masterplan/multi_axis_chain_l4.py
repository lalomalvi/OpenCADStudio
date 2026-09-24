"""Bind one synthetic axis-chain PlanSpec to owned CAD and AutoCAD DXF census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from owned_cad_executor import verify_owned_cad_evidence
from planspec import dry_run
from reserved_trial import _file_sha


class ChainL4Error(ValueError):
    pass


def _point(value: str) -> tuple[float, float, float]:
    matched = re.fullmatch(
        r"\(([-+\d.eE]+) ([-+\d.eE]+) ([-+\d.eE]+)\)", value)
    if not matched:
        raise ChainL4Error("External DXF point is invalid")
    return tuple(float(item) for item in matched.groups())


def _close(first, second) -> bool:
    return all(abs(a - b) <= 1e-6 for a, b in zip(first, second))


def assess(fixture_path: Path, l2_path: Path, external_path: Path) -> dict:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    compiled = dry_run(fixture)
    if not compiled["executable"] or compiled["dimension_compilation"] != {
            "status": "compiled_multi_axis_spans", "generated_parts": 3} or \
            len(compiled["commands"]) != 7:
        raise ChainL4Error("Synthetic PlanSpec chain differs")
    l2 = json.loads(l2_path.read_text(encoding="utf-8"))
    cad_files = list((l2_path.parent / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise ChainL4Error("Owned CAD evidence is missing or ambiguous")
    cad_path = cad_files[0].resolve(strict=True)
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    if l2.get("schema_version") != "m4-multi-axis-chain-l2-1" or \
            l2.get("status") != "passed_l2_internal" or \
            l2.get("fixture_sha256") != _file_sha(fixture_path) or \
            l2.get("commands_sha256") != compiled["commands_sha256"] or \
            l2.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            l2.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            l2.get("handles_by_id") != handles or \
            l2.get("gui_exited") is not True or l2.get("shutdown") != "exited":
        raise ChainL4Error("L2 chain report or nested CAD evidence differs")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 7 or \
            external.get("model_types") != {"DIMENSION": 3, "LINE": 4} or \
            external.get("census_done") is not True or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed" or \
            _file_sha(census_path) != external.get("census_sha256"):
        raise ChainL4Error("AutoCAD audit, source or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            parts = row.split("|")
            if len(parts) != 19 or parts[2] in census:
                raise ChainL4Error("External census entity differs")
            census[parts[2]] = parts
    if set(census) != set(handles.values()):
        raise ChainL4Error("External handles differ from PlanSpec")
    nodes = {item["id"]: (float(item["x"]), float(item["y"]), 0.0)
             for item in fixture["nodes"]}
    dimensions = {item["id"]: item for item in fixture["dimensions"]}
    placements = {item["dimension_id"]: item for item in fixture["dimension_placements"]}
    matched = []
    for command in compiled["commands"]:
        name = command["planspec_id"]
        parts = census[handles[name]]
        if name in dimensions:
            dimension = dimensions[name]
            a, b = nodes[dimension["start"]], nodes[dimension["end"]]
            offset = float(placements[name]["offset_m"])
            measurement = external.get("dimension_measurements", {}).get(handles[name], {})
            same = (parts[1] == "DIMENSION" and parts[3] == "0" and
                    abs(float(parts[4]) - float(dimension["value"])) <= 1e-6 and
                    _close(_point(parts[13]), a) and _close(_point(parts[14]), b) and
                    _close(_point(parts[9]), (b[0], offset, 0.0)) and
                    measurement.get("dxf_42") == parts[4] and
                    measurement.get("dxf_13") == parts[13] and
                    measurement.get("dxf_14") == parts[14] and
                    abs(float(l2["measures_before"][name]) - float(dimension["value"])) <= 1e-6 and
                    abs(float(l2["measures_after"][name]) - float(dimension["value"])) <= 1e-6)
        else:
            match = re.fullmatch(r"LINE ([-+\d.eE]+),([-+\d.eE]+) ([-+\d.eE]+),([-+\d.eE]+)",
                                 command["command"])
            if match is None:
                raise ChainL4Error("Compiled wall command differs")
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            actual_a, actual_b = _point(parts[9]), _point(parts[16])
            same = (parts[1] == "LINE" and parts[3] == "0" and
                    ((_close(actual_a, (x0, y0, 0.0)) and
                      _close(actual_b, (x1, y1, 0.0))) or
                     (_close(actual_b, (x0, y0, 0.0)) and
                      _close(actual_a, (x1, y1, 0.0)))))
        matched.append({"planspec_id": name, "handle": handles[name],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matched)
    return {"schema_version": "m4-multi-axis-chain-l4-1",
            "status": "passed_scoped_l4" if count == 7 else "failed_scoped_l4",
            "fixture_sha256": _file_sha(fixture_path),
            "l2_report_sha256": _file_sha(l2_path),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": len(matched),
            "geometry_comparison": matched,
            "scope": "one_synthetic_horizontal_wall_three_linear_axis_dimensions"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--l2", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.fixture.resolve(strict=True), args.l2.resolve(strict=True),
                    args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(result, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({key: result[key] for key in
                      ("status", "geometry_matches", "geometry_total", "dwg_sha256")}))
    if result["status"] != "passed_scoped_l4":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
