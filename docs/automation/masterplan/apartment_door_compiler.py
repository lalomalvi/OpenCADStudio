"""Compose one source-backed door and missing jamb wall into the partial apartment.

This is a development composite, not a general PlanSpec door opening compiler.
The opening already exists between two wall segments; it is never filled.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math

from planspec import dry_run


class ApartmentDoorError(ValueError):
    pass


def _last_observation(events_path):
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    messages = [event["item"]["text"] for event in events
                if event.get("type") == "item.completed" and
                event.get("item", {}).get("type") == "agent_message"]
    if len(messages) != 1 or sum(event.get("type") == "turn.completed"
                                 for event in events) != 1:
        raise ApartmentDoorError("Exactly one terminal model observation required")
    return json.loads(messages[0])


def _point_text(point):
    return f"{point[0]:.9f},{point[1]:.9f}"


def compose(base_plan: dict, wall_observation: dict,
            door_observation: dict, wall_freeze: dict) -> tuple[dict, dict, dict]:
    if (base_plan.get("schema_version") != "planspec-8" or
            len(base_plan.get("lines", [])) != 21 or
            len(base_plan.get("dimensions", [])) != 7 or
            len(base_plan.get("walls", [])) != 1 or
            base_plan["walls"][0]["layer"] != "OCS_DIM_REF" or
            wall_freeze.get("crop_original_xyxy") != [970, 690, 1025, 760] or
            wall_freeze.get("scale") != 10 or
            wall_freeze.get("expected_original_start") != [1000, 708] or
            wall_freeze.get("expected_original_end") != [1000, 744] or
            wall_freeze.get("tolerance_original_px") != 10 or
            wall_observation.get("schema_version") != "ocs-single-wall-crop-1" or
            wall_observation.get("status") != "observed" or
            door_observation.get("schema_version") != "ocs-door-three-points-1" or
            door_observation.get("status") != "estimated"):
        raise ApartmentDoorError("Source or composite scope differs")
    start, end = wall_observation.get("start_px"), wall_observation.get("end_px")
    if any(not isinstance(point, list) or len(point) != 2 or
           any(type(value) is not int for value in point)
           for point in (start, end)):
        raise ApartmentDoorError("Wall crop points invalid")
    mapped = [[970 + point[0] / 10, 690 + point[1] / 10]
              for point in (start, end)]
    for point, expected in zip(mapped, ([1000, 708], [1000, 744])):
        if math.dist(point, expected) > 10:
            raise ApartmentDoorError("Wall differs from frozen source oracle")
    if abs(mapped[0][0] - mapped[1][0]) > 3 or mapped[1][1] - mapped[0][1] < 25:
        raise ApartmentDoorError("Wall is not the expected vertical segment")
    plan = deepcopy(base_plan)
    nodes = {node["id"]: node for node in plan["nodes"]}
    lines = {line["id"]: line for line in plan["lines"]}
    if "horizontal3" not in lines or "horizontal4" not in lines:
        raise ApartmentDoorError("Door host walls are missing")
    left = nodes[lines["horizontal3"]["end"]]
    bottom = nodes[lines["horizontal4"]["start"]]
    if not (8.5 < left["x"] < 8.8 and 2.4 < left["y"] < 2.7 and
            9.2 < bottom["x"] < 9.5 and 1.8 < bottom["y"] < 2.1):
        raise ApartmentDoorError("Door host anchors differ")
    width = bottom["x"] - left["x"]
    if not 0.6 <= width <= 0.9:
        raise ApartmentDoorError("Door opening width differs")
    hinge = (bottom["x"], left["y"])
    tip = (hinge[0], hinge[1] + width)
    points = door_observation["points"]
    if set(points) != {"A", "B", "C"}:
        raise ApartmentDoorError("Door source point IDs differ")
    predicted = {"A": (left["x"], left["y"]), "B": hinge, "C": tip}
    for name, (x_m, y_m) in predicted.items():
        point = points[name]
        if not isinstance(point, list) or len(point) != 2 or \
                any(type(value) is not int for value in point):
            raise ApartmentDoorError("Door source point invalid")
        source_px = (915 + point[0] / 8, 640 + point[1] / 8)
        compiled_px = (392 + x_m * 893 / 13.86, 869 - y_m * 504 / 8)
        if math.dist(source_px, compiled_px) > 20 / 8 + 10:
            raise ApartmentDoorError(f"Door {name} differs from source geometry")
    # The source crop also confirms that the new wall joins the existing h4 line.
    top_px = (392 + hinge[0] * 893 / 13.86, 869 - hinge[1] * 504 / 8)
    bottom_px = (392 + bottom["x"] * 893 / 13.86,
                 869 - bottom["y"] * 504 / 8)
    if math.dist(top_px, mapped[0]) > 10 or math.dist(bottom_px, mapped[1]) > 10:
        raise ApartmentDoorError("Snapped jamb wall differs from source crop")
    # Existing lines may touch the jambs, but none may bridge the open interval.
    for line in plan["lines"]:
        a, b = nodes[line["start"]], nodes[line["end"]]
        if (abs(a["y"] - left["y"]) < 0.05 and
                abs(b["y"] - left["y"]) < 0.05 and
                min(a["x"], b["x"]) < hinge[0] - 0.02 and
                max(a["x"], b["x"]) > left["x"] + 0.02 and
                line["id"] != "horizontal3"):
            raise ApartmentDoorError("Another wall bridges the door opening")
    provenance = {"classification": "inferred", "confidence": 0.67,
                  "region_px": [990, 704, 1010, 749]}
    plan["nodes"].extend([
        {"id": "door-jamb-top", "x": hinge[0], "y": hinge[1],
         "source": deepcopy(provenance)},
        {"id": "door-leaf-tip", "x": tip[0], "y": tip[1],
         "source": {"classification": "inferred", "confidence": 0.7,
                    "region_px": [985, 655, 1000, 711]}}])
    plan["lines"].extend([
        {"id": "door-jamb-wall", "start": "door-jamb-top",
         "end": lines["horizontal4"]["start"], "layer": "0",
         "source": deepcopy(provenance)},
        {"id": "door-leaf", "start": "door-jamb-top", "end": "door-leaf-tip",
         "layer": "A-DOOR", "source": {"classification": "inferred",
                                     "confidence": 0.7,
                                     "region_px": [985, 655, 1000, 711]}}])
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (compiled["executable"] is not True or compiled["unsupported"] or
            compiled["quality_blockers"] or len(compiled["commands"]) != 34 or
            compiled["execution_steps"][-1]["command"] != "LAYER OFF OCS_DIM_REF"):
        raise ApartmentDoorError("Door composite failed PlanSpec gate")
    radius = width
    midpoint = (hinge[0] - radius / math.sqrt(2),
                hinge[1] + radius / math.sqrt(2))
    arc = {"planspec_id": "door-swing", "source_id": "door-swing",
           "part": "door_swing_arc", "command":
           f"ARC {_point_text(tip)} {_point_text(midpoint)} "
           f"{_point_text((left['x'], left['y']))}", "layer": "A-DOOR"}
    compiled["commands"].append(arc)
    compiled["execution_steps"][-1:-1] = [
        {"planspec_id": None, "command": "CLAYER A-DOOR", "layer": "A-DOOR"},
        arc,
        {"planspec_id": None, "command": "CLAYER 0", "layer": "0"}]
    wire = json.dumps(compiled["execution_steps"], sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    compiled["commands_sha256"] = hashlib.sha256(wire).hexdigest()
    metadata = {"schema_version": "m7-apartment-door-composite-1",
                "door_opening_width_m": round(width, 6),
                "door_hinge_m": list(hinge), "door_tip_m": list(tip),
                "source_observation_scope": "development_supervised",
                "cad_entities": 35, "acceptance_m7": False}
    return plan, compiled, metadata
