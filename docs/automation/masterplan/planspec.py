"""PlanSpec v1: strict, pure validation and deterministic CAD command dry-run.

Only line and circle commands are compiled in this first scope. Dimensions are
validated but reported as unsupported until native dimension semantics are proven.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from typing import Any


class PlanError(ValueError):
    pass


def _keys(value: Any, expected: set[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise PlanError(f"{where}: unexpected or missing fields")


def _id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 80 \
            or not all(c.isascii() and (c.isalnum() or c in "-_") for c in value):
        raise PlanError(f"{where}: invalid stable ID")
    return value


def _number(value: Any, where: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PlanError(f"{where}: invalid number")
    try:
        number = Decimal(str(value))
    except InvalidOperation as error:
        raise PlanError(f"{where}: invalid number") from error
    if not number.is_finite():
        raise PlanError(f"{where}: non-finite number")
    return number


def _source(value: Any, where: str) -> None:
    _keys(value, {"region_px", "confidence", "classification"}, where)
    region = value["region_px"]
    if not isinstance(region, list) or len(region) != 4 or any(type(x) is not int or x < 0 for x in region) \
            or region[2] <= region[0] or region[3] <= region[1]:
        raise PlanError(f"{where}: invalid source region")
    confidence = _number(value["confidence"], where)
    if not Decimal(0) <= confidence <= Decimal(1) \
            or not isinstance(value["classification"], str) \
            or value["classification"] not in {"measured", "inferred", "unknown"}:
        raise PlanError(f"{where}: invalid provenance")


def _text_dimension(value: Any) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > 32:
        raise PlanError("Dimension text is invalid")
    text = value.strip()
    if text.endswith(" m"):
        text = text[:-2]
    return _number(text, "dimension text")


def validate(plan: dict[str, Any]) -> None:
    _keys(plan, {"schema_version", "units", "origin", "nodes", "lines", "circles", "dimensions"}, "plan")
    if plan["schema_version"] != "planspec-1" or plan["units"] != "m":
        raise PlanError("PlanSpec version or units unsupported; explicit conversion required")
    _keys(plan["origin"], {"x", "y"}, "origin")
    _number(plan["origin"]["x"], "origin.x")
    _number(plan["origin"]["y"], "origin.y")
    if not isinstance(plan["nodes"], list) or not isinstance(plan["lines"], list) \
            or not isinstance(plan["circles"], list) or not isinstance(plan["dimensions"], list):
        raise PlanError("Collections must be arrays")
    nodes: dict[str, tuple[Decimal, Decimal]] = {}
    ids: set[str] = set()
    for node in plan["nodes"]:
        _keys(node, {"id", "x", "y", "source"}, "node")
        name = _id(node["id"], "node")
        if name in ids:
            raise PlanError("Duplicate PlanSpec ID")
        ids.add(name)
        nodes[name] = (_number(node["x"], "node.x"), _number(node["y"], "node.y"))
        _source(node["source"], "node.source")
    for kind, fields in (("lines", {"id", "start", "end", "layer", "source"}),
                         ("circles", {"id", "center", "radius", "layer", "source"}),
                         ("dimensions", {"id", "start", "end", "axis", "reference_type",
                                         "value", "text", "source"})):
        for item in plan[kind]:
            _keys(item, fields, kind)
            name = _id(item["id"], kind)
            if name in ids:
                raise PlanError("Duplicate PlanSpec ID")
            ids.add(name)
            _source(item["source"], f"{kind}.source")
            for key in ("start", "end") if kind != "circles" else ("center",):
                if not isinstance(item[key], str) or item[key] not in nodes:
                    raise PlanError(f"{kind}: dangling node reference")
            if kind != "dimensions":
                _id(item["layer"], "layer")
            if kind == "lines" and nodes[item["start"]] == nodes[item["end"]]:
                raise PlanError("Zero-length line")
            if kind == "circles" and _number(item["radius"], "circle.radius") <= 0:
                raise PlanError("Circle radius must be positive")
            if kind == "dimensions":
                if not isinstance(item["axis"], str) or item["axis"] not in {"x", "y", "aligned"} \
                        or not isinstance(item["reference_type"], str) \
                        or item["reference_type"] not in {"face", "axis", "exterior", "interior"}:
                    raise PlanError("Dimension reference is invalid")
                value = _number(item["value"], "dimension.value")
                if value <= 0 or abs(value - _text_dimension(item["text"])) > Decimal("0.001"):
                    raise PlanError("Dimension text differs from stated value")
                a, b = nodes[item["start"]], nodes[item["end"]]
                distance = (abs(b[0] - a[0]) if item["axis"] == "x" else
                            abs(b[1] - a[1]) if item["axis"] == "y" else
                            Decimal(str(math.hypot(float(b[0] - a[0]), float(b[1] - a[1])))))
                if abs(distance - value) > Decimal("0.001"):
                    raise PlanError(f"Dimension {name} differs from referenced geometry")


def _coordinate(value: Decimal) -> str:
    if abs(value) > Decimal("1000000"):
        raise PlanError("Coordinate exceeds compiler range")
    rounded = value.quantize(Decimal("0.000001"))
    if rounded == 0:
        if value != 0:
            raise PlanError("Coordinate is below compiler precision")
        return "0"
    return format(rounded, "f").rstrip("0").rstrip(".")


def dry_run(plan: dict[str, Any]) -> dict[str, Any]:
    validate(plan)
    nodes = {node["id"]: (_number(node["x"], "x"), _number(node["y"], "y"))
             for node in plan["nodes"]}
    origin = (_number(plan["origin"]["x"], "origin.x"),
              _number(plan["origin"]["y"], "origin.y"))
    commands: list[dict[str, str]] = []
    for line in sorted(plan["lines"], key=lambda item: item["id"]):
        a, b = nodes[line["start"]], nodes[line["end"]]
        args = [*(_coordinate(a[i] + origin[i]) for i in range(2)),
                *(_coordinate(b[i] + origin[i]) for i in range(2))]
        if args[:2] == args[2:]:
            raise PlanError("Line collapses at compiler precision")
        commands.append({"planspec_id": line["id"], "command": f"LINE {args[0]},{args[1]} {args[2]},{args[3]}",
                         "layer": line["layer"]})
    for circle in sorted(plan["circles"], key=lambda item: item["id"]):
        center = nodes[circle["center"]]
        x, y = (_coordinate(center[i] + origin[i]) for i in range(2))
        radius = _coordinate(_number(circle["radius"], "radius"))
        commands.append({"planspec_id": circle["id"], "command": f"CIRCLE {x},{y} {radius}",
                         "layer": circle["layer"]})
    missing = set()
    if plan["dimensions"]:
        missing.add("native_dimension")
    if any(item["layer"] != "0" for item in (*plan["lines"], *plan["circles"])):
        missing.add("layer_assignment")
    unsupported = sorted(missing)
    wire = json.dumps(commands, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema_version": "planspec-dry-run-1", "commands": commands,
            "commands_sha256": hashlib.sha256(wire).hexdigest(),
            "unsupported": unsupported, "executable": not unsupported,
            "note": "Layer assignment needs manifest/GUI verification before execution"}
