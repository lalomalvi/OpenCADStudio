"""PlanSpec v1/v2/v3: strict validation and deterministic CAD command dry-run.

Only line and circle commands are compiled in this first scope. Dimensions are
validated but reported as unsupported until native dimension semantics are proven.
"""

from __future__ import annotations

import hashlib
import json
import math
from decimal import Decimal, InvalidOperation
from itertools import combinations
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


def _validate_basic(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") not in {
            "planspec-1", "planspec-2", "planspec-3"}:
        raise PlanError("PlanSpec version unsupported")
    fields = {"schema_version", "units", "origin", "nodes", "lines", "circles", "dimensions"}
    if plan["schema_version"] in {"planspec-2", "planspec-3"}:
        fields.add("topology")
    if plan["schema_version"] == "planspec-3":
        fields.update({"walls", "openings"})
    _keys(plan, fields, "plan")
    if plan["units"] != "m":
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
    if plan["schema_version"] in {"planspec-2", "planspec-3"}:
        _keys(plan["topology"], {"contours"}, "topology")
        if not isinstance(plan["topology"]["contours"], list):
            raise PlanError("Contour collection must be an array")
        for contour in plan["topology"]["contours"]:
            _keys(contour, {"id", "line_ids", "role", "source"}, "contour")
            name = _id(contour["id"], "contour")
            if name in ids:
                raise PlanError("Duplicate PlanSpec ID")
            ids.add(name)
            _source(contour["source"], "contour.source")
            if not isinstance(contour["role"], str) or \
                    contour["role"] not in {"exterior", "room"} or \
                    not isinstance(contour["line_ids"], list) or \
                    len(contour["line_ids"]) < 3 or \
                    any(not isinstance(line_id, str) for line_id in contour["line_ids"]) or \
                    len(set(contour["line_ids"])) != len(contour["line_ids"]):
                raise PlanError("Contour role or line sequence is invalid")
            line_ids = {line["id"] for line in plan["lines"]}
            if any(line_id not in line_ids
                   for line_id in contour["line_ids"]):
                raise PlanError("Contour has a dangling line reference")
    if plan["schema_version"] == "planspec-3":
        if not isinstance(plan["walls"], list) or not isinstance(plan["openings"], list):
            raise PlanError("Wall and opening collections must be arrays")
        walls: dict[str, dict] = {}
        for wall in plan["walls"]:
            _keys(wall, {"id", "start", "end", "thickness_m", "layer", "source"}, "wall")
            name = _id(wall["id"], "wall")
            if name in ids:
                raise PlanError("Duplicate PlanSpec ID")
            ids.add(name)
            for key in ("start", "end"):
                if not isinstance(wall[key], str) or wall[key] not in nodes:
                    raise PlanError("Wall has a dangling node reference")
            if nodes[wall["start"]] == nodes[wall["end"]] or \
                    not Decimal("0.01") <= _number(wall["thickness_m"], "wall.thickness_m") <= Decimal("2"):
                raise PlanError("Wall length or thickness is invalid")
            _id(wall["layer"], "wall.layer")
            _source(wall["source"], "wall.source")
            walls[name] = wall
        for opening in plan["openings"]:
            _keys(opening, {"id", "wall_id", "offset_m", "width_m", "kind", "source"}, "opening")
            name = _id(opening["id"], "opening")
            if name in ids:
                raise PlanError("Duplicate PlanSpec ID")
            ids.add(name)
            if not isinstance(opening["wall_id"], str) or opening["wall_id"] not in walls or \
                    not isinstance(opening["kind"], str) or \
                    opening["kind"] not in {"door", "window"} or \
                    _number(opening["offset_m"], "opening.offset_m") <= 0 or \
                    _number(opening["width_m"], "opening.width_m") <= 0:
                raise PlanError("Opening reference, kind or dimensions are invalid")
            _source(opening["source"], "opening.source")


