"""Compare an isolated synthetic HATCH path with an independent AutoCAD census."""

import argparse
import hashlib
import json
import re
from pathlib import Path


POINT = re.compile(r"^\((-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)\)$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def point(raw: str) -> tuple[float, float, float]:
    match = POINT.fullmatch(raw)
    if not match:
        raise ValueError(f"Invalid HATCH point: {raw!r}")
    return tuple(float(part) for part in match.groups())


def compare(source: dict, external: dict, census: list[str], census_sha: str) -> dict:
    if source.get("status") != "passed":
        raise ValueError("Source run did not pass")
    if (external.get("verdict") != "audit_and_census_passed"
            or external.get("source_report_match") is not True
            or external.get("input_unchanged") is not True
            or external.get("audit_zero_errors_zero_fixes") is not True
            or external.get("census_sha256") != census_sha):
        raise ValueError("External audit, source match, or census integrity failed")
    input_sha = external["input_sha256_before"]
    if input_sha == source["first_save"]["sha256"]:
        expected = source["association"]["initial_boundary"]
        stage = "before"
    elif input_sha == source["second_save"]["sha256"]:
        expected = source["association"]["edited_boundary_after_second_reopen"]
        stage = "after"
    else:
        raise ValueError("External input is not one of the two frozen source DWGs")
    hatch = source["association"]["hatch_handle"].upper()
    contour = source["association"]["source_handle"].upper()
    paths = expected["paths"]
    if len(paths) != 1 or len(paths[0]["edges"]) != 3:
        raise ValueError("Only the frozen triangular LINE path is supported")
    if expected.get("is_associative") is not True:
        raise ValueError("Source HATCH is not associative")
    if paths[0]["boundary_handles"] != [int(contour, 16)]:
        raise ValueError("Source path does not reference the contour")
    rows = [line.split("|") for line in census if line.startswith("HATCHEDGE|")]
    refs = [line.split("|") for line in census if line.startswith("HATCHREF|")]
    if len(rows) != 3 or len(refs) != 1 or refs[0] != ["HATCHREF", hatch, contour]:
        raise ValueError("AutoCAD HATCH edges or source reference differ")
    checks = []
    for index, (row, edge) in enumerate(zip(rows, paths[0]["edges"])):
        if row[:4] != ["HATCHEDGE", hatch, str(index), "1"] or len(row) != 6:
            raise ValueError(f"AutoCAD HATCH edge {index} has wrong identity/type")
        line = edge["Line"]
        expected_start = (line["start"]["x"], line["start"]["y"], 0.0)
        expected_end = (line["end"]["x"], line["end"]["y"], 0.0)
        actual_start, actual_end = point(row[4]), point(row[5])
        if any(abs(a - b) > 1e-6 for a, b in zip(actual_start, expected_start)):
            raise ValueError(f"AutoCAD HATCH edge {index} start differs")
        if any(abs(a - b) > 1e-6 for a, b in zip(actual_end, expected_end)):
            raise ValueError(f"AutoCAD HATCH edge {index} end differs")
        checks.append({"edge": index, "type": "LINE", "start": actual_start,
                       "end": actual_end, "matched_1e_6": True})
    return {"schema_version": "mcp-hatch-boundary-l4-1", "verdict": "matched_scoped",
            "stage": stage, "input_sha256": input_sha, "census_sha256": census_sha,
            "hatch_handle": hatch, "source_handle": contour, "edges": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_report", type=Path)
    parser.add_argument("external_report", type=Path)
    parser.add_argument("census", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(json.loads(args.source_report.read_text(encoding="utf-8")),
                     json.loads(args.external_report.read_text(encoding="utf-8")),
                     args.census.read_text(encoding="utf-8").splitlines(),
                     digest(args.census))
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
