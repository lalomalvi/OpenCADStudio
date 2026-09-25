"""Add a second source-observed 2D window to the typed apartment PlanSpec."""

from copy import deepcopy

from planspec import dry_run


class SecondWindowError(ValueError):
    pass


def compose(base, observation):
    if observation.get("status") != "passed_observation_only":
        raise SecondWindowError("Second window source gate did not pass")
    pixels = observation.get("observed_original_px")
    if not isinstance(pixels, list) or len(pixels) != 2 or any(
            abs(point[1] - 365) > 5 for point in pixels) or \
            not 1150 <= pixels[0][0] < pixels[1][0] <= 1244:
        raise SecondWindowError("Second window endpoints differ from source interval")
    plan = deepcopy(base)
    if plan.get("schema_version") != "planspec-11" or len(plan.get("window_symbols", [])) != 1 or \
            plan["window_symbols"][0]["id"] != "north-window":
        raise SecondWindowError("Expected one typed first window")
    original = next((line for line in plan["lines"] if line["id"] == "edge4"), None)
    p4 = next((node for node in plan["nodes"] if node["id"] == "p4"), None)
    p5 = next((node for node in plan["nodes"] if node["id"] == "p5"), None)
    if not original or original["start"] != "p4" or original["end"] != "p5" or \
            not p4 or not p5:
        raise SecondWindowError("East north host edge differs")
    def x_from_pixel(px):
        return round(p4["x"] + (px - 1095) * (p5["x"] - p4["x"]) / (1287 - 1095), 6)
    left, right = (x_from_pixel(point[0]) for point in pixels)
    if not p4["x"] + 0.1 < left < right - 0.1 < p5["x"] - 0.1:
        raise SecondWindowError("Second window gap escapes host")
    lower = round(p4["y"] - 0.15, 6)
    source = {"classification": "inferred", "confidence": 0.7,
              "region_px": [1150, 355, 1244, 375]}
    plan["nodes"].extend([
        {"id": "east-window-left", "x": left, "y": p4["y"], "source": source},
        {"id": "east-window-right", "x": right, "y": p4["y"], "source": source},
        {"id": "east-window-lower-left", "x": left, "y": lower, "source": source},
        {"id": "east-window-lower-right", "x": right, "y": lower, "source": source},
    ])
    plan["lines"].remove(original)
    plan["lines"].extend([
        {"id": "east-north-wall-left", "start": "p4", "end": "east-window-left",
         "layer": "0", "source": source},
        {"id": "east-north-wall-right", "start": "east-window-right", "end": "p5",
         "layer": "0", "source": source},
        {"id": "east-window-outer", "start": "east-window-left",
         "end": "east-window-right", "layer": "A-WINDOW", "source": source},
        {"id": "east-window-inner", "start": "east-window-lower-left",
         "end": "east-window-lower-right", "layer": "A-WINDOW", "source": source},
        {"id": "east-window-jamb-left", "start": "east-window-left",
         "end": "east-window-lower-left", "layer": "A-WINDOW", "source": source},
        {"id": "east-window-jamb-right", "start": "east-window-right",
         "end": "east-window-lower-right", "layer": "A-WINDOW", "source": source},
    ])
    contour = plan["topology"]["contours"][0]["line_ids"]
    if contour.count("edge4") != 1:
        raise SecondWindowError("East north contour differs")
    index = contour.index("edge4")
    contour[index:index+1] = ["east-north-wall-left", "east-window-outer",
                              "east-north-wall-right"]
    plan["window_symbols"].append({
        "id": "east-north-window",
        "left_wall_line_id": "east-north-wall-left",
        "right_wall_line_id": "east-north-wall-right",
        "outer_rail_line_id": "east-window-outer",
        "inner_rail_line_id": "east-window-inner",
        "left_jamb_line_id": "east-window-jamb-left",
        "right_jamb_line_id": "east-window-jamb-right",
        "layer": "A-WINDOW", "elevation_status": "unverified",
        "frame_profile_status": "schematic", "source": source,
    })
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 45 or \
            compiled["window_symbol_qa"]["status"] != "clear" or \
            compiled["door_symbol_qa"]["status"] != "clear" or \
            compiled["topology"]["status"] != "validated":
        raise SecondWindowError("Two-window PlanSpec did not pass pre-CAD gates")
    return plan, compiled, {"schema_version": "m7-apartment-two-windows-composite-1",
                            "status": "two_schematic_windows",
                            "east_window_width_m": round(right - left, 6),
                            "east_frame_offset_m": 0.15,
                            "source_observed_px": pixels,
                            "window_symbol_qa": compiled["window_symbol_qa"],
                            "limitation": "both elevations and frame profiles unverified"}
