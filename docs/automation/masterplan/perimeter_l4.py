"""Bind a Luna pixel perimeter to a synthetic AutoCAD LINE census."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from cli_development_trial import parse_cli_events
from five_bay_l4 import _point, _same
from owned_cad_executor import verify_owned_cad_evidence
from pixel_perimeter import compile_visible_perimeter
from planspec import dry_run
from reserved_trial import _file_sha


class PerimeterL4Error(ValueError):
    pass


def assess(run: Path, image: Path, external_path: Path) -> dict:
    freeze_path, prompt_path, events_path = (run / name for name in
                                            ("freeze.json", "prompt.txt", "events.jsonl"))
    report_path, plan_path = run / "report.json", run / "model-plan.json"
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    observation, _ = parse_cli_events(events_path)
    with Image.open(image) as bitmap:
        expected = compile_visible_perimeter(observation, frozen=frozen,
                                             image_width=bitmap.width,
                                             image_height=bitmap.height)
    if plan != expected:
        raise PerimeterL4Error("PlanSpec differs from frozen pixel compilation")
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise PerimeterL4Error("CAD evidence is absent or ambiguous")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    compiled = dry_run(plan)
    if frozen.get("shape") != "visible_perimeter_pixels_v1" or \
            frozen.get("acceptance_m7") is not False or \
            frozen.get("source_sha256") != _file_sha(image) or \
            frozen.get("prompt_sha256") != _file_sha(prompt_path) or \
            report.get("status") != "passed_scoped_cli_l3_cad_l2" or \
            report.get("gui_exited") is not True or \
            report.get("freeze_sha256") != _file_sha(freeze_path) or \
            report.get("events_sha256") != _file_sha(events_path) or \
            report.get("plan_sha256") != _file_sha(plan_path) or \
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            cad.get("commands_sha256") != compiled["commands_sha256"] or \
            len(handles) != 13 or set(handles) != {line["id"] for line in plan["lines"]}:
        raise PerimeterL4Error("Frozen run or CAD evidence differs")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 13 or \
            external.get("model_types") != {"LINE": 13} or \
            external.get("census_done") is not True or \
            external.get("census_sha256") != _file_sha(census_path) or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed":
        raise PerimeterL4Error("AutoCAD audit or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            parts = row.split("|")
            if len(parts) != 19 or parts[2] in census:
                raise PerimeterL4Error("AutoCAD census row differs")
            census[parts[2]] = parts
    if set(census) != set(handles.values()):
        raise PerimeterL4Error("AutoCAD handles differ")
    nodes = {node["id"]: (float(node["x"]), float(node["y"]), 0.0)
             for node in plan["nodes"]}
    matches = []
    for line in plan["lines"]:
        parts = census[handles[line["id"]]]
        a, b = nodes[line["start"]], nodes[line["end"]]
        observed_a, observed_b = _point(parts[9]), _point(parts[16])
        same = (parts[1] == "LINE" and parts[3] == "0" and
                ((_same(a, observed_a) and _same(b, observed_b)) or
                 (_same(a, observed_b) and _same(b, observed_a))))
        matches.append({"planspec_id": line["id"], "handle": handles[line["id"]],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matches)
    return {"schema_version": "m7-perimeter-l4-1",
            "status": "passed_scoped_l4" if count == 13 else "failed_scoped_l4",
            "scope": "visible_outer_reference_only_not_full_plan",
            "acceptance_m7": False,
            "freeze_sha256": _file_sha(freeze_path),
            "report_sha256": _file_sha(report_path),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": 13,
            "geometry_comparison": matches}


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
