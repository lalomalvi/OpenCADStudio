"""Compare the post-selected apartment outline and three wall references to AutoCAD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from cli_development_trial import parse_cli_events
from five_bay_l4 import _point, _same
from owned_cad_executor import verify_owned_cad_evidence
from pixel_interior_walls import compile_interior_walls
from pixel_perimeter import compile_visible_perimeter
from planspec import dry_run
from reserved_trial import _file_sha


class InteriorL4Error(ValueError):
    pass


def assess(run: Path, image: Path, external_path: Path) -> dict:
    base = run.parent / "apartment-visible-perimeter-v3"
    frozen = json.loads((run / "freeze.json").read_text(encoding="utf-8"))
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    plan = json.loads((run / "model-plan.json").read_text(encoding="utf-8"))
    observed, _ = parse_cli_events(run / "events.jsonl")
    base_observed, _ = parse_cli_events(base / "events.jsonl")
    if frozen.get("shape") != "apartment_interior_discovery_derived_three_v1" or \
            frozen.get("selected_segment_ids") != ["s1", "s2", "s3"] or \
            frozen.get("discovery_events_sha256") != _file_sha(run / "events.jsonl") or \
            _file_sha(run / "events.jsonl") != _file_sha(
                run.parent / "apartment-interior-wall-discovery-v1" / "events.jsonl") or \
            len(observed.get("segments", [])) != 6 or \
            [item.get("id") for item in observed["segments"]] != \
                [f"s{i}" for i in range(1, 7)] or \
            frozen.get("source_sha256") != _file_sha(image) or \
            frozen.get("prompt_sha256") != _file_sha(run / "prompt.txt") or \
            frozen.get("base_freeze_sha256") != _file_sha(base / "freeze.json") or \
            frozen.get("base_events_sha256") != _file_sha(base / "events.jsonl") or \
            frozen.get("base_report_sha256") != _file_sha(base / "report.json"):
        raise InteriorL4Error("Frozen source or post hoc selection differs")
    with Image.open(image) as bitmap:
        perimeter = compile_visible_perimeter(
            base_observed,
            frozen=json.loads((base / "freeze.json").read_text(encoding="utf-8")),
            image_width=bitmap.width, image_height=bitmap.height)
        expected = compile_interior_walls(
            {**observed, "segments": observed["segments"][:3]},
            perimeter=perimeter, frozen=frozen,
            image_width=bitmap.width, image_height=bitmap.height)
    if plan != expected:
        raise InteriorL4Error("Saved PlanSpec differs from frozen compilation")
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise InteriorL4Error("CAD evidence is absent or ambiguous")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    compiled = dry_run(plan)
    if report.get("status") != "passed_scoped_cli_l3_cad_l2" or \
            report.get("gui_exited") is not True or \
            report.get("acceptance_m7") is not False or \
            report.get("freeze_sha256") != _file_sha(run / "freeze.json") or \
            report.get("events_sha256") != _file_sha(run / "events.jsonl") or \
            report.get("plan_sha256") != _file_sha(run / "model-plan.json") or \
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            report.get("model_reuse", {}).get("selection") != \
                "post_hoc_first_three_of_six_not_model_retrial" or \
            cad.get("commands_sha256") != compiled["commands_sha256"] or \
            len(handles) != 16 or set(handles) != \
                {line["id"] for line in plan["lines"]}:
        raise InteriorL4Error("CAD execution or report differs")
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
            external.get("census_sha256") != _file_sha(census_path) or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed":
        raise InteriorL4Error("AutoCAD audit or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            parts = row.split("|")
            if len(parts) != 19 or parts[2] in census:
                raise InteriorL4Error("AutoCAD census row differs")
            census[parts[2]] = parts
    if set(census) != set(handles.values()):
        raise InteriorL4Error("AutoCAD handles differ")
    nodes = {node["id"]: (float(node["x"]), float(node["y"]), 0.0)
             for node in plan["nodes"]}
    matches = []
    for line in plan["lines"]:
        parts = census[handles[line["id"]]]
        a, b = nodes[line["start"]], nodes[line["end"]]
        p, q = _point(parts[9]), _point(parts[16])
        same = (parts[1] == "LINE" and parts[3] == "0" and
                ((_same(a, p) and _same(b, q)) or
                 (_same(a, q) and _same(b, p))))
        matches.append({"planspec_id": line["id"],
                        "handle": handles[line["id"]],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matches)
    return {"schema_version": "m7-interior-walls-l4-1",
            "status": "passed_scoped_l4" if count == 16 else "failed_scoped_l4",
            "scope": "outer_reference_plus_three_post_selected_wall_centerlines",
            "acceptance_m7": False, "post_hoc_selection": True,
            "freeze_sha256": _file_sha(run / "freeze.json"),
            "report_sha256": _file_sha(run / "report.json"),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": 16,
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
