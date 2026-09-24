"""Bind six image-measured spans and their native CAD dimensions to AutoCAD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from PIL import Image

from cli_development_trial import parse_cli_events
from measurement_axis_chain import compile_bottom_chain
from multi_axis_chain_l4 import _close, _point
from owned_cad_executor import verify_owned_cad_evidence
from planspec import dry_run
from reserved_trial import _file_sha


class BottomChainL4Error(ValueError):
    pass


def assess(run: Path, image_path: Path, external_path: Path) -> dict:
    freeze_path, prompt_path = run / "freeze.json", run / "prompt.txt"
    events_path, report_path = run / "events.jsonl", run / "report.json"
    plan_path = run / "model-plan.json"
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    measurement, usage = parse_cli_events(events_path)
    with Image.open(image_path) as bitmap:
        expected_plan = compile_bottom_chain(measurement, frozen=frozen,
                                             image_width=bitmap.width,
                                             image_height=bitmap.height)
    compiled = dry_run(plan)
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise BottomChainL4Error("Owned CAD evidence differs")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    if frozen.get("shape") != "bottom_axis_chain_six_v1" or \
            frozen.get("acceptance_m7") is not False or \
            frozen.get("source_sha256") != _file_sha(image_path) or \
            frozen.get("prompt_sha256") != _file_sha(prompt_path) or \
            plan != expected_plan or not compiled["executable"] or \
            compiled["dimension_graph"]["status"] != "satisfied" or \
            compiled["dimension_compilation"] != {
                "status": "compiled_multi_axis_spans", "generated_parts": 7} or \
            report.get("status") != "passed_scoped_cli_l3_cad_l2" or \
            report.get("gui_exited") is not True or \
            report.get("source_sha256") != _file_sha(image_path) or \
            report.get("prompt_sha256") != _file_sha(prompt_path) or \
            report.get("freeze_sha256") != _file_sha(freeze_path) or \
            report.get("events_sha256") != _file_sha(events_path) or \
            report.get("plan_sha256") != _file_sha(plan_path) or \
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            report.get("usage_cli_aggregate") != usage or \
            cad.get("commands_sha256") != compiled["commands_sha256"] or \
            len(handles) != 11 or set(handles) != \
            {item["planspec_id"] for item in compiled["commands"]}:
        raise BottomChainL4Error("Frozen model or CAD evidence differs")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 11 or \
            external.get("model_types") != {"LINE": 4, "DIMENSION": 7} or \
            external.get("census_done") is not True or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed" or \
            external.get("census_sha256") != _file_sha(census_path):
        raise BottomChainL4Error("AutoCAD audit, source or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            parts = row.split("|")
            if len(parts) != 19 or parts[2] in census:
                raise BottomChainL4Error("AutoCAD census row differs")
            census[parts[2]] = parts
    if set(census) != set(handles.values()):
        raise BottomChainL4Error("AutoCAD handles differ")
    nodes = {item["id"]: (float(item["x"]), float(item["y"]), 0.0)
             for item in plan["nodes"]}
    dimensions = {item["id"]: item for item in plan["dimensions"]}
    placements = {item["dimension_id"]: item for item in plan["dimension_placements"]}
    matched = []
    for command in compiled["commands"]:
        name = command["planspec_id"]
        parts = census[handles[name]]
        if name in dimensions:
            dimension = dimensions[name]
            a, b = nodes[dimension["start"]], nodes[dimension["end"]]
            measurement = external.get("dimension_measurements", {}).get(handles[name], {})
            same = (parts[1] == "DIMENSION" and parts[3] == "0" and
                    abs(float(parts[4]) - float(dimension["value"])) <= 1e-6 and
                    _close(_point(parts[13]), a) and _close(_point(parts[14]), b) and
                    _close(_point(parts[9]), (b[0], float(placements[name]["offset_m"]), 0.0)) and
                    measurement.get("dxf_42") == parts[4] and
                    measurement.get("dxf_13") == parts[13] and
                    measurement.get("dxf_14") == parts[14])
        else:
            match = re.fullmatch(r"LINE ([-+\d.eE]+),([-+\d.eE]+) ([-+\d.eE]+),([-+\d.eE]+)",
                                 command["command"])
            if match is None:
                raise BottomChainL4Error("Compiled support command differs")
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            observed_a, observed_b = _point(parts[9]), _point(parts[16])
            same = (parts[1] == "LINE" and parts[3] == "0" and
                    ((_close(observed_a, (x0, y0, 0.0)) and
                      _close(observed_b, (x1, y1, 0.0))) or
                     (_close(observed_b, (x0, y0, 0.0)) and
                      _close(observed_a, (x1, y1, 0.0)))))
        matched.append({"planspec_id": name, "handle": handles[name],
                        "matched_1e_6": bool(same)})
    count = sum(row["matched_1e_6"] for row in matched)
    return {"schema_version": "m7-bottom-axis-chain-l4-1",
            "status": "passed_scoped_l4" if count == 11 else "failed_scoped_l4",
            "scope": "six_image_measured_bottom_spans_reference_only",
            "acceptance_m7": False,
            "freeze_sha256": _file_sha(freeze_path),
            "report_sha256": _file_sha(report_path),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": len(matched),
            "geometry_comparison": matched}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verdict = assess(args.run_root.resolve(strict=True), args.image.resolve(strict=True),
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
