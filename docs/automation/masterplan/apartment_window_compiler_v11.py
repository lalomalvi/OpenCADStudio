"""Bind the scoped north frame to PlanSpec v11 window geometry."""

from apartment_window_compiler_v2 import compose as compose_v2, WindowComposeError
from planspec import dry_run


def compose(base, observation):
    plan, prior, metadata = compose_v2(base, observation)
    plan["schema_version"] = "planspec-11"
    plan["window_symbols"] = [{
        "id": "north-window",
        "left_wall_line_id": "north-wall-left",
        "right_wall_line_id": "north-wall-right",
        "outer_rail_line_id": "north-window-centerline",
        "inner_rail_line_id": "north-window-lower",
        "left_jamb_line_id": "north-window-jamb-left",
        "right_jamb_line_id": "north-window-jamb-right",
        "layer": "A-WINDOW",
        "elevation_status": "unverified",
        "frame_profile_status": "schematic",
        "source": {"classification": "inferred", "confidence": 0.7,
                   "region_px": [457, 355, 558, 375]},
    }]
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (compiled["executable"] is not True or compiled["unsupported"] or
            compiled["quality_blockers"] or len(compiled["commands"]) != 40 or
            compiled["window_symbol_qa"]["status"] != "clear" or
            compiled["door_symbol_qa"]["status"] != "clear"):
        raise WindowComposeError("Typed PlanSpec window did not pass pre-CAD gates")
    return plan, compiled, {**metadata,
                            "schema_version": "m7-apartment-window-composite-3",
                            "compiler_mode": "planspec-11-typed-window",
                            "window_symbol_qa": compiled["window_symbol_qa"]}
