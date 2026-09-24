"""Compare a development five-bay reference grid with an AutoCAD census."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

from PIL import Image

from cli_development_trial import parse_cli_events
from measurement_grid import compile_five_bay
from owned_cad_executor import verify_owned_cad_evidence
from planspec import dry_run
from reserved_trial import _file_sha


class FiveBayL4Error(ValueError):
    pass


def _point(raw: str) -> tuple[float, float, float]:
    match = re.fullmatch(r"\(([-+\d.eE]+) ([-+\d.eE]+) ([-+\d.eE]+)\)", raw)
    if match is None:
        raise FiveBayL4Error("Census point has invalid syntax")
    value = tuple(float(item) for item in match.groups())
    if not all(math.isfinite(item) for item in value):
        raise FiveBayL4Error("Census point is nonfinite")
    return value


def _same(a, b) -> bool:
    return all(abs(x - y) <= 1e-6 for x, y in zip(a, b))


def assess(run: Path, image_path: Path, external_path: Path) -> dict:
    freeze_path = run / "freeze.json"
    events_path = run / "events.jsonl"
    prompt_path = run / "prompt.txt"
    report_path = run / "report.json"
    plan_path = run / "model-plan.json"
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    measurement, _ = parse_cli_events(events_path)
    with Image.open(image_path) as bitmap:
        expected_plan = compile_five_bay(measurement, frozen=frozen,
                                         image_width=bitmap.width,
                                         image_height=bitmap.height)
    if plan != expected_plan:
        raise FiveBayL4Error("CAD PlanSpec differs from frozen model measurements")
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise FiveBayL4Error("CAD evidence is absent or ambiguous")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    compiled = dry_run(plan)
    if frozen.get("shape") != "measurement_grid_five_bay_v1" or \
            frozen.get("acceptance_m7") is not False or \
            frozen.get("source_sha256") != _file_sha(image_path) or \
            frozen.get("prompt_sha256") != _file_sha(prompt_path) or \
            report.get("status") != "passed_scoped_cli_l3_cad_l2" or \
            report.get("gui_exited") is not True or \
            report.get("freeze_sha256") != _file_sha(freeze_path) or \
            report.get("source_sha256") != _file_sha(image_path) or \
            report.get("prompt_sha256") != _file_sha(prompt_path) or \
            report.get("events_sha256") != _file_sha(events_path) or \
            report.get("plan_sha256") != _file_sha(plan_path) or \
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            cad.get("commands_sha256") != compiled["commands_sha256"] or \
            len(handles) != 16 or set(handles) != {item["id"] for item in plan["lines"]}:
        raise FiveBayL4Error("Frozen development or CAD evidence differs")
    expected_stations = [0.0]
    for width in frozen["expected_widths_m"]:
        expected_stations.append(expected_stations[-1] + float(width))
    expected_depth = float(frozen["expected_depth_m"])
    expected_nodes = {(row, column): (x, row * expected_depth, 0.0)
                      for row in (0, 1) for column, x in enumerate(expected_stations)}
    actual_nodes = {item["id"]: (float(item["x"]), float(item["y"]), 0.0)
                    for item in plan["nodes"]}
    if set(actual_nodes) != {f"n{row}_{column}" for row in (0, 1) for column in range(6)} or \
            any(not _same(actual_nodes[f"n{row}_{column}"], point)
                                       for (row, column), point in expected_nodes.items()):
        raise FiveBayL4Error("CAD PlanSpec nodes differ from frozen metric oracle")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 16 or \
            external.get("model_types") != {"LINE": 16} or \
            external.get("census_done") is not True or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed" or \
            external.get("census_sha256") != _file_sha(census_path):
        raise FiveBayL4Error("AutoCAD audit, source or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            parts = row.split("|")
            if len(parts) != 19 or parts[2] in census:
                raise FiveBayL4Error("AutoCAD census row differs")
            census[parts[2]] = parts
    if set(census) != set(handles.values()):
        raise FiveBayL4Error("AutoCAD handles differ from CAD evidence")
    matched = []
    for line in plan["lines"]:
        parts = census[handles[line["id"]]]
        a, b = actual_nodes[line["start"]], actual_nodes[line["end"]]
        observed_a, observed_b = _point(parts[9]), _point(parts[16])
        same = (parts[1] == "LINE" and parts[3] == "0" and
                ((_same(a, observed_a) and _same(b, observed_b)) or
                 (_same(a, observed_b) and _same(b, observed_a))))
        matched.append({"planspec_id": line["id"], "handle": handles[line["id"]],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matched)
    return {"schema_version": "m7-five-bay-l4-1",
            "status": "passed_scoped_l4" if count == 16 else "failed_scoped_l4",
            "scope": "five_bay_reference_grid_only_not_full_plan",
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
    verdict = assess(args.run_root.resolve(strict=True),
                     args.image.resolve(strict=True),
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
