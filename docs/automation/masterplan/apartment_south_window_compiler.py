"""Add one source-observed schematic south window to the typed apartment."""

from copy import deepcopy

from planspec import dry_run


class SouthWindowError(ValueError):
    pass


def compose(base, observation):
    if observation.get("status") != "passed_observation_only":
        raise SouthWindowError("South window source gate did not pass")
    pixels = observation.get("observed_original_px")
    if not isinstance(pixels, list) or len(pixels) != 2 or any(
            abs(point[1] - 869) > 5 for point in pixels) or \
            not 1152 <= pixels[0][0] < pixels[1][0] <= 1244:
        raise SouthWindowError("South window endpoints differ from source interval")
    plan = deepcopy(base)
    if plan.get("schema_version") != "planspec-11" or \
            {item["id"] for item in plan.get("window_symbols", [])} != \
            {"north-window", "east-north-window"}:
        raise SouthWindowError("Expected two typed upper windows")
    host = next((line for line in plan["lines"] if line["id"] == "edge6"), None)
    p6 = next((node for node in plan["nodes"] if node["id"] == "p6"), None)
    p7 = next((node for node in plan["nodes"] if node["id"] == "p7"), None)
    if not host or host["start"] != "p6" or host["end"] != "p7" or not p6 or not p7:
        raise SouthWindowError("South host edge differs")

    def x_from_pixel(px):
        return round(p7["x"] + (px - 1090) * (p6["x"] - p7["x"]) / (1284 - 1090), 6)

    visual_left, visual_right = (x_from_pixel(point[0]) for point in pixels)
    if not p7["x"] + 0.1 < visual_left < visual_right - 0.1 < p6["x"] - 0.1:
        raise SouthWindowError("South window gap escapes host")
    # edge6 is traversed right-to-left in the exterior contour.
    first, second = visual_right, visual_left
    inner_y = round(p6["y"] + 0.15, 6)
    source = {"classification": "inferred", "confidence": 0.7,
              "region_px": [1152, 855, 1244, 880]}
    plan["nodes"].extend([
        {"id": "south-window-first", "x": first, "y": p6["y"], "source": source},
        {"id": "south-window-second", "x": second, "y": p6["y"], "source": source},
        {"id": "south-window-inner-first", "x": first, "y": inner_y, "source": source},
        {"id": "south-window-inner-second", "x": second, "y": inner_y, "source": source},
    ])
    plan["lines"].remove(host)
    plan["lines"].extend([
        {"id": "south-wall-first", "start": "p6", "end": "south-window-first",
         "layer": "0", "source": source},
        {"id": "south-wall-second", "start": "south-window-second", "end": "p7",
         "layer": "0", "source": source},
        {"id": "south-window-outer", "start": "south-window-first",
         "end": "south-window-second", "layer": "A-WINDOW", "source": source},
        {"id": "south-window-inner", "start": "south-window-inner-first",
         "end": "south-window-inner-second", "layer": "A-WINDOW", "source": source},
        {"id": "south-window-jamb-first", "start": "south-window-first",
         "end": "south-window-inner-first", "layer": "A-WINDOW", "source": source},
        {"id": "south-window-jamb-second", "start": "south-window-second",
         "end": "south-window-inner-second", "layer": "A-WINDOW", "source": source},
    ])
    contour = plan["topology"]["contours"][0]["line_ids"]
    if contour.count("edge6") != 1:
        raise SouthWindowError("South contour differs")
    index = contour.index("edge6")
    contour[index:index+1] = ["south-wall-first", "south-window-outer",
                              "south-wall-second"]
    plan["window_symbols"].append({
        "id": "south-window", "left_wall_line_id": "south-wall-first",
        "right_wall_line_id": "south-wall-second",
        "outer_rail_line_id": "south-window-outer",
        "inner_rail_line_id": "south-window-inner",
        "left_jamb_line_id": "south-window-jamb-first",
        "right_jamb_line_id": "south-window-jamb-second",
        "layer": "A-WINDOW", "elevation_status": "unverified",
        "frame_profile_status": "schematic", "source": source,
    })
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if not compiled["executable"] or compiled["unsupported"] or \
            compiled["quality_blockers"] or len(compiled["commands"]) != 50 or \
            compiled["window_symbol_qa"]["status"] != "clear" or \
            compiled["door_symbol_qa"]["status"] != "clear" or \
            compiled["topology"]["status"] != "validated":
        raise SouthWindowError("Three-window PlanSpec did not pass pre-CAD gates")
    return plan, compiled, {
        "schema_version": "m7-apartment-three-windows-composite-1",
        "status": "three_schematic_windows",
        "south_window_width_m": round(visual_right - visual_left, 6),
        "south_frame_offset_m": 0.15,
        "source_observed_px": pixels,
        "window_symbol_qa": compiled["window_symbol_qa"],
        "limitation": "elevations and frame profiles unverified",
    }
