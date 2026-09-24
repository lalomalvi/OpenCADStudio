"""PlanSpec v1–v8: strict validation and deterministic CAD command dry-run.

Lines, circles, one straight wall with an opening, and a two-wall orthogonal
union compile. V6 binds dimensions to wall faces or axes. V7 compiles one
axis-aligned face thickness dimension with an explicit metric style. Other native
dimensions and multiple symbolic openings remain unsupported. V8 adds typed
3D-height obstacles for door-clearance preflight; it does not draw obstacles.
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


def _wall_reference_point(ref: dict, walls: dict[str, dict],
                          nodes: dict[str, tuple[Decimal, Decimal]]) -> tuple[Decimal, Decimal]:
    _keys(ref, {"wall_id", "side", "station_m"}, "dimension wall reference")
    wall_id, side = ref["wall_id"], ref["side"]
    if not isinstance(wall_id, str) or wall_id not in walls or \
            not isinstance(side, str) or side not in {"left", "right", "axis"}:
        raise PlanError("Dimension wall reference is invalid")
    wall = walls[wall_id]
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    station = _number(ref["station_m"], "dimension wall station")
    if not 0 < station < length:
        raise PlanError("Dimension wall station lies outside the open wall span")
    offset = _number(wall["thickness_m"], "wall.thickness_m") / 2
    signed = offset if side == "left" else -offset if side == "right" else Decimal(0)
    return (a[0] + dx * station / length - dy * signed / length,
            a[1] + dy * station / length + dx * signed / length)


def _validate_basic(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") not in {
            "planspec-1", "planspec-2", "planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
        raise PlanError("PlanSpec version unsupported")
    fields = {"schema_version", "units", "origin", "nodes", "lines", "circles", "dimensions"}
    if plan["schema_version"] in {"planspec-2", "planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
        fields.add("topology")
    if plan["schema_version"] in {"planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
        fields.update({"walls", "openings"})
    if plan["schema_version"] in {"planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
        fields.add("joins")
    if plan["schema_version"] in {"planspec-6", "planspec-7", "planspec-8"}:
        fields.add("dimension_bindings")
    if plan["schema_version"] in {"planspec-7", "planspec-8"}:
        fields.update({"dimension_style", "dimension_placements"})
    if plan["schema_version"] == "planspec-8":
        fields.add("obstacles")
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
    if plan["schema_version"] in {"planspec-2", "planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
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
    if plan["schema_version"] in {"planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
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
            if not isinstance(opening, dict):
                raise PlanError("opening: expected object")
            fields = {"id", "wall_id", "offset_m", "width_m", "kind", "source"}
            if plan["schema_version"] in {"planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
                if opening.get("kind") == "door":
                    fields.add("swing")
                elif opening.get("kind") == "window":
                    fields.add("elevation")
            _keys(opening, fields, "opening")
            name = _id(opening["id"], "opening")
            if name in ids:
                raise PlanError("Duplicate PlanSpec ID")
            ids.add(name)
            if not isinstance(opening["wall_id"], str) or opening["wall_id"] not in walls or \
                    not isinstance(opening["kind"], str) or \
                    opening["kind"] not in {"clear", "door", "window"} or \
                    _number(opening["offset_m"], "opening.offset_m") <= 0 or \
                    _number(opening["width_m"], "opening.width_m") <= 0:
                raise PlanError("Opening reference, kind or dimensions are invalid")
            _source(opening["source"], "opening.source")
            if plan["schema_version"] in {"planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
                if opening["kind"] == "door":
                    swing = opening["swing"]
                    swing_fields = {"hinge", "side", "angle_deg"}
                    if plan["schema_version"] == "planspec-8":
                        swing_fields.add("leaf_height_m")
                    _keys(swing, swing_fields, "door.swing")
                    if not isinstance(swing["hinge"], str) or \
                            swing["hinge"] not in {"start", "end"} or \
                            not isinstance(swing["side"], str) or \
                            swing["side"] not in {"left", "right"} or \
                            type(swing["angle_deg"]) is not int or swing["angle_deg"] != 90:
                        raise PlanError("Door swing requires explicit hinge, side and 90 degrees")
                    if plan["schema_version"] == "planspec-8" and not \
                            Decimal("1.5") <= _number(swing["leaf_height_m"], "door.leaf_height_m") <= Decimal(4):
                        raise PlanError("Door leaf height is out of scope")
                elif opening["kind"] == "window":
                    elevation = opening["elevation"]
                    _keys(elevation, {"sill_m", "head_m"}, "window.elevation")
                    sill = _number(elevation["sill_m"], "window.elevation.sill_m")
                    head = _number(elevation["head_m"], "window.elevation.head_m")
                    if sill < 0 or head <= sill:
                        raise PlanError("Window sill/head elevation is invalid")
        if plan["schema_version"] in {"planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
            if not isinstance(plan["joins"], list):
                raise PlanError("Join collection must be an array")
            used_ends: set[tuple[str, str]] = set()
            for join in plan["joins"]:
                _keys(join, {"id", "wall_a_id", "wall_a_end", "wall_b_id", "wall_b_end",
                             "style", "source"}, "join")
                name = _id(join["id"], "join")
                if name in ids:
                    raise PlanError("Duplicate PlanSpec ID")
                ids.add(name)
                _source(join["source"], "join.source")
                a_id, b_id = join["wall_a_id"], join["wall_b_id"]
                if not isinstance(a_id, str) or not isinstance(b_id, str) or \
                        a_id not in walls or b_id not in walls or a_id == b_id or \
                        not isinstance(join["wall_a_end"], str) or \
                        not isinstance(join["wall_b_end"], str) or \
                        join["wall_a_end"] not in {"start", "end"} or \
                        join["wall_b_end"] not in {"start", "end"} or \
                        join["style"] != "orthogonal_union":
                    raise PlanError("Join wall reference, end or style is invalid")
                for wall_id, end in ((a_id, join["wall_a_end"]),
                                     (b_id, join["wall_b_end"])):
                    if (wall_id, end) in used_ends:
                        raise PlanError("Wall endpoint participates in multiple joins")
                    used_ends.add((wall_id, end))
                a_wall, b_wall = walls[a_id], walls[b_id]
                a_end = nodes[a_wall[join["wall_a_end"]]]
                b_end = nodes[b_wall[join["wall_b_end"]]]
                if a_end != b_end:
                    raise PlanError("Joined wall endpoints do not coincide exactly")
                av = (nodes[a_wall["end"]][0] - nodes[a_wall["start"]][0],
                      nodes[a_wall["end"]][1] - nodes[a_wall["start"]][1])
                bv = (nodes[b_wall["end"]][0] - nodes[b_wall["start"]][0],
                      nodes[b_wall["end"]][1] - nodes[b_wall["start"]][1])
                if av[0] * bv[0] + av[1] * bv[1] != 0 or \
                        _number(a_wall["thickness_m"], "wall.thickness_m") != \
                        _number(b_wall["thickness_m"], "wall.thickness_m"):
                    raise PlanError("Orthogonal join requires perpendicular axes and equal thickness")
        if plan["schema_version"] in {"planspec-6", "planspec-7", "planspec-8"}:
            if not isinstance(plan["dimension_bindings"], list):
                raise PlanError("Dimension bindings must be an array")
            dimensions = {item["id"]: item for item in plan["dimensions"]}
            bindings: set[str] = set()
            for binding in plan["dimension_bindings"]:
                _keys(binding, {"dimension_id", "start_ref", "end_ref", "source"},
                      "dimension binding")
                name = binding["dimension_id"]
                if not isinstance(name, str) or name not in dimensions or name in bindings:
                    raise PlanError("Dimension binding is missing, duplicated or dangling")
                bindings.add(name)
                _source(binding["source"], "dimension binding.source")
                dimension = dimensions[name]
                start_ref, end_ref = binding["start_ref"], binding["end_ref"]
                sides = (start_ref.get("side") if isinstance(start_ref, dict) else None,
                         end_ref.get("side") if isinstance(end_ref, dict) else None)
                if ((dimension["reference_type"] == "face" and
                     any(side not in {"left", "right"} for side in sides)) or
                    (dimension["reference_type"] == "axis" and sides != ("axis", "axis")) or
                    dimension["reference_type"] not in {"face", "axis"}):
                    raise PlanError("Dimension reference type differs from bound wall parts")
                for key, ref in (("start", start_ref), ("end", end_ref)):
                    resolved = _wall_reference_point(ref, walls, nodes)
                    wall_id = ref["wall_id"]
                    if any(wall_id in (join["wall_a_id"], join["wall_b_id"])
                           for join in plan["joins"]):
                        raise PlanError("Dimension binding at joined wall is not yet supported")
                    station = _number(ref["station_m"], "dimension wall station")
                    if any(opening["wall_id"] == wall_id and
                           _number(opening["offset_m"], "opening.offset_m") <= station <=
                           _number(opening["offset_m"], "opening.offset_m") +
                           _number(opening["width_m"], "opening.width_m")
                           for opening in plan["openings"]):
                        raise PlanError("Dimension binding falls in a wall opening")
                    node = nodes[dimension[key]]
                    if any(abs(resolved[axis] - node[axis]) > Decimal("0.000001")
                           for axis in (0, 1)):
                        raise PlanError("Dimension node differs from its bound wall reference")
            if bindings != set(dimensions):
                raise PlanError("Every v6 dimension requires exactly one wall binding")
        if plan["schema_version"] in {"planspec-7", "planspec-8"}:
            style = plan["dimension_style"]
            _keys(style, {"name", "text_height_m", "arrow_size_m", "gap_m",
                          "scale", "measurement_factor"}, "dimension style")
            if not _id(style["name"], "dimension style").startswith("OCS_"):
                raise PlanError("Dimension style must use a reserved OCS_ name")
            for key in ("text_height_m", "arrow_size_m"):
                if not Decimal("0.001") <= _number(style[key], f"dimension style.{key}") <= Decimal("0.5"):
                    raise PlanError("Dimension style size is out of scope")
            if not Decimal(0) <= _number(style["gap_m"], "dimension style.gap_m") <= Decimal("0.5") or \
                    _number(style["scale"], "dimension style.scale") != 1 or \
                    _number(style["measurement_factor"], "dimension style.measurement_factor") != 1:
                raise PlanError("Dimension style scale, factor or gap is out of scope")
            if not isinstance(plan["dimension_placements"], list):
                raise PlanError("Dimension placements must be an array")
            placements: set[str] = set()
            for placement in plan["dimension_placements"]:
                _keys(placement, {"dimension_id", "offset_m", "layer", "source"},
                      "dimension placement")
                name = placement["dimension_id"]
                if not isinstance(name, str) or name not in dimensions or name in placements:
                    raise PlanError("Dimension placement is missing, duplicated or dangling")
                placements.add(name)
                if not Decimal("0.01") <= _number(placement["offset_m"], "dimension placement.offset_m") <= Decimal(10):
                    raise PlanError("Dimension placement offset is out of scope")
                _id(placement["layer"], "dimension placement.layer")
                _source(placement["source"], "dimension placement.source")
            if placements != set(dimensions):
                raise PlanError("Every v7 dimension requires exactly one placement")
        if plan["schema_version"] == "planspec-8":
            if not isinstance(plan["obstacles"], list):
                raise PlanError("Obstacle collection must be an array")
            for obstacle in plan["obstacles"]:
                _keys(obstacle, {"id", "kind", "min_x_m", "min_y_m", "max_x_m",
                                 "max_y_m", "base_z_m", "height_m", "source"}, "obstacle")
                name = _id(obstacle["id"], "obstacle")
                if name in ids:
                    raise PlanError("Duplicate PlanSpec ID")
                ids.add(name)
                if not isinstance(obstacle["kind"], str) or \
                        obstacle["kind"] not in {"fixed_partition", "furniture", "annotation"}:
                    raise PlanError("Obstacle kind is unsupported")
                bounds = [_number(obstacle[key], f"obstacle.{key}") for key in
                          ("min_x_m", "min_y_m", "max_x_m", "max_y_m")]
                if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                    raise PlanError("Obstacle XY bounds must have positive area")
                if _number(obstacle["base_z_m"], "obstacle.base_z_m") < 0 or \
                        _number(obstacle["height_m"], "obstacle.height_m") <= 0:
                    raise PlanError("Obstacle elevation or height is invalid")
                _source(obstacle["source"], "obstacle.source")


def analyze_architecture(plan: dict[str, Any]) -> dict[str, Any]:
    """Validate wall/opening identity and spacing before any CAD command is emitted."""
    _validate_basic(plan)
    if plan["schema_version"] not in {"planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
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
                                "width_m": format(end - start, "f"),
                                **({"swing": opening["swing"]} if "swing" in opening else {}),
                                **({"elevation": opening["elevation"]} if "elevation" in opening else {})})
    for wall_id, intervals in openings_by_wall.items():
        intervals.sort()
        for first, second in zip(intervals, intervals[1:]):
            if second[0] - first[1] < Decimal("0.001"):
                raise PlanError(f"Openings {first[2]} and {second[2]} overlap or touch on {wall_id}")
    return {"schema_version": "planspec-architecture-1", "status": "validated",
            "walls": walls, "openings": opening_results,
            **({"joins": sorted(({"id": item["id"], "wall_a_id": item["wall_a_id"],
                                   "wall_a_end": item["wall_a_end"],
                                   "wall_b_id": item["wall_b_id"],
                                   "wall_b_end": item["wall_b_end"], "style": item["style"]}
                                  for item in plan["joins"]), key=lambda item: item["id"])}
               if plan["schema_version"] in {"planspec-5", "planspec-6", "planspec-7", "planspec-8"} else {}),
            "scope": "straight_wall_axes_and_opening_intervals"}


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
    """Report 2D primitive intersections without guessing architectural intent.

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
    line_circle_intersections = []
    for line_id, a, b, _ in segments:
        vx, vy = b[0] - a[0], b[1] - a[1]
        length_squared = vx * vx + vy * vy
        for circle_id, center, radius in circles:
            wx, wy = a[0] - center[0], a[1] - center[1]
            projection = -(vx * wx + vy * wy) / length_squared
            discriminant = (vx * wx + vy * wy) ** 2 - length_squared * (wx * wx + wy * wy - radius * radius)
            if discriminant < 0:
                continue
            root = discriminant.sqrt()
            parameters = {(projection * length_squared + sign * root) / length_squared
                          for sign in (-1, 1)}
            count = sum(Decimal(0) <= t <= Decimal(1) for t in parameters)
            if count:
                line_circle_intersections.append({"line_id": line_id, "circle_id": circle_id,
                                                  "kind": "tangent" if discriminant == 0 else
                                                          "one_on_segment" if count == 1 else "secant"})
    circle_circle_intersections = []
    for (first_id, a, first_radius), (second_id, b, second_radius) in combinations(circles, 2):
        distance_squared = (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
        if distance_squared == 0:
            continue
        outer = (first_radius + second_radius) ** 2
        inner = (first_radius - second_radius) ** 2
        if inner <= distance_squared <= outer:
            circle_circle_intersections.append({"circle_ids": [first_id, second_id],
                                                "kind": "tangent" if distance_squared in (inner, outer)
                                                        else "secant"})
    issues = (duplicates or overlaps or crossings or t_junctions or open_endpoints or
              circle_duplicates or line_circle_intersections or circle_circle_intersections)
    return {"schema_version": "planspec-geometry-qa-2",
            "status": "review_required" if issues else "clear",
            "duplicate_lines": duplicates, "duplicate_circles": circle_duplicates,
            "overlapping_lines": overlaps, "interior_crossings": crossings,
            "t_junctions": t_junctions, "open_line_endpoints": open_endpoints,
            "line_circle_intersections": line_circle_intersections,
            "circle_circle_intersections": circle_circle_intersections,
            "scope": "2d_line_circle_primitives_no_contour_semantics"}


def _coordinate(value: Decimal) -> str:
    if abs(value) > Decimal("1000000"):
        raise PlanError("Coordinate exceeds compiler range")
    rounded = value.quantize(Decimal("0.000001"))
    if rounded == 0:
        if value != 0:
            raise PlanError("Coordinate is below compiler precision")
        return "0"
    return format(rounded, "f").rstrip("0").rstrip(".")


def _single_wall_commands(wall: dict, nodes: dict, origin: tuple[Decimal, Decimal]) -> list[dict]:
    """Compile one straight wall without openings as a closed four-line outline."""
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    if length == 0:
        raise PlanError("Wall axis has zero length")
    half = _number(wall["thickness_m"], "wall.thickness_m") / 2
    offset = (-dy * half / length, dx * half / length)
    corners = [(a[0] + offset[0], a[1] + offset[1]),
               (b[0] + offset[0], b[1] + offset[1]),
               (b[0] - offset[0], b[1] - offset[1]),
               (a[0] - offset[0], a[1] - offset[1])]
    commands = []
    for index in range(4):
        start, end = corners[index], corners[(index + 1) % 4]
        coords = [*(_coordinate(start[axis] + origin[axis]) for axis in (0, 1)),
                  *(_coordinate(end[axis] + origin[axis]) for axis in (0, 1))]
        if coords[:2] == coords[2:]:
            raise PlanError(f"Wall {wall['id']} outline collapses at compiler precision")
        commands.append({"planspec_id": f"{wall['id']}__edge_{index}",
                         "source_id": wall["id"], "part": f"edge_{index}",
                         "command": f"LINE {coords[0]},{coords[1]} {coords[2]},{coords[3]}",
                         "layer": wall["layer"]})
    return commands


def _clear_opening_wall_commands(wall: dict, openings: list[dict], nodes: dict,
                                 origin: tuple[Decimal, Decimal]) -> list[dict]:
    """Compile one straight wall with explicit clear gaps and jambs, no symbols."""
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    ux, uy = dx / length, dy / length
    half = _number(wall["thickness_m"], "wall.thickness_m") / 2
    intervals = sorted(((_number(item["offset_m"], "opening.offset_m"),
                         _number(item["offset_m"], "opening.offset_m") +
                         _number(item["width_m"], "opening.width_m"), item["id"])
                        for item in openings), key=lambda item: (item[0], item[2]))

    def point(distance: Decimal, side: int) -> tuple[Decimal, Decimal]:
        return (a[0] + ux * distance - uy * half * side,
                a[1] + uy * distance + ux * half * side)

    def line(part_id: str, source_id: str, part: str,
             start: tuple[Decimal, Decimal], end: tuple[Decimal, Decimal]) -> dict:
        coords = [*(_coordinate(start[axis] + origin[axis]) for axis in (0, 1)),
                  *(_coordinate(end[axis] + origin[axis]) for axis in (0, 1))]
        if coords[:2] == coords[2:]:
            raise PlanError(f"Wall {wall['id']} gap outline collapses at compiler precision")
        return {"planspec_id": part_id, "source_id": source_id, "part": part,
                "command": f"LINE {coords[0]},{coords[1]} {coords[2]},{coords[3]}",
                "layer": wall["layer"]}

    spans = []
    previous = Decimal(0)
    for start, end, _ in intervals:
        spans.append((previous, start))
        previous = end
    spans.append((previous, length))
    commands = []
    for side, side_name in ((1, "left"), (-1, "right")):
        for index, (start, end) in enumerate(spans):
            part = f"{side_name}_span_{index}"
            commands.append(line(f"{wall['id']}__{part}", wall["id"], part,
                                 point(start, side), point(end, side)))
    for name, distance in (("start_cap", Decimal(0)), ("end_cap", length)):
        commands.append(line(f"{wall['id']}__{name}", wall["id"], name,
                             point(distance, 1), point(distance, -1)))
    for start, end, opening_id in intervals:
        for name, distance in (("jamb_start", start), ("jamb_end", end)):
            commands.append(line(f"{opening_id}__{name}", opening_id, name,
                                 point(distance, 1), point(distance, -1)))
    return commands


def _single_door_symbol_commands(wall: dict, door: dict, nodes: dict,
                                 origin: tuple[Decimal, Decimal]) -> list[dict]:
    """Emit one 90-degree plan-view leaf and its swing arc on the declared wall face."""
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    ux, uy = dx / length, dy / length
    normal = (-uy, ux)
    width = _number(door["width_m"], "door.width_m")
    offset = _number(door["offset_m"], "door.offset_m")
    hinge_at_start = door["swing"]["hinge"] == "start"
    side = 1 if door["swing"]["side"] == "left" else -1
    hinge_distance = offset if hinge_at_start else offset + width
    half = _number(wall["thickness_m"], "wall.thickness_m") / 2
    hinge = (a[0] + ux * hinge_distance + normal[0] * half * side,
             a[1] + uy * hinge_distance + normal[1] * half * side)
    along = (ux if hinge_at_start else -ux, uy if hinge_at_start else -uy)
    outward = (normal[0] * side, normal[1] * side)
    closed = (hinge[0] + along[0] * width, hinge[1] + along[1] * width)
    opened = (hinge[0] + outward[0] * width, hinge[1] + outward[1] * width)
    diagonal = width / Decimal(2).sqrt()
    midpoint = (hinge[0] + (along[0] + outward[0]) * diagonal,
                hinge[1] + (along[1] + outward[1]) * diagonal)

    def xy(point: tuple[Decimal, Decimal]) -> str:
        return ",".join(_coordinate(point[index] + origin[index]) for index in (0, 1))

    points = [xy(point) for point in (hinge, closed, midpoint, opened)]
    if len(set(points)) != 4:
        raise PlanError(f"Door {door['id']} symbol collapses at compiler precision")
    return [{"planspec_id": f"{door['id']}__leaf_open", "source_id": door["id"],
             "part": "leaf_open", "command": f"LINE {points[0]} {points[3]}",
             "layer": wall["layer"]},
            {"planspec_id": f"{door['id']}__swing_arc", "source_id": door["id"],
             "part": "swing_arc", "command": f"ARC {points[1]} {points[2]} {points[3]}",
             "layer": wall["layer"]}]


def _single_window_symbol_commands(wall: dict, window: dict, nodes: dict,
                                   origin: tuple[Decimal, Decimal]) -> list[dict]:
    """Emit two 3D frame rails so sill/head heights survive DWG persistence."""
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    ux, uy = dx / length, dy / length
    offset = _number(window["offset_m"], "window.offset_m")
    width = _number(window["width_m"], "window.width_m")
    half_rail = _number(wall["thickness_m"], "wall.thickness_m") / 4
    result = []
    for part, side, elevation_key in (("sill_rail", 1, "sill_m"),
                                      ("head_rail", -1, "head_m")):
        z = _number(window["elevation"][elevation_key], f"window.{elevation_key}")
        def xyz(distance: Decimal) -> str:
            x = a[0] + ux * distance - uy * half_rail * side + origin[0]
            y = a[1] + uy * distance + ux * half_rail * side + origin[1]
            return ",".join((_coordinate(x), _coordinate(y), _coordinate(z)))
        start, end = xyz(offset), xyz(offset + width)
        if start == end:
            raise PlanError(f"Window {window['id']} rail collapses at compiler precision")
        result.append({"planspec_id": f"{window['id']}__{part}",
                       "source_id": window["id"], "part": part,
                       "command": f"LINE {start} {end}", "layer": wall["layer"]})
    return result


def _orthogonal_union_commands(join: dict, walls: dict[str, dict], nodes: dict,
                               origin: tuple[Decimal, Decimal]) -> list[dict]:
    """Outline the union of two perpendicular end-connected wall rectangles."""
    first, second = walls[join["wall_a_id"]], walls[join["wall_b_id"]]
    junction = nodes[first[join["wall_a_end"]]]
    far_a = nodes[first["start" if join["wall_a_end"] == "end" else "end"]]
    far_b = nodes[second["start" if join["wall_b_end"] == "end" else "end"]]
    av = (far_a[0] - junction[0], far_a[1] - junction[1])
    bv = (far_b[0] - junction[0], far_b[1] - junction[1])
    length_a = (av[0] * av[0] + av[1] * av[1]).sqrt()
    length_b = (bv[0] * bv[0] + bv[1] * bv[1]).sqrt()
    half = _number(first["thickness_m"], "wall.thickness_m") / 2
    if length_a <= half or length_b <= half:
        raise PlanError("Joined wall is too short for an orthogonal outline union")
    u = (av[0] / length_a, av[1] / length_a)
    v = (bv[0] / length_b, bv[1] / length_b)
    local = [(Decimal(0), -half), (length_a, -half), (length_a, half),
             (half, half), (half, length_b), (-half, length_b),
             (-half, Decimal(0)), (Decimal(0), Decimal(0))]
    owners = [first["id"]] * 3 + [second["id"]] * 3 + [join["id"]] * 2

    def xy(point: tuple[Decimal, Decimal]) -> str:
        x = junction[0] + u[0] * point[0] + v[0] * point[1] + origin[0]
        y = junction[1] + u[1] * point[0] + v[1] * point[1] + origin[1]
        return f"{_coordinate(x)},{_coordinate(y)}"

    vertices = [xy(point) for point in local]
    if len(set(vertices)) != len(vertices):
        raise PlanError("Joined wall outline collapses at compiler precision")
    commands = []
    for index, (start, end) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
        if start == end:
            raise PlanError("Joined wall edge collapses at compiler precision")
        commands.append({"planspec_id": f"{join['id']}__outline_{index}",
                         "source_id": owners[index], "part": f"outline_{index}",
                         "command": f"LINE {start} {end}", "layer": first["layer"]})
    return commands


def _door_swing_extrema(wall: dict, door: dict,
                        nodes: dict[str, tuple[Decimal, Decimal]]) -> list[tuple[Decimal, Decimal]]:
    """Quarter-circle endpoints and included cardinal extrema in wall coordinates."""
    a, b = nodes[wall["start"]], nodes[wall["end"]]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = (dx * dx + dy * dy).sqrt()
    ux, uy = dx / length, dy / length
    normal = (-uy, ux)
    width = _number(door["width_m"], "door.width_m")
    offset = _number(door["offset_m"], "door.offset_m")
    from_start = door["swing"]["hinge"] == "start"
    side = 1 if door["swing"]["side"] == "left" else -1
    distance = offset if from_start else offset + width
    half = _number(wall["thickness_m"], "wall.thickness_m") / 2
    hinge = (a[0] + ux * distance + normal[0] * half * side,
             a[1] + uy * distance + normal[1] * half * side)
    along = (ux if from_start else -ux, uy if from_start else -uy)
    outward = (normal[0] * side, normal[1] * side)
    closed = (hinge[0] + along[0] * width, hinge[1] + along[1] * width)
    opened = (hinge[0] + outward[0] * width, hinge[1] + outward[1] * width)
    start_angle = math.atan2(float(along[1]), float(along[0]))
    ccw = along[0] * outward[1] - along[1] * outward[0] > 0
    quarter = math.pi / 2
    points = [hinge, closed, opened]
    for index, direction in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
        angle = index * quarter
        delta = ((angle - start_angle) if ccw else (start_angle - angle)) % (2 * math.pi)
        if delta <= quarter + 1e-12:
            points.append((hinge[0] + width * direction[0],
                           hinge[1] + width * direction[1]))
    return points


def analyze_door_clearance(plan: dict[str, Any]) -> dict[str, Any]:
    """Report open leaf and swept quarter-disk contacts with source geometry.

    A line is not assumed to be an obstruction; contour membership only names
    its source category. Tangent and endpoint-only contacts are excluded.
    """
    _validate_basic(plan)
    if plan["schema_version"] not in {"planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"}:
        return {"schema_version": "planspec-door-clearance-qa-3", "status": "unavailable",
                "strict_crossings": [], "sweep_intersections": [],
                "typed_obstacle_intersections": [],
                "scope": "v4_or_later_quarter_sweep_against_source_lines"}
    nodes = {node["id"]: (_number(node["x"], "node.x"), _number(node["y"], "node.y"))
             for node in plan["nodes"]}
    walls = {wall["id"]: wall for wall in plan["walls"]}
    contour_lines = {line_id for contour in plan["topology"]["contours"]
                     for line_id in contour["line_ids"]}

    def orient(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal],
               c: tuple[Decimal, Decimal]) -> Decimal:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def segment_enters_sweep(hinge, closed, opened, a, b, width: Decimal) -> bool:
        along = ((closed[0] - hinge[0]) / width, (closed[1] - hinge[1]) / width)
        outward = ((opened[0] - hinge[0]) / width, (opened[1] - hinge[1]) / width)

        def local(point):
            delta = (point[0] - hinge[0], point[1] - hinge[1])
            return (delta[0] * along[0] + delta[1] * along[1],
                    delta[0] * outward[0] + delta[1] * outward[1])

        start, end = local(a), local(b)
        delta = (end[0] - start[0], end[1] - start[1])
        low, high = Decimal(0), Decimal(1)
        epsilon = Decimal("0.000000001")
        for axis in (0, 1):
            if delta[axis] == 0:
                if start[axis] <= epsilon:
                    return False
                continue
            edge = (epsilon - start[axis]) / delta[axis]
            if delta[axis] > 0:
                low = max(low, edge)
            else:
                high = min(high, edge)
        if low >= high:
            return False
        norm = delta[0] * delta[0] + delta[1] * delta[1]
        closest = max(low, min(high,
            -(start[0] * delta[0] + start[1] * delta[1]) / norm))
        point = (start[0] + delta[0] * closest, start[1] + delta[1] * closest)
        return point[0] * point[0] + point[1] * point[1] < (width - epsilon) ** 2

    crossings = []
    sweep_intersections = []
    typed_obstacle_intersections = []
    for door in sorted((item for item in plan["openings"] if item["kind"] == "door"),
                       key=lambda item: item["id"]):
        hinge, closed, opened = _door_swing_extrema(walls[door["wall_id"]], door, nodes)[:3]
        width = _number(door["width_m"], "door.width_m")
        for line in sorted(plan["lines"], key=lambda item: item["id"]):
            a, b = nodes[line["start"]], nodes[line["end"]]
            category = "contour" if line["id"] in contour_lines else "unclassified"
            if orient(hinge, opened, a) * orient(hinge, opened, b) < 0 and \
                    orient(a, b, hinge) * orient(a, b, opened) < 0:
                crossings.append({"door_id": door["id"], "line_id": line["id"],
                                  "line_category": category})
            if segment_enters_sweep(hinge, closed, opened, a, b, width):
                sweep_intersections.append({"door_id": door["id"], "line_id": line["id"],
                                            "line_category": category})
        if plan["schema_version"] == "planspec-8":
            leaf_height = _number(door["swing"]["leaf_height_m"], "door.leaf_height_m")
            for obstacle in sorted(plan["obstacles"], key=lambda item: item["id"]):
                base = _number(obstacle["base_z_m"], "obstacle.base_z_m")
                if base >= leaf_height:
                    continue
                x0, y0, x1, y1 = (_number(obstacle[key], f"obstacle.{key}") for key in
                                   ("min_x_m", "min_y_m", "max_x_m", "max_y_m"))
                corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                intersects = x0 < hinge[0] < x1 and y0 < hinge[1] < y1 or any(
                    segment_enters_sweep(hinge, closed, opened, corners[index],
                                         corners[(index + 1) % 4], width)
                    for index in range(4))
                if intersects:
                    kind = obstacle["kind"]
                    source = obstacle["source"]
                    disposition = ("nonphysical" if kind == "annotation" else
                                   "blocking" if source["classification"] == "measured" else
                                   "review_blocked")
                    typed_obstacle_intersections.append({"door_id": door["id"],
                        "obstacle_id": obstacle["id"], "kind": kind,
                        "source_classification": source["classification"],
                        "source_confidence": source["confidence"],
                        "disposition": disposition})
    return {"schema_version": "planspec-door-clearance-qa-3",
            "status": "review_required" if crossings or sweep_intersections or
                      typed_obstacle_intersections else "clear",
            "strict_crossings": crossings, "sweep_intersections": sweep_intersections,
            "typed_obstacle_intersections": typed_obstacle_intersections,
            "scope": "v4_or_later_quarter_sweep_lines_and_v8_typed_rectangles_with_z_range"}


