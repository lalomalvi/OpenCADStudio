"""Check the synthetic MCP-SYMBOL definition against an independent AutoCAD census."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def near(actual, expected):
    return isinstance(actual, (int, float)) and abs(actual - expected) <= 1e-6


def point(actual, expected):
    return isinstance(actual, list) and len(actual) == 3 and all(
        near(a, e) for a, e in zip(actual, expected)
    )


def verify(source_path, external_path):
    source_path, external_path = Path(source_path), Path(external_path)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    external = json.loads(external_path.read_text(encoding="utf-8"))
    census_path = external_path.parent / "model-census.txt"
    drawing = Path(source["verified_output"]["path"])
    checks = {
        "source_passed": source.get("status") == "passed" and source.get("semantic_insunits") == 6,
        "external_passed": external.get("verdict") == "audit_and_census_passed"
                           and external.get("audit_zero_errors_zero_fixes") is True
                           and external.get("input_unchanged") is True
                           and external.get("source_report_match") is True,
        "units_meters": external.get("insunits") == 6 and external.get("unit_match") is True,
        "source_dwg_hash": drawing.is_file() and sha(drawing) == source["verified_output"]["sha256"],
        "external_dwg_hash": external.get("input_sha256_before") == external.get("input_sha256_after")
                             == source["verified_output"]["sha256"],
        "census_hash": census_path.is_file() and sha(census_path) == external.get("census_sha256"),
        "property_comparison": len(external.get("property_comparison", [])) == 23
                               and all(row.get("matched_1e_6") is True
                                       for row in external.get("property_comparison", [])),
    }
    block = external.get("block_definitions", {}).get("MCP-SYMBOL", {})
    children = block.get("entities", [])
    child = children[0] if len(children) == 1 else {}
    checks["block_content"] = (
        point(block.get("base_point"), [0, 0, 0]) and near(block.get("flags"), 0)
        and child.get("type") == "LINE" and child.get("layer") == "A-DIMS"
        and point(child.get("start_point"), [0, 0, 0])
        and point(child.get("end_point"), [2, 0, 0])
        and bool(block.get("handle")) and bool(child.get("handle"))
    )
    raw = census_path.read_text(encoding="utf-8") if census_path.is_file() else ""
    checks["census_content"] = (
        raw.count("BLOCKDEF|MCP-SYMBOL|") == 1
        and raw.count("BLOCKENTITY|MCP-SYMBOL|") == 1
        and f"BLOCKDEF|MCP-SYMBOL|{block.get('handle')}|" in raw
        and f"BLOCKENTITY|MCP-SYMBOL|LINE|{child.get('handle')}|A-DIMS|" in raw
    )
    fixture = source.get("block_fixture", {})
    instances = fixture.get("instances", [])
    handles = fixture.get("insert_handles", [])
    checks["fixture_instances"] = (
        len(instances) == len(handles) == 2
        and all(instance.get("block") == "MCP-SYMBOL" for instance in instances)
        and fixture.get("roundtrip_transforms") == "matched_1e-6_internal"
    )
    # Transform local endpoints using the INSERT fields independently read by AutoCAD.
    expected = [([62, 0, 0], [62 + math.sqrt(3), 1, 0]),
                ([66, 0, 0], [70, 0, 0])]
    derived = []
    for handle, instance in zip(handles, instances):
        rows = [row for row in external.get("property_comparison", [])
                if row.get("handle") == handle]
        props = {row["property"]: row.get("observed") for row in rows}
        if not all(key in props for key in ("block", "x_scale", "y_scale", "rotation",
                                            "position_0", "position_1", "position_2")):
            continue
        x, y, z = (props[f"position_{i}"] for i in range(3))
        angle, sx, sy = props["rotation"], props["x_scale"], props["y_scale"]
        endpoints = []
        for local in (child.get("start_point", []), child.get("end_point", [])):
            if len(local) != 3:
                break
            dx, dy = local[0] * sx, local[1] * sy
            endpoints.append([x + dx * math.cos(angle) - dy * math.sin(angle),
                              y + dx * math.sin(angle) + dy * math.cos(angle), z + local[2]])
        if len(endpoints) == 2:
            derived.append({"handle": handle, "endpoints": endpoints,
                            "properties_match": all(row.get("matched_1e_6") is True for row in rows)})
    checks["effective_geometry"] = len(derived) == 2 and all(
        item["properties_match"] and point(item["endpoints"][0], pair[0])
        and point(item["endpoints"][1], pair[1])
        for item, pair in zip(derived, expected)
    )
    return {"schema_version": "block-definition-l4-1",
            "status": "passed" if all(checks.values()) else "failed",
            "source_report_sha256": sha(source_path),
            "external_report_sha256": sha(external_path),
            "census_sha256": sha(census_path) if census_path.is_file() else None,
            "dwg_sha256": source["verified_output"]["sha256"],
            "checks": checks, "effective_endpoints": derived,
            "scope": "one synthetic LINE block and two INSERT transforms; no rendered or exploded comparison"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_report")
    parser.add_argument("external_report")
    args = parser.parse_args()
    result = verify(args.source_report, args.external_report)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