def analyze_architecture(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate wall/opening identity and spacing; no wall CAD is emitted yet."""
    _validate_basic(plan)
    if plan["schema_version"] != "planspec-3":
        return {"schema_version": "planspec-architecture-1", "status": "unavailable",
                "walls": [], "openings": [], "scope": "no_explicit_walls_in_v1_v2"}
    nodes = {node["id"]: (_number(node["x"], "node.x"),
                          _number(node["y"], "node.y")) for node in plan["nodes"]}
    wall_lengths: dict[str, Decimal] = {}
    walls = []
    for wall in sorted(plan["walls"], key=lambda item: item["id"]):
        a, b = nodes[wall["start"]], nodes[wall["end"]]
        distance = math.hypot(float(b[0] - a[0]), float(b[1] - a[1]))
        if not math.isfinite(distance):
            raise PlanError(f"Wall {wall['id']} length exceeds numeric range")
        length = Decimal(str(distance))
        wall_lengths[wall["id"]] = length
        walls.append({"id": wall["id"], "length_m": format(length, "f"),
                      "thickness_m": format(_number(wall["thickness_m"], "wall.thickness_m"), "f")})
    openings_by_wall: dict[str, list[tuple[Decimal, Decimal, str]]] = {}
    opening_results = []
    for opening in sorted(plan["openings"], key=lambda item: item["id"]):
        start = _number(opening["offset_m"], "opening.offset_m")
        end = start + _number(opening["width_m"], "opening.width_m")
        wall_id = opening["wall_id"]
        if end >= wall_lengths[wall_id]:
            raise PlanError(f"Opening {opening['id']} extends beyond wall endpoints")
        openings_by_wall.setdefault(wall_id, []).append((start, end, opening["id"]))
        opening_results.append({"id": opening["id"], "wall_id": wall_id,
                                "kind": opening["kind"],
                                "offset_m": format(start, "f"),
                                "width_m": format(end - start, "f")})
    for wall_id, intervals in openings_by_wall.items():
        intervals.sort()
        for first, second in zip(intervals, intervals[1:]):
            if second[0] - first[1] < Decimal("0.001"):
                raise PlanError(f"Openings {first[2]} and {second[2]} overlap or touch on {wall_id}")
    return {"schema_version": "planspec-architecture-1", "status": "validated_uncompiled",
            "walls": walls, "openings": opening_results,
            "scope": "straight_wall_axes_and_opening_intervals_no_cad_compiler"}


def analyze_topology(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate explicit v2 contour edges without inferring walls or openings."""
    _validate_basic(plan)
    if plan["schema_version"] == "planspec-1":
        return {"schema_version": "planspec-topology-1", "status": "unavailable",
                "contours": [], "scope": "no_explicit_contours_in_v1"}
    lines = {line["id"]: (line["start"], line["end"]) for line in plan["lines"]}
    nodes = {node["id"]: (_number(node["x"], "node.x"),
                          _number(node["y"], "node.y")) for node in plan["nodes"]}
    results = []
    for contour in sorted(plan["topology"]["contours"], key=lambda item: item["id"]):
        edges = [lines[line_id] for line_id in contour["line_ids"]]
        ordered = None
        for first in (edges[0], edges[0][::-1]):
            sequence = [first[0], first[1]]
            for a, b in edges[1:]:
                if a == sequence[-1]:
                    sequence.append(b)
                elif b == sequence[-1]:
                    sequence.append(a)
                else:
                    break
            if len(sequence) == len(edges) + 1 and sequence[-1] == sequence[0]:
                ordered = sequence[:-1]
                break
        if ordered is None:
            raise PlanError(f"Contour {contour['id']} is not a closed ordered chain")
        if len(set(ordered)) != len(ordered) or len({nodes[node] for node in ordered}) != len(ordered):
            raise PlanError(f"Contour {contour['id']} repeats a vertex")
        points = [nodes[node] for node in ordered]
        twice_area = sum(points[i][0] * points[(i + 1) % len(points)][1] -
                         points[(i + 1) % len(points)][0] * points[i][1]
                         for i in range(len(points)))
        if twice_area == 0:
            raise PlanError(f"Contour {contour['id']} has zero area")
        def orientation(a, b, c):
            return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        def on_segment(a, b, p):
            return min(a[0], b[0]) <= p[0] <= max(a[0], b[0]) and \
                min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
        for i, j in combinations(range(len(points)), 2):
            if j == i + 1 or (i == 0 and j == len(points) - 1):
                continue
            a, b = points[i], points[(i + 1) % len(points)]
            c, d = points[j], points[(j + 1) % len(points)]
            ab_c, ab_d = orientation(a, b, c), orientation(a, b, d)
            cd_a, cd_b = orientation(c, d, a), orientation(c, d, b)
            if (ab_c * ab_d < 0 and cd_a * cd_b < 0) or \
                    any(cross == 0 and on_segment(start, end, point)
                        for cross, start, end, point in
                        ((ab_c, a, b, c), (ab_d, a, b, d),
                         (cd_a, c, d, a), (cd_b, c, d, b))):
                raise PlanError(f"Contour {contour['id']} crosses itself")
        results.append({"id": contour["id"], "role": contour["role"],
                        "line_ids": contour["line_ids"],
                        "signed_area_m2": format(twice_area / 2, "f")})
    return {"schema_version": "planspec-topology-1", "status": "validated",
            "contours": results, "scope": "ordered_closed_contours_no_wall_or_opening_semantics"}


def analyze_dimension_graph(plan: dict[str, Any]) -> dict[str, Any]:
    """Find inconsistent dimension chains without mixing axes or reference types.

    Aligned dimensions are checked against their own geometry by the basic
    validator, but a general signed aligned-chain solver is not yet available.
    """
    _validate_basic(plan)
    nodes = {node["id"]: (_number(node["x"], "node.x"),
                          _number(node["y"], "node.y")) for node in plan["nodes"]}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    unresolved: list[str] = []
    for dimension in plan["dimensions"]:
        if dimension["axis"] == "aligned":
            unresolved.append(dimension["id"])
        else:
            groups.setdefault((dimension["axis"], dimension["reference_type"]), []).append(dimension)
    conflicts: list[dict[str, str]] = []
    components = 0
    for (axis, reference_type), dimensions in sorted(groups.items()):
        coordinate = 0 if axis == "x" else 1
        adjacent: dict[str, list[tuple[str, Decimal, str]]] = {}
        for dimension in sorted(dimensions, key=lambda item: item["id"]):
            start, end = dimension["start"], dimension["end"]
            direction = 1 if nodes[end][coordinate] > nodes[start][coordinate] else -1
            delta = _number(dimension["value"], "dimension.value") * direction
            adjacent.setdefault(start, []).append((end, delta, dimension["id"]))
            adjacent.setdefault(end, []).append((start, -delta, dimension["id"]))
        potentials: dict[str, Decimal] = {}
        visited_edges: set[str] = set()
        for root in sorted(adjacent):
            if root in potentials:
                continue
            components += 1
            potentials[root] = Decimal(0)
            pending = [root]
            while pending:
                node = pending.pop(0)
                for neighbor, delta, edge_id in sorted(adjacent[node], key=lambda edge: edge[2]):
                    if edge_id in visited_edges:
                        continue
                    visited_edges.add(edge_id)
                    predicted = potentials[node] + delta
                    if neighbor not in potentials:
                        potentials[neighbor] = predicted
                        pending.append(neighbor)
                    else:
                        residual = predicted - potentials[neighbor]
                        if abs(residual) > Decimal("0.001"):
                            conflicts.append({"dimension_id": edge_id, "axis": axis,
                                              "reference_type": reference_type,
                                              "component_root": root,
                                              "residual_m": format(residual, "f")})
    return {"schema_version": "planspec-dimension-graph-1",
            "status": "conflict" if conflicts else "indeterminate" if unresolved else "satisfied",
            "components": components, "conflicts": conflicts,
            "unresolved_aligned": sorted(unresolved)}


def validate(plan: dict[str, Any]) -> None:
    report = analyze_dimension_graph(plan)
    if report["conflicts"]:
        ids = ", ".join(conflict["dimension_id"] for conflict in report["conflicts"])
        raise PlanError(f"Dimension chain conflict: {ids}")
    analyze_topology(plan)
    analyze_architecture(plan)


def analyze_geometry(plan: dict[str, Any]) -> dict[str, Any]:
    """Report exact 2D line conflicts without guessing architectural intent.

    PlanSpec v1 has no wall/contour identity. Open endpoints and crossings are
    review candidates, not proof of an erroneous wall or doorway.
    """
    _validate_basic(plan)
    nodes = {node["id"]: (_number(node["x"], "node.x"),
                          _number(node["y"], "node.y")) for node in plan["nodes"]}
    segments = [(item["id"], nodes[item["start"]], nodes[item["end"]], item["layer"])
                for item in sorted(plan["lines"], key=lambda item: item["id"])]

    def orient(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal],
               c: tuple[Decimal, Decimal]) -> Decimal:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def interior(point: tuple[Decimal, Decimal], a: tuple[Decimal, Decimal],
                 b: tuple[Decimal, Decimal]) -> bool:
        return point != a and point != b and orient(a, b, point) == 0 and \
            min(a[0], b[0]) <= point[0] <= max(a[0], b[0]) and \
            min(a[1], b[1]) <= point[1] <= max(a[1], b[1])

    duplicates: list[list[str]] = []
    overlaps: list[list[str]] = []
    crossings: list[list[str]] = []
    t_junctions: list[list[str]] = []
    for (first_id, a, b, _), (second_id, c, d, _) in combinations(segments, 2):
        pair = [first_id, second_id]
        if {a, b} == {c, d}:
            duplicates.append(pair)
            continue
        ab_c, ab_d = orient(a, b, c), orient(a, b, d)
        cd_a, cd_b = orient(c, d, a), orient(c, d, b)
        if ab_c == ab_d == cd_a == cd_b == 0:
            axis = 0 if a[0] != b[0] else 1
            if max(min(a[axis], b[axis]), min(c[axis], d[axis])) < \
                    min(max(a[axis], b[axis]), max(c[axis], d[axis])):
                overlaps.append(pair)
        elif ab_c * ab_d < 0 and cd_a * cd_b < 0:
            crossings.append(pair)
        elif any((interior(point, start, end) for point, start, end in
                  ((a, c, d), (b, c, d), (c, a, b), (d, a, b)))):
            t_junctions.append(pair)

    degrees: dict[tuple[Decimal, Decimal], int] = {}
    for _, a, b, _ in segments:
        degrees[a] = degrees.get(a, 0) + 1
        degrees[b] = degrees.get(b, 0) + 1
    open_endpoints = [{"x": format(point[0], "f"), "y": format(point[1], "f")}
                      for point, degree in sorted(degrees.items()) if degree == 1]
    circles = [(item["id"], nodes[item["center"]],
                _number(item["radius"], "circle.radius"))
               for item in sorted(plan["circles"], key=lambda item: item["id"])]
    circle_duplicates = [[first_id, second_id]
                         for (first_id, a, radius_a), (second_id, b, radius_b)
                         in combinations(circles, 2) if a == b and radius_a == radius_b]
    issues = duplicates or overlaps or crossings or t_junctions or open_endpoints or circle_duplicates
    return {"schema_version": "planspec-geometry-qa-1",
            "status": "review_required" if issues else "clear",
            "duplicate_lines": duplicates, "duplicate_circles": circle_duplicates,
            "overlapping_lines": overlaps, "interior_crossings": crossings,
            "t_junctions": t_junctions, "open_line_endpoints": open_endpoints,
            "scope": "2d_lines_and_duplicate_circles_no_contour_semantics"}


