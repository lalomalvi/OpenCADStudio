"""Promote the scoped apartment door to the typed PlanSpec v10 arc contract."""

from __future__ import annotations

from apartment_door_compiler import compose as compose_v1, ApartmentDoorError
from planspec import dry_run


def compose(base_plan: dict, wall_observation: dict,
            door_observation: dict, wall_freeze: dict) -> tuple[dict, dict, dict]:
    plan, previous, metadata = compose_v1(
        base_plan, wall_observation, door_observation, wall_freeze)
    old_arc = previous["commands"][-1]
    if old_arc["planspec_id"] != "door-swing" or old_arc["part"] != "door_swing_arc":
        raise ApartmentDoorError("Previous scoped door symbol differs")
    plan["schema_version"] = "planspec-10"
    plan["door_symbols"] = [{
        "id": "door-swing", "opposite_line_id": "horizontal3",
        "hinge_line_id": "door-jamb-wall", "leaf_line_id": "door-leaf",
        "layer": "A-DOOR", "source": {
            "classification": "inferred", "confidence": 0.7,
            "region_px": [945, 655, 1005, 712]}}]
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (compiled["executable"] is not True or compiled["unsupported"] or
            compiled["quality_blockers"] or len(compiled["commands"]) != 35 or
            compiled.get("door_symbol_qa", {}).get("status") != "clear" or
            compiled["commands"][-1]["planspec_id"] != "door-swing" or
            compiled["commands"][-1]["part"] != "door_symbol_arc"):
        raise ApartmentDoorError("PlanSpec v10 door gate did not pass")
    metadata = {**metadata, "schema_version": "m7-apartment-door-composite-2",
                "compiler_mode": "planspec-10-native-door-symbol",
                "door_symbol_qa": compiled["door_symbol_qa"]}
    return plan, compiled, metadata
