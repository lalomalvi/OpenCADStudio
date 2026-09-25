"""External AutoCAD geometry verdict for a deterministic LINE-only release case."""

import argparse
import json
from pathlib import Path
import re

from m8_case_cli import verify, validate
from owned_cad_executor import verify_owned_cad_evidence
from reserved_trial import _file_sha


class ReleaseExternalError(ValueError):
    pass


POINT = re.compile(r"^\(([-+0-9.eE]+) ([-+0-9.eE]+) ([-+0-9.eE]+)\)$")
LINE = re.compile(r"^LINE ([-+0-9.eE]+),([-+0-9.eE]+) "
                  r"([-+0-9.eE]+),([-+0-9.eE]+)$")


def point(value: str) -> tuple[float, float, float]:
    found = POINT.fullmatch(value)
    if not found:
        raise ReleaseExternalError("AutoCAD point is invalid")
    return tuple(float(item) for item in found.groups())


def close(a, b):
    return len(a) == len(b) == 3 and all(abs(x - y) <= 1e-6 for x, y in zip(a, b))


def assess(root: Path, plan_path: Path, binary: Path, external_path: Path) -> dict:
    local = verify(root, plan_path, binary)
    _, compiled = validate(root, plan_path, binary)
    if any(not LINE.fullmatch(command["command"])
           for command in compiled["commands"]):
        raise ReleaseExternalError("This L4 comparator only supports LINE entities")
    files = list((root / "cad").glob("*.json"))
    cad = verify_owned_cad_evidence(files[0])
    handles = cad["handles_by_id"]
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    expected_count = len(compiled["commands"])
    if (external.get("product") != "AutoCAD Core Console" or
            external.get("input_sha256_before") != local["dwg_sha256"] or
            external.get("input_sha256_after") != local["dwg_sha256"] or
            external.get("input_unchanged") is not True or
            external.get("audit_zero_errors_zero_fixes") is not True or
            external.get("insunits") != 6 or external.get("unit_match") is not True or
            external.get("model_census_count") != expected_count or
            external.get("model_types") != {"LINE": expected_count} or
            external.get("census_sha256") != _file_sha(census_path) or
            external.get("forced_termination") is not False or
            external.get("exit_code") != 0 or
            external.get("verdict") != "audit_and_census_passed"):
        raise ReleaseExternalError("AutoCAD audit, units or census integrity differs")
    rows = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ENTITY|"):
            fields = line.split("|")
            if len(fields) != 19 or fields[2] in rows:
                raise ReleaseExternalError("AutoCAD entity row differs")
            rows[fields[2]] = fields
    if set(rows) != set(handles.values()) or len(rows) != expected_count:
        raise ReleaseExternalError("AutoCAD handles differ from owned CAD")
    matches = []
    for command in compiled["commands"]:
        name = command["planspec_id"]
        handle = handles[name]
        fields = rows[handle]
        parsed = LINE.fullmatch(command["command"])
        x0, y0, x1, y1 = (float(value) for value in parsed.groups())
        a, b = point(fields[9]), point(fields[16])
        same = (fields[1] == "LINE" and fields[3] == command["layer"] and
                ((close(a, (x0, y0, 0.0)) and close(b, (x1, y1, 0.0))) or
                 (close(b, (x0, y0, 0.0)) and close(a, (x1, y1, 0.0)))))
        matches.append({"planspec_id": name, "handle": handle,
                        "matched_1e_6": bool(same)})
    count = sum(item["matched_1e_6"] for item in matches)
    return {"schema_version": "m8-deterministic-case-l4-1",
            "status": "passed_scoped_l4" if count == expected_count else "failed_scoped_l4",
            "model_call": False, "geometry_matches": count,
            "geometry_total": expected_count, "geometry_comparison": matches,
            "contract_sha256": local["contract_sha256"],
            "report_sha256": local["report_sha256"],
            "external_report_sha256": _file_sha(external_path),
            "census_sha256": _file_sha(census_path),
            "dwg_sha256": local["dwg_sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.run_root.resolve(strict=True),
                    args.plan.resolve(strict=True), args.binary.resolve(strict=True),
                    args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"], result["geometry_matches"], result["geometry_total"])
    raise SystemExit(0 if result["status"] == "passed_scoped_l4" else 1)


if __name__ == "__main__":
    main()