def _coordinate(value: Decimal) -> str:
    if abs(value) > Decimal("1000000"):
        raise PlanError("Coordinate exceeds compiler range")
    rounded = value.quantize(Decimal("0.000001"))
    if rounded == 0:
        if value != 0:
            raise PlanError("Coordinate is below compiler precision")
        return "0"
    return format(rounded, "f").rstrip("0").rstrip(".")


def dry_run(plan: dict[str, Any], *, capabilities: set[str] | None = None) -> dict[str, Any]:
    validate(plan)
    dimension_graph = analyze_dimension_graph(plan)
    topology = analyze_topology(plan)
    architecture = analyze_architecture(plan)
    geometry_qa = analyze_geometry(plan)
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
    layers = sorted({item["layer"] for item in (*plan["lines"], *plan["circles"])} - {"0"})
    # INSUNITS=6 is metres in DWG. A metric GUI template may otherwise default
    # to INSUNITS=4 (millimetres), silently changing insertion scale semantics.
    execution = [{"planspec_id": None, "command": "SETVAR INSUNITS 6", "layer": "0"}]
    execution.extend({"planspec_id": None, "command": f"LAYER NEW {layer}", "layer": layer}
                     for layer in layers)
    current_layer = "0"
    for command in commands:
        if command["layer"] != current_layer:
            execution.append({"planspec_id": None,
                              "command": f"CLAYER {command['layer']}",
                              "layer": command["layer"]})
            current_layer = command["layer"]
        execution.append(command)
    missing = set()
    if plan["dimensions"]:
        missing.add("native_dimension")
    if plan["schema_version"] == "planspec-3" and plan["walls"]:
        missing.add("wall_compilation")
    if plan["schema_version"] == "planspec-3" and plan["openings"]:
        missing.add("opening_compilation")
    if layers and "layer_assignment" not in (capabilities or set()):
        missing.add("layer_assignment")
    unsupported = sorted(missing)
    wire = json.dumps(execution, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema_version": "planspec-dry-run-1", "commands": commands,
            "execution_steps": execution,
            "dwg_unit_profile": {"plan_units": "m", "insunits": 6},
            "dimension_graph": dimension_graph,
            "topology": topology,
            "architecture": architecture,
            "geometry_qa": geometry_qa,
            "commands_sha256": hashlib.sha256(wire).hexdigest(),
            "unsupported": unsupported, "executable": not unsupported,
            "note": "Nonzero layers require layer_assignment in a manifest verified for this build"}
