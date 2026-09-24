"""Add one source observed east bedroom divider to the partial apartment."""

from copy import deepcopy
import json
from pathlib import Path

from planspec import dry_run


BASE_SHA = "4FC786BB52F9417125A3E012F465A0EF694AA47D3A7EE9632FA5995C6C2A0A4D"
SOURCE_REGION = [1080, 605, 1293, 630]


class EastDividerError(ValueError):
    pass


def compose(base: dict, verdict: dict) -> tuple[dict, dict]:
    if (base.get("schema_version") != "planspec-11"
            or verdict.get("schema_version") != "m7-east-divider-verdict-1"
            or verdict.get("status") != "passed_observation_only"
            or verdict.get("cad_permitted") is not True):
        raise EastDividerError("Base or observation is not eligible")
    observed = verdict.get("observed_original_px")
    if (not isinstance(observed, list) or len(observed) != 2
            or any(not isinstance(point, list) or len(point) != 2 for point in observed)
            or max(abs(observed[0][0] - 1090), abs(observed[0][1] - 617),
                   abs(observed[1][0] - 1285), abs(observed[1][1] - 617)) > 8
            or abs(observed[0][1] - observed[1][1]) > 2):
        raise EastDividerError("Divider endpoints differ from frozen source region")
    # Snap horizontal wall ends to the centers of the already observed hosts.
    y = round((869 - (observed[0][1] + observed[1][1]) / 2) * 8 / 504, 6)
    plan = deepcopy(base)
    node_by_id = {node["id"]: node for node in plan["nodes"]}
    line_by_id = {line["id"]: line for line in plan["lines"]}
    if not {"wall3", "edge5"}.issubset(line_by_id):
        raise EastDividerError("Expected vertical hosts absent")
    west, east = line_by_id["wall3"], line_by_id["edge5"]
    if (abs(node_by_id[west["start"]]["x"] - 10.83346) > 1e-6
            or abs(node_by_id[east["start"]]["x"] - 13.891041) > 1e-6
            or not (node_by_id[west["start"]]["y"] > y > node_by_id[west["end"]]["y"])
            or not (node_by_id[east["start"]]["y"] > y > node_by_id[east["end"]]["y"])):
        raise EastDividerError("Directed host geometry differs")
    source = {"classification": "inferred", "confidence": 0.94,
              "region_px": SOURCE_REGION}
    west_node = "east-divider-west-junction"
    east_node = "east-divider-east-junction"
    current_ids = set(node_by_id) | set(line_by_id)
    new_ids = {west_node, east_node, "wall3-upper", "wall3-lower",
               "edge5-upper", "edge5-lower", "east-bedroom-divider"}
    if current_ids & new_ids:
        raise EastDividerError("Divider IDs already exist")
    plan["nodes"].extend([
        {"id": west_node, "x": node_by_id[west["start"]]["x"], "y": y,
         "source": source},
        {"id": east_node, "x": node_by_id[east["start"]]["x"], "y": y,
         "source": source},
    ])
    replacements = {
        "wall3": [dict(west, id="wall3-upper", end=west_node),
                  dict(west, id="wall3-lower", start=west_node)],
        "edge5": [dict(east, id="edge5-upper", end=east_node),
                  dict(east, id="edge5-lower", start=east_node)],
    }
    lines = []
    for line in plan["lines"]:
        lines.extend(replacements.get(line["id"], [line]))
    lines.append({"id": "east-bedroom-divider", "start": west_node,
                  "end": east_node, "layer": "0", "source": source})
    plan["lines"] = lines
    contours = plan.get("topology", {}).get("contours", [])
    if len(contours) != 1 or contours[0]["line_ids"].count("edge5") != 1:
        raise EastDividerError("Exterior contour reference differs")
    contour = contours[0]["line_ids"]
    position = contour.index("edge5")
    contour[position:position + 1] = ["edge5-upper", "edge5-lower"]
    compiled = dry_run(plan, capabilities={"layer_assignment"})
    if (not compiled["executable"] or compiled["unsupported"]
            or compiled["quality_blockers"] or len(compiled["commands"]) != 58):
        raise EastDividerError("Extended PlanSpec failed QA")
    return plan, compiled


def main():
    import argparse
    import hashlib
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--verdict", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base_path = args.base.resolve(strict=True)
    if hashlib.sha256(base_path.read_bytes()).hexdigest().upper() != BASE_SHA:
        raise EastDividerError("Base PlanSpec bytes differ")
    verdict_path = args.verdict.resolve(strict=True)
    plan, compiled = compose(json.loads(base_path.read_text(encoding="utf-8")),
                             json.loads(verdict_path.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"commands_sha256": compiled["commands_sha256"],
                      "entities": len(compiled["commands"])}, indent=2))


if __name__ == "__main__":
    main()
