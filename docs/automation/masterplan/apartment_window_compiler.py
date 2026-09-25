"""Add one sourced schematic window opening to the partial apartment PlanSpec."""

from copy import deepcopy

from planspec import dry_run


class WindowComposeError(ValueError):
    pass


def compose(base, observation):
    if observation.get("status") != "passed_observation_only":
        raise WindowComposeError("Source observation has not passed")
    pixels = observation.get("observed_original_px")
    if not isinstance(pixels, list) or len(pixels) != 2 or any(
            abs(p[1] - 365) > 5 for p in pixels) or not 457 <= pixels[0][0] < pixels[1][0] <= 558:
        raise WindowComposeError("Window endpoints differ from frozen source interval")
    plan = deepcopy(base)
    if plan.get("schema_version") != "planspec-10":
        raise WindowComposeError("Expected partial apartment PlanSpec v10")
    original = next((item for item in plan["lines"] if item["id"] == "edge0"), None)
    p0 = next((item for item in plan["nodes"] if item["id"] == "p0"), None)
    p1 = next((item for item in plan["nodes"] if item["id"] == "p1"), None)
    if not original or original["start"] != "p0" or original["end"] != "p1" or not p0 or not p1:
        raise WindowComposeError("North host edge differs")
    def x_from_pixel(px):
        return round(p0["x"] + (px - 388) * (p1["x"] - p0["x"]) / (903 - 388), 6)
    left, right = (x_from_pixel(p[0]) for p in pixels)
    if not p0["x"] + 0.1 < left < right - 0.1 < p1["x"] - 0.1:
        raise WindowComposeError("Window gap is outside host")
    source = {"classification": "inferred", "confidence": min(0.93,
              observation["observation"]["confidence"]),
              "region_px": [457, 355, 558, 375]}
    plan["nodes"].extend([{"id": "north-window-left", "x": left, "y": p0["y"],
                           "source": source},
                          {"id": "north-window-right", "x": right, "y": p0["y"],
                           "source": source}])
    plan["lines"].remove(original)
    plan["lines"].extend([
        {"id": "north-wall-left", "start": "p0", "end": "north-window-left",
         "layer": "0", "source": source},
        {"id": "north-window-centerline", "start": "north-window-left",
         "end": "north-window-right", "layer": "A-WINDOW", "source": source},
        {"id": "north-wall-right", "start": "north-window-right", "end": "p1",
         "layer": "0", "source": source},
    ])
    contour = plan["topology"]["contours"][0]
    if contour["line_ids"][0] != "edge0":
        raise WindowComposeError("North contour differs")
    contour["line_ids"][:1] = ["north-wall-left", "north-window-centerline",
                              "north-wall-right"]
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 37 or \
            compiled["door_symbol_qa"]["status"] != "clear" or \
            compiled["topology"]["status"] != "validated":
        raise WindowComposeError("Window plan did not pass pre-CAD gates")
    host_lines = [line for line in plan["lines"] if line["id"] in
                  {"north-wall-left", "north-wall-right", "north-window-centerline"}]
    if len(host_lines) != 3 or any(line["id"] == "edge0" for line in plan["lines"]):
        raise WindowComposeError("North wall still bridges window")
    return plan, compiled, {"status": "schematic_window_centerline",
                            "left_x_m": left, "right_x_m": right,
                            "opening_width_m": round(right - left, 6),
                            "source_observed_px": pixels,
                            "limitation": "wall thickness, frame profile and glazing elevation unverified"}
