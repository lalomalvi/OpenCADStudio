"""Add the visible lower rail and jambs to the scoped north window."""

from apartment_window_compiler import compose as compose_v1, WindowComposeError
from planspec import dry_run


def compose(base, observation):
    plan, prior, metadata = compose_v1(base, observation)
    top_left = next(node for node in plan["nodes"] if node["id"] == "north-window-left")
    top_right = next(node for node in plan["nodes"] if node["id"] == "north-window-right")
    # Source frame spans approximately y=359..370 px; 0.15 m is a scoped
    # schematic offset at this plan's calibration, not a measured profile.
    lower_y = round(top_left["y"] - 0.15, 6)
    source = {"classification": "inferred", "confidence": 0.7,
              "region_px": [457, 355, 558, 375]}
    plan["nodes"].extend([
        {"id": "north-window-lower-left", "x": top_left["x"], "y": lower_y,
         "source": source},
        {"id": "north-window-lower-right", "x": top_right["x"], "y": lower_y,
         "source": source},
    ])
    plan["lines"].extend([
        {"id": "north-window-lower", "start": "north-window-lower-left",
         "end": "north-window-lower-right", "layer": "A-WINDOW", "source": source},
        {"id": "north-window-jamb-left", "start": "north-window-left",
         "end": "north-window-lower-left", "layer": "A-WINDOW", "source": source},
        {"id": "north-window-jamb-right", "start": "north-window-right",
         "end": "north-window-lower-right", "layer": "A-WINDOW", "source": source},
    ])
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (compiled["executable"] is not True or compiled["unsupported"] or
            compiled["quality_blockers"] or len(compiled["commands"]) != 40 or
            compiled["door_symbol_qa"]["status"] != "clear" or
            compiled["topology"]["status"] != "validated"):
        raise WindowComposeError("Four-line window frame did not pass pre-CAD gates")
    metadata = {**metadata, "status": "schematic_four_line_window_frame",
                "frame_offset_m": 0.15,
                "limitation": "frame profile, wall thickness and glazing elevation unverified"}
    return plan, compiled, metadata
