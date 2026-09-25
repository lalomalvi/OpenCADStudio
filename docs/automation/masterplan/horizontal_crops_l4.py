"""Bind five crop traces and a saved synthetic DWG to AutoCAD LINE handles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from five_bay_l4 import _point, _same
from horizontal_crops_trial import validate_bundle
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha


class HorizontalL4Error(ValueError):
    pass


def assess(run: Path, image: Path, binary: Path, external_path: Path) -> dict:
    plan, result = validate_bundle(run, image, binary)
    saved = json.loads((run / "model-plan.json").read_text(encoding="utf-8"))
    if saved != plan:
        raise HorizontalL4Error("Saved plan differs from frozen crop bundle")
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    cad_files = list((run / "cad").glob("*.json"))
    if len(cad_files) != 1:
        raise HorizontalL4Error("Owned CAD evidence is absent or ambiguous")
    cad_path = cad_files[0]
    cad = verify_owned_cad_evidence(cad_path)
    handles = cad["handles_by_id"]
    if report.get("schema_version") != "m7-horizontal-bundle-trial-1" or \
            report.get("status") != "passed_scoped_cli_l3_cad_l2" or \
            report.get("acceptance_m7") is not False or \
            report.get("gui_exited") is not True or \
            report.get("freeze_sha256") != _file_sha(run / "freeze.json") or \
            report.get("plan_sha256") != _file_sha(run / "model-plan.json") or \
            report.get("cad_evidence_sha256") != _file_sha(cad_path) or \
            report.get("dwg_sha256") != cad["dwg"]["sha256"] or \
            cad.get("commands_sha256") != result["compiled"]["commands_sha256"] or \
            len(handles) != 21 or set(handles) != \
                {line["id"] for line in plan["lines"]}:
        raise HorizontalL4Error("Owned CAD evidence differs")
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 21 or \
            external.get("model_types") != {"LINE": 21} or \
            external.get("census_done") is not True or \
            external.get("census_sha256") != _file_sha(census_path) or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed":
        raise HorizontalL4Error("AutoCAD audit or census differs")
    census = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if row.startswith("ENTITY|"):
            fields = row.split("|")
            if len(fields) != 19 or fields[2] in census:
                raise HorizontalL4Error("AutoCAD census row differs")
            census[fields[2]] = fields
    if set(census) != set(handles.values()):
        raise HorizontalL4Error("AutoCAD handles differ")
    nodes = {node["id"]: (float(node["x"]), float(node["y"]), 0.0)
             for node in plan["nodes"]}
    matches = []
    for line in plan["lines"]:
        fields = census[handles[line["id"]]]
        a, b = nodes[line["start"]], nodes[line["end"]]
        p, q = _point(fields[9]), _point(fields[16])
        same = (fields[1] == "LINE" and fields[3] == "0" and
                ((_same(a, p) and _same(b, q)) or
                 (_same(a, q) and _same(b, p))))
        matches.append({"planspec_id": line["id"],
                        "handle": handles[line["id"]],
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matches)
    return {"schema_version": "m7-horizontal-crops-l4-1",
            "status": "passed_scoped_l4" if count == 21 else "failed_scoped_l4",
            "scope": "visible_outer_reference_plus_three_vertical_and_five_horizontal_centerlines",
            "acceptance_m7": False,
            "base_vertical_selection_post_hoc": True,
            "horizontal_five_crop_oracles_pre_frozen": True,
            "freeze_sha256": _file_sha(run / "freeze.json"),
            "report_sha256": _file_sha(run / "report.json"),
            "cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": 21,
            "geometry_comparison": matches}


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