def _source_bounds(plan: dict[str, Any], nodes: dict[str, tuple[Decimal, Decimal]],
                   origin: tuple[Decimal, Decimal], dimension_status: str) -> dict[str, Any]:
    """Separate 2D source footprints from dimension references, excluding glyph extents."""
    architecture: list[tuple[Decimal, Decimal]] = []
    annotation: list[tuple[Decimal, Decimal]] = []
    unresolved: list[str] = []
    def add(target, point):
        target.append((point[0] + origin[0], point[1] + origin[1]))
    for line in plan["lines"]:
        add(architecture, nodes[line["start"]])
        add(architecture, nodes[line["end"]])
    for circle in plan["circles"]:
        center = nodes[circle["center"]]
        radius = _number(circle["radius"], "circle.radius")
        add(architecture, (center[0] - radius, center[1] - radius))
        add(architecture, (center[0] + radius, center[1] + radius))
    if "walls" in plan:
        for wall in plan["walls"]:
            a, b = nodes[wall["start"]], nodes[wall["end"]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = (dx * dx + dy * dy).sqrt()
            half = _number(wall["thickness_m"], "wall.thickness_m") / 2
            normal = (-dy * half / length, dx * half / length)
            for endpoint in (a, b):
                for sign in (-1, 1):
                    add(architecture, (endpoint[0] + sign * normal[0],
                                       endpoint[1] + sign * normal[1]))
        walls = {wall["id"]: wall for wall in plan["walls"]}
        for opening in plan["openings"]:
            if opening["kind"] == "door" and "swing" in opening:
                for point in _door_swing_extrema(walls[opening["wall_id"]], opening, nodes):
                    add(architecture, point)
            elif opening["kind"] == "door":
                unresolved.append("door_swing_without_v4_contract")
    for dimension in plan["dimensions"]:
        add(annotation, nodes[dimension["start"]])
        add(annotation, nodes[dimension["end"]])
    if dimension_status in {"compiled_single_horizontal_face_thickness",
                            "compiled_single_vertical_face_thickness"}:
        dimension = plan["dimensions"][0]
        placement = plan["dimension_placements"][0]
        a, b = nodes[dimension["start"]], nodes[dimension["end"]]
        offset = _number(placement["offset_m"], "offset_m")
        if dimension_status == "compiled_single_horizontal_face_thickness":
            add(annotation, (a[0] + offset, (a[1] + b[1]) / 2))
        else:
            add(annotation, ((a[0] + b[0]) / 2, a[1] + offset))
    elif plan["dimensions"]:
        unresolved.append("dimension_placement_or_rendered_extents")
    def box(points):
        if not points:
            return None
        return {"min_x": format(min(point[0] for point in points), "f"),
                "min_y": format(min(point[1] for point in points), "f"),
                "max_x": format(max(point[0] for point in points), "f"),
                "max_y": format(max(point[1] for point in points), "f")}
    return {"schema_version": "planspec-source-bounds-1",
            "architecture_bounds_m": box(architecture),
            "annotation_reference_bounds_m": box(annotation),
            "unresolved": sorted(unresolved),
            "scope": "2d_source_footprints_no_text_arrow_or_rendered_bounds"}


def dry_run(plan: dict[str, Any], *, capabilities: set[str] | None = None) -> dict[str, Any]:
    validate(plan)
    dimension_graph = analyze_dimension_graph(plan)
    topology = analyze_topology(plan)
    architecture = analyze_architecture(plan)
    geometry_qa = analyze_geometry(plan)
    door_clearance_qa = analyze_door_clearance(plan)
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
    wall_parts = 0
    wall_status = "not_applicable"
    if plan["schema_version"] in {"planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"} and plan["walls"]:
        wall_status = "unsupported"
        if plan["schema_version"] in {"planspec-5", "planspec-6", "planspec-7", "planspec-8"} and len(plan["walls"]) == 2 and \
                len(plan["joins"]) == 1 and not plan["openings"]:
            walls_by_id = {wall["id"]: wall for wall in plan["walls"]}
            join = plan["joins"][0]
            if set(walls_by_id) == {join["wall_a_id"], join["wall_b_id"]} and \
                    len({wall["layer"] for wall in plan["walls"]}) == 1:
                commands.extend(_orthogonal_union_commands(join, walls_by_id, nodes, origin))
                wall_parts = 8
                wall_status = "compiled_orthogonal_union_two_walls"
        elif len(plan["walls"]) == 1 and not plan["openings"]:
            commands.extend(_single_wall_commands(plan["walls"][0], nodes, origin))
            wall_parts = 4
            wall_status = "compiled_single_unopened_wall"
        elif len(plan["walls"]) == 1 and \
                all(opening["kind"] == "clear" for opening in plan["openings"]):
            commands.extend(_clear_opening_wall_commands(
                plan["walls"][0], plan["openings"], nodes, origin))
            wall_parts = 4 * (len(plan["openings"]) + 1)
            wall_status = "compiled_single_clear_opening_wall"
        elif plan["schema_version"] in {"planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"} and len(plan["walls"]) == 1 and \
                len(plan["openings"]) == 1 and plan["openings"][0]["kind"] == "door":
            wall, door = plan["walls"][0], plan["openings"][0]
            commands.extend(_clear_opening_wall_commands(wall, [door], nodes, origin))
            commands.extend(_single_door_symbol_commands(wall, door, nodes, origin))
            wall_parts = 10
            wall_status = "compiled_single_door_wall"
        elif plan["schema_version"] in {"planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"} and len(plan["walls"]) == 1 and \
                len(plan["openings"]) == 1 and plan["openings"][0]["kind"] == "window":
            wall, window = plan["walls"][0], plan["openings"][0]
            commands.extend(_clear_opening_wall_commands(wall, [window], nodes, origin))
            commands.extend(_single_window_symbol_commands(wall, window, nodes, origin))
            wall_parts = 10
            wall_status = "compiled_single_window_wall"
    dimension_status = "not_applicable" if not plan["dimensions"] else "unsupported"
    dimension_placement_qa = {"status": "unavailable",
                              "scope": "only_single_axis_aligned_face_thickness"}
    if (plan["schema_version"] in {"planspec-7", "planspec-8"} and len(plan["walls"]) == 1 and
            not plan["lines"] and not plan["circles"] and not plan["openings"] and
            not plan["joins"] and len(plan["dimensions"]) == 1 and
            wall_status == "compiled_single_unopened_wall"):
        wall = plan["walls"][0]
        dimension = plan["dimensions"][0]
        binding = plan["dimension_bindings"][0]
        placement = plan["dimension_placements"][0]
        a, b = nodes[wall["start"]], nodes[wall["end"]]
        horizontal = a[1] == b[1] and a[0] < b[0]
        vertical = a[0] == b[0] and a[1] < b[1]
        station = ((b[0] - a[0]) if horizontal else (b[1] - a[1])) / 2
        start_ref, end_ref = binding["start_ref"], binding["end_ref"]
        if ((horizontal and dimension["axis"] == "y" or
             vertical and dimension["axis"] == "x") and
                dimension["reference_type"] == "face" and
                start_ref["wall_id"] == wall["id"] and end_ref["wall_id"] == wall["id"] and
                start_ref["side"] == "left" and end_ref["side"] == "right" and
                _number(start_ref["station_m"], "station") == station and
                _number(end_ref["station_m"], "station") == station and
                binding["dimension_id"] == dimension["id"] == placement["dimension_id"]):
            start, end = nodes[dimension["start"]], nodes[dimension["end"]]
            offset = _number(placement["offset_m"], "offset_m")
            location = ((start[0] + offset, (start[1] + end[1]) / 2) if horizontal else
                        ((start[0] + end[0]) / 2, start[1] + offset))
            def point(value):
                return ",".join(_coordinate(value[axis] + origin[axis]) for axis in (0, 1))
            commands.append({"planspec_id": dimension["id"], "source_id": dimension["id"],
                             "part": "face_thickness_dimension",
                             "command": f"DIMLINEAR {point(start)} {point(end)} {point(location)}",
                             "layer": placement["layer"]})
            dimension_status = ("compiled_single_horizontal_face_thickness" if horizontal else
                                "compiled_single_vertical_face_thickness")
            beyond = location[0] > b[0] if horizontal else location[1] > b[1]
            dimension_placement_qa = {
                "status": "outside_wall_bounds" if beyond else "inside_wall_bounds",
                "wall_id": wall["id"], "dimension_id": dimension["id"],
                "wall_end_x_m" if horizontal else "wall_end_y_m":
                    format((b[0] + origin[0]) if horizontal else (b[1] + origin[1]), "f"),
                "dimension_line_x_m" if horizontal else "dimension_line_y_m":
                    format((location[0] + origin[0]) if horizontal else
                           (location[1] + origin[1]), "f"),
                "scope": "2d_dimension_line_position_only_no_text_extents"}
    if len({item["planspec_id"] for item in commands}) != len(commands):
        raise PlanError("Generated wall part ID collides with PlanSpec geometry ID")
    layers = sorted({item["layer"] for item in commands} - {"0"})
    # INSUNITS=6 is metres in DWG. A metric GUI template may otherwise default
    # to INSUNITS=4 (millimetres), silently changing insertion scale semantics.
    execution = [{"planspec_id": None, "command": "SETVAR INSUNITS 6", "layer": "0"}]
    if dimension_status in {"compiled_single_horizontal_face_thickness",
                            "compiled_single_vertical_face_thickness"}:
        style = plan["dimension_style"]
        name = style["name"]
        execution.extend({"planspec_id": None, "command": command, "layer": "0"} for command in (
            f"DIMSTYLE NEW {name}",
            f"DIMSTYLE SET {name} dimtxt {_coordinate(_number(style['text_height_m'], 'text_height_m'))}",
            f"DIMSTYLE SET {name} dimasz {_coordinate(_number(style['arrow_size_m'], 'arrow_size_m'))}",
            f"DIMSTYLE SET {name} dimgap {_coordinate(_number(style['gap_m'], 'gap_m'))}",
            f"DIMSTYLE SET {name} dimscale 1",
            f"DIMSTYLE SET {name} dimlfac 1",
            f"CDIMSTY {name}",
            "SETVAR DIMASSOC 2"))
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
    if plan["dimensions"] and dimension_status == "unsupported":
        missing.add("native_dimension")
    if wall_status == "unsupported":
        missing.add("wall_compilation")
    if plan["schema_version"] in {"planspec-3", "planspec-4", "planspec-5", "planspec-6", "planspec-7", "planspec-8"} and any(
            opening["kind"] != "clear" for opening in plan["openings"]) and \
            wall_status not in {"compiled_single_door_wall", "compiled_single_window_wall"}:
        missing.add("opening_compilation")
    if plan["schema_version"] in {"planspec-5", "planspec-6", "planspec-7", "planspec-8"} and plan["joins"] and \
            wall_status != "compiled_orthogonal_union_two_walls":
        missing.add("join_compilation")
    if layers and "layer_assignment" not in (capabilities or set()):
        missing.add("layer_assignment")
    unsupported = sorted(missing)
    source_bounds = _source_bounds(plan, nodes, origin, dimension_status)
    quality_blockers = (["dimension_line_inside_wall_bounds"]
                        if dimension_placement_qa["status"] == "inside_wall_bounds" else [])
    if any(item["line_category"] == "contour"
           for item in door_clearance_qa["sweep_intersections"]):
        quality_blockers.append("door_swing_sweep_crosses_contour")
    if any(item["disposition"] in {"blocking", "review_blocked"}
           for item in door_clearance_qa["typed_obstacle_intersections"]):
        quality_blockers.append("door_sweep_hits_typed_obstacle")
    wire = json.dumps(execution, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return {"schema_version": "planspec-dry-run-1", "commands": commands,
            "execution_steps": execution,
            "dwg_unit_profile": {"plan_units": "m", "insunits": 6},
            "dimension_graph": dimension_graph,
            "topology": topology,
            "architecture": architecture,
            "wall_compilation": {"status": wall_status, "generated_parts": wall_parts},
            "dimension_compilation": {"status": dimension_status,
                                      "generated_parts": 1 if dimension_status.startswith("compiled_") else 0},
            "dimension_placement_qa": dimension_placement_qa,
            "source_bounds": source_bounds,
            "geometry_qa": geometry_qa,
            "door_clearance_qa": door_clearance_qa,
            "commands_sha256": hashlib.sha256(wire).hexdigest(),
            "unsupported": unsupported, "quality_blockers": quality_blockers,
            "executable": not unsupported and not quality_blockers,
            "note": "Nonzero layers require layer_assignment in a manifest verified for this build"}
