"""Compare a synthetic edited native dimension to independent AutoCAD data."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from five_bay_l4 import _point
from reserved_trial import _file_sha


class Fixed2AssocL4Error(ValueError):
    pass


def _near(a: object, b: float) -> bool:
    return type(a) in {int, float} and math.isfinite(a) and abs(a - b) <= 1e-6


def assess(source_path: Path, external_path: Path) -> dict:
    source = json.loads(source_path.read_text(encoding="utf-8"))
    external = json.loads(external_path.read_text(encoding="utf-8"))
    if source.get("schema_version") != "mcp-fixed2-dimension-reopen-l2-2" or \
            source.get("status") != "passed" or source.get("gui_exited") is not True or \
            source.get("dimension_style") != "OCS_ASSOC_FIXED2" or \
            not _near(source.get("association", {}).get("initial_measurement"), 2.5) or \
            not _near(source.get("association", {}).get("reopened_measurement"), 2.5) or \
            not _near(source.get("association", {}).get("edited_measurement"), 3.5):
        raise Fixed2AssocL4Error("L2 association evidence differs")
    drawing = source_path.parent / source["second_save"]["file"]
    if _file_sha(drawing) != source["second_save"]["sha256"] or \
            external.get("schema_version") != "mcp-autocad-audit-l4-17" or \
            external.get("product") != "AutoCAD Core Console" or \
            external.get("input_sha256_before") != _file_sha(drawing) or \
            external.get("input_sha256_after") != _file_sha(drawing) or \
            external.get("input_unchanged") is not True or \
            external.get("audit_zero_errors_zero_fixes") is not True or \
            external.get("source_report_match") is not True or \
            external.get("insunits") != 6 or \
            external.get("model_census_count") != 2 or \
            external.get("model_types") != {"LINE": 1, "DIMENSION": 1} or \
            external.get("forced_termination") is not False or \
            external.get("exit_code") != 0 or \
            external.get("verdict") != "audit_and_census_passed":
        raise Fixed2AssocL4Error("AutoCAD source, units, audit or census differs")
    dim = source["association"]["dimension_handle"]
    line = source["association"]["line_handle"]
    if not isinstance(dim, str) or not isinstance(line, str) or dim == line:
        raise Fixed2AssocL4Error("L2 handles differ")
    data = external.get("dimension_measurements", {}).get(dim, {})
    style = external.get("dimension_styles", {}).get(dim, {})
    expected_style = {"name": "OCS_ASSOC_FIXED2", "text_height_m": 0.25,
                      "arrow_size_m": 0.08, "gap_m": 0.02, "scale": 1,
                      "measurement_factor": 1, "decimal_places": 2,
                      "zero_suppression": 0}
    style_ok = set(style) == set(expected_style) and all(
        style[key] == expected if key == "name" else _near(style[key], expected)
        for key, expected in expected_style.items())
    try:
        measure = float(data["dxf_42"])
        start, end = _point(data["dxf_13"]), _point(data["dxf_14"])
    except (KeyError, TypeError, ValueError) as error:
        raise Fixed2AssocL4Error("AutoCAD dimension fields differ") from error
    geometry_ok = (_near(measure, 3.5) and
                   all(_near(value, expected) for value, expected in
                       zip(start, (70, 0, 0))) and
                   all(_near(value, expected) for value, expected in
                       zip(end, (73.5, 0, 0))))
    return {"schema_version": "m5-fixed2-association-l4-1",
            "status": "passed_scoped_l4" if style_ok and geometry_ok else "failed_scoped_l4",
            "scope": "one_synthetic_linked_dimension_after_edit_and_reopen",
            "source_report_sha256": _file_sha(source_path),
            "external_report_sha256": _file_sha(external_path),
            "dwg_sha256": _file_sha(drawing),
            "dimension_handle": dim, "line_handle": line,
            "style_match": style_ok, "geometry_match": geometry_ok}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--external", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verdict = assess(args.source.resolve(strict=True),
                     args.external.resolve(strict=True))
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(verdict, target, sort_keys=True, indent=2)
        target.write("\n")
    print(json.dumps({key: verdict[key] for key in
                      ("status", "style_match", "geometry_match")}))
    if verdict["status"] != "passed_scoped_l4":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
