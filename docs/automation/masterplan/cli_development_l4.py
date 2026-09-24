"""Independent handle/coordinate verdict for a scoped CLI development drawing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha


class CliL4Error(ValueError):
    pass


_POINT = re.compile(r"^\(([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+)\)$")


def _point(raw: str) -> tuple[float, float, float]:
    matched = _POINT.fullmatch(raw)
    if matched is None:
        raise CliL4Error("External point is invalid")
    return tuple(float(value) for value in matched.groups())


def _same(first: tuple, second: tuple) -> bool:
    return all(abs(x - y) <= 1e-6 for x, y in zip(first, second))


def assess(plan_path: Path, cad_path: Path, external_path: Path) -> dict:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cad = verify_owned_cad_evidence(cad_path)
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    if external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != cad["dwg"]["sha256"] or \
            external.get("input_sha256_after") != cad["dwg"]["sha256"] or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("insunits") != 6 or external.get("unit_match") is not True or \
            external.get("model_census_count") != 4 or \
            external.get("model_types") != {"LINE": 4} or \
            external.get("census_done") is not True or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed" or \
            _file_sha(census_path) != external.get("census_sha256"):
        raise CliL4Error("External DWG audit, source or census differs")
    lines = {}
    for row in census_path.read_text(encoding="utf-8").splitlines():
        if not row.startswith("ENTITY|"):
            continue
        parts = row.split("|")
        if len(parts) != 19 or parts[1] != "LINE" or parts[3] != "0" or \
                parts[2] in lines:
            raise CliL4Error("External entity type, layer or handle differs")
        lines[parts[2]] = (_point(parts[9]), _point(parts[16]))
    handles = cad["handles_by_id"]
    nodes = {node["id"]: (float(node["x"]), float(node["y"]), 0.0)
             for node in plan["nodes"]}
    if len(lines) != len(handles) or len(plan["lines"]) != len(handles) or \
            set(lines) != set(handles.values()):
        raise CliL4Error("External handle census differs from PlanSpec")
    matches = []
    for expected in plan["lines"]:
        handle = handles[expected["id"]]
        actual_a, actual_b = lines[handle]
        expected_a, expected_b = nodes[expected["start"]], nodes[expected["end"]]
        same = ((_same(actual_a, expected_a) and _same(actual_b, expected_b)) or
                (_same(actual_a, expected_b) and _same(actual_b, expected_a)))
        matches.append({"planspec_id": expected["id"], "handle": handle,
                        "matched_1e_6": same})
    count = sum(item["matched_1e_6"] for item in matches)
    return {"schema_version": "m7-cli-development-l4-1",
            "status": "passed_scoped_l4" if count == len(matches) else "failed_scoped_l4",
            "acceptance_m7": False, "source_plan_sha256": _file_sha(plan_path),
            "source_cad_evidence_sha256": _file_sha(cad_path),
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": cad["dwg"]["sha256"],
            "geometry_matches": count, "geometry_total": len(matches),
            "geometry_comparison": matches,
            "m7_gates": {f"G{i}": "pending" for i in range(11)}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cad", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.plan.resolve(strict=True), args.cad.resolve(strict=True),
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
