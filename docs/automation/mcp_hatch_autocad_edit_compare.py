"""Seal an AutoCAD-originated synthetic PLINE edit and its HATCH update."""

import argparse
import hashlib
import json
from pathlib import Path

from mcp_hatch_external_compare import point


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def same(first, second) -> bool:
    return len(first) == len(second) == 3 and all(
        abs(a - b) <= 1e-6 for a, b in zip(first, second))


def compare(source: dict, edit: dict, probe: dict, census: list[str],
            census_sha: str, source_dwg_sha: str, edited_dwg_sha: str) -> dict:
    if source.get("status") != "passed":
        raise ValueError("Source L2 run did not pass")
    original = source["first_save"]["sha256"]
    if (source_dwg_sha != original or edit.get("source_sha256_before") != original
            or edit.get("source_sha256_after") != original
            or edit.get("copy_sha256_before") != original
            or edit.get("source_unchanged") is not True
            or edit.get("copy_changed") is not True
            or edit.get("status") != "edited_copy_needs_external_reopen"
            or edit.get("edit_rows") != ["EDIT|64|24,0|25,0"]
            or edit.get("forced_termination") is not False
            or edit.get("exit_code") != 0):
        raise ValueError("AutoCAD edit or untouched source is not proven")
    if (edited_dwg_sha != edit.get("copy_sha256_after")
            or probe.get("input_sha256_before") != edited_dwg_sha
            or probe.get("input_sha256_after") != edited_dwg_sha
            or probe.get("input_unchanged") is not True
            or probe.get("audit_zero_errors_zero_fixes") is not True
            or probe.get("verdict") != "audit_and_census_passed"
            or probe.get("model_types") != {"HATCH": 1, "LWPOLYLINE": 1}
            or probe.get("census_sha256") != census_sha):
        raise ValueError("Independent reopen or census integrity failed")
    association = source["association"]
    hatch = association["hatch_handle"].upper()
    contour = association["source_handle"].upper()
    expected_path = association["edited_boundary_after_second_reopen"]["paths"]
    expected_vertices = association["edited_vertices"]
    if hatch != "65" or contour != "64" or len(expected_path) != 1 or \
            len(expected_path[0]["edges"]) != 3 or len(expected_vertices) != 3 or \
            expected_path[0]["boundary_handles"] != [int(contour, 16)]:
        raise ValueError("Frozen source fixture differs")
    edge_rows = [row.split("|") for row in census if row.startswith("HATCHEDGE|")]
    ref_rows = [row.split("|") for row in census if row.startswith("HATCHREF|")]
    vertex_rows = [row.split("|") for row in census if row.startswith("PLINEVERTEX|")]
    if len(edge_rows) != 3 or ref_rows != [["HATCHREF", hatch, contour]] or \
            len(vertex_rows) != 3:
        raise ValueError("AutoCAD HATCH/PLINE structure differs")
    for index, (row, expected) in enumerate(zip(edge_rows, expected_path[0]["edges"])):
        line = expected["Line"]
        if row[:4] != ["HATCHEDGE", hatch, str(index), "1"] or len(row) != 6 or \
                not same(point(row[4]), (line["start"]["x"], line["start"]["y"], 0.0)) or \
                not same(point(row[5]), (line["end"]["x"], line["end"]["y"], 0.0)):
            raise ValueError(f"AutoCAD HATCH edge {index} differs")
    for index, (row, expected) in enumerate(zip(vertex_rows, expected_vertices)):
        if row[:3] != ["PLINEVERTEX", contour, str(index)] or len(row) != 4 or \
                not same(point(row[3]), (expected[0], expected[1], 0.0)):
            raise ValueError(f"AutoCAD PLINE vertex {index} differs")
    return {"schema_version": "mcp-hatch-autocad-edit-compare-l4-1",
            "verdict": "matched_scoped", "original_sha256": original,
            "edited_sha256": edited_dwg_sha, "census_sha256": census_sha,
            "hatch_handle": hatch, "contour_handle": contour,
            "matched_edges": 3, "matched_vertices": 3,
            "scope": "one triangular synthetic LINE-path HATCH"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_report", type=Path)
    parser.add_argument("source_dwg", type=Path)
    parser.add_argument("edit_report", type=Path)
    parser.add_argument("edited_dwg", type=Path)
    parser.add_argument("probe_report", type=Path)
    parser.add_argument("census", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(
        json.loads(args.source_report.read_text(encoding="utf-8")),
        json.loads(args.edit_report.read_text(encoding="utf-8")),
        json.loads(args.probe_report.read_text(encoding="utf-8")),
        args.census.read_text(encoding="utf-8").splitlines(),
        digest(args.census), digest(args.source_dwg), digest(args.edited_dwg))
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
