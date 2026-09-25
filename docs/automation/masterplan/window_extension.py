"""Insert a typed schematic window into an existing PlanSpec v11 host edge."""

from copy import deepcopy
from decimal import Decimal

from planspec import dry_run


class WindowExtensionError(ValueError):
    pass


def extend(base, *, host_id, window_id, first, second, inward, source):
    """Return a new plan and compiled preflight; first/second follow host direction."""
    plan = deepcopy(base)
    if plan.get("schema_version") != "planspec-11":
        raise WindowExtensionError("PlanSpec v11 required")
    lines = {line["id"]: line for line in plan["lines"]}
    nodes = {node["id"]: node for node in plan["nodes"]}
    host = lines.get(host_id)
    if not host or window_id in {item["id"] for item in plan["window_symbols"]}:
        raise WindowExtensionError("Host or window identity differs")
    a, b = nodes[host["start"]], nodes[host["end"]]
    def xy(values):
        if len(values) != 2:
            raise WindowExtensionError("2D coordinate required")
        return tuple(Decimal(str(value)) for value in values)
    origin = xy((a["x"], a["y"]))
    finish = xy((b["x"], b["y"]))
    p, q, v = xy(first), xy(second), xy(inward)
    u = (finish[0] - origin[0], finish[1] - origin[1])
    length2 = u[0] * u[0] + u[1] * u[1]
    if length2 <= 0:
        raise WindowExtensionError("Degenerate host")
    cross = lambda x, y: x[0] * y[1] - x[1] * y[0]
    rel_p = (p[0] - origin[0], p[1] - origin[1])
    rel_q = (q[0] - origin[0], q[1] - origin[1])
    tp = (rel_p[0] * u[0] + rel_p[1] * u[1]) / length2
    tq = (rel_q[0] * u[0] + rel_q[1] * u[1]) / length2
    width2 = (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2
    depth2 = v[0] ** 2 + v[1] ** 2
    if (abs(cross(u, rel_p)) > Decimal("0.000001")
            or abs(cross(u, rel_q)) > Decimal("0.000001")
            or not Decimal("0.01") < tp < tq < Decimal("0.99")
            or not Decimal("0.09") <= width2 <= Decimal("25")
            or not Decimal("0.0009") <= depth2 <= Decimal("0.25")
            or abs(u[0] * v[0] + u[1] * v[1]) > Decimal("0.000001")):
        raise WindowExtensionError("Window does not fit the directed host edge")
    ids = {item["id"] for item in plan["nodes"]} | set(lines)
    names = {suffix: f"{window_id}-{suffix}" for suffix in
             ("first", "second", "inner-first", "inner-second", "wall-first",
              "wall-second", "outer", "inner", "jamb-first", "jamb-second")}
    if ids.intersection(names.values()):
        raise WindowExtensionError("Window node or line ID already exists")
    geometry = {"first": p, "second": q,
                "inner-first": (p[0] + v[0], p[1] + v[1]),
                "inner-second": (q[0] + v[0], q[1] + v[1])}
    for suffix, (x, y) in geometry.items():
        plan["nodes"].append({"id": names[suffix], "x": float(x), "y": float(y),
                              "source": source})
    plan["lines"].remove(host)
    specs = [
        ("wall-first", host["start"], names["first"], host["layer"]),
        ("wall-second", names["second"], host["end"], host["layer"]),
        ("outer", names["first"], names["second"], "A-WINDOW"),
        ("inner", names["inner-first"], names["inner-second"], "A-WINDOW"),
        ("jamb-first", names["first"], names["inner-first"], "A-WINDOW"),
        ("jamb-second", names["second"], names["inner-second"], "A-WINDOW"),
    ]
    plan["lines"].extend({"id": names[key], "start": start, "end": end,
                          "layer": layer, "source": source}
                         for key, start, end, layer in specs)
    contour = plan["topology"]["contours"][0]["line_ids"]
    if contour.count(host_id) != 1:
        raise WindowExtensionError("Directed host is not unique in contour")
    index = contour.index(host_id)
    contour[index:index + 1] = [names["wall-first"], names["outer"],
                                names["wall-second"]]
    plan["window_symbols"].append({
        "id": window_id,
        "left_wall_line_id": names["wall-first"],
        "right_wall_line_id": names["wall-second"],
        "outer_rail_line_id": names["outer"],
        "inner_rail_line_id": names["inner"],
        "left_jamb_line_id": names["jamb-first"],
        "right_jamb_line_id": names["jamb-second"],
        "layer": "A-WINDOW", "elevation_status": "unverified",
        "frame_profile_status": "schematic", "source": source,
    })
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or \
            compiled["window_symbol_qa"]["status"] != "clear" or \
            compiled["topology"]["status"] != "validated":
        raise WindowExtensionError("Extended PlanSpec did not pass CAD preflight")
    return plan, compiled
